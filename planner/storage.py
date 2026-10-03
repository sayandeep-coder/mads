from __future__ import annotations

from pathlib import Path

# Projects/tasks/prompts now live in Postgres (see planner/project_manager.py,
# task_manager.py, prompt_library.py) — MADS_HOME survives here only for the
# few things that are still genuinely local, per-machine state, like the
# active-project pointer file (planner/project_manager.py's
# _active_pointer_path). The old JsonRecordStore/JsonListStore generics that
# used to back project.json/tasks.json are gone along with the files.

MADS_HOME = Path.home() / ".mads"
