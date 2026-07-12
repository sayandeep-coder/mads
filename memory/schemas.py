from __future__ import annotations

from mcp import Tool

_CATEGORY_ENUM = ["preference", "project", "decision", "person"]
_CATEGORY_DESC = (
    "The kind of memory: 'preference' (things Sayan likes/dislikes/prefers), "
    "'project' (what he's working on and its state), 'decision' (a choice made and why), "
    "or 'person' (facts about someone he works with or knows)."
)

MEMORY_TOOLS = [
    Tool(
        name="remember",
        description=(
            "Store a new memory about Sayan — a preference, an active project, a decision made, "
            "or a fact about a person. Call this whenever he shares something worth remembering "
            "long-term (not for one-off details irrelevant beyond this conversation)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": _CATEGORY_ENUM, "description": _CATEGORY_DESC},
                "content": {"type": "string", "description": "The memory itself, written as a clear standalone statement."},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional short keywords to help future search find this memory.",
                },
            },
            "required": ["category", "content"],
        },
    ),
    Tool(
        name="forget",
        description="Permanently delete a stored memory by its id.",
        inputSchema={
            "type": "object",
            "properties": {
                "memory_id": {"type": "integer", "description": "The id of the memory to delete, from search_memory or list_memories."},
            },
            "required": ["memory_id"],
        },
    ),
    Tool(
        name="update_memory",
        description="Update the content and/or tags of an existing memory (e.g. a project's status changed).",
        inputSchema={
            "type": "object",
            "properties": {
                "memory_id": {"type": "integer", "description": "The id of the memory to update."},
                "content": {"type": "string", "description": "New content, replacing the old. Omit to leave unchanged."},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "New tags, replacing the old set. Omit to leave unchanged.",
                },
            },
            "required": ["memory_id"],
        },
    ),
    Tool(
        name="search_memory",
        description=(
            "Search stored memories about Sayan by relevance to a query. Use this before assuming "
            "you don't know something about his preferences, projects, decisions, or people he knows."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for."},
                "category": {"type": "string", "enum": _CATEGORY_ENUM, "description": "Optionally restrict the search to one category."},
                "limit": {"type": "integer", "description": "Maximum number of results.", "default": 10},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="list_memories",
        description="List all stored memories, optionally filtered by category, most recently updated first.",
        inputSchema={
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": _CATEGORY_ENUM, "description": "Optionally restrict to one category."},
            },
            "required": [],
        },
    ),
]
