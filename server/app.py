from __future__ import annotations

import json
import logging
import mimetypes
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from adaptive.profile import AdaptiveProfile
from agent.agent import Agent
from agent.session import (
    Session,
    build_agent_for_session,
    build_browser_session,
    build_excel_session,
    build_session,
    resolve_startup_project,
)
from agent.system_prompt import apply_mode
from config.settings import get_settings
from planner.planner import Planner
from server.browser_bridge import browser_bridge, excel_bridge
from server.code_runner import handle_code_run
from server.store import chat_store

logger = logging.getLogger(__name__)

_state: dict[str, object] = {}

# Where files the web UI uploads (e.g. an attachment from ChatInput's "+"
# button) land on disk. Lives under the home directory, which
# settings.allowed_roots always includes, so an uploaded file is
# immediately readable by every filesystem-scoped tool/skill regardless of
# which project is currently active.
_UPLOAD_DIR = Path.home() / ".mads" / "uploads"

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def _configure_logging(log_level: str) -> None:
    logging.basicConfig(level=log_level)
    if log_level != "DEBUG":
        for noisy in ("httpx", "google_genai", "googleapiclient.discovery_cache", "mcp"):
            logging.getLogger(noisy).setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build one Mads session at server startup, matching the CLI's single-
    session model — see agent/session.py for the shared assembly logic.
    There's no console to prompt on here, so an unregistered workspace at
    the server's cwd is auto-registered rather than asked about (see
    resolve_startup_project's auto_register flag).
    """
    base_settings = get_settings()
    _configure_logging(base_settings.log_level)

    planner = Planner()
    adaptive_profile = AdaptiveProfile()
    resolve_startup_project(planner, Path.cwd(), auto_register=True)

    session = await build_session(base_settings, planner, adaptive_profile, Path.cwd())
    browser_session = await build_browser_session(base_settings, browser_bridge)
    excel_session = await build_excel_session(base_settings, excel_bridge)

    _state["base_settings"] = base_settings
    _state["planner"] = planner
    _state["adaptive_profile"] = adaptive_profile
    _state["session"] = session
    _state["browser_session"] = browser_session
    _state["excel_session"] = excel_session
    # One live Agent per stored chat conversation (session_id -> Agent),
    # all sharing `session`'s already-connected MCP tools — see
    # _get_chat_agent. Built lazily on first message, not for every row
    # ChatStore knows about, so having years of chat history sitting in
    # SQLite costs nothing until a given conversation is actually reopened.
    _state["chat_agents"] = {}

    logger.info("Mads web server ready — connected: %s", session.mcp_manager.connected_servers)

    yield

    session = _state["session"]
    await session.mcp_manager.aclose()
    browser_session: Session = _state["browser_session"]  # type: ignore[assignment]
    await browser_session.mcp_manager.aclose()
    excel_session: Session = _state["excel_session"]  # type: ignore[assignment]
    await excel_session.mcp_manager.aclose()


app = FastAPI(title="Mads", lifespan=lifespan)

# No authentication: this server is designed to run only on a trusted home
# LAN (the phone/browser reaches it via the Mac's local IP, e.g.
# 192.168.0.215:8000). Anyone who can reach this port can drive every tool
# Mads has — filesystem, Gmail, Spotify, etc. — with no login. That's a
# deliberate v1 tradeoff, not an oversight: never port-forward this or
# expose it beyond your home network. See README's Safety Model.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    # "study" | "research" | None — the web UI's "+" menu toggle; see
    # agent.system_prompt.apply_mode for what each one actually does.
    mode: str | None = None


class RenameRequest(BaseModel):
    title: str


def _derive_title(message: str) -> str:
    """First line of the opening message, trimmed to a sidebar-friendly
    length — same idea as Claude Code titling a session from its first
    prompt rather than asking the user to name it upfront.
    """
    first_line = message.strip().splitlines()[0] if message.strip() else "New chat"
    return first_line[:60] + ("…" if len(first_line) > 60 else "")


def _get_chat_agent(session_id: str) -> Agent:
    """Return the live Agent for this stored conversation, building it (and
    replaying any prior messages as history) on first use.
    """
    agents: dict[str, Agent] = _state["chat_agents"]  # type: ignore[assignment]
    if session_id in agents:
        return agents[session_id]

    main_session: Session = _state["session"]  # type: ignore[assignment]
    planner: Planner = _state["planner"]  # type: ignore[assignment]
    adaptive_profile: AdaptiveProfile = _state["adaptive_profile"]  # type: ignore[assignment]

    agent = build_agent_for_session(main_session, planner, adaptive_profile)

    prior = chat_store.list_messages(session_id)
    if prior:
        turns = [("user" if m["role"] == "user" else "model", m["text"]) for m in prior]
        agent.prime_history(turns)

    agents[session_id] = agent
    return agent


def _event_to_sse_dict(event) -> dict:
    payload = {"type": event.type}
    if event.tool_name is not None:
        payload["tool_name"] = event.tool_name
    if event.tool_args is not None:
        payload["tool_args"] = event.tool_args
    if event.is_error is not None:
        payload["is_error"] = event.is_error
    if event.text is not None:
        payload["text"] = event.text
    if event.result is not None:
        payload["result"] = event.result
    if event.call_id is not None:
        payload["call_id"] = event.call_id
    if event.output is not None:
        payload["output"] = event.output
    return payload


@app.get("/api/status")
async def status():
    session: Session = _state["session"]  # type: ignore[assignment]
    planner: Planner = _state["planner"]  # type: ignore[assignment]
    active_project = planner.projects.get_active()
    return {
        "connected_servers": session.mcp_manager.connected_servers,
        "active_project": active_project.name if active_project else None,
    }


@app.get("/api/sessions")
async def list_sessions():
    return {"sessions": chat_store.list_sessions()}


@app.post("/api/sessions")
async def create_session():
    return chat_store.create_session()


@app.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    if chat_store.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"messages": chat_store.list_messages(session_id)}


@app.patch("/api/sessions/{session_id}")
async def rename_session(session_id: str, request: RenameRequest):
    if chat_store.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    chat_store.rename_session(session_id, request.title.strip()[:60] or "New chat")
    return {"ok": True}


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    chat_store.delete_session(session_id)
    agents: dict[str, Agent] = _state["chat_agents"]  # type: ignore[assignment]
    agents.pop(session_id, None)
    return {"ok": True}


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Stream tool-call activity and the final reply as Server-Sent Events.

    Event shape matches agent.agent.AgentEvent: tool_call_started ->
    tool_call_finished (possibly several, concurrent) -> final_response.
    Every call belongs to a stored conversation (session_id): a brand new
    one is created automatically if the caller doesn't have one yet, and
    the exchange is persisted to ChatStore as it completes so the sidebar
    and history survive a server restart.
    """
    planner: Planner = _state["planner"]  # type: ignore[assignment]

    session_id = request.session_id
    is_new_session = session_id is None or chat_store.get_session(session_id) is None
    if is_new_session:
        created = chat_store.create_session(_derive_title(request.message))
        session_id = created["id"]

    agent = _get_chat_agent(session_id)
    # Stored/shown to the user as-is; the model only ever sees the
    # mode-prefixed version below, so history replay never re-injects a
    # mode instruction into a turn that didn't actually have one active.
    chat_store.add_message(session_id, "user", request.message)
    message_for_model = apply_mode(request.message, request.mode)

    async def event_generator():
        full_text = ""
        tool_calls: list[dict] = []
        files: list[dict] = []

        if is_new_session:
            yield {"event": "message", "data": json.dumps({"type": "session_created", "session_id": session_id})}

        async for event in agent.stream(message_for_model):
            if event.type == "tool_call_started":
                tool_calls.append({"name": event.tool_name, "args": event.tool_args})
            elif event.type == "tool_call_finished":
                result = event.result or {}
                path = result.get("path")
                if not event.is_error and isinstance(path, str) and path:
                    files.append({"path": path, "name": path.split("/")[-1]})
            elif event.type == "text_delta":
                full_text += event.text or ""
            elif event.type == "final_response":
                full_text = full_text or event.text or ""
            yield {"event": "message", "data": json.dumps(_event_to_sse_dict(event))}

        chat_store.add_message(session_id, "model", full_text, tool_calls=tool_calls, files=files)
        planner.record_action(request.message[:120])

    return EventSourceResponse(event_generator())


