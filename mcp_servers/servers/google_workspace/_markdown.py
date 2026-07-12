from __future__ import annotations

import re
from dataclasses import dataclass, field

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")
_BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")

_HEADING_STYLES = {1: "HEADING_1", 2: "HEADING_2", 3: "HEADING_3"}


@dataclass
class _ParsedLine:
    text: str
    heading_level: int | None = None
    is_bullet: bool = False
    bold_spans: list[tuple[int, int]] = field(default_factory=list)


def _parse_line(raw_line: str) -> _ParsedLine:
    heading_match = _HEADING_RE.match(raw_line)
    if heading_match:
        content = heading_match.group(2)
        text, bold_spans = _strip_bold(content)
        return _ParsedLine(text=text, heading_level=len(heading_match.group(1)), bold_spans=bold_spans)

    bullet_match = _BULLET_RE.match(raw_line)
    if bullet_match:
        content = bullet_match.group(1)
        text, bold_spans = _strip_bold(content)
        return _ParsedLine(text=text, is_bullet=True, bold_spans=bold_spans)

    text, bold_spans = _strip_bold(raw_line)
    return _ParsedLine(text=text, bold_spans=bold_spans)


def _strip_bold(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Remove ** markers, returning the plain text and the (start, end) offsets that were bold."""
    spans: list[tuple[int, int]] = []
    result = []
    cursor = 0

    for match in _BOLD_RE.finditer(text):
        result.append(text[cursor : match.start()])
        plain_start = sum(len(p) for p in result)
        bold_text = match.group(1)
        result.append(bold_text)
        spans.append((plain_start, plain_start + len(bold_text)))
        cursor = match.end()

    result.append(text[cursor:])
    return "".join(result), spans


def markdown_to_batch_requests(markdown: str, start_index: int = 1) -> list[dict]:
    """Convert a markdown string into Google Docs batchUpdate requests.

    Supports '#'/'##'/'###' headings, '**bold**' spans, and '-'/'*' bullet
    lists. Text is inserted first (as plain text, markdown syntax stripped),
    then paragraph/text style requests are layered on top of the resulting
    index ranges — batchUpdate applies requests in order, and insertText
    shifts indices, so style requests must reference post-insertion offsets.
    """
    lines = markdown.split("\n")
    parsed_lines = [_parse_line(line) for line in lines]

    insert_requests: list[dict] = []
    style_requests: list[dict] = []
    index = start_index

    for parsed in parsed_lines:
        line_start = index
        insert_requests.append({"insertText": {"location": {"index": index}, "text": parsed.text + "\n"}})

        if parsed.heading_level:
            style_requests.append(
                {
                    "updateParagraphStyle": {
                        "range": {"startIndex": line_start, "endIndex": line_start + len(parsed.text)},
                        "paragraphStyle": {"namedStyleType": _HEADING_STYLES[parsed.heading_level]},
                        "fields": "namedStyleType",
                    }
                }
            )

        if parsed.is_bullet:
            style_requests.append(
                {
                    "createParagraphBullets": {
                        "range": {"startIndex": line_start, "endIndex": line_start + len(parsed.text)},
                        "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                    }
                }
            )

        for bold_start, bold_end in parsed.bold_spans:
            style_requests.append(
                {
                    "updateTextStyle": {
                        "range": {"startIndex": line_start + bold_start, "endIndex": line_start + bold_end},
                        "textStyle": {"bold": True},
                        "fields": "bold",
                    }
                }
            )

        index = line_start + len(parsed.text) + 1  # +1 for the trailing newline

    return insert_requests + style_requests
