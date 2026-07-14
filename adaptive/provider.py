from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from typing import Any

from mcp import Tool

from adaptive.models import FactCategory
from adaptive.profile import AdaptiveProfile, CandidateNotFoundError
from adaptive.schemas import ADAPTIVE_TOOLS
from config.settings import Settings
from mcp_servers.manager import ToolCallResult

logger = logging.getLogger(__name__)


class AdaptiveProvider:
    """Exposes the approval-queue surface (list/approve/reject pending,
    list approved profile) as tools. The import pipeline itself is
    deliberately not here — see adaptive.schemas for why; it's a CLI-only
    command in cli/main.py.
    """

    def __init__(self, profile: AdaptiveProfile, settings: Settings) -> None:
        self._profile = profile
        self._settings = settings

    @property
    def name(self) -> str:
        return "adaptive"

    @staticmethod
    def is_available(settings: Settings) -> bool:
        return True  # local-only, no credentials required

    async def connect(self, exit_stack: AsyncExitStack) -> None:
        pass

    def list_tools(self) -> list[Tool]:
        return list(ADAPTIVE_TOOLS)

    async def call_tool(self, name: str, arguments: dict) -> ToolCallResult:
        try:
            result = await asyncio.to_thread(self._dispatch, name, arguments)
        except Exception as exc:  # noqa: BLE001 — surface any tool failure back to the model
            logger.exception("Adaptive tool %r failed", name)
            return ToolCallResult(text=f"Error: {exc}", is_error=True)

        return ToolCallResult(text=str(result), is_error=False)

    def _dispatch(self, name: str, arguments: dict) -> Any:
        if name == "list_pending_candidates":
            category = FactCategory(arguments["category"]) if arguments.get("category") else None
            return [p.model_dump(mode="json") for p in self._profile.list_pending(category)]

        if name == "approve_candidate":
            try:
                fact = self._profile.approve(arguments["candidate_id"])
            except CandidateNotFoundError as exc:
                return {"error": str(exc)}
            return fact.model_dump(mode="json")

        if name == "reject_candidate":
            rejected = self._profile.reject(arguments["candidate_id"])
            return {"rejected": rejected}

        if name == "list_adaptive_profile":
            category = FactCategory(arguments["category"]) if arguments.get("category") else None
            return [f.model_dump(mode="json") for f in self._profile.list_approved(category)]

        raise ValueError(f"Unknown adaptive tool: {name!r}")
