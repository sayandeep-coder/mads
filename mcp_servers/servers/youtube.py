from __future__ import annotations

import asyncio
import logging
import re
from contextlib import AsyncExitStack
from typing import Any, Callable

from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError
from mcp import Tool

from config.settings import Settings
from mcp_servers.manager import ToolCallResult

logger = logging.getLogger(__name__)

_VIDEO_URL_TEMPLATE = "https://www.youtube.com/watch?v={video_id}"
_CHANNEL_URL_TEMPLATE = "https://www.youtube.com/channel/{channel_id}"

_TOOLS = [
    Tool(
        name="search_videos",
        description="Search YouTube for videos matching a query. Returns id, title, description, channel, published date, and url for each result.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "max_results": {"type": "integer", "description": "Maximum number of results (1-50).", "default": 10},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="get_video_details",
        description=(
            "Get full details for a YouTube video by id: title, description, tags, duration, "
            "view/like/comment counts, channel, published date, and url. Use this to understand "
            "what a video is about (e.g. before summarizing it) — full transcript text is not available."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "video_id": {"type": "string", "description": "The YouTube video id (from search_videos, or the 'v=' part of a YouTube URL)."},
            },
            "required": ["video_id"],
        },
    ),
    Tool(
        name="get_channel",
        description="Get details for a YouTube channel by handle (e.g. '@mkbhd') or channel id: title, description, subscriber/video counts, url.",
        inputSchema={
            "type": "object",
            "properties": {
                "handle_or_id": {"type": "string", "description": "A channel handle starting with '@', or a raw channel id."},
            },
            "required": ["handle_or_id"],
        },
    ),
    Tool(
        name="list_playlist_items",
        description="List the videos in a YouTube playlist by playlist id.",
        inputSchema={
            "type": "object",
            "properties": {
                "playlist_id": {"type": "string", "description": "The YouTube playlist id."},
                "max_results": {"type": "integer", "description": "Maximum number of items (1-50).", "default": 20},
            },
            "required": ["playlist_id"],
        },
    ),
]


def _iso8601_duration_to_text(duration: str) -> str:
    """Render an ISO 8601 duration (e.g. 'PT1H2M3S') as 'H:MM:SS' / 'M:SS'."""
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not match:
        return duration

    hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


