"""Build and send the TAS → CURIE assessment-review trigger."""

from __future__ import annotations

import logging
from typing import Any

import requests
from django.db import transaction

from tas_app.curie.constants import ORIGIN_TAS
from tas_app.curie.metrics import record_trigger_accepted
from tas_app.curie.settings import (
    auth_header_name,
    callback_base_url,
    connect_timeout_seconds,
    curie_enabled,
    response_timeout_seconds,
    shared_secret,
    trigger_url,
    validate_curie_settings,
)
from tas_app.curie.transitions import is_curie_eligible
from tas_app.models import CurieReview, Submission

logger = logging.getLogger(__name__)


class RetryableTriggerError(Exception):
    """Connection, timeout, 429, or 5xx — TAS retries with the same trigger_id."""


class TerminalTriggerError(Exception):
    """Non-retryable 4xx. Do not retry; fail the pending review."""


def _field_answer(form_data: dict[str, Any], field_id: str) -> str:
    value = form_data.get(field_id, "")
    if isinstance(value, dict):
        answer = value.get("answer", "")
        return answer if isinstance(answer, str) else str(answer or "")
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def build_trigger_form_data(submission: Submission) -> dict[str, dict[str, str]]:
    """Map TAS string answers onto the CURIE {label, answer} objects."""
    template = submission.template_block.template
    form_data = submission.form_data or {}
    fields = template.active_fields() if hasattr(template, "active_fields") else template.fields or []
    payload = {}
    for field in fields:
        field_id = str(field.get("id") or field.get("key") or field.get("name") or "")
        if not field_id:
            continue
        payload[field_id] = {
            "label": str(field.get("label") or field_id),
            "answer": _field_answer(form_data, field_id),
        }
    if payload:
        return payload
    for field_id, value in form_data.items():
        payload[str(field_id)] = {
            "label": str(field_id),
            "answer": _field_answer(form_data, str(field_id)),
        }
    return payload


def build_callback_url(trigger_id, *, request=None) -> str:
    base = callback_base_url().rstrip("/")
    if not base and request is not None:
        base = request.build_absolute_uri("/").rstrip("/")
    if not base:
        raise ValueError("CURIE callback base URL is missing.")
    return f"{base}/tas/api/v1/curie/reviews/{trigger_id}/callback/"


def build_trigger_payload(
    review: CurieReview,
    submission: Submission,
    *,
    request=None,
    callback_url: str | None = None,
) -> dict[str, Any]:
    return {
        "trigger_id": str(review.trigger_id),
        "user_id": str(submission.student_id),
        "origin": ORIGIN_TAS,
        "user_query": None,
        "assignment_type": submission.template_block.template.template_type.slug,
        "assignment_id": str(submission.template_block_id),
        "submission_id": str(submission.id),
        "submission_version_number": int(review.submission_version_number),
        "course_id": str(submission.course_key),
        "usage_key": str(submission.usage_key),
        "form_data": build_trigger_form_data(submission),
        "callback_url": callback_url or build_callback_url(review.trigger_id, request=request),
    }


def send_trigger(payload: dict[str, Any]) -> int:
    """POST the exact trigger URL once. Classify transport and HTTP failures for the task."""
    headers = {
        auth_header_name(): shared_secret(),
        "Content-Type": "application/json",
    }
    timeout = (connect_timeout_seconds(), response_timeout_seconds())
    try:
        response = requests.post(trigger_url(), json=payload, headers=headers, timeout=timeout)
    except (requests.ConnectionError, requests.Timeout) as exc:
        raise RetryableTriggerError(str(exc) or exc.__class__.__name__) from exc
    status_code = response.status_code
    if status_code < 400:
        logger.info(
            "CURIE trigger accepted trigger_id=%s status=%s",
            payload.get("trigger_id"),
            status_code,
        )
        record_trigger_accepted()
        return status_code
    logger.warning(
        "CURIE trigger rejected trigger_id=%s status=%s",
        payload.get("trigger_id"),
        status_code,
    )
    if status_code == 429 or status_code >= 500:
        raise RetryableTriggerError(f"HTTP {status_code}")
    raise TerminalTriggerError(f"HTTP {status_code}")


def maybe_start_curie_review(submission: Submission, *, request=None) -> CurieReview | None:
    """Create a pending CurieReview and enqueue the trigger when this block is eligible."""
    if not curie_enabled():
        return None
    validate_curie_settings(enabled=True)
    block = submission.template_block
    assignment_type = block.template.template_type.slug
    if not is_curie_eligible(
        global_enabled=True,
        block_enabled=block.curie_enabled,
        assignment_type=assignment_type,
    ):
        return None

    review = CurieReview.objects.create(
        submission=submission,
        submission_version_number=submission.version_number,
    )
    enqueue_trigger(review, submission, request=request)
    return review


def enqueue_trigger(review: CurieReview, submission: Submission, *, request=None) -> None:
    """Freeze the canonical trigger body, then enqueue Celery delivery after commit."""
    payload = build_trigger_payload(review, submission, request=request)
    review.trigger_payload = payload
    review.save(update_fields=["trigger_payload", "modified"])
    trigger_id = str(review.trigger_id)

    def _enqueue():
        from tas_app.curie.celery_tasks import deliver_curie_trigger

        deliver_curie_trigger.delay(trigger_id)

    transaction.on_commit(_enqueue)
