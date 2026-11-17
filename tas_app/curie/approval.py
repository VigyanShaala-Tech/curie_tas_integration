"""Instructor approval: release stored CURIE output to the learner, unchanged or edited."""

from __future__ import annotations

import logging
from typing import Any, Callable

from django.db import transaction
from django.utils import timezone

from tas_app.curie.constants import (
    APPROVAL_ACTION_APPROVE,
    APPROVAL_ACTION_OVERRIDE,
    SOURCE_CURIE,
    SOURCE_HUMAN,
    STATUS_APPROVED,
    STATUS_READY_FOR_APPROVAL,
)
from tas_app.curie.projection import apply_feedback, sanitize_overall_feedback
from tas_app.curie.scoring import compute_verdict, instructor_rubric_entries
from tas_app.curie.settings import component_pass_threshold
from tas_app.curie.transitions import projected_submission_status
from tas_app.curie.validation import (
    CallbackValidationError,
    validate_criterion_scores,
    validate_field_feedback,
)
from tas_app.models import CurieReview, Submission

logger = logging.getLogger(__name__)

APPROVAL_ACTIONS = (APPROVAL_ACTION_APPROVE, APPROVAL_ACTION_OVERRIDE)


class CurieApprovalError(Exception):
    """Mapped to an HTTP error by the approval view."""

    def __init__(self, detail: str, status_code: int = 409, code: str = "conflict"):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.code = code


def _override_content(review: CurieReview, data: dict[str, Any]) -> tuple[list, list, str]:
    """Merge instructor edits onto the stored CURIE output and validate the result."""
    stored_fields = review.field_feedback or []
    stored_by_id = {item["field_id"]: item for item in stored_fields}

    edits = data.get("field_feedback")
    if edits is None:
        edits = []
    if not isinstance(edits, list):
        raise CurieApprovalError("field_feedback must be a list.", status_code=400, code="invalid")
    edits_by_id = {}
    for index, raw in enumerate(edits):
        if not isinstance(raw, dict) or not isinstance(raw.get("field_id"), str):
            raise CurieApprovalError(
                f"field_feedback[{index}].field_id is required.", status_code=400, code="invalid"
            )
        if raw["field_id"] not in stored_by_id:
            raise CurieApprovalError(
                f"field_id {raw['field_id']!r} is not part of this CURIE review.",
                status_code=400,
                code="invalid",
            )
        edits_by_id[raw["field_id"]] = raw

    merged = []
    for stored in stored_fields:
        edit = edits_by_id.get(stored["field_id"], {})
        merged.append(
            {
                "field_id": stored["field_id"],
                "weight": stored.get("weight", 1),
                "comment": edit.get("comment", stored.get("comment", "")),
                "criterion_scores": edit.get("criterion_scores", stored.get("criterion_scores")),
            }
        )

    overall = data.get("overall_feedback", review.overall_feedback)
    if not isinstance(overall, str) or not overall.strip():
        raise CurieApprovalError("overall_feedback is required.", status_code=400, code="invalid")

    try:
        gate = validate_criterion_scores(
            data.get("gate_criterion_scores", review.gate_criterion_scores),
            label="gate_criterion_scores",
        )
        fields = validate_field_feedback(merged, allowed_field_ids=list(stored_by_id))
    except CallbackValidationError as exc:
        raise CurieApprovalError(str(exc), status_code=400, code="invalid") from exc
    return gate, fields, overall


def _same_content(review: CurieReview, gate, fields, overall) -> bool:
    return (
        review.approved_gate_criterion_scores == gate
        and review.approved_field_feedback == fields
        and review.approved_overall_feedback == overall
    )


def _differs_from_curie(review: CurieReview, gate, fields, overall) -> bool:
    try:
        stored_gate = validate_criterion_scores(review.gate_criterion_scores, label="gate")
        stored_fields = validate_field_feedback(review.field_feedback)
    except CallbackValidationError:
        return True
    return stored_gate != gate or stored_fields != fields or review.overall_feedback != overall


