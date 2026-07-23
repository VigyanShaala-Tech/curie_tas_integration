"""
Server-side filters and ordering for the admin submission list endpoint.
"""

from __future__ import annotations

from django.db.models import Count, Exists, OuterRef, Q

from tas_app.models import Submission

from .cohort_form_metadata import CohortFormSubmission

SORT_FIELD_MAP = {
    "submitted_at": "submitted_at",
    "resubmission_count": "resubmission_count",
}


def build_base_submission_list_queryset(usage_key: str):
    """Submission queryset for the admin list — one row per submission."""
    return (
        Submission.objects.filter(usage_key=usage_key)
        .select_related("student", "feedback")
        .annotate(
            resubmission_count=Count(
                "tas_submission_versions",
                filter=(
                    Q(tas_submission_versions__pdf__isnull=False)
                    & ~Q(tas_submission_versions__pdf="")
                ),
            )
        )
    )


def _query_param(params, key: str) -> str:
    value = params.get(key)
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        if not value:
            return ""
        value = value[0]
    return str(value).strip()


def apply_submission_list_filters(queryset, query_params):
    """
    Server-side filters for the admin submission list.

    Cohort filters use Exists against cohort_management_form_cohortformsubmission
    joined on Submission.student_id = user_id.
    """
    email = _query_param(query_params, "email")
    if email:
        queryset = queryset.filter(student__email__icontains=email)

    college = _query_param(query_params, "college")
    university = _query_param(query_params, "university")
    partner = _query_param(query_params, "partner")

    cohort_q = Q(user_id=OuterRef("student_id"))
    if college:
        cohort_q &= Q(response_data__college_name=college)
    if university:
        cohort_q &= Q(response_data__university_name=university)
    if partner:
        cohort_q &= Q(response_data__partner_organization=partner)

    if college or university or partner:
        queryset = queryset.filter(
            Exists(CohortFormSubmission.objects.filter(cohort_q))
        )

    submitted_after = _query_param(query_params, "submitted_after")
    if submitted_after:
        queryset = queryset.filter(submitted_at__date__gte=submitted_after)

    submitted_before = _query_param(query_params, "submitted_before")
    if submitted_before:
        queryset = queryset.filter(submitted_at__date__lte=submitted_before)

    return queryset


def apply_submission_list_ordering(queryset, query_params):
    """Sort by submitted_at or resubmission_count; tie-break on id ascending."""
    sort_by = _query_param(query_params, "sort_by") or "submitted_at"
    sort_dir = _query_param(query_params, "sort_dir") or "desc"
    field = SORT_FIELD_MAP.get(sort_by, "submitted_at")
    prefix = "-" if sort_dir == "desc" else ""
    return queryset.order_by(f"{prefix}{field}", "id")
