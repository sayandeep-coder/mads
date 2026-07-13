from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class TaskStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Task(BaseModel):
    """A single unit of work, always scoped to a project."""

    model_config = ConfigDict(frozen=True)

    id: int
    project_slug: str
    title: str
    description: str = ""
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.OPEN
    due_date: date | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class Project(BaseModel):
    """A registered workspace: the persisted record, not the enriched runtime view."""

    model_config = ConfigDict(frozen=True)

    slug: str
    name: str
    github_repo: str | None = None
    folder: str | None = None
    drive_folder: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    last_active_at: datetime | None = None

    @property
    def folder_path(self) -> Path | None:
        return Path(self.folder).expanduser().resolve() if self.folder else None


class PromptScope(StrEnum):
    GLOBAL = "global"
    PROJECT = "project"


class Prompt(BaseModel):
    """A reusable prompt asset, stored as markdown with frontmatter."""

    model_config = ConfigDict(frozen=True)

    slug: str
    title: str
    description: str = ""
    category: str = "general"
    body: str
    tags: list[str] = Field(default_factory=list)
    scope: PromptScope
    project_slug: str | None = None
    favorite: bool = False
    created_at: datetime
    updated_at: datetime


class ProjectContext(BaseModel):
    """The enriched, read-time view of a project every planner submodule consumes.

    Unlike `Project` (the persisted record), this includes computed
    summaries — open task counts, recent documents, available prompts —
    gathered fresh each time rather than stored, so nothing here can drift
    out of sync with the underlying task/prompt/document state.
    """

    model_config = ConfigDict(frozen=True)

    project: Project
    open_task_count: int = 0
    blocked_task_count: int = 0
    completed_task_count: int = 0
    recent_documents: list[str] = Field(default_factory=list)
    available_prompts: list[str] = Field(default_factory=list)
    recent_memories: list[str] = Field(default_factory=list)


class SessionContext(BaseModel):
    """Everything the planner knows about the current session, built once at
    startup and mutated in place as the session progresses."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    active_project: ProjectContext | None = None
    cwd: Path
    started_at: datetime
    preferences: dict[str, str] = Field(default_factory=dict)
    recent_actions: list[str] = Field(default_factory=list)
    current_goal: str | None = None

    def record_action(self, description: str, *, max_history: int = 20) -> None:
        self.recent_actions.append(description)
        del self.recent_actions[:-max_history]


class DailyPlan(BaseModel):
    project_name: str | None
    priorities: list[Task] = Field(default_factory=list)
    suggested_prompt: str | None = None
    suggested_next_task: Task | None = None
    summary: str = ""


class DashboardView(BaseModel):
    project: Project
    branch: str | None = None
    open_tasks: int = 0
    completed_tasks: int = 0
    progress_pct: float = 0.0
    recent_commits: list[str] = Field(default_factory=list)
    recent_documents: list[str] = Field(default_factory=list)
    last_session_at: datetime | None = None
    recommended_next_task: Task | None = None
