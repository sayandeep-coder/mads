from __future__ import annotations

from typing import Any

from mcp_servers.servers.system._shell import CommandError, fail, ok, run, run_osascript


def open_app(name: str) -> dict[str, Any]:
    """Launch (or bring to front) a macOS application by name."""
    try:
        run(["open", "-a", name])
    except CommandError as exc:
        return fail("app_not_found", f"Could not open {name!r}: {exc}")

    return ok({"app": name, "status": "launched"})


def quit_app(name: str) -> dict[str, Any]:
    """Quit a running macOS application by name."""
    script = f'tell application "{name}" to quit'
    try:
        run_osascript(script)
    except CommandError as exc:
        return fail("quit_failed", f"Could not quit {name!r}: {exc}")

    return ok({"app": name, "status": "quit"})


def list_running_apps() -> dict[str, Any]:
    """List the names of currently running (foreground) macOS applications."""
    script = "tell application \"System Events\" to get name of every process whose background only is false"
    try:
        output = run_osascript(script)
    except CommandError as exc:
        return fail("list_failed", f"Could not list running apps: {exc}")

    apps = [name.strip() for name in output.split(",") if name.strip()]
    return ok({"running_apps": apps, "count": len(apps)})
