from __future__ import annotations

import asyncio
import logging
import os
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from mcp import ClientSession, StdioServerParameters, Tool
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

# How long one provider's connect() gets before it's given up on. Exists
# because a stdio MCP server that needs a one-time interactive OAuth
# login (e.g. the mcp-remote-bridged commerce connectors — Swiggy, Zepto,
# Groww, Zomato) has no cached token on first use and will sit waiting on
# a browser flow nobody's completed; with no timeout, that one provider's
# await blocks every provider connected after it, and MCPManager.connect()
# is what server/app.py's lifespan awaits — so one stuck login silently
# hangs the entire backend's startup, not just that one connector.
_CONNECT_TIMEOUT_SECONDS = 20


class MCPToolNotFoundError(RuntimeError):
    """Raised when a requested tool isn't registered on any connected provider."""


@dataclass(frozen=True, slots=True)
class ToolCallResult:
    """The outcome of invoking a tool, regardless of which provider backs it."""

    text: str
    is_error: bool


@runtime_checkable
class ToolProvider(Protocol):
    """A source of callable tools: a stdio MCP server, or a local implementation.

    The agent only ever sees this interface, so it cannot tell (and does not
    need to know) whether a given tool is backed by a spawned MCP subprocess
    or by Python code calling a REST API directly.
    """

    @property
    def name(self) -> str: ...

    async def connect(self, exit_stack: AsyncExitStack) -> None: ...

    def list_tools(self) -> list[Tool]: ...

    async def call_tool(self, name: str, arguments: dict) -> ToolCallResult: ...


class StdioToolProvider:
    """A ToolProvider backed by a real MCP server spawned as a subprocess."""

    def __init__(self, name: str, params: StdioServerParameters) -> None:
        self._name = name
        self._params = params
        self._session: ClientSession | None = None
        self._tools: list[Tool] = []

    @property
    def name(self) -> str:
        return self._name

    async def connect(self, exit_stack: AsyncExitStack) -> None:
        # mcp-remote (the stdio bridge the commerce connectors — Swiggy,
        # Zepto, Groww, Zomato — use to reach a remote OAuth-gated MCP
        # server) prints its "open this URL to log in" message to stderr,
        # same channel as every routine startup banner — suppressing it
        # unconditionally (the branch below) silently swallowed the one
        # thing a first-time connect actually needs the user to see.
        is_oauth_bridge = self._params.command == "npx" and "mcp-remote" in self._params.args
        if is_oauth_bridge or logger.isEnabledFor(logging.DEBUG):
            transport = stdio_client(self._params)
        else:
            # MCP servers commonly print startup banners and routine INFO logs to
            # stderr. Keep the normal UI quiet; DEBUG mode restores that output.
            errlog = exit_stack.enter_context(open(os.devnull, "w"))
            transport = stdio_client(self._params, errlog=errlog)

        read, write = await exit_stack.enter_async_context(transport)
        session = await exit_stack.enter_async_context(ClientSession(read, write))
        await session.initialize()

        list_result = await session.list_tools()
        self._session = session
        self._tools = list_result.tools

    def list_tools(self) -> list[Tool]:
        return list(self._tools)

    async def call_tool(self, name: str, arguments: dict) -> ToolCallResult:
        assert self._session is not None, "connect() must be called before call_tool()"
        result = await self._session.call_tool(name, arguments)
        text = "\n".join(block.text for block in result.content if hasattr(block, "text"))
        return ToolCallResult(text=text, is_error=bool(result.isError))


class MCPManager:
    """Owns a set of tool providers and presents them as one flat tool namespace.

    Each provider's tools are listed and dispatched by name, so the agent
    never needs to know which provider backs which capability.
    """

    def __init__(self) -> None:
        self._exit_stack = AsyncExitStack()
        self._providers: dict[str, ToolProvider] = {}
        self._tool_to_provider: dict[str, str] = {}
        self._tools: dict[str, Tool] = {}
        self._connected: list[str] = []

    @property
    def connected_servers(self) -> list[str]:
        return list(self._connected)

    async def connect(self, providers: list[ToolProvider]) -> None:
        """Connect to each provider at startup, skipping (and logging) any
        that fail or time out — see connect_one for the shared logic and
        _CONNECT_TIMEOUT_SECONDS for why a timeout is load-bearing here.
        """
        for provider in providers:
            await self.connect_one(provider)

    async def connect_one(self, provider: ToolProvider) -> tuple[bool, str | None]:
        """Connect a single provider, on a timeout so a stuck interactive
        login (OAuth browser flow nobody's completed) can't hang the
        caller forever. Used both by connect() at startup and by
        server/app.py's on-demand "Connect" endpoint for the commerce
        connectors (Swiggy/Zepto/Groww/Zomato), which are never auto-
        connected at startup — only ever by an explicit click, since each
        one's first connection pops open a real OAuth login for a real
        account. Returns (connected, error_message).
        """
        if provider.name in self._providers:
            return True, None  # already connected — calling again is a no-op, not an error
        try:
            await asyncio.wait_for(self._connect_one(provider), timeout=_CONNECT_TIMEOUT_SECONDS)
            self._connected.append(provider.name)
            return True, None
        except TimeoutError:
            message = (
                f"Didn't connect within {_CONNECT_TIMEOUT_SECONDS}s — likely waiting on an "
                "interactive login (OAuth browser flow) nobody completed."
            )
            logger.error("Provider %r: %s", provider.name, message)
            return False, message
        except Exception as exc:  # noqa: BLE001 — surface any failure back to the caller
            logger.exception("Failed to connect provider %r", provider.name)
            return False, str(exc)

    async def _connect_one(self, provider: ToolProvider) -> None:
        await provider.connect(self._exit_stack)

        tools = provider.list_tools()
        for tool in tools:
            if tool.name in self._tool_to_provider:
                logger.warning(
                    "Tool name collision: %r from provider %r shadowed by %r",
                    tool.name,
                    provider.name,
                    self._tool_to_provider[tool.name],
                )
                continue
            self._tool_to_provider[tool.name] = provider.name
            self._tools[tool.name] = tool

        self._providers[provider.name] = provider
        logger.debug("Connected provider %r with %d tool(s)", provider.name, len(tools))

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    async def call_tool(self, name: str, arguments: dict) -> ToolCallResult:
        provider_name = self._tool_to_provider.get(name)
        if provider_name is None:
            raise MCPToolNotFoundError(f"No connected provider exposes tool {name!r}")

        provider = self._providers[provider_name]
        return await provider.call_tool(name, arguments)

    async def aclose(self) -> None:
        await self._exit_stack.aclose()
