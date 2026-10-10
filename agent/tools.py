from __future__ import annotations

import logging

from google.genai import types as genai_types
from mcp import Tool

logger = logging.getLogger(__name__)

# JSON Schema keys accepted by google.genai.types.Schema (its field aliases).
# MCP tool schemas are plain JSON Schema and may include keys Gemini's Schema
# doesn't model (e.g. $schema, exclusiveMinimum/Maximum) — those are dropped.
#
# "additionalProperties" is deliberately NOT in this set, despite
# google.genai.types.Schema having a field for it: the SDK's local Pydantic
# model accepts it fine (so a bad schema here doesn't get caught by
# mcp_tools_to_function_declarations's try/except, which only guards that
# local conversion step), but Gemini's actual function-calling API rejects
# it outright at request time — "Unknown name additional_properties...
# Cannot find field" — which took down an entire chat turn (a 500 mid-
# stream, not a skippable single tool) the first time a commerce
# connector's tool schema used it. Confirmed against the live API, not a
# guess: this key must be dropped before it ever reaches the model.
_SUPPORTED_SCHEMA_KEYS = {
    "defs", "ref", "anyOf", "default", "description",
    "enum", "example", "format", "items", "maxItems", "maxLength",
    "maxProperties", "maximum", "minItems", "minLength", "minProperties",
    "minimum", "nullable", "pattern", "properties", "propertyOrdering",
    "required", "title", "type",
}


def _clean_schema(schema: dict) -> dict:
    cleaned = {k: v for k, v in schema.items() if k in _SUPPORTED_SCHEMA_KEYS}

    # "required" only means anything on an object schema ("only allowed for
    # OBJECT type" is literally the API's own rejection message) — a real
    # external tool schema has shipped `required` on a branch with no
    # `type: object` (or no `type` at all post-cleaning). Rather than try
    # to infer whether a given branch "counts" as an object, drop `required`
    # wherever the schema isn't explicitly typed as one; Gemini still
    # enforces nothing is silently optional-vs-required beyond what the
    # model infers from `description`, but that's a usability tradeoff, not
    # a correctness one — far better than crashing the whole request.
    if str(cleaned.get("type", "")).lower() != "object" and "required" in cleaned:
        del cleaned["required"]

    # Gemini's Schema.enum is strictly list[str] — plain JSON Schema has no
    # such restriction, and a real external server has already sent an
    # integer enum in practice (Swiggy's `vegFilter: {type: integer, enum:
    # [0, 1]}`). Coercing to str keeps the tool usable instead of rejecting
    # the whole declaration; the model only ever needs to pass the value
    # back verbatim; it doesn't need to know it was "really" an int.
    if "enum" in cleaned and isinstance(cleaned["enum"], list):
        cleaned["enum"] = [str(v) for v in cleaned["enum"]]

    if "properties" in cleaned and isinstance(cleaned["properties"], dict):
        cleaned["properties"] = {
            key: _clean_schema(value) if isinstance(value, dict) else value
            for key, value in cleaned["properties"].items()
        }

    if "items" in cleaned and isinstance(cleaned["items"], dict):
        cleaned["items"] = _clean_schema(cleaned["items"])

    # Previously missing entirely: anyOf's value is a LIST of sub-schemas,
    # not a single dict, so it fell through every check above untouched —
    # each branch's own stray/unsupported keys (like the `required`-on-a-
    # non-object case above) reached the live API uncleaned. This is
    # exactly what broke a real request from a connected commerce
    # connector's tool schema.
    if "anyOf" in cleaned and isinstance(cleaned["anyOf"], list):
        cleaned["anyOf"] = [
            _clean_schema(branch) if isinstance(branch, dict) else branch
            for branch in cleaned["anyOf"]
        ]

    return cleaned


def mcp_tool_to_function_declaration(tool: Tool) -> genai_types.FunctionDeclaration:
    """Translate an MCP tool definition into a Gemini function declaration."""
    parameters = _clean_schema(tool.inputSchema) if tool.inputSchema else {"type": "object", "properties": {}}

    return genai_types.FunctionDeclaration(
        name=tool.name,
        description=tool.description or "",
        parameters=parameters,
    )


def mcp_tools_to_function_declarations(tools: list[Tool]) -> list[genai_types.FunctionDeclaration]:
    """Convert every tool, skipping (and logging) any one whose schema still
    doesn't fit Gemini's stricter JSON Schema subset after _clean_schema —
    an external MCP server we don't control (a commerce connector, say) can
    ship something else _clean_schema doesn't yet normalize; one such tool
    shouldn't take down every other tool from that same provider, the same
    way one failed provider in MCPManager.connect doesn't take down the rest.
    """
    declarations = []
    for tool in tools:
        try:
            declarations.append(mcp_tool_to_function_declaration(tool))
        except Exception:
            logger.exception("Skipping tool %r — its schema didn't convert to a Gemini FunctionDeclaration", tool.name)
    return declarations


def build_gemini_tools(tools: list[Tool]) -> list[genai_types.Tool]:
    """Wrap all MCP tool declarations into a single Gemini Tool for function calling."""
    if not tools:
        return []

    declarations = mcp_tools_to_function_declarations(tools)
    return [genai_types.Tool(function_declarations=declarations)] if declarations else []
