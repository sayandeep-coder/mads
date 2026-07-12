from __future__ import annotations

from pathlib import Path
from typing import Any

import docx

_MAX_CHARS = 50_000


def read_docx(path: Path) -> dict[str, Any]:
    """Extract paragraph text (with heading structure) from a Word document."""
    document = docx.Document(str(path))

    paragraphs: list[dict[str, str]] = []
    text_parts: list[str] = []
    for paragraph in document.paragraphs:
        if not paragraph.text.strip():
            continue
        paragraphs.append({"text": paragraph.text, "style": paragraph.style.name if paragraph.style else "Normal"})
        text_parts.append(paragraph.text)

    full_text = "\n".join(text_parts)
    truncated = len(full_text) > _MAX_CHARS

    result: dict[str, Any] = {
        "paragraph_count": len(paragraphs),
        "text": full_text[:_MAX_CHARS],
        "truncated": truncated,
    }
    if truncated:
        result["note"] = f"Text truncated at {_MAX_CHARS} characters."
    return result


def extract_docx_tables(path: Path) -> list[dict[str, Any]]:
    """Extract all tables from a Word document as row-lists."""
    document = docx.Document(str(path))

    tables: list[dict[str, Any]] = []
    for index, table in enumerate(document.tables):
        rows = [[cell.text for cell in row.cells] for row in table.rows]
        tables.append({"table_index": index, "rows": rows})
    return tables
