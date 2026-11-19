"""Map a weighted-rubric instructor grade onto the stored CURIE field contract.

The grading screen scores components. A ready CURIE review is still stored per
template field. This keeps the existing override record (verdict, gate scores,
field comments, and weights) in sync with the component rows the instructor saved.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from tas_app.curie.constants import CURIE_CRITERIA
from tas_app.utils.rubric_scoring import iter_components


def _norm(name: Any) -> str:
    return "".join(ch for ch in str(name or "").lower() if ch.isalnum())


def _finite_score(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if isinstance(value, bool) or not math.isfinite(number):
        return None
    return min(max(number, 0.0), 10.0)


def _scores_by_norm(component: Mapping[str, Any] | None, row: Mapping[str, Any] | None) -> dict[str, float]:
    if not row:
        return {}
    id_to_name = {}
    if component:
        for criterion in component.get("criteria") or []:
            if isinstance(criterion, dict) and criterion.get("id"):
                id_to_name[criterion["id"]] = criterion.get("name") or ""
    found = {}
    for item in row.get("criterion_scores") or []:
        if not isinstance(item, dict):
            continue
        score = _finite_score(item.get("score"))
        if score is None:
            continue
        name = id_to_name.get(item.get("criterion_id")) or item.get("criterion") or ""
        if name:
            found[_norm(name)] = score
    return found


def _fallback_scores(scores: Sequence[Any] | None) -> dict[str, float]:
    found = {}
    for item in scores or []:
        if not isinstance(item, dict):
            continue
        score = _finite_score(item.get("score"))
        if score is not None and item.get("criterion"):
            found[_norm(item["criterion"])] = score
    return found


def _criterion_scores(
    component: Mapping[str, Any] | None,
    row: Mapping[str, Any] | None,
    fallback: Sequence[Any] | None,
) -> list[dict[str, Any]]:
    found = _scores_by_norm(component, row)
    original = _fallback_scores(fallback)
    scores = []
    for name in CURIE_CRITERIA:
        key = _norm(name)
        score = found.get(key, original.get(key, 0.0))
        scores.append({"criterion": name, "score": score, "max_score": 10})
    return scores


def structured_feedback_from_components(
    *,
    sections: Sequence[Any],
    component_rows: Sequence[Any],
    gate_criterion_scores: Sequence[Any] | None,
    field_feedback: Sequence[Any] | None,
    overall_feedback: str,
    verdict: str,
) -> dict[str, Any]:
    """Build the override record from instructor component rows.

    Fields linked to a component take that component's scores and section
    feedback. Unlinked fields keep the original CURIE entry. Weights are copied
    from the stored review and are not taken from the grading form.
    """
    rows_by_id = {
        row.get("component_id"): row
        for row in component_rows or []
        if isinstance(row, dict) and row.get("component_id")
    }
    components = list(iter_components(sections))
    gate = next((component for component in components if component.get("is_gate")), None)
    gate_row = rows_by_id.get(gate.get("id")) if gate else None

    updated_fields = []
    for entry in field_feedback or []:
        if not isinstance(entry, dict) or not entry.get("field_id"):
            continue
        field_id = entry["field_id"]
        component = next(
            (
                item for item in components
                if not item.get("is_gate") and field_id in (item.get("field_ids") or [])
            ),
            None,
        )
        row = rows_by_id.get(component.get("id")) if component else None
        if row is None:
            comment = entry.get("comment") or ""
            scores = _criterion_scores(None, None, entry.get("criterion_scores"))
        else:
            comment = row["comment"] if isinstance(row.get("comment"), str) else (entry.get("comment") or "")
            scores = _criterion_scores(component, row, entry.get("criterion_scores"))
        weight = entry.get("weight", 1)
        try:
            weight = int(weight)
        except (TypeError, ValueError):
            weight = 1
        updated_fields.append(
            {
                "field_id": field_id,
                "weight": weight,
                "comment": comment,
                "criterion_scores": scores,
            }
        )

    return {
        "schema_version": 1,
        "verdict": verdict,
        "gate_criterion_scores": _criterion_scores(gate, gate_row, gate_criterion_scores),
        "field_feedback": updated_fields,
        "overall_feedback": overall_feedback or "",
    }
