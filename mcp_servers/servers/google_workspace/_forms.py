from __future__ import annotations

from typing import Any

from googleapiclient.discovery import Resource

# forms.body: create/edit forms. forms.responses.readonly: read submitted
# answers. Two distinct scopes (unlike most other services here) because
# Google splits form-editing and response-reading permission separately.
FORMS_SCOPES = [
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/forms.responses.readonly",
]

_FORM_URL_TEMPLATE = "https://docs.google.com/forms/d/{form_id}/edit"
_RESPONDER_URL_TEMPLATE = "https://docs.google.com/forms/d/{form_id}/viewform"

# Question "kind" values the tool schema exposes to the model — a flatter,
# friendlier surface than the Forms API's own nested union of
# ChoiceQuestion/TextQuestion/ScaleQuestion/etc, translated below.
_CHOICE_KIND_TO_TYPE = {
    "multiple_choice": "RADIO",
    "checkboxes": "CHECKBOX",
    "dropdown": "DROP_DOWN",
}


def _build_question(q: dict[str, Any]) -> dict[str, Any]:
    """Translate one flat question spec (from the tool's input schema) into
    a Forms API Question object, keyed by q['kind'].

    Branching options (`options_goto`) are NOT resolved here — Google
    assigns real item IDs only after creation, so create_form does this in
    two passes: create everything with plain options first, then a second
    batchUpdate patches in goToSectionId once real section IDs are known.
    See _resolve_branching.
    """
    kind = q["kind"]
    required = bool(q.get("required", False))

    if kind in _CHOICE_KIND_TO_TYPE:
        options = [{"value": opt} for opt in q.get("options", [])]
        return {
            "required": required,
            "choiceQuestion": {
                "type": _CHOICE_KIND_TO_TYPE[kind],
                "options": options,
                "shuffle": bool(q.get("shuffle", False)),
            },
        }

    if kind == "short_text":
        return {"required": required, "textQuestion": {"paragraph": False}}

    if kind == "paragraph_text":
        return {"required": required, "textQuestion": {"paragraph": True}}

    if kind == "linear_scale":
        scale: dict[str, Any] = {
            "low": q.get("scale_low", 1),
            "high": q.get("scale_high", 5),
        }
        if q.get("scale_low_label"):
            scale["lowLabel"] = q["scale_low_label"]
        if q.get("scale_high_label"):
            scale["highLabel"] = q["scale_high_label"]
        return {"required": required, "scaleQuestion": scale}

    if kind == "date":
        return {
            "required": required,
            "dateQuestion": {
                "includeYear": True,
                "includeTime": bool(q.get("include_time", False)),
            },
        }

    if kind == "time":
        return {"required": required, "timeQuestion": {"duration": bool(q.get("is_duration", False))}}

    if kind == "file_upload":
        return {
            "required": required,
            "fileUploadQuestion": {
                "maxFiles": q.get("max_files", 1),
                "maxFileSize": q.get("max_file_size_bytes", 10 * 1024 * 1024),
            },
        }

    raise ValueError(f"Unknown question kind: {kind!r}")


def _build_grid_item(q: dict[str, Any], index: int) -> dict[str, Any]:
    """A grid is a group of identical row-questions sharing one set of
    columns — the one question kind that isn't a single Question object."""
    grid_type = "CHECKBOX" if q.get("grid_multiple_selection") else "RADIO"
    return {
        "item": {
            "title": q["title"],
            "questionGroupItem": {
                "questions": [
                    {"required": bool(q.get("required", False)), "rowQuestion": {"title": row}}
                    for row in q.get("grid_rows", [])
                ],
                "grid": {
                    "columns": {
                        "type": grid_type,
                        "options": [{"value": col} for col in q.get("grid_columns", [])],
                    }
                },
            },
        },
        "location": {"index": index},
    }


# Sentinel goToSectionId values matching Forms API's GoToAction enum, for
# options that submit the form or restart it rather than jump to a labeled
# section — resolved directly, no item-id lookup needed.
_GOTO_SENTINELS = {"@submit": "SUBMIT_FORM", "@restart": "RESTART_FORM", "@next": "NEXT_SECTION"}


