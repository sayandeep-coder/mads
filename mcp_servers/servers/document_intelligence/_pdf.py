from __future__ import annotations

from pathlib import Path
from typing import Any

import pymupdf

_MAX_CHARS = 50_000


def read_pdf(path: Path, start_page: int | None = None, end_page: int | None = None) -> dict[str, Any]:
    """Extract text from a PDF, optionally restricted to a 1-indexed inclusive page range."""
    document = pymupdf.open(path)
    try:
        page_count = document.page_count
        first = max((start_page or 1) - 1, 0)
        last = min(end_page or page_count, page_count)

        text_parts: list[str] = []
        for page_index in range(first, last):
            text_parts.append(document[page_index].get_text())
        full_text = "\n".join(text_parts)

        truncated = len(full_text) > _MAX_CHARS
        text = full_text[:_MAX_CHARS]

        result: dict[str, Any] = {
            "page_count": page_count,
            "pages_read": f"{first + 1}-{last}",
            "text": text,
            "truncated": truncated,
        }
        if truncated:
            result["note"] = (
                f"Text truncated at {_MAX_CHARS} characters. Document has {page_count} pages; "
                "specify start_page/end_page to read a narrower range."
            )
        return result
    finally:
        document.close()


def extract_pdf_tables(path: Path, start_page: int | None = None, end_page: int | None = None) -> list[dict[str, Any]]:
    """Extract detected tables from a PDF, optionally restricted to a 1-indexed inclusive page range."""
    document = pymupdf.open(path)
    try:
        page_count = document.page_count
        first = max((start_page or 1) - 1, 0)
        last = min(end_page or page_count, page_count)

        tables: list[dict[str, Any]] = []
        for page_index in range(first, last):
            page = document[page_index]
            for table in page.find_tables().tables:
                tables.append({"page": page_index + 1, "rows": table.extract()})
        return tables
    finally:
        document.close()
