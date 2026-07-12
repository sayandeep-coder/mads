from __future__ import annotations

import difflib
from typing import Any

_MAX_DIFF_LINES = 400


def compare_texts(text_a: str, label_a: str, text_b: str, label_b: str) -> dict[str, Any]:
    """Produce a unified diff between two documents' extracted text, plus a similarity ratio."""
    lines_a = text_a.splitlines()
    lines_b = text_b.splitlines()

    similarity = difflib.SequenceMatcher(None, text_a, text_b).ratio()

    diff_lines = list(
        difflib.unified_diff(lines_a, lines_b, fromfile=label_a, tofile=label_b, lineterm="")
    )
    truncated = len(diff_lines) > _MAX_DIFF_LINES

    result: dict[str, Any] = {
        "similarity_ratio": round(similarity, 4),
        "diff": "\n".join(diff_lines[:_MAX_DIFF_LINES]),
        "truncated": truncated,
    }
    if truncated:
        result["note"] = f"Diff truncated at {_MAX_DIFF_LINES} lines."
    return result
