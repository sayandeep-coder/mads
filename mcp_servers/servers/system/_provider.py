from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from functools import partial
from typing import Any, Callable

from mcp import Tool

from config.settings import Settings
from mcp_servers.manager import ToolCallResult
from mcp_servers.servers.system import _apps, _destructive, _sysinfo
from mcp_servers.servers.system._schemas import SYSTEM_TOOLS

logger = logging.getLogger(__name__)


class SystemProvider:
    """Native macOS system control: apps, files, system info, and (later) volume,
    clipboard, screenshots, notifications, brightness, network status.

    Every capability function returns a structured {"success": ...} envelope
    itself — call_tool never needs to interpret raw shell output, and the
    agent never knows these are backed by subprocess/osascript/psutil rather
    than an MCP server.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def name(self) -> str:
        return "system"

    @staticmethod
    def is_available(settings: Settings) -> bool:
        return True  # local-only, no credentials required

    async def connect(self, exit_stack: AsyncExitStack) -> None:
        pass

    def list_tools(self) -> list[Tool]:
        return list(SYSTEM_TOOLS)

    async def call_tool(self, name: str, arguments: dict) -> ToolCallResult:
        dispatch_table: dict[str, Callable[..., dict[str, Any]]] = {
            "open_app": _apps.open_app,
            "quit_app": _apps.quit_app,
            "list_running_apps": _apps.list_running_apps,
            "battery_status": _sysinfo.battery_status,
            "cpu_usage": _sysinfo.cpu_usage,
            "memory_usage": _sysinfo.memory_usage,
            "disk_usage": _sysinfo.disk_usage,
            "uptime": _sysinfo.uptime,
            "shutdown": _destructive.shutdown,
            "restart": _destructive.restart,
            "empty_trash": _destructive.empty_trash,
            "delete_files": partial(_destructive.delete_files, self._settings),
            "terminate_process": _destructive.terminate_process,
        }
        func = dispatch_table.get(name)
        if func is None:
            return ToolCallResult(text=f"Unknown system tool: {name!r}", is_error=True)

        try:
            result = await asyncio.to_thread(func, **arguments)
        except Exception as exc:  # noqa: BLE001 — surface any failure back to the model
            logger.exception("System tool %r failed", name)
            result = {"success": False, "error": "unexpected_error", "message": str(exc)}

        return ToolCallResult(text=str(result), is_error=not result.get("success", False))
