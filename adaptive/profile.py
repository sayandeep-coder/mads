from __future__ import annotations

from datetime import datetime, timezone

from adaptive.models import (
    ApprovedFact,
    FactCategory,
    PendingCandidate,
    PendingStatus,
    ScoredCandidate,
)
from server.db.connection import get_connection

_CATEGORY_HEADINGS = {
    FactCategory.IDENTITY: "Identity & Contact Info",
    FactCategory.PREFERENCE: "Preferences",
    FactCategory.DECISION: "Decisions",
    FactCategory.WORKFLOW: "Workflows",
    FactCategory.CONSTRAINT: "Constraints",
}


class CandidateNotFoundError(ValueError):
    """Raised when a pending candidate id doesn't exist."""


def _row_to_pending(row: dict) -> PendingCandidate:
    return PendingCandidate(
        id=row["id"],
        category=FactCategory(row["category"]),
        statement=row["statement"],
        confidence=row["confidence"],
        recurrence=row["recurrence"],
        source_conversation_ids=row["source_conversation_ids"] or [],
        contradicts=row["contradicts"] or [],
        status=PendingStatus(row["status"]),
        created_at=row["created_at"],
    )


def _row_to_approved(row: dict) -> ApprovedFact:
    return ApprovedFact(
        id=row["id"],
        category=FactCategory(row["category"]),
        statement=row["statement"],
        confidence=row["confidence"],
        approved_at=row["approved_at"],
        source_conversation_ids=row["source_conversation_ids"] or [],
    )


class AdaptiveProfile:
    """Owns the approval queue and the approved Adaptive Profile.

    Backed by the `adaptive_pending_candidates` and `adaptive_approved_facts`
    tables — this is the only boundary between the import pipeline (which
    handles raw conversation text) and everything else in Mads (which only
    ever sees approved, structured facts); nothing reaches ApprovedFact
    without passing through explicit user approval here.
    """

    def enqueue(self, scored_candidates: list[ScoredCandidate]) -> list[PendingCandidate]:
        """Add newly scored candidates to the pending queue. Does not
        deduplicate against existing pending/approved entries — that's a
        judgment call left to the user during review, since a new import
        run's clustering may phrase a recurring fact slightly differently
        than a previous approval."""
        now = datetime.now(timezone.utc)
        new_entries: list[PendingCandidate] = []

        with get_connection() as conn, conn.cursor() as cur:
            for c in scored_candidates:
                cur.execute(
                    """
                    INSERT INTO adaptive_pending_candidates
                        (category, statement, confidence, recurrence,
                         source_conversation_ids, contradicts, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (c.category.value, c.statement, c.confidence, c.recurrence,
                     c.source_conversation_ids, c.contradicts, PendingStatus.PENDING.value, now),
                )
                new_id = cur.fetchone()["id"]
                new_entries.append(
                    PendingCandidate(
                        id=new_id, category=c.category, statement=c.statement, confidence=c.confidence,
                        recurrence=c.recurrence, source_conversation_ids=c.source_conversation_ids,
                        contradicts=c.contradicts, status=PendingStatus.PENDING, created_at=now,
                    )
                )
        return new_entries

    def list_pending(self, category: FactCategory | None = None) -> list[PendingCandidate]:
        with get_connection() as conn, conn.cursor() as cur:
            if category is not None:
                cur.execute(
                    """
                    SELECT * FROM adaptive_pending_candidates
                    WHERE status = 'pending' AND category = %s
                    ORDER BY confidence DESC
                    """,
                    (category.value,),
                )
            else:
                cur.execute(
                    "SELECT * FROM adaptive_pending_candidates WHERE status = 'pending' ORDER BY confidence DESC"
                )
            rows = cur.fetchall()
        return [_row_to_pending(row) for row in rows]

    def approve(self, candidate_id: int) -> ApprovedFact:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM adaptive_pending_candidates WHERE id = %s", (candidate_id,))
            row = cur.fetchone()
            if row is None:
                raise CandidateNotFoundError(f"No pending candidate with id {candidate_id}")
            target = _row_to_pending(row)

            cur.execute(
                "UPDATE adaptive_pending_candidates SET status = 'approved' WHERE id = %s",
                (candidate_id,),
            )

            now = datetime.now(timezone.utc)
            cur.execute(
                """
                INSERT INTO adaptive_approved_facts (category, statement, confidence, approved_at, source_conversation_ids)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (target.category.value, target.statement, target.confidence, now, target.source_conversation_ids),
            )
            fact_id = cur.fetchone()["id"]

        return ApprovedFact(
            id=fact_id, category=target.category, statement=target.statement,
            confidence=target.confidence, approved_at=now, source_conversation_ids=target.source_conversation_ids,
        )

    def reject(self, candidate_id: int) -> bool:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE adaptive_pending_candidates SET status = 'rejected' WHERE id = %s AND status = 'pending'",
                (candidate_id,),
            )
            return cur.rowcount > 0

    # -- approved profile ---------------------------------------------------

    def list_approved(self, category: FactCategory | None = None) -> list[ApprovedFact]:
        with get_connection() as conn, conn.cursor() as cur:
            if category is not None:
                cur.execute("SELECT * FROM adaptive_approved_facts WHERE category = %s", (category.value,))
            else:
                cur.execute("SELECT * FROM adaptive_approved_facts")
            rows = cur.fetchall()
        return [_row_to_approved(row) for row in rows]

    def render_context(self) -> str:
        """Render the approved profile as a system-prompt block, or '' if
        nothing has been approved yet. Only ever reads ApprovedFact — raw
        conversation text and unapproved candidates never reach this method,
        by construction (they don't exist in this store).
        """
        facts = self.list_approved()
        if not facts:
            return ""

        by_category: dict[FactCategory, list[ApprovedFact]] = {}
        for fact in facts:
            by_category.setdefault(fact.category, []).append(fact)

        sections = ["## Adaptive Profile (learned from your history, approved by you)"]
        for category, heading in _CATEGORY_HEADINGS.items():
            items = by_category.get(category)
            if not items:
                continue
            lines = [f"### {heading}"] + [f"- {f.statement}" for f in items]
            sections.append("\n".join(lines))

        return "\n\n".join(sections)
