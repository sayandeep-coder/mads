from __future__ import annotations

from google.genai import types as genai_types
from mcp import Tool

# JSON Schema keys accepted by google.genai.types.Schema (its field aliases).
# MCP tool schemas are plain JSON Schema and may include keys Gemini's Schema
# doesn't model (e.g. $schema, exclusiveMinimum/Maximum) — those are dropped.
_SUPPORTED_SCHEMA_KEYS = {
    "additionalProperties", "defs", "ref", "anyOf", "default", "description",
    "enum", "example", "format", "items", "maxItems", "maxLength",
    "maxProperties", "maximum", "minItems", "minLength", "minProperties",
    "minimum", "nullable", "pattern", "properties", "propertyOrdering",
    "required", "title", "type",
}


def _clean_schema(schema: dict) -> dict:
    cleaned = {k: v for k, v in schema.items() if k in _SUPPORTED_SCHEMA_KEYS}

    if "properties" in cleaned and isinstance(cleaned["properties"], dict):
        cleaned["properties"] = {
            key: _clean_schema(value) if isinstance(value, dict) else value
            for key, value in cleaned["properties"].items()
        }

    if "items" in cleaned and isinstance(cleaned["items"], dict):
        cleaned["items"] = _clean_schema(cleaned["items"])

    return cleaned


def mcp_tool_to_function_declaration(tool: Tool) -> genai_types.FunctionDeclaration:
    """Translate an MCP tool definition into a Gemini function declaration."""
    parameters = _clean_schema(tool.inputSchema) if tool.inputSchema else {"type": "object", "properties": {}}

    return genai_types.FunctionDeclaration(
        name=tool.name,
        description=tool.description or "",
        parameters=parameters,
    )


def build_gemini_tools(tools: list[Tool]) -> list[genai_types.Tool]:
    """Wrap all MCP tool declarations into a single Gemini Tool for function calling."""
    if not tools:
        return []

    declarations = [mcp_tool_to_function_declaration(tool) for tool in tools]
    return [genai_types.Tool(function_declarations=declarations)]
