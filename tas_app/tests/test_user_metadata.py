"""Tests for user_metadata path extraction helpers."""

from django.test import SimpleTestCase

from tas_app.utils.user_metadata import (
    EMPTY_METADATA_FIELDS,
    extract_user_metadata_fields,
    metadata_fields_for_user,
)


SAMPLE_DYNAMIC_FIELDS = {
    "01_academic_information": {
        "04_college_name": "Example College",
        "03_university_name": "Example University",
    },
    "03_location_information": {
        "12_college_country": "IN",
        "13_college_state": "KA",
        "14_college_district": "BLR",
    },
    "04_additional_information": {
        "24_partner_organization": "Partner Org",
    },
}


class ExtractUserMetadataFieldsTest(SimpleTestCase):
    def test_extracts_nested_production_shape(self):
        result = extract_user_metadata_fields(SAMPLE_DYNAMIC_FIELDS)
        self.assertEqual(result["college_name"], "Example College")
        self.assertEqual(result["university_name"], "Example University")
        self.assertEqual(result["partner_organization"], "Partner Org")

    def test_missing_sections_return_empty_strings(self):
        self.assertEqual(
            extract_user_metadata_fields({}),
            EMPTY_METADATA_FIELDS,
        )
        self.assertEqual(
            extract_user_metadata_fields(None),
            EMPTY_METADATA_FIELDS,
        )

    def test_strips_whitespace(self):
        result = extract_user_metadata_fields(
            {
                "01_academic_information": {
                    "04_college_name": "  College  ",
                    "03_university_name": " Uni ",
                },
                "04_additional_information": {
                    "24_partner_organization": " Org ",
                },
            }
        )
        self.assertEqual(result["college_name"], "College")
        self.assertEqual(result["university_name"], "Uni")
        self.assertEqual(result["partner_organization"], "Org")


class MetadataFieldsForUserTest(SimpleTestCase):
    def test_missing_user_returns_empty(self):
        self.assertEqual(metadata_fields_for_user({}, 1), EMPTY_METADATA_FIELDS)
        self.assertEqual(metadata_fields_for_user({2: {"college_name": "A"}}, None), EMPTY_METADATA_FIELDS)

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
