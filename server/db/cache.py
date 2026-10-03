"""Redis cache-aside layer for ChatStore.list_sessions().

Why this one thing: list_sessions() is the sidebar's read — hit on every
page load and every sidebar refresh — and each call is a Postgres round
trip over the network to Neon (unlike the old local sqlite3 file, that
latency is now real). Everything else in server/store.py is either a
write (must hit Postgres for durability regardless) or a per-session read
already cached for free by _get_chat_agent's in-process Agent cache. This
is the one read worth caching; adding more speculative caching than that
would be solving a problem this single-user app doesn't actually have.

Cache-aside, not read-through: a miss reads Postgres and repopulates the
cache; any write invalidates it outright rather than trying to patch it in
place, since list_sessions()'s sort order and per-session preview text
make incremental updates more complex than they're worth for a few dozen
sessions.
"""

from __future__ import annotations

import json
import os

import redis
from dotenv import load_dotenv

load_dotenv(override=False)

_SESSIONS_KEY = "mads:sessions"
_TTL_SECONDS = 300  # belt-and-suspenders expiry in case an invalidation is ever missed

_client: redis.Redis | None = None
_unavailable = False


def _get_client() -> redis.Redis | None:
    """Returns None (rather than raising) once Redis has proven
    unreachable, so a misconfigured/down Redis degrades this app straight
    to "always hit Postgres" instead of breaking the sidebar outright —
    caching is a speed optimization here, not a correctness dependency.

    No ping() here: connecting lazily and letting the first real command
    fail (caught below) avoids doubling every cache op's round trip with a
    health check that gains nothing a try/except doesn't already cover.
    """
    global _client, _unavailable
    if _unavailable:
        return None
    if _client is None:
        redis_url = os.environ.get("REDIS_URL")
        if not redis_url:
            _unavailable = True
            return None
        _client = redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
    return _client


def get_cached_sessions() -> list[dict] | None:
    client = _get_client()
    if client is None:
        return None
    try:
        raw = client.get(_SESSIONS_KEY)
    except redis.RedisError:
        global _unavailable
        _unavailable = True
        return None
    return json.loads(raw) if raw else None


def set_cached_sessions(sessions: list[dict]) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        client.set(_SESSIONS_KEY, json.dumps(sessions), ex=_TTL_SECONDS)
    except redis.RedisError:
        pass


def invalidate_sessions_cache() -> None:
    client = _get_client()
    if client is None:
        return
    try:
        client.delete(_SESSIONS_KEY)
    except redis.RedisError:
        pass
