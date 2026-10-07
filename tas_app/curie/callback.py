"""Apply an authenticated CURIE callback to CurieReview and the one-way projection."""

from __future__ import annotations

import hmac
import logging

from django.db import transaction
from django.utils import timezone

from tas_app.curie.constants import (
    HUMAN_SUPERSEDED_DETAIL,
    RESULT_ERROR,
    RESULT_SUCCESS,
    STATUS_FAILED,
    STATUS_PENDING_EVALUATION,
    STATUS_READY,
    VERDICT_ACCEPTED,
)
from tas_app.curie.metrics import record_callback_outcome
from tas_app.curie.projection import apply_curie_success
from tas_app.curie.settings import auth_header_name, shared_secret
from tas_app.curie.transitions import can_apply_curie_projection, human_owns_projection
from tas_app.curie.validation import CallbackValidationError, validate_callback_payload
from tas_app.models import CurieReview, InstructorFeedback, Submission

logger = logging.getLogger(__name__)

OUTCOME_HTTP_STATUS = {
    "applied": 200,
    "replayed": 200,
    "superseded": 200,
    "failed": 200,
    "stale": 409,
    "conflict": 409,
}


def header_secret_matches(request) -> bool:
    expected = shared_secret().strip()
    supplied = (request.headers.get(auth_header_name()) or "").strip()
    if not expected or not supplied:
        return False
    expected_bytes = expected.encode("utf-8")
    supplied_bytes = supplied.encode("utf-8")
    if len(expected_bytes) != len(supplied_bytes):
        hmac.compare_digest(expected_bytes, expected_bytes)
        return False
    return hmac.compare_digest(supplied_bytes, expected_bytes)


def submitted_field_ids(review: CurieReview) -> list[str]:
    """Return field IDs from the immutable payload issued for this review."""
    form_data = (review.trigger_payload or {}).get("form_data")
    if not isinstance(form_data, dict):
        return []
    return [str(field_id) for field_id in form_data if str(field_id)]


def _feedback_source_and_status(submission) -> tuple[str | None, str | None]:
    try:
        feedback = submission.feedback
    except InstructorFeedback.DoesNotExist:
        return None, None
    return feedback.source, feedback.status


def _success_matches_stored(review: CurieReview, payload: dict) -> bool:
    return (
        review.status == STATUS_READY
        and payload["result"] == RESULT_SUCCESS
        and review.gate_criterion_scores == payload["gate_criterion_scores"]
        and review.field_feedback == payload["field_feedback"]
        and review.overall_feedback == payload["overall_feedback"]
    )


def _record_superseded(review: CurieReview) -> str:
    if HUMAN_SUPERSEDED_DETAIL not in (review.error_detail or ""):
        detail = HUMAN_SUPERSEDED_DETAIL
        if review.error_detail:
            detail = f"{review.error_detail}\n{HUMAN_SUPERSEDED_DETAIL}"
        review.error_detail = detail
        review.save(update_fields=["error_detail", "modified"])
    logger.info("CURIE callback superseded trigger_id=%s", review.trigger_id)
    record_callback_outcome("superseded")
    return "superseded"


def apply_callback(review: CurieReview, raw_payload: dict, *, after_success=None) -> str:
    """
    Return applied, replayed, superseded, failed, stale, or conflict.

    Locks the submission row first, then the review, to match submit lock order.
    """
    payload = None
    with transaction.atomic():
        submission = Submission.objects.select_for_update().select_related(
            "template_block__template",
            "template_block__rubric",
            "student",
        ).get(pk=review.submission_id)
        review = (
            CurieReview.objects.select_for_update()
            .select_related("submission")
            .get(pk=review.pk)
        )

        allowed_ids = submitted_field_ids(review)
        if raw_payload.get("result") == RESULT_SUCCESS and not allowed_ids:
            raise CallbackValidationError("Stored trigger payload has no submitted field IDs.")
        payload = validate_callback_payload(
            raw_payload,
            allowed_field_ids=allowed_ids or None,
        )

        if str(payload["trigger_id"]) != str(review.trigger_id):
            raise CallbackValidationError("trigger_id does not match the callback URL.")
        if str(payload["submission_id"]) != str(submission.id):
            raise CallbackValidationError("submission_id does not match the stored review.")
        if str(payload["user_id"]) != str(submission.student_id):
            raise CallbackValidationError("user_id does not match the stored review.")

        callback_version = int(payload["submission_version_number"])
        if callback_version != int(review.submission_version_number) or callback_version != int(
            submission.version_number
        ):
            logger.info(
                "CURIE callback stale trigger_id=%s callback_version=%s current=%s review_version=%s",
                review.trigger_id,
                callback_version,
                submission.version_number,
                review.submission_version_number,
            )
            record_callback_outcome("stale")
            return "stale"

        if _success_matches_stored(review, payload):
            record_callback_outcome("replayed")
            return "replayed"

        if review.status == STATUS_READY:
            logger.info("CURIE callback conflict trigger_id=%s", review.trigger_id)
            record_callback_outcome("conflict")
            return "conflict"

        if payload["result"] == RESULT_ERROR:
            if review.status == STATUS_FAILED and review.error_detail == payload["error_message"]:
                record_callback_outcome("replayed")
                return "replayed"
            if review.status != STATUS_PENDING_EVALUATION:
                record_callback_outcome("conflict")
                return "conflict"
            review.status = STATUS_FAILED
            review.error_detail = payload["error_message"]
            review.completed_at = timezone.now()
            review.save(update_fields=["status", "error_detail", "completed_at", "modified"])
            logger.info("CURIE callback stored failure trigger_id=%s", review.trigger_id)
            record_callback_outcome("failed", requested_at=review.requested_at)
            return "failed"

        source, status = _feedback_source_and_status(submission)
        if human_owns_projection(source, status):
            return _record_superseded(review)

        if not can_apply_curie_projection(
            review_status=review.status,
            callback_version=callback_version,
            current_version=int(submission.version_number),
            feedback_source=source,
            feedback_status=status,
        ):
            logger.info("CURIE callback conflict trigger_id=%s", review.trigger_id)
            record_callback_outcome("conflict")
            return "conflict"

        def _after():
            if after_success is not None:
                after_success(review)

        apply_curie_success(
            review,
            submission,
            payload,
            after_commit=_after if after_success else None,
        )
        logger.info(
            "CURIE callback applied trigger_id=%s verdict=%s",
            review.trigger_id,
            review.verdict,
        )
        record_callback_outcome("applied", requested_at=review.requested_at)
        return "applied"


def should_push_grade(review: CurieReview) -> bool:
    return review.verdict == VERDICT_ACCEPTED and review.status == review.STATUS_READY
