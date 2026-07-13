from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from typing import Any

import httpx
from mcp import Tool

from config.settings import Settings
from mcp_servers.manager import ToolCallResult

logger = logging.getLogger(__name__)

_API_URL = "https://serpapi.com/search"
_TIMEOUT_SECONDS = 15.0

_TOOLS = [
    Tool(
        name="search_web",
        description=(
            "Search Google for a query and return real, current results (title, link, snippet) "
            "for each match. Use this for anything requiring up-to-date information from the web "
            "that isn't covered by a more specific tool."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "num_results": {"type": "integer", "description": "Maximum number of results to return.", "default": 10},
            },
            "required": ["query"],
        },
    ),
]


class SearchError(RuntimeError):
    """Raised when the SerpApi request fails, times out, or returns something unusable."""


class SearchProvider:
    """Google Search via SerpApi. Direct HTTP call — no official Python SDK dependency needed
    for a single GET+JSON endpoint, consistent with how Mads calls YouTube/Spotify/Pollinations.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def name(self) -> str:
        return "search"

    @staticmethod
    def is_available(settings: Settings) -> bool:
        return bool(settings.serpapi_api_key)

    async def connect(self, exit_stack: AsyncExitStack) -> None:
        pass

    def list_tools(self) -> list[Tool]:
        return list(_TOOLS)

    async def call_tool(self, name: str, arguments: dict) -> ToolCallResult:
        if name != "search_web":
            return ToolCallResult(text=f"Unknown search tool: {name!r}", is_error=True)

        try:
            result = await asyncio.to_thread(self._search_web, **arguments)
        except SearchError as exc:
            return ToolCallResult(text=str(exc), is_error=True)
        except Exception as exc:  # noqa: BLE001 — surface any failure back to the model
            logger.exception("Web search failed")
            return ToolCallResult(text=f"Error: {exc}", is_error=True)

        return ToolCallResult(text=str(result), is_error=False)

    def _search_web(self, query: str, num_results: int = 10) -> list[dict[str, Any]]:
        params = {
            "engine": "google",
            "q": query,
            "num": num_results,
            "api_key": self._settings.serpapi_api_key,
        }

        try:
            response = httpx.get(_API_URL, params=params, timeout=_TIMEOUT_SECONDS)
        except httpx.TimeoutException as exc:
            raise SearchError(f"Search request timed out after {_TIMEOUT_SECONDS}s") from exc
        except httpx.RequestError as exc:
            raise SearchError(f"Network error contacting SerpApi: {exc}") from exc

        if response.status_code != 200:
            raise SearchError(f"SerpApi returned HTTP {response.status_code}: {response.text[:200]}")

        data = response.json()
        if "error" in data:
            raise SearchError(f"SerpApi error: {data['error']}")

        results = data.get("organic_results", [])
        return [
            {
                "position": item.get("position"),
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            }
            for item in results[:num_results]
        ]
