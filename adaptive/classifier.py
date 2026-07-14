from __future__ import annotations

import asyncio
import json
import logging

from google import genai
from google.genai import types as genai_types

from adaptive.models import ClassificationResult, RawConversation
from config.settings import Settings

logger = logging.getLogger(__name__)

_BATCH_SIZE = 20
_SNIPPET_CHARS = 500  # enough to judge "is there signal here", not full extraction

_CLASSIFY_PROMPT = """\
For each numbered conversation snippet below, decide whether it contains \
any long-term information worth learning about the user — preferences, \
engineering decisions, workflows, reusable prompts, writing style, \
constraints, or coding conventions. One-off factual Q&A (math help, "what \
does X mean", unrelated trivia) does NOT count, even if long. Only mark \
YES if the user states or implies something that should influence future \
behavior.

{snippets}

Respond with a JSON array of {{"index": <int>, "worth_learning": <bool>}} \
for every conversation listed above, in order.
"""

_RESPONSE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "index": {"type": "integer"},
            "worth_learning": {"type": "boolean"},
        },
        "required": ["index", "worth_learning"],
    },
}


def _batches(items: list[RawConversation], size: int) -> list[list[RawConversation]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _build_snippets(batch: list[RawConversation]) -> str:
    lines = []
    for i, conversation in enumerate(batch):
        snippet = conversation.text[:_SNIPPET_CHARS].replace("\n", " ")
        lines.append(f"{i}. [{conversation.title}] {snippet}")
    return "\n\n".join(lines)


async def _classify_batch(
    client: genai.Client, model: str, batch: list[RawConversation]
) -> list[ClassificationResult]:
    prompt = _CLASSIFY_PROMPT.format(snippets=_build_snippets(batch))
    config = genai_types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=_RESPONSE_SCHEMA,
    )

    response = await asyncio.to_thread(
        client.models.generate_content, model=model, contents=prompt, config=config
    )

    try:
        results = json.loads(response.text)
    except Exception:
        logger.exception("Failed to parse classifier response for batch of %d", len(batch))
        # Fail open toward inclusion rather than silently dropping —
        # extraction will find nothing if there's truly no signal, but a
        # parse failure shouldn't silently erase conversations from
        # consideration.
        return [
            ClassificationResult(conversation_id=c.conversation_id, worth_learning=True)
            for c in batch
        ]

    by_index = {item["index"]: item["worth_learning"] for item in results}
    return [
        ClassificationResult(
            conversation_id=c.conversation_id,
            worth_learning=by_index.get(i, True),
        )
        for i, c in enumerate(batch)
    ]


async def classify_conversations(
    settings: Settings, conversations: list[RawConversation]
) -> dict[str, bool]:
    """Batched YES/NO classification: does this conversation contain
    anything worth learning? Returns conversation_id -> worth_learning.

    Batches run concurrently (asyncio.gather) so wall-clock time is
    dominated by one round-trip, not len(conversations)/batch_size
    sequential round-trips.
    """
    if not conversations:
        return {}

    client = genai.Client(api_key=settings.gemini_api_key)
    batches = _batches(conversations, _BATCH_SIZE)

    results_per_batch = await asyncio.gather(
        *(_classify_batch(client, settings.model, batch) for batch in batches)
    )

    verdicts: dict[str, bool] = {}
    for results in results_per_batch:
        for result in results:
            verdicts[result.conversation_id] = result.worth_learning
    return verdicts
