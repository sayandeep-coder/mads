from __future__ import annotations

from typing import Any

from googleapiclient.discovery import Resource
from googleapiclient.http import MediaInMemoryUpload

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]

_FILE_FIELDS = "id,name,mimeType,webViewLink,modifiedTime,size"
_LIST_FIELDS = f"files({_FILE_FIELDS})"


def _normalize_file(file: dict[str, Any]) -> dict[str, Any]:
    file = dict(file)
    file["url"] = file.pop("webViewLink", "")
    return file


def search_drive(drive: Resource, query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search Drive using Drive query syntax (e.g. \"name contains 'report'\")."""
    response = (
        drive.files()
        .list(q=query, pageSize=max_results, fields=_LIST_FIELDS)
        .execute()
    )
    return [_normalize_file(f) for f in response.get("files", [])]


def list_files(drive: Resource, max_results: int = 10) -> list[dict[str, Any]]:
    """List the user's most recently modified Drive files."""
    response = (
        drive.files()
        .list(pageSize=max_results, orderBy="modifiedTime desc", fields=_LIST_FIELDS)
        .execute()
    )
    return [_normalize_file(f) for f in response.get("files", [])]


def read_file_content(drive: Resource, file_id: str) -> dict[str, Any]:
    """Read the raw text content of a Drive file (works for plain text/binary-as-text files)."""
    metadata = drive.files().get(fileId=file_id, fields=_FILE_FIELDS).execute()
    content = drive.files().get_media(fileId=file_id).execute()
    return {**_normalize_file(metadata), "content": content.decode("utf-8", errors="replace")}


def create_file(
    drive: Resource, name: str, content: str = "", mime_type: str = "text/plain"
) -> dict[str, Any]:
    """Create a new file in Drive with the given text content."""
    media = MediaInMemoryUpload(content.encode("utf-8"), mimetype=mime_type)
    file = (
        drive.files()
        .create(body={"name": name, "mimeType": mime_type}, media_body=media, fields=_FILE_FIELDS)
        .execute()
    )
    return _normalize_file(file)


def copy_file(drive: Resource, file_id: str, new_name: str | None = None) -> dict[str, Any]:
    """Create a copy of an existing Drive file."""
    body = {"name": new_name} if new_name else {}
    file = drive.files().copy(fileId=file_id, body=body, fields=_FILE_FIELDS).execute()
    return _normalize_file(file)
