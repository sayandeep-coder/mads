from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class FactCategory(StrEnum):
    PREFERENCE = "preference"
    DECISION = "decision"
    WORKFLOW = "workflow"
    CONSTRAINT = "constraint"
    IDENTITY = "identity"


class RawConversation(BaseModel):
    """A single conversation reconstructed from a ChatGPT export shard —
    the linear text of the path to current_node, not the raw branching tree.
    Never leaves the import pipeline; nothing downstream of extraction ever
    sees this."""

    model_config = ConfigDict(frozen=True)

    conversation_id: str
    title: str
    create_time: datetime | None
    content_hash: str
    text: str
    message_count: int


class ClassificationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    conversation_id: str
    worth_learning: bool


class CompressedConversation(BaseModel):
    model_config = ConfigDict(frozen=True)

    conversation_id: str
    title: str
    create_time: datetime | None
    text: str


class Candidate(BaseModel):
    """A single extracted fact before scoring/dedup — one per (conversation,
    statement), not yet merged with restatements from other conversations."""

    model_config = ConfigDict(frozen=True)

    category: FactCategory
    statement: str
    source_conversation_id: str
    source_title: str
    source_create_time: datetime | None


class ScoredCandidate(BaseModel):
    """A cluster of near-duplicate Candidates merged into one statement,
    with a confidence score reflecting recurrence/consistency/contradiction/recency."""

    model_config = ConfigDict(frozen=True)

    category: FactCategory
    statement: str
    confidence: float
    recurrence: int
    source_conversation_ids: list[str]
    contradicts: list[str] = Field(default_factory=list)
    latest_source_time: datetime | None = None


class PendingStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PendingCandidate(BaseModel):
    """A ScoredCandidate sitting in the approval queue — nothing here has
    reached the Adaptive Profile yet."""

    model_config = ConfigDict(frozen=True)

    id: int
    category: FactCategory
    statement: str
    confidence: float
    recurrence: int
    source_conversation_ids: list[str]
    contradicts: list[str] = Field(default_factory=list)
    status: PendingStatus = PendingStatus.PENDING
    created_at: datetime


class ApprovedFact(BaseModel):
    """A fact the user has explicitly approved — the only thing the
    Adaptive Profile ever exposes to the system prompt."""

    model_config = ConfigDict(frozen=True)

    id: int
    category: FactCategory
    statement: str
    confidence: float
    approved_at: datetime
    source_conversation_ids: list[str] = Field(default_factory=list)


class ProcessedLedgerEntry(BaseModel):
    """Marks a conversation as already run through the pipeline, keyed by
    id+hash so an edited/re-exported conversation is reprocessed but an
    unchanged one is skipped on the next import."""

    model_config = ConfigDict(frozen=True)

    conversation_id: str
    content_hash: str
    processed_at: datetime
    outcome: str  # "gated" | "not_worth_learning" | "extracted"
