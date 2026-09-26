from __future__ import annotations

import asyncio
import zipfile
from typing import Any

from mcp import Tool

from config.settings import Settings
from mcp_servers.servers.document_intelligence import _docx, _docx_writer
from skills._paths import resolve_allowed_path, resolve_allowed_write_path
from skills.registry import Skill

_ZIP_MAGIC = b"PK\x03\x04"

_INSTRUCTIONS = """\
# Word (DOCX) skill

Read and generate real Word documents.

## Reading
- `read_docx` extracts paragraph text with heading/style info.
- `extract_docx_tables` pulls every table in the document as row data.

## Creating
- `create_docx` builds a real Word document from a title, markdown-ish
  body content, and optional tables. Supported markdown in `content`:
  `#`/`##`/`###` headings, `**bold**` spans, `-`/`*` bullet lists, and
  numbered lists (`1.`/`1)`) — these render as real Word formatting
  (headings, bold runs, bullet/numbered list styles), never as literal
  markdown characters. Pass `tables` (each `{title?, headers, rows}`) for
  any tabular data — real editable Word tables, not text-art. Use this
  whenever asked to save something as a Word doc, memo, or write-up in
  .docx form.
"""


class DocxGenerationError(RuntimeError):
    """Raised when a generated DOCX fails validation (not a valid ZIP/OOXML package)."""


def _dispatch_sync(settings: Settings, name: str, arguments: dict) -> Any:
    if name == "read_docx":
        path = resolve_allowed_path(settings, arguments["path"])
        return _docx.read_docx(path)

    if name == "extract_docx_tables":
        path = resolve_allowed_path(settings, arguments["path"])
        return _docx.extract_docx_tables(path)

    if name == "create_docx":
        path = resolve_allowed_write_path(settings, arguments["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        _docx_writer.create_docx(path, arguments["title"], arguments["content"], arguments.get("tables"))

        with path.open("rb") as f:
            header = f.read(len(_ZIP_MAGIC))
        if header != _ZIP_MAGIC or not zipfile.is_zipfile(path):
            raise DocxGenerationError(f"Generated file at {path} is not a valid ZIP/OOXML package; not a valid DOCX.")

        return {"path": str(path), "size_bytes": path.stat().st_size, "valid_docx": True}

    raise ValueError(f"Unknown docs skill tool: {name!r}")


_TOOLS = [
    Tool(
        name="read_docx",
        description="Extract paragraph text (with heading/style info) from a Word (.docx) document.",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the .docx file."},
            },
            "required": ["path"],
        },
    ),
    Tool(
        name="extract_docx_tables",
        description="Extract all tables (as row data) from a Word (.docx) document.",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the .docx file."},
            },
            "required": ["path"],
        },
    ),
    Tool(
        name="create_docx",
        description=(
            "Generate a real, valid Word (.docx) document from a title and content. Content may use "
            "simple markdown — '#'/'##'/'###' headings, '**bold**' spans, '-'/'*' bullet lists, and "
            "numbered lists ('1.'/'1)') — rendered as real Word formatting, not literal markdown "
            "characters. Optionally pass `tables` for real editable Word tables. Use this whenever "
            "asked to save a report, memo, or write-up as a Word document."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Where to save the document, e.g. '~/report.docx'."},
                "title": {"type": "string", "description": "Document title, shown as the top heading."},
                "content": {"type": "string", "description": "Body content, in simple markdown as described above."},
                "tables": {
                    "type": "array",
                    "description": "Optional tables to include, each {title?, headers: [str,...], rows: [[str,...],...]}.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "headers": {"type": "array", "items": {"type": "string"}},
                            "rows": {"type": "array", "items": {"type": "array", "items": {}}},
                        },
                    },
                },
            },
            "required": ["path", "title", "content"],
        },
    ),
]


def build_skill(settings: Settings) -> Skill:
    async def dispatch(name: str, arguments: dict) -> Any:
        return await asyncio.to_thread(_dispatch_sync, settings, name, arguments)

    return Skill(
        name="docs",
        description="Read and generate real Word (.docx) documents.",
        instructions=_INSTRUCTIONS,
        tools=list(_TOOLS),
        dispatch=dispatch,
    )
