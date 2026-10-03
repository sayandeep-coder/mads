from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from config.settings import SCRATCH_DIR

logger = logging.getLogger(__name__)

# Maps the language tag a fenced code block carries (```python, ```js, ...)
# to the command that runs a file of that kind. `-u` keeps Python's stdout
# unbuffered — without it, a script's `input("name: ")` prompt sits in
# Python's internal buffer and never reaches the user until the buffer
# flushes, which defeats the entire point of an interactive terminal.
_LANGUAGE_RUNNERS: dict[str, tuple[str, list[str]]] = {
    "python": (".py", ["python3", "-u"]),
    "py": (".py", ["python3", "-u"]),
    "javascript": (".js", ["node"]),
    "js": (".js", ["node"]),
    "node": (".js", ["node"]),
    "typescript": (".ts", ["npx", "-y", "tsx"]),
    "ts": (".ts", ["npx", "-y", "tsx"]),
    "bash": (".sh", ["bash"]),
    "sh": (".sh", ["bash"]),
    "shell": (".sh", ["bash"]),
}


async def _send_json(websocket: WebSocket, payload: dict) -> bool:
    """Best-effort send — the client may have already gone away (closed tab,
    clicked Stop then immediately navigated off), which is routine here, not
    an error worth logging."""
    if websocket.client_state != WebSocketState.CONNECTED:
        return False
    try:
        await websocket.send_json(payload)
        return True
    except Exception:  # noqa: BLE001
        return False


async def handle_code_run(websocket: WebSocket) -> None:
    """Backs the "Run" button on a code block in the chat: the user (not
    the agent) triggers this, so it's a separate, simpler path from
    Agent._run_shell_command — one process per connection, full-duplex
    (the user can type input into the running program), torn down the
    moment the socket closes.

    Protocol (JSON frames):
      client -> {"action": "start", "language": "python", "code": "..."}
      client -> {"action": "input", "text": "..."}   (appends \\n, like Enter)
      client -> {"action": "stop"}
      server -> {"type": "output", "text": "..."}    (raw chunk, not lines —
                 see the read loop below for why)
      server -> {"type": "exit", "code": <int>}
      server -> {"type": "error", "message": "..."}
    """
    await websocket.accept()
    process: asyncio.subprocess.Process | None = None
    script_path: Path | None = None

    try:
        start_msg = await websocket.receive_json()
        if start_msg.get("action") != "start":
            await _send_json(websocket, {"type": "error", "message": "Expected a 'start' message first."})
            return

        language = str(start_msg.get("language", "")).lower().strip()
        code = start_msg.get("code")
        runner = _LANGUAGE_RUNNERS.get(language)
        if runner is None or not isinstance(code, str) or not code.strip():
            await _send_json(
                websocket,
                {"type": "error", "message": f"Can't run language {language!r} — nothing to execute."},
            )
            return

        extension, command_prefix = runner
        SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
        script_path = SCRATCH_DIR / f"run_{uuid.uuid4().hex[:10]}{extension}"
        script_path.write_text(code)

        try:
            process = await asyncio.create_subprocess_exec(
                *command_prefix,
                str(script_path),
                cwd=str(SCRATCH_DIR),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except Exception as exc:  # noqa: BLE001 — e.g. node/npx isn't installed
            await _send_json(websocket, {"type": "error", "message": f"Couldn't start: {exc}"})
            return

        async def pump_output() -> None:
            assert process is not None and process.stdout is not None
            while True:
                # .read(n) returns as soon as ANY bytes are available (up to
                # n), unlike .readline() — essential here, since a prompt
                # like `input("Name: ")` writes text with NO trailing
                # newline and then blocks waiting for the user, so a
                # line-based reader would never see it at all.
                chunk = await process.stdout.read(4096)
                if not chunk:
                    break
                await _send_json(websocket, {"type": "output", "text": chunk.decode(errors="replace")})

        async def pump_input() -> None:
            assert process is not None and process.stdin is not None
            while True:
                msg = await websocket.receive_json()
                action = msg.get("action")
                if action == "input":
                    text = msg.get("text", "")
                    try:
                        process.stdin.write(f"{text}\n".encode())
                        await process.stdin.drain()
                    except (BrokenPipeError, ConnectionResetError):
                        break
                elif action == "stop":
                    process.kill()
                    break

        output_task = asyncio.create_task(pump_output())
        input_task = asyncio.create_task(pump_input())
        try:
            # The run ends the instant EITHER side finishes: the process
            # exiting (pump_output hits EOF) or the client disconnecting/
            # stopping (pump_input returns or raises) — whichever comes
            # first, the other task's work is no longer meaningful.
            done, pending = await asyncio.wait({output_task, input_task}, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in done:
                exc = task.exception()
                if exc and not isinstance(exc, WebSocketDisconnect):
                    raise exc
        finally:
            if process.returncode is None:
                process.kill()
            exit_code = await process.wait()
            await _send_json(websocket, {"type": "exit", "code": exit_code})

    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 — never let a bad run wedge the socket open
        logger.exception("Code run failed")
        await _send_json(websocket, {"type": "error", "message": "The run crashed unexpectedly."})
    finally:
        if process is not None and process.returncode is None:
            process.kill()
        if script_path is not None:
            script_path.unlink(missing_ok=True)
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close()
