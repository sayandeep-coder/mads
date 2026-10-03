from __future__ import annotations

from config.settings import Settings
from skills import docs, excel, pdf, pptx
from skills.registry import Skill, SkillRegistry

__all__ = ["Skill", "SkillRegistry", "build_registry"]


def build_registry(settings: Settings) -> SkillRegistry:
    """Assemble every document skill Mads knows about. Called once per
    session (agent.session.build_session and friends) — see skills/registry.py
    for what a Skill actually is and how Agent loads one on demand.
    """
    return SkillRegistry(
        [
            pdf.build_skill(settings),
            pptx.build_skill(settings),
            excel.build_skill(settings),
            docs.build_skill(settings),
        ]
    )
