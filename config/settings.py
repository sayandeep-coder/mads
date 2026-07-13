from __future__ import annotations

import os
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


class MissingConfigError(RuntimeError):
    """Raised when a required environment variable is not set."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Typed application configuration, loaded once from the environment."""

    gemini_api_key: str
    model: str
    log_level: str

    github_token: str | None
    context7_api_key: str | None
    google_client_id: str | None
    google_client_secret: str | None
    google_redirect_uri: str | None
    google_api_key: str | None
    oauth_token_encryption_key: str | None
    youtube_api_key: str | None
    spotify_client_id: str | None
    spotify_client_secret: str | None
    spotify_redirect_uri: str | None
    serpapi_api_key: str | None
    google_maps_api_key: str | None

    filesystem_root: Path

    def with_filesystem_root(self, root: Path) -> "Settings":
        """Return a copy of these settings scoped to a different filesystem root.

        Used when a project is active: the filesystem MCP server, document
        tools, and shell tools should all resolve paths relative to the
        project's folder instead of the global FILESYSTEM_ROOT default.
        """
        return replace(self, filesystem_root=root)

    @property
    def allowed_roots(self) -> tuple[Path, ...]:
        """All directories filesystem-touching tools may read/write under.

        Always includes filesystem_root (the active project's folder, or
        the global default) plus the home directory unconditionally — so
        sibling folders outside the active project (e.g. ~/mads_works while
        a narrower project is active) stay reachable without a config
        change. Single source of truth: the Filesystem MCP server, document
        tools, and destructive shell operations all resolve against this.
        """
        home = Path.home().resolve()
        if self.filesystem_root == home:
            return (self.filesystem_root,)
        return (self.filesystem_root, home)

    def is_path_allowed(self, path: Path) -> bool:
        return any(path == root or root in path.parents for root in self.allowed_roots)


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingConfigError(f"Missing required environment variable: {name}")
    return value


def _optional(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache application settings from the environment / .env file."""
    load_dotenv(override=False)

    return Settings(
        gemini_api_key=_require("GEMINI_API_KEY"),
        model=os.environ.get("MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash",
        log_level=os.environ.get("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        github_token=_optional("GITHUB_TOKEN"),
        context7_api_key=_optional("CONTEXT7_API_KEY"),
        google_client_id=_optional("GOOGLE_CLIENT_ID"),
        google_client_secret=_optional("GOOGLE_CLIENT_SECRET"),
        google_redirect_uri=_optional("GOOGLE_REDIRECT_URI"),
        google_api_key=_optional("GOOGLE_API_KEY"),
        oauth_token_encryption_key=_optional("OAUTH_TOKEN_ENCRYPTION_KEY"),
        youtube_api_key=_optional("YOUTUBE_API_KEY"),
        spotify_client_id=_optional("SPOTIFY_CLIENT_ID"),
        spotify_client_secret=_optional("SPOTIFY_CLIENT_SECRET"),
        spotify_redirect_uri=_optional("SPOTIFY_REDIRECT_URI"),
        serpapi_api_key=_optional("SERPAPI_API_KEY"),
        google_maps_api_key=_optional("GOOGLE_MAPS_API_KEY"),
        filesystem_root=Path(
            os.environ.get("FILESYSTEM_ROOT", str(Path.home()))
        ).expanduser().resolve(),
    )
