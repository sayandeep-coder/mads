from __future__ import annotations

from urllib.parse import quote

import httpx

from mcp_servers.servers.image._backend import GeneratedImage

_BASE_URL = "https://image.pollinations.ai/prompt"
_TIMEOUT_SECONDS = 60.0


class PollinationsError(RuntimeError):
    """Raised when the Pollinations API fails, times out, or returns something unusable."""


class PollinationsBackend:
    """Image generation via Pollinations.AI's public HTTP API — no API key required.

    Reference: https://github.com/pollinations/pollinations/blob/master/APIDOCS.md
    Endpoint: GET https://image.pollinations.ai/prompt/{prompt}?model=&width=&height=
    """

    @property
    def name(self) -> str:
        return "pollinations"

    def generate(self, prompt: str, model: str, width: int, height: int) -> GeneratedImage:
        if not prompt.strip():
            raise PollinationsError("Prompt must not be empty")

        url = f"{_BASE_URL}/{quote(prompt)}"
        params = {"model": model, "width": width, "height": height, "nologo": "true"}

        try:
            response = httpx.get(url, params=params, timeout=_TIMEOUT_SECONDS, follow_redirects=True)
        except httpx.TimeoutException as exc:
            raise PollinationsError(f"Request to Pollinations timed out after {_TIMEOUT_SECONDS}s") from exc
        except httpx.RequestError as exc:
            raise PollinationsError(f"Network error contacting Pollinations: {exc}") from exc

        if response.status_code != 200:
            raise PollinationsError(f"Pollinations returned HTTP {response.status_code}: {response.text[:200]}")

        content_type = response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        if not content_type.startswith("image/"):
            raise PollinationsError(
                f"Pollinations did not return an image (content-type: {content_type!r}); "
                "the prompt may have been rejected."
            )

        return GeneratedImage(data=response.content, content_type=content_type)