class YouTubeProvider:
    """Tool provider for YouTube search/lookup, backed directly by the YouTube Data API v3.

    The official youtube-mcp-server npm package is broken (depends on an
    unpinned @modelcontextprotocol/sdk version whose exports it no longer
    matches), so this calls the Data API directly instead — same pattern as
    google_workspace. Transcript/caption text is intentionally not exposed:
    the Data API's captions.download requires OAuth as the video's owner,
    so real transcript access would require scraping an unofficial
    endpoint, which was decided against.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._youtube: Resource | None = None

    @property
    def name(self) -> str:
        return "youtube"

    @staticmethod
    def is_available(settings: Settings) -> bool:
        return bool(settings.youtube_api_key)

    async def connect(self, exit_stack: AsyncExitStack) -> None:
        self._youtube = build("youtube", "v3", developerKey=self._settings.youtube_api_key)

    def list_tools(self) -> list[Tool]:
        return list(_TOOLS)

    async def call_tool(self, name: str, arguments: dict) -> ToolCallResult:
        if self._youtube is None:
            raise RuntimeError("connect() must be called before call_tool()")

        try:
            result = await asyncio.to_thread(self._dispatch, name, arguments)
        except HttpError as exc:
            logger.exception("YouTube API call %r failed", name)
            return ToolCallResult(text=f"YouTube API error: {exc}", is_error=True)
        except Exception as exc:  # noqa: BLE001 — surface any failure back to the model
            logger.exception("YouTube call %r failed", name)
            return ToolCallResult(text=f"Error: {exc}", is_error=True)

        return ToolCallResult(text=str(result), is_error=False)

    def _dispatch(self, name: str, arguments: dict) -> Any:
        dispatch_table: dict[str, Callable[..., Any]] = {
            "search_videos": self._search_videos,
            "get_video_details": self._get_video_details,
            "get_channel": self._get_channel,
            "list_playlist_items": self._list_playlist_items,
        }
        func = dispatch_table.get(name)
        if func is None:
            raise ValueError(f"Unknown youtube tool: {name!r}")
        return func(**arguments)

    def _search_videos(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        assert self._youtube is not None
        response = (
            self._youtube.search()
            .list(q=query, part="snippet", type="video", maxResults=max_results)
            .execute()
        )
        results = []
        for item in response.get("items", []):
            video_id = item["id"]["videoId"]
            snippet = item["snippet"]
            results.append(
                {
                    "video_id": video_id,
                    "title": snippet.get("title", ""),
                    "description": snippet.get("description", ""),
                    "channel": snippet.get("channelTitle", ""),
                    "published_at": snippet.get("publishedAt", ""),
                    "url": _VIDEO_URL_TEMPLATE.format(video_id=video_id),
                }
            )
        return results

    def _get_video_details(self, video_id: str) -> dict[str, Any]:
        assert self._youtube is not None
        response = (
            self._youtube.videos()
            .list(id=video_id, part="snippet,contentDetails,statistics")
            .execute()
        )
        items = response.get("items", [])
        if not items:
            raise ValueError(f"No video found with id {video_id!r}")

        item = items[0]
        snippet = item.get("snippet", {})
        content_details = item.get("contentDetails", {})
        statistics = item.get("statistics", {})

        return {
            "video_id": video_id,
            "title": snippet.get("title", ""),
            "description": snippet.get("description", ""),
            "tags": snippet.get("tags", []),
            "channel": snippet.get("channelTitle", ""),
            "published_at": snippet.get("publishedAt", ""),
            "duration": _iso8601_duration_to_text(content_details.get("duration", "")),
            "view_count": statistics.get("viewCount", "0"),
            "like_count": statistics.get("likeCount", "0"),
            "comment_count": statistics.get("commentCount", "0"),
            "url": _VIDEO_URL_TEMPLATE.format(video_id=video_id),
        }

    def _get_channel(self, handle_or_id: str) -> dict[str, Any]:
        assert self._youtube is not None
        lookup_kwargs = (
            {"forHandle": handle_or_id.lstrip("@")}
            if handle_or_id.startswith("@")
            else {"id": handle_or_id}
        )
        response = self._youtube.channels().list(part="snippet,statistics", **lookup_kwargs).execute()
        items = response.get("items", [])
        if not items:
            raise ValueError(f"No channel found for {handle_or_id!r}")

        item = items[0]
        snippet = item.get("snippet", {})
        statistics = item.get("statistics", {})
        channel_id = item["id"]

        return {
            "channel_id": channel_id,
            "title": snippet.get("title", ""),
            "description": snippet.get("description", ""),
            "subscriber_count": statistics.get("subscriberCount", "0"),
            "video_count": statistics.get("videoCount", "0"),
            "view_count": statistics.get("viewCount", "0"),
            "url": _CHANNEL_URL_TEMPLATE.format(channel_id=channel_id),
        }

    def _list_playlist_items(self, playlist_id: str, max_results: int = 20) -> list[dict[str, Any]]:
        assert self._youtube is not None
        response = (
            self._youtube.playlistItems()
            .list(playlistId=playlist_id, part="snippet", maxResults=max_results)
            .execute()
        )
        results = []
        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            video_id = snippet.get("resourceId", {}).get("videoId", "")
            results.append(
                {
                    "video_id": video_id,
                    "title": snippet.get("title", ""),
                    "position": snippet.get("position", 0),
                    "url": _VIDEO_URL_TEMPLATE.format(video_id=video_id) if video_id else "",
                }
            )
        return results
