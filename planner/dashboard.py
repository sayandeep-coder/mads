from __future__ import annotations

import subprocess
from pathlib import Path

from planner.documents import list_recent_documents
from planner.models import DashboardView, Project
from planner.planning_engine import PlanningEngine
from planner.project_manager import ProjectManager
from planner.task_manager import TaskManager

_MAX_RECENT_COMMITS = 5


class Dashboard:
    """Read-only aggregate view of a project: identity, tasks, progress,
    repo state, recent documents. Nothing here is stored — every call
    recomputes from ProjectManager/TaskManager plus a live (cheap, local)
    git read, so the view can never drift from the underlying state.
    """

    def __init__(
        self,
        project_manager: ProjectManager,
        task_manager: TaskManager,
        planning_engine: PlanningEngine,
    ) -> None:
        self._projects = project_manager
        self._tasks = task_manager
        self._planner = planning_engine

    def build(self, project: Project) -> DashboardView:
        open_count, blocked_count, done_count = self._tasks.project_progress(project.slug)
        total = open_count + blocked_count + done_count
        progress_pct = round((done_count / total) * 100, 1) if total else 0.0

        folder = project.folder_path
        branch = self._projects.detect_current_branch(folder) if folder else None
        recent_commits = self._recent_commits(folder) if folder else []
        recent_documents = list_recent_documents(folder) if folder else []

        recommended = self._planner.suggest_next_task(project.slug)

        return DashboardView(
            project=project,
            branch=branch,
            open_tasks=open_count,
            completed_tasks=done_count,
            progress_pct=progress_pct,
            recent_commits=recent_commits,
            recent_documents=recent_documents,
            last_session_at=project.last_active_at,
            recommended_next_task=recommended,
        )

    @staticmethod
    def _recent_commits(folder: Path) -> list[str]:
        try:
            result = subprocess.run(
                ["git", "-C", str(folder), "log", f"-{_MAX_RECENT_COMMITS}", "--oneline"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        if result.returncode != 0:
            return []
        return [line for line in result.stdout.splitlines() if line.strip()]
