from __future__ import annotations

from pathlib import Path

from config.settings import Settings


class PathNotAllowedError(ValueError):
    """Raised when a requested file path falls outside the allowed root."""


def resolve_allowed_path(settings: Settings, path: str) -> Path:
    """Resolve a user-supplied path and ensure it stays within an allowed root.

    Mirrors the same boundary the Filesystem MCP server enforces, so
    document reading can't be used to reach files outside the sanctioned
    directory trees.
    """
    resolved = Path(path).expanduser().resolve()

    if not settings.is_path_allowed(resolved):
        raise PathNotAllowedError(f"Path {path!r} is outside the allowed directories {settings.allowed_roots}")

    if not resolved.exists():
        raise FileNotFoundError(f"No such file: {resolved}")

    return resolved


def resolve_allowed_write_path(settings: Settings, path: str) -> Path:
    """Resolve a user-supplied output path for a new file, enforcing the same
    allowed-root boundary as resolve_allowed_path but without requiring the
    file to already exist.
    """
    resolved = Path(path).expanduser().resolve()

    if not settings.is_path_allowed(resolved):
        raise PathNotAllowedError(f"Path {path!r} is outside the allowed directories {settings.allowed_roots}")

    return resolved
