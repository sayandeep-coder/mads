from __future__ import annotations

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from auth.oauth_manager import OAuthError, OAuthManager, TokenSet
from config.settings import Settings

_TOKEN_URI = "https://oauth2.googleapis.com/token"
_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"


class GoogleAuthError(OAuthError):
    """Raised when Google OAuth credentials cannot be obtained or refreshed."""


def _credentials_to_token_set(credentials: Credentials) -> TokenSet:
    return TokenSet(
        access_token=credentials.token,
        refresh_token=credentials.refresh_token,
        expires_at=credentials.expiry.isoformat() + "Z" if credentials.expiry else None,
        scopes=list(credentials.scopes or []),
    )


def _token_set_to_credentials(token_set: TokenSet, client_id: str, client_secret: str) -> Credentials:
    return Credentials(
        token=token_set.access_token,
        refresh_token=token_set.refresh_token,
        token_uri=_TOKEN_URI,
        client_id=client_id,
        client_secret=client_secret,
        scopes=token_set.scopes,
    )


class GoogleOAuthAdapter:
    """Provider-specific OAuth logic for Google; storage/refresh-orchestration lives in OAuthManager."""

    def __init__(self, settings: Settings) -> None:
        if not (settings.google_client_id and settings.google_client_secret):
            raise GoogleAuthError("GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are not set")
        self._settings = settings

    @property
    def provider_name(self) -> str:
        return "google"

    def run_consent_flow(self, scopes: list[str]) -> TokenSet:
        # Desktop-app OAuth clients register a bare "http://localhost" redirect
        # (no fixed port) — Google accepts any local port at consent time, so
        # we let run_local_server pick an ephemeral one rather than forcing a
        # fixed port, which would only work if that exact port were registered.
        client_config = {
            "installed": {
                "client_id": self._settings.google_client_id,
                "client_secret": self._settings.google_client_secret,
                "auth_uri": _AUTH_URI,
                "token_uri": _TOKEN_URI,
                "redirect_uris": ["http://localhost"],
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, scopes=scopes)
        credentials = flow.run_local_server(port=0, open_browser=True)
        return _credentials_to_token_set(credentials)

    def refresh(self, token_set: TokenSet) -> TokenSet:
        credentials = _token_set_to_credentials(
            token_set, self._settings.google_client_id, self._settings.google_client_secret
        )
        credentials.refresh(Request())
        return _credentials_to_token_set(credentials)


def get_credentials(settings: Settings, scopes: list[str]) -> Credentials:
    """Return valid Google API credentials, authenticating or refreshing as needed.

    Thin compatibility wrapper: delegates all storage/refresh orchestration
    to the shared OAuthManager, then converts the resulting TokenSet back
    into the google-auth Credentials object the googleapiclient SDK expects.
    """
    manager = OAuthManager(settings.oauth_token_encryption_key or "")
    adapter = GoogleOAuthAdapter(settings)
    token_set = manager.get_token(adapter, scopes)
    return _token_set_to_credentials(token_set, settings.google_client_id, settings.google_client_secret)
