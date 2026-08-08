"""Tests for admin submission list filters and filter-options helpers."""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from tas_app.utils.admin_submission_filters import (
    apply_submission_list_filters,
    apply_submission_list_ordering,
    apply_submission_status_filter,
    build_submission_status_counts,
)
from tas_app.utils.cohort_form_metadata import (
    EMPTY_COHORT_FORM_FIELDS,
    distinct_cohort_form_values,
    extract_cohort_form_fields,
)


class ExtractCohortFormFieldsDistinctTest(SimpleTestCase):
    def test_distinct_values_from_response_data(self):
        with patch("tas_app.utils.cohort_form_metadata.CohortFormSubmission") as model:
            row1 = MagicMock()
            row1.response_data = {
                "college_name": "College A",
                "university_name": "Uni X",
                "partner_organization": "Partner 1",
            }
            row2 = MagicMock()
            row2.response_data = {
                "college_name": "College B",
                "university_name": "Uni X",
                "partner_organization": "Partner 2",
            }
            model.objects.filter.return_value.only.return_value = [row1, row2]

            result = distinct_cohort_form_values([1, 2])

        self.assertEqual(result["college_name"], ["College A", "College B"])
        self.assertEqual(result["university_name"], ["Uni X"])
        self.assertEqual(result["partner_organization"], ["Partner 1", "Partner 2"])

    def test_empty_user_ids_returns_empty_lists(self):
        result = distinct_cohort_form_values([])
        self.assertEqual(result, {key: [] for key in EMPTY_COHORT_FORM_FIELDS})

    def test_extract_ignores_email_in_response_data(self):
        result = extract_cohort_form_fields(
            {
                "college_name": "C",
                "university_name": "U",
                "partner_organization": "P",
                "email": "old@example.com",
            }
        )
        self.assertNotIn("email", result)


class ApplySubmissionListFiltersTest(SimpleTestCase):
    def test_email_filter_uses_student_email(self):
        queryset = MagicMock()
        filtered = MagicMock()
        queryset.filter.return_value = filtered

        result = apply_submission_list_filters(queryset, {"email": ["student@"]})

        queryset.filter.assert_called_once_with(student__email__icontains="student@")
        self.assertIs(result, filtered)

    def test_cohort_filters_use_exists_subquery(self):
        queryset = MagicMock()
        filtered = MagicMock()
        queryset.filter.return_value = filtered

        with patch(
            "tas_app.utils.admin_submission_filters.CohortFormSubmission"
        ) as cohort_model, patch(
            "tas_app.utils.admin_submission_filters.Exists"
        ) as exists_cls:
            exists_cls.return_value = MagicMock()
            cohort_model.objects.filter.return_value = MagicMock()

            result = apply_submission_list_filters(
                queryset,
                {
                    "college": ["College A"],
                    "university": ["Uni X"],
                    "partner": ["Partner 1"],
                },
            )

        exists_cls.assert_called_once()
        queryset.filter.assert_called_once()
        self.assertIs(result, filtered)

    def test_date_range_filters(self):
        queryset = MagicMock()
        after_filtered = MagicMock()
        before_filtered = MagicMock()
        queryset.filter.return_value = after_filtered
        after_filtered.filter.return_value = before_filtered

        result = apply_submission_list_filters(
            queryset,
            {
                "submitted_after": ["2026-01-01"],
                "submitted_before": ["2026-12-31"],
            },
        )

        queryset.filter.assert_called_once_with(submitted_at__date__gte="2026-01-01")
        after_filtered.filter.assert_called_once_with(submitted_at__date__lte="2026-12-31")
        self.assertIs(result, before_filtered)

    def test_status_filter_submitted(self):
        queryset = MagicMock()
        filtered = MagicMock()
        queryset.filter.return_value = filtered

        result = apply_submission_list_filters(
            queryset, {"status": ["submitted"]},
        )

        queryset.filter.assert_called_once_with(status="submitted")
        self.assertIs(result, filtered)

    def test_status_filter_approved(self):
        queryset = MagicMock()
        filtered = MagicMock()
        queryset.filter.return_value = filtered

        result = apply_submission_status_filter(queryset, {"status": ["approved"]})

        queryset.filter.assert_called_once_with(status="approved")
        self.assertIs(result, filtered)

    def test_status_filter_rejected(self):
        queryset = MagicMock()
        filtered = MagicMock()
        queryset.filter.return_value = filtered

        result = apply_submission_status_filter(queryset, {"status": ["rejected"]})

        queryset.filter.assert_called_once_with(status="rejected")
        self.assertIs(result, filtered)

    def test_no_status_leaves_queryset_unfiltered(self):
        queryset = MagicMock()

        result = apply_submission_list_filters(queryset, {})

        queryset.filter.assert_not_called()
        self.assertIs(result, queryset)

    def test_status_filter_skipped_when_include_status_false(self):
        queryset = MagicMock()

        result = apply_submission_list_filters(
            queryset, {"status": ["submitted"]}, include_status=False,
        )

        queryset.filter.assert_not_called()
        self.assertIs(result, queryset)

    def test_invalid_status_ignored(self):
        queryset = MagicMock()

        result = apply_submission_status_filter(queryset, {"status": ["not-a-status"]})

        queryset.filter.assert_not_called()
        self.assertIs(result, queryset)

    def test_empty_status_ignored(self):
        queryset = MagicMock()

        result = apply_submission_status_filter(queryset, {"status": [""]})

        queryset.filter.assert_not_called()
        self.assertIs(result, queryset)


class BuildSubmissionStatusCountsTest(SimpleTestCase):
    def test_returns_zero_defaults_and_per_status_counts(self):
        """Counts are computed on the pre-status queryset (caller passes include_status=False)."""
        queryset = MagicMock()
        queryset.filter.return_value.count.side_effect = [40, 35, 25]

        result = build_submission_status_counts(queryset)

        self.assertEqual(
            result,
            {"submitted": 40, "approved": 35, "rejected": 25},
        )
        self.assertEqual(queryset.filter.call_count, 3)
        queryset.filter.assert_any_call(status="submitted")
        queryset.filter.assert_any_call(status="approved")
        queryset.filter.assert_any_call(status="rejected")


class ApplySubmissionListOrderingTest(SimpleTestCase):
    def test_default_sort_submitted_at_desc(self):
        queryset = MagicMock()
        ordered = MagicMock()
        queryset.order_by.return_value = ordered

        result = apply_submission_list_ordering(queryset, {})

        queryset.order_by.assert_called_once_with("-submitted_at", "id")
        self.assertIs(result, ordered)

    def test_resubmission_count_asc(self):
        queryset = MagicMock()
        ordered = MagicMock()
        queryset.order_by.return_value = ordered

        result = apply_submission_list_ordering(
            queryset,
            {"sort_by": ["resubmission_count"], "sort_dir": ["asc"]},
        )

        queryset.order_by.assert_called_once_with("resubmission_count", "id")
        self.assertIs(result, ordered)
