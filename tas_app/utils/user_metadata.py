"""
Read-only access to Open edX user_metadata_app_usermetadata.

Production stores nested JSON in dynamic_fields_data. Local Tutor may not have
this table — all public helpers degrade to empty strings / empty maps.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from django.conf import settings
from django.db import DatabaseError, ProgrammingError, models

logger = logging.getLogger(__name__)

# Map API field name → nested path inside dynamic_fields_data.
# Add entries here to expose more metadata on the submissions list.
USER_METADATA_FIELD_PATHS: Dict[str, Tuple[str, ...]] = {
    "college_name": (
        "01_academic_information",
        "04_college_name",
    ),
    "university_name": (
        "01_academic_information",
        "03_university_name",
    ),
    "partner_organization": (
        "04_additional_information",
        "24_partner_organization",
    ),
}

EMPTY_METADATA_FIELDS: Dict[str, str] = {key: "" for key in USER_METADATA_FIELD_PATHS}


class UserMetadata(models.Model):
    """
    Unmanaged mirror of production table user_metadata_app_usermetadata.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.DO_NOTHING,
        db_column="user_id",
        related_name="+",
    )
    dynamic_fields_data = models.JSONField(default=dict, blank=True)

    class Meta:
        managed = False
        db_table = "user_metadata_app_usermetadata"
        app_label = "tas_app"


def _walk_path(data: Any, path: Sequence[str]) -> Any:
    current = data
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def extract_user_metadata_fields(
    dynamic_fields_data: Any,
    field_paths: Optional[Mapping[str, Sequence[str]]] = None,
) -> Dict[str, str]:
    """
    Walk nested JSON using USER_METADATA_FIELD_PATHS (or a custom map).

    Missing / non-string values become "".
    """
    paths = field_paths if field_paths is not None else USER_METADATA_FIELD_PATHS
    result: Dict[str, str] = {key: "" for key in paths}
    if not isinstance(dynamic_fields_data, Mapping):
        return result

    for field_name, path in paths.items():
        try:
            value = _walk_path(dynamic_fields_data, path)
        except Exception:  # noqa: BLE001 — never break list API on bad JSON shape
            logger.debug("Failed walking metadata path %s", path, exc_info=True)
            continue
        if value is None:
            continue
        text = str(value).strip() if not isinstance(value, str) else value.strip()
        result[field_name] = text
    return result


def bulk_user_metadata_by_user_ids(
    user_ids: Iterable[int],
) -> Dict[int, Dict[str, str]]:
    """
    One query for the page of student ids. Returns {} if table/model unavailable.
    """
    ids = list({int(uid) for uid in user_ids if uid is not None})
    if not ids:
        return {}

    try:
        rows = UserMetadata.objects.filter(user_id__in=ids).only(
            "user_id", "dynamic_fields_data"
        )
        out: Dict[int, Dict[str, str]] = {}
        for row in rows:
            try:
                out[int(row.user_id)] = extract_user_metadata_fields(row.dynamic_fields_data)
            except Exception:  # noqa: BLE001
                logger.debug(
                    "Failed extracting metadata for user_id=%s", row.user_id, exc_info=True
                )
                out[int(row.user_id)] = dict(EMPTY_METADATA_FIELDS)
        return out
    except (ProgrammingError, DatabaseError, RuntimeError) as exc:
        # Missing table (local Tutor) or DB errors — degrade gracefully.
        logger.info("user_metadata lookup skipped: %s", exc)
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("user_metadata lookup failed unexpectedly: %s", exc, exc_info=True)
        return {}


def metadata_fields_for_user(
    lookup: Mapping[int, Mapping[str, str]],
    user_id: Optional[int],
) -> Dict[str, str]:
    """Return a mutable copy of fields for user_id, or empty strings."""
    if user_id is None:
        return dict(EMPTY_METADATA_FIELDS)
    fields = lookup.get(int(user_id))
    if not fields:
        return dict(EMPTY_METADATA_FIELDS)
    return {key: fields.get(key, "") for key in USER_METADATA_FIELD_PATHS}
