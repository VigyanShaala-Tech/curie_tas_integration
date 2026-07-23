"""
Read-only access to Open edX cohort_management_form_cohortformsubmission.

Production stores flat JSON keys in response_data. Local Tutor may not have
this table — all public helpers degrade to empty strings / empty maps.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from django.conf import settings
from django.db import DatabaseError, ProgrammingError, models

logger = logging.getLogger(__name__)

COHORT_FORM_FIELD_KEYS: Sequence[str] = (
    "college_name",
    "university_name",
    "partner_organization",
)

EMPTY_COHORT_FORM_FIELDS: Dict[str, str] = {key: "" for key in COHORT_FORM_FIELD_KEYS}


class CohortFormSubmission(models.Model):
    """
    Unmanaged mirror of production table cohort_management_form_cohortformsubmission.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.DO_NOTHING,
        db_column="user_id",
        related_name="+",
    )
    response_data = models.JSONField(default=dict, blank=True)

    class Meta:
        managed = False
        db_table = "cohort_management_form_cohortformsubmission"
        app_label = "tas_app"


def extract_cohort_form_fields(response_data: Any) -> Dict[str, str]:
    """
    Read flat top-level keys from response_data.

    Missing / non-string values become "".
    """
    result: Dict[str, str] = dict(EMPTY_COHORT_FORM_FIELDS)
    if not isinstance(response_data, Mapping):
        return result

    for field_name in COHORT_FORM_FIELD_KEYS:
        try:
            value = response_data.get(field_name)
        except Exception:  # noqa: BLE001 — never break list API on bad JSON shape
            logger.debug("Failed reading cohort form field %s", field_name, exc_info=True)
            continue
        if value is None:
            continue
        text = str(value).strip() if not isinstance(value, str) else value.strip()
        result[field_name] = text
    return result


def bulk_cohort_form_metadata_by_user_ids(
    user_ids: Iterable[int],
) -> Dict[int, Dict[str, str]]:
    """
    One query for the page of student ids. Returns {} if table/model unavailable.

    When multiple rows exist for the same user_id, the latest row by id wins.
    """
    ids = list({int(uid) for uid in user_ids if uid is not None})
    if not ids:
        return {}

    try:
        rows = (
            CohortFormSubmission.objects.filter(user_id__in=ids)
            .only("id", "user_id", "response_data")
            .order_by("user_id", "id")
        )
        out: Dict[int, Dict[str, str]] = {}
        for row in rows:
            try:
                out[int(row.user_id)] = extract_cohort_form_fields(row.response_data)
            except Exception:  # noqa: BLE001
                logger.debug(
                    "Failed extracting cohort form metadata for user_id=%s",
                    row.user_id,
                    exc_info=True,
                )
                out[int(row.user_id)] = dict(EMPTY_COHORT_FORM_FIELDS)
        return out
    except (ProgrammingError, DatabaseError, RuntimeError) as exc:
        logger.info("cohort form metadata lookup skipped: %s", exc)
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "cohort form metadata lookup failed unexpectedly: %s", exc, exc_info=True
        )
        return {}


def metadata_fields_for_user(
    lookup: Mapping[int, Mapping[str, str]],
    user_id: Optional[int],
) -> Dict[str, str]:
    """Return a mutable copy of fields for user_id, or empty strings."""
    if user_id is None:
        return dict(EMPTY_COHORT_FORM_FIELDS)
    fields = lookup.get(int(user_id))
    if not fields:
        return dict(EMPTY_COHORT_FORM_FIELDS)
    return {key: fields.get(key, "") for key in COHORT_FORM_FIELD_KEYS}


def distinct_cohort_form_values(
    user_ids: Iterable[int],
) -> Dict[str, list[str]]:
    """
    Sorted distinct non-empty values per field for dropdown filter options.
    """
    ids = list({int(uid) for uid in user_ids if uid is not None})
    empty_options: Dict[str, list[str]] = {key: [] for key in COHORT_FORM_FIELD_KEYS}
    if not ids:
        return empty_options

    try:
        rows = CohortFormSubmission.objects.filter(user_id__in=ids).only(
            "response_data"
        )
        buckets: Dict[str, set[str]] = {key: set() for key in COHORT_FORM_FIELD_KEYS}
        for row in rows:
            fields = extract_cohort_form_fields(row.response_data)
            for key in COHORT_FORM_FIELD_KEYS:
                value = fields.get(key, "")
                if value:
                    buckets[key].add(value)
        return {key: sorted(values) for key, values in buckets.items()}
    except (ProgrammingError, DatabaseError, RuntimeError) as exc:
        logger.info("cohort form distinct values lookup skipped: %s", exc)
        return empty_options
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "cohort form distinct values lookup failed unexpectedly: %s",
            exc,
            exc_info=True,
        )
        return empty_options
