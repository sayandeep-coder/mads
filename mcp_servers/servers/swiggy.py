from __future__ import annotations

from mcp import StdioServerParameters

from config.settings import Settings

# Swiggy runs four independent MCP servers (no shared cart/order/session
# state between them) — only Food is wired up here since it covers the
# same "order food" use case as Zepto/Zomato. Add the others the same way
# (a second StdioToolProvider in agent/session.py) if you want them:
#   Instamart (groceries): https://mcp.swiggy.com/im
#   Dineout (reservations): https://mcp.swiggy.com/dineout
#   Scenes (events/tickets): https://mcp.swiggy.com/scenes
REMOTE_URL = "https://mcp.swiggy.com/food"


def build_server_params(settings: Settings) -> StdioServerParameters:
    """Launch spec for Swiggy's Food MCP server, bridged over stdio via
    the `mcp-remote` npm package (Swiggy's docs don't show this bridge
    explicitly, but it's Streamable HTTP + OAuth 2.1/PKCE like Zepto/
    Zomato, which `mcp-remote` is built for). Places real food orders
    with real money once its OAuth flow completes.

    Reference: https://mcp.swiggy.com/builders/docs/start/what-is-swiggy-mcp/
    """
    return StdioServerParameters(
        command="npx",
        args=["-y", "mcp-remote", REMOTE_URL],
        env=None,
    )