def _build_create_item_requests(
    questions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Build the first-pass createItem requests, and return a map of
    section_id (the model's own label, from a section_break's "section_id"
    field) -> its position in `questions`, so the branching pass can find
    which created item to look up once real IDs are assigned.
    """
    requests: list[dict[str, Any]] = []
    section_positions: dict[str, int] = {}

    for index, q in enumerate(questions):
        if q.get("kind") == "section_break":
            if q.get("section_id"):
                section_positions[q["section_id"]] = index
            requests.append(
                {
                    "createItem": {
                        "item": {
                            "title": q.get("title", ""),
                            "description": q.get("description", ""),
                            "pageBreakItem": {},
                        },
                        "location": {"index": index},
                    }
                }
            )
            continue

        if q.get("kind") == "grid":
            requests.append({"createItem": _build_grid_item(q, index)})
            continue

        requests.append(
            {
                "createItem": {
                    "item": {
                        "title": q["title"],
                        "description": q.get("description", ""),
                        "questionItem": {"question": _build_question(q)},
                    },
                    "location": {"index": index},
                }
            }
        )
    return requests, section_positions


def _build_branching_requests(
    questions: list[dict[str, Any]],
    item_ids_by_position: list[str],
    section_positions: dict[str, int],
) -> list[dict[str, Any]]:
    """Second pass: for every choice question with `options_goto`, patch in
    the real goToSectionId now that section item IDs are known. Only
    RADIO/DROP_DOWN choice types support branching (a Forms API
    constraint, not this tool's) — CHECKBOX questions with options_goto are
    silently ignored rather than erroring, since "check several boxes,
    which one branches?" has no sound answer.
    """
    requests: list[dict[str, Any]] = []

    for index, q in enumerate(questions):
        options_goto = q.get("options_goto")
        if not options_goto or q.get("kind") not in ("multiple_choice", "dropdown"):
            continue

        # options_goto is a list of {"option": ..., "goto": ...} pairs (not
        # a dict — Gemini's function-calling schema doesn't support
        # free-form object maps via additionalProperties).
        goto_by_option = {entry["option"]: entry["goto"] for entry in options_goto}

        question = _build_question(q)
        for option in question["choiceQuestion"]["options"]:
            target = goto_by_option.get(option["value"])
            if target is None:
                continue
            if target in _GOTO_SENTINELS:
                option["goToAction"] = _GOTO_SENTINELS[target]
            elif target in section_positions:
                option["goToSectionId"] = item_ids_by_position[section_positions[target]]
            # Unknown target label: leave the option as a plain choice
            # rather than erroring the whole form build over one typo.

        requests.append(
            {
                "updateItem": {
                    "item": {
                        "title": q["title"],
                        "description": q.get("description", ""),
                        "questionItem": {"question": question},
                    },
                    "location": {"index": index},
                    "updateMask": "questionItem",
                }
            }
        )

    return requests


def create_form(
    forms: Resource,
    title: str,
    description: str = "",
    questions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a new Google Form and populate it with questions in one call,
    including section branching if requested.

    `questions` is a list of flat specs, each with a "kind": short_text,
    paragraph_text, multiple_choice, checkboxes, dropdown, linear_scale,
    date, time, file_upload, grid, or section_break. See FORMS_TOOLS in
    _schemas.py for the full per-kind field reference — this function is
    a thin translator from that flat shape into the Forms API's nested
    Question union, not a place to encode question-design judgment calls.

    Branching (multiple_choice/dropdown only, a Forms API constraint) is a
    second pass: Google only assigns real item IDs after creation, so
    goToSectionId can't be set in the same request that creates the
    section. create_form creates everything first, re-reads the form to
    learn real IDs, then patches in the branching in one more batchUpdate.
    """
    form = forms.forms().create(body={"info": {"title": title}}).execute()
    form_id = form["formId"]

    questions = questions or []
    create_requests, section_positions = _build_create_item_requests(questions)

    update_requests: list[dict[str, Any]] = []
    if description:
        update_requests.append(
            {
                "updateFormInfo": {
                    "info": {"description": description},
                    "updateMask": "description",
                }
            }
        )
    update_requests.extend(create_requests)

    if update_requests:
        forms.forms().batchUpdate(formId=form_id, body={"requests": update_requests}).execute()

    has_branching = any(q.get("options_goto") for q in questions)
    if has_branching:
        loaded = forms.forms().get(formId=form_id).execute()
        item_ids_by_position = [item["itemId"] for item in loaded["items"]]
        branching_requests = _build_branching_requests(questions, item_ids_by_position, section_positions)
        if branching_requests:
            forms.forms().batchUpdate(formId=form_id, body={"requests": branching_requests}).execute()

    return {
        "form_id": form_id,
        "title": title,
        "edit_url": _FORM_URL_TEMPLATE.format(form_id=form_id),
        "responder_url": _RESPONDER_URL_TEMPLATE.format(form_id=form_id),
        "question_count": len(questions),
        "has_branching": has_branching,
    }


def get_form_responses(forms: Resource, form_id: str, max_results: int = 50) -> dict[str, Any]:
    """Read submitted responses to a form as structured question->answer data."""
    form = forms.forms().get(formId=form_id).execute()

    question_titles: dict[str, str] = {}
    for item in form.get("items", []):
        question_item = item.get("questionItem")
        if question_item:
            question_titles[question_item["question"]["questionId"]] = item.get("title", "")
        group = item.get("questionGroupItem")
        if group:
            for row_q in group.get("questions", []):
                row_title = row_q.get("rowQuestion", {}).get("title", "")
                question_titles[row_q["questionId"]] = f"{item.get('title', '')} — {row_title}"

    result = forms.forms().responses().list(formId=form_id, pageSize=max_results).execute()

    responses = []
    for response in result.get("responses", []):
        answers: dict[str, Any] = {}
        for question_id, answer in response.get("answers", {}).items():
            title = question_titles.get(question_id, question_id)
            text_answers = answer.get("textAnswers", {}).get("answers", [])
            answers[title] = [a.get("value", "") for a in text_answers]
        responses.append(
            {
                "response_id": response.get("responseId"),
                "submitted_at": response.get("createTime"),
                "answers": answers,
            }
        )

    return {
        "form_id": form_id,
        "response_count": len(responses),
        "responses": responses,
    }
