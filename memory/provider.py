from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from dataclasses import asdict
from typing import Any

from mcp import Tool

from config.settings import Settings
from mcp_servers.manager import ToolCallResult
from memory import store
from memory.schemas import MEMORY_TOOLS
from memory.search import search_memory as _search_memory

logger = logging.getLogger(__name__)


class MemoryProvider:
    """Local, persistent memory: preferences, projects, decisions, people.

    Backed by SQLite in ~/.mads/memory.sqlite3 — no external service, no
    vector DB. remember()/forget()/update_memory()/search_memory() are
    exposed as ordinary tools; Gemini decides when something is worth
    remembering, same as it decides when to call any other tool.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def name(self) -> str:
        return "memory"

    @staticmethod
    def is_available(settings: Settings) -> bool:
        return True  # local-only, no credentials required

    async def connect(self, exit_stack: AsyncExitStack) -> None:
        pass

    def list_tools(self) -> list[Tool]:
        return list(MEMORY_TOOLS)

    async def call_tool(self, name: str, arguments: dict) -> ToolCallResult:
        try:
            result = await asyncio.to_thread(self._dispatch, name, arguments)
        except Exception as exc:  # noqa: BLE001 — surface any failure back to the model
            logger.exception("Memory tool %r failed", name)
            return ToolCallResult(text=f"Error: {exc}", is_error=True)

        return ToolCallResult(text=str(result), is_error=False)

    def _dispatch(self, name: str, arguments: dict) -> Any:
        if name == "remember":
            memory = store.remember(arguments["category"], arguments["content"], arguments.get("tags"))
            return asdict(memory)

        if name == "forget":
            deleted = store.forget(arguments["memory_id"])
            return {"deleted": deleted}

        if name == "update_memory":
            try:
                memory = store.update_memory(
                    arguments["memory_id"],
                    arguments.get("content"),
                    arguments.get("tags"),
                    arguments.get("category"),
                )
            except store.InvalidCategoryError as exc:
                return {"error": str(exc)}
            if memory is None:
                return {"error": f"No memory found with id {arguments['memory_id']}"}
            return asdict(memory)

        if name == "search_memory":
            results = _search_memory(
                arguments["query"], arguments.get("category"), arguments.get("limit", 10)
            )
            return [{"score": r.score, "source": r.source, **asdict(r.memory)} for r in results]

        if name == "list_memories":
            memories = store.list_all(arguments.get("category"))
            return [asdict(m) for m in memories]

        raise ValueError(f"Unknown memory tool: {name!r}")
