from __future__ import annotations

from typing import Any

from googleapiclient.discovery import Resource

from mcp_servers.servers.google_workspace._markdown import markdown_to_batch_requests

DOCS_SCOPES = ["https://www.googleapis.com/auth/documents"]

_DOC_URL_TEMPLATE = "https://docs.google.com/document/d/{document_id}/edit"


def _extract_text(body: dict[str, Any]) -> str:
    text_parts: list[str] = []
    for element in body.get("content", []):
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        for run in paragraph.get("elements", []):
            text_run = run.get("textRun")
            if text_run:
                text_parts.append(text_run.get("content", ""))
    return "".join(text_parts)


def read_document(docs: Resource, document_id: str) -> dict[str, Any]:
    """Read a Google Doc's title and full plain-text content."""
    document = docs.documents().get(documentId=document_id).execute()
    return {
        "document_id": document["documentId"],
        "title": document.get("title", ""),
        "content": _extract_text(document.get("body", {})),
        "url": _DOC_URL_TEMPLATE.format(document_id=document["documentId"]),
    }


def create_document(docs: Resource, title: str, content: str = "") -> dict[str, Any]:
    """Create a new Google Doc with the given title and optional initial content.

    Content may use simple markdown — '#'/'##'/'###' headings, '**bold**'
    spans, and '-'/'*' bullet lists — which is rendered as real Google Docs
    formatting rather than inserted as literal markdown characters.
    """
    document = docs.documents().create(body={"title": title}).execute()
    document_id = document["documentId"]

    if content:
        requests = markdown_to_batch_requests(content, start_index=1)
        docs.documents().batchUpdate(documentId=document_id, body={"requests": requests}).execute()

    return {
        "document_id": document_id,
        "title": title,
        "url": _DOC_URL_TEMPLATE.format(document_id=document_id),
    }


def update_document(docs: Resource, document_id: str, content: str, append: bool = True) -> dict[str, Any]:
    """Insert content into an existing Google Doc. Appends to the end by default.

    Content may use simple markdown — '#'/'##'/'###' headings, '**bold**'
    spans, and '-'/'*' bullet lists — which is rendered as real Google Docs
    formatting rather than inserted as literal markdown characters.
    """
    if append:
        document = docs.documents().get(documentId=document_id).execute()
        end_index = document["body"]["content"][-1]["endIndex"] - 1
        index = max(end_index, 1)
    else:
        index = 1

    requests = markdown_to_batch_requests(content, start_index=index)
    docs.documents().batchUpdate(documentId=document_id, body={"requests": requests}).execute()

    return {
        "document_id": document_id,
        "url": _DOC_URL_TEMPLATE.format(document_id=document_id),
    }
