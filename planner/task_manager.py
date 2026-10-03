from __future__ import annotations

from datetime import date, datetime, timezone

from planner.models import Task, TaskPriority, TaskStatus
from server.db.connection import get_connection


class TaskNotFoundError(ValueError):
    """Raised when a task id doesn't exist for a project."""


def _row_to_task(row: dict) -> Task:
    return Task(
        id=row["id"],
        project_slug=row["project_slug"],
        title=row["title"],
        description=row["description"],
        priority=TaskPriority(row["priority"]),
        status=TaskStatus(row["status"]),
        due_date=row["due_date"],
        tags=row["tags"] or [],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        completed_at=row["completed_at"],
    )


class TaskManager:
    """Project-scoped task tracking: create, list, complete, update, delete.

    Backed by the `tasks` table (one row per task, scoped by project_slug) —
    same Task model (priority, due date, blocked status, tags) as before,
    just no longer one tasks.json file per project.
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
        now = datetime.now(timezone.utc)
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tasks (project_slug, title, description, priority, status,
                                    due_date, tags, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (project_slug, title, description, priority.value, TaskStatus.OPEN.value,
                 due_date, tags or [], now, now),
            )
            task_id = cur.fetchone()["id"]

        return Task(
            id=task_id, project_slug=project_slug, title=title, description=description,
            priority=priority, status=TaskStatus.OPEN, due_date=due_date, tags=tags or [],
            created_at=now, updated_at=now, completed_at=None,
        )

    def list_all(
        self,
        project_slug: str,
        status: TaskStatus | None = None,
    ) -> list[Task]:
        with get_connection() as conn, conn.cursor() as cur:
            if status is not None:
                cur.execute(
                    "SELECT * FROM tasks WHERE project_slug = %s AND status = %s ORDER BY id",
                    (project_slug, status.value),
                )
            else:
                cur.execute("SELECT * FROM tasks WHERE project_slug = %s ORDER BY id", (project_slug,))
            rows = cur.fetchall()
        return [_row_to_task(row) for row in rows]

    def get(self, project_slug: str, task_id: int) -> Task:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM tasks WHERE project_slug = %s AND id = %s", (project_slug, task_id))
            row = cur.fetchone()
        if row is None:
            raise TaskNotFoundError(f"No task with id {task_id} in project {project_slug!r}")
        return _row_to_task(row)

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
        current = self.get(project_slug, task_id)  # raises TaskNotFoundError if missing

        now = datetime.now(timezone.utc)
        new_title = title if title is not None else current.title
        new_description = description if description is not None else current.description
        new_priority = priority if priority is not None else current.priority
        new_due_date = due_date if due_date is not None else current.due_date
        new_tags = tags if tags is not None else current.tags
        new_status = status if status is not None else current.status
        new_completed_at = (now if new_status == TaskStatus.DONE else None) if status is not None else current.completed_at

        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tasks SET title = %s, description = %s, priority = %s, status = %s,
                                  due_date = %s, tags = %s, updated_at = %s, completed_at = %s
                WHERE project_slug = %s AND id = %s
                """,
                (new_title, new_description, new_priority.value, new_status.value, new_due_date,
                 new_tags, now, new_completed_at, project_slug, task_id),
            )

        return Task(
            id=task_id, project_slug=project_slug, title=new_title, description=new_description,
            priority=new_priority, status=new_status, due_date=new_due_date, tags=new_tags,
            created_at=current.created_at, updated_at=now, completed_at=new_completed_at,
        )

    def complete(self, project_slug: str, task_id: int) -> Task:
        return self.update(project_slug, task_id, status=TaskStatus.DONE)

    def delete(self, project_slug: str, task_id: int) -> bool:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM tasks WHERE project_slug = %s AND id = %s", (project_slug, task_id))
            return cur.rowcount > 0

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
