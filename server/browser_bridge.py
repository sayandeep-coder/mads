from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

# How long a browser-control tool call waits for the extension to act on a
# page and report back before giving up — generous because a real page
# navigation or a slow site can take several seconds.
_COMMAND_TIMEOUT_SECONDS = 20.0


class ClientNotConnectedError(RuntimeError):
    """Raised when a tool is called but no client (browser extension, Excel add-in, ...) is connected."""


class ClientCommandError(RuntimeError):
    """Raised when the connected client reports that a command failed."""


# Old names kept as aliases — browser_control's provider and error handling
# already import these; renaming them too is unnecessary churn for what's
# now a generic mechanism, not something specific to the browser case.
BrowserNotConnectedError = ClientNotConnectedError
BrowserCommandError = ClientCommandError


class WebSocketCommandBridge:
    """Holds one live WebSocket connection from a client UI (a Chrome side
    panel, an Office task pane, ...) and turns it into a request/response
    call, so a tool provider can `await bridge.send_command(...)` exactly
    like it would call a local function — the agent's tool-calling loop
    (agent/agent.py) never needs to know the "function" actually executes
    inside someone's browser tab or Excel workbook a network hop away.

    Single-connection by design: Mads assumes one client of a given kind
    connected at a time, matching the one-agent-session model the rest of
    the app already uses (see agent/session.py). A second client of the
    same kind connecting replaces the first. Different kinds (browser vs.
    Excel) get their own bridge instance — see browser_bridge/excel_bridge
    below — so they never contend for the same pending-request table.
    """

    def __init__(self, client_label: str) -> None:
        self._client_label = client_label
        self._socket: WebSocket | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}

    @property
    def is_connected(self) -> bool:
        return self._socket is not None

    async def handle_connection(self, socket: WebSocket) -> None:
        await socket.accept()
        if self._socket is not None:
            logger.info("New %s connected — replacing previous connection", self._client_label)
            await self._fail_all_pending(f"{self._client_label} reconnected before this command finished")
        self._socket = socket
        logger.info("%s connected", self._client_label)

        try:
            while True:
                message = await socket.receive_json()
                self._handle_message(message)
        except WebSocketDisconnect:
            pass
        finally:
            if self._socket is socket:
                self._socket = None
            await self._fail_all_pending(f"{self._client_label} disconnected")
            logger.info("%s disconnected", self._client_label)

    def _handle_message(self, message: dict[str, Any]) -> None:
        request_id = message.get("request_id")
        if not isinstance(request_id, str):
            logger.warning("Dropping %s message with no request_id: %r", self._client_label, message)
            return
        future = self._pending.pop(request_id, None)
        if future is None or future.done():
            return
        future.set_result(message)

    async def _fail_all_pending(self, reason: str) -> None:
        pending, self._pending = self._pending, {}
        for future in pending.values():
            if not future.done():
                future.set_exception(ClientNotConnectedError(reason))

    async def send_command(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Send one action to the connected client and wait for its reply.

        Returns the client's `result` payload on success. Raises
        ClientNotConnectedError if no client is connected, or
        ClientCommandError if the client reports the action failed (e.g.
        "no element matches that id" after a page changed, or an Office.js
        call threw).
        """
        if self._socket is None:
            raise ClientNotConnectedError(
                f"No {self._client_label} is connected. Ask the user to open it first."
            )

        request_id = uuid.uuid4().hex
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future

        try:
            await self._socket.send_json({"request_id": request_id, "action": action, "payload": payload})
        except Exception as exc:  # noqa: BLE001 — socket write failed, surface as disconnect
            self._pending.pop(request_id, None)
            raise ClientNotConnectedError(f"Failed to reach the {self._client_label}: {exc}") from exc

        try:
            response = await asyncio.wait_for(future, timeout=_COMMAND_TIMEOUT_SECONDS)
        except asyncio.TimeoutError as exc:
            self._pending.pop(request_id, None)
            raise ClientCommandError(
                f"The {self._client_label} didn't respond to {action!r} within {_COMMAND_TIMEOUT_SECONDS:.0f}s."
            ) from exc

        if not response.get("ok", False):
            raise ClientCommandError(str(response.get("error") or "Unknown client-side error"))

        return response.get("result") or {}


# Old name kept as an alias so browser_control's imports don't need to change.
BrowserBridge = WebSocketCommandBridge

# One bridge per client kind per server process — mirrors the module-level
# `_state` dict app.py already uses for the single Session, same
# single-process app.
browser_bridge = WebSocketCommandBridge("browser extension")
excel_bridge = WebSocketCommandBridge("Excel add-in")
