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

SECURITY — single-tenant only (audit finding F-04): _SESSIONS_KEY is one
global, unscoped key shared by every caller of this module. That is safe
ONLY because this whole server is explicitly single-user/trusted-LAN with
no authentication anywhere in the codebase (see server/app.py's own
"No authentication" comment — verified, not assumed, before writing this
note). There is no user/tenant identity available anywhere in this
application to scope a cache key by, so none is invented here. If this
server is ever extended to serve more than one user, this key MUST be
namespaced by whatever identity/tenant concept gets introduced (e.g.
f"mads:sessions:{user_id}") on every one of get_cached_sessions,
set_cached_sessions_if_current, and invalidate_sessions_cache below —
otherwise one user's session listing would be served to another. Do not
copy this module into a multi-tenant system without making that change
first.
"""

from __future__ import annotations

import json
import logging
import os
import time

import redis
from dotenv import load_dotenv

load_dotenv(override=False)

logger = logging.getLogger(__name__)

_SESSIONS_KEY = "mads:sessions"
# Bumped by invalidate_sessions_cache() on every write — lets a caller
# that started reading Postgres before an invalidation detect, after the
# fact, that its result is now potentially stale (see
# set_cached_sessions_if_current / audit finding F-02).
_GENERATION_KEY = "mads:sessions:gen"
_TTL_SECONDS = 300  # belt-and-suspenders expiry in case an invalidation is ever missed

# Atomically: only (re)populate the cache if the generation counter still
# matches what the caller observed before it started its Postgres read.
# A concurrent invalidate_sessions_cache() bumps the generation, which
# turns this into a deliberate no-op instead of a stale write clobbering
# newer data — a plain "GET generation, compare in Python, then SET" would
# itself be racy, so the compare-and-set has to happen server-side in one
# round trip.
_CAS_SET_SCRIPT = """
local current = redis.call("GET", KEYS[2])
if (current == false and ARGV[2] == "0") or current == ARGV[2] then
    redis.call("SET", KEYS[1], ARGV[1], "EX", ARGV[3])
    return 1
end
return 0
"""

_client: redis.Redis | None = None
# Cooldown-based unavailability (audit finding F-06) rather than a
# permanent latch: after a failure, caching is skipped until this
# deadline, then one fresh attempt is allowed. This recovers automatically
# if Redis comes back, without hammering it every single request while
# it's still down (each failed attempt still costs a connect timeout).
_RETRY_COOLDOWN_SECONDS = 30
_unavailable_until = 0.0
# Only log the transition into/out of "unavailable," not every request
# that happens to land while already in that state — otherwise a Redis
# outage turns into a log flood at this app's request volume.
_was_unavailable = False


def _mark_unavailable(exc: Exception) -> None:
    global _client, _unavailable_until, _was_unavailable
    _client = None
    _unavailable_until = time.monotonic() + _RETRY_COOLDOWN_SECONDS
    if not _was_unavailable:
        logger.warning(
            "Redis unavailable (%s: %s) — session list caching disabled for %ss, "
            "falling back to Postgres directly in the meantime.",
            type(exc).__name__, exc, _RETRY_COOLDOWN_SECONDS,
        )
        _was_unavailable = True


def _get_client() -> redis.Redis | None:
    """Returns None (rather than raising) when Redis is unreachable or
    still in its post-failure cooldown, so a misconfigured/down Redis
    degrades this app straight to "always hit Postgres" instead of
    breaking the sidebar outright — caching is a speed optimization here,
    not a correctness dependency.
    """
    global _client, _unavailable_until, _was_unavailable
    if time.monotonic() < _unavailable_until:
        return None
    if _was_unavailable:
        logger.info("Retrying Redis after cooldown — caching re-enabled if this succeeds.")
        _was_unavailable = False
    if _client is None:
        redis_url = os.environ.get("REDIS_URL")
        if not redis_url:
            # Not configured at all — not a failure, nothing to retry.
            _unavailable_until = float("inf")
            return None
        _client = redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
    return _client


def get_cached_sessions() -> list[dict] | None:
    client = _get_client()
    if client is None:
        return None
    try:
        raw = client.get(_SESSIONS_KEY)
    except redis.RedisError as exc:
        _mark_unavailable(exc)
        return None
    return json.loads(raw) if raw else None


def get_current_generation() -> str:
    """Snapshot the invalidation generation — call this BEFORE reading
    Postgres (see server/store.py's list_sessions), then pass the result
    to set_cached_sessions_if_current afterward. "0" (Redis's own
    representation of a counter key that's never been incremented) is the
    correct default both when Redis is unavailable and when no
    invalidation has ever happened yet; either way the later conditional
    write-back just degrades to "don't cache it," never to a stale write.
    """
    client = _get_client()
    if client is None:
        return "0"
    try:
        raw = client.get(_GENERATION_KEY)
    except redis.RedisError as exc:
        _mark_unavailable(exc)
        return "0"
    return raw.decode() if raw else "0"


def set_cached_sessions_if_current(sessions: list[dict], generation: str) -> None:
    """Writes to cache only if the generation hasn't moved since
    `generation` was read (see get_current_generation) — the fix for the
    cache-aside write-after-invalidate race (audit finding F-02). If a
    concurrent write invalidated the cache in between, this is a no-op:
    the stale result simply isn't cached, and the next reader re-queries
    Postgres, which is always correct.
    """
    client = _get_client()
    if client is None:
        return
    try:
        client.eval(_CAS_SET_SCRIPT, 2, _SESSIONS_KEY, _GENERATION_KEY, json.dumps(sessions), generation, str(_TTL_SECONDS))
    except redis.RedisError as exc:
        _mark_unavailable(exc)


def invalidate_sessions_cache() -> None:
    client = _get_client()
    if client is None:
        return
    try:
        # Pipelined with transaction=True (MULTI/EXEC) so the delete and
        # the generation bump are atomic together — a reader that observes
        # the new generation is guaranteed to also observe the deleted key,
        # and vice versa; no window where one applied and not the other.
        with client.pipeline(transaction=True) as pipe:
            pipe.delete(_SESSIONS_KEY)
            pipe.incr(_GENERATION_KEY)
            pipe.execute()
    except redis.RedisError as exc:
        _mark_unavailable(exc)
