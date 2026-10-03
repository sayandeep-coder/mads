from __future__ import annotations

import os

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

# ChatStore's module-level `chat_store = ChatStore()` singleton is
# imported (server/app.py) before config.settings.get_settings() ever
# runs its own load_dotenv() — load it here too (override=False makes a
# second call harmless) so DATABASE_URL is in os.environ regardless of
# which module happens to touch the database first.
load_dotenv(override=False)


def get_connection() -> psycopg.Connection:
    """One psycopg connection per call, dict-row results — same per-call-
    connection posture the old sqlite3 stores used (this app is single-
    user/single-process, so connection pooling isn't warranted), just
    pointed at Postgres (DATABASE_URL, e.g. a Neon branch) instead of a
    local file.
    """
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, autocommit=True)
