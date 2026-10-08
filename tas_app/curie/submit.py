"""Atomic final-submit orchestration for CURIE-eligible assignments."""

from __future__ import annotations

import logging
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from tas_app.curie.constants import MAX_SUBMISSION_ATTEMPTS
from tas_app.curie.settings import curie_enabled, validate_curie_settings
from tas_app.curie.transitions import (
    attempt_count,
    human_owns_projection,
    is_at_attempt_cap,
    is_curie_eligible,
    legal_curie_resubmit,
)
from tas_app.curie.trigger import enqueue_trigger
from tas_app.models import CurieReview, InstructorFeedback, Submission
from tas_app.pdf_generator import generate_submission_pdf

logger = logging.getLogger(__name__)


class CurieSubmitError(Exception):
    """Mapped to an HTTP error by the submit view. Does not leak internals."""

    def __init__(self, detail: str, status_code: int = 409, extra: dict[str, Any] | None = None):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.extra = extra or {}


def _assignment_type(submission: Submission) -> str | None:
    return submission.template_block.template.template_type.slug


def _is_curie_path(submission: Submission) -> bool:
    return is_curie_eligible(
        global_enabled=curie_enabled(),
        block_enabled=submission.template_block.curie_enabled,
        assignment_type=_assignment_type(submission),
    )


def _feedback_source(submission: Submission) -> str | None:
    try:
        return submission.feedback.source
    except InstructorFeedback.DoesNotExist:
        return None


def _current_review(submission: Submission) -> CurieReview | None:
    return submission.curie_reviews.filter(submission_version_number=submission.version_number).first()


def _apply_form_data(submission: Submission, form_data: Any, *, required: bool) -> None:
    if form_data is None:
        if required:
            raise CurieSubmitError("form_data is required.", status_code=400)
        return
    if not isinstance(form_data, dict):
        raise CurieSubmitError("form_data must be an object.", status_code=400)
    submission.form_data = form_data


def _bump_to_submitted(submission: Submission) -> None:
    submission.status = Submission.STATUS_SUBMITTED
    submission.version_number += 1
    submission.submitted_at = timezone.now()
    submission.save()
    try:
        generate_submission_pdf(submission)
    except Exception as exc:  # noqa: BLE001
        logger.warning("PDF generation failed for submission %s: %s", submission.pk, exc)
    submission.create_version_snapshot(include_pdf=True)


def _legacy_finalize(submission: Submission, form_data: Any) -> Submission:
    if submission.status == Submission.STATUS_SUBMITTED:
        raise CurieSubmitError("This submission is already submitted.")
    _apply_form_data(submission, form_data, required=False)
    _bump_to_submitted(submission)
    return submission


def _curie_conflict_message(submission: Submission, review_status: str | None, feedback_source: str | None) -> str:
    if human_owns_projection(feedback_source):
        return "CURIE reattempt is not available for human-graded submissions."
    if submission.status == Submission.STATUS_APPROVED:
        return "Accepted submissions cannot be resubmitted."
    if submission.status == Submission.STATUS_SUBMITTED:
        return "This submission is already submitted."
    return "This submission cannot be submitted."


def _curie_finalize(submission: Submission, form_data: Any, *, request=None) -> Submission:
    validate_curie_settings(enabled=True)
    reviews = list(submission.curie_reviews.all())
    current = _current_review(submission)
    review_status = current.status if current is not None else None
    feedback_source = _feedback_source(submission)

    if not legal_curie_resubmit(
        submission_status=submission.status,
        review_status=review_status,
        feedback_source=feedback_source,
    ):
        raise CurieSubmitError(_curie_conflict_message(submission, review_status, feedback_source))

    if is_at_attempt_cap(reviews):
        raise CurieSubmitError(
            "Submission attempt cap reached.",
            extra={
                "attempt_count": attempt_count(reviews),
                "max_attempts": MAX_SUBMISSION_ATTEMPTS,
            },
        )

    _apply_form_data(submission, form_data, required=True)
    _bump_to_submitted(submission)

    try:
        review = CurieReview.objects.create(
            submission=submission,
            submission_version_number=submission.version_number,
        )
    except IntegrityError:
        raise CurieSubmitError("This submission is already submitted.")
    enqueue_trigger(review, submission, request=request)
    return submission


def submit_student_submission(
    *,
    pk,
    student,
    form_data: Any = None,
    request=None,
) -> Submission:
    """
    Lock the submission row, persist authoritative form_data on the CURIE path,
    then either run the CURIE atomic path or the legacy finalize path.
    """
    with transaction.atomic():
        try:
            submission = (
                Submission.objects.select_related("template_block__template__template_type")
                .select_for_update()
                .get(pk=pk, student=student)
            )
        except Submission.DoesNotExist:
            raise

        if _is_curie_path(submission):
            return _curie_finalize(submission, form_data, request=request)
        return _legacy_finalize(submission, form_data)
