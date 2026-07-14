from __future__ import annotations

from datetime import datetime, timezone

from adaptive.models import (
    ApprovedFact,
    FactCategory,
    PendingCandidate,
    PendingStatus,
    ScoredCandidate,
)
from adaptive.storage import PENDING_PATH, PROFILE_PATH, JsonListStore

_CATEGORY_HEADINGS = {
    FactCategory.IDENTITY: "Identity & Contact Info",
    FactCategory.PREFERENCE: "Preferences",
    FactCategory.DECISION: "Decisions",
    FactCategory.WORKFLOW: "Workflows",
    FactCategory.CONSTRAINT: "Constraints",
}


class CandidateNotFoundError(ValueError):
    """Raised when a pending candidate id doesn't exist."""


class AdaptiveProfile:
    """Owns the approval queue and the approved Adaptive Profile.

    This is the only boundary between the import pipeline (which handles
    raw conversation text) and everything else in Mads (which only ever
    sees approved, structured facts) — nothing reaches ApprovedFact without
    passing through explicit user approval here.
    """

    def __init__(self) -> None:
        self._pending_store = JsonListStore(PENDING_PATH, PendingCandidate)
        self._profile_store = JsonListStore(PROFILE_PATH, ApprovedFact)

    # -- approval queue ----------------------------------------------------

    def enqueue(self, scored_candidates: list[ScoredCandidate]) -> list[PendingCandidate]:
        """Add newly scored candidates to the pending queue. Does not
        deduplicate against existing pending/approved entries — that's a
        judgment call left to the user during review, since a new import
        run's clustering may phrase a recurring fact slightly differently
        than a previous approval."""
        existing = self._pending_store.read_all()
        next_id = max((p.id for p in existing), default=0) + 1
        now = datetime.now(timezone.utc)

        new_entries = [
            PendingCandidate(
                id=next_id + i,
                category=c.category,
                statement=c.statement,
                confidence=c.confidence,
                recurrence=c.recurrence,
                source_conversation_ids=c.source_conversation_ids,
                contradicts=c.contradicts,
                status=PendingStatus.PENDING,
                created_at=now,
            )
            for i, c in enumerate(scored_candidates)
        ]

        self._pending_store.write_all(existing + new_entries)
        return new_entries

    def list_pending(self, category: FactCategory | None = None) -> list[PendingCandidate]:
        pending = [p for p in self._pending_store.read_all() if p.status == PendingStatus.PENDING]
        if category is not None:
            pending = [p for p in pending if p.category == category]
        return sorted(pending, key=lambda p: p.confidence, reverse=True)

    def approve(self, candidate_id: int) -> ApprovedFact:
        all_pending = self._pending_store.read_all()
        target = next((p for p in all_pending if p.id == candidate_id), None)
        if target is None:
            raise CandidateNotFoundError(f"No pending candidate with id {candidate_id}")

        updated_pending = [
            p.model_copy(update={"status": PendingStatus.APPROVED}) if p.id == candidate_id else p
            for p in all_pending
        ]
        self._pending_store.write_all(updated_pending)

        approved_facts = self._profile_store.read_all()
        next_id = max((f.id for f in approved_facts), default=0) + 1
        fact = ApprovedFact(
            id=next_id,
            category=target.category,
            statement=target.statement,
            confidence=target.confidence,
            approved_at=datetime.now(timezone.utc),
            source_conversation_ids=target.source_conversation_ids,
        )
        self._profile_store.write_all(approved_facts + [fact])
        return fact

    def reject(self, candidate_id: int) -> bool:
        all_pending = self._pending_store.read_all()
        if not any(p.id == candidate_id for p in all_pending):
            return False

        updated = [
            p.model_copy(update={"status": PendingStatus.REJECTED}) if p.id == candidate_id else p
            for p in all_pending
        ]
        self._pending_store.write_all(updated)
        return True

    # -- approved profile ---------------------------------------------------

    def list_approved(self, category: FactCategory | None = None) -> list[ApprovedFact]:
        facts = self._profile_store.read_all()
        if category is not None:
            facts = [f for f in facts if f.category == category]
        return facts

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
