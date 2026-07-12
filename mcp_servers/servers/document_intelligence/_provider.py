from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import Tool

from config.settings import Settings
from mcp_servers.manager import ToolCallResult
from mcp_servers.servers.document_intelligence import _compare, _docx, _pdf, _pdf_writer, _xlsx
from mcp_servers.servers.document_intelligence._paths import resolve_allowed_path, resolve_allowed_write_path
from mcp_servers.servers.document_intelligence._schemas import DOCUMENT_TOOLS

logger = logging.getLogger(__name__)

_PDF_MAGIC = b"%PDF-"


class PdfGenerationError(RuntimeError):
    """Raised when a generated PDF fails validation (doesn't start with the PDF magic bytes)."""


def _read_text_for_compare(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _pdf.read_pdf(path)["text"]
    if suffix == ".docx":
        return _docx.read_docx(path)["text"]
    return path.read_text(encoding="utf-8", errors="replace")


class DocumentIntelligenceProvider:
    """Local document reading/extraction: PDF, DOCX, XLSX.

    Pure extraction only — this module never summarizes or reasons about
    content itself. It hands clean text/table data back to the agent, and
    Gemini (the one brain in Mads) does the actual summarizing, comparing,
    and note-generation from that extracted content, same as it already
    does with fetched web pages or search results.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def name(self) -> str:
        return "document_intelligence"

    @staticmethod
    def is_available(settings: Settings) -> bool:
        return True  # local-only, no credentials required

    async def connect(self, exit_stack: AsyncExitStack) -> None:
        pass

    def list_tools(self) -> list[Tool]:
        return list(DOCUMENT_TOOLS)

    async def call_tool(self, name: str, arguments: dict) -> ToolCallResult:
        try:
            result = await asyncio.to_thread(self._dispatch, name, arguments)
        except Exception as exc:  # noqa: BLE001 — surface any failure back to the model
            logger.exception("Document tool %r failed", name)
            return ToolCallResult(text=f"Error: {exc}", is_error=True)

        return ToolCallResult(text=str(result), is_error=False)

    def _dispatch(self, name: str, arguments: dict) -> Any:
        if name == "read_pdf":
            path = resolve_allowed_path(self._settings, arguments["path"])
            return _pdf.read_pdf(path, arguments.get("start_page"), arguments.get("end_page"))

        if name == "read_docx":
            path = resolve_allowed_path(self._settings, arguments["path"])
            return _docx.read_docx(path)

        if name == "read_xlsx":
            path = resolve_allowed_path(self._settings, arguments["path"])
            return _xlsx.read_xlsx(
                path, arguments.get("sheet_name"), arguments.get("start_row"), arguments.get("end_row")
            )

        if name == "extract_tables":
            path = resolve_allowed_path(self._settings, arguments["path"])
            if path.suffix.lower() == ".pdf":
                return _pdf.extract_pdf_tables(path, arguments.get("start_page"), arguments.get("end_page"))
            if path.suffix.lower() == ".docx":
                return _docx.extract_docx_tables(path)
            raise ValueError(f"Table extraction only supports .pdf and .docx files, got {path.suffix!r}")

        if name == "create_pdf":
            path = resolve_allowed_write_path(self._settings, arguments["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            _pdf_writer.create_pdf(path, arguments["title"], arguments["content"])

            with path.open("rb") as f:
                header = f.read(len(_PDF_MAGIC))
            if header != _PDF_MAGIC:
                raise PdfGenerationError(
                    f"Generated file at {path} does not start with the PDF magic bytes "
                    f"({_PDF_MAGIC!r}); the file is not a valid PDF."
                )

            return {"path": str(path), "size_bytes": path.stat().st_size, "valid_pdf": True}

        if name == "compare_documents":
            path_a = resolve_allowed_path(self._settings, arguments["path_a"])
            path_b = resolve_allowed_path(self._settings, arguments["path_b"])
            return _compare.compare_texts(
                _read_text_for_compare(path_a), path_a.name, _read_text_for_compare(path_b), path_b.name
            )

        raise ValueError(f"Unknown document_intelligence tool: {name!r}")
