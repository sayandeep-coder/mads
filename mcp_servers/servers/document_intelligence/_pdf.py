from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pymupdf
import pytesseract
from PIL import Image

_MAX_CHARS = 50_000

# A page whose real text layer has fewer than this many non-whitespace
# characters is treated as "no meaningful extractable text" — a scanned
# page (a photographed marksheet, a certificate saved as a picture) still
# has get_text() return an empty string or, sometimes, a stray watermark/
# header string, never a real body of text.
_MIN_REAL_TEXT_CHARS = 20

# Render scale for OCR: pymupdf's default pixmap is 72 DPI, too low for
# Tesseract to read reliably. 2x roughly matches 144 DPI, a reasonable
# quality/speed tradeoff for a scanned document page.
_OCR_ZOOM = 2.0


def _ocr_page(page: pymupdf.Page) -> str:
    """Render a page to an image and OCR it — the real fix for scanned/
    image-only pages, not a guess: Tesseract (already installed on this
    Mac via Homebrew) reads the rendered pixels directly rather than
    relying on a text layer that simply doesn't exist for these pages.
    """
    matrix = pymupdf.Matrix(_OCR_ZOOM, _OCR_ZOOM)
    pixmap = page.get_pixmap(matrix=matrix)
    image = Image.open(io.BytesIO(pixmap.tobytes("png")))
    return pytesseract.image_to_string(image)


def _extract_page_text(page: pymupdf.Page) -> tuple[str, bool]:
    """Returns (text, was_ocr) for one page — real text layer if it has
    meaningful content, otherwise an OCR pass over the rendered page.
    """
    real_text = page.get_text()
    if len(real_text.strip()) >= _MIN_REAL_TEXT_CHARS:
        return real_text, False

    ocr_text = _ocr_page(page)
    if ocr_text.strip():
        return ocr_text, True

    # Genuinely blank page (or OCR found nothing either) — report the
    # sparse real_text as-is rather than inventing content; a truly empty
    # page is a real, distinct case, never treated as an error.
    return real_text, False


def read_pdf(path: Path, start_page: int | None = None, end_page: int | None = None) -> dict[str, Any]:
    """Extract text from a PDF, optionally restricted to a 1-indexed inclusive page range.

    Falls back to OCR (Tesseract) per page when a page has no meaningful
    real text layer — a scanned document or an image-only page (a
    photographed marksheet, a certificate saved as a picture) would
    otherwise silently come back near-empty from the real text layer alone.
    """
    document = pymupdf.open(path)
    try:
        page_count = document.page_count
        first = max((start_page or 1) - 1, 0)
        last = min(end_page or page_count, page_count)

        text_parts: list[str] = []
        ocr_pages: list[int] = []
        for page_index in range(first, last):
            page_text, was_ocr = _extract_page_text(document[page_index])
            text_parts.append(page_text)
            if was_ocr:
                ocr_pages.append(page_index + 1)
        full_text = "\n".join(text_parts)

        truncated = len(full_text) > _MAX_CHARS
        text = full_text[:_MAX_CHARS]

        result: dict[str, Any] = {
            "page_count": page_count,
            "pages_read": f"{first + 1}-{last}",
            "text": text,
            "truncated": truncated,
        }
        notes: list[str] = []
        if truncated:
            notes.append(
                f"Text truncated at {_MAX_CHARS} characters. Document has {page_count} pages; "
                "specify start_page/end_page to read a narrower range."
            )
        if ocr_pages:
            result["ocr_pages"] = ocr_pages
            notes.append(
                f"Page(s) {', '.join(map(str, ocr_pages))} had no real text layer (a scanned/image "
                "page) and were read via OCR instead — OCR text can contain recognition errors, "
                "especially for handwriting, stamps, or low-quality scans; treat it as a best-effort "
                "reading, not a guaranteed-exact transcription."
            )
        if notes:
            result["note"] = " ".join(notes)
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
