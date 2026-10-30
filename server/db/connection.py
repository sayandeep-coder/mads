from __future__ import annotations

import os

from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

# ChatStore's module-level `chat_store = ChatStore()` singleton is
# imported (server/app.py) before config.settings.get_settings() ever
# runs its own load_dotenv() — load it here too (override=False makes a
# second call harmless) so DATABASE_URL is in os.environ regardless of
# which module happens to touch the database first.
load_dotenv(override=False)

_pool: ConnectionPool | None = None


def _configure(conn) -> None:
    conn.row_factory = dict_row
    conn.autocommit = True
    register_vector(conn)


def get_db_pool() -> ConnectionPool:
    """A pooled connection to Neon opens once per process and is reused —
    a fresh psycopg.connect() per call was costing ~2 SECONDS on every
    single query (confirmed by timing a bare `SELECT 1`: Neon's serverless
    compute has real TLS-handshake + connection-routing overhead per new
    connection, not a per-query cost), which made every store in this app
    — chat, memory, planner, adaptive — far slower than it needed to be.
    A warm pooled connection cuts that same query to tens of milliseconds.
    """
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            os.environ["DATABASE_URL"],
            min_size=1,
            max_size=5,
            configure=_configure,
            # Single-user app behind a handful of concurrent requests at
            # most (one chat turn, maybe a background migration script) —
            # 5 is headroom, not a number tuned against real contention.
        )
    return _pool


def get_connection():
    """Context manager yielding a pooled connection with dict-row results
    and pgvector's `vector` type already registered — `with get_connection()
    as conn, conn.cursor() as cur:` works exactly as it did with a bare
    psycopg.connect(), just backed by the pool instead of a new socket.
    """
    return get_db_pool().connection()
