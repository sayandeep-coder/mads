from __future__ import annotations

from mcp import Tool

SYSTEM_TOOLS = [
    Tool(
        name="open_app",
        description="Launch a macOS application by name (e.g. 'Safari', 'Notes'), or bring it to the front if already running.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The application's name, as it appears in the Applications folder or Dock."},
            },
            "required": ["name"],
        },
    ),
    Tool(
        name="quit_app",
        description="Quit a running macOS application by name.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The application's name."},
            },
            "required": ["name"],
        },
    ),
    Tool(
        name="list_running_apps",
        description="List the names of currently running (foreground) macOS applications.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="battery_status",
        description="Report battery charge percentage, whether it's plugged in, and estimated time remaining.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="cpu_usage",
        description="Report current CPU utilization percentage and core count.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="memory_usage",
        description="Report current memory (RAM) usage: total, used, available, and percent.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="disk_usage",
        description="Report disk usage (total/used/free/percent) for a mount point. Defaults to the main system volume.",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Mount point to check.", "default": "/"},
            },
            "required": [],
        },
    ),
    Tool(
        name="uptime",
        description="Report how long the machine has been running since it was last started.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="shutdown",
        description=(
            "Shut down the computer. DESTRUCTIVE — first call without confirmed=true; this returns "
            "requires_confirmation=true instead of acting. Ask the user to confirm, then call again "
            "with confirmed=true to actually shut down."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "confirmed": {"type": "boolean", "description": "Set true only after the user has explicitly confirmed.", "default": False},
            },
            "required": [],
        },
    ),
    Tool(
        name="restart",
        description=(
            "Restart the computer. DESTRUCTIVE — first call without confirmed=true; this returns "
            "requires_confirmation=true instead of acting. Ask the user to confirm, then call again "
            "with confirmed=true to actually restart."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "confirmed": {"type": "boolean", "description": "Set true only after the user has explicitly confirmed.", "default": False},
            },
            "required": [],
        },
    ),
    Tool(
        name="empty_trash",
        description=(
            "Permanently empty the Trash. DESTRUCTIVE and irreversible — first call without "
            "confirmed=true; this returns requires_confirmation=true instead of acting. Ask the user "
            "to confirm, then call again with confirmed=true to actually empty it."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "confirmed": {"type": "boolean", "description": "Set true only after the user has explicitly confirmed.", "default": False},
            },
            "required": [],
        },
    ),
    Tool(
        name="delete_files",
        description=(
            "Permanently delete one or more files or folders (not moved to Trash — unrecoverable). "
            "DESTRUCTIVE — first call without confirmed=true; this returns requires_confirmation=true "
            "instead of acting. Ask the user to confirm, then call again with confirmed=true to actually delete."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"}, "description": "Paths to delete."},
                "confirmed": {"type": "boolean", "description": "Set true only after the user has explicitly confirmed.", "default": False},
            },
            "required": ["paths"],
        },
    ),
    Tool(
        name="terminate_process",
        description=(
            "Forcibly terminate a running process by name or PID. DESTRUCTIVE — first call without "
            "confirmed=true; this returns requires_confirmation=true instead of acting. Ask the user "
            "to confirm, then call again with confirmed=true to actually terminate it."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name_or_pid": {"type": "string", "description": "Process name (matches substrings) or exact PID."},
                "confirmed": {"type": "boolean", "description": "Set true only after the user has explicitly confirmed.", "default": False},
            },
            "required": ["name_or_pid"],
        },
    ),
]
