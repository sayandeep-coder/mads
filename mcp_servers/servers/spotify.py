from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from typing import Any, Callable

import httpx
from mcp import Tool

from auth.oauth_manager import OAuthManager, TokenSet
from auth.spotify_oauth import SpotifyOAuthAdapter
from config.settings import Settings
from mcp_servers.manager import ToolCallResult

logger = logging.getLogger(__name__)

_API_BASE = "https://api.spotify.com/v1"

_SCOPES = [
    "user-read-playback-state",
    "user-read-currently-playing",
    "user-modify-playback-state",
    "user-library-read",
    "user-library-modify",
]


class NoActiveDeviceError(RuntimeError):
    """Raised when a playback action is requested but no Spotify Connect device is active."""

    def __init__(self) -> None:
        super().__init__(
            "No active Spotify device found. Open Spotify on your phone, desktop, or another "
            "device and start playing (or pausing) something there first, then try again."
        )


_TOOLS = [
    Tool(
        name="search_tracks",
        description="Search Spotify for tracks matching a query. Returns track name, artist, album, uri, and duration for each result.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (song name, artist, etc)."},
                "limit": {"type": "integer", "description": "Maximum number of results (1-50).", "default": 10},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="play_track",
        description=(
            "Play a specific track immediately on the user's active Spotify device. "
            "Requires Spotify Premium and at least one active device."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "track_uri": {"type": "string", "description": "The Spotify track URI (from search_tracks), e.g. 'spotify:track:...'."},
            },
            "required": ["track_uri"],
        },
    ),
]


class SpotifyProvider:
    """Tool provider for Spotify playback control and search, backed directly by the Spotify Web API.

    Requires Spotify Premium for playback control (search/read works on any
    account). All playback-affecting calls go through ensure_active_device()
    first, so a missing device produces one consistent, user-friendly error
    instead of a raw 404 from the API.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._oauth_manager = OAuthManager(settings.oauth_token_encryption_key or "")
        self._adapter = SpotifyOAuthAdapter(settings)
        self._token: TokenSet | None = None

    @property
    def name(self) -> str:
        return "spotify"

    @staticmethod
    def is_available(settings: Settings) -> bool:
        return bool(
            settings.spotify_client_id
            and settings.spotify_client_secret
            and settings.oauth_token_encryption_key
        )

    async def connect(self, exit_stack: AsyncExitStack) -> None:
        # OAuth (including the one-time browser consent flow) is blocking
        # I/O; run it off the event loop so it doesn't stall the REPL.
        self._token = await asyncio.to_thread(self._oauth_manager.get_token, self._adapter, _SCOPES)

    def _ensure_fresh_token(self) -> None:
        # Access tokens expire in ~1 hour; a long-running session must
        # re-check and refresh before each call, not just once at connect().
        assert self._token is not None
        self._token = self._oauth_manager.get_token(self._adapter, _SCOPES)

    def list_tools(self) -> list[Tool]:
        return list(_TOOLS)

    async def call_tool(self, name: str, arguments: dict) -> ToolCallResult:
        if self._token is None:
            raise RuntimeError("connect() must be called before call_tool()")

        try:
            result = await asyncio.to_thread(self._dispatch, name, arguments)
        except NoActiveDeviceError as exc:
            return ToolCallResult(text=str(exc), is_error=True)
        except httpx.HTTPStatusError as exc:
            logger.exception("Spotify API call %r failed", name)
            return ToolCallResult(text=f"Spotify API error: {exc.response.status_code} {exc.response.text}", is_error=True)
        except Exception as exc:  # noqa: BLE001 — surface any failure back to the model
            logger.exception("Spotify call %r failed", name)
            return ToolCallResult(text=f"Error: {exc}", is_error=True)

        return ToolCallResult(text=str(result), is_error=False)

    def _dispatch(self, name: str, arguments: dict) -> Any:
        dispatch_table: dict[str, Callable[..., Any]] = {
            "search_tracks": self._search_tracks,
            "play_track": self._play_track,
        }
        func = dispatch_table.get(name)
        if func is None:
            raise ValueError(f"Unknown spotify tool: {name!r}")
        return func(**arguments)

    def _client(self) -> httpx.Client:
        self._ensure_fresh_token()
        assert self._token is not None
        return httpx.Client(
            base_url=_API_BASE,
            headers={"Authorization": f"Bearer {self._token.access_token}"},
            timeout=10.0,
        )

    def ensure_active_device(self, client: httpx.Client) -> str:
        """Return the id of the user's active Spotify Connect device, or raise NoActiveDeviceError."""
        response = client.get("/me/player/devices")
        response.raise_for_status()
        devices = response.json().get("devices", [])

        for device in devices:
            if device.get("is_active"):
                return device["id"]

        raise NoActiveDeviceError()

    def _search_tracks(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        with self._client() as client:
            response = client.get("/search", params={"q": query, "type": "track", "limit": limit})
            response.raise_for_status()
            items = response.json().get("tracks", {}).get("items", [])

        return [
            {
                "name": item["name"],
                "artists": [a["name"] for a in item.get("artists", [])],
                "album": item.get("album", {}).get("name", ""),
                "uri": item["uri"],
                "duration_ms": item.get("duration_ms", 0),
            }
            for item in items
        ]

    def _play_track(self, track_uri: str) -> dict[str, Any]:
        with self._client() as client:
            device_id = self.ensure_active_device(client)
            response = client.put(
                "/me/player/play",
                params={"device_id": device_id},
                json={"uris": [track_uri]},
            )
            response.raise_for_status()

        return {"status": "playing", "track_uri": track_uri}
