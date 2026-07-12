from __future__ import annotations

from mcp import StdioServerParameters

from config.settings import Settings


def build_server_params(settings: Settings) -> StdioServerParameters:
    """Launch spec for the official Filesystem MCP server.

    Reference: https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem
    Spawned via npx; the allowed root is passed as a positional CLI arg.
    """
    return StdioServerParameters(
        command="npx",
        args=[
            "-y",
            "@modelcontextprotocol/server-filesystem",
            str(settings.filesystem_root),
        ],
        env=None,
    )
