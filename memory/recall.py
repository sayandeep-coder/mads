from __future__ import annotations

from pathlib import Path

from memory.store import list_all

_PROFILE_PATH = Path(__file__).parent / "profile.md"

# Per-category cap on how many recent memories get folded into the system
# prompt automatically. Bounded so this stays a summary, not the whole
# store — anything beyond this is still reachable via search_memory().
_MAX_PER_CATEGORY = 8

_CATEGORY_HEADINGS = {
    "preference": "Preferences",
    "project": "Active Projects",
    "decision": "Recent Decisions",
    "person": "People",
}


def _load_profile() -> str:
    if not _PROFILE_PATH.exists():
        return ""
    return _PROFILE_PATH.read_text(encoding="utf-8").strip()


def _format_memories_section() -> str:
    sections: list[str] = []

    for category, heading in _CATEGORY_HEADINGS.items():
        memories = list_all(category=category)[:_MAX_PER_CATEGORY]
        if not memories:
            continue

        lines = [f"### {heading}"]
        lines.extend(f"- {m.content}" for m in memories)
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def build_recall_summary() -> str:
    """Build the memory context injected into the system prompt at session start.

    Combines the static executive profile (always included in full) with a
    bounded, recency-ordered slice of accumulated memories per category.
    Anything not captured here is still reachable through search_memory().
    """
    profile = _load_profile()
    memories_section = _format_memories_section()

    parts = []
    if profile:
        parts.append(profile)
    if memories_section:
        parts.append("## Recent Memory\n\n" + memories_section)

    return "\n\n".join(parts)
