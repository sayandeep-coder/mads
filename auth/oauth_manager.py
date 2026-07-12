from __future__ import annotations

import json
import logging
from base64 import urlsafe_b64encode
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_AUTH_DIR = Path.home() / ".mads" / "auth"

# Refresh this many seconds before actual expiry, so a token that's about
# to expire mid-call doesn't get treated as still valid.
_EXPIRY_SAFETY_MARGIN = timedelta(seconds=60)


class OAuthError(RuntimeError):
    """Raised when credentials cannot be obtained or refreshed for a provider."""


@dataclass(frozen=True, slots=True)
class TokenSet:
    """Provider-neutral OAuth token state — the only shape OAuthManager knows about."""

    access_token: str
    refresh_token: str | None
    expires_at: str | None  # ISO 8601, or None if the token doesn't expire
    scopes: list[str]

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        expiry = datetime.fromisoformat(self.expires_at)
        return datetime.now(timezone.utc) >= expiry - _EXPIRY_SAFETY_MARGIN

    def has_scopes(self, required: list[str]) -> bool:
        return set(required).issubset(set(self.scopes))


class OAuthAdapter(Protocol):
    """Provider-specific OAuth logic. OAuthManager handles everything else:
    storage, encryption, expiry checking, and the refresh-vs-reauth decision.
    """

    @property
    def provider_name(self) -> str:
        """Short, filesystem-safe identifier, e.g. 'google' or 'spotify'."""
        ...

    def run_consent_flow(self, scopes: list[str]) -> TokenSet:
        """Run the one-time browser consent flow and return the resulting tokens."""
        ...

    def refresh(self, token_set: TokenSet) -> TokenSet:
        """Exchange a refresh token for a new access token."""
        ...


def _fernet(encryption_key: str) -> Fernet:
    # Derive a valid 32-byte urlsafe-base64 Fernet key from whatever string
    # the user supplied, so any sufficiently random secret works as-is.
    digest = sha256(encryption_key.encode("utf-8")).digest()
    return Fernet(urlsafe_b64encode(digest))


class OAuthManager:
    """Shared OAuth engine: encrypted local token storage, expiry checks, and
    the refresh-or-reauthenticate decision — identical for every provider.

    Each provider (Google, Spotify, future ones) supplies a small OAuthAdapter
    implementing only what's actually provider-specific: how to run consent
    and how to refresh a token. Everything else lives here exactly once.
    """

    def __init__(self, encryption_key: str) -> None:
        if not encryption_key:
            raise OAuthError("OAuth token encryption key is not set")
        self._fernet = _fernet(encryption_key)

    def _token_path(self, provider_name: str) -> Path:
        return _AUTH_DIR / f"{provider_name}.enc"

    def _load(self, provider_name: str) -> TokenSet | None:
        path = self._token_path(provider_name)
        if not path.exists():
            return None

        try:
            info = json.loads(self._fernet.decrypt(path.read_bytes()))
        except (InvalidToken, ValueError, json.JSONDecodeError):
            logger.warning("Stored %s token could not be decrypted; re-authentication required", provider_name)
            return None

        return TokenSet(**info)

    def _store(self, provider_name: str, token_set: TokenSet) -> None:
        _AUTH_DIR.mkdir(parents=True, exist_ok=True)
        path = self._token_path(provider_name)
        ciphertext = self._fernet.encrypt(json.dumps(asdict(token_set)).encode("utf-8"))
        path.write_bytes(ciphertext)
        path.chmod(0o600)

    def get_token(self, adapter: OAuthAdapter, scopes: list[str]) -> TokenSet:
        """Return a valid TokenSet for this provider, authenticating or refreshing as needed.

        First call: opens a browser for one-time OAuth consent and stores
        the resulting (encrypted) refresh token. Subsequent calls silently
        refresh the access token — no repeated login unless the refresh
        token itself is revoked/invalid, or the requested scopes have grown
        beyond what was previously granted.
        """
        token_set = self._load(adapter.provider_name)

        if token_set and not token_set.has_scopes(scopes):
            logger.info(
                "Stored %s token is missing newly requested scopes; re-authenticating", adapter.provider_name
            )
            token_set = None

        if token_set and not token_set.is_expired:
            return token_set

        if token_set and token_set.refresh_token:
            try:
                refreshed = adapter.refresh(token_set)
                self._store(adapter.provider_name, refreshed)
                return refreshed
            except Exception:
                logger.warning(
                    "Failed to refresh %s token; falling back to re-authentication", adapter.provider_name
                )

        token_set = adapter.run_consent_flow(scopes)
        self._store(adapter.provider_name, token_set)
        return token_set
