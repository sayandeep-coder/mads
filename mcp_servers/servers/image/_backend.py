from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class GeneratedImage:
    """Raw bytes and detected format from an image generation backend.

    content_type drives the saved file's extension — never assumed from
    the request, since a backend's actual output format may not match
    what was requested (e.g. Pollinations always returns JPEG regardless
    of query parameters).
    """

    data: bytes
    content_type: str


class ImageBackend(Protocol):
    """A pluggable image generation backend (Pollinations today; OpenAI,
    Gemini, Hugging Face, or Stability AI later — ImageProvider's public
    generate_image() tool never changes regardless of which backend answers it.
    """

    @property
    def name(self) -> str:
        """Short identifier returned in generate_image()'s metadata, e.g. 'pollinations'."""
        ...

    def generate(self, prompt: str, model: str, width: int, height: int) -> GeneratedImage:
        """Generate an image and return its raw bytes plus detected content type."""
        ...
