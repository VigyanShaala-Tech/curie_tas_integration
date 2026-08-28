"""Focused tests for plain-text Student Instructions display."""

import re
from pathlib import Path

from django.template import Context, Engine
from django.test import SimpleTestCase


XBLOCK_STATIC = Path(__file__).resolve().parents[2] / "tas_xblock" / "static"
TAS_CSS = XBLOCK_STATIC / "css" / "tas.css"
TAS_HTML = XBLOCK_STATIC / "html" / "tas.html"

INSTRUCTION_STATUSES = ("not_submitted", "draft", "rejected")
HIDDEN_STATUSES = ("submitted", "approved")

MULTILINE_INSTRUCTIONS = (
    "Please read the following instructions carefully:\n"
    "\n"
    "Content Quality:\n"
    "\n"
    "• Complete Video 1\n"
    "• Complete Video 2\n"
    "• Complete Video 3\n"
    "\n"
    "Technical Accuracy:\n"
    "\n"
    "• Complete the SWOT quiz\n"
    "• Complete the Communication quiz\n"
    "\n"
    "1. Numbered item one\n"
    "2. Numbered item two\n"
    "\n"
    "Best of luck! 😊"
)

HTML_LIKE_INSTRUCTIONS = 'See <script>alert("xss")</script> and <b>bold</b>.'

_INSTRUCTIONS_BLOCK_RE = re.compile(
    r'<p class="instructions-text">(.*?)</p>',
    re.DOTALL,
)
_INSTRUCTIONS_TEXT_RULE_RE = re.compile(
    r"\.tas_block\s+\.instructions-text\s*\{([^}]+)\}",
    re.DOTALL,
)


def _render_tas_html(instructions, status):
    engine = Engine(libraries={"i18n": "django.templatetags.i18n"})
    template = engine.from_string(TAS_HTML.read_text(encoding="utf-8"))
    return template.render(Context({
        "template_type": "1",
        "template": "1",
        "is_course_staff": False,
        "assigment_status": status,
        "instructions": instructions,
        "assigment_submission_url": "/submit",
        "assigment_review_url": "/review",
        "assigment_feedback": None,
        "assigment_pdf_url": None,
    }))


def _instructions_markup(html):
    match = _INSTRUCTIONS_BLOCK_RE.search(html)
    return match.group(1) if match else None


class StudentInstructionsCssTest(SimpleTestCase):
    def test_instructions_text_preserves_whitespace(self):
        css = TAS_CSS.read_text(encoding="utf-8")
        match = _INSTRUCTIONS_TEXT_RULE_RE.search(css)
        self.assertIsNotNone(match, ".tas_block .instructions-text rule missing")
        self.assertIn("white-space: pre-wrap", match.group(1))


class StudentInstructionsTemplateTest(SimpleTestCase):
    def test_multiline_plain_text_preserved_in_all_display_states(self):
        for status in INSTRUCTION_STATUSES:
            with self.subTest(status=status):
                html = _render_tas_html(MULTILINE_INSTRUCTIONS, status)
                markup = _instructions_markup(html)
                self.assertIsNotNone(markup, f"instructions missing for {status}")
                self.assertIn("Content Quality:", markup)
                self.assertIn("Technical Accuracy:", markup)
                self.assertIn("• Complete Video 1", markup)
                self.assertIn("1. Numbered item one", markup)
                self.assertIn("2. Numbered item two", markup)
                self.assertIn("😊", markup)
                self.assertIn("\n\n", markup)
                self.assertIn("carefully:\n\nContent Quality:", markup)

    def test_single_line_instructions_unchanged(self):
        single = "This is a template based assignment."
        html = _render_tas_html(single, "not_submitted")
        self.assertEqual(_instructions_markup(html), single)

    def test_html_like_text_is_escaped(self):
        html = _render_tas_html(HTML_LIKE_INSTRUCTIONS, "not_submitted")
        markup = _instructions_markup(html)
        self.assertIsNotNone(markup)
        self.assertIn("&lt;script&gt;", markup)
        self.assertIn("&lt;/script&gt;", markup)
        self.assertIn("&lt;b&gt;", markup)
        self.assertNotIn("<script>", markup)
        self.assertNotIn("<b>bold</b>", markup)
        self.assertNotRegex(
            TAS_HTML.read_text(encoding="utf-8"),
            r"\{\{\s*instructions\s*\|safe\s*\}\}",
        )

    def test_submitted_and_approved_do_not_show_instructions(self):
        for status in HIDDEN_STATUSES:
            with self.subTest(status=status):
                html = _render_tas_html(MULTILINE_INSTRUCTIONS, status)
                self.assertIsNone(_instructions_markup(html))
