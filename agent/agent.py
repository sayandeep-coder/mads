from __future__ import annotations

import ast
import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

from google import genai
from google.genai import types as genai_types

from agent.system_prompt import build_system_prompt
from agent.tools import build_gemini_tools
from config.settings import Settings
from mcp_servers.manager import MCPManager, MCPToolNotFoundError

logger = logging.getLogger(__name__)

_MAX_TOOL_CALL_ROUNDS = 8


def _parse_tool_output(response_payload: dict[str, Any]) -> dict[str, Any]:
    """Best-effort structured view of a tool's result, for consumers that
    want to react to it programmatically (e.g. the web UI offering a
    download when a tool wrote a file) — without changing what Gemini
    itself receives.

    Tool providers return their result as ToolCallResult.text, built with
    str(dict) rather than json.dumps across the codebase (Gemini reads it
    as loose text either way, so this was never tightened). ast.literal_eval
    safely parses that Python-literal repr back into real Python types —
    unlike eval(), it only accepts literals, never arbitrary code.
    """
    output = response_payload.get("output")
    if not isinstance(output, str):
        return response_payload
    try:
        parsed = ast.literal_eval(output)
    except (ValueError, SyntaxError):
        return response_payload
    return parsed if isinstance(parsed, dict) else response_payload


@dataclass(frozen=True, slots=True)
class AgentEvent:
    """One step of an Agent.stream() run — a tool call starting/finishing,
    or the final text reply. Consumers (the CLI, the web backend) render
    each kind differently; Agent itself doesn't know or care who's listening.
    """

    type: Literal["tool_call_started", "tool_call_finished", "text_delta", "final_response"]
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    is_error: bool | None = None
    text: str | None = None
    # The tool's raw JSON result, only set on tool_call_finished — lets
    # consumers (the web frontend) notice things like a generated file's
    # path without Agent needing to know what any particular tool means.
    result: dict[str, Any] | None = None


class Agent:
    """The single Mads agent: one Gemini chat session, many MCP-backed tools.

    Gemini alone decides whether a tool call is needed, which tool(s) to
    call, and whether to chain multiple calls — this class only executes
    what Gemini asks for and feeds results back.
    """

    def __init__(
        self,
        settings: Settings,
        mcp_manager: MCPManager,
        memory_context: str = "",
        project_context: str = "",
        adaptive_context: str = "",
        browser_mode: bool = False,
        excel_mode: bool = False,
    ) -> None:
        self._mcp = mcp_manager
        self._client = genai.Client(api_key=settings.gemini_api_key)

        tools = build_gemini_tools(mcp_manager.list_tools())
        config = genai_types.GenerateContentConfig(
            system_instruction=build_system_prompt(
                memory_context,
                project_context,
                adaptive_context,
                browser_mode=browser_mode,
                excel_mode=excel_mode,
            ),
            tools=tools or None,
        )
        self._model = settings.model
        self._config = config
        self.reset()

    def reset(self) -> None:
        """Start a fresh model conversation while keeping tools and context."""
        self._chat = self._client.chats.create(model=self._model, config=self._config)

    async def send(self, message: str) -> str:
        """Send a user message, resolving any tool calls Gemini requests, and return the final reply.

        Thin wrapper around stream() for callers (the CLI) that only want
        the end result, not live tool-call visibility.
        """
        final_text = ""
        async for event in self.stream(message):
            if event.type == "final_response":
                final_text = event.text or ""
        return final_text

    async def stream(self, message: str) -> AsyncIterator[AgentEvent]:
        """Send a user message, yielding an AgentEvent for every tool call
        as it starts and finishes, text_delta as the reply is generated,
        and finally the complete reply text.

        Each round uses send_message_stream rather than send_message so
        text actually arrives incrementally instead of all at once at the
        end — a round that asks for tool calls streams no text (Gemini
        emits those as a single chunk with no .text, confirmed against the
        live API), so text_delta only ever fires on the round that produces
        the final reply.
        """
        full_text = ""
        next_message: Any = message

        for _ in range(_MAX_TOOL_CALL_ROUNDS):
            function_calls: list[genai_types.FunctionCall] = []
            round_text = ""

            async for chunk in self._stream_chunks(next_message):
                if chunk.text:
                    round_text += chunk.text
                    full_text += chunk.text
                    yield AgentEvent(type="text_delta", text=chunk.text)
                if chunk.function_calls:
                    function_calls = chunk.function_calls

            if not function_calls:
                break

            for call in function_calls:
                yield AgentEvent(type="tool_call_started", tool_name=call.name, tool_args=call.args or {})

            # Independent tool calls Gemini requested in the same turn (e.g.
            # research mode's Context7 + GitHub + Fetch + YouTube lookups)
            # run concurrently rather than one-by-one — same one-agent
            # architecture, just not needlessly serialized. Events for
            # calls that finish first are yielded first; the client sees
            # completion order, not request order.
            queue: asyncio.Queue[tuple[genai_types.FunctionCall, genai_types.Part]] = asyncio.Queue()

            async def _run(call: genai_types.FunctionCall) -> None:
                part = await self._execute_function_call(call)
                await queue.put((call, part))

            tasks = [asyncio.create_task(_run(call)) for call in function_calls]
            response_parts: list[genai_types.Part] = []
            for _ in function_calls:
                call, part = await queue.get()
                response_payload = part.function_response.response or {}
                is_error = "error" in response_payload
                yield AgentEvent(
                    type="tool_call_finished",
                    tool_name=call.name,
                    is_error=is_error,
                    result=_parse_tool_output(response_payload),
                )
                response_parts.append(part)
            await asyncio.gather(*tasks)

            next_message = response_parts

        yield AgentEvent(type="final_response", text=full_text)

    async def _stream_chunks(self, message: Any) -> AsyncIterator[genai_types.GenerateContentResponse]:
        """Bridge the SDK's sync streaming iterator (send_message_stream
        blocks on network I/O per chunk) onto the async world by running it
        in a thread and forwarding each chunk through a queue — so a slow
        model response doesn't stall the event loop other requests share.
        """
        queue: asyncio.Queue[Any] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        _SENTINEL = object()

        def _produce() -> None:
            try:
                for chunk in self._chat.send_message_stream(message):
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
            except Exception as exc:  # noqa: BLE001 — forward the failure into the async side
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)

        thread = asyncio.get_running_loop().run_in_executor(None, _produce)
        try:
            while True:
                item = await queue.get()
                if item is _SENTINEL:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            await thread

    async def _execute_function_call(
        self, call: genai_types.FunctionCall
    ) -> genai_types.Part:
        assert call.name is not None
        logger.info("Tool call: %s(%s)", call.name, call.args)

        try:
            result = await self._mcp.call_tool(call.name, call.args or {})
            payload = {"error": result.text} if result.is_error else {"output": result.text}
        except MCPToolNotFoundError as exc:
            payload = {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001 — surface any tool failure back to the model
            logger.exception("Tool call %r failed", call.name)
            payload = {"error": f"Tool execution failed: {exc}"}

        return genai_types.Part.from_function_response(name=call.name, response=payload)
