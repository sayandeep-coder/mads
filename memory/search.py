from __future__ import annotations

import re
from dataclasses import dataclass

from memory.store import Memory, list_all

_WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class SearchResult:
    memory: Memory
    score: float


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


def search_memory(query: str, category: str | None = None, limit: int = 10) -> list[SearchResult]:
    """Rank stored memories by relevance to a query using field-weighted keyword overlap.

    Deterministic and fully local — no embeddings or external services.
    Swappable for semantic search later without changing this function's
    signature or the tool surface built on top of it.
    """
    query_tokens = _tokenize(query)
    candidates = list_all(category=category)

    scored = [SearchResult(memory=m, score=_score(query_tokens, m)) for m in candidates]
    relevant = [r for r in scored if r.score > 0]
    relevant.sort(key=lambda r: r.score, reverse=True)

    return relevant[:limit]
