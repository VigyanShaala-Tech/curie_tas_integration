"""Outbound CURIE trigger delivery: retries, exhaustion, and pending-review failure."""

from __future__ import annotations

import logging
import random

from celery.exceptions import MaxRetriesExceededError, Retry
from django.db import transaction
from django.utils import timezone

from tas_app.curie.constants import (
    STATUS_PENDING_EVALUATION,
    TRIGGER_EXHAUSTED_ERROR_DETAIL,
    TRIGGER_RETRY_COUNTDOWNS,
    TRIGGER_RETRY_JITTER_RATIO,
)
from tas_app.curie.metrics import record_trigger_exhausted, record_trigger_retried
from tas_app.curie.trigger import (
    RetryableTriggerError,
    TerminalTriggerError,
    build_trigger_payload,
    send_trigger,
)
from tas_app.models import CurieReview

logger = logging.getLogger(__name__)


def retry_countdown_seconds(retry_index: int, *, rng=random.random) -> float:
    """Jitter around 15s, then 60s, then 240s for retries 0, 1, 2."""
    base = TRIGGER_RETRY_COUNTDOWNS[min(max(retry_index, 0), len(TRIGGER_RETRY_COUNTDOWNS) - 1)]
    jitter = base * TRIGGER_RETRY_JITTER_RATIO
    return max(1.0, base + (rng() * 2 - 1) * jitter)


def mark_trigger_failed(trigger_id, detail: str) -> None:
    with transaction.atomic():
        try:
            review = CurieReview.objects.select_for_update().get(trigger_id=trigger_id)
        except CurieReview.DoesNotExist:
            return
        if review.status != STATUS_PENDING_EVALUATION:
            return
        review.status = CurieReview.STATUS_FAILED
        review.error_detail = detail
        review.completed_at = timezone.now()
        review.save(update_fields=["status", "error_detail", "completed_at", "modified"])
        logger.warning(
            "CURIE trigger marked failed trigger_id=%s detail=%s",
            trigger_id,
            detail,
        )


def attempt_trigger_delivery(trigger_id, callback_url=None) -> None:
    review = (
        CurieReview.objects.select_related(
            "submission__student",
            "submission__template_block__template__template_type",
        )
        .filter(trigger_id=trigger_id)
        .first()
    )
    if review is None or review.status != STATUS_PENDING_EVALUATION:
        return
    payload = review.trigger_payload or None
    if not payload:
        payload = build_trigger_payload(review, review.submission, callback_url=callback_url)
    elif callback_url and not payload.get("callback_url"):
        payload = {**payload, "callback_url": callback_url}
    send_trigger(payload)


def run_deliver_curie_trigger(task, trigger_id, callback_url=None) -> None:
    """Celery task body. Uses Celery 5 retry semantics: exhaustion re-raises the cause."""
    try:
        attempt_trigger_delivery(trigger_id, callback_url)
    except RetryableTriggerError as exc:
        retries = int(getattr(getattr(task, "request", None), "retries", 0) or 0)
        max_retries = int(getattr(task, "max_retries", 3) or 3)
        if retries >= max_retries:
            mark_trigger_failed(trigger_id, f"{TRIGGER_EXHAUSTED_ERROR_DETAIL} {exc}".strip())
            record_trigger_exhausted()
            return
        try:
            record_trigger_retried()
            raise task.retry(
                exc=exc,
                countdown=retry_countdown_seconds(retries),
            )
        except Retry:
            raise
        except RetryableTriggerError:
            mark_trigger_failed(trigger_id, f"{TRIGGER_EXHAUSTED_ERROR_DETAIL} {exc}".strip())
            record_trigger_exhausted()
        except MaxRetriesExceededError:
            mark_trigger_failed(trigger_id, f"{TRIGGER_EXHAUSTED_ERROR_DETAIL} {exc}".strip())
            record_trigger_exhausted()
    except TerminalTriggerError as exc:
        mark_trigger_failed(trigger_id, f"CURIE trigger failed: {exc}")
