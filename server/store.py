from __future__ import annotations

import json
import time

from server.db import cache
from server.db.connection import get_connection

_DEFAULT_TITLE = "New chat"


class ChatStore:
    """Postgres-backed persistence for chat sessions and their messages.

    Table shape lives in server/db/schema.sql, applied once to the
    database up front — this class only ever reads/writes rows, it
    doesn't create tables itself (unlike the old sqlite3 version), so
    schema changes have one source of truth instead of two.
    """

    def create_session(self, title: str = _DEFAULT_TITLE) -> dict:
        now = time.time()
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sessions (id, title, created_at, updated_at)
                VALUES (gen_random_uuid()::text, %s, %s, %s)
                RETURNING id, title, created_at, updated_at
                """,
                (title, now, now),
            )
            created = dict(cur.fetchone())
        cache.invalidate_sessions_cache()
        return created

    def list_sessions(self) -> list[dict]:
        cached = cache.get_cached_sessions()
        if cached is not None:
            return cached

        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.id, s.title, s.created_at, s.updated_at,
                       (SELECT text FROM messages m WHERE m.session_id = s.id AND m.role = 'user'
                        ORDER BY m.id ASC LIMIT 1) AS preview
                FROM sessions s
                ORDER BY s.updated_at DESC
                """
            )
            sessions = [dict(row) for row in cur.fetchall()]

        cache.set_cached_sessions(sessions)
        return sessions

    def get_session(self, session_id: str) -> dict | None:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM sessions WHERE id = %s", (session_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def rename_session(self, session_id: str, title: str) -> None:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE sessions SET title = %s, updated_at = %s WHERE id = %s",
                (title, time.time(), session_id),
            )
        cache.invalidate_sessions_cache()

    def touch_session(self, session_id: str) -> None:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("UPDATE sessions SET updated_at = %s WHERE id = %s", (time.time(), session_id))
        cache.invalidate_sessions_cache()

    def delete_session(self, session_id: str) -> None:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM messages WHERE session_id = %s", (session_id,))
            cur.execute("DELETE FROM sessions WHERE id = %s", (session_id,))
        cache.invalidate_sessions_cache()

    def add_message(
        self,
        session_id: str,
        role: str,
        text: str,
        tool_calls: list[dict] | None = None,
        files: list[dict] | None = None,
    ) -> None:
        now = time.time()
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO messages (session_id, role, text, tool_calls, files, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    session_id,
                    role,
                    text,
                    json.dumps(tool_calls) if tool_calls else None,
                    json.dumps(files) if files else None,
                    now,
                ),
            )
            cur.execute("UPDATE sessions SET updated_at = %s WHERE id = %s", (now, session_id))
        cache.invalidate_sessions_cache()

    def list_messages(self, session_id: str) -> list[dict]:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM messages WHERE session_id = %s ORDER BY id ASC", (session_id,))
            rows = cur.fetchall()
        messages = []
        for row in rows:
            item = dict(row)
            item["tool_calls"] = json.loads(item["tool_calls"]) if item["tool_calls"] else []
            item["files"] = json.loads(item["files"]) if item["files"] else []
            messages.append(item)
        return messages


chat_store = ChatStore()
