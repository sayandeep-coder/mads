from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from typing import Any, Callable

import httpx
from mcp import Tool

from config.settings import Settings
from mcp_servers.manager import ToolCallResult

logger = logging.getLogger(__name__)

_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
_ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
_PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
_TIMEOUT_SECONDS = 15.0

_VALID_TRAVEL_MODES = {"DRIVE", "WALK", "BICYCLE", "TRANSIT"}

_TOOLS = [
    Tool(
        name="geocode",
        description="Convert a place name or address into latitude/longitude coordinates and its formatted address.",
        inputSchema={
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "Place name or address, e.g. 'Eiffel Tower' or '221B Baker Street, London'."},
            },
            "required": ["address"],
        },
    ),
    Tool(
        name="get_directions",
        description=(
            "Get the best route between two places, with live-traffic-aware travel duration and "
            "distance. Origin/destination may be place names or addresses (resolved automatically)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "Starting place name or address."},
                "destination": {"type": "string", "description": "Destination place name or address."},
                "travel_mode": {
                    "type": "string",
                    "enum": sorted(_VALID_TRAVEL_MODES),
                    "description": "Mode of travel.",
                    "default": "DRIVE",
                },
            },
            "required": ["origin", "destination"],
        },
    ),
    Tool(
        name="search_places",
        description=(
            "Search for places — hotels, restaurants, attractions, or any point of interest — "
            "matching a natural-language query (e.g. 'hotels in Goa', 'best ramen near Shinjuku'). "
            "Returns name, address, rating, and coordinates for each match."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural-language search query."},
                "max_results": {"type": "integer", "description": "Maximum number of results (1-20).", "default": 10},
            },
            "required": ["query"],
        },
    ),
]


class MapsError(RuntimeError):
    """Raised when a Google Maps API request fails, times out, or returns something unusable."""


class MapsProvider:
    """Directions, place search, and geocoding via Google Maps Platform APIs
    (Routes API, Places API, Geocoding API) — API-key auth, no OAuth, no
    access to any personal Google account data. Architecturally the same
    shape as YouTube: a standalone Google product reached with an API key.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def name(self) -> str:
        return "maps"

    @staticmethod
    def is_available(settings: Settings) -> bool:
        return bool(settings.google_maps_api_key)

    async def connect(self, exit_stack: AsyncExitStack) -> None:
        pass

    def list_tools(self) -> list[Tool]:
        return list(_TOOLS)

    async def call_tool(self, name: str, arguments: dict) -> ToolCallResult:
        dispatch_table: dict[str, Callable[..., Any]] = {
            "geocode": self._geocode,
            "get_directions": self._get_directions,
            "search_places": self._search_places,
        }
        func = dispatch_table.get(name)
        if func is None:
            return ToolCallResult(text=f"Unknown maps tool: {name!r}", is_error=True)

        try:
            result = await asyncio.to_thread(func, **arguments)
        except MapsError as exc:
            return ToolCallResult(text=str(exc), is_error=True)
        except Exception as exc:  # noqa: BLE001 — surface any failure back to the model
            logger.exception("Maps tool %r failed", name)
            return ToolCallResult(text=f"Error: {exc}", is_error=True)

        return ToolCallResult(text=str(result), is_error=False)

    def _get(self, url: str, params: dict) -> dict:
        try:
            response = httpx.get(url, params=params, timeout=_TIMEOUT_SECONDS)
        except httpx.TimeoutException as exc:
            raise MapsError(f"Request to Google Maps timed out after {_TIMEOUT_SECONDS}s") from exc
        except httpx.RequestError as exc:
            raise MapsError(f"Network error contacting Google Maps: {exc}") from exc

        if response.status_code != 200:
            raise MapsError(f"Google Maps returned HTTP {response.status_code}: {response.text[:200]}")
        return response.json()

    def _post(self, url: str, json_body: dict, field_mask: str) -> dict:
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._settings.google_maps_api_key,
            "X-Goog-FieldMask": field_mask,
        }
        try:
            response = httpx.post(url, json=json_body, headers=headers, timeout=_TIMEOUT_SECONDS)
        except httpx.TimeoutException as exc:
            raise MapsError(f"Request to Google Maps timed out after {_TIMEOUT_SECONDS}s") from exc
        except httpx.RequestError as exc:
            raise MapsError(f"Network error contacting Google Maps: {exc}") from exc

        if response.status_code != 200:
            raise MapsError(f"Google Maps returned HTTP {response.status_code}: {response.text[:200]}")
        return response.json()

    def _geocode(self, address: str) -> dict[str, Any]:
        data = self._get(_GEOCODE_URL, {"address": address, "key": self._settings.google_maps_api_key})

        if data.get("status") != "OK" or not data.get("results"):
            raise MapsError(f"Could not geocode {address!r}: {data.get('status', 'UNKNOWN_ERROR')}")

        result = data["results"][0]
        location = result["geometry"]["location"]
        return {
            "formatted_address": result.get("formatted_address", ""),
            "latitude": location["lat"],
            "longitude": location["lng"],
        }

    def _get_directions(self, origin: str, destination: str, travel_mode: str = "DRIVE") -> dict[str, Any]:
        if travel_mode not in _VALID_TRAVEL_MODES:
            raise MapsError(f"travel_mode must be one of {sorted(_VALID_TRAVEL_MODES)}, got {travel_mode!r}")

        origin_location = self._geocode(origin)
        destination_location = self._geocode(destination)

        body = {
            "origin": {"location": {"latLng": {"latitude": origin_location["latitude"], "longitude": origin_location["longitude"]}}},
            "destination": {"location": {"latLng": {"latitude": destination_location["latitude"], "longitude": destination_location["longitude"]}}},
            "travelMode": travel_mode,
            "routingPreference": "TRAFFIC_AWARE" if travel_mode == "DRIVE" else "TRAFFIC_UNAWARE",
            "units": "METRIC",
        }
        field_mask = "routes.duration,routes.staticDuration,routes.distanceMeters"

        data = self._post(_ROUTES_URL, body, field_mask)
        routes = data.get("routes", [])
        if not routes:
            raise MapsError(f"No route found from {origin!r} to {destination!r}")

        route = routes[0]
        duration_seconds = int(route.get("duration", "0s").rstrip("s"))
        distance_meters = route.get("distanceMeters", 0)

        return {
            "origin": origin_location["formatted_address"],
            "destination": destination_location["formatted_address"],
            "travel_mode": travel_mode,
            "duration_minutes": round(duration_seconds / 60, 1),
            "distance_km": round(distance_meters / 1000, 2),
        }

    def _search_places(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        body = {"textQuery": query, "pageSize": max_results}
        field_mask = "places.displayName,places.formattedAddress,places.rating,places.location"

        data = self._post(_PLACES_URL, body, field_mask)
        places = data.get("places", [])

        return [
            {
                "name": place.get("displayName", {}).get("text", ""),
                "address": place.get("formattedAddress", ""),
                "rating": place.get("rating"),
                "latitude": place.get("location", {}).get("latitude"),
                "longitude": place.get("location", {}).get("longitude"),
            }
            for place in places[:max_results]
        ]
