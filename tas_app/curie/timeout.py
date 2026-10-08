"""Read-time timeout resolution for pending CurieReview rows."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from django.db import transaction
from django.utils import timezone

from tas_app.curie.constants import (
    DEFAULT_MAX_WAIT_SECONDS,
    DEFAULT_SLOW_REVIEW_SECONDS,
    STATUS_FAILED,
    STATUS_PENDING_EVALUATION,
    TIMEOUT_ERROR_DETAIL,
)
from tas_app.curie.metrics import record_timeout


def elapsed_seconds(requested_at: datetime, now: datetime) -> float:
    return (now - requested_at).total_seconds()


def is_slow_pending(
    requested_at: datetime,
    now: datetime,
    *,
    slow_after_seconds: int = DEFAULT_SLOW_REVIEW_SECONDS,
) -> bool:
    """Five-minute mark changes learner copy only."""
    return elapsed_seconds(requested_at, now) >= slow_after_seconds


def has_timed_out(
    requested_at: datetime,
    now: datetime,
    *,
    max_wait_seconds: int = DEFAULT_MAX_WAIT_SECONDS,
) -> bool:
    return elapsed_seconds(requested_at, now) >= max_wait_seconds


def resolve_timeout(
    review: Any,
    now: datetime,
    *,
    max_wait_seconds: int = DEFAULT_MAX_WAIT_SECONDS,
    persist: Callable[[Any], None] | None = None,
) -> Any:
    """
    Idempotently mark a pending review failed after the 30-minute outer bound.

    Does not write a projection or grade. Persist is injected so callers can
    use a row lock in later phases without changing this predicate.
    """
    if getattr(review, "status", None) != STATUS_PENDING_EVALUATION:
        return review
    if not has_timed_out(review.requested_at, now, max_wait_seconds=max_wait_seconds):
        return review
    review.status = STATUS_FAILED
    review.error_detail = TIMEOUT_ERROR_DETAIL
    review.completed_at = now
    if persist is not None:
        persist(review)
    return review


def persist_timeout_if_due(review: Any, *, now: datetime | None = None) -> Any:
    """Lock a pending row and persist the 30-minute failure when it is due."""
    if review is None:
        return None

    from tas_app.curie.settings import max_wait_seconds
    from tas_app.models import CurieReview

    now = now or timezone.now()
    wait = max_wait_seconds()
    if getattr(review, "status", None) != STATUS_PENDING_EVALUATION:
        return review
    if not has_timed_out(review.requested_at, now, max_wait_seconds=wait):
        return review

    def _save(locked: Any) -> None:
        locked.save(update_fields=["status", "error_detail", "completed_at"])

    with transaction.atomic():
        locked = CurieReview.objects.select_for_update().get(pk=review.pk)
        was_pending = getattr(locked, "status", None) == STATUS_PENDING_EVALUATION
        resolved = resolve_timeout(locked, now, max_wait_seconds=wait, persist=_save)
        if (
            was_pending
            and getattr(resolved, "status", None) == STATUS_FAILED
            and getattr(resolved, "error_detail", "") == TIMEOUT_ERROR_DETAIL
        ):
            record_timeout()
        return resolved
