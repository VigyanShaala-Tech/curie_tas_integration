"""Pure score reduction, verdict, colour, and star-rating helpers."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping, Sequence

from tas_app.curie.constants import (
    CURIE_CRITERIA,
    DEFAULT_COMPONENT_PASS_THRESHOLD,
    FIELD_COLOR_COULD_IMPROVE,
    FIELD_COLOR_GOOD,
    FIELD_COLOR_NEEDS_REVISION,
    RUBRIC_CATEGORY_BY_CURIE_CRITERION,
    VERDICT_ACCEPTED,
    VERDICT_REJECTED,
)


class ScoringError(ValueError):
    """Raised when scores cannot be reduced because the payload is inconsistent."""


def round_half_up(value: float) -> int:
    """Conventional half-up rounding so 4.5 stars becomes 5, not banker's 4."""
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def average_criterion_scores(scores: Sequence[Mapping[str, Any]]) -> float:
    """Average the numeric `score` values in a 3-criterion list."""
    if not scores:
        raise ScoringError("Cannot average an empty criterion-score list.")
    values = [float(item["score"]) for item in scores]
    return sum(values) / len(values)


def component_score(entry: Mapping[str, Any]) -> float | None:
    """Return a 0-10 component mean, or None for weight-zero fields."""
    if int(entry.get("weight", 1)) == 0:
        return None
    return average_criterion_scores(entry.get("criterion_scores") or [])


def scored_component_entries(field_feedback: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [entry for entry in field_feedback if int(entry.get("weight", 1)) != 0]


def all_component_scores(
    gate_criterion_scores: Sequence[Mapping[str, Any]],
    field_feedback: Sequence[Mapping[str, Any]],
) -> list[float]:
    """Gate mean plus every weight=1 field mean. Weight-zero fields are skipped."""
    scores = [average_criterion_scores(gate_criterion_scores)]
    for entry in field_feedback:
        field_score = component_score(entry)
        if field_score is not None:
            scores.append(field_score)
    return scores


def compute_verdict(
    gate_criterion_scores: Sequence[Mapping[str, Any]],
    field_feedback: Sequence[Mapping[str, Any]],
    *,
    threshold: float,
) -> str:
    """Reject when the minimum component score is below the configured pass threshold."""
    scores = all_component_scores(gate_criterion_scores, field_feedback)
    if min(scores) < threshold:
        return VERDICT_REJECTED
    return VERDICT_ACCEPTED


def field_color_for_score(score: float | None, *, threshold: float = DEFAULT_COMPONENT_PASS_THRESHOLD) -> str | None:
    """Map a field mean onto the closed colour bands. Weight-zero fields have no colour."""
    if score is None:
        return None
    if score < threshold:
        return FIELD_COLOR_NEEDS_REVISION
    if score < 8:
        return FIELD_COLOR_COULD_IMPROVE
    return FIELD_COLOR_GOOD


def criterion_wise_scores(field_feedback: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    """Average each CURIE criterion across weight=1 fields only. Gate is excluded."""
    buckets: dict[str, list[float]] = {name: [] for name in CURIE_CRITERIA}
    for entry in scored_component_entries(field_feedback):
        seen = set()
        for item in entry.get("criterion_scores") or []:
            name = item["criterion"]
            if name not in buckets:
                raise ScoringError(f"Unknown criterion name {name!r}.")
            if name in seen:
                raise ScoringError(f"Duplicate criterion {name!r} on field {entry.get('field_id')!r}.")
            seen.add(name)
            buckets[name].append(float(item["score"]))
        missing = [name for name in CURIE_CRITERIA if name not in seen]
        if missing:
            raise ScoringError(f"Field {entry.get('field_id')!r} is missing criteria {missing}.")
    if any(not values for values in buckets.values()):
        return {}
    return {name: sum(values) / len(values) for name, values in buckets.items()}


def star_rating(field_feedback: Sequence[Mapping[str, Any]]) -> int | None:
    """Whole-star rating from criterion-wise means. None when fields were not scored."""
    averages = criterion_wise_scores(field_feedback)
    if not averages:
        return None
    grand_mean = sum(averages.values()) / len(averages)
    return round_half_up((grand_mean / 10.0) * 5)


def instructor_rubric_entries(field_feedback: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Three InstructorFeedback.rubrics rows keyed by TAS Rubric Category names."""
    averages = criterion_wise_scores(field_feedback)
    if not averages:
        return []
    entries = []
    for curie_name in CURIE_CRITERIA:
        value = averages[curie_name]
        category = RUBRIC_CATEGORY_BY_CURIE_CRITERION[curie_name]
        entries.append(
            {
                "criterion": category,
                "marks": value,
                "selected_option": f"Score: {value}",
            }
        )
    return entries
