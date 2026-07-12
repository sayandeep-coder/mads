from __future__ import annotations

import os
from dataclasses import dataclass
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

    filesystem_root: Path


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
        filesystem_root=Path(
            os.environ.get("FILESYSTEM_ROOT", str(Path.home()))
        ).expanduser().resolve(),
    )
