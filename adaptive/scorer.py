from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone

from google import genai
from google.genai import types as genai_types

from adaptive.models import Candidate, FactCategory, ScoredCandidate
from config.settings import Settings

logger = logging.getLogger(__name__)

_CLUSTER_PROMPT = """\
Below is a numbered list of statements about a user, all in the same \
category ({category}). Group statements that express the same underlying \
fact (even if worded differently) into clusters. Also flag any pair of \
clusters that directly contradict each other (e.g. "prefers Vue" vs \
"prefers React" as defaults would contradict).

{statements}

Respond with a JSON object:
{{
  "clusters": [
    {{"indices": [<int>, ...], "representative_statement": <string>}}
  ],
  "contradictions": [[<cluster_index>, <cluster_index>], ...]
}}
Every input index must appear in exactly one cluster. representative_statement \
should be the clearest phrasing among the group, written as a standalone \
sentence about the user.
"""

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "clusters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "indices": {"type": "array", "items": {"type": "integer"}},
                    "representative_statement": {"type": "string"},
                },
                "required": ["indices", "representative_statement"],
            },
        },
        "contradictions": {
            "type": "array",
            "items": {"type": "array", "items": {"type": "integer"}},
        },
    },
    "required": ["clusters"],
}

# Confidence weighting: recurrence dominates (a fact stated once is weak
# evidence), consistency and recency are secondary adjustments layered on
# top rather than independent multipliers, matching "slightly weighted"
# recency from the design brief.
_RECURRENCE_SATURATION = 5  # recurrence contribution saturates around 5 mentions
_CONTRADICTION_PENALTY = 0.35
_RECENCY_HALF_LIFE_DAYS = 180
_RECENCY_MAX_BOOST = 0.15


def _recurrence_score(count: int) -> float:
    return min(count / _RECURRENCE_SATURATION, 1.0)


def _recency_boost(latest: datetime | None) -> float:
    if latest is None:
        return 0.0
    now = datetime.now(timezone.utc)
    age_days = max((now - latest).days, 0)
    decay = 0.5 ** (age_days / _RECENCY_HALF_LIFE_DAYS)
    return _RECENCY_MAX_BOOST * decay


async def _cluster_category(
    client: genai.Client, model: str, category: FactCategory, candidates: list[Candidate]
) -> list[ScoredCandidate]:
    if not candidates:
        return []

    if len(candidates) == 1:
        # No clustering call needed for a single candidate — nothing to group.
        c = candidates[0]
        return [
            ScoredCandidate(
                category=category,
                statement=c.statement,
                confidence=round(_recurrence_score(1) + _recency_boost(c.source_create_time), 3),
                recurrence=1,
                source_conversation_ids=[c.source_conversation_id],
                latest_source_time=c.source_create_time,
            )
        ]

    statements_block = "\n".join(f"{i}. {c.statement}" for i, c in enumerate(candidates))
    prompt = _CLUSTER_PROMPT.format(category=category.value, statements=statements_block)
    config = genai_types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=_RESPONSE_SCHEMA,
    )

    response = await asyncio.to_thread(
        client.models.generate_content, model=model, contents=prompt, config=config
    )

    try:
        parsed = json.loads(response.text)
        clusters_raw = parsed["clusters"]
        contradiction_pairs = parsed.get("contradictions", [])
    except Exception:
        logger.exception("Failed to parse scorer response for %s (%d candidates)", category.value, len(candidates))
        # Fail open: treat every candidate as its own singleton cluster
        # rather than losing them entirely.
        clusters_raw = [{"indices": [i], "representative_statement": c.statement} for i, c in enumerate(candidates)]
        contradiction_pairs = []

    contradicted_clusters: dict[int, list[int]] = defaultdict(list)
    for pair in contradiction_pairs:
        if len(pair) != 2:
            continue
        a, b = pair
        contradicted_clusters[a].append(b)
        contradicted_clusters[b].append(a)

    scored: list[ScoredCandidate] = []
    for cluster_index, cluster in enumerate(clusters_raw):
        indices = [i for i in cluster["indices"] if 0 <= i < len(candidates)]
        if not indices:
            continue
        members = [candidates[i] for i in indices]

        source_ids = [m.source_conversation_id for m in members]
        times = [m.source_create_time for m in members if m.source_create_time is not None]
        latest = max(times) if times else None

        recurrence = len(members)
        base = _recurrence_score(recurrence)
        recency = _recency_boost(latest)
        confidence = base + recency

        contradicting_cluster_indices = contradicted_clusters.get(cluster_index, [])
        contradicts_statements = [
            clusters_raw[ci]["representative_statement"]
            for ci in contradicting_cluster_indices
            if 0 <= ci < len(clusters_raw)
        ]
        if contradicting_cluster_indices:
            confidence -= _CONTRADICTION_PENALTY

        confidence = max(0.0, min(1.0, confidence))

        scored.append(
            ScoredCandidate(
                category=category,
                statement=cluster["representative_statement"],
                confidence=round(confidence, 3),
                recurrence=recurrence,
                source_conversation_ids=source_ids,
                contradicts=contradicts_statements,
                latest_source_time=latest,
            )
        )

    return scored


async def score_candidates(settings: Settings, candidates: list[Candidate]) -> list[ScoredCandidate]:
    """Cluster near-duplicate candidates per category, then score each
    cluster's confidence from recurrence, consistency (via clustering
    itself — inconsistent restatements won't cluster together), detected
    contradictions, and a slight recency boost.
    """
    if not candidates:
        return []

    by_category: dict[FactCategory, list[Candidate]] = defaultdict(list)
    for c in candidates:
        by_category[c.category].append(c)

    client = genai.Client(api_key=settings.gemini_api_key)

    results_per_category = await asyncio.gather(
        *(
            _cluster_category(client, settings.model, category, items)
            for category, items in by_category.items()
        )
    )

    scored: list[ScoredCandidate] = []
    for results in results_per_category:
        scored.extend(results)

    scored.sort(key=lambda s: s.confidence, reverse=True)
    return scored
