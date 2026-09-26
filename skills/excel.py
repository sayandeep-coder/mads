from __future__ import annotations

import asyncio
import zipfile
from typing import Any

from mcp import Tool

from config.settings import Settings
from mcp_servers.servers.document_intelligence import _excel_writer, _xlsx
from skills._paths import resolve_allowed_path, resolve_allowed_write_path
from skills.registry import Skill

_ZIP_MAGIC = b"PK\x03\x04"

_INSTRUCTIONS = """\
# Excel (XLSX) skill

Read and generate real Excel spreadsheets.

## Reading
- `read_xlsx` reads rows from a sheet (defaults to the first sheet). For
  large sheets, always use start_row/end_row rather than reading
  thousands of rows in one call. (To pull tables out of a PDF or Word
  document instead, use the pdf or docs skill's own table-extraction tool.)

## Creating
`create_excel` builds a real .xlsx workbook from one or more sheet specs.
Every sheet gets a bold header row (frozen so it stays visible while
scrolling) and auto-sized columns automatically — don't try to style
cells yourself, just provide clean column names and row data. Use this
whenever asked to save data as an Excel file, export a table, or build a
spreadsheet. For multiple related tables, use multiple sheets in one
`create_excel` call rather than several separate files.

This is a real, professional spreadsheet tool, not a bare CSV dump —
always reach for these when they fit the data, not just when explicitly
asked:
- `table`: `{name?, style?}` — turns the data into a real Excel Table
  (filterable, sortable, banded rows), not just styled cells. Use this by
  default for any tabular dataset; it's what makes a sheet feel like a
  real deliverable instead of a plain grid.
- `number_formats`: `{column_name_or_index: format}` where format is one
  of `currency` (₹), `currency_usd` ($), `percent`, `integer`, `decimal`,
  `date`, or a raw Excel number-format code. ALWAYS format money as
  currency and rates/ratios as percent — never leave `0.15` sitting there
  when it means 15%, and never leave a bare number when it's a rupee/
  dollar amount.
- `conditional_formats`: list of `{column, type: 'color_scale'}` (a real
  heatmap gradient — great for scores, growth rates, any "which values
  are high/low" data) or `{column, type: 'highlight', operator, value,
  fill?, font?}` (flag specific values, e.g. highlight every row where
  Status == 'REGRET' or a grade is below a threshold).
- `charts`: list of `{type: 'bar'|'column'|'line'|'pie'|'scatter'|'area',
  title?, categories, series: [column,...], anchor?}` — real, live Excel
  charts referencing the sheet's own cells (not a static image), so they
  stay correct if the data is edited later. `categories` and each entry in
  `series` are column names from the same sheet. NEVER tell Sayan "graphs
  can't be added directly" or that he needs to build the chart himself in
  Excel/Sheets — this tool builds real native charts; use it.

When asked for something "professional," combine several of these in one
call: a real Table for the data, currency/percent number formats on the
right columns, a color-scale or highlight rule on whatever the data's
actual signal is (top performers, problem rows, growth), and at least one
real chart visualizing the headline metric. A sheet with none of this is
a rough draft, not a finished deliverable.
"""


class ExcelGenerationError(RuntimeError):
    """Raised when a generated XLSX fails validation (not a valid ZIP/OOXML package)."""


def _dispatch_sync(settings: Settings, name: str, arguments: dict) -> Any:
    if name == "read_xlsx":
        path = resolve_allowed_path(settings, arguments["path"])
        return _xlsx.read_xlsx(
            path, arguments.get("sheet_name"), arguments.get("start_row"), arguments.get("end_row")
        )

    if name == "create_excel":
        path = resolve_allowed_write_path(settings, arguments["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        _excel_writer.create_excel(path, arguments["sheets"])

        with path.open("rb") as f:
            header = f.read(len(_ZIP_MAGIC))
        if header != _ZIP_MAGIC or not zipfile.is_zipfile(path):
            raise ExcelGenerationError(f"Generated file at {path} is not a valid ZIP/OOXML package; not a valid XLSX.")

        return {
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "sheet_count": len(arguments["sheets"]),
            "valid_xlsx": True,
        }

    raise ValueError(f"Unknown excel skill tool: {name!r}")


_TOOLS = [
    Tool(
        name="read_xlsx",
        description=(
            "Read rows from an Excel (.xlsx) spreadsheet. Defaults to the first sheet. "
            "For large sheets, specify start_row/end_row (1-indexed, inclusive) to read a "
            "specific range instead of the whole sheet."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the .xlsx file."},
                "sheet_name": {"type": "string", "description": "Sheet to read. Defaults to the first sheet."},
                "start_row": {"type": "integer", "description": "First row to read (1-indexed)."},
                "end_row": {"type": "integer", "description": "Last row to read (1-indexed, inclusive)."},
            },
            "required": ["path"],
        },
    ),
    Tool(
        name="create_excel",
        description=(
            "Generate a real, valid, professional Excel (.xlsx) workbook from one or more sheets — "
            "with real Excel Tables, number formats, conditional formatting, and native charts "
            "(referencing live cells, not static images), not just plain unstyled cells. Use this "
            "whenever asked to save data as an Excel file, export a table, or build a spreadsheet. "
            "Each sheet gets a bold, frozen header row and auto-sized columns automatically."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Where to save the workbook, e.g. '~/export.xlsx'."},
                "sheets": {
                    "type": "array",
                    "description": "Ordered list of sheet specs.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Sheet name (max 31 chars)."},
                            "columns": {"type": "array", "items": {"type": "string"}},
                            "rows": {"type": "array", "items": {"type": "array", "items": {}}},
                            "table": {
                                "type": "object",
                                "description": "Turn this sheet's data into a real, filterable/sortable Excel Table.",
                                "properties": {
                                    "name": {"type": "string"},
                                    "style": {"type": "string", "description": "e.g. 'TableStyleMedium9' (default)."},
                                },
                            },
                            "number_formats": {
                                "type": "object",
                                "description": "Map of column name -> 'currency'|'currency_usd'|'percent'|'integer'|'decimal'|'date' or a raw Excel format code.",
                            },
                            "conditional_formats": {
                                "type": "array",
                                "description": "List of {column, type: 'color_scale'|'highlight', ...}.",
                                "items": {"type": "object"},
                            },
                            "charts": {
                                "type": "array",
                                "description": "List of real native charts: {type: 'bar'|'column'|'line'|'pie'|'scatter'|'area', title?, categories, series: [column,...], anchor?}.",
                                "items": {"type": "object"},
                            },
                        },
                        "required": ["name", "columns", "rows"],
                    },
                },
            },
            "required": ["path", "sheets"],
        },
    ),
]


def build_skill(settings: Settings) -> Skill:
    async def dispatch(name: str, arguments: dict) -> Any:
        return await asyncio.to_thread(_dispatch_sync, settings, name, arguments)

    return Skill(
        name="excel",
        description="Read and generate real Excel (.xlsx) spreadsheets.",
        instructions=_INSTRUCTIONS,
        tools=list(_TOOLS),
        dispatch=dispatch,
    )