@app.websocket("/ws/browser")
async def browser_socket(websocket: WebSocket):
    """The Mads Chrome extension's side panel holds this connection open for
    its whole lifetime. Every browser_control tool call (see
    mcp_servers/servers/browser_control) sends a command down this same
    socket and awaits the matching reply — see server.browser_bridge for the
    request/response matching.
    """
    await browser_bridge.handle_connection(websocket)


@app.get("/api/browser/status")
async def browser_status():
    return {"connected": browser_bridge.is_connected}


@app.post("/api/browser/chat")
async def browser_chat(request: ChatRequest):
    """Same streaming contract as /api/chat, but driven by the browser
    session (browser_control + memory only) instead of the full CLI/web
    chat session — see agent.session.build_browser_session.
    """
    browser_session: Session = _state["browser_session"]  # type: ignore[assignment]

    async def event_generator():
        async for event in browser_session.agent.stream(request.message):
            yield {"event": "message", "data": json.dumps(_event_to_sse_dict(event))}

    return EventSourceResponse(event_generator())


@app.post("/api/browser/chat/reset")
async def browser_chat_reset():
    """Start a fresh browser-agent conversation (e.g. when the side panel reopens)."""
    browser_session: Session = _state["browser_session"]  # type: ignore[assignment]
    browser_session.agent.reset()
    return {"ok": True}


