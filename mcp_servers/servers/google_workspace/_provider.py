from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from typing import Any, Callable

from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError
from mcp import Tool

from auth.google_oauth import get_credentials
from config.settings import Settings
from mcp_servers.manager import ToolCallResult
from mcp_servers.servers.google_workspace import _calendar, _docs, _drive, _gmail, _sheets
from mcp_servers.servers.google_workspace._schemas import ALL_TOOLS

logger = logging.getLogger(__name__)

ALL_SCOPES = (
    _gmail.GMAIL_SCOPES
    + _calendar.CALENDAR_SCOPES
    + _drive.DRIVE_SCOPES
    + _docs.DOCS_SCOPES
    + _sheets.SHEETS_SCOPES
)


class GoogleWorkspaceProvider:
    """Single unified tool provider for Google Workspace: Gmail, Calendar, Drive, Docs, Sheets.

    Backed by direct Google REST APIs (via google-api-python-client) rather
    than Google's official per-app MCP servers, since those don't cover
    write operations (send, delete, patch) or Docs/Sheets at all. To the
    agent and MCPManager this is indistinguishable from any other
    ToolProvider — same list_tools()/call_tool() surface, so the LLM never
    knows (or needs to know) which Google service or transport backs a call.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._services: dict[str, Resource] = {}

    @property
    def name(self) -> str:
        return "google_workspace"

    @staticmethod
    def is_available(settings: Settings) -> bool:
        return bool(
            settings.google_client_id
            and settings.google_client_secret
            and settings.oauth_token_encryption_key
        )

    async def connect(self, exit_stack: AsyncExitStack) -> None:
        # OAuth (including the one-time browser consent flow) is blocking
        # I/O; run it off the event loop so it doesn't stall the REPL.
        credentials = await asyncio.to_thread(get_credentials, self._settings, ALL_SCOPES)
        self._services = {
            "gmail": build("gmail", "v1", credentials=credentials),
            "calendar": build("calendar", "v3", credentials=credentials),
            "drive": build("drive", "v3", credentials=credentials),
            "docs": build("docs", "v1", credentials=credentials),
            "sheets": build("sheets", "v4", credentials=credentials),
        }

    def list_tools(self) -> list[Tool]:
        return list(ALL_TOOLS)

    async def call_tool(self, name: str, arguments: dict) -> ToolCallResult:
        if not self._services:
            raise RuntimeError("connect() must be called before call_tool()")

        try:
            result = await asyncio.to_thread(self._dispatch, name, arguments)
        except HttpError as exc:
            logger.exception("Google Workspace API call %r failed", name)
            return ToolCallResult(text=f"Google API error: {exc}", is_error=True)
        except Exception as exc:  # noqa: BLE001 — surface any failure back to the model
            logger.exception("Google Workspace call %r failed", name)
            return ToolCallResult(text=f"Error: {exc}", is_error=True)

        return ToolCallResult(text=str(result), is_error=False)

    def _dispatch(self, name: str, arguments: dict) -> Any:
        dispatch_table: dict[str, tuple[Resource, Callable[..., Any]]] = {
            "search_emails": (self._services["gmail"], _gmail.search_emails),
            "read_email": (self._services["gmail"], _gmail.read_email),
            "draft_email": (self._services["gmail"], _gmail.draft_email),
            "send_email": (self._services["gmail"], _gmail.send_email),
            "list_events": (self._services["calendar"], _calendar.list_events),
            "create_event": (self._services["calendar"], _calendar.create_event),
            "update_event": (self._services["calendar"], _calendar.update_event),
            "delete_event": (self._services["calendar"], _calendar.delete_event),
            "search_drive": (self._services["drive"], _drive.search_drive),
            "list_files": (self._services["drive"], _drive.list_files),
            "read_file_content": (self._services["drive"], _drive.read_file_content),
            "create_file": (self._services["drive"], _drive.create_file),
            "copy_file": (self._services["drive"], _drive.copy_file),
            "read_document": (self._services["docs"], _docs.read_document),
            "create_document": (self._services["docs"], _docs.create_document),
            "update_document": (self._services["docs"], _docs.update_document),
            "read_sheet": (self._services["sheets"], _sheets.read_sheet),
            "append_sheet": (self._services["sheets"], _sheets.append_sheet),
            "update_sheet": (self._services["sheets"], _sheets.update_sheet),
            "create_sheet": (self._services["sheets"], _sheets.create_sheet),
        }

        entry = dispatch_table.get(name)
        if entry is None:
            raise ValueError(f"Unknown google_workspace tool: {name!r}")

        service, func = entry
        return func(service, **arguments)
