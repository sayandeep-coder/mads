"""One-off: embed every existing memory/approved-fact row that predates
the embedding column (added after the Postgres migration). Idempotent —
only touches rows where embedding IS NULL, so re-running after new rows
land costs nothing extra.

Run with: uv run python3 -m server.db.backfill_embeddings
"""

from __future__ import annotations

from server.db.connection import get_connection
from server.embeddings import embed_text


def backfill_memories() -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, content FROM memories WHERE embedding IS NULL")
        rows = cur.fetchall()
        for row in rows:
            embedding = embed_text(row["content"])
            cur.execute("UPDATE memories SET embedding = %s WHERE id = %s", (embedding, row["id"]))
    print(f"memories: embedded {len(rows)} rows")


def backfill_adaptive_facts() -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, statement FROM adaptive_approved_facts WHERE embedding IS NULL")
        rows = cur.fetchall()
        for row in rows:
            embedding = embed_text(row["statement"])
            cur.execute("UPDATE adaptive_approved_facts SET embedding = %s WHERE id = %s", (embedding, row["id"]))
    print(f"adaptive_approved_facts: embedded {len(rows)} rows")


if __name__ == "__main__":
    backfill_memories()
    backfill_adaptive_facts()
    print("Backfill complete.")
