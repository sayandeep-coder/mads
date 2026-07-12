from __future__ import annotations

import asyncio
import logging

from google import genai
from google.genai import types as genai_types

from agent.system_prompt import build_system_prompt
from agent.tools import build_gemini_tools
from config.settings import Settings
from mcp_servers.manager import MCPManager, MCPToolNotFoundError

logger = logging.getLogger(__name__)

_MAX_TOOL_CALL_ROUNDS = 8


class Agent:
    """The single Mads agent: one Gemini chat session, many MCP-backed tools.

    Gemini alone decides whether a tool call is needed, which tool(s) to
    call, and whether to chain multiple calls — this class only executes
    what Gemini asks for and feeds results back.
    """

    def __init__(self, settings: Settings, mcp_manager: MCPManager, memory_context: str = "") -> None:
        self._mcp = mcp_manager
        self._client = genai.Client(api_key=settings.gemini_api_key)

        tools = build_gemini_tools(mcp_manager.list_tools())
        config = genai_types.GenerateContentConfig(
            system_instruction=build_system_prompt(memory_context),
            tools=tools or None,
        )
        self._chat = self._client.chats.create(model=settings.model, config=config)

    async def send(self, message: str) -> str:
        """Send a user message, resolving any tool calls Gemini requests, and return the final reply."""
        response = self._chat.send_message(message)

        for _ in range(_MAX_TOOL_CALL_ROUNDS):
            function_calls = response.function_calls
            if not function_calls:
                break

            # Independent tool calls Gemini requested in the same turn (e.g.
            # research mode's Context7 + GitHub + Fetch + YouTube lookups)
            # run concurrently rather than one-by-one — same one-agent
            # architecture, just not needlessly serialized.
            response_parts = await asyncio.gather(
                *(self._execute_function_call(call) for call in function_calls)
            )
            response = self._chat.send_message(list(response_parts))

        return response.text or ""

    async def _execute_function_call(
        self, call: genai_types.FunctionCall
    ) -> genai_types.Part:
        assert call.name is not None
        logger.info("Tool call: %s(%s)", call.name, call.args)

        try:
            result = await self._mcp.call_tool(call.name, call.args or {})
            payload = {"error": result.text} if result.is_error else {"output": result.text}
        except MCPToolNotFoundError as exc:
            payload = {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001 — surface any tool failure back to the model
            logger.exception("Tool call %r failed", call.name)
            payload = {"error": f"Tool execution failed: {exc}"}

        return genai_types.Part.from_function_response(name=call.name, response=payload)
