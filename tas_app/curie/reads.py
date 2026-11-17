"""CURIE read payloads and batched history summaries."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.utils import timezone

from tas_app.curie.constants import LEARNER_FAILURE_DETAIL, OUTPUT_STATUSES, SOURCE_CURIE
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


def published_source(review: CurieReview) -> str | None:
    if review.status == CurieReview.STATUS_APPROVED:
        return review.published_source or SOURCE_CURIE
    if review.status == CurieReview.STATUS_READY:
        return SOURCE_CURIE
    return None


def learner_review_payload(review: CurieReview, *, now: datetime | None = None) -> dict[str, Any]:
    """Learner view. Content stays empty until the review is published."""
    now = now or timezone.now()
    published = review.published_content()
    verdict, _gate, fields, overall = published or (None, [], [], "")
    return {
        "status": review.status,
        "verdict": verdict,
        "overall_feedback": overall,
        "field_feedback": learner_field_entries(fields) if published else [],
        "star_rating": star_rating(fields) if published else None,
        "feedback_source": published_source(review),
        "approval_modified": bool(review.approval_modified) if published else False,
        "is_slow_pending": _is_slow(review, now),
        "submission_version_number": review.submission_version_number,
        "error_detail": LEARNER_FAILURE_DETAIL if review.status == CurieReview.STATUS_FAILED else "",
        "requested_at": review.requested_at,
        "completed_at": review.completed_at,
    }


def _approval_payload(review: CurieReview) -> dict[str, Any] | None:
    if review.status != CurieReview.STATUS_APPROVED:
        return None
    gate = review.approved_gate_criterion_scores or []
    fields = review.approved_field_feedback or []
    approver = review.approved_by
    return {
        "approved_by": approver.username if approver else None,
        "approved_at": review.approved_at,
        "approval_modified": review.approval_modified,
        "published_source": published_source(review),
        "verdict": review.approved_verdict,
        "overall_feedback": review.approved_overall_feedback,
        "gate_criterion_scores": gate,
        "gate_score": average_criterion_scores(gate) if gate else None,
        "criterion_wise_scores": criterion_wise_scores(fields),
        "field_feedback": staff_field_entries(fields),
        "star_rating": star_rating(fields),
    }


def staff_review_payload(review: CurieReview, *, now: datetime | None = None) -> dict[str, Any]:
    """Instructor view: the original CURIE output once evaluated, plus approval details."""
    now = now or timezone.now()
    has_output = review.status in OUTPUT_STATUSES
    gate = review.gate_criterion_scores or []
    payload = learner_review_payload(review, now=now)
    payload.update(
        {
            "trigger_id": str(review.trigger_id),
            "verdict": review.verdict if has_output else None,
            "overall_feedback": review.overall_feedback if has_output else "",
            "star_rating": star_rating(review.field_feedback) if has_output else None,
            "gate_criterion_scores": gate if has_output else [],
            "gate_score": average_criterion_scores(gate) if has_output and gate else None,
            "criterion_wise_scores": criterion_wise_scores(review.field_feedback) if has_output else {},
            "field_feedback": staff_field_entries(review.field_feedback) if has_output else [],
            "error_detail": review.error_detail if review.status == CurieReview.STATUS_FAILED else "",
            "instructor_form_locked": instructor_form_locked(review_status=review.status),
            "awaiting_approval": review.status == CurieReview.STATUS_READY_FOR_APPROVAL,
            "approval": _approval_payload(review),
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
        published = resolved.published_content()
        summaries[resolved.submission_version_number] = {
            "status": resolved.status,
            "verdict": published[0] if published else None,
            "star_rating": star_rating(published[2]) if published else None,
            "feedback_source": published_source(resolved),
        }
    submission._curie_reviews_cache = None
    return summaries


def attempt_numbers_for_versions(version_numbers: list[int]) -> dict[int, int]:
    ordered = sorted(version_numbers)
    return {number: index + 1 for index, number in enumerate(ordered)}


def instructor_queue_curie_fields(submission: Submission) -> dict[str, Any]:
    status = getattr(submission, "curie_review_status", None)
    source = getattr(submission, "curie_published_source", None)
    if status is None:
        review = current_review(submission)
        status = review.status if review else None
        source = review.published_source if review else None
    if status == CurieReview.STATUS_READY_FOR_APPROVAL:
        feedback_source = SOURCE_CURIE
    elif status == CurieReview.STATUS_APPROVED:
        feedback_source = source or SOURCE_CURIE
    else:
        feedback_source = feedback_source_for(submission)
    return {
        "curie_review_status": status,
        "feedback_source": feedback_source,
        "instructor_form_locked": instructor_form_locked(review_status=status),
    }
