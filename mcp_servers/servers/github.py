from __future__ import annotations

import os
import shutil

from mcp import StdioServerParameters

from config.settings import Settings


def is_available(settings: Settings) -> bool:
    """Whether the GitHub MCP server can be launched: token set and binary on PATH."""
    return bool(settings.github_token) and shutil.which("github-mcp-server") is not None


def build_server_params(settings: Settings) -> StdioServerParameters:
    """Launch spec for the official GitHub MCP server (read-only).

    Reference: https://github.com/github/github-mcp-server
    Built locally via `go install github.com/github/github-mcp-server/cmd/github-mcp-server@latest`
    (no official npm/uvx distribution; Docker is the other option but requires
    a running daemon). Auth via GITHUB_PERSONAL_ACCESS_TOKEN env var.
    """
    if not settings.github_token:
        raise ValueError("GITHUB_TOKEN is not set")

    return StdioServerParameters(
        command="github-mcp-server",
        args=["stdio", "--read-only", "--toolsets=default"],
        env={**os.environ, "GITHUB_PERSONAL_ACCESS_TOKEN": settings.github_token},
    )
