from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from mcp import Tool

# A skill's dispatch function: given a tool name (one this skill owns) and
# its arguments, run it and return whatever the tool should hand back to
# Gemini. Raising is fine — Agent already catches and reports tool
# failures the same way it does for MCP-backed tools.
SkillDispatch = Callable[[str, dict[str, Any]], Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class Skill:
    """One self-contained capability Mads can load on demand: document
    generation/reading for one file type (PDF, PPTX, Excel, Docs), bundled
    with its own usage guidance and its own tools — mirrors how Claude
    Code's skills work (a name + one-line description always visible, full
    instructions and tool access only loaded once actually invoked).
    """

    name: str
    description: str
    instructions: str
    tools: list[Tool]
    dispatch: SkillDispatch


class SkillRegistry:
    """Holds every skill Mads knows about. Agent consults this to build the
    always-visible skill index (name + description) and to resolve a
    load_skill call into the real markdown + tools to activate.
    """

    def __init__(self, skills: list[Skill] | None = None) -> None:
        self._skills: dict[str, Skill] = {}
        for skill in skills or []:
            self.register(skill)

    def register(self, skill: Skill) -> None:
        if skill.name in self._skills:
            raise ValueError(f"Duplicate skill name: {skill.name!r}")
        self._skills[skill.name] = skill

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def all(self) -> list[Skill]:
        return list(self._skills.values())

    def render_index(self) -> str:
        """One line per skill: name + description — cheap enough to always
        keep in the system prompt so Gemini knows what exists without
        paying for every skill's full tool schemas up front.
        """
        if not self._skills:
            return ""
        lines = [f"- {skill.name}: {skill.description}" for skill in self._skills.values()]
        return "\n".join(lines)

    def tool_owner(self, tool_name: str) -> Skill | None:
        """Which skill (if any) owns a given tool name — used once a skill
        is loaded and Agent needs to route a real tool call to it.
        """
        for skill in self._skills.values():
            if any(tool.name == tool_name for tool in skill.tools):
                return skill
        return None
