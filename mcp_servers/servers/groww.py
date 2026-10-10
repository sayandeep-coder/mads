from __future__ import annotations

from mcp import StdioServerParameters

from config.settings import Settings

REMOTE_URL = "https://mcp.groww.in/mcp"


def build_server_params(settings: Settings) -> StdioServerParameters:
    """Launch spec for Groww's remote MCP server, bridged over stdio via
    the `mcp-remote` npm package (the same bridge Groww's own docs show
    for Cursor/VS Code; Claude Desktop instead adds it as a custom
    connector, which isn't applicable here since Mads is its own MCP
    client, not Claude Desktop).

    Current scope per Groww's docs: stocks and F&O only (no mutual
    funds/IPOs/bonds yet). DDPI authorisation is required on the Groww
    account side to place sell orders.

    Reference: https://groww.in/updates/groww-mcp
    """
    return StdioServerParameters(
        command="npx",
        args=["-y", "mcp-remote", REMOTE_URL],
        env=None,
    )
