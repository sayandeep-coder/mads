from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path

# Where chat history lives. Same ~/.mads home as _UPLOAD_DIR in app.py —
# this is a single-user, trusted-LAN server (see app.py's CORS comment),
# so one SQLite file with no auth/isolation is the right amount of
# ceremony for "remember my past conversations across restarts".
_DB_PATH = Path.home() / ".mads" / "chats.db"

_DEFAULT_TITLE = "New chat"


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


class ChatStore:
    """SQLite-backed persistence for chat sessions and their messages.

    Every call opens and closes its own connection — sqlite3 connections
    aren't safe to share across the threads FastAPI's asyncio.to_thread
    pool may use, and at this app's single-user scale the per-call open
    cost is irrelevant.
    """

    def __init__(self) -> None:
        with _connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL DEFAULT '',
                    tool_calls TEXT,
                    files TEXT,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id)")

    def create_session(self, title: str = _DEFAULT_TITLE) -> dict:
        session_id = uuid.uuid4().hex
        now = time.time()
        with _connect() as conn:
            conn.execute(
                "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (session_id, title, now, now),
            )
        return {"id": session_id, "title": title, "created_at": now, "updated_at": now}

    def list_sessions(self) -> list[dict]:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT s.id, s.title, s.created_at, s.updated_at,
                       (SELECT text FROM messages m WHERE m.session_id = s.id AND m.role = 'user'
                        ORDER BY m.id ASC LIMIT 1) AS preview
                FROM sessions s
                ORDER BY s.updated_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_session(self, session_id: str) -> dict | None:
        with _connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(row) if row else None

    def rename_session(self, session_id: str, title: str) -> None:
        with _connect() as conn:
            conn.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                (title, time.time(), session_id),
            )

    def touch_session(self, session_id: str) -> None:
        with _connect() as conn:
            conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (time.time(), session_id))

    def delete_session(self, session_id: str) -> None:
        with _connect() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    def add_message(
        self,
        session_id: str,
        role: str,
        text: str,
        tool_calls: list[dict] | None = None,
        files: list[dict] | None = None,
    ) -> None:
        now = time.time()
        with _connect() as conn:
            conn.execute(
                "INSERT INTO messages (session_id, role, text, tool_calls, files, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    role,
                    text,
                    json.dumps(tool_calls) if tool_calls else None,
                    json.dumps(files) if files else None,
                    now,
                ),
            )
            conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))

    def list_messages(self, session_id: str) -> list[dict]:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC", (session_id,)
            ).fetchall()
        messages = []
        for row in rows:
            item = dict(row)
            item["tool_calls"] = json.loads(item["tool_calls"]) if item["tool_calls"] else []
            item["files"] = json.loads(item["files"]) if item["files"] else []
            messages.append(item)
        return messages


chat_store = ChatStore()
