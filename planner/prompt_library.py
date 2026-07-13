from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from planner import storage
from planner.models import Prompt, PromptScope
from planner.storage import project_dir

_FRONTMATTER_PATTERN = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


class PromptNotFoundError(ValueError):
    """Raised when a named prompt doesn't exist in the requested scope."""


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip("-")
    if not slug:
        raise ValueError(f"Prompt title {title!r} has no usable characters for a slug")
    return slug


def _global_prompts_dir() -> Path:
    return storage.MADS_HOME / "prompts" / "global"


def _project_prompts_dir(project_slug: str) -> Path:
    return project_dir(project_slug) / "prompts"


def _prompts_dir(scope: PromptScope, project_slug: str | None) -> Path:
    if scope == PromptScope.GLOBAL:
        return _global_prompts_dir()
    if not project_slug:
        raise ValueError("project_slug is required for project-scoped prompts")
    return _project_prompts_dir(project_slug)


def _format_frontmatter(prompt: Prompt) -> str:
    lines = [
        "---",
        f"title: {prompt.title}",
        f"description: {prompt.description}",
        f"category: {prompt.category}",
        f"tags: {', '.join(prompt.tags)}",
        f"favorite: {str(prompt.favorite).lower()}",
        f"created: {prompt.created_at.isoformat()}",
        f"updated: {prompt.updated_at.isoformat()}",
        "---",
        "",
    ]
    return "\n".join(lines) + prompt.body


def _parse_prompt_file(path: Path, scope: PromptScope, project_slug: str | None) -> Prompt:
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_PATTERN.match(text)
    if not match:
        raise ValueError(f"Prompt file {path} is missing a frontmatter block")

    raw_frontmatter, body = match.group(1), match.group(2)
    fields: dict[str, str] = {}
    for line in raw_frontmatter.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()

    tags = [t.strip() for t in fields.get("tags", "").split(",") if t.strip()]

    return Prompt(
        slug=path.stem,
        title=fields.get("title", path.stem),
        description=fields.get("description", ""),
        category=fields.get("category", "general"),
        body=body.strip("\n"),
        tags=tags,
        scope=scope,
        project_slug=project_slug,
        favorite=fields.get("favorite", "false").lower() == "true",
        created_at=datetime.fromisoformat(fields["created"]) if "created" in fields else datetime.now(timezone.utc),
        updated_at=datetime.fromisoformat(fields["updated"]) if "updated" in fields else datetime.now(timezone.utc),
    )


class PromptLibrary:
    """Reusable prompt assets, global or project-scoped, stored as markdown
    files with a YAML-like frontmatter block — designed to be readable and
    hand-editable, not just machine-managed.
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
        slug = _slugify(title)
        directory = _prompts_dir(scope, project_slug)
        path = directory / f"{slug}.md"
        if path.exists():
            raise FileExistsError(f"Prompt {title!r} already exists in this scope")

        now = datetime.now(timezone.utc)
        prompt = Prompt(
            slug=slug,
            title=title,
            description=description,
            category=category,
            body=body,
            tags=tags or [],
            scope=scope,
            project_slug=project_slug,
            favorite=False,
            created_at=now,
            updated_at=now,
        )
        directory.mkdir(parents=True, exist_ok=True)
        path.write_text(_format_frontmatter(prompt), encoding="utf-8")
        return prompt

    def list_all(
        self,
        project_slug: str | None = None,
        category: str | None = None,
        favorites_only: bool = False,
    ) -> list[Prompt]:
        """List global prompts plus, if project_slug is given, that project's prompts too."""
        prompts: list[Prompt] = []

        global_dir = _global_prompts_dir()
        if global_dir.exists():
            for path in sorted(global_dir.glob("*.md")):
                prompts.append(_parse_prompt_file(path, PromptScope.GLOBAL, None))

        if project_slug:
            project_dir_path = _project_prompts_dir(project_slug)
            if project_dir_path.exists():
                for path in sorted(project_dir_path.glob("*.md")):
                    prompts.append(_parse_prompt_file(path, PromptScope.PROJECT, project_slug))

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
        path = _prompts_dir(scope, project_slug) / f"{slug}.md"
        if not path.exists():
            raise PromptNotFoundError(f"No prompt {slug!r} in scope {scope.value}")
        return _parse_prompt_file(path, scope, project_slug)

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
        existing = self.get(slug, scope, project_slug)
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
        path = _prompts_dir(scope, project_slug) / f"{slug}.md"
        path.write_text(_format_frontmatter(updated), encoding="utf-8")
        return updated

    def delete(
        self,
        slug: str,
        scope: PromptScope = PromptScope.GLOBAL,
        project_slug: str | None = None,
    ) -> bool:
        path = _prompts_dir(scope, project_slug) / f"{slug}.md"
        if not path.exists():
            return False
        path.unlink()
        return True

    def favorite(
        self,
        slug: str,
        scope: PromptScope = PromptScope.GLOBAL,
        project_slug: str | None = None,
        favorite: bool = True,
    ) -> Prompt:
        existing = self.get(slug, scope, project_slug)
        updated = existing.model_copy(update={"favorite": favorite, "updated_at": datetime.now(timezone.utc)})
        path = _prompts_dir(scope, project_slug) / f"{slug}.md"
        path.write_text(_format_frontmatter(updated), encoding="utf-8")
        return updated
