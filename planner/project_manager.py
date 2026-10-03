from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from planner.models import Project
from planner import storage
from server.db.connection import get_connection


def _active_pointer_path() -> Path:
    # Which project is "active" is per-machine session state (like a
    # shell's $PWD or kubectl's current-context) — not data to share
    # across machines, so this one stays a local file even though the
    # project registry itself now lives in Postgres.
    return storage.MADS_HOME / "active_project"

# Presence of any of these at a directory's root marks it as a real software
# workspace worth knowing about — not an arbitrary folder.
_WORKSPACE_MARKERS = (
    ".git",
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "Gemfile",
    "composer.json",
)

_GIT_REMOTE_PATTERNS = (
    re.compile(r"^git@github\.com:(?P<repo>[^/]+/[^/]+?)(?:\.git)?$"),
    re.compile(r"^https://github\.com/(?P<repo>[^/]+/[^/]+?)(?:\.git)?$"),
)


class ProjectNotFoundError(ValueError):
    """Raised when a named project doesn't exist."""


class ProjectAlreadyExistsError(ValueError):
    """Raised when creating a project whose slug is already taken."""


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if not slug:
        raise ValueError(f"Project name {name!r} has no usable characters for a slug")
    return slug


def _row_to_project(row: dict) -> Project:
    return Project(
        slug=row["slug"],
        name=row["name"],
        github_repo=row["github_repo"],
        folder=row["folder"],
        drive_folder=row["drive_folder"],
        tags=row["tags"] or [],
        created_at=row["created_at"],
        last_active_at=row["last_active_at"],
    )


class ProjectManager:
    """Registry of known workspaces, plus workspace discovery.

    Discovery is the primary path (find_workspace_root / detect_github_repo,
    used at startup to auto-detect and offer to register unseen workspaces);
    the registry (create/get/list/set_active) is what makes a discovered
    workspace durable across sessions — backed by the `projects` table.
    Neither is meant to be used without the other — see
    planner.planner.Planner for the orchestration.
    """

    # -- registry --------------------------------------------------------

    def create(
        self,
        name: str,
        github_repo: str | None = None,
        folder: str | None = None,
        drive_folder: str | None = None,
        tags: list[str] | None = None,
    ) -> Project:
        slug = _slugify(name)
        now = datetime.now(timezone.utc)

        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM projects WHERE slug = %s", (slug,))
            if cur.fetchone() is not None:
                raise ProjectAlreadyExistsError(f"Project {name!r} already exists")

            cur.execute(
                """
                INSERT INTO projects (slug, name, github_repo, folder, drive_folder, tags, created_at, last_active_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NULL)
                """,
                (slug, name, github_repo or None, folder or None, drive_folder or None, tags or [], now),
            )

        return Project(
            slug=slug, name=name, github_repo=github_repo or None, folder=folder or None,
            drive_folder=drive_folder or None, tags=tags or [], created_at=now, last_active_at=None,
        )

    def get(self, name_or_slug: str) -> Project:
        slug = _slugify(name_or_slug)
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM projects WHERE slug = %s", (slug,))
            row = cur.fetchone()
        if row is None:
            raise ProjectNotFoundError(f"No project named {name_or_slug!r}")
        return _row_to_project(row)

    def list_all(self) -> list[Project]:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM projects ORDER BY slug")
            rows = cur.fetchall()
        return [_row_to_project(row) for row in rows]

    def find_by_folder(self, folder: Path) -> Project | None:
        """Return the registered project whose folder exactly matches, if any."""
        folder = folder.expanduser().resolve()
        for project in self.list_all():
            if project.folder_path == folder:
                return project
        return None

    def touch(self, slug: str) -> Project:
        """Update a project's last_active_at to now."""
        project = self.get(slug)  # validates existence
        now = datetime.now(timezone.utc)
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("UPDATE projects SET last_active_at = %s WHERE slug = %s", (now, project.slug))
        return project.model_copy(update={"last_active_at": now})

    def set_active(self, slug: str) -> Project:
        """Mark a project active: writes the pointer file and bumps last_active_at."""
        project = self.touch(slug)
        pointer_path = _active_pointer_path()
        pointer_path.parent.mkdir(parents=True, exist_ok=True)
        pointer_path.write_text(project.slug, encoding="utf-8")
        return project

    def get_active(self) -> Project | None:
        """Return the currently active project, if any pointer is set."""
        pointer_path = _active_pointer_path()
        if not pointer_path.exists():
            return None
        slug = pointer_path.read_text(encoding="utf-8").strip()
        if not slug:
            return None
        try:
            return self.get(slug)
        except ProjectNotFoundError:
            return None

    def clear_active(self) -> None:
        pointer_path = _active_pointer_path()
        if pointer_path.exists():
            pointer_path.unlink()

    def detect_from_cwd(self, cwd: Path) -> Project | None:
        """Find the registered project whose folder is an ancestor of (or
        equal to) cwd, if any. When multiple match (nested folders), the
        most specific (longest path) wins.
        """
        cwd = cwd.expanduser().resolve()
        best: Project | None = None
        best_len = -1

        for project in self.list_all():
            folder = project.folder_path
            if folder is None:
                continue
            try:
                cwd.relative_to(folder)
            except ValueError:
                continue
            depth = len(folder.parts)
            if depth > best_len:
                best = project
                best_len = depth

        return best

    # -- workspace discovery ---------------------------------------------

    @staticmethod
    def find_workspace_root(start: Path) -> Path | None:
        """Walk upward from `start` looking for a directory with a project marker.

        Mirrors how `git`, `npm`, etc. locate the project root from any
        subdirectory — the closest ancestor (including `start` itself) wins.
        """
        current = start.expanduser().resolve()
        for directory in (current, *current.parents):
            if any((directory / marker).exists() for marker in _WORKSPACE_MARKERS):
                return directory
        return None

    @staticmethod
    def detect_github_repo(workspace_root: Path) -> str | None:
        """Infer 'owner/repo' from the workspace's git remote — never prompts
        for or touches any GitHub credentials, this only reads local git config."""
        try:
            result = subprocess.run(
                ["git", "-C", str(workspace_root), "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return None

        if result.returncode != 0:
            return None

        url = result.stdout.strip()
        for pattern in _GIT_REMOTE_PATTERNS:
            match = pattern.match(url)
            if match:
                return match.group("repo")
        return None

    @staticmethod
    def detect_current_branch(workspace_root: Path) -> str | None:
        try:
            result = subprocess.run(
                ["git", "-C", str(workspace_root), "branch", "--show-current"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    @staticmethod
    def suggest_project_name(workspace_root: Path) -> str:
        return workspace_root.name

    def register_workspace(
        self,
        workspace_root: Path,
        name: str | None = None,
        drive_folder: str | None = None,
    ) -> Project:
        """Register a discovered workspace, auto-filling repo/name from disk state.

        Idempotent: registering an already-known folder just reactivates it,
        so callers never need to check find_by_folder first.
        """
        workspace_root = workspace_root.expanduser().resolve()
        existing = self.find_by_folder(workspace_root)
        if existing is not None:
            return self.set_active(existing.slug)

        project_name = name or self.suggest_project_name(workspace_root)
        github_repo = self.detect_github_repo(workspace_root)
        project = self.create(
            name=project_name,
            github_repo=github_repo,
            folder=str(workspace_root),
            drive_folder=drive_folder,
        )
        return self.set_active(project.slug)
