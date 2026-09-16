"""Write-path guards so legacy TAS endpoints cannot bypass the CURIE state machine."""

from __future__ import annotations

from typing import Any

from tas_app.curie.settings import curie_enabled
from tas_app.curie.timeout import persist_timeout_if_due
from tas_app.curie.transitions import (
    can_withdraw_feedback,
    instructor_form_locked,
    is_at_attempt_cap,
    is_curie_eligible,
)
from tas_app.models import InstructorFeedback, Submission


class CuriePolicyError(Exception):
    """Mapped to an HTTP error by the calling view."""

    def __init__(self, detail: str, status_code: int = 409):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def assignment_type_for_block(block: Any) -> str | None:
    try:
        return block.template.template_type.slug
    except Exception:  # noqa: BLE001
        return None


def is_block_curie_eligible(block: Any) -> bool:
    if block is None:
        return False
    return is_curie_eligible(
        global_enabled=curie_enabled(),
        block_enabled=bool(getattr(block, "curie_enabled", False)),
        assignment_type=assignment_type_for_block(block),
    )


def is_submission_curie_eligible(submission: Submission) -> bool:
    return is_block_curie_eligible(getattr(submission, "template_block", None))


def feedback_source_for(submission: Submission) -> str | None:
    try:
        return submission.feedback.source
    except InstructorFeedback.DoesNotExist:
        return None


def current_review(submission: Submission, version_number: int | None = None):
    version = submission.version_number if version_number is None else int(version_number)
    return submission.curie_reviews.filter(submission_version_number=version).first()


def assert_create_status_allowed(block: Any, new_status: str) -> None:
    """CURIE-eligible blocks cannot Create with status=submitted; they must POST /submit/."""
    if new_status != Submission.STATUS_SUBMITTED:
        return
    if is_block_curie_eligible(block):
        raise CuriePolicyError(
            "CURIE submissions must use the submit endpoint.",
            status_code=409,
        )


def assert_student_patch_allowed(submission: Submission, *, is_reopen: bool) -> None:
    """Block approved/rejected → draft except legacy human reopen, and cap-gate reopen."""
    if is_reopen:
        if not is_submission_curie_eligible(submission):
            return
        reviews = list(submission.curie_reviews.all())
        if is_at_attempt_cap(reviews):
            raise CuriePolicyError(
                "Maximum CURIE submission attempts reached.",
                status_code=409,
            )
        if feedback_source_for(submission) == InstructorFeedback.SOURCE_CURIE:
            raise CuriePolicyError(
                "CURIE-owned feedback cannot be reopened. Resubmit instead.",
                status_code=409,
            )
        return

    if submission.status in (Submission.STATUS_APPROVED, Submission.STATUS_REJECTED):
        raise CuriePolicyError(
            "Cannot return an approved or rejected submission to draft.",
            status_code=409,
        )


def assert_curie_feedback_withdrawable(submission: Submission) -> None:
    source = feedback_source_for(submission)
    if not can_withdraw_feedback(source):
        raise CuriePolicyError(
            "CURIE-owned feedback cannot be withdrawn.",
            status_code=403,
        )


def assert_instructor_form_unlocked(submission: Submission) -> None:
    review = persist_timeout_if_due(current_review(submission))
    status = review.status if review is not None else None
    if instructor_form_locked(review_status=status):
        raise CuriePolicyError(
            "CURIE is still reviewing this submission.",
            status_code=409,
        )
