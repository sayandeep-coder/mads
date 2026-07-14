from __future__ import annotations

from adaptive.models import RawConversation

# A dumb floor, not a signal filter — this exists only to avoid spending a
# classifier call on conversations that cannot possibly carry a durable
# preference/decision/workflow/constraint. Real judgment happens in the
# Gemini classifier (adaptive.classifier), not here.
_MIN_MESSAGE_COUNT = 3
_MIN_TEXT_LENGTH = 80


def passes_gate(conversation: RawConversation) -> bool:
    if conversation.message_count < _MIN_MESSAGE_COUNT:
        return False
    if len(conversation.text) < _MIN_TEXT_LENGTH:
        return False
    return True


def apply_gate(conversations: list[RawConversation]) -> tuple[list[RawConversation], list[RawConversation]]:
    """Split conversations into (kept, gated_out)."""
    kept: list[RawConversation] = []
    gated_out: list[RawConversation] = []
    for c in conversations:
        (kept if passes_gate(c) else gated_out).append(c)
    return kept, gated_out
