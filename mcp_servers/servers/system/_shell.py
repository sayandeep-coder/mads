from __future__ import annotations

import subprocess
from typing import Any

_DEFAULT_TIMEOUT_SECONDS = 15


class CommandError(RuntimeError):
    """Raised when a subprocess command fails or times out."""


def run(args: list[str], timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> str:
    """Run a command and return its stripped stdout, raising CommandError on failure.

    Every System Tool capability goes through this single chokepoint rather
    than calling subprocess.run directly, so error handling and timeouts are
    consistent everywhere.
    """
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CommandError(f"Command timed out after {timeout}s: {' '.join(args)}") from exc
    except FileNotFoundError as exc:
        raise CommandError(f"Command not found: {args[0]}") from exc

    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        raise CommandError(message)

    return result.stdout.strip()


def run_osascript(script: str, timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> str:
    """Run an AppleScript snippet via osascript and return its stripped stdout."""
    return run(["osascript", "-e", script], timeout=timeout)


def ok(result: Any = None) -> dict[str, Any]:
    """Build the standard success envelope every capability function returns."""
    return {"success": True, "result": result}


def fail(error: str, message: str | None = None) -> dict[str, Any]:
    """Build the standard failure envelope every capability function returns."""
    return {"success": False, "error": error, "message": message or error}
