from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from adaptive.models import RawConversation

_MIN_MESSAGE_COUNT = 1

# Only these content_types carry conversational prose. 'thoughts' and
# 'reasoning_recap' are internal model reasoning traces, not something the
# user said or a conclusion reached — including them would pollute
# extraction with the model's scratch work rather than actual decisions.
_TEXT_CONTENT_TYPES = {"text", "multimodal_text"}


def _extract_text_from_message(message: dict[str, Any]) -> str:
    content = message.get("content", {})
    if content.get("content_type") not in _TEXT_CONTENT_TYPES:
        return ""

    fragments: list[str] = []
    for part in content.get("parts", []):
        if isinstance(part, str):
            if part.strip():
                fragments.append(part.strip())
        elif isinstance(part, dict) and isinstance(part.get("text"), str):
            if part["text"].strip():
                fragments.append(part["text"].strip())

    return "\n".join(fragments)


def _linearize(conversation: dict[str, Any]) -> tuple[str, int]:
    """Walk the parent chain from current_node back to root, producing the
    linear conversation as currently visible in ChatGPT's UI — this skips
    abandoned regeneration branches rather than including every dead end
    in the tree."""
    mapping = conversation.get("mapping", {})
    node_id = conversation.get("current_node")

    chain: list[str] = []
    while node_id is not None:
        node = mapping.get(node_id)
        if node is None:
            break
        chain.append(node_id)
        node_id = node.get("parent")
    chain.reverse()

    lines: list[str] = []
    message_count = 0
    for nid in chain:
        message = mapping[nid].get("message")
        if message is None:
            continue
        role = message.get("author", {}).get("role")
        if role not in ("user", "assistant"):
            continue
        text = _extract_text_from_message(message)
        if not text:
            continue
        message_count += 1
        speaker = "You" if role == "user" else "Assistant"
        lines.append(f"{speaker}: {text}")

    return "\n\n".join(lines), message_count


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_conversations(export_dir: Path) -> Iterator[RawConversation]:
    """Yield every conversation across all conversations-*.json shards in a
    ChatGPT export directory, reconstructed as linear text.

    This is the only place raw export JSON is read — everything downstream
    of this module works with RawConversation, never the original tree.
    """
    shard_paths = sorted(export_dir.glob("conversations*.json"))

    for shard_path in shard_paths:
        conversations = json.loads(shard_path.read_text(encoding="utf-8"))
        for conversation in conversations:
            text, message_count = _linearize(conversation)
            if message_count < _MIN_MESSAGE_COUNT:
                continue

            create_time = conversation.get("create_time")
            yield RawConversation(
                conversation_id=conversation["conversation_id"],
                title=conversation.get("title") or "(untitled)",
                create_time=(
                    datetime.fromtimestamp(create_time, tz=timezone.utc)
                    if create_time
                    else None
                ),
                content_hash=_content_hash(text),
                text=text,
                message_count=message_count,
            )
