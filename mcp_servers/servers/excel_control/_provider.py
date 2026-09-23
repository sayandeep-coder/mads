from __future__ import annotations

import logging
from contextlib import AsyncExitStack

from mcp import Tool

from mcp_servers.manager import ToolCallResult
from mcp_servers.servers.excel_control._schemas import EXCEL_CONTROL_TOOLS
from server.browser_bridge import ClientCommandError, ClientNotConnectedError, WebSocketCommandBridge

logger = logging.getLogger(__name__)

_ACTION_NAMES = {tool.name for tool in EXCEL_CONTROL_TOOLS}


class ExcelControlProvider:
    """Tools that drive the user's actual open Excel workbook through the
    Mads Office add-in's task pane: list sheets, read/write ranges, read
    the current selection. Every tool call is a round trip over
    server.browser_bridge.excel_bridge to whatever workbook the task pane
    is currently open in — this module holds no Office.js logic itself
    (that lives in excel-addin/taskpane.js, which is the only place with
    access to the Excel.run() API), it only forwards the action and waits
    for the task pane to report back what happened.
    """

    def __init__(self, bridge: WebSocketCommandBridge) -> None:
        self._bridge = bridge

    @property
    def name(self) -> str:
        return "excel_control"

    async def connect(self, exit_stack: AsyncExitStack) -> None:
        pass

    def list_tools(self) -> list[Tool]:
        return list(EXCEL_CONTROL_TOOLS)

    async def call_tool(self, name: str, arguments: dict) -> ToolCallResult:
        if name not in _ACTION_NAMES:
            return ToolCallResult(text=f"Unknown excel_control tool: {name!r}", is_error=True)

        try:
            result = await self._bridge.send_command(name, arguments)
        except (ClientNotConnectedError, ClientCommandError) as exc:
            return ToolCallResult(text=str(exc), is_error=True)
        except Exception as exc:  # noqa: BLE001 — surface any failure back to the model
            logger.exception("excel_control tool %r failed", name)
            return ToolCallResult(text=f"Error: {exc}", is_error=True)

        return ToolCallResult(text=str(result), is_error=False)
