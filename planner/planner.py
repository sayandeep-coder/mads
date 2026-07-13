from __future__ import annotations

from pathlib import Path

from planner.dashboard import Dashboard
from planner.models import DailyPlan, DashboardView, Project, SessionContext
from planner.planning_engine import PlanningEngine
from planner.project_manager import ProjectManager
from planner.prompt_library import PromptLibrary
from planner.session_context import SessionContextBuilder
from planner.task_manager import TaskManager


class Planner:
    """The operational brain of Mads: orchestrates project awareness, tasks,
    prompts, planning, and the dashboard, and owns SessionContext.

    This is not a ToolProvider — Gemini never calls into Planner directly
    through the MCP tool-call loop. It's constructed once per session by
    cli/main.py, sits between session assembly and the Agent, and is the
    single source of truth for "what's the active project and what does it
    look like right now." A thin ToolProvider (planner.provider) re-exposes
    a query/mutation surface so Gemini can still ask for a plan or register
    a workspace mid-conversation, but the object itself is plain Python,
    constructible and testable with zero MCP/Gemini involvement.
    """

    def __init__(
        self,
        project_manager: ProjectManager | None = None,
        task_manager: TaskManager | None = None,
        prompt_library: PromptLibrary | None = None,
        planning_engine: PlanningEngine | None = None,
        dashboard: Dashboard | None = None,
        session_context_builder: SessionContextBuilder | None = None,
    ) -> None:
        self.projects = project_manager or ProjectManager()
        self.tasks = task_manager or TaskManager()
        self.prompts = prompt_library or PromptLibrary()
        self.planning = planning_engine or PlanningEngine(self.tasks, self.prompts)
        self.dashboard = dashboard or Dashboard(self.projects, self.tasks, self.planning)
        self._context_builder = session_context_builder or SessionContextBuilder(self.tasks, self.prompts)

        self.session: SessionContext | None = None

    # -- session lifecycle -------------------------------------------------

    def start_session(self, cwd: Path) -> SessionContext:
        """Resolve the active project the way `cd` implies a shell context,
        and build the SessionContext for it. Does not prompt — that's the
        caller's job (see resolve_startup_project for the interactive flow
        cli/main.py drives).
        """
        active = self.projects.get_active()
        self.session = self._context_builder.build_session(cwd, active)
        return self.session

    def resolve_startup_project(self, cwd: Path) -> tuple[Project | None, Path | None]:
        """Workspace discovery first, registry second, matching how `cd`
        implies context without being told.

        Returns (project, unregistered_workspace_root). Exactly one of the
        two is non-None when a workspace is found but not yet registered —
        the caller (cli/main.py) owns the interactive "register it? [Y/n]"
        prompt, this method only does the read-only detection.
        """
        workspace_root = self.projects.find_workspace_root(cwd)
        if workspace_root is not None:
            registered = self.projects.find_by_folder(workspace_root)
            if registered is not None:
                activated = self.projects.set_active(registered.slug)
                return activated, None
            return None, workspace_root

        last_active = self.projects.get_active()
        return last_active, None

    def register_workspace(
        self,
        workspace_root: Path,
        name: str | None = None,
        drive_folder: str | None = None,
    ) -> Project:
        return self.projects.register_workspace(workspace_root, name, drive_folder)

    def switch_project(self, name: str) -> Project:
        project = self.projects.get(name)
        return self.projects.set_active(project.slug)

    def refresh_session(self, cwd: Path) -> SessionContext:
        """Rebuild SessionContext from current disk state — call after any
        mutation that should be reflected immediately (project switch, task
        completed, prompt added) rather than waiting for the next full
        session start.
        """
        return self.start_session(cwd)

    def record_action(self, description: str) -> None:
        if self.session is not None:
            self.session.record_action(description)

    # -- convenience passthroughs ------------------------------------------

    def render_system_context(self) -> str:
        """Render the active project + plan as a system-prompt block, or ''
        if no project is active. This is how the agent learns which repo,
        folder, and tasks it's scoped to without being told mid-conversation.
        """
        if self.session is None or self.session.active_project is None:
            return ""

        ctx = self.session.active_project
        project = ctx.project

        lines = [
            f"## Active Project: {project.name}",
            "You are currently scoped to this project — assume any repo, file, "
            "or task reference is about it unless Sayan says otherwise.",
        ]
        if project.github_repo:
            lines.append(f"- GitHub repo: {project.github_repo}")
        if project.folder:
            lines.append(f"- Local folder: {project.folder}")
        if project.drive_folder:
            lines.append(f"- Google Drive folder: {project.drive_folder}")
        lines.append(f"- Open tasks: {ctx.open_task_count}")
        if ctx.blocked_task_count:
            lines.append(f"- Blocked tasks: {ctx.blocked_task_count}")
        if ctx.available_prompts:
            lines.append(f"- Available prompts: {', '.join(ctx.available_prompts)}")

        plan = self.planning.daily_plan(project)
        if plan.suggested_next_task:
            lines.append(f"- Suggested next task: {plan.suggested_next_task.title}")
        if plan.suggested_prompt:
            lines.append(f"- Suggested prompt: {plan.suggested_prompt}")

        return "\n".join(lines)

    def daily_plan(self) -> DailyPlan:
        active = self.projects.get_active()
        return self.planning.daily_plan(active)

    def project_dashboard(self, name: str | None = None) -> DashboardView | None:
        project = self.projects.get(name) if name else self.projects.get_active()
        if project is None:
            return None
        return self.dashboard.build(project)
