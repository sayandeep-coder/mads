from __future__ import annotations

from pathlib import Path

_DOCUMENT_EXTENSIONS = {".md", ".pdf", ".docx", ".xlsx", ".pptx"}
_DEFAULT_LIMIT = 5


def list_recent_documents(folder: Path, limit: int = _DEFAULT_LIMIT) -> list[str]:
    """Most recently modified document files under `folder`, relative paths.

    Shared by Dashboard (project overview) and SessionContextBuilder
    (system-prompt context) — neither owns this, it's a plain filesystem
    scan both need.
    """
    if not folder.exists():
        return []

    candidates = [
        p for p in folder.rglob("*")
        if p.is_file()
        and p.suffix.lower() in _DOCUMENT_EXTENSIONS
        and ".git" not in p.parts
    ]
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [str(p.relative_to(folder)) for p in candidates[:limit]]
