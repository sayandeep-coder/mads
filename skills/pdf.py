from __future__ import annotations

import asyncio
import urllib.parse
import zipfile
from pathlib import Path
from typing import Any

import fitz
from mcp import Tool

from config.settings import Settings
from mcp_servers.servers.document_intelligence import _compare, _docx, _pdf, _pdf_writer
from skills._paths import resolve_allowed_path, resolve_allowed_write_path
from skills.registry import Skill

_PDF_MAGIC = b"%PDF-"

_INSTRUCTIONS = """\
# PDF skill

Read, generate, and annotate real PDF files.

## Reading
- `read_pdf` extracts text (optionally a page range for long documents —
  always use start_page/end_page rather than reading a huge PDF in one go).
  Scanned/image-only pages (a photographed marksheet, a certificate saved
  as a picture, no real text layer) are automatically OCR'd instead — the
  result carries an `ocr_pages` list and a `note` when this happened. OCR
  text can contain recognition errors (handwriting, stamps, low-quality
  scans especially), so when a result used OCR, read it as a best-effort
  transcription and mention that to Sayan rather than presenting it with
  the same confidence as a real embedded text layer.
- `extract_pdf_tables` pulls detected tables as row data.

## Creating
`create_pdf` builds a real, valid, professional PDF from a title +
markdown-ish content string, plus optional real embedded images. This is
a real document-production tool, not a plain text dump — use its actual
capabilities:
- Content markdown: `#`/`##`/`###` headings, `**bold**` spans, `-`/`*`
  bullet lists, GFM-style pipe tables (`| a | b |` with a `|---|---|`
  separator row right under the header, exactly like the chat UI's own
  tables) for any tabular data — real bordered/shaded tables, never
  ASCII-art or a bullet list pretending to be a table — and an explicit
  `---pagebreak---` line on its own to force a hard page break (e.g.
  before a new major section).
- `images`: a list of `{path, width_inches?, caption?}` to embed real
  images (a chart you rendered elsewhere, a photo, a diagram) after the
  main content, each scaled to fit the page with its real aspect ratio
  preserved and an optional caption underneath.
Use this whenever asked to save a report, summary, or write-up as a PDF —
and reach for a real table the moment the content has rows/columns of
data, not a bulleted approximation of one.

## Annotating
- `annotate_pdf` circles specific text and/or adds notes on an existing
  PDF. Pass the exact `target_text` to circle/annotate near — never invent
  coordinates; the tool finds the real text on the page for you. Each
  annotation needs `page_number` (1-indexed), a `type`
  (`circle_text`/`add_text`), and `annotation_text`. This writes a new
  `<name>_annotated.pdf` next to the original; give the user the returned
  download link.

## Comparing
- `compare_documents` diffs two PDFs (or DOCX/plain text files) and
  returns a unified diff plus a similarity ratio — use this to spot
  differences between two versions of a document or contract.
"""


class PdfGenerationError(RuntimeError):
    """Raised when a generated PDF fails validation (doesn't start with the PDF magic bytes)."""


def _get_color(color_name: str) -> tuple[float, float, float]:
    colors = {
        "red": (1.0, 0.0, 0.0),
        "blue": (0.0, 0.0, 1.0),
        "green": (0.0, 1.0, 0.0),
        "black": (0.0, 0.0, 0.0),
    }
    return colors.get(color_name.lower(), (1.0, 0.0, 0.0))


