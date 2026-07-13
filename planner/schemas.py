from __future__ import annotations

from mcp import Tool

PLANNER_TOOLS = [
    Tool(
        name="register_workspace",
        description=(
            "Register a local folder as a tracked project. The GitHub repo (if any) is detected "
            "automatically from the folder's git remote — never ask Sayan for a repo name, just "
            "point this at the folder. Call this when Sayan wants Mads to start tracking a project "
            "that isn't registered yet. If he doesn't give a folder, use the current workspace."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "folder": {"type": "string", "description": "Absolute path to the project's local folder."},
                "name": {"type": "string", "description": "Human-readable project name; defaults to the folder name if omitted."},
                "drive_folder": {"type": "string", "description": "Google Drive folder name or id, if Sayan mentions one."},
            },
            "required": ["folder"],
        },
    ),
    Tool(
        name="use_project",
        description=(
            "Switch the active project by name. Once active, filesystem tools, task tools, prompt "
            "tools, and conversation context all scope to this project until switched again."
        ),
        inputSchema={
            "type": "object",
            "properties": {"name": {"type": "string", "description": "The project name to activate."}},
            "required": ["name"],
        },
    ),
    Tool(
        name="list_projects",
        description="List all known projects.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_active_project",
        description="Get the currently active project and its details, or none if no project is active.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="add_task",
        description="Add a task to the active project's task list.",
        inputSchema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short task title."},
                "description": {"type": "string", "description": "Optional longer description."},
                "priority": {"type": "string", "enum": ["low", "medium", "high"], "description": "Defaults to medium."},
                "due_date": {"type": "string", "description": "Optional due date, ISO format YYYY-MM-DD."},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title"],
        },
    ),
    Tool(
        name="list_tasks",
        description="List tasks for the active project, optionally filtered by status.",
        inputSchema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["open", "in_progress", "blocked", "done"],
                    "description": "Filter by status; omit for all.",
                },
            },
        },
    ),
    Tool(
        name="update_task",
        description="Update a task's title, description, priority, status, due date, or tags.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                "status": {"type": "string", "enum": ["open", "in_progress", "blocked", "done"]},
                "due_date": {"type": "string", "description": "ISO format YYYY-MM-DD."},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["task_id"],
        },
    ),
    Tool(
        name="complete_task",
        description="Mark a task as done by its id, in the active project.",
        inputSchema={
            "type": "object",
            "properties": {"task_id": {"type": "integer", "description": "The id of the task to complete, from list_tasks."}},
            "required": ["task_id"],
        },
    ),
    Tool(
        name="delete_task",
        description="Permanently delete a task by its id, in the active project.",
        inputSchema={
            "type": "object",
            "properties": {"task_id": {"type": "integer"}},
            "required": ["task_id"],
        },
    ),
    Tool(
        name="create_prompt",
        description=(
            "Save a reusable prompt to the prompt library — global (available across all projects) "
            "or scoped to the active project. Use this when Sayan wants to save a prompt template "
            "he'll reuse, like a report format or review checklist."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string", "description": "The prompt content/template."},
                "scope": {"type": "string", "enum": ["global", "project"], "description": "Defaults to global."},
                "description": {"type": "string"},
                "category": {"type": "string", "description": "e.g. 'reports', 'reviews', 'planning'."},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "body"],
        },
    ),
    Tool(
        name="list_prompts",
        description="List available prompts — global prompts plus the active project's prompts.",
        inputSchema={
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "favorites_only": {"type": "boolean"},
            },
        },
    ),
    Tool(
        name="use_prompt",
        description="Retrieve a saved prompt's full text by its slug, ready to use.",
        inputSchema={
            "type": "object",
            "properties": {
                "slug": {"type": "string"},
                "scope": {"type": "string", "enum": ["global", "project"], "description": "Defaults to global."},
            },
            "required": ["slug"],
        },
    ),
    Tool(
        name="daily_plan",
        description=(
            "Get today's plan for the active project: priority tasks, a suggested next task, and a "
            "suggested prompt. Call this when Sayan asks what he should work on, what's pending, or "
            "wants a morning briefing."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="project_dashboard",
        description=(
            "Get a full status snapshot of a project: repo, branch, task counts, progress, recent "
            "commits, recent documents, and a recommended next task. Defaults to the active project."
        ),
        inputSchema={
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Project name; defaults to the active project."}},
        },
    ),
]
