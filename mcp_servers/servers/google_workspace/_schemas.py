from __future__ import annotations

from mcp import Tool

GMAIL_TOOLS = [
    Tool(
        name="search_emails",
        description=(
            "Search the user's Gmail mailbox using Gmail search syntax "
            "(e.g. 'from:someone@example.com', 'is:unread', 'subject:invoice'). "
            "Returns a list of matching message summaries (id, subject, sender, date, snippet, url)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Gmail search query string."},
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return.",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="read_email",
        description="Read the full content (subject, sender, recipient, date, plain-text body, url) of one email by its message id.",
        inputSchema={
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "The Gmail message id, as returned by search_emails."},
            },
            "required": ["message_id"],
        },
    ),
    Tool(
        name="draft_email",
        description=(
            "Create a draft email in the user's Gmail account. This does NOT send the email — "
            "it only saves a draft for the user to review and send themselves."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address."},
                "subject": {"type": "string", "description": "Email subject line."},
                "body": {"type": "string", "description": "Plain-text email body."},
            },
            "required": ["to", "subject", "body"],
        },
    ),
    Tool(
        name="send_email",
        description=(
            "Immediately send an email from the user's Gmail account. This is irreversible. "
            "Only call this when the user has explicitly asked to send an email, not merely draft one."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address."},
                "subject": {"type": "string", "description": "Email subject line."},
                "body": {"type": "string", "description": "Plain-text email body."},
            },
            "required": ["to", "subject", "body"],
        },
    ),
]

CALENDAR_TOOLS = [
    Tool(
        name="list_events",
        description="List upcoming calendar events, optionally within a time range. Returns summary, start/end, location, and url for each.",
        inputSchema={
            "type": "object",
            "properties": {
                "time_min": {"type": "string", "description": "RFC3339 timestamp; events starting after this. Omit for 'from now'."},
                "time_max": {"type": "string", "description": "RFC3339 timestamp; events starting before this."},
                "max_results": {"type": "integer", "description": "Maximum number of events to return.", "default": 10},
            },
            "required": [],
        },
    ),
    Tool(
        name="create_event",
        description="Create a new calendar event and return its id and url.",
        inputSchema={
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Event title."},
                "start": {"type": "string", "description": "RFC3339 start timestamp, e.g. 2026-07-15T14:00:00+05:30."},
                "end": {"type": "string", "description": "RFC3339 end timestamp."},
                "description": {"type": "string", "description": "Event description."},
                "location": {"type": "string", "description": "Event location."},
            },
            "required": ["summary", "start", "end"],
        },
    ),
    Tool(
        name="update_event",
        description="Update fields on an existing calendar event. Only the fields provided are changed.",
        inputSchema={
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event id, as returned by list_events or create_event."},
                "summary": {"type": "string", "description": "New event title."},
                "start": {"type": "string", "description": "New RFC3339 start timestamp."},
                "end": {"type": "string", "description": "New RFC3339 end timestamp."},
                "description": {"type": "string", "description": "New event description."},
                "location": {"type": "string", "description": "New event location."},
            },
            "required": ["event_id"],
        },
    ),
    Tool(
        name="delete_event",
        description="Permanently delete a calendar event. This is irreversible.",
        inputSchema={
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event id to delete."},
            },
            "required": ["event_id"],
        },
    ),
]

DRIVE_TOOLS = [
    Tool(
        name="search_drive",
        description="Search Google Drive using Drive query syntax (e.g. \"name contains 'report'\"). Returns file id, name, type, and url.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Drive search query string."},
                "max_results": {"type": "integer", "description": "Maximum number of results.", "default": 10},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="list_files",
        description="List the user's most recently modified Drive files.",
        inputSchema={
            "type": "object",
            "properties": {
                "max_results": {"type": "integer", "description": "Maximum number of files to return.", "default": 10},
            },
            "required": [],
        },
    ),
    Tool(
        name="read_file_content",
        description="Read the text content of a Drive file by id.",
        inputSchema={
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "The Drive file id."},
            },
            "required": ["file_id"],
        },
    ),
    Tool(
        name="create_file",
        description="Create a new file in Drive with the given text content and return its id and url.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "File name."},
                "content": {"type": "string", "description": "Text content of the file."},
                "mime_type": {"type": "string", "description": "MIME type of the file.", "default": "text/plain"},
            },
            "required": ["name"],
        },
    ),
    Tool(
        name="copy_file",
        description="Create a copy of an existing Drive file.",
        inputSchema={
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "The Drive file id to copy."},
                "new_name": {"type": "string", "description": "Name for the copy. Defaults to 'Copy of <original>' if omitted."},
            },
            "required": ["file_id"],
        },
    ),
]

