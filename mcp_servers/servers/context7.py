from __future__ import annotations

from mcp import StdioServerParameters

from config.settings import Settings


def build_server_params(settings: Settings) -> StdioServerParameters:
    """Launch spec for the official Context7 MCP server.

    Reference: https://github.com/upstash/context7
    Spawned via npx. The API key is optional (raises rate limits when set).
    """
    args = ["-y", "@upstash/context7-mcp"]
    if settings.context7_api_key:
        args += ["--api-key", settings.context7_api_key]

    return StdioServerParameters(
        command="npx",
        args=args,
        env=None,
    )
