from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from adaptive.classifier import classify_conversations
from adaptive.compressor import compress_all
from adaptive.export_reader import read_conversations
from adaptive.extractor import extract_candidates
from adaptive.gatekeeper import apply_gate
from adaptive.ledger import Ledger
from adaptive.models import PendingCandidate
from adaptive.profile import AdaptiveProfile
from adaptive.scorer import score_candidates
from config.settings import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ImportStats:
    total_in_export: int
    already_processed: int
    gated_out: int
    classified: int
    worth_learning: int
    candidates_extracted: int
    candidates_scored: int
    enqueued: list[PendingCandidate]


async def run_import(settings: Settings, export_dir: Path) -> ImportStats:
    """Run the full Adaptive Intelligence import pipeline against a ChatGPT
    export directory: read -> skip already-processed -> gate -> classify ->
    compress -> extract -> score -> enqueue for approval.

    Nothing here writes to the Adaptive Profile directly — everything lands
    in the pending queue (adaptive.profile.AdaptiveProfile.enqueue), which
    only becomes profile knowledge once the user explicitly approves each
    item. The ledger is updated for every conversation that was actually
    read this run, regardless of outcome, so a second run against the same
    export is nearly free.
    """
    ledger = Ledger()
    profile = AdaptiveProfile()

    all_conversations = list(read_conversations(export_dir))
    unprocessed = ledger.filter_unprocessed(all_conversations)
    already_processed = len(all_conversations) - len(unprocessed)

    kept, gated_out = apply_gate(unprocessed)
    ledger.mark_processed_batch([(c, "gated") for c in gated_out])

    if not kept:
        return ImportStats(
            total_in_export=len(all_conversations),
            already_processed=already_processed,
            gated_out=len(gated_out),
            classified=0,
            worth_learning=0,
            candidates_extracted=0,
            candidates_scored=0,
            enqueued=[],
        )

    verdicts = await classify_conversations(settings, kept)
    worth_learning = [c for c in kept if verdicts.get(c.conversation_id)]
    not_worth_learning = [c for c in kept if not verdicts.get(c.conversation_id)]
    ledger.mark_processed_batch([(c, "not_worth_learning") for c in not_worth_learning])

    if not worth_learning:
        return ImportStats(
            total_in_export=len(all_conversations),
            already_processed=already_processed,
            gated_out=len(gated_out),
            classified=len(kept),
            worth_learning=0,
            candidates_extracted=0,
            candidates_scored=0,
            enqueued=[],
        )

    compressed = compress_all(worth_learning)
    candidates = await extract_candidates(settings, compressed)
    scored = await score_candidates(settings, candidates)
    enqueued = profile.enqueue(scored)

    ledger.mark_processed_batch([(c, "extracted") for c in worth_learning])

    return ImportStats(
        total_in_export=len(all_conversations),
        already_processed=already_processed,
        gated_out=len(gated_out),
        classified=len(kept),
        worth_learning=len(worth_learning),
        candidates_extracted=len(candidates),
        candidates_scored=len(scored),
        enqueued=enqueued,
    )
