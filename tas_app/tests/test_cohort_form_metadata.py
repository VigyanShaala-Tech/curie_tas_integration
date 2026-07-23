"""Tests for cohort form metadata extraction helpers."""

from django.test import SimpleTestCase

from tas_app.utils.cohort_form_metadata import (
    EMPTY_COHORT_FORM_FIELDS,
    extract_cohort_form_fields,
    metadata_fields_for_user,
)


SAMPLE_RESPONSE_DATA = {
    "college_name": "Example College",
    "university_name": "Example University",
    "partner_organization": "Partner Org",
    "email": "historical@example.com",
}


class ExtractCohortFormFieldsTest(SimpleTestCase):
    def test_extracts_flat_response_data_keys(self):
        result = extract_cohort_form_fields(SAMPLE_RESPONSE_DATA)
        self.assertEqual(result["college_name"], "Example College")
        self.assertEqual(result["university_name"], "Example University")
        self.assertEqual(result["partner_organization"], "Partner Org")

    def test_does_not_use_email_from_response_data(self):
        result = extract_cohort_form_fields(SAMPLE_RESPONSE_DATA)
        self.assertNotIn("email", result)

    def test_missing_sections_return_empty_strings(self):
        self.assertEqual(
            extract_cohort_form_fields({}),
            EMPTY_COHORT_FORM_FIELDS,
        )
        self.assertEqual(
            extract_cohort_form_fields(None),
            EMPTY_COHORT_FORM_FIELDS,
        )

    def test_strips_whitespace(self):
        result = extract_cohort_form_fields(
            {
                "college_name": "  College  ",
                "university_name": " Uni ",
                "partner_organization": " Org ",
            }
        )
        self.assertEqual(result["college_name"], "College")
        self.assertEqual(result["university_name"], "Uni")
        self.assertEqual(result["partner_organization"], "Org")


class MetadataFieldsForUserTest(SimpleTestCase):
    def test_missing_user_returns_empty(self):
        self.assertEqual(metadata_fields_for_user({}, 1), EMPTY_COHORT_FORM_FIELDS)
        self.assertEqual(metadata_fields_for_user({2: {"college_name": "A"}}, None), EMPTY_COHORT_FORM_FIELDS)

    def test_returns_lookup_copy(self):
        lookup = {
            5: {
                "college_name": "C",
                "university_name": "U",
                "partner_organization": "P",
            }
        }
        result = metadata_fields_for_user(lookup, 5)
        self.assertEqual(result["college_name"], "C")
        self.assertEqual(result["university_name"], "U")
        self.assertEqual(result["partner_organization"], "P")
