from __future__ import annotations

from typing import Any

from googleapiclient.discovery import Resource

CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _summarize_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": event["id"],
        "summary": event.get("summary", ""),
        "start": event.get("start", {}),
        "end": event.get("end", {}),
        "location": event.get("location", ""),
        "status": event.get("status", ""),
        "url": event.get("htmlLink", ""),
    }


def list_events(
    calendar: Resource,
    time_min: str | None = None,
    time_max: str | None = None,
    max_results: int = 10,
    calendar_id: str = "primary",
) -> list[dict[str, Any]]:
    """List upcoming events. time_min/time_max are RFC3339 timestamps; omit time_min for 'from now'."""
    response = (
        calendar.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    return [_summarize_event(event) for event in response.get("items", [])]


def create_event(
    calendar: Resource,
    summary: str,
    start: str,
    end: str,
    description: str = "",
    location: str = "",
    calendar_id: str = "primary",
) -> dict[str, Any]:
    """Create a calendar event. start/end are RFC3339 timestamps (e.g. 2026-07-15T14:00:00+05:30)."""
    body = {
        "summary": summary,
        "description": description,
        "location": location,
        "start": {"dateTime": start},
        "end": {"dateTime": end},
    }
    event = calendar.events().insert(calendarId=calendar_id, body=body).execute()
    return _summarize_event(event)


def update_event(
    calendar: Resource,
    event_id: str,
    summary: str | None = None,
    start: str | None = None,
    end: str | None = None,
    description: str | None = None,
    location: str | None = None,
    calendar_id: str = "primary",
) -> dict[str, Any]:
    """Update fields on an existing event. Only provided fields are changed."""
    event = calendar.events().get(calendarId=calendar_id, eventId=event_id).execute()

    if summary is not None:
        event["summary"] = summary
    if start is not None:
        event["start"] = {"dateTime": start}
    if end is not None:
        event["end"] = {"dateTime": end}
    if description is not None:
        event["description"] = description
    if location is not None:
        event["location"] = location

    updated = calendar.events().update(calendarId=calendar_id, eventId=event_id, body=event).execute()
    return _summarize_event(updated)


def delete_event(calendar: Resource, event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
    """Permanently delete a calendar event. This is irreversible."""
    calendar.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    return {"deleted_event_id": event_id}
