from __future__ import annotations

from mcp import Tool

IMAGE_TOOLS = [
    Tool(
        name="generate_image",
        description=(
            "Generate an image from a text prompt and save it locally. Returns the file path "
            "and metadata. Use this whenever asked to create, draw, or generate an image, picture, "
            "illustration, or artwork."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Description of the image to generate."},
                "model": {"type": "string", "description": "Generation model to use.", "default": "flux"},
                "width": {"type": "integer", "description": "Image width in pixels.", "default": 1024},
                "height": {"type": "integer", "description": "Image height in pixels.", "default": 1024},
            },
            "required": ["prompt"],
        },
    ),
]
