from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")
_BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_PAGEBREAK_RE = re.compile(r"^-{3,}\s*pagebreak\s*-{3,}$", re.IGNORECASE)

_HEADING_STYLES = {1: "Heading1", 2: "Heading2", 3: "Heading3"}

_TABLE_HEADER_BG = colors.HexColor("#1F2937")
_TABLE_ROW_ALT_BG = colors.HexColor("#F3F4F6")


def _markdown_inline_to_reportlab(text: str) -> str:
    """Convert '**bold**' spans to reportlab's <b> markup; escape any raw <, >, & first."""
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return _BOLD_RE.sub(r"<b>\1</b>", escaped)


def _parse_markdown_table(lines: list[str], start: int) -> tuple[list[list[str]], int] | None:
    """If `lines[start]` begins a GFM-style pipe table (a header row
    immediately followed by a '|---|---|' separator row), parse the whole
    block and return (rows, next_index) — otherwise None.
    """
    if "|" not in lines[start]:
        return None
    if start + 1 >= len(lines):
        return None

    separator = lines[start + 1].strip()
    if not re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?", separator):
        return None

    def split_row(line: str) -> list[str]:
        trimmed = line.strip().strip("|")
        return [cell.strip() for cell in trimmed.split("|")]

    rows = [split_row(lines[start])]
    index = start + 2
    while index < len(lines) and "|" in lines[index] and lines[index].strip():
        rows.append(split_row(lines[index]))
        index += 1

    return rows, index


def _build_table_flowable(rows: list[list[str]]) -> Table:
    styled_rows = [
        [Paragraph(_markdown_inline_to_reportlab(cell), getSampleStyleSheet()["Normal"]) for cell in row]
        for row in rows
    ]
    table = Table(styled_rows, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _TABLE_HEADER_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _TABLE_ROW_ALT_BG]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _markdown_to_flowables(markdown: str, styles) -> list:
    """Translate simple markdown into reportlab flowables: '#'/'##'/'###'
    headings, '**bold**', '-'/'*' bullets, GFM-style pipe tables
    ('| a | b |' + '|---|---|' separator, same syntax the chat UI already
    renders), and an explicit '---pagebreak---' marker for a hard page
    break — same supported subset as the chat UI's own markdown renderer,
    plus tables/page-breaks which are PDF-specific real capabilities.
    """
    flowables: list = []
    pending_bullets: list[str] = []
    lines = markdown.split("\n")

    def flush_bullets() -> None:
        if not pending_bullets:
            return
        flowables.append(
            ListFlowable(
                [ListItem(Paragraph(item, styles["Normal"])) for item in pending_bullets],
                bulletType="bullet",
            )
        )
        pending_bullets.clear()

    index = 0
    while index < len(lines):
        raw_line = lines[index]
        heading_match = _HEADING_RE.match(raw_line)
        bullet_match = _BULLET_RE.match(raw_line)

        if _PAGEBREAK_RE.match(raw_line.strip()):
            flush_bullets()
            flowables.append(PageBreak())
            index += 1
            continue

        table_result = _parse_markdown_table(lines, index)
        if table_result:
            flush_bullets()
            rows, next_index = table_result
            flowables.append(_build_table_flowable(rows))
            flowables.append(Spacer(1, 0.15 * inch))
            index = next_index
            continue

        if heading_match:
            flush_bullets()
            level = len(heading_match.group(1))
            text = _markdown_inline_to_reportlab(heading_match.group(2))
            flowables.append(Paragraph(text, styles[_HEADING_STYLES[level]]))
        elif bullet_match:
            pending_bullets.append(_markdown_inline_to_reportlab(bullet_match.group(1)))
        elif raw_line.strip():
            flush_bullets()
            flowables.append(Paragraph(_markdown_inline_to_reportlab(raw_line), styles["Normal"]))
        else:
            flush_bullets()
            flowables.append(Spacer(1, 0.15 * inch))
        index += 1

    flush_bullets()
    return flowables


def _build_image_flowable(image_spec: dict[str, Any]) -> list:
    """image_spec: {path, width_inches?, caption?}. Embeds a real image at
    its path, scaled to fit the page width (preserving its real aspect
    ratio, read via PIL) if no explicit width is given, with an optional
    caption underneath.
    """
    from PIL import Image as PILImage

    flowables: list = []
    width_inches = image_spec.get("width_inches") or 6.0

    with PILImage.open(image_spec["path"]) as source_image:
        source_width, source_height = source_image.size
    height_inches = width_inches * (source_height / source_width) if source_width else width_inches

    # Cap the height too — a very tall/narrow image (e.g. a long
    # screenshot) at full page width could otherwise overflow a page's
    # printable height entirely.
    max_height_inches = 9.0
    if height_inches > max_height_inches:
        scale = max_height_inches / height_inches
        width_inches *= scale
        height_inches = max_height_inches

    image = Image(image_spec["path"], width=width_inches * inch, height=height_inches * inch, hAlign="CENTER")
    flowables.append(image)
    if image_spec.get("caption"):
        styles = getSampleStyleSheet()
        caption_style = styles["Italic"]
        flowables.append(Paragraph(image_spec["caption"], caption_style))
    flowables.append(Spacer(1, 0.2 * inch))
    return flowables


def create_pdf(
    path: Path,
    title: str,
    content: str,
    images: list[dict[str, Any]] | None = None,
) -> None:
    """Build a real, valid PDF at `path` from a title, simple-markdown
    content (headings, bold, bullets, GFM tables, '---pagebreak---'), and
    optional real embedded images (each {path, width_inches?, caption?}),
    appended after the main content.

    Uses reportlab's SimpleDocTemplate/Paragraph/Table/Image flowables —
    never writes raw text/markdown bytes directly to a .pdf file, which
    produces a corrupt, non-PDF file despite the extension.
    """
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(str(path), pagesize=letter)

    story: list = [Paragraph(title, styles["Title"]), Spacer(1, 0.25 * inch)]
    story.extend(_markdown_to_flowables(content, styles))

    for image_spec in images or []:
        story.extend(_build_image_flowable(image_spec))

    document.build(story)