def approve_curie_review(
    *,
    submission_id,
    instructor,
    action: str,
    submission_version_number,
    trigger_id: str | None = None,
    data: dict[str, Any] | None = None,
    after_release: Callable[[CurieReview, Submission], None] | None = None,
) -> tuple[str, CurieReview]:
    """
    Release a ready_for_approval review. Returns ("approved" | "already_approved", review).

    Locks the submission row, then the review, matching callback and submit lock order.
    Replaying the same approval is a no-op; any other second approval is a conflict.
    """
    data = data or {}
    if action not in APPROVAL_ACTIONS:
        raise CurieApprovalError(
            f"action must be one of {list(APPROVAL_ACTIONS)}.", status_code=400, code="invalid"
        )
    if isinstance(submission_version_number, bool) or not isinstance(submission_version_number, int):
        raise CurieApprovalError(
            "submission_version_number must be an integer.", status_code=400, code="invalid"
        )

    with transaction.atomic():
        try:
            submission = (
                Submission.objects.select_for_update()
                .select_related("template_block__rubric", "student")
                .get(pk=submission_id)
            )
        except Submission.DoesNotExist as exc:
            raise CurieApprovalError("Submission not found.", status_code=404, code="not_found") from exc

        review = (
            CurieReview.objects.select_for_update()
            .filter(submission=submission, submission_version_number=submission_version_number)
            .first()
        )
        if review is None:
            raise CurieApprovalError("CURIE review not found.", status_code=404, code="not_found")
        if trigger_id and str(review.trigger_id) != str(trigger_id):
            raise CurieApprovalError(
                "trigger_id does not match this submission version.", status_code=409, code="stale"
            )
        if int(submission_version_number) != int(submission.version_number):
            raise CurieApprovalError(
                "This review belongs to an older attempt and cannot be approved.",
                status_code=409,
                code="stale",
            )
        if review.status not in (STATUS_READY_FOR_APPROVAL, STATUS_APPROVED):
            raise CurieApprovalError(
                f"CURIE review is not awaiting approval (status={review.status}).",
                status_code=409,
                code="not_ready",
            )

        if action == APPROVAL_ACTION_APPROVE:
            source = SOURCE_CURIE
            gate = review.gate_criterion_scores
            fields = review.field_feedback
            overall = review.overall_feedback
        else:
            source = SOURCE_HUMAN
            gate, fields, overall = _override_content(review, data)

        if review.status == STATUS_APPROVED:
            if review.published_source == source and (
                action == APPROVAL_ACTION_APPROVE or _same_content(review, gate, fields, overall)
            ):
                return "already_approved", review
            raise CurieApprovalError(
                "This CURIE review has already been approved.", status_code=409, code="already_approved"
            )

        verdict = compute_verdict(gate, fields, threshold=component_pass_threshold())
        modified = action == APPROVAL_ACTION_OVERRIDE and _differs_from_curie(review, gate, fields, overall)

        review.status = STATUS_APPROVED
        review.approved_by = instructor
        review.approved_at = timezone.now()
        review.approval_modified = modified
        review.published_source = source
        review.approved_verdict = verdict
        review.approved_gate_criterion_scores = gate
        review.approved_field_feedback = fields
        review.approved_overall_feedback = overall
        review.save()

        apply_feedback(
            submission,
            source=source,
            instructor=instructor if source == SOURCE_HUMAN else None,
            rubrics=instructor_rubric_entries(fields),
            comment=sanitize_overall_feedback(overall),
            status=projected_submission_status(verdict),
            after_commit=(lambda: after_release(review, submission)) if after_release else None,
        )
        logger.info(
            "CURIE review approved trigger_id=%s action=%s verdict=%s modified=%s",
            review.trigger_id,
            action,
            verdict,
            modified,
        )
    return "approved", review