@app.websocket("/ws/excel")
async def excel_socket(websocket: WebSocket):
    """The Mads Excel task pane holds this connection open for its whole
    lifetime. Every excel_control tool call (see
    mcp_servers/servers/excel_control) sends a command down this same
    socket and awaits the matching reply — see server.browser_bridge for
    the request/response matching (excel_bridge is a separate instance of
    the same WebSocketCommandBridge the Chrome extension uses).
    """
    await excel_bridge.handle_connection(websocket)


@app.websocket("/ws/run")
async def run_socket(websocket: WebSocket):
    """Backs the web UI's "Run" button on a code block in a chat message —
    a user-triggered, interactive run (full stdin/stdout), completely
    separate from the agent's own run_command tool. See
    server.code_runner.handle_code_run for the actual protocol.
    """
    await handle_code_run(websocket)


@app.get("/api/excel/status")
async def excel_status():
    return {"connected": excel_bridge.is_connected}


@app.post("/api/excel/chat")
async def excel_chat(request: ChatRequest):
    """Same streaming contract as /api/chat, but driven by the Excel
    session (excel_control + memory only) — see agent.session.build_excel_session.
    """
    excel_session: Session = _state["excel_session"]  # type: ignore[assignment]

    async def event_generator():
        async for event in excel_session.agent.stream(request.message):
            yield {"event": "message", "data": json.dumps(_event_to_sse_dict(event))}

    return EventSourceResponse(event_generator())


@app.post("/api/excel/chat/reset")
async def excel_chat_reset():
    """Start a fresh Excel-agent conversation (e.g. when the task pane reopens)."""
    excel_session: Session = _state["excel_session"]  # type: ignore[assignment]
    excel_session.agent.reset()
    return {"ok": True}


@app.post("/api/chat/reset")
async def reset_chat():
    """Start a fresh conversation without rebuilding MCP connections."""
    session: Session = _state["session"]  # type: ignore[assignment]
    session.agent.reset()
    return {"ok": True}


@app.post("/api/upload")
async def upload_file(file: UploadFile):
    """Accept a file the web UI's chat input attached (via ChatInput's "+"
    button) and save it under _UPLOAD_DIR, returning the path the chat
    message can then reference so Gemini/the skills system can read it.

    No dedicated size cap beyond FastAPI/Starlette's own request-body
    handling — this server already runs trusted-LAN-only (see the
    CORSMiddleware comment above), same threat model as every other
    filesystem-touching endpoint here.
    """
    original_name = file.filename or "upload"
    safe_name = _UNSAFE_FILENAME_CHARS.sub("_", original_name).strip("._") or "upload"

    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = _UPLOAD_DIR / f"{int(time.time())}-{uuid.uuid4().hex[:8]}-{safe_name}"

    with dest.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            out.write(chunk)

    return {"path": str(dest), "name": original_name, "size_bytes": dest.stat().st_size}


def _resolve_generated_file(path: str) -> Path:
    """Shared path check for every endpoint that serves a file Mads
    generated — same allowed_roots boundary the filesystem/document tools
    already enforce, so none of these can be used to reach arbitrary paths
    off the Mac just because a request happens to specify one.
    """
    session: Session = _state["session"]  # type: ignore[assignment]
    settings = session.settings

    resolved = Path(path).expanduser().resolve()
    if not settings.is_path_allowed(resolved):
        raise HTTPException(status_code=403, detail="Path is outside the allowed directories")
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return resolved


@app.get("/api/files")
async def download_file(path: str):
    """Serve a file Mads generated (PDF/PPTX/image) so the web UI can offer
    a download — the phone has no access to the Mac's disk otherwise.
    """
    resolved = _resolve_generated_file(path)
    media_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
    return FileResponse(
        resolved,
        media_type=media_type,
        filename=resolved.name,
        headers={"Content-Disposition": f'attachment; filename="{resolved.name}"'},
    )


@app.get("/api/files/preview")
async def preview_file(path: str):
    """Same file, but served inline rather than as an attachment — for the
    web UI's in-app preview panel (an <iframe src="..."> for a PDF, e.g.).
    A browser won't render a PDF inline if the server says
    Content-Disposition: attachment, so this is a genuinely different
    response, not just download_file with a different name.
    """
    resolved = _resolve_generated_file(path)
    media_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
    return FileResponse(
        resolved,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{resolved.name}"'},
    )


@app.get("/api/files/xlsx-preview")
async def preview_xlsx(path: str):
    """Read every sheet of a generated .xlsx workbook and return it as
    plain JSON rows for the web UI to render as an HTML table — there's no
    native browser renderer for spreadsheets the way there is for PDFs, so
    the preview panel builds its own simple table view from this data
    rather than trying to embed the real file.
    """
    resolved = _resolve_generated_file(path)
    if resolved.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise HTTPException(status_code=400, detail=f"Not a spreadsheet: {resolved.suffix!r}")

    from mcp_servers.servers.document_intelligence._xlsx_preview import read_all_sheets_for_preview

    return read_all_sheets_for_preview(resolved)
