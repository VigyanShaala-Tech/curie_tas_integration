"""Strict, result-specific callback validation. No database writes."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from tas_app.curie.constants import CURIE_CRITERIA, RESULT_ERROR, RESULT_SUCCESS


class CallbackValidationError(ValueError):
    """Malformed or internally inconsistent CURIE callback."""


REQUIRED_IDENTITY_FIELDS = (
    "trigger_id",
    "user_id",
    "submission_id",
    "submission_version_number",
    "result",
)
REQUIRED_MAX_SCORE = 10


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CallbackValidationError(f"{label} must be an object.")
    return value


def _require_list(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise CallbackValidationError(f"{label} must be a list.")
    return value


def _require_json_int(value: Any, label: str, *, minimum: int | None = None) -> int:
    """Accept only a JSON integer. Reject bools, floats, and numeric strings."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise CallbackValidationError(f"{label} must be a JSON integer.")
    if minimum is not None and value < minimum:
        raise CallbackValidationError(f"{label} must be >= {minimum}.")
    return value


def _require_finite_score(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CallbackValidationError(f"{label} must be a finite number.")
    number = float(value)
    if not math.isfinite(number):
        raise CallbackValidationError(f"{label} must be a finite number.")
    return number


def validate_criterion_scores(scores: Any, *, label: str, allow_empty: bool = False) -> list[dict[str, Any]]:
    items = _require_list(scores, label)
    if allow_empty and not items:
        return []
    if len(items) != len(CURIE_CRITERIA):
        raise CallbackValidationError(f"{label} must contain exactly {len(CURIE_CRITERIA)} scores.")
    seen = []
    normalized = []
    for index, raw in enumerate(items):
        item = _require_mapping(raw, f"{label}[{index}]")
        name = item.get("criterion")
        if name not in CURIE_CRITERIA:
            raise CallbackValidationError(f"{label}[{index}] uses unknown criterion {name!r}.")
        if name in seen:
            raise CallbackValidationError(f"{label} repeats criterion {name!r}.")
        if "score" not in item or "max_score" not in item:
            raise CallbackValidationError(f"{label}[{index}] score/max_score is invalid.")
        score = _require_finite_score(item["score"], f"{label}[{index}].score")
        max_score = _require_finite_score(item["max_score"], f"{label}[{index}].max_score")
        if max_score != REQUIRED_MAX_SCORE:
            raise CallbackValidationError(f"{label}[{index}].max_score must equal {REQUIRED_MAX_SCORE}.")
        if score < 0 or score > REQUIRED_MAX_SCORE:
            raise CallbackValidationError(f"{label}[{index}] score {score} is outside 0..{REQUIRED_MAX_SCORE}.")
        seen.append(name)
        normalized.append({"criterion": name, "score": score, "max_score": max_score})
    if set(seen) != set(CURIE_CRITERIA):
        raise CallbackValidationError(f"{label} must include each of {CURIE_CRITERIA}.")
    return normalized


def validate_field_feedback(
    field_feedback: Any,
    *,
    allowed_field_ids: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    items = _require_list(field_feedback, "field_feedback")
    if not items:
        if allowed_field_ids:
            raise CallbackValidationError(
                f"field_feedback is missing submitted fields {list(allowed_field_ids)}."
            )
        raise CallbackValidationError("field_feedback is required when result is success.")

    seen_ids = []
    normalized = []
    for index, raw in enumerate(items):
        entry = _require_mapping(raw, f"field_feedback[{index}]")
        field_id = entry.get("field_id")
        if not field_id or not isinstance(field_id, str):
            raise CallbackValidationError(f"field_feedback[{index}].field_id is required.")
        if field_id in seen_ids:
            raise CallbackValidationError(f"Duplicate field_id {field_id!r}.")
        if allowed_field_ids is not None and field_id not in allowed_field_ids:
            raise CallbackValidationError(f"field_id {field_id!r} is not on the submitted template.")
        weight = _require_json_int(
            entry.get("weight"),
            f"field_feedback[{index}].weight",
            minimum=0,
        )
        comment = entry.get("comment")
        if not isinstance(comment, str) or not comment.strip():
            raise CallbackValidationError(f"field_feedback[{index}].comment is required.")
        scores = validate_criterion_scores(
            entry.get("criterion_scores"),
            label=f"field_feedback[{index}].criterion_scores",
        )
        seen_ids.append(field_id)
        normalized.append(
            {
                "field_id": field_id,
                "weight": weight,
                "comment": comment,
                "criterion_scores": scores,
            }
        )
    if allowed_field_ids is not None:
        missing = [field_id for field_id in allowed_field_ids if field_id not in seen_ids]
        if missing:
            raise CallbackValidationError(f"field_feedback is missing submitted fields {missing}.")
    return normalized


def validate_callback_payload(
    payload: Mapping[str, Any],
    *,
    allowed_field_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Return a normalized callback dict or raise CallbackValidationError."""
    body = _require_mapping(payload, "callback")
    missing = [name for name in REQUIRED_IDENTITY_FIELDS if name not in body]
    if missing:
        raise CallbackValidationError(f"Missing required fields: {missing}.")

    result = body.get("result")
    if result not in (RESULT_SUCCESS, RESULT_ERROR):
        raise CallbackValidationError(f"result must be {RESULT_SUCCESS!r} or {RESULT_ERROR!r}.")

    version = _require_json_int(
        body["submission_version_number"],
        "submission_version_number",
        minimum=1,
    )

    normalized: dict[str, Any] = {
        "trigger_id": str(body["trigger_id"]),
        "user_id": str(body["user_id"]),
        "submission_id": str(body["submission_id"]),
        "submission_version_number": version,
        "result": result,
    }

    if result == RESULT_ERROR:
        error_message = body.get("error_message")
        if not isinstance(error_message, str) or not error_message.strip():
            raise CallbackValidationError("error_message is required when result is error.")
        extra = [key for key in ("gate_criterion_scores", "field_feedback", "overall_feedback") if key in body]
        if extra:
            raise CallbackValidationError(f"error callbacks must not include {extra}.")
        normalized["error_message"] = error_message.strip()
        return normalized

    overall = body.get("overall_feedback")
    if not isinstance(overall, str) or not overall.strip():
        raise CallbackValidationError("overall_feedback is required when result is success.")
    gate = validate_criterion_scores(body.get("gate_criterion_scores"), label="gate_criterion_scores")
    fields = validate_field_feedback(
        body.get("field_feedback"),
        allowed_field_ids=allowed_field_ids,
    )
    normalized.update(
        {
            "gate_criterion_scores": gate,
            "field_feedback": fields,
            "overall_feedback": overall,
        }
    )
    return normalized
