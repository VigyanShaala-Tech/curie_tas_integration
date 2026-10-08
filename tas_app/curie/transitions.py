"""Explicit CURIE lifecycle predicates. Callers must not scatter raw status checks."""

from __future__ import annotations

from typing import Any

from tas_app.curie.constants import (
    ASSIGNMENT_TYPE_SWOT,
    ELIGIBLE_ASSIGNMENT_TYPES,
    MAX_SUBMISSION_ATTEMPTS,
    SOURCE_CURIE,
    SOURCE_HUMAN,
    STATUS_FAILED,
    STATUS_PENDING_EVALUATION,
    VERDICT_ACCEPTED,
    VERDICT_REJECTED,
)

SUBMISSION_DRAFT = "draft"
SUBMISSION_SUBMITTED = "submitted"
SUBMISSION_APPROVED = "approved"
SUBMISSION_REJECTED = "rejected"


def is_curie_enabled(*, global_enabled: bool, block_enabled: bool) -> bool:
    return bool(global_enabled) and bool(block_enabled)


def is_assignment_type_eligible(assignment_type: str | None) -> bool:
    return assignment_type in ELIGIBLE_ASSIGNMENT_TYPES


def is_curie_eligible(
    *,
    global_enabled: bool,
    block_enabled: bool,
    assignment_type: str | None,
) -> bool:
    return (
        is_curie_enabled(global_enabled=global_enabled, block_enabled=block_enabled)
        and is_assignment_type_eligible(assignment_type)
    )


def attempt_count(reviews: list[Any]) -> int:
    """Count attempts that consume the cap. Failed reviews do not count."""
    return sum(1 for review in reviews if getattr(review, "status", review) != STATUS_FAILED)


def is_at_attempt_cap(reviews: list[Any], *, max_attempts: int = MAX_SUBMISSION_ATTEMPTS) -> bool:
    return attempt_count(reviews) >= max_attempts


def human_owns_projection(feedback_source: str | None, feedback_status: str | None = None) -> bool:
    """Human ownership is permanent, including after withdraw back to pending."""
    return feedback_source == SOURCE_HUMAN


def can_withdraw_feedback(feedback_source: str | None) -> bool:
    """CURIE-authored projections cannot be withdrawn. Human-authored ones can."""
    return feedback_source != SOURCE_CURIE


def is_stale_version(callback_version: int, current_version: int) -> bool:
    return int(callback_version) != int(current_version)


def can_apply_curie_projection(
    *,
    review_status: str,
    callback_version: int,
    current_version: int,
    feedback_source: str | None,
    feedback_status: str | None,
) -> bool:
    if is_stale_version(callback_version, current_version):
        return False
    if human_owns_projection(feedback_source, feedback_status):
        return False
    return review_status in (STATUS_PENDING_EVALUATION, STATUS_FAILED)


def legal_curie_resubmit(
    *,
    submission_status: str,
    review_status: str | None,
    feedback_source: str | None,
) -> bool:
    """Direct reattempt is allowed from draft, CURIE-failed submitted, or CURIE-rejected.

    Human ownership is permanent: any ``source=human`` projection blocks CURIE submit,
    including draft and submitted/failed after withdraw. No feedback row is first submit.
    """
    if human_owns_projection(feedback_source):
        return False
    if submission_status == SUBMISSION_APPROVED:
        return False
    if submission_status == SUBMISSION_DRAFT:
        return True
    if submission_status == SUBMISSION_SUBMITTED and review_status == STATUS_FAILED:
        return True
    if submission_status == SUBMISSION_REJECTED and feedback_source == SOURCE_CURIE:
        return True
    return False


def instructor_form_locked(*, review_status: str | None) -> bool:
    return review_status == STATUS_PENDING_EVALUATION


def projected_submission_status(verdict: str) -> str:
    if verdict == VERDICT_ACCEPTED:
        return SUBMISSION_APPROVED
    if verdict == VERDICT_REJECTED:
        return SUBMISSION_REJECTED
    raise ValueError(f"Unknown verdict {verdict!r}.")


def swot_release_assignment_type() -> str:
    return ASSIGNMENT_TYPE_SWOT
