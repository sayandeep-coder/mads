from __future__ import annotations

from mcp import StdioServerParameters

from config.settings import Settings


def build_server_params(settings: Settings) -> StdioServerParameters:
    """Launch spec for the official Fetch MCP server.

    Reference: https://github.com/modelcontextprotocol/servers/tree/main/src/fetch
    Spawned via uvx; robots.txt is respected (no --ignore-robots-txt).
    """
    return StdioServerParameters(
        command="uvx",
        args=["mcp-server-fetch"],
        env=None,
    )
