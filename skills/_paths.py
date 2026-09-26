from __future__ import annotations

# Re-exports so skill modules don't need to reach into
# mcp_servers.servers.document_intelligence for the one thing they actually
# share with it: the allowed-root path boundary every filesystem-touching
# tool in Mads enforces (see config.settings.Settings.allowed_roots).
from mcp_servers.servers.document_intelligence._paths import (
    PathNotAllowedError,
    resolve_allowed_path,
    resolve_allowed_write_path,
)

__all__ = ["PathNotAllowedError", "resolve_allowed_path", "resolve_allowed_write_path"]
