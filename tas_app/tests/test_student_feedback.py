"""Tests for student-facing instructor comment formatting."""

from django.test import SimpleTestCase

from tas_app.utils.student_feedback import (
    flatten_instructor_comment_for_student,
    is_category_heading_line,
    strip_category_headings_from_comment,
)


class StripCategoryHeadingsFromCommentTest(SimpleTestCase):
    def test_strips_html_headings_and_keeps_markup(self):
        html = (
            "<p><u>Technical Accuracy:</u></p>"
            "<p><strong>Quiz on Collaboration</strong></p>"
            "<p><u>Presentation:</u></p>"
            '<p><a href="https://example.com">link text</a></p>'
            "<p>please do it asap</p>"
        )
        result = strip_category_headings_from_comment(html)
        self.assertNotIn("Technical Accuracy", result)
        self.assertNotIn("Presentation", result)
        self.assertIn("<strong>Quiz on Collaboration</strong>", result)
        self.assertIn('href="https://example.com"', result)
        self.assertIn("please do it asap", result)

    def test_plain_text_headings_removed(self):
        comment = (
            "Technical Accuracy:\n"
            "Quiz on Collaboration\n"
            "\n"
            "Presentation:\n"
            "please revise\n"
        )
        result = strip_category_headings_from_comment(comment)
        self.assertEqual(result, "Quiz on Collaboration\nplease revise")

    def test_empty_comment(self):
        self.assertEqual(strip_category_headings_from_comment(""), "")
        self.assertEqual(strip_category_headings_from_comment(None), "")


class FlattenInstructorCommentForStudentTest(SimpleTestCase):
    def test_strips_html_and_category_headings(self):
        html = (
            "<p><u>Technical Accuracy:</u></p>"
            "<p>Quiz on Collaboration</p>"
            "<p>Quiz on Creativity_Growth</p>"
            "<p><u>Presentation:</u></p>"
            "<p>Assignment on Critical_Thinking</p>"
            "<p>please do it asap</p>"
        )
        self.assertEqual(
            flatten_instructor_comment_for_student(html),
            [
                "Quiz on Collaboration",
                "Quiz on Creativity_Growth",
                "Assignment on Critical_Thinking",
                "please do it asap",
            ],
        )

    def test_is_category_heading_line(self):
        self.assertTrue(is_category_heading_line("Technical Accuracy:"))
        self.assertFalse(is_category_heading_line("Note: please revise"))
