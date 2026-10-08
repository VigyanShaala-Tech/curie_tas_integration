"""CURIE read payloads and batched history summaries."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.utils import timezone

from tas_app.curie.constants import LEARNER_FAILURE_DETAIL
from tas_app.curie.policy import current_review, feedback_source_for
from tas_app.curie.scoring import (
    average_criterion_scores,
    component_score,
    criterion_wise_scores,
    field_color_for_score,
    star_rating,
)
from tas_app.curie.settings import slow_review_seconds
from tas_app.curie.timeout import is_slow_pending, persist_timeout_if_due
from tas_app.curie.transitions import attempt_count, instructor_form_locked, is_at_attempt_cap
from tas_app.models import CurieReview, Submission


def reviews_for(submission: Submission) -> list[CurieReview]:
    cached = getattr(submission, "_curie_reviews_cache", None)
    if cached is None:
        cached = list(submission.curie_reviews.all())
        submission._curie_reviews_cache = cached
    return cached


def review_for_version(submission: Submission, version_number: int | None = None) -> CurieReview | None:
    version = submission.version_number if version_number is None else int(version_number)
    for review in reviews_for(submission):
        if review.submission_version_number == version:
            return review
    return current_review(submission, version)


def resolve_review_for_read(
    submission: Submission,
    version_number: int | None = None,
    *,
    now: datetime | None = None,
) -> CurieReview | None:
    review = review_for_version(submission, version_number)
    resolved = persist_timeout_if_due(review, now=now)
    if resolved is None:
        return None
    cached = getattr(submission, "_curie_reviews_cache", None)
    if cached is not None:
        submission._curie_reviews_cache = [
            resolved if item.pk == resolved.pk else item for item in cached
        ]
    return resolved


def _is_slow(review: CurieReview, now: datetime) -> bool:
    if review.status != CurieReview.STATUS_PENDING_EVALUATION:
        return False
    return is_slow_pending(
        review.requested_at,
        now,
        slow_after_seconds=slow_review_seconds(),
    )


def learner_field_entries(field_feedback: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    entries = []
    for item in field_feedback or []:
        score = component_score(item)
        entries.append(
            {
                "field_id": item.get("field_id"),
                "weight": item.get("weight", 1),
                "comment": item.get("comment", ""),
                "color": field_color_for_score(score),
            }
        )
    return entries


def staff_field_entries(field_feedback: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    entries = []
    for item in field_feedback or []:
        score = component_score(item)
        entries.append(
            {
                "field_id": item.get("field_id"),
                "weight": item.get("weight", 1),
                "comment": item.get("comment", ""),
                "color": field_color_for_score(score),
                "field_score": score,
                "criterion_scores": item.get("criterion_scores") or [],
            }
        )
    return entries


def learner_review_payload(review: CurieReview, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or timezone.now()
    ready = review.status == CurieReview.STATUS_READY
    return {
        "status": review.status,
        "verdict": review.verdict if ready else None,
        "overall_feedback": review.overall_feedback if ready else "",
        "field_feedback": learner_field_entries(review.field_feedback) if ready else [],
        "star_rating": star_rating(review.field_feedback) if ready else None,
        "is_slow_pending": _is_slow(review, now),
        "submission_version_number": review.submission_version_number,
        "error_detail": LEARNER_FAILURE_DETAIL if review.status == CurieReview.STATUS_FAILED else "",
        "requested_at": review.requested_at,
        "completed_at": review.completed_at,
    }


def staff_review_payload(review: CurieReview, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or timezone.now()
    ready = review.status == CurieReview.STATUS_READY
    gate = review.gate_criterion_scores or []
    payload = learner_review_payload(review, now=now)
    payload.update(
        {
            "trigger_id": str(review.trigger_id),
            "gate_criterion_scores": gate if ready else [],
            "gate_score": average_criterion_scores(gate) if ready and gate else None,
            "criterion_wise_scores": criterion_wise_scores(review.field_feedback) if ready else {},
            "field_feedback": staff_field_entries(review.field_feedback) if ready else [],
            "error_detail": review.error_detail if review.status == CurieReview.STATUS_FAILED else "",
            "instructor_form_locked": instructor_form_locked(review_status=review.status),
        }
    )
    return payload


def submission_curie_fields(submission: Submission, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or timezone.now()
    reviews = reviews_for(submission)
    current = resolve_review_for_read(submission, now=now)
    reviews = reviews_for(submission)
    return {
        "curie_review_status": current.status if current else None,
        "is_slow_pending": _is_slow(current, now) if current else False,
        "submission_attempt_count": attempt_count(reviews),
        "at_max_attempts": is_at_attempt_cap(reviews),
    }


def history_curie_summaries(submission: Submission, *, now: datetime | None = None) -> dict[int, dict[str, Any]]:
    now = now or timezone.now()
    summaries = {}
    for review in list(reviews_for(submission)):
        resolved = persist_timeout_if_due(review, now=now)
        if resolved is None:
            continue
        ready = resolved.status == CurieReview.STATUS_READY
        summaries[resolved.submission_version_number] = {
            "status": resolved.status,
            "verdict": resolved.verdict if ready else None,
            "star_rating": star_rating(resolved.field_feedback) if ready else None,
        }
    submission._curie_reviews_cache = None
    return summaries


def attempt_numbers_for_versions(version_numbers: list[int]) -> dict[int, int]:
    ordered = sorted(version_numbers)
    return {number: index + 1 for index, number in enumerate(ordered)}


def instructor_queue_curie_fields(submission: Submission) -> dict[str, Any]:
    status = getattr(submission, "curie_review_status", None)
    if status is None:
        review = current_review(submission)
        status = review.status if review else None
    return {
        "curie_review_status": status,
        "feedback_source": feedback_source_for(submission),
        "instructor_form_locked": instructor_form_locked(review_status=status),
    }
