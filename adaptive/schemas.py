from __future__ import annotations

from mcp import Tool

# Import itself (adaptive.pipeline.run_import) is deliberately NOT exposed
# here — it's a slow, cost-incurring bulk job that must stay under
# explicit manual control via the CLI's `import chatgpt <path>` command,
# not something Gemini can trigger as a side effect of interpreting a
# request. Everything below is cheap, single-item, and safe for the agent
# to call on its own judgment.
ADAPTIVE_TOOLS = [
    Tool(
        name="list_pending_candidates",
        description=(
            "List learned facts (identity/preferences/decisions/workflows/constraints) waiting for "
            "Sayan's approval, from a ChatGPT history import. Sorted by confidence, highest first."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["preference", "decision", "workflow", "constraint", "identity"],
                    "description": "Filter by category; omit for all.",
                },
            },
        },
    ),
    Tool(
        name="approve_candidate",
        description=(
            "Approve a pending learned fact, moving it into the Adaptive Profile — from then on it "
            "influences how Mads responds. Only call this when Sayan explicitly confirms he wants a "
            "specific candidate approved; never approve on his behalf without him seeing the statement."
        ),
        inputSchema={
            "type": "object",
            "properties": {"candidate_id": {"type": "integer", "description": "From list_pending_candidates."}},
            "required": ["candidate_id"],
        },
    ),
    Tool(
        name="reject_candidate",
        description="Reject a pending learned fact — it will not enter the Adaptive Profile.",
        inputSchema={
            "type": "object",
            "properties": {"candidate_id": {"type": "integer", "description": "From list_pending_candidates."}},
            "required": ["candidate_id"],
        },
    ),
    Tool(
        name="list_adaptive_profile",
        description=(
            "List facts already approved into the Adaptive Profile — what Mads has actually learned "
            "about Sayan's identity/contact info, preferences, decisions, workflows, and constraints "
            "so far. Check this (or search_memory, which also covers the Adaptive Profile) before "
            "asking Sayan to repeat any personal or contact details."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["preference", "decision", "workflow", "constraint", "identity"],
                    "description": "Filter by category; omit for all.",
                },
            },
        },
    ),
]
