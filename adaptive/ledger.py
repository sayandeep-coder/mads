from __future__ import annotations

from datetime import datetime, timezone

from adaptive.models import ProcessedLedgerEntry, RawConversation
from adaptive.storage import LEDGER_PATH, JsonListStore


class Ledger:
    """Tracks which conversations have already been run through the
    pipeline, keyed by (conversation_id, content_hash) — so an edited or
    re-exported conversation is reprocessed but an unchanged one is
    skipped, making repeat imports cheap by construction.
    """

    def __init__(self) -> None:
        self._store = JsonListStore(LEDGER_PATH, ProcessedLedgerEntry)

    def _entries_by_id(self) -> dict[str, ProcessedLedgerEntry]:
        return {e.conversation_id: e for e in self._store.read_all()}

    def is_processed(self, conversation: RawConversation) -> bool:
        entry = self._entries_by_id().get(conversation.conversation_id)
        return entry is not None and entry.content_hash == conversation.content_hash

    def filter_unprocessed(self, conversations: list[RawConversation]) -> list[RawConversation]:
        by_id = self._entries_by_id()
        unprocessed = []
        for c in conversations:
            entry = by_id.get(c.conversation_id)
            if entry is None or entry.content_hash != c.content_hash:
                unprocessed.append(c)
        return unprocessed

    def mark_processed(self, conversation: RawConversation, outcome: str) -> None:
        entries = self._entries_by_id()
        entries[conversation.conversation_id] = ProcessedLedgerEntry(
            conversation_id=conversation.conversation_id,
            content_hash=conversation.content_hash,
            processed_at=datetime.now(timezone.utc),
            outcome=outcome,
        )
        self._store.write_all(list(entries.values()))

    def mark_processed_batch(self, entries: list[tuple[RawConversation, str]]) -> None:
        """Batch version of mark_processed — one disk write instead of N,
        for use after a pipeline stage processes many conversations at once."""
        current = self._entries_by_id()
        now = datetime.now(timezone.utc)
        for conversation, outcome in entries:
            current[conversation.conversation_id] = ProcessedLedgerEntry(
                conversation_id=conversation.conversation_id,
                content_hash=conversation.content_hash,
                processed_at=now,
                outcome=outcome,
            )
        self._store.write_all(list(current.values()))
