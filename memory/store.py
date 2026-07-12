from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_DB_PATH = Path.home() / ".mads" / "memory.sqlite3"

_VALID_CATEGORIES = {"preference", "project", "decision", "person"}


class InvalidCategoryError(ValueError):
    """Raised when a memory category isn't one of the recognized kinds."""


@dataclass(frozen=True, slots=True)
class Memory:
    id: int
    category: str
    content: str
    tags: list[str]
    created_at: str
    updated_at: str


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    is_new_file = not _DB_PATH.exists()

    conn = sqlite3.connect(_DB_PATH)

    if is_new_file:
        # Memory contains personal preferences/projects/decisions in plain
        # text (unlike the encrypted OAuth tokens) — restrict to owner-only,
        # same posture as ~/.mads/auth/*.enc.
        _DB_PATH.chmod(0o600)

    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            content TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    return conn


def _row_to_memory(row: sqlite3.Row) -> Memory:
    tags = [t for t in row["tags"].split(",") if t]
    return Memory(
        id=row["id"],
        category=row["category"],
        content=row["content"],
        tags=tags,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _validate_category(category: str) -> None:
    if category not in _VALID_CATEGORIES:
        raise InvalidCategoryError(
            f"Unknown category {category!r}. Must be one of: {sorted(_VALID_CATEGORIES)}"
        )


def remember(category: str, content: str, tags: list[str] | None = None) -> Memory:
    """Store a new memory."""
    _validate_category(category)
    now = datetime.now(timezone.utc).isoformat()
    tags_str = ",".join(tags or [])

    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO memories (category, content, tags, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (category, content, tags_str, now, now),
        )
        memory_id = cursor.lastrowid

    return Memory(id=memory_id, category=category, content=content, tags=tags or [], created_at=now, updated_at=now)


def forget(memory_id: int) -> bool:
    """Delete a memory by id. Returns True if a memory was actually deleted."""
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        return cursor.rowcount > 0


def update_memory(memory_id: int, content: str | None = None, tags: list[str] | None = None) -> Memory | None:
    """Update an existing memory's content and/or tags. Returns the updated memory, or None if not found."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        if row is None:
            return None

        new_content = content if content is not None else row["content"]
        new_tags = ",".join(tags) if tags is not None else row["tags"]
        now = datetime.now(timezone.utc).isoformat()

        conn.execute(
            "UPDATE memories SET content = ?, tags = ?, updated_at = ? WHERE id = ?",
            (new_content, new_tags, now, memory_id),
        )
        updated_row = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()

    return _row_to_memory(updated_row)


def list_all(category: str | None = None) -> list[Memory]:
    """List all memories, optionally filtered by category, most recently updated first."""
    with _connect() as conn:
        if category:
            _validate_category(category)
            rows = conn.execute(
                "SELECT * FROM memories WHERE category = ? ORDER BY updated_at DESC", (category,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM memories ORDER BY updated_at DESC").fetchall()

    return [_row_to_memory(row) for row in rows]
