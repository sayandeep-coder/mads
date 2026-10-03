from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from server.db.connection import get_connection

_VALID_CATEGORIES = {"preference", "project", "decision", "person", "identity"}


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


def _row_to_memory(row: dict) -> Memory:
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

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO memories (category, content, tags, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (category, content, tags_str, now, now),
        )
        memory_id = cur.fetchone()["id"]

    return Memory(id=memory_id, category=category, content=content, tags=tags or [], created_at=now, updated_at=now)


def forget(memory_id: int) -> bool:
    """Delete a memory by id. Returns True if a memory was actually deleted."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM memories WHERE id = %s", (memory_id,))
        return cur.rowcount > 0


def update_memory(
    memory_id: int,
    content: str | None = None,
    tags: list[str] | None = None,
    category: str | None = None,
) -> Memory | None:
    """Update an existing memory's content, tags, and/or category. Returns the updated memory, or None if not found."""
    if category is not None:
        _validate_category(category)

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM memories WHERE id = %s", (memory_id,))
        row = cur.fetchone()
        if row is None:
            return None

        new_content = content if content is not None else row["content"]
        new_tags = ",".join(tags) if tags is not None else row["tags"]
        new_category = category if category is not None else row["category"]
        now = datetime.now(timezone.utc).isoformat()

        cur.execute(
            "UPDATE memories SET content = %s, tags = %s, category = %s, updated_at = %s WHERE id = %s",
            (new_content, new_tags, new_category, now, memory_id),
        )
        cur.execute("SELECT * FROM memories WHERE id = %s", (memory_id,))
        updated_row = cur.fetchone()

    return _row_to_memory(updated_row)


def list_all(category: str | None = None) -> list[Memory]:
    """List all memories, optionally filtered by category, most recently updated first."""
    with get_connection() as conn, conn.cursor() as cur:
        if category:
            _validate_category(category)
            cur.execute("SELECT * FROM memories WHERE category = %s ORDER BY updated_at DESC", (category,))
        else:
            cur.execute("SELECT * FROM memories ORDER BY updated_at DESC")
        rows = cur.fetchall()

    return [_row_to_memory(row) for row in rows]