def _read_text_for_compare(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _pdf.read_pdf(path)["text"]
    if suffix == ".docx":
        return _docx.read_docx(path)["text"]
    return path.read_text(encoding="utf-8", errors="replace")


def _annotate_pdf(file_path: str, annotations: list[dict]) -> dict[str, Any]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    doc = fitz.open(file_path)
    try:
        for ann in annotations:
            page_idx = ann.get("page_number", 1) - 1
            if page_idx < 0 or page_idx >= len(doc):
                continue

            page = doc[page_idx]
            target_text = ann.get("target_text")
            ann_type = ann.get("type")
            ann_text = ann.get("annotation_text", "")
            color = _get_color(ann.get("color", "red"))
            position = ann.get("position", "right_of_circle")

            if not target_text:
                page.insert_text((50, 50), ann_text, color=color, fontsize=12)
                continue

            text_instances = page.search_for(target_text)
            if not text_instances:
                continue

            rect = text_instances[0]

            if ann_type == "circle_text":
                expanded_rect = fitz.Rect(rect.x0 - 2, rect.y0 - 2, rect.x1 + 2, rect.y1 + 2)
                page.draw_oval(expanded_rect, color=color, width=1.5)

            if ann_text:
                if position == "right_of_circle":
                    point = fitz.Point(rect.x1 + 10, rect.y1)
                elif position == "left_of_circle":
                    point = fitz.Point(rect.x0 - 50, rect.y1)
                elif position == "above_circle":
                    point = fitz.Point(rect.x0, rect.y0 - 10)
                elif position == "below_circle":
                    point = fitz.Point(rect.x0, rect.y1 + 15)
                else:
                    point = fitz.Point(rect.x1 + 10, rect.y1)
                page.insert_text(point, ann_text, color=color, fontsize=10)

        out_path = path.with_name(f"{path.stem}_annotated.pdf")
        doc.save(out_path)
    finally:
        doc.close()

    download_url = f"/api/files?path={urllib.parse.quote(out_path.absolute().as_posix())}"
    return {"path": str(out_path), "download_url": download_url}


def _dispatch_sync(settings: Settings, name: str, arguments: dict) -> Any:
    if name == "read_pdf":
        path = resolve_allowed_path(settings, arguments["path"])
        return _pdf.read_pdf(path, arguments.get("start_page"), arguments.get("end_page"))

    if name == "extract_pdf_tables":
        path = resolve_allowed_path(settings, arguments["path"])
        return _pdf.extract_pdf_tables(path, arguments.get("start_page"), arguments.get("end_page"))

    if name == "create_pdf":
        path = resolve_allowed_write_path(settings, arguments["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        _pdf_writer.create_pdf(path, arguments["title"], arguments["content"], arguments.get("images"))

        with path.open("rb") as f:
            header = f.read(len(_PDF_MAGIC))
        if header != _PDF_MAGIC:
            raise PdfGenerationError(
                f"Generated file at {path} does not start with the PDF magic bytes; not a valid PDF."
            )
        return {"path": str(path), "size_bytes": path.stat().st_size, "valid_pdf": True}

    if name == "annotate_pdf":
        path = resolve_allowed_path(settings, arguments["file_path"])
        return _annotate_pdf(str(path), arguments.get("annotations", []))

    if name == "compare_documents":
        path_a = resolve_allowed_path(settings, arguments["path_a"])
        path_b = resolve_allowed_path(settings, arguments["path_b"])
        return _compare.compare_texts(
            _read_text_for_compare(path_a), path_a.name, _read_text_for_compare(path_b), path_b.name
        )

    raise ValueError(f"Unknown pdf skill tool: {name!r}")


_TOOLS = [
    Tool(
        name="read_pdf",
        description=(
            "Extract text from a PDF file. Returns the extracted text plus page count. "
            "For large PDFs, specify start_page/end_page (1-indexed, inclusive) to read a "
            "specific range instead of the whole document. Scanned/image-only pages are "
            "automatically OCR'd — check the result's `ocr_pages`/`note` fields and flag to the "
            "user when a page was OCR'd, since that text may contain recognition errors."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the PDF file."},
                "start_page": {"type": "integer", "description": "First page to read (1-indexed)."},
                "end_page": {"type": "integer", "description": "Last page to read (1-indexed, inclusive)."},
            },
            "required": ["path"],
        },
    ),
    Tool(
        name="extract_pdf_tables",
        description="Extract all detected tables (as row data) from a PDF file.",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the PDF file."},
                "start_page": {"type": "integer", "description": "First page to search (1-indexed)."},
                "end_page": {"type": "integer", "description": "Last page to search (1-indexed, inclusive)."},
            },
            "required": ["path"],
        },
    ),
    Tool(
        name="create_pdf",
        description=(
            "Generate a real, valid, professional PDF file from a title and content. Content may use "
            "simple markdown — '#'/'##'/'###' headings, '**bold**' spans, '-'/'*' bullet lists, "
            "GFM-style pipe tables ('| a | b |' + a '|---|---|' separator row) for real bordered "
            "tables, and an explicit '---pagebreak---' line to force a page break — all rendered as "
            "real PDF formatting, never literal markdown characters. Use `images` to embed real "
            "pictures/charts/diagrams after the content. Use this whenever asked to save a report, "
            "summary, or document as a PDF — reach for a real table the moment the content is "
            "tabular, don't approximate one with bullets."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Where to save the PDF, e.g. '~/report.pdf'."},
                "title": {"type": "string", "description": "Document title, shown at the top of the PDF."},
                "content": {"type": "string", "description": "Body content, in simple markdown as described above."},
                "images": {
                    "type": "array",
                    "description": "Real images to embed after the content, each {path, width_inches?, caption?}.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "width_inches": {"type": "number"},
                            "caption": {"type": "string"},
                        },
                        "required": ["path"],
                    },
                },
            },
            "required": ["path", "title", "content"],
        },
    ),
    Tool(
        name="annotate_pdf",
        description="Annotate a PDF file with circles around specific text and/or added notes.",
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the PDF file to annotate."},
                "annotations": {
                    "type": "array",
                    "description": "List of annotations to apply.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "page_number": {"type": "integer", "description": "1-indexed page number."},
                            "type": {
                                "type": "string",
                                "enum": ["circle_text", "add_text"],
                                "description": "Type of annotation.",
                            },
                            "target_text": {
                                "type": "string",
                                "description": "Exact text to circle or place text near.",
                            },
                            "annotation_text": {"type": "string", "description": "Text to add."},
                            "color": {"type": "string", "description": "Color name, e.g. 'red'.", "default": "red"},
                            "position": {
                                "type": "string",
                                "enum": ["right_of_circle", "left_of_circle", "above_circle", "below_circle"],
                                "description": "Where to place the text relative to the target.",
                            },
                        },
                        "required": ["page_number", "type", "annotation_text"],
                    },
                },
            },
            "required": ["file_path", "annotations"],
        },
    ),
    Tool(
        name="compare_documents",
        description=(
            "Compare two documents (PDF, DOCX, or plain text files) and return a unified diff of "
            "their extracted text plus a similarity ratio. Use this to spot differences between two "
            "versions of a document, contract, or report."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "path_a": {"type": "string", "description": "Path to the first document."},
                "path_b": {"type": "string", "description": "Path to the second document."},
            },
            "required": ["path_a", "path_b"],
        },
    ),
]


def build_skill(settings: Settings) -> Skill:
    async def dispatch(name: str, arguments: dict) -> Any:
        return await asyncio.to_thread(_dispatch_sync, settings, name, arguments)

    return Skill(
        name="pdf",
        description="Read, generate, annotate, and compare PDF files.",
        instructions=_INSTRUCTIONS,
        tools=list(_TOOLS),
        dispatch=dispatch,
    )
