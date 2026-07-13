from __future__ import annotations

from datetime import date

from planner.models import DailyPlan, Project, Prompt, Task, TaskPriority, TaskStatus
from planner.prompt_library import PromptLibrary
from planner.task_manager import TaskManager

_PRIORITY_RANK = {TaskPriority.HIGH: 0, TaskPriority.MEDIUM: 1, TaskPriority.LOW: 2}

# Rule-based only, deliberately: deterministic, unit-testable, no added
# latency/cost from a second LLM call. LLM-driven reprioritization is the
# explicitly-deferred Adaptive Intelligence work — this ranking function is
# the seam it will eventually plug into without changing PlanningEngine's
# public surface.
def _task_sort_key(task: Task, today: date) -> tuple:
    is_overdue = task.due_date is not None and task.due_date < today and task.status != TaskStatus.DONE
    is_due_today = task.due_date == today
    return (
        0 if is_overdue else 1,
        0 if is_due_today else 1,
        _PRIORITY_RANK.get(task.priority, 1),
        task.updated_at,
    )


class PlanningEngine:
    """Turns raw task/prompt state into an actionable plan.

    Pure computation over TaskManager + PromptLibrary — no storage of its
    own, no I/O beyond what those two already do.
    """

    def __init__(self, task_manager: TaskManager, prompt_library: PromptLibrary) -> None:
        self._tasks = task_manager
        self._prompts = prompt_library

    def prioritized_tasks(self, project_slug: str, limit: int = 5) -> list[Task]:
        today = date.today()
        open_tasks = [
            t for t in self._tasks.list_all(project_slug)
            if t.status in (TaskStatus.OPEN, TaskStatus.IN_PROGRESS)
        ]
        open_tasks.sort(key=lambda t: _task_sort_key(t, today))
        return open_tasks[:limit]

    def suggest_next_task(self, project_slug: str) -> Task | None:
        prioritized = self.prioritized_tasks(project_slug, limit=1)
        return prioritized[0] if prioritized else None

    def suggest_prompt(self, project_slug: str | None) -> Prompt | None:
        """Favor a favorited prompt scoped to the project, then any
        favorite, then the most recently updated prompt available."""
        prompts = self._prompts.list_all(project_slug=project_slug)
        if not prompts:
            return None

        favorites = [p for p in prompts if p.favorite]
        pool = favorites or prompts
        return max(pool, key=lambda p: p.updated_at)

    def recently_completed(self, project_slug: str, since: date) -> list[Task]:
        return [
            t for t in self._tasks.list_all(project_slug, status=TaskStatus.DONE)
            if t.completed_at is not None and t.completed_at.date() >= since
        ]

    def daily_plan(self, project: Project | None) -> DailyPlan:
        if project is None:
            return DailyPlan(project_name=None, summary="No active project — nothing to plan yet.")

        priorities = self.prioritized_tasks(project.slug, limit=3)
        suggested_prompt = self.suggest_prompt(project.slug)
        suggested_next = priorities[0] if priorities else None

        summary = (
            f"{len(priorities)} priority task(s) for {project.name}."
            if priorities
            else f"No open tasks for {project.name} — clean slate."
        )

        return DailyPlan(
            project_name=project.name,
            priorities=priorities,
            suggested_prompt=suggested_prompt.title if suggested_prompt else None,
            suggested_next_task=suggested_next,
            summary=summary,
        )
