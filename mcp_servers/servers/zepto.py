from __future__ import annotations

from mcp import StdioServerParameters

from config.settings import Settings

REMOTE_URL = "https://mcp.zepto.co.in/mcp"


def build_server_params(settings: Settings) -> StdioServerParameters:
    """Launch spec for Zepto's remote MCP server, bridged over stdio via
    the `mcp-remote` npm package — the same pattern Zepto's own docs give
    for Claude Desktop/Cursor/VS Code. `mcp-remote` itself:
      - speaks Streamable HTTP to https://mcp.zepto.co.in/mcp
      - runs the OAuth 2.1 flow (Indian mobile number + OTP) in a browser
        on first use, then caches the resulting token locally
      - exposes the remote server's tools over stdio, same as any other
        StdioToolProvider here

    Reference: https://github.com/zeptonow/mcp
    """
    return StdioServerParameters(
        command="npx",
        args=["-y", "mcp-remote", REMOTE_URL],
        env=None,
    )
