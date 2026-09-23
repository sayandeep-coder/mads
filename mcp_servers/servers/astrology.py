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

_BASE_URL = "https://json.freeastrologyapi.com"
_TIMEOUT_SECONDS = 15.0

_TOOLS = [
    Tool(
        name="query_astrology_api",
        description=(
            "Query the FreeAstrologyAPI for Vedic astrology details. "
            "Pass an 'endpoint' such as 'planets', 'planets/extended', 'good-bad-times', 'vimsottari/maha-dasas-and-antar-dasas'. "
            "Returns the raw JSON data from the API."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "endpoint": {"type": "string", "description": "The API endpoint to query (e.g., 'planets', 'birth-details', 'panchang', 'dashas')"},
                "year": {"type": "integer", "description": "Birth year (e.g., 2005)"},
                "month": {"type": "integer", "description": "Birth month (1-12)"},
                "date": {"type": "integer", "description": "Birth date (1-31)"},
                "hours": {"type": "integer", "description": "Birth hours in 24h format (0-23)"},
                "minutes": {"type": "integer", "description": "Birth minutes (0-59)"},
                "seconds": {"type": "integer", "description": "Birth seconds (0-59)", "default": 0},
                "latitude": {"type": "number", "description": "Latitude of birth place (e.g., 22.37)"},
                "longitude": {"type": "number", "description": "Longitude of birth place (e.g., 88.17)"},
                "timezone": {"type": "number", "description": "Timezone offset (e.g., 5.5 for India)", "default": 5.5},
            },
            "required": ["endpoint", "year", "month", "date", "hours", "minutes", "latitude", "longitude"],
        },
    ),
]


class AstrologyError(RuntimeError):
    pass


class AstrologyProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def name(self) -> str:
        return "astrology"

    @staticmethod
    def is_available(settings: Settings) -> bool:
        return bool(settings.astrology_api_key)

    async def connect(self, exit_stack: AsyncExitStack) -> None:
        pass

    def list_tools(self) -> list[Tool]:
        return list(_TOOLS)

    async def call_tool(self, name: str, arguments: dict) -> ToolCallResult:
        if name != "query_astrology_api":
            return ToolCallResult(text=f"Unknown astrology tool: {name!r}", is_error=True)

        try:
            result = await asyncio.to_thread(self._query_api, **arguments)
        except AstrologyError as exc:
            return ToolCallResult(text=str(exc), is_error=True)
        except Exception as exc:
            logger.exception("Astrology search failed")
            return ToolCallResult(text=f"Error: {exc}", is_error=True)

        import json
        return ToolCallResult(text=json.dumps(result, indent=2), is_error=False)

    def _query_api(self, endpoint: str, **kwargs) -> dict[str, Any]:
        headers = {
            "x-api-key": self._settings.astrology_api_key,
            "Content-Type": "application/json"
        }
        
        # Ensure seconds is present if missing
        if "seconds" not in kwargs:
            kwargs["seconds"] = 0
        if "timezone" not in kwargs:
            kwargs["timezone"] = 5.5

        try:
            url = f"{_BASE_URL}/{endpoint.lstrip('/')}"
            response = httpx.post(url, json=kwargs, headers=headers, timeout=_TIMEOUT_SECONDS)
        except httpx.TimeoutException as exc:
            raise AstrologyError(f"Astrology request timed out after {_TIMEOUT_SECONDS}s") from exc
        except httpx.RequestError as exc:
            raise AstrologyError(f"Network error contacting FreeAstrologyAPI: {exc}") from exc

        if response.status_code != 200:
            raise AstrologyError(f"FreeAstrologyAPI returned HTTP {response.status_code}: {response.text[:200]}")

        return response.json()
