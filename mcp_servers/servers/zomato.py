from __future__ import annotations

from mcp import StdioServerParameters

from config.settings import Settings

REMOTE_URL = "https://mcp-server.zomato.com/mcp"


def build_server_params(settings: Settings) -> StdioServerParameters:
    """Launch spec for Zomato's remote MCP server, bridged over stdio via
    the `mcp-remote` npm package (same bridge Zomato's own README shows
    for Claude Desktop). Places real food orders with real money once its
    OAuth flow completes.

    Reference: https://github.com/Zomato/mcp-server-manifest
    """
    return StdioServerParameters(
        command="npx",
        args=["-y", "mcp-remote", REMOTE_URL],
        env=None,
    )
