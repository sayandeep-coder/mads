from __future__ import annotations

import json
import logging
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from adaptive.profile import AdaptiveProfile
from agent.session import Session, build_session, resolve_startup_project
from config.settings import get_settings
from planner.planner import Planner

logger = logging.getLogger(__name__)

_state: dict[str, object] = {}


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

    _state["base_settings"] = base_settings
    _state["planner"] = planner
    _state["adaptive_profile"] = adaptive_profile
    _state["session"] = session

    logger.info("Mads web server ready — connected: %s", session.mcp_manager.connected_servers)

    yield

    session = _state["session"]
    await session.mcp_manager.aclose()


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


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Stream tool-call activity and the final reply as Server-Sent Events.

    Event shape matches agent.agent.AgentEvent: tool_call_started ->
    tool_call_finished (possibly several, concurrent) -> final_response.
    """
    session: Session = _state["session"]  # type: ignore[assignment]
    planner: Planner = _state["planner"]  # type: ignore[assignment]

    async def event_generator():
        async for event in session.agent.stream(request.message):
            yield {"event": "message", "data": json.dumps(_event_to_sse_dict(event))}
        planner.record_action(request.message[:120])

    return EventSourceResponse(event_generator())


@app.post("/api/chat/reset")
async def reset_chat():
    """Start a fresh conversation without rebuilding MCP connections."""
    session: Session = _state["session"]  # type: ignore[assignment]
    session.agent.reset()
    return {"ok": True}


@app.get("/api/files")
async def download_file(path: str):
    """Serve a file Mads generated (PDF/PPTX/image) so the web UI can offer
    a download — the phone has no access to the Mac's disk otherwise.

    Scoped to the same allowed_roots boundary the filesystem/document tools
    already enforce, so this can't be used to read arbitrary paths off the
    Mac just because a request happens to specify one.
    """
    session: Session = _state["session"]  # type: ignore[assignment]
    settings = session.settings

    resolved = Path(path).expanduser().resolve()
    if not settings.is_path_allowed(resolved):
        raise HTTPException(status_code=403, detail="Path is outside the allowed directories")
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    media_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
    return FileResponse(
        resolved,
        media_type=media_type,
        filename=resolved.name,
        headers={"Content-Disposition": f'attachment; filename="{resolved.name}"'},
    )
