"""Shared InstructorFeedback projection for CURIE and human grading."""

from __future__ import annotations

from typing import Any, Callable

from django.db import transaction
from django.utils import timezone

from tas_app.curie.constants import SOURCE_CURIE, SOURCE_HUMAN, STATUS_READY
from tas_app.curie.scoring import compute_verdict, instructor_rubric_entries
from tas_app.curie.settings import component_pass_threshold
from tas_app.curie.transitions import projected_submission_status
from tas_app.models import STATUS_APPROVED, STATUS_REJECTED, InstructorFeedback, Submission
from tas_app.utils.student_feedback import is_category_heading_line


def sanitize_overall_feedback(text: str) -> str:
    """Drop colon-ending heading lines so XBlock/MFE filters cannot hide CURIE copy."""
    kept = []
    for line in (text or "").splitlines():
        if is_category_heading_line(line):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def build_curie_projection(field_feedback, overall_feedback: str, verdict: str) -> dict[str, Any]:
    return {
        "source": SOURCE_CURIE,
        "instructor": None,
        "rubrics": instructor_rubric_entries(field_feedback),
        "comment": sanitize_overall_feedback(overall_feedback),
        "status": projected_submission_status(verdict),
    }


def apply_feedback(
    submission: Submission,
    *,
    source: str,
    instructor,
    rubrics,
    comment: str,
    status: str,
    snapshot: bool = True,
    after_commit: Callable[[], None] | None = None,
) -> InstructorFeedback:
    """
    Persist InstructorFeedback, submission status, and a version snapshot.

    Grade publication and other external IO must be passed as after_commit.
    """
    with transaction.atomic():
        feedback, _created = InstructorFeedback.objects.update_or_create(
            submission=submission,
            defaults={
                "source": source,
                "instructor": instructor,
                "rubrics": rubrics,
                "comment": comment,
                "status": status,
            },
        )
        if status in (STATUS_APPROVED, STATUS_REJECTED):
            submission.status = status
            submission.save(update_fields=["status", "modified"])
        if snapshot:
            feedback.create_version_snapshot()
        if after_commit is not None:
            transaction.on_commit(after_commit)
    return feedback


def apply_curie_success(review, submission: Submission, payload: dict[str, Any], *, after_commit=None):
    """Write CurieReview success fields and the one-way InstructorFeedback projection."""
    verdict = compute_verdict(
        payload["gate_criterion_scores"],
        payload["field_feedback"],
        threshold=component_pass_threshold(),
    )
    projection = build_curie_projection(payload["field_feedback"], payload["overall_feedback"], verdict)
    now = timezone.now()
    with transaction.atomic():
        review.status = STATUS_READY
        review.verdict = verdict
        review.gate_criterion_scores = payload["gate_criterion_scores"]
        review.field_feedback = payload["field_feedback"]
        review.overall_feedback = payload["overall_feedback"]
        review.error_detail = ""
        review.completed_at = now
        review.save()
        apply_feedback(
            submission,
            source=SOURCE_CURIE,
            instructor=None,
            rubrics=projection["rubrics"],
            comment=projection["comment"],
            status=projection["status"],
            after_commit=after_commit,
        )
    return review


def apply_human_feedback(submission: Submission, *, instructor, rubrics, comment, status, after_commit=None):
    return apply_feedback(
        submission,
        source=SOURCE_HUMAN,
        instructor=instructor,
        rubrics=rubrics,
        comment=comment,
        status=status,
        after_commit=after_commit,
    )
