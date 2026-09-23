from __future__ import annotations

import logging
from contextlib import AsyncExitStack

from mcp import Tool

from mcp_servers.manager import ToolCallResult
from mcp_servers.servers.browser_control._schemas import BROWSER_CONTROL_TOOLS
from server.browser_bridge import BrowserBridge, BrowserCommandError, BrowserNotConnectedError

logger = logging.getLogger(__name__)

_ACTION_NAMES = {tool.name for tool in BROWSER_CONTROL_TOOLS}


class BrowserControlProvider:
    """Tools that drive the user's actual Chrome tab through the Mads side
    panel extension: extract the page, click, type, navigate. Every tool
    call is a round trip over server.browser_bridge to whatever page the
    user currently has the extension open on — this module holds no DOM
    logic itself, it only forwards the action and waits for the extension's
    content script to report back what happened.
    """

    def __init__(self, bridge: BrowserBridge) -> None:
        self._bridge = bridge

    @property
    def name(self) -> str:
        return "browser_control"

    async def connect(self, exit_stack: AsyncExitStack) -> None:
        pass

    def list_tools(self) -> list[Tool]:
        return list(BROWSER_CONTROL_TOOLS)

    async def call_tool(self, name: str, arguments: dict) -> ToolCallResult:
        if name not in _ACTION_NAMES:
            return ToolCallResult(text=f"Unknown browser_control tool: {name!r}", is_error=True)

        try:
            result = await self._bridge.send_command(name, arguments)
        except (BrowserNotConnectedError, BrowserCommandError) as exc:
            return ToolCallResult(text=str(exc), is_error=True)
        except Exception as exc:  # noqa: BLE001 — surface any failure back to the model
            logger.exception("browser_control tool %r failed", name)
            return ToolCallResult(text=f"Error: {exc}", is_error=True)

        return ToolCallResult(text=str(result), is_error=False)
