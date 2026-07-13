from __future__ import annotations

import asyncio
import logging
import mimetypes
from contextlib import AsyncExitStack
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp import Tool
from PIL import Image

from config.settings import Settings
from mcp_servers.manager import ToolCallResult
from mcp_servers.servers.image._backend import ImageBackend
from mcp_servers.servers.image._pollinations import PollinationsBackend, PollinationsError
from mcp_servers.servers.image._schemas import IMAGE_TOOLS

logger = logging.getLogger(__name__)

_DEFAULT_SAVE_DIR = Path.home() / "Pictures" / "Mads"


def _unique_path(directory: Path, extension: str) -> Path:
    """Build a timestamped filename, disambiguating with a numeric suffix if it already exists.

    Never overwrites an existing image — if two images are generated within
    the same second, a suffix is appended rather than clobbering the first.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = directory / f"image_{timestamp}{extension}"

    suffix = 1
    while candidate.exists():
        candidate = directory / f"image_{timestamp}_{suffix}{extension}"
        suffix += 1

    return candidate


class ImageProvider:
    """Image generation, backed by a pluggable ImageBackend (Pollinations today).

    generate_image() is the only public tool regardless of backend — adding
    OpenAI, Gemini, Hugging Face, or Stability AI later means writing a new
    ImageBackend and swapping it in here, not changing this class's public
    surface or the agent's view of it.
    """

    def __init__(self, settings: Settings, backend: ImageBackend | None = None, save_dir: Path | None = None) -> None:
        self._settings = settings
        self._backend = backend or PollinationsBackend()
        self._save_dir = save_dir or _DEFAULT_SAVE_DIR

    @property
    def name(self) -> str:
        return "image"

    @staticmethod
    def is_available(settings: Settings) -> bool:
        return True  # Pollinations requires no credentials

    async def connect(self, exit_stack: AsyncExitStack) -> None:
        pass

    def list_tools(self) -> list[Tool]:
        return list(IMAGE_TOOLS)

    async def call_tool(self, name: str, arguments: dict) -> ToolCallResult:
        if name != "generate_image":
            return ToolCallResult(text=f"Unknown image tool: {name!r}", is_error=True)

        try:
            result = await asyncio.to_thread(self._generate_image, **arguments)
        except Exception as exc:  # noqa: BLE001 — surface any failure back to the model
            logger.exception("Image generation failed")
            result = {"success": False, "error": "unexpected_error", "message": str(exc)}

        return ToolCallResult(text=str(result), is_error=not result.get("success", False))

    def _generate_image(
        self, prompt: str, model: str = "flux", width: int = 1024, height: int = 1024
    ) -> dict[str, Any]:
        try:
            image = self._backend.generate(prompt, model, width, height)
        except PollinationsError as exc:
            return {"success": False, "error": "generation_failed", "message": str(exc)}

        self._save_dir.mkdir(parents=True, exist_ok=True)
        extension = mimetypes.guess_extension(image.content_type) or ".jpg"
        path = _unique_path(self._save_dir, extension)
        path.write_bytes(image.data)

        # Report the image's real, saved dimensions rather than echoing back
        # the request — backends (Pollinations included) don't always honor
        # the requested width/height exactly.
        with Image.open(path) as saved_image:
            actual_width, actual_height = saved_image.size

        return {
            "success": True,
            "path": str(path),
            "filename": path.name,
            "width": actual_width,
            "height": actual_height,
            "provider": self._backend.name,
            "model": model,
        }