DOCS_TOOLS = [
    Tool(
        name="read_document",
        description="Read a Google Doc's title and full plain-text content by document id.",
        inputSchema={
            "type": "object",
            "properties": {
                "document_id": {"type": "string", "description": "The Google Doc's document id."},
            },
            "required": ["document_id"],
        },
    ),
    Tool(
        name="create_document",
        description="Create a new Google Doc with the given title and optional initial text content. Returns its id and url.",
        inputSchema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Document title."},
                "content": {"type": "string", "description": "Initial plain-text content."},
            },
            "required": ["title"],
        },
    ),
    Tool(
        name="update_document",
        description="Insert text into an existing Google Doc. Appends to the end by default.",
        inputSchema={
            "type": "object",
            "properties": {
                "document_id": {"type": "string", "description": "The Google Doc's document id."},
                "content": {"type": "string", "description": "Text to insert."},
                "append": {"type": "boolean", "description": "Append to the end (true) or insert at the start (false).", "default": True},
            },
            "required": ["document_id", "content"],
        },
    ),
]

SHEETS_TOOLS = [
    Tool(
        name="read_sheet",
        description="Read cell values from a spreadsheet range (A1 notation, e.g. 'Sheet1!A1:D20').",
        inputSchema={
            "type": "object",
            "properties": {
                "spreadsheet_id": {"type": "string", "description": "The spreadsheet id."},
                "range_": {"type": "string", "description": "A1 notation range, e.g. 'Sheet1!A1:D20'."},
            },
            "required": ["spreadsheet_id", "range_"],
        },
    ),
    Tool(
        name="append_sheet",
        description="Append one or more rows after the last row of data in the given range.",
        inputSchema={
            "type": "object",
            "properties": {
                "spreadsheet_id": {"type": "string", "description": "The spreadsheet id."},
                "range_": {"type": "string", "description": "A1 notation range to append after, e.g. 'Sheet1!A1'."},
                "values": {
                    "type": "array",
                    "description": "Rows to append; each row is an array of cell values.",
                    "items": {"type": "array", "items": {"type": "string"}},
                },
            },
            "required": ["spreadsheet_id", "range_", "values"],
        },
    ),
    Tool(
        name="update_sheet",
        description="Overwrite cell values in the given range (A1 notation).",
        inputSchema={
            "type": "object",
            "properties": {
                "spreadsheet_id": {"type": "string", "description": "The spreadsheet id."},
                "range_": {"type": "string", "description": "A1 notation range to overwrite, e.g. 'Sheet1!A1:B2'."},
                "values": {
                    "type": "array",
                    "description": "Rows to write; each row is an array of cell values.",
                    "items": {"type": "array", "items": {"type": "string"}},
                },
            },
            "required": ["spreadsheet_id", "range_", "values"],
        },
    ),
    Tool(
        name="create_sheet",
        description="Create a new Google Sheet with the given title. Returns its id and url.",
        inputSchema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Spreadsheet title."},
            },
            "required": ["title"],
        },
    ),
]

