"""CURIE Django settings accessors and enablement validation."""

from __future__ import annotations

import math
import re
from urllib.parse import urlparse

from django.conf import settings

from tas_app.curie.constants import (
    DEFAULT_COMPONENT_PASS_THRESHOLD,
    DEFAULT_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_MAX_WAIT_SECONDS,
    DEFAULT_RESPONSE_TIMEOUT_SECONDS,
    DEFAULT_SLOW_REVIEW_SECONDS,
)


class CurieSettingsError(ValueError):
    """Raised when CURIE is enabled without a complete, valid wire configuration."""


_HTTP_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


def curie_enabled() -> bool:
    return bool(getattr(settings, "CURIE_ENABLED", False))


def trigger_url() -> str:
    return str(getattr(settings, "CURIE_TRIGGER_URL", "") or "")


def callback_base_url() -> str:
    """Absolute origin the stub uses to reach TAS, e.g. http://lms:8000. Empty falls back to the submit request."""
    return str(getattr(settings, "CURIE_CALLBACK_BASE_URL", "") or "")


def auth_header_name() -> str:
    return str(getattr(settings, "CURIE_AUTH_HEADER_NAME", "") or "")


def shared_secret() -> str:
    return str(getattr(settings, "CURIE_SHARED_SECRET", "") or "")


def connect_timeout_seconds() -> int:
    return int(getattr(settings, "CURIE_CONNECT_TIMEOUT_SECONDS", DEFAULT_CONNECT_TIMEOUT_SECONDS))


def response_timeout_seconds() -> int:
    return int(getattr(settings, "CURIE_REQUEST_TIMEOUT_SECONDS", DEFAULT_RESPONSE_TIMEOUT_SECONDS))


def slow_review_seconds() -> int:
    return int(getattr(settings, "CURIE_REVIEW_TIMEOUT_SECONDS", DEFAULT_SLOW_REVIEW_SECONDS))


def max_wait_seconds() -> int:
    return int(getattr(settings, "CURIE_REVIEW_MAX_WAIT_SECONDS", DEFAULT_MAX_WAIT_SECONDS))


def component_pass_threshold() -> float:
    return float(getattr(settings, "CURIE_COMPONENT_PASS_THRESHOLD", DEFAULT_COMPONENT_PASS_THRESHOLD))


def _require_http_url(value: str, name: str) -> None:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CurieSettingsError(f"{name} must be an absolute http(s) URL.")


def _require_header_name(value: str, name: str) -> None:
    if not _HTTP_HEADER_NAME.fullmatch(value.strip()):
        raise CurieSettingsError(f"{name} is not a valid HTTP header name.")


def _require_positive_number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CurieSettingsError(f"{name} must be a positive number.")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise CurieSettingsError(f"{name} must be a positive number.")
    return number


def _require_threshold(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CurieSettingsError(f"{name} must be a number between 0 and 10.")
    number = float(value)
    if not math.isfinite(number) or number < 0 or number > 10:
        raise CurieSettingsError(f"{name} must be a number between 0 and 10.")
    return number


def validate_curie_settings(*, enabled: bool | None = None) -> None:
    """When CURIE is on, the exact URL, auth, timeouts, and threshold must all be valid."""
    if enabled is None:
        enabled = curie_enabled()
    if not enabled:
        return

    url = trigger_url().strip()
    header = auth_header_name().strip()
    secret = shared_secret().strip()
    missing = []
    if not url:
        missing.append("CURIE_TRIGGER_URL")
    if not header:
        missing.append("CURIE_AUTH_HEADER_NAME")
    if not secret:
        missing.append("CURIE_SHARED_SECRET")
    if missing:
        raise CurieSettingsError(
            "CURIE_ENABLED requires these settings to be non-empty: " + ", ".join(missing)
        )

    _require_http_url(url, "CURIE_TRIGGER_URL")
    _require_header_name(header, "CURIE_AUTH_HEADER_NAME")

    _require_positive_number(connect_timeout_seconds(), "CURIE_CONNECT_TIMEOUT_SECONDS")
    _require_positive_number(response_timeout_seconds(), "CURIE_REQUEST_TIMEOUT_SECONDS")
    slow = _require_positive_number(slow_review_seconds(), "CURIE_REVIEW_TIMEOUT_SECONDS")
    max_wait = _require_positive_number(max_wait_seconds(), "CURIE_REVIEW_MAX_WAIT_SECONDS")
    if slow >= max_wait:
        raise CurieSettingsError(
            "CURIE_REVIEW_TIMEOUT_SECONDS must be less than CURIE_REVIEW_MAX_WAIT_SECONDS."
        )
    _require_threshold(component_pass_threshold(), "CURIE_COMPONENT_PASS_THRESHOLD")
