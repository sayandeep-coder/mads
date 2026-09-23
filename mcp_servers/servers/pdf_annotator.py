import logging
import asyncio
import urllib.parse
from pathlib import Path
from typing import Any
import fitz

from mcp import Tool
from contextlib import AsyncExitStack

from config.settings import Settings
from mcp_servers.manager import ToolCallResult

logger = logging.getLogger(__name__)

_TOOLS = [
    Tool(
        name="annotate_pdf",
        description="Annotate a PDF file with red circles and text.",
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path to the PDF file to annotate."},
                "annotations": {
                    "type": "array",
                    "description": "List of annotations to apply.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "page_number": {"type": "integer", "description": "1-indexed page number."},
                            "type": {"type": "string", "enum": ["circle_text", "add_text"], "description": "Type of annotation."},
                            "target_text": {"type": "string", "description": "Exact text to circle or place text near. Optional if coordinates are provided."},
                            "annotation_text": {"type": "string", "description": "Text to add."},
                            "color": {"type": "string", "description": "Color name, e.g. 'red'", "default": "red"},
                            "position": {"type": "string", "enum": ["right_of_circle", "left_of_circle", "above_circle", "below_circle"], "description": "Where to place the text relative to the target."}
                        },
                        "required": ["page_number", "type", "annotation_text"]
                    }
                }
            },
            "required": ["file_path", "annotations"]
        }
    )
]

def get_color(color_name: str) -> tuple[float, float, float]:
    colors = {
        "red": (1.0, 0.0, 0.0),
        "blue": (0.0, 0.0, 1.0),
        "green": (0.0, 1.0, 0.0),
        "black": (0.0, 0.0, 0.0)
    }
    return colors.get(color_name.lower(), (1.0, 0.0, 0.0))

class PdfAnnotatorProvider:
    def __init__(self, settings: Settings):
        self._settings = settings

    @property
    def name(self) -> str:
        return "pdf_annotator"

    @classmethod
    def is_available(cls, settings: Settings) -> bool:
        return True

    async def connect(self, exit_stack: AsyncExitStack) -> None:
        pass

    def list_tools(self) -> list[Tool]:
        return list(_TOOLS)

    async def call_tool(self, name: str, arguments: dict) -> ToolCallResult:
        if name == "annotate_pdf":
            return await asyncio.to_thread(self._annotate_pdf, arguments["file_path"], arguments.get("annotations", []))
        return ToolCallResult(text=f"Unknown tool: {name}", is_error=True)

    def _annotate_pdf(self, file_path: str, annotations: list[dict]) -> ToolCallResult:
        path = Path(file_path)
        if not path.exists():
            return ToolCallResult(text=f"File not found: {file_path}", is_error=True)

        try:
            doc = fitz.open(file_path)
            
            for ann in annotations:
                page_idx = ann.get("page_number", 1) - 1
                if page_idx < 0 or page_idx >= len(doc):
                    continue
                
                page = doc[page_idx]
                target_text = ann.get("target_text")
                ann_type = ann.get("type")
                ann_text = ann.get("annotation_text", "")
                color = get_color(ann.get("color", "red"))
                position = ann.get("position", "right_of_circle")
                
                if not target_text:
                    # Fallback to absolute positioning if no target text
                    page.insert_text((50, 50), ann_text, color=color, fontsize=12)
                    continue
                
                # Search for target text
                text_instances = page.search_for(target_text)
                if not text_instances:
                    continue # Could not find text to annotate
                
                # Take the first instance found
                rect = text_instances[0]
                
                if ann_type == "circle_text":
                    # Draw a red oval around the bounding box
                    # Expand rect slightly to make oval look better
                    expanded_rect = fitz.Rect(rect.x0 - 2, rect.y0 - 2, rect.x1 + 2, rect.y1 + 2)
                    page.draw_oval(expanded_rect, color=color, width=1.5)
                
                # Add text
                if ann_text:
                    if position == "right_of_circle":
                        point = fitz.Point(rect.x1 + 10, rect.y1)
                    elif position == "left_of_circle":
                        point = fitz.Point(rect.x0 - 50, rect.y1)
                    elif position == "above_circle":
                        point = fitz.Point(rect.x0, rect.y0 - 10)
                    elif position == "below_circle":
                        point = fitz.Point(rect.x0, rect.y1 + 15)
                    else:
                        point = fitz.Point(rect.x1 + 10, rect.y1)
                        
                    page.insert_text(point, ann_text, color=color, fontsize=10)
                    
            out_path = path.with_name(f"{path.stem}_annotated.pdf")
            doc.save(out_path)
            doc.close()
            
            download_url = f"/api/files?path={urllib.parse.quote(out_path.absolute().as_posix())}"
            return ToolCallResult(
                text=f"Successfully annotated PDF.\n\n[Download Annotated PDF]({download_url})",
                is_error=False
            )
            
        except Exception as e:
            logger.exception("Failed to annotate PDF")
            return ToolCallResult(text=f"Error annotating PDF: {e}", is_error=True)
