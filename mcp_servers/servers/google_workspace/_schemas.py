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

ALL_TOOLS = GMAIL_TOOLS + CALENDAR_TOOLS + DRIVE_TOOLS + DOCS_TOOLS + SHEETS_TOOLS
