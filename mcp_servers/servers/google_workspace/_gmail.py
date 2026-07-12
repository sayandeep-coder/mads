from __future__ import annotations

import base64
from email.message import EmailMessage
from typing import Any

from googleapiclient.discovery import Resource

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

_MESSAGE_URL_TEMPLATE = "https://mail.google.com/mail/u/0/#all/{message_id}"


def search_emails(gmail: Resource, query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search the user's mailbox with Gmail search syntax and return matching message summaries."""
    response = (
        gmail.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )
    message_refs = response.get("messages", [])

    summaries = []
    for ref in message_refs:
        message = (
            gmail.users()
            .messages()
            .get(userId="me", id=ref["id"], format="metadata", metadataHeaders=["Subject", "From", "Date"])
            .execute()
        )
        headers = {h["name"]: h["value"] for h in message.get("payload", {}).get("headers", [])}
        summaries.append(
            {
                "id": message["id"],
                "thread_id": message["threadId"],
                "snippet": message.get("snippet", ""),
                "subject": headers.get("Subject", ""),
                "from": headers.get("From", ""),
                "date": headers.get("Date", ""),
                "url": _MESSAGE_URL_TEMPLATE.format(message_id=message["id"]),
            }
        )
    return summaries


def _extract_plain_text_body(payload: dict[str, Any]) -> str:
    if payload.get("mimeType") == "text/plain" and "data" in payload.get("body", {}):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

    for part in payload.get("parts", []):
        text = _extract_plain_text_body(part)
        if text:
            return text

    return ""


def read_email(gmail: Resource, message_id: str) -> dict[str, Any]:
    """Fetch the full content (headers + plain-text body) of a single email by id."""
    message = gmail.users().messages().get(userId="me", id=message_id, format="full").execute()
    payload = message.get("payload", {})
    headers = {h["name"]: h["value"] for h in payload.get("headers", [])}

    return {
        "id": message["id"],
        "thread_id": message["threadId"],
        "subject": headers.get("Subject", ""),
        "from": headers.get("From", ""),
        "to": headers.get("To", ""),
        "date": headers.get("Date", ""),
        "body": _extract_plain_text_body(payload),
        "url": _MESSAGE_URL_TEMPLATE.format(message_id=message["id"]),
    }


def _build_mime_message(to: str, subject: str, body: str) -> dict[str, str]:
    message = EmailMessage()
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    return {"raw": raw}


def draft_email(gmail: Resource, to: str, subject: str, body: str) -> dict[str, Any]:
    """Create a Gmail draft. Does not send — the user reviews and sends it themselves."""
    draft = (
        gmail.users()
        .drafts()
        .create(userId="me", body={"message": _build_mime_message(to, subject, body)})
        .execute()
    )
    return {
        "draft_id": draft["id"],
        "message_id": draft["message"]["id"],
        "url": _MESSAGE_URL_TEMPLATE.format(message_id=draft["message"]["id"]),
    }


def send_email(gmail: Resource, to: str, subject: str, body: str) -> dict[str, Any]:
    """Send an email immediately. This is irreversible — use only when explicitly asked to send."""
    sent = (
        gmail.users()
        .messages()
        .send(userId="me", body=_build_mime_message(to, subject, body))
        .execute()
    )
    return {
        "message_id": sent["id"],
        "thread_id": sent["threadId"],
        "url": _MESSAGE_URL_TEMPLATE.format(message_id=sent["id"]),
    }
