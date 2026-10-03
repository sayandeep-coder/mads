"""One-off migration: copies every local store (~/.mads/chats.db,
~/.mads/memory.sqlite3, ~/.mads/projects/*/{project,tasks}.json,
~/.mads/adaptive/{profile,pending,ledger}.json) into the Postgres schema
in server/db/schema.sql. Idempotent — every insert is ON CONFLICT DO
NOTHING, so re-running after partial progress or new local data just
fills in what's missing rather than duplicating rows.

Run with: uv run python3 -m server.db.migrate_from_sqlite
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from dotenv import load_dotenv

MADS_HOME = Path.home() / ".mads"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sqlite(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def migrate_chats(pg: psycopg.Connection) -> None:
    db_path = MADS_HOME / "chats.db"
    if not db_path.exists():
        print("chats.db not found — skipping")
        return
    with _sqlite(db_path) as conn:
        sessions = conn.execute("SELECT * FROM sessions").fetchall()
        messages = conn.execute("SELECT * FROM messages").fetchall()

    with pg.cursor() as cur:
        for s in sessions:
            cur.execute(
                """
                INSERT INTO sessions (id, title, created_at, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (s["id"], s["title"], s["created_at"], s["updated_at"]),
            )
        for m in messages:
            cur.execute(
                """
                INSERT INTO messages (id, session_id, role, text, tool_calls, files, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (m["id"], m["session_id"], m["role"], m["text"], m["tool_calls"], m["files"], m["created_at"]),
            )
    print(f"chats: {len(sessions)} sessions, {len(messages)} messages")


def migrate_memory(pg: psycopg.Connection) -> None:
    db_path = MADS_HOME / "memory.sqlite3"
    if not db_path.exists():
        print("memory.sqlite3 not found — skipping")
        return
    with _sqlite(db_path) as conn:
        rows = conn.execute("SELECT * FROM memories").fetchall()

    with pg.cursor() as cur:
        for r in rows:
            cur.execute(
                """
                INSERT INTO memories (id, category, content, tags, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (r["id"], r["category"], r["content"], r["tags"], r["created_at"], r["updated_at"]),
            )
    print(f"memory: {len(rows)} memories")


def migrate_planner(pg: psycopg.Connection) -> None:
    projects_root = MADS_HOME / "projects"
    if not projects_root.exists():
        print("projects/ not found — skipping")
        return

    project_count = 0
    task_count = 0
    prompt_count = 0

    with pg.cursor() as cur:
        for project_dir in sorted(projects_root.iterdir()):
            project_json = project_dir / "project.json"
            if not project_json.exists():
                continue
            p = json.loads(project_json.read_text())
            cur.execute(
                """
                INSERT INTO projects (slug, name, github_repo, folder, drive_folder, tags, created_at, last_active_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (slug) DO NOTHING
                """,
                (
                    p["slug"], p["name"], p.get("github_repo"), p.get("folder"), p.get("drive_folder"),
                    p.get("tags", []), p["created_at"], p.get("last_active_at"),
                ),
            )
            project_count += 1

            tasks_json = project_dir / "tasks.json"
            if tasks_json.exists():
                for t in json.loads(tasks_json.read_text()):
                    cur.execute(
                        """
                        INSERT INTO tasks (id, project_slug, title, description, priority, status,
                                           due_date, tags, created_at, updated_at, completed_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        (
                            t["id"], t["project_slug"], t["title"], t.get("description", ""),
                            t.get("priority", "medium"), t.get("status", "open"), t.get("due_date"),
                            t.get("tags", []), t["created_at"], t["updated_at"], t.get("completed_at"),
                        ),
                    )
                    task_count += 1

            prompts_dir = project_dir / "prompts"
            if prompts_dir.exists():
                prompt_count += _migrate_prompt_dir(cur, prompts_dir, project_slug=p["slug"])

        global_prompts_dir = MADS_HOME / "prompts" / "global"
        if global_prompts_dir.exists():
            prompt_count += _migrate_prompt_dir(cur, global_prompts_dir, project_slug=None)

    print(f"planner: {project_count} projects, {task_count} tasks, {prompt_count} prompts")


def _migrate_prompt_dir(cur: psycopg.Cursor, prompts_dir: Path, project_slug: str | None) -> int:
    """Prompts are markdown files with a frontmatter block written by
    planner/prompt_library.py's _format_frontmatter — slug is the filename
    stem (never stored in the frontmatter itself), and dates use the keys
    `created`/`updated`, not `created_at`/`updated_at`. Mirrors
    _parse_prompt_file's parsing exactly rather than re-deriving it.
    """
    count = 0
    for md_file in prompts_dir.glob("*.md"):
        text = md_file.read_text()
        if not text.startswith("---"):
            continue
        _, frontmatter, body = text.split("---", 2)
        meta: dict[str, str] = {}
        for line in frontmatter.strip().splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip()

        cur.execute(
            """
            INSERT INTO prompts (slug, title, description, category, body, tags, scope,
                                  project_slug, favorite, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (slug) DO NOTHING
            """,
            (
                md_file.stem, meta.get("title", md_file.stem), meta.get("description", ""),
                meta.get("category", "general"), body.strip("\n"),
                [t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
                "project" if project_slug else "global", project_slug,
                meta.get("favorite", "false").lower() == "true",
                meta.get("created") or _now_iso(), meta.get("updated") or _now_iso(),
            ),
        )
        count += 1
    return count


def migrate_adaptive(pg: psycopg.Connection) -> None:
    adaptive_home = MADS_HOME / "adaptive"

    pending_path = adaptive_home / "pending.json"
    approved_count = 0
    pending_count = 0
    with pg.cursor() as cur:
        if pending_path.exists():
            for c in json.loads(pending_path.read_text()):
                cur.execute(
                    """
                    INSERT INTO adaptive_pending_candidates
                        (id, category, statement, confidence, recurrence,
                         source_conversation_ids, contradicts, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (
                        c["id"], c["category"], c["statement"], c["confidence"], c["recurrence"],
                        c.get("source_conversation_ids", []), c.get("contradicts", []),
                        c.get("status", "pending"), c["created_at"],
                    ),
                )
                pending_count += 1

        profile_path = adaptive_home / "profile.json"
        if profile_path.exists():
            for f in json.loads(profile_path.read_text()):
                cur.execute(
                    """
                    INSERT INTO adaptive_approved_facts
                        (id, category, statement, confidence, approved_at, source_conversation_ids)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (
                        f["id"], f["category"], f["statement"], f["confidence"],
                        f["approved_at"], f.get("source_conversation_ids", []),
                    ),
                )
                approved_count += 1

        ledger_path = adaptive_home / "ledger.json"
        ledger_count = 0
        if ledger_path.exists():
            for entry in json.loads(ledger_path.read_text()):
                cur.execute(
                    """
                    INSERT INTO adaptive_ledger (conversation_id, content_hash, processed_at, outcome)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (conversation_id) DO NOTHING
                    """,
                    (entry["conversation_id"], entry["content_hash"], entry["processed_at"], entry["outcome"]),
                )
                ledger_count += 1

    print(f"adaptive: {pending_count} pending, {approved_count} approved, {ledger_count} ledger entries")


def main() -> None:
    load_dotenv()
    with psycopg.connect(os.environ["DATABASE_URL"]) as pg:
        migrate_chats(pg)
        migrate_memory(pg)
        migrate_planner(pg)
        migrate_adaptive(pg)
        pg.commit()
    print("Migration complete.")


if __name__ == "__main__":
    main()
