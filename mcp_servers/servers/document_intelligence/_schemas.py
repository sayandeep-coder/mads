from __future__ import annotations

from mcp import Tool

DOCUMENT_TOOLS = [
    Tool(
        name="read_pdf",
        description=(
            "Extract text from a PDF file. Returns the extracted text plus page count. "
            "For large PDFs, specify start_page/end_page (1-indexed, inclusive) to read a "
            "specific range instead of the whole document."
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
        name="extract_tables",
        description="Extract all tables (as row data) from a PDF or DOCX file.",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to a .pdf or .docx file."},
                "start_page": {"type": "integer", "description": "For PDFs: first page to search (1-indexed)."},
                "end_page": {"type": "integer", "description": "For PDFs: last page to search (1-indexed, inclusive)."},
            },
            "required": ["path"],
        },
    ),
    Tool(
        name="create_pdf",
        description=(
            "Generate a real, valid PDF file from a title and content. Content may use simple "
            "markdown — '#'/'##'/'###' headings, '**bold**' spans, and '-'/'*' bullet lists — "
            "which is rendered as real PDF formatting, not literal markdown characters. Use this "
            "whenever asked to save a report, summary, or document as a PDF."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Where to save the PDF, e.g. '~/report.pdf'."},
                "title": {"type": "string", "description": "Document title, shown at the top of the PDF."},
                "content": {"type": "string", "description": "Body content, in simple markdown as described above."},
            },
            "required": ["path", "title", "content"],
        },
    ),
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
