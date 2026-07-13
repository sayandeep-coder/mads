from __future__ import annotations

from datetime import date, datetime, timezone

from planner.models import Task, TaskPriority, TaskStatus
from planner.storage import JsonListStore, project_dir


class TaskNotFoundError(ValueError):
    """Raised when a task id doesn't exist for a project."""


def _list_store(slug: str) -> JsonListStore[Task]:
    return JsonListStore(project_dir(slug) / "tasks.json", Task)


class TaskManager:
    """Project-scoped task tracking: create, list, complete, update, delete.

    Storage is one tasks.json per project (via JsonListStore) — same layout
    as the original projects/tasks.py, now with a richer Task model
    (priority, due date, blocked status, tags) so the Planning Engine has
    something to actually reason about.
    """

    def create(
        self,
        project_slug: str,
        title: str,
        description: str = "",
        priority: TaskPriority = TaskPriority.MEDIUM,
        due_date: date | None = None,
        tags: list[str] | None = None,
    ) -> Task:
        store = _list_store(project_slug)
        tasks = store.read_all()
        next_id = max((t.id for t in tasks), default=0) + 1
        now = datetime.now(timezone.utc)

        task = Task(
            id=next_id,
            project_slug=project_slug,
            title=title,
            description=description,
            priority=priority,
            status=TaskStatus.OPEN,
            due_date=due_date,
            tags=tags or [],
            created_at=now,
            updated_at=now,
        )
        tasks.append(task)
        store.write_all(tasks)
        return task

    def list_all(
        self,
        project_slug: str,
        status: TaskStatus | None = None,
    ) -> list[Task]:
        tasks = _list_store(project_slug).read_all()
        if status is not None:
            tasks = [t for t in tasks if t.status == status]
        return tasks

    def get(self, project_slug: str, task_id: int) -> Task:
        for task in _list_store(project_slug).read_all():
            if task.id == task_id:
                return task
        raise TaskNotFoundError(f"No task with id {task_id} in project {project_slug!r}")

    def update(
        self,
        project_slug: str,
        task_id: int,
        title: str | None = None,
        description: str | None = None,
        priority: TaskPriority | None = None,
        status: TaskStatus | None = None,
        due_date: date | None = None,
        tags: list[str] | None = None,
    ) -> Task:
        store = _list_store(project_slug)
        tasks = store.read_all()

        updated: Task | None = None
        for index, task in enumerate(tasks):
            if task.id != task_id:
                continue

            changes: dict = {"updated_at": datetime.now(timezone.utc)}
            if title is not None:
                changes["title"] = title
            if description is not None:
                changes["description"] = description
            if priority is not None:
                changes["priority"] = priority
            if due_date is not None:
                changes["due_date"] = due_date
            if tags is not None:
                changes["tags"] = tags
            if status is not None:
                changes["status"] = status
                changes["completed_at"] = (
                    datetime.now(timezone.utc) if status == TaskStatus.DONE else None
                )

            updated = task.model_copy(update=changes)
            tasks[index] = updated
            break

        if updated is None:
            raise TaskNotFoundError(f"No task with id {task_id} in project {project_slug!r}")

        store.write_all(tasks)
        return updated

    def complete(self, project_slug: str, task_id: int) -> Task:
        return self.update(project_slug, task_id, status=TaskStatus.DONE)

    def delete(self, project_slug: str, task_id: int) -> bool:
        store = _list_store(project_slug)
        tasks = store.read_all()
        remaining = [t for t in tasks if t.id != task_id]
        if len(remaining) == len(tasks):
            return False
        store.write_all(remaining)
        return True

    def project_progress(self, project_slug: str) -> tuple[int, int, int]:
        """Return (open_count, blocked_count, done_count) for a project."""
        tasks = self.list_all(project_slug)
        open_count = sum(1 for t in tasks if t.status == TaskStatus.OPEN)
        blocked_count = sum(1 for t in tasks if t.status == TaskStatus.BLOCKED)
        done_count = sum(1 for t in tasks if t.status == TaskStatus.DONE)
        return open_count, blocked_count, done_count

    def due_today(self, project_slug: str) -> list[Task]:
        today = datetime.now().date()
        return [
            t for t in self.list_all(project_slug)
            if t.due_date == today and t.status != TaskStatus.DONE
        ]

    def open_task_count(self, project_slug: str) -> int:
        return len(self.list_all(project_slug, status=TaskStatus.OPEN))
