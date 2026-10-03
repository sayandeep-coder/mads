from __future__ import annotations

from datetime import datetime, timezone

from adaptive.models import RawConversation
from server.db.connection import get_connection


class Ledger:
    """Tracks which conversations have already been run through the
    pipeline, keyed by (conversation_id, content_hash) — so an edited or
    re-exported conversation is reprocessed but an unchanged one is
    skipped, making repeat imports cheap by construction. Backed by the
    `adaptive_ledger` table.
    """

    def is_processed(self, conversation: RawConversation) -> bool:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT content_hash FROM adaptive_ledger WHERE conversation_id = %s",
                (conversation.conversation_id,),
            )
            row = cur.fetchone()
        return row is not None and row["content_hash"] == conversation.content_hash

    def filter_unprocessed(self, conversations: list[RawConversation]) -> list[RawConversation]:
        if not conversations:
            return []
        ids = [c.conversation_id for c in conversations]
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT conversation_id, content_hash FROM adaptive_ledger WHERE conversation_id = ANY(%s)",
                (ids,),
            )
            hashes_by_id = {row["conversation_id"]: row["content_hash"] for row in cur.fetchall()}

        return [c for c in conversations if hashes_by_id.get(c.conversation_id) != c.content_hash]

    def mark_processed(self, conversation: RawConversation, outcome: str) -> None:
        self.mark_processed_batch([(conversation, outcome)])

    def mark_processed_batch(self, entries: list[tuple[RawConversation, str]]) -> None:
        """Batch version of mark_processed — one round trip instead of N,
        for use after a pipeline stage processes many conversations at once."""
        if not entries:
            return
        now = datetime.now(timezone.utc)
        with get_connection() as conn, conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO adaptive_ledger (conversation_id, content_hash, processed_at, outcome)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (conversation_id) DO UPDATE SET
                    content_hash = EXCLUDED.content_hash,
                    processed_at = EXCLUDED.processed_at,
                    outcome = EXCLUDED.outcome
                """,
                [(c.conversation_id, c.content_hash, now, outcome) for c, outcome in entries],
            )
