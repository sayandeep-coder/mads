from __future__ import annotations

from mcp import StdioServerParameters

from config.settings import Settings


def build_server_params(settings: Settings) -> StdioServerParameters:
    """Launch spec for the official Filesystem MCP server.

    Reference: https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem
    Spawned via npx; allowed roots are passed as positional CLI args — the
    server accepts more than one. settings.allowed_roots is the single
    source of truth for this boundary, shared with the document tools and
    destructive shell operations.
    """
    return StdioServerParameters(
        command="npx",
        args=[
            "-y",
            "@modelcontextprotocol/server-filesystem",
            *[str(root) for root in settings.allowed_roots],
        ],
        env=None,
    )
