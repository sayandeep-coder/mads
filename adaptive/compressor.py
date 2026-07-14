from __future__ import annotations

import re

from adaptive.models import CompressedConversation, RawConversation

_TARGET_CHARS = 1500

# Lines that are pure social filler carry no extraction signal — dropping
# them before truncation means the character budget goes to actual
# substance instead of "good morning" and "thanks bhai".
_FILLER_PATTERNS = (
    re.compile(r"^(hi|hello|hey|hola|namaste)\b.{0,20}$", re.IGNORECASE),
    re.compile(r"^(thanks?|thank you|shukriya|dhanyawad)[!. ]*$", re.IGNORECASE),
    re.compile(r"^(ok|okay|cool|nice|great|good|got it|got itt?)[!. ]*$", re.IGNORECASE),
    re.compile(r"^(bye|goodbye|see ya|alvida)[!. ]*$", re.IGNORECASE),
    re.compile(r"^(kaise ho|kya haal hai|kaisa hai)\b.{0,20}$", re.IGNORECASE),
)

# A line that's almost entirely a fenced code block contributes little to
# "what does the user prefer" — keep a short marker instead of the full
# block so the character budget favors surrounding prose (the actual
# preference/decision framing) over verbatim code.
_CODE_FENCE_PATTERN = re.compile(r"```[\s\S]*?```")


_SPEAKER_PREFIX_PATTERN = re.compile(r"^(You|Assistant):\s*")


def _is_filler_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    # Lines carry a "You: "/"Assistant: " prefix from the linearizer —
    # strip it before matching, since the filler patterns describe the
    # utterance itself, not the transcript formatting around it.
    content = _SPEAKER_PREFIX_PATTERN.sub("", stripped)
    return any(pattern.match(content) for pattern in _FILLER_PATTERNS)


def _collapse_code_blocks(text: str) -> str:
    def _replace(match: re.Match) -> str:
        block = match.group(0)
        first_line = block.splitlines()[0] if block.splitlines() else "```"
        lang = first_line.removeprefix("```").strip() or "code"
        return f"[{lang} code block omitted]"

    return _CODE_FENCE_PATTERN.sub(_replace, text)


def _strip_filler(text: str) -> str:
    lines = text.split("\n")
    kept_lines = [line for line in lines if not _is_filler_line(line)]
    # collapse resulting blank-line runs from removed filler
    collapsed = re.sub(r"\n{3,}", "\n\n", "\n".join(kept_lines))
    return collapsed.strip()


def _truncate_keep_edges(text: str, target_chars: int) -> str:
    """Keep the first and last portions of a conversation — framing and
    conclusions tend to live at the edges, the meandering middle is where
    exploration/back-and-forth (lower signal density) usually lives."""
    if len(text) <= target_chars:
        return text

    half = target_chars // 2
    head = text[:half]
    tail = text[-half:]
    return f"{head}\n\n[...]\n\n{tail}"


def compress(conversation: RawConversation, target_chars: int = _TARGET_CHARS) -> CompressedConversation:
    text = _collapse_code_blocks(conversation.text)
    text = _strip_filler(text)
    text = _truncate_keep_edges(text, target_chars)

    return CompressedConversation(
        conversation_id=conversation.conversation_id,
        title=conversation.title,
        create_time=conversation.create_time,
        text=text,
    )


def compress_all(
    conversations: list[RawConversation], target_chars: int = _TARGET_CHARS
) -> list[CompressedConversation]:
    return [compress(c, target_chars) for c in conversations]
