from __future__ import annotations

from dataclasses import dataclass

from adaptive.models import FactCategory
from memory.store import Memory, _VALID_CATEGORIES
from server.db.connection import get_connection
from server.embeddings import embed_text

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


def search_memory(query: str, category: str | None = None, limit: int = 10) -> list[SearchResult]:
    """Rank stored memories by semantic similarity to a query.

    Embeds the query (gemini-embedding-001) and ranks both memory.sqlite3's
    successor — the `memories` table — and the Adaptive Profile's
    `adaptive_approved_facts` by cosine distance via pgvector's `<=>`
    operator, merging the two into one relevance-ordered list. Replaces
    the original keyword-overlap scorer: "my partner's name" now finds a
    memory phrased as "spouse is named ...", which word matching couldn't.
    """
    query_embedding = embed_text(query, task_type="RETRIEVAL_QUERY")

    results: list[SearchResult] = []

    with get_connection() as conn, conn.cursor() as cur:
        if category is None or category in _VALID_CATEGORIES:
            if category is not None:
                cur.execute(
                    """
                    SELECT *, 1 - (embedding <=> %s::vector) AS similarity FROM memories
                    WHERE embedding IS NOT NULL AND category = %s
                    ORDER BY embedding <=> %s::vector LIMIT %s
                    """,
                    (query_embedding, category, query_embedding, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT *, 1 - (embedding <=> %s::vector) AS similarity FROM memories
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> %s::vector LIMIT %s
                    """,
                    (query_embedding, query_embedding, limit),
                )
            for row in cur.fetchall():
                tags = [t for t in row["tags"].split(",") if t]
                memory = Memory(
                    id=row["id"], category=row["category"], content=row["content"],
                    tags=tags, created_at=row["created_at"], updated_at=row["updated_at"],
                )
                results.append(SearchResult(memory=memory, score=row["similarity"], source="memory"))

        adaptive_category_ok = category is None
        if category is not None:
            try:
                FactCategory(category)
                adaptive_category_ok = True
            except ValueError:
                pass  # Not one of the adaptive categories (e.g. "person") — nothing to contribute.

        if adaptive_category_ok:
            if category is not None:
                cur.execute(
                    """
                    SELECT *, 1 - (embedding <=> %s::vector) AS similarity FROM adaptive_approved_facts
                    WHERE embedding IS NOT NULL AND category = %s
                    ORDER BY embedding <=> %s::vector LIMIT %s
                    """,
                    (query_embedding, category, query_embedding, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT *, 1 - (embedding <=> %s::vector) AS similarity FROM adaptive_approved_facts
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> %s::vector LIMIT %s
                    """,
                    (query_embedding, query_embedding, limit),
                )
            for row in cur.fetchall():
                memory = Memory(
                    id=_ADAPTIVE_ID_OFFSET + row["id"], category=row["category"], content=row["statement"],
                    tags=[], created_at=row["approved_at"].isoformat(), updated_at=row["approved_at"].isoformat(),
                )
                results.append(SearchResult(memory=memory, score=row["similarity"], source="adaptive_profile"))

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:limit]
