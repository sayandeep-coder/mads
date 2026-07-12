from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")
_BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")

_HEADING_STYLES = {1: "Heading1", 2: "Heading2", 3: "Heading3"}


def _markdown_inline_to_reportlab(text: str) -> str:
    """Convert '**bold**' spans to reportlab's <b> markup; escape any raw <, >, & first."""
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return _BOLD_RE.sub(r"<b>\1</b>", escaped)


def _markdown_to_flowables(markdown: str, styles) -> list:
    """Translate simple markdown ('#'/'##'/'###' headings, '**bold**', '-'/'*' bullets)
    into reportlab flowables — same supported subset as the Google Docs markdown renderer.
    """
    flowables: list = []
    pending_bullets: list[str] = []

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

    for raw_line in markdown.split("\n"):
        heading_match = _HEADING_RE.match(raw_line)
        bullet_match = _BULLET_RE.match(raw_line)

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

    flush_bullets()
    return flowables


def create_pdf(path: Path, title: str, content: str) -> None:
    """Build a real, valid PDF at `path` from a title and simple-markdown content.

    Uses reportlab's SimpleDocTemplate/Paragraph flowables — never writes raw
    text/markdown bytes directly to a .pdf file, which produces a corrupt,
    non-PDF file despite the extension.
    """
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(str(path), pagesize=letter)

    story: list = [Paragraph(title, styles["Title"]), Spacer(1, 0.25 * inch)]
    story.extend(_markdown_to_flowables(content, styles))

    document.build(story)
