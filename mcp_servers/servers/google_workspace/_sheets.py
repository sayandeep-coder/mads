from __future__ import annotations

from typing import Any

from googleapiclient.discovery import Resource

SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def read_sheet(sheets: Resource, spreadsheet_id: str, range_: str) -> dict[str, Any]:
    """Read cell values from a range (A1 notation, e.g. 'Sheet1!A1:D20')."""
    response = sheets.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range_).execute()
    return {
        "range": response.get("range", range_),
        "values": response.get("values", []),
    }


def append_sheet(sheets: Resource, spreadsheet_id: str, range_: str, values: list[list[str]]) -> dict[str, Any]:
    """Append one or more rows after the last row of data in the given range."""
    response = (
        sheets.spreadsheets()
        .values()
        .append(
            spreadsheetId=spreadsheet_id,
            range=range_,
            valueInputOption="USER_ENTERED",
            body={"values": values},
        )
        .execute()
    )
    return {
        "updated_range": response.get("updates", {}).get("updatedRange", ""),
        "updated_rows": response.get("updates", {}).get("updatedRows", 0),
    }


def update_sheet(sheets: Resource, spreadsheet_id: str, range_: str, values: list[list[str]]) -> dict[str, Any]:
    """Overwrite cell values in the given range (A1 notation)."""
    response = (
        sheets.spreadsheets()
        .values()
        .update(
            spreadsheetId=spreadsheet_id,
            range=range_,
            valueInputOption="USER_ENTERED",
            body={"values": values},
        )
        .execute()
    )
    return {
        "updated_range": response.get("updatedRange", ""),
        "updated_cells": response.get("updatedCells", 0),
    }


def create_sheet(sheets: Resource, title: str) -> dict[str, Any]:
    """Create a new Google Sheet with the given title."""
    spreadsheet = (
        sheets.spreadsheets()
        .create(body={"properties": {"title": title}}, fields="spreadsheetId,spreadsheetUrl")
        .execute()
    )
    return {
        "spreadsheet_id": spreadsheet["spreadsheetId"],
        "url": spreadsheet["spreadsheetUrl"],
    }
