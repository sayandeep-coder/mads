from __future__ import annotations

import asyncio
import json
import logging

from google import genai
from google.genai import types as genai_types

from adaptive.models import Candidate, CompressedConversation, FactCategory
from config.settings import Settings

logger = logging.getLogger(__name__)

_BATCH_SIZE = 10  # smaller than the classifier batch — each conversation here can be up to ~1500 chars

_EXTRACT_PROMPT = """\
Below are {count} conversations between a user and an AI assistant. For \
each one, extract any durable, long-term facts about the user that should \
influence how an AI assistant behaves with them in the future. Extract \
into exactly these five categories:

- preference: things the user likes/dislikes, favors, or wants by default \
(language, tone, formatting, tools, frameworks).
- decision: a specific choice the user made and is likely to stick with \
(e.g. "chose Postgres over MySQL for project X").
- workflow: a recurring process or habit in how the user works (e.g. \
"reviews PRs before merging", "writes tests first").
- constraint: a hard rule the user has stated the assistant should follow \
(e.g. "never use multi-agent architectures", "always use conventional \
commits", "prefer official documentation over blog posts").
- identity: stable factual/biographical/contact information about the user \
— full name, roll number or student/employee id, institution or employer \
name, department, degree/program, address, phone number, email address, or \
similar. Extract these whenever the user states them, even if they look \
like one-off details being given for a specific task (e.g. filling in a \
form or letter) — these are exactly the facts worth remembering so the \
user never has to repeat them.

Only extract things that are durable and would still be true/relevant \
beyond this one conversation. Do not extract one-off facts, trivia, or \
anything already scoped to a single task — except identity information, \
which should always be extracted when present regardless of the task it \
appeared in. If a conversation has nothing worth extracting, contribute \
nothing for it. Write each statement as a clear, standalone sentence about \
the user (not "the user said X" — just state the fact directly, e.g. \
"Prefers Markdown for documentation" or "Email address is x@y.com").

{conversations}

Respond with a JSON array of objects: \
{{"conversation_index": <int>, "category": "preference"|"decision"|"workflow"|"constraint"|"identity", "statement": <string>}}. \
Omit conversations that yield nothing.
"""

_RESPONSE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "conversation_index": {"type": "integer"},
            "category": {
                "type": "string",
                "enum": ["preference", "decision", "workflow", "constraint", "identity"],
            },
            "statement": {"type": "string"},
        },
        "required": ["conversation_index", "category", "statement"],
    },
}


def _batches(
    items: list[CompressedConversation], size: int
) -> list[list[CompressedConversation]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _build_conversations_block(batch: list[CompressedConversation]) -> str:
    blocks = []
    for i, conversation in enumerate(batch):
        blocks.append(f"--- Conversation {i}: {conversation.title} ---\n{conversation.text}")
    return "\n\n".join(blocks)


async def _extract_batch(
    client: genai.Client, model: str, batch: list[CompressedConversation]
) -> list[Candidate]:
    prompt = _EXTRACT_PROMPT.format(
        count=len(batch), conversations=_build_conversations_block(batch)
    )
    config = genai_types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=_RESPONSE_SCHEMA,
    )

    response = await asyncio.to_thread(
        client.models.generate_content, model=model, contents=prompt, config=config
    )

    try:
        raw_items = json.loads(response.text)
    except Exception:
        logger.exception("Failed to parse extractor response for batch of %d", len(batch))
        return []

    candidates: list[Candidate] = []
    for item in raw_items:
        index = item.get("conversation_index")
        if index is None or not (0 <= index < len(batch)):
            continue
        conversation = batch[index]
        try:
            category = FactCategory(item["category"])
        except (KeyError, ValueError):
            continue
        statement = (item.get("statement") or "").strip()
        if not statement:
            continue

        candidates.append(
            Candidate(
                category=category,
                statement=statement,
                source_conversation_id=conversation.conversation_id,
                source_title=conversation.title,
                source_create_time=conversation.create_time,
            )
        )

    return candidates


async def extract_candidates(
    settings: Settings, conversations: list[CompressedConversation]
) -> list[Candidate]:
    """Batched extraction of Preference/Decision/Workflow/Constraint/Identity
    candidates. Batches run concurrently, same pattern as the classifier."""
    if not conversations:
        return []

    client = genai.Client(api_key=settings.gemini_api_key)
    batches = _batches(conversations, _BATCH_SIZE)

    results_per_batch = await asyncio.gather(
        *(_extract_batch(client, settings.model, batch) for batch in batches)
    )

    candidates: list[Candidate] = []
    for batch_results in results_per_batch:
        candidates.extend(batch_results)
    return candidates
