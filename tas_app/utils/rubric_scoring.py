"""
Rubric marks and scores.

Simple rubrics (schema_version 1): each criterion's options are parts of that criterion's
marks (Manage Rubrics makes them add up to 10), and the grading screen scores every
criterion out of that total, so a criterion is worth the sum of its option marks and a
rubric the sum over its criteria (three criteria of 10 make 30).

Weighted rubrics (schema_version 2) are stored as sections of components::

    {"id", "title", "components": [
        {"id", "name", "learning_objective", "learning_outcome", "field_ids": [...],
         "weight": 12.5, "is_gate": false, "feedbacks": [...],
         "criteria": [{"id", "name", "indicators": [{"text", "marks"}]}]}]}

Each criterion is scored out of 10 (its indicator marks add up to 10). A component
score is the average of its criterion scores; the component is worth
``10 * weight%`` marks and earns that times ``component score / 10``. Gate components
carry no weight: they decide whether the submission can be accepted, not its marks.
The rubric is worth 10 when the non-gate weights add up to 100%.
"""

from __future__ import annotations

CRITERION_MAX = 10
WEIGHT_TOTAL = 100
_TOLERANCE = 1e-6


def criterion_max_marks(options) -> float:
    """Marks a criterion is worth: the sum of its options' marks."""
    return sum(option.get("marks", 0) or 0 for option in options or [])


def rubric_max_marks(criteria) -> float:
    """Marks a rubric is worth: the sum over its criteria."""
    return sum(criterion_max_marks(criterion.get("options", [])) for criterion in criteria or [])


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None  # NaN check


def iter_components(sections):
    """Yield every component dict of a weighted rubric in order."""
    for section in sections or []:
        if not isinstance(section, dict):
            continue
        for component in section.get("components") or []:
            if isinstance(component, dict):
                yield component


def validate_rubric_sections(sections) -> list[str]:
    """Return human-readable problems with a weighted rubric; empty when valid."""
    if not isinstance(sections, list) or not sections:
        return ["Add at least one section."]

    errors = []
    weight_total = 0.0
    component_count = 0
    seen_ids = set()
    for s_index, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            errors.append(f"Section {s_index} is not valid.")
            continue
        title = (section.get("title") or "").strip()
        label = title or f"Section {s_index}"
        if not title:
            errors.append(f"Section {s_index} needs a title.")
        components = section.get("components") or []
        if not components:
            errors.append(f'"{label}" needs at least one component.')
        for c_index, component in enumerate(components, start=1):
            component_count += 1
            name = (component.get("name") or "").strip() if isinstance(component, dict) else ""
            c_label = name or f"Component {c_index} in {label}"
            if not isinstance(component, dict):
                errors.append(f"{c_label} is not valid.")
                continue
            component_id = component.get("id")
            if not component_id:
                errors.append(f"{c_label} is missing an id.")
            elif component_id in seen_ids:
                errors.append(f"{c_label} repeats id {component_id}.")
            seen_ids.add(component_id)
            if not name:
                errors.append(f"Component {c_index} in {label} needs a name.")
            weight = _number(component.get("weight"))
            if weight is None or weight < 0:
                errors.append(f"{c_label}: weight must be a number of 0 or more.")
                weight = 0.0
            if component.get("is_gate"):
                if weight > _TOLERANCE:
                    errors.append(f"{c_label}: a gate component must have 0% weight.")
            else:
                weight_total += weight
            criteria = component.get("criteria") or []
            if not criteria:
                errors.append(f"{c_label} needs at least one criterion.")
            for k_index, criterion in enumerate(criteria, start=1):
                if not isinstance(criterion, dict):
                    errors.append(f"{c_label}: criterion {k_index} is not valid.")
                    continue
                k_name = (criterion.get("name") or "").strip()
                k_label = k_name or f"criterion {k_index}"
                if not k_name:
                    errors.append(f"{c_label}: criterion {k_index} needs a name.")
                indicators = criterion.get("indicators") or []
                if not indicators:
                    errors.append(f"{c_label} / {k_label} needs at least one indicator.")
                total = 0.0
                for indicator in indicators:
                    if not isinstance(indicator, dict) or not (indicator.get("text") or "").strip():
                        errors.append(f"{c_label} / {k_label}: every indicator needs text.")
                        continue
                    marks = _number(indicator.get("marks"))
                    if marks is None or marks < 0:
                        errors.append(f"{c_label} / {k_label}: indicator marks must be 0 or more.")
                        continue
                    total += marks
                if indicators and abs(total - CRITERION_MAX) > _TOLERANCE:
                    errors.append(f"{c_label} / {k_label}: indicator marks must add up to 10 (now {total:g}).")
    if component_count and abs(weight_total - WEIGHT_TOTAL) > _TOLERANCE:
        errors.append(f"Component weights must add up to 100% (now {weight_total:g}%).")
    return errors


def component_score(component, feedback_row) -> float | None:
    """Average criterion score (0-10) of one component, or None when nothing is scored."""
    if not isinstance(feedback_row, dict):
        return None
    scores_by_id = {}
    scores_by_name = {}
    for item in feedback_row.get("criterion_scores") or []:
        if not isinstance(item, dict):
            continue
        score = _number(item.get("score"))
        if score is None:
            continue
        score = min(max(score, 0.0), float(CRITERION_MAX))
        if item.get("criterion_id"):
            scores_by_id[item["criterion_id"]] = score
        if item.get("criterion"):
            scores_by_name[item["criterion"]] = score

    found = []
    for criterion in component.get("criteria") or []:
        score = scores_by_id.get(criterion.get("id"))
        if score is None:
            score = scores_by_name.get(criterion.get("name"))
        if score is not None:
            found.append(score)
    if not found:
        return None
    return sum(found) / len(found)


def weighted_rubric_score(feedback_rubrics, sections) -> tuple[float, float]:
    """(earned, max_possible) for a weighted rubric; unscored components earn 0."""
    rows = {
        entry.get("component_id"): entry
        for entry in feedback_rubrics or []
        if isinstance(entry, dict) and entry.get("component_id")
    }
    earned = 0.0
    max_possible = 0.0
    for component in iter_components(sections):
        if component.get("is_gate"):
            continue
        weight = _number(component.get("weight")) or 0.0
        component_max = CRITERION_MAX * weight / WEIGHT_TOTAL
        max_possible += component_max
        score = component_score(component, rows.get(component.get("id")))
        if score is not None:
            earned += component_max * score / CRITERION_MAX
    return round(earned, 2), round(max_possible, 2)
