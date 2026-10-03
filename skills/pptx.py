from __future__ import annotations

import asyncio
import zipfile
from typing import Any

from mcp import Tool

from config.settings import Settings
from mcp_servers.servers.document_intelligence import _pptx_writer
from skills._paths import resolve_allowed_write_path
from skills.registry import Skill

_ZIP_MAGIC = b"PK\x03\x04"

_INSTRUCTIONS = """\
# PowerPoint (PPTX) skill

Generate real, professional PowerPoint decks with `create_presentation`.

Supports a mix of slide types in one deck — build whatever mix best fits
the content; a real deck rarely uses only one type:
- `title`: {title, subtitle} — opening slide.
- `section`: {title} — a divider slide marking a new section.
- `bullets`: {title, bullets: [str, ...]} — title + bulleted content.
- `table`: {title, headers: [str,...], rows: [[str,...], ...]} — a real
  editable table.
- `chart`: {title, chart_type: 'bar'|'line'|'pie', categories: [str,...],
  series: {seriesName: [number,...]}} — a real editable native chart, not
  an image.
- `comparison`: {title, left: {heading, points:[str,...]}, right:
  {heading, points:[str,...]}} — two-column side-by-side comparison.
- `image`: {title?, path, caption?} — a real embedded picture, scaled to
  fit the slide with its aspect ratio preserved. Use this for a photo, a
  screenshot, a diagram, or a chart image you rendered elsewhere. Omit
  `title` for a full-bleed image slide.

Every slide type also accepts an optional `notes` string — real speaker
notes attached to that slide (visible in presenter view, never printed on
the slide itself). Add these for any deck meant to actually be presented,
not just read as a document — a few sentences of what to say, not a
repeat of the slide's own text.

All text fields support `**bold**` inline formatting. Bullets and
comparison points also support `#`/`##` hierarchy and optional `-`/`*`
bullet prefixes.

Use `accent_color` (hex, e.g. `#2D5BFF`) to theme the deck; omit for a
professional default blue.
"""


class PptxGenerationError(RuntimeError):
    """Raised when a generated PPTX fails validation (not a valid ZIP/OOXML package)."""


def _dispatch_sync(settings: Settings, name: str, arguments: dict) -> Any:
    if name != "create_presentation":
        raise ValueError(f"Unknown pptx skill tool: {name!r}")

    path = resolve_allowed_write_path(settings, arguments["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    _pptx_writer.create_presentation(path, arguments["slides"], arguments.get("accent_color"))

    with path.open("rb") as f:
        header = f.read(len(_ZIP_MAGIC))
    if header != _ZIP_MAGIC or not zipfile.is_zipfile(path):
        raise PptxGenerationError(f"Generated file at {path} is not a valid ZIP/OOXML package; not a valid PPTX.")

    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "slide_count": len(arguments["slides"]),
        "valid_pptx": True,
    }


_TOOLS = [
    Tool(
        name="create_presentation",
        description=(
            "Generate a real, professional PowerPoint (.pptx) deck from a list of slides. Use this "
            "whenever asked to create a presentation, slide deck, or PPT — for example a project "
            "update, pitch, or executive review. Supports a mix of slide types in one deck: "
            "\n- 'title': {title, subtitle} — opening slide."
            "\n- 'section': {title} — a divider slide marking a new section."
            "\n- 'bullets': {title, bullets: [str, ...]} — title + bulleted content."
            "\n- 'table': {title, headers: [str,...], rows: [[str,...], ...]} — a real editable table."
            "\n- 'chart': {title, chart_type: 'bar'|'line'|'pie', categories: [str,...], series: "
            "{seriesName: [number,...]}} — a real editable native chart, not an image."
            "\n- 'comparison': {title, left: {heading, points:[str,...]}, right: {heading, "
            "points:[str,...]}} — two-column side-by-side comparison."
            "\n- 'image': {title?, path, caption?} — a real embedded picture, scaled to fit with its "
            "aspect ratio preserved."
            "\nAny slide spec can also include 'notes': a string of real speaker notes for that slide "
            "(visible in presenter view, not printed on the slide) — add these whenever the deck is "
            "meant to actually be presented."
            "\nAll text fields support '**bold**' inline formatting. Bullets and comparison points "
            "also support '#'/'##' hierarchy and optional '-'/'*' bullet prefixes."
            "\nBuild a deck that mixes whatever slide types best fit the content — a real deck rarely "
            "uses only one type."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Where to save the deck, e.g. '~/review.pptx'."},
                "slides": {
                    "type": "array",
                    "description": "Ordered list of slide specs, each with a 'type' field as described above.",
                    "items": {"type": "object"},
                },
                "accent_color": {
                    "type": "string",
                    "description": "Hex accent color for the deck's theme, e.g. '#2D5BFF'. Defaults to a professional blue if omitted.",
                },
            },
            "required": ["path", "slides"],
        },
    ),
]


def build_skill(settings: Settings) -> Skill:
    async def dispatch(name: str, arguments: dict) -> Any:
        return await asyncio.to_thread(_dispatch_sync, settings, name, arguments)

    return Skill(
        name="pptx",
        description="Generate real, professional PowerPoint (.pptx) presentations.",
        instructions=_INSTRUCTIONS,
        tools=list(_TOOLS),
        dispatch=dispatch,
    )
