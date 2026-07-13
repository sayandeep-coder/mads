from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from planner.documents import list_recent_documents
from planner.models import Project, ProjectContext, SessionContext
from planner.prompt_library import PromptLibrary
from planner.task_manager import TaskManager


class SessionContextBuilder:
    """Builds and refreshes SessionContext — the one place that turns raw
    Project/Task/Prompt state into the enriched, read-time ProjectContext
    every planner submodule (and, via the system prompt, the agent) consumes.
    """

    def __init__(self, task_manager: TaskManager, prompt_library: PromptLibrary) -> None:
        self._tasks = task_manager
        self._prompts = prompt_library

    def build_project_context(self, project: Project) -> ProjectContext:
        open_count, blocked_count, done_count = self._tasks.project_progress(project.slug)
        prompts = self._prompts.list_all(project_slug=project.slug)

        folder = project.folder_path
        recent_documents = list_recent_documents(folder) if folder else []

        return ProjectContext(
            project=project,
            open_task_count=open_count,
            blocked_task_count=blocked_count,
            completed_task_count=done_count,
            recent_documents=recent_documents,
            available_prompts=[p.title for p in prompts],
            recent_memories=[],
        )

    def build_session(self, cwd: Path, active_project: Project | None) -> SessionContext:
        project_context = self.build_project_context(active_project) if active_project else None
        return SessionContext(
            active_project=project_context,
            cwd=cwd,
            started_at=datetime.now(timezone.utc),
        )
