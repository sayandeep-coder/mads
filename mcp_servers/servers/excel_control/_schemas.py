from __future__ import annotations

from mcp import Tool

EXCEL_CONTROL_TOOLS = [
    Tool(
        name="list_sheets",
        description=(
            "List every worksheet in the currently open Excel workbook, and which one is active. "
            "Call this first when you don't already know the sheet name a range like 'Sheet1!A1:D20' "
            "needs — sheet names in a real workbook are rarely 'Sheet1'."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="read_range",
        description=(
            "Read cell values from a range in the open workbook, e.g. 'Sheet1!A1:D20'. Use this to "
            "see real current values before deciding what to change — never guess a cell's contents. "
            "Always use a bounded A1 range with both a start and end cell (e.g. 'A1:F50', "
            "'A2:F2' for one row) — whole-row/column shorthand like '2:2' or 'A:A' is NOT valid "
            "here. If you don't know how much data a sheet has, call this with a generous bounded "
            "guess (e.g. 'A1:Z200') first; an empty result includes a `note` telling you the "
            "sheet's actual used range so you can re-read the right area on the next call."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "range_": {
                    "type": "string",
                    "description": "Bounded A1 notation range, optionally sheet-qualified, e.g. 'Sheet1!A1:D20' or 'B2'. Never a whole-row/column shorthand like '2:2'.",
                },
            },
            "required": ["range_"],
        },
    ),
    Tool(
        name="write_range",
        description=(
            "Overwrite cell values in a range of the open workbook, e.g. 'Sheet1!B2' or "
            "'Sheet1!A1:B2'. `values` must be a 2D array matching the range's shape — one row "
            "of cells per inner array. This is a real, immediate edit to the user's open workbook."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "range_": {"type": "string", "description": "A1 notation range to overwrite."},
                "values": {
                    "type": "array",
                    "description": "Rows to write; each row is an array of cell values (numbers or strings).",
                    "items": {"type": "array", "items": {}},
                },
            },
            "required": ["range_", "values"],
        },
    ),
    Tool(
        name="get_selection",
        description="Get the range address, values, and sheet name of whatever the user currently has selected in Excel.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="add_sheet",
        description="Add a new worksheet to the open workbook with the given name, and make it active.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name for the new sheet."},
            },
            "required": ["name"],
        },
    ),
]
