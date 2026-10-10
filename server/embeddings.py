"""Text embeddings for semantic memory search — see memory/search.py.

gemini-embedding-001, truncated to 768 dimensions (the model natively
returns up to 3072; 768 is the documented sweet spot for retrieval quality
per dollar/storage, and matches the `vector(768)` columns in schema.sql).

Cosine distance (pgvector's `<=>` operator) is scale-invariant, so the
fact that a truncated embedding isn't unit-length (confirmed empirically —
Google only auto-normalizes the full 3072-dim output) doesn't need
correcting here; only a dot-product or L2 comparison would require it.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(override=False)

_DIMENSIONS = 768
_MODEL = "gemini-embedding-001"

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def embed_text(text: str, *, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float]:
    """Embed one piece of text. task_type matters for retrieval quality:
    use the default when storing a memory/fact, and "RETRIEVAL_QUERY" when
    embedding a search query — Gemini's embedding model is trained to
    treat the two asymmetrically (a query and the document that answers it
    aren't expected to look alike token-for-token).
    """
    response = _get_client().models.embed_content(
        model=_MODEL,
        contents=text,
        config=types.EmbedContentConfig(output_dimensionality=_DIMENSIONS, task_type=task_type),
    )
    return list(response.embeddings[0].values)
