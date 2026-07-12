from __future__ import annotations

import threading
import webbrowser
from base64 import b64encode
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from auth.oauth_manager import OAuthError, TokenSet
from config.settings import Settings

_AUTH_URL = "https://accounts.spotify.com/authorize"
_TOKEN_URL = "https://accounts.spotify.com/api/token"


class SpotifyAuthError(OAuthError):
    """Raised when Spotify OAuth credentials cannot be obtained or refreshed."""


class _CallbackHandler(BaseHTTPRequestHandler):
    """Captures the single 'code' (or 'error') query param from Spotify's redirect."""

    result: dict[str, str] = {}

    def do_GET(self) -> None:  # noqa: N802 — required method name from BaseHTTPRequestHandler
        query = parse_qs(urlparse(self.path).query)
        if "code" in query:
            _CallbackHandler.result["code"] = query["code"][0]
            body = b"Mads is now connected to Spotify. You can close this tab."
        else:
            _CallbackHandler.result["error"] = query.get("error", ["unknown_error"])[0]
            body = b"Spotify authorization failed. You can close this tab and check the terminal."

        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 — suppress default request logging
        pass


def _basic_auth_header(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode("utf-8")
    return "Basic " + b64encode(raw).decode("ascii")


def _token_response_to_token_set(data: dict, fallback_refresh_token: str | None = None) -> TokenSet:
    expires_at = (
        (datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"])).isoformat()
        if "expires_in" in data
        else None
    )
    return TokenSet(
        access_token=data["access_token"],
        # Spotify doesn't always return a new refresh_token on refresh —
        # when omitted, the existing one must keep being used.
        refresh_token=data.get("refresh_token", fallback_refresh_token),
        expires_at=expires_at,
        scopes=data.get("scope", "").split(" ") if data.get("scope") else [],
    )


class SpotifyOAuthAdapter:
    """Provider-specific OAuth logic for Spotify; storage/refresh-orchestration lives in OAuthManager."""

    def __init__(self, settings: Settings) -> None:
        if not (settings.spotify_client_id and settings.spotify_client_secret):
            raise SpotifyAuthError("SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET are not set")
        self._settings = settings

    @property
    def provider_name(self) -> str:
        return "spotify"

    def run_consent_flow(self, scopes: list[str]) -> TokenSet:
        redirect_uri = self._settings.spotify_redirect_uri or "http://127.0.0.1:8765/callback"
        parsed = urlparse(redirect_uri)
        port = parsed.port or 8765

        _CallbackHandler.result = {}
        server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
        server_thread = threading.Thread(target=server.handle_request, daemon=True)
        server_thread.start()

        auth_url = _AUTH_URL + "?" + urlencode(
            {
                "client_id": self._settings.spotify_client_id,
                "response_type": "code",
                "redirect_uri": redirect_uri,
                "scope": " ".join(scopes),
            }
        )
        webbrowser.open(auth_url)

        server_thread.join(timeout=300)
        server.server_close()

        if "error" in _CallbackHandler.result:
            raise SpotifyAuthError(f"Spotify authorization failed: {_CallbackHandler.result['error']}")
        code = _CallbackHandler.result.get("code")
        if not code:
            raise SpotifyAuthError("Timed out waiting for Spotify authorization")

        response = httpx.post(
            _TOKEN_URL,
            data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
            headers={
                "Authorization": _basic_auth_header(
                    self._settings.spotify_client_id, self._settings.spotify_client_secret
                ),
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        response.raise_for_status()
        return _token_response_to_token_set(response.json())

    def refresh(self, token_set: TokenSet) -> TokenSet:
        response = httpx.post(
            _TOKEN_URL,
            data={"grant_type": "refresh_token", "refresh_token": token_set.refresh_token},
            headers={
                "Authorization": _basic_auth_header(
                    self._settings.spotify_client_id, self._settings.spotify_client_secret
                ),
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        response.raise_for_status()
        return _token_response_to_token_set(response.json(), fallback_refresh_token=token_set.refresh_token)
