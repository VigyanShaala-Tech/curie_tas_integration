"""Operational CURIE metrics via Open edX edx_django_utils.monitoring.

Counters are New Relic / Datadog increments. Latency uses accumulate plus a
request-scoped custom attribute. Monitoring failures must never affect grading.
"""

from __future__ import annotations

import logging
from datetime import datetime

from django.utils import timezone

logger = logging.getLogger(__name__)

try:
    from edx_django_utils.monitoring import accumulate, increment, set_custom_attribute
except ImportError:  # pragma: no cover - unit hosts without edx-django-utils
    def increment(name, value=1, **kwargs):  # type: ignore[misc]
        return None

    def accumulate(name, value, **kwargs):  # type: ignore[misc]
        return None

    def set_custom_attribute(name, value):  # type: ignore[misc]
        return None

CALLBACK_OUTCOMES = frozenset(
    {"applied", "replayed", "conflict", "stale", "superseded", "failed"}
)


def _inc(name: str, value: int = 1) -> None:
    try:
        for _ in range(max(value, 1)):
            increment(name)
    except Exception:  # noqa: BLE001
        logger.debug("CURIE metric increment failed name=%s", name, exc_info=True)


def _accumulate(name: str, value: float) -> None:
    try:
        accumulate(name, value)
    except Exception:  # noqa: BLE001
        logger.debug("CURIE metric accumulate failed name=%s", name, exc_info=True)


def _attribute(name: str, value) -> None:
    try:
        set_custom_attribute(name, value)
    except Exception:  # noqa: BLE001
        logger.debug("CURIE metric attribute failed name=%s", name, exc_info=True)


def record_trigger_accepted() -> None:
    _inc("curie.trigger.accepted")


def record_trigger_retried() -> None:
    _inc("curie.trigger.retried")


def record_trigger_exhausted() -> None:
    _inc("curie.trigger.exhausted")


def record_callback_outcome(outcome: str, *, requested_at: datetime | None = None) -> None:
    name = outcome if outcome in CALLBACK_OUTCOMES else "unknown"
    _inc(f"curie.callback.{name}")
    _attribute("curie.callback_outcome", name)
    if requested_at is not None and name in {"applied", "failed"}:
        record_callback_latency(requested_at)


def record_timeout() -> None:
    _inc("curie.timeout")


def record_callback_latency(requested_at: datetime, *, now: datetime | None = None) -> None:
    now = now or timezone.now()
    seconds = (now - requested_at).total_seconds()
    if seconds < 0:
        return
    _accumulate("curie.callback.latency_seconds", seconds)
    _attribute("curie.callback_latency_seconds", seconds)