_QUESTION_SCHEMA = {
    "type": "object",
    "description": "One form question or structural element.",
    "properties": {
        "kind": {
            "type": "string",
            "enum": [
                "short_text",
                "paragraph_text",
                "multiple_choice",
                "checkboxes",
                "dropdown",
                "linear_scale",
                "date",
                "time",
                "file_upload",
                "grid",
                "section_break",
            ],
            "description": (
                "The question type. short_text/paragraph_text: free text (one line vs multi-line). "
                "multiple_choice: pick one (radio buttons). checkboxes: pick any number. "
                "dropdown: pick one from a dropdown menu. linear_scale: numeric scale (e.g. 1-5 rating). "
                "date/time: date or time picker. file_upload: respondent uploads a file. "
                "grid: a matrix of rows x columns (e.g. rate several items on the same scale). "
                "section_break: a page break / section title, not a question — use to split a long "
                "form into pages."
            ),
        },
        "title": {
            "type": "string",
            "description": (
                "The question text (or section title for section_break). For short_text fields that "
                "need a specific format (email, phone number, URL), say so directly in the title or "
                "description, e.g. 'Email address' with description 'Must be a valid email address' — "
                "Google Forms' API does not expose settable format validation (email/phone/URL/regex), "
                "so this is the only way to signal the expectation to respondents; a human can add real "
                "validation afterward in the Forms editor UI (Google Forms > question > ⋮ > Response "
                "validation) in a few seconds per field."
            ),
        },
        "description": {"type": "string", "description": "Optional helper text shown below the title."},
        "required": {"type": "boolean", "description": "Whether an answer is mandatory. Default false.", "default": False},
        "section_id": {
            "type": "string",
            "description": (
                "For section_break only: a short label you choose (e.g. 'flutter', 'backend') so "
                "other questions' options_goto can target this section by name. Only needed on "
                "sections that are branching destinations."
            ),
        },
        "options": {
            "type": "array",
            "items": {"type": "string"},
            "description": "For multiple_choice/checkboxes/dropdown: the list of choices.",
        },
        "options_goto": {
            "type": "array",
            "description": (
                "For multiple_choice/dropdown ONLY (Google Forms does not support branching on "
                "checkboxes, since multiple can be selected at once — there's no single answer to "
                "branch on). Each entry routes one option to a destination when the respondent picks "
                "it. Options not listed here fall through to the next section as normal."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "option": {"type": "string", "description": "The option's exact text, from `options`."},
                    "goto": {
                        "type": "string",
                        "description": (
                            "Where this option sends the respondent: a section_id defined on some "
                            "section_break's `section_id` field, or one of '@next' (continue to the "
                            "very next section — the default behavior, only specify to be explicit), "
                            "'@submit' (submit the form immediately), or '@restart' (return to the "
                            "start of the form)."
                        ),
                    },
                },
                "required": ["option", "goto"],
            },
        },
        "shuffle": {"type": "boolean", "description": "For multiple_choice/checkboxes/dropdown: randomize option order per respondent."},
        "scale_low": {"type": "integer", "description": "For linear_scale: lowest value (usually 0 or 1)."},
        "scale_high": {"type": "integer", "description": "For linear_scale: highest value (up to 10)."},
        "scale_low_label": {"type": "string", "description": "For linear_scale: label for the low end, e.g. 'Not likely'."},
        "scale_high_label": {"type": "string", "description": "For linear_scale: label for the high end, e.g. 'Very likely'."},
        "include_time": {"type": "boolean", "description": "For date: also ask for a time, not just a date."},
        "is_duration": {"type": "boolean", "description": "For time: ask for a duration instead of a time of day."},
        "max_files": {"type": "integer", "description": "For file_upload: max number of files the respondent may attach."},
        "max_file_size_bytes": {"type": "integer", "description": "For file_upload: max size per file in bytes."},
        "grid_rows": {
            "type": "array",
            "items": {"type": "string"},
            "description": "For grid: the row labels (e.g. the items being rated).",
        },
        "grid_columns": {
            "type": "array",
            "items": {"type": "string"},
            "description": "For grid: the column labels (e.g. the rating scale).",
        },
        "grid_multiple_selection": {
            "type": "boolean",
            "description": "For grid: allow multiple column selections per row (checkbox grid) instead of one (radio grid).",
        },
    },
    "required": ["kind", "title"],
}

FORMS_TOOLS = [
    Tool(
        name="create_form",
        description=(
            "Create a new Google Form with a title and a full list of questions, in one call. "
            "Supports every common question type: short/long text, multiple choice, checkboxes, "
            "dropdown, linear scale (rating), date, time, file upload, grids (matrix questions), "
            "and section breaks for multi-page forms. Build the entire question list up front rather "
            "than creating an empty form and adding questions one at a time.\n\n"
            "Conditional branching (e.g. 'if the applicant picks Flutter, only show Flutter "
            "questions') is supported via a multiple_choice or dropdown question's `options_goto` "
            "field routing to a section_break's `section_id` — see those fields' descriptions for the "
            "exact shape. Branching only works on multiple_choice/dropdown (a Google Forms API "
            "constraint), never checkboxes.\n\n"
            "Field-format validation (must be a valid email/phone/URL) is NOT settable through this "
            "API at all — that's a real Google Forms API limitation, not a gap in this tool. Say the "
            "expected format in the question title/description instead, and mention to the user that "
            "real validation can be added afterward in the Forms editor UI in a few seconds per field."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Form title."},
                "description": {"type": "string", "description": "Form description, shown at the top."},
                "questions": {
                    "type": "array",
                    "items": _QUESTION_SCHEMA,
                    "description": "The form's questions and section breaks, in display order.",
                },
            },
            "required": ["title"],
        },
    ),
    Tool(
        name="get_form_responses",
        description="Read submitted responses to a form as structured question-to-answer data, most recent first.",
        inputSchema={
            "type": "object",
            "properties": {
                "form_id": {"type": "string", "description": "The form id, as returned by create_form."},
                "max_results": {"type": "integer", "description": "Maximum number of responses to return.", "default": 50},
            },
            "required": ["form_id"],
        },
    ),
]

ALL_TOOLS = GMAIL_TOOLS + CALENDAR_TOOLS + DRIVE_TOOLS + DOCS_TOOLS + SHEETS_TOOLS + FORMS_TOOLS
