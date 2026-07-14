from __future__ import annotations

import re
from dataclasses import dataclass

from memory.store import InvalidCategoryError, Memory, list_all

_WORD_RE = re.compile(r"[a-z0-9]+")

# The Adaptive Profile (adaptive/profile.py) is a separate store — facts
# extracted from imported history and approved by the user — but from the
# agent's perspective "search my memory for X" should have one answer
# regardless of which store a fact happens to live in. Approved facts are
# normalized into Memory-shaped results here so search_memory has a single
# output contract; category names are kept as-is (identity/preference/
# decision/workflow/constraint) so results are distinguishable from
# memory.sqlite3's own categories (preference/project/decision/person).
_ADAPTIVE_ID_OFFSET = 1_000_000


@dataclass(frozen=True, slots=True)
class SearchResult:
    memory: Memory
    score: float
    source: str = "memory"  # "memory" or "adaptive_profile"


def _tokenize(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _score(query_tokens: set[str], memory: Memory) -> float:
    if not query_tokens:
        return 0.0

    content_tokens = _tokenize(memory.content)
    tag_tokens = _tokenize(" ".join(memory.tags))
    category_tokens = _tokenize(memory.category)

    # Field-weighted overlap: tags and category are short, deliberate labels,
    # so a hit there is a stronger signal than a hit buried in free-text content.
    content_hits = len(query_tokens & content_tokens)
    tag_hits = len(query_tokens & tag_tokens)
    category_hits = len(query_tokens & category_tokens)

    return content_hits * 1.0 + tag_hits * 2.0 + category_hits * 1.5


def _adaptive_profile_as_memories(category: str | None) -> list[Memory]:
    # Local import: memory/ has no other dependency on adaptive/, and this
    # keeps the import lazy in case the adaptive package is ever optional.
    from adaptive.profile import AdaptiveProfile
    from adaptive.models import FactCategory

    adaptive_category = None
    if category is not None:
        try:
            adaptive_category = FactCategory(category)
        except ValueError:
            # Not one of the adaptive categories (e.g. "person") — the
            # Adaptive Profile has nothing to contribute for this filter.
            return []

    facts = AdaptiveProfile().list_approved(category=adaptive_category)
    return [
        Memory(
            id=_ADAPTIVE_ID_OFFSET + fact.id,
            category=fact.category.value,
            content=fact.statement,
            tags=[],
            created_at=fact.approved_at.isoformat(),
            updated_at=fact.approved_at.isoformat(),
        )
        for fact in facts
    ]


def search_memory(query: str, category: str | None = None, limit: int = 10) -> list[SearchResult]:
    """Rank stored memories by relevance to a query using field-weighted keyword overlap.

    Searches both memory.sqlite3 (facts told directly in conversation) and
    the Adaptive Profile (facts approved from imported history) — the
    agent shouldn't need to know or care which store a given fact lives in.

    Deterministic and fully local — no embeddings or external services.
    Swappable for semantic search later without changing this function's
    signature or the tool surface built on top of it.
    """
    query_tokens = _tokenize(query)

    try:
        memory_candidates = list_all(category=category)
    except InvalidCategoryError:
        # `category` may be valid for the Adaptive Profile's category set
        # (e.g. "constraint", "identity") but not memory.sqlite3's — that's
        # not an error, it just means memory.sqlite3 has nothing to
        # contribute for this filter.
        memory_candidates = []

    adaptive_candidates = _adaptive_profile_as_memories(category)

    scored = [
        SearchResult(memory=m, score=_score(query_tokens, m), source="memory")
        for m in memory_candidates
    ] + [
        SearchResult(memory=m, score=_score(query_tokens, m), source="adaptive_profile")
        for m in adaptive_candidates
    ]
    relevant = [r for r in scored if r.score > 0]
    relevant.sort(key=lambda r: r.score, reverse=True)

    return relevant[:limit]
