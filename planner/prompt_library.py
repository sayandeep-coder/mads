from __future__ import annotations

import re
from datetime import datetime, timezone

from planner.models import Prompt, PromptScope
from server.db.connection import get_connection


class PromptNotFoundError(ValueError):
    """Raised when a named prompt doesn't exist in the requested scope."""


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip("-")
    if not slug:
        raise ValueError(f"Prompt title {title!r} has no usable characters for a slug")
    return slug


def _row_to_prompt(row: dict) -> Prompt:
    return Prompt(
        slug=row["slug"],
        title=row["title"],
        description=row["description"],
        category=row["category"],
        body=row["body"],
        tags=row["tags"] or [],
        scope=PromptScope(row["scope"]),
        project_slug=row["project_slug"],
        favorite=row["favorite"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class PromptLibrary:
    """Reusable prompt assets, global or project-scoped — backed by the
    `prompts` table (slug is unique per scope, not globally; see
    schema.sql's prompts_scope_unique index).
    """

    def create(
        self,
        title: str,
        body: str,
        scope: PromptScope = PromptScope.GLOBAL,
        project_slug: str | None = None,
        description: str = "",
        category: str = "general",
        tags: list[str] | None = None,
    ) -> Prompt:
        if scope == PromptScope.PROJECT and not project_slug:
            raise ValueError("project_slug is required for project-scoped prompts")

        slug = _slugify(title)
        now = datetime.now(timezone.utc)

        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM prompts WHERE slug = %s AND scope = %s AND COALESCE(project_slug, '') = %s",
                (slug, scope.value, project_slug or ""),
            )
            if cur.fetchone() is not None:
                raise FileExistsError(f"Prompt {title!r} already exists in this scope")

            cur.execute(
                """
                INSERT INTO prompts (slug, title, description, category, body, tags, scope,
                                      project_slug, favorite, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, FALSE, %s, %s)
                """,
                (slug, title, description, category, body, tags or [], scope.value, project_slug, now, now),
            )

        return Prompt(
            slug=slug, title=title, description=description, category=category, body=body,
            tags=tags or [], scope=scope, project_slug=project_slug, favorite=False,
            created_at=now, updated_at=now,
        )

    def list_all(
        self,
        project_slug: str | None = None,
        category: str | None = None,
        favorites_only: bool = False,
    ) -> list[Prompt]:
        """List global prompts plus, if project_slug is given, that project's prompts too."""
        with get_connection() as conn, conn.cursor() as cur:
            if project_slug:
                cur.execute(
                    "SELECT * FROM prompts WHERE scope = 'global' OR project_slug = %s ORDER BY slug",
                    (project_slug,),
                )
            else:
                cur.execute("SELECT * FROM prompts WHERE scope = 'global' ORDER BY slug")
            rows = cur.fetchall()

        prompts = [_row_to_prompt(row) for row in rows]
        if category is not None:
            prompts = [p for p in prompts if p.category == category]
        if favorites_only:
            prompts = [p for p in prompts if p.favorite]
        return prompts

    def get(
        self,
        slug: str,
        scope: PromptScope = PromptScope.GLOBAL,
        project_slug: str | None = None,
    ) -> Prompt:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM prompts WHERE slug = %s AND scope = %s AND COALESCE(project_slug, '') = %s",
                (slug, scope.value, project_slug or ""),
            )
            row = cur.fetchone()
        if row is None:
            raise PromptNotFoundError(f"No prompt {slug!r} in scope {scope.value}")
        return _row_to_prompt(row)

    def use(
        self,
        slug: str,
        scope: PromptScope = PromptScope.GLOBAL,
        project_slug: str | None = None,
    ) -> str:
        """Return a prompt's body, ready to send as a message — this is the
        read path chat uses; it does not mutate usage stats (no tracking
        beyond favorite/updated_at exists yet, kept simple by design)."""
        return self.get(slug, scope, project_slug).body

    def update(
        self,
        slug: str,
        scope: PromptScope = PromptScope.GLOBAL,
        project_slug: str | None = None,
        title: str | None = None,
        body: str | None = None,
        description: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
    ) -> Prompt:
        existing = self.get(slug, scope, project_slug)  # raises PromptNotFoundError if missing
        updated = existing.model_copy(
            update={
                "title": title if title is not None else existing.title,
                "body": body if body is not None else existing.body,
                "description": description if description is not None else existing.description,
                "category": category if category is not None else existing.category,
                "tags": tags if tags is not None else existing.tags,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE prompts SET title = %s, body = %s, description = %s, category = %s,
                                    tags = %s, updated_at = %s
                WHERE slug = %s AND scope = %s AND COALESCE(project_slug, '') = %s
                """,
                (updated.title, updated.body, updated.description, updated.category, updated.tags,
                 updated.updated_at, slug, scope.value, project_slug or ""),
            )
        return updated

    def delete(
        self,
        slug: str,
        scope: PromptScope = PromptScope.GLOBAL,
        project_slug: str | None = None,
    ) -> bool:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM prompts WHERE slug = %s AND scope = %s AND COALESCE(project_slug, '') = %s",
                (slug, scope.value, project_slug or ""),
            )
            return cur.rowcount > 0

    def favorite(
        self,
        slug: str,
        scope: PromptScope = PromptScope.GLOBAL,
        project_slug: str | None = None,
        favorite: bool = True,
    ) -> Prompt:
        existing = self.get(slug, scope, project_slug)  # raises PromptNotFoundError if missing
        now = datetime.now(timezone.utc)
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE prompts SET favorite = %s, updated_at = %s
                WHERE slug = %s AND scope = %s AND COALESCE(project_slug, '') = %s
                """,
                (favorite, now, slug, scope.value, project_slug or ""),
            )
        return existing.model_copy(update={"favorite": favorite, "updated_at": now})
