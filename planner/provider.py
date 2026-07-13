from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from datetime import date
from pathlib import Path
from typing import Any, Awaitable, Callable

from mcp import Tool

from config.settings import Settings
from mcp_servers.manager import ToolCallResult
from planner.models import Project, PromptScope, TaskPriority, TaskStatus
from planner.planner import Planner
from planner.project_manager import ProjectNotFoundError
from planner.prompt_library import PromptNotFoundError
from planner.schemas import PLANNER_TOOLS
from planner.task_manager import TaskNotFoundError

logger = logging.getLogger(__name__)

OnSwitchCallback = Callable[[Project], Awaitable[None]]


class PlannerProvider:
    """Exposes Planner's project/task/prompt/planning surface as tools.

    This is the *only* way Gemini reaches Planner — everything else
    (startup resolution, system-prompt rendering, dashboard rendering) is
    driven directly by cli/main.py outside the tool-call loop. Switching
    the active project fires an on-switch callback so the REPL can re-scope
    the live filesystem MCP server and rebuild the system prompt to match.
    """

    def __init__(self, planner: Planner, settings: Settings, on_switch: OnSwitchCallback | None = None) -> None:
        self._planner = planner
        self._settings = settings
        self._on_switch = on_switch

    @property
    def name(self) -> str:
        return "planner"

    @staticmethod
    def is_available(settings: Settings) -> bool:
        return True  # local-only, no credentials required

    async def connect(self, exit_stack: AsyncExitStack) -> None:
        pass

    def list_tools(self) -> list[Tool]:
        return list(PLANNER_TOOLS)

    async def call_tool(self, name: str, arguments: dict) -> ToolCallResult:
        try:
            result = await asyncio.to_thread(self._dispatch, name, arguments)
            if name in {"use_project", "register_workspace"} and self._on_switch is not None:
                project = self._planner.projects.get_active()
                if project is not None:
                    await self._on_switch(project)
        except Exception as exc:  # noqa: BLE001 — surface any tool failure back to the model
            logger.exception("Planner tool %r failed", name)
            return ToolCallResult(text=f"Error: {exc}", is_error=True)

        return ToolCallResult(text=str(result), is_error=False)

    def _dispatch(self, name: str, arguments: dict) -> Any:
        planner = self._planner

        if name == "register_workspace":
            folder = Path(arguments["folder"]).expanduser().resolve()
            project = planner.register_workspace(
                folder, name=arguments.get("name"), drive_folder=arguments.get("drive_folder")
            )
            return project.model_dump(mode="json")

        if name == "use_project":
            try:
                project = planner.switch_project(arguments["name"])
            except ProjectNotFoundError as exc:
                return {"error": str(exc)}
            return project.model_dump(mode="json")

        if name == "list_projects":
            return [p.model_dump(mode="json") for p in planner.projects.list_all()]

        if name == "get_active_project":
            project = planner.projects.get_active()
            return project.model_dump(mode="json") if project else {"active_project": None}

        if name == "add_task":
            slug = self._require_active_slug()
            due_date = date.fromisoformat(arguments["due_date"]) if arguments.get("due_date") else None
            task = planner.tasks.create(
                slug,
                title=arguments["title"],
                description=arguments.get("description", ""),
                priority=TaskPriority(arguments.get("priority", "medium")),
                due_date=due_date,
                tags=arguments.get("tags"),
            )
            return task.model_dump(mode="json")

        if name == "list_tasks":
            slug = self._require_active_slug()
            status = TaskStatus(arguments["status"]) if arguments.get("status") else None
            return [t.model_dump(mode="json") for t in planner.tasks.list_all(slug, status)]

        if name == "update_task":
            slug = self._require_active_slug()
            due_date = date.fromisoformat(arguments["due_date"]) if arguments.get("due_date") else None
            try:
                task = planner.tasks.update(
                    slug,
                    task_id=arguments["task_id"],
                    title=arguments.get("title"),
                    description=arguments.get("description"),
                    priority=TaskPriority(arguments["priority"]) if arguments.get("priority") else None,
                    status=TaskStatus(arguments["status"]) if arguments.get("status") else None,
                    due_date=due_date,
                    tags=arguments.get("tags"),
                )
            except TaskNotFoundError as exc:
                return {"error": str(exc)}
            return task.model_dump(mode="json")

        if name == "complete_task":
            slug = self._require_active_slug()
            try:
                task = planner.tasks.complete(slug, arguments["task_id"])
            except TaskNotFoundError as exc:
                return {"error": str(exc)}
            return task.model_dump(mode="json")

        if name == "delete_task":
            slug = self._require_active_slug()
            deleted = planner.tasks.delete(slug, arguments["task_id"])
            return {"deleted": deleted}

        if name == "create_prompt":
            scope = PromptScope(arguments.get("scope", "global"))
            slug = planner.projects.get_active().slug if scope == PromptScope.PROJECT else None
            if scope == PromptScope.PROJECT and slug is None:
                return {"error": "No active project — can't create a project-scoped prompt."}
            prompt = planner.prompts.create(
                title=arguments["title"],
                body=arguments["body"],
                scope=scope,
                project_slug=slug,
                description=arguments.get("description", ""),
                category=arguments.get("category", "general"),
                tags=arguments.get("tags"),
            )
            return prompt.model_dump(mode="json")

        if name == "list_prompts":
            active = planner.projects.get_active()
            prompts = planner.prompts.list_all(
                project_slug=active.slug if active else None,
                category=arguments.get("category"),
                favorites_only=arguments.get("favorites_only", False),
            )
            return [p.model_dump(mode="json") for p in prompts]

        if name == "use_prompt":
            scope = PromptScope(arguments.get("scope", "global"))
            active = planner.projects.get_active()
            slug = active.slug if scope == PromptScope.PROJECT and active else None
            try:
                return planner.prompts.use(arguments["slug"], scope, slug)
            except PromptNotFoundError as exc:
                return {"error": str(exc)}

        if name == "daily_plan":
            plan = planner.daily_plan()
            return plan.model_dump(mode="json")

        if name == "project_dashboard":
            view = planner.project_dashboard(arguments.get("name"))
            if view is None:
                return {"error": "No active project and none specified."}
            return view.model_dump(mode="json")

        raise ValueError(f"Unknown planner tool: {name!r}")

    def _require_active_slug(self) -> str:
        project = self._planner.projects.get_active()
        if project is None:
            raise ValueError("No active project — use_project or register_workspace first.")
        return project.slug
