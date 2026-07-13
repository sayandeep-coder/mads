from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import psutil

from config.settings import Settings
from mcp_servers.servers.system._shell import CommandError, fail, ok, run_osascript


def _needs_confirmation(action: str, confirmed: bool, warning: str) -> dict[str, Any] | None:
    """Shared confirmation gate: returns a confirmation-required envelope if
    not yet confirmed, or None if the caller should proceed with the action.

    This is the entire safety mechanism for destructive operations — no
    blocking I/O inside the tool call. The first call (confirmed=False,
    the default) always stops here; Gemini sees requires_confirmation=true
    and asks the user in normal chat, then re-calls with confirmed=true.
    """
    if confirmed:
        return None
    return {
        "success": False,
        "requires_confirmation": True,
        "action": action,
        "message": f"{warning} Call this again with confirmed=true to proceed.",
    }


def shutdown(confirmed: bool = False) -> dict[str, Any]:
    """Shut down the Mac. Requires confirmed=true."""
    gate = _needs_confirmation("shutdown", confirmed, "This will shut down the computer immediately.")
    if gate:
        return gate

    try:
        run_osascript('tell app "System Events" to shut down')
    except CommandError as exc:
        return fail("shutdown_failed", str(exc))
    return ok({"action": "shutdown", "status": "shutting_down"})


def restart(confirmed: bool = False) -> dict[str, Any]:
    """Restart the Mac. Requires confirmed=true."""
    gate = _needs_confirmation("restart", confirmed, "This will restart the computer immediately.")
    if gate:
        return gate

    try:
        run_osascript('tell app "System Events" to restart')
    except CommandError as exc:
        return fail("restart_failed", str(exc))
    return ok({"action": "restart", "status": "restarting"})


def empty_trash(confirmed: bool = False) -> dict[str, Any]:
    """Permanently empty the Trash. Requires confirmed=true."""
    gate = _needs_confirmation(
        "empty_trash", confirmed, "This will permanently delete everything in the Trash."
    )
    if gate:
        return gate

    try:
        run_osascript('tell application "Finder" to empty trash')
    except CommandError as exc:
        return fail("empty_trash_failed", str(exc))
    return ok({"action": "empty_trash", "status": "emptied"})


def delete_files(settings: Settings, paths: list[str], confirmed: bool = False) -> dict[str, Any]:
    """Permanently delete one or more files or folders. Requires confirmed=true.

    Paths are resolved and must fall within the allowed filesystem root,
    same boundary enforced by the Filesystem and Document Intelligence tools.
    """
    gate = _needs_confirmation(
        "delete_files",
        confirmed,
        f"This will permanently delete {len(paths)} item(s): {', '.join(paths)}.",
    )
    if gate:
        return gate

    deleted: list[str] = []
    errors: list[dict[str, str]] = []

    for raw_path in paths:
        resolved = Path(raw_path).expanduser().resolve()

        if not settings.is_path_allowed(resolved):
            errors.append({"path": raw_path, "error": f"Outside allowed directories {settings.allowed_roots}"})
            continue
        if not resolved.exists():
            errors.append({"path": raw_path, "error": "No such file or directory"})
            continue

        try:
            if resolved.is_dir():
                shutil.rmtree(resolved)
            else:
                resolved.unlink()
            deleted.append(str(resolved))
        except OSError as exc:
            errors.append({"path": raw_path, "error": str(exc)})

    if errors and not deleted:
        return fail("delete_failed", f"Could not delete any files: {errors}")

    return ok({"action": "delete_files", "deleted": deleted, "errors": errors})


def terminate_process(name_or_pid: str, confirmed: bool = False) -> dict[str, Any]:
    """Forcibly terminate a running process by name or PID. Requires confirmed=true."""
    gate = _needs_confirmation(
        "terminate_process", confirmed, f"This will forcibly terminate the process {name_or_pid!r}."
    )
    if gate:
        return gate

    matched: list[psutil.Process] = []
    if name_or_pid.isdigit():
        try:
            matched = [psutil.Process(int(name_or_pid))]
        except psutil.NoSuchProcess:
            return fail("process_not_found", f"No process with PID {name_or_pid}")
    else:
        for proc in psutil.process_iter(["pid", "name"]):
            if proc.info["name"] and name_or_pid.lower() in proc.info["name"].lower():
                matched.append(proc)

    if not matched:
        return fail("process_not_found", f"No running process matching {name_or_pid!r}")

    terminated: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for proc in matched:
        try:
            proc.terminate()
            terminated.append({"pid": proc.pid, "name": proc.name()})
        except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
            errors.append({"pid": proc.pid, "error": str(exc)})

    return ok({"action": "terminate_process", "terminated": terminated, "errors": errors})
