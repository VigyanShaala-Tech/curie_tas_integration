"""Tests for submission PDF layout (aligned with frontend fieldLayout.ts)."""

import uuid
from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase
from opaque_keys.edx.keys import CourseKey, UsageKey

from tas_app.models import Submission, Template, TemplateBlock, TemplateType
from tas_app.pdf_generator import (
    BUNDLED_FONT_PATH,
    FIELD_FONT_NAME,
    FIELD_TEXT_PADDING_PX,
    _draw_text_in_box,
    frontend_px_to_pdf,
    generate_submission_pdf,
    get_field_font_name,
    image_to_pdf_scale,
    resolve_field_font_size,
    wrap_field_text,
)


User = get_user_model()


def _unique(prefix):
    return f"{prefix}{uuid.uuid4().hex[:10]}"


def _make_submission(fields, field_positions, form_data, image_width=800, image_height=1000):
    user = User.objects.create_user(
        username=_unique("pdfuser"),
        email=f"{_unique('pdf')}@example.com",
        password="password",
    )
    template_type = TemplateType.objects.create(
        name=_unique("PDF Type"),
        slug=_unique("pdf-type"),
    )
    template = Template.objects.create(
        template_type=template_type,
        name=_unique("PDF Template"),
        image_width=image_width,
        image_height=image_height,
        fields=fields,
        field_positions=field_positions,
        created_by=user,
    )
    usage_key = UsageKey.from_string(
        f"block-v1:edX+DemoX+2026_T1+type@problem+block@{_unique('pdfgen')}"
    )
    course_key = CourseKey.from_string("course-v1:edX+DemoX+2026_T1")
    block = TemplateBlock.objects.create(
        template=template,
        usage_key=usage_key,
        course_key=course_key,
        assigned_by=user,
    )
    return Submission.objects.create(
        student=user,
        template_block=block,
        course_key=course_key,
        usage_key=usage_key,
        form_data=form_data,
        status=Submission.STATUS_SUBMITTED,
        version_number=3,
    )


class PdfGeneratorLayoutTest(TestCase):
    def test_bundled_liberation_sans_exists(self):
        """Verify the project-controlled TTF is present for every environment."""
        self.assertTrue(
            BUNDLED_FONT_PATH.is_file(),
            f"Bundled PDF font missing at {BUNDLED_FONT_PATH}",
        )
        self.assertGreater(BUNDLED_FONT_PATH.stat().st_size, 1000)

    def test_get_field_font_name_uses_bundled_font(self):
        """Verify the normal path registers TASFieldFont from the bundled TTF."""
        self.assertEqual(get_field_font_name(), FIELD_FONT_NAME)
        self.assertNotEqual(get_field_font_name(), "Helvetica")

    def test_clip_path_does_not_paint_field_background(self):
        """Verify overflow clip is invisible (stroke=0, fill=0); no filled field rect."""
        font_name = get_field_font_name()
        canvas = MagicMock()
        clip_path = MagicMock()
        canvas.beginPath.return_value = clip_path

        _draw_text_in_box(canvas, "Hello", 10, 20, 100, 40, 14, font_name)

        canvas.saveState.assert_called_once()
        clip_path.rect.assert_called_once_with(10, 20, 100, 40)
        canvas.clipPath.assert_called_once()
        _args, kwargs = canvas.clipPath.call_args
        self.assertEqual(kwargs.get("stroke"), 0)
        self.assertEqual(kwargs.get("fill"), 0)
        canvas.rect.assert_not_called()
        canvas.restoreState.assert_called_once()
        fill_order = [name for name, _a, _k in canvas.method_calls]
        self.assertLess(
            fill_order.index("clipPath"),
            fill_order.index("setFillColorRGB"),
        )

    def test_resolve_field_font_size_uses_explicit_font_size(self):
        """Verify field.fontSize is used when provided (frontend resolveFieldFontSize)."""
        self.assertEqual(resolve_field_font_size({"fontSize": 14}, 100), 14.0)
        self.assertEqual(resolve_field_font_size({"fontSize": 12}, 10), 12.0)

    def test_explicit_fontsize_converted_with_page_scale(self):
        """Verify explicit CSS px fontSize is converted by page/image scale (1.0 today)."""
        scale = image_to_pdf_scale(800, 800)
        self.assertEqual(scale, 1.0)
        font_px = resolve_field_font_size({"fontSize": 14}, 100)
        self.assertEqual(frontend_px_to_pdf(font_px, scale), 14.0)

    def test_resolve_field_font_size_matches_frontend_fallback_formula(self):
        """Verify fallback is max(10, min(20, h * 0.6)) in image px, then scaled."""
        self.assertEqual(resolve_field_font_size({}, 100), 20.0)
        self.assertEqual(resolve_field_font_size({}, 20), 12.0)
        self.assertEqual(resolve_field_font_size({}, 10), 10.0)
        self.assertNotEqual(resolve_field_font_size({}, 10), 7.0)
        self.assertNotEqual(resolve_field_font_size({}, 40), 22.0)
        scale = image_to_pdf_scale(1000, 1000)
        self.assertEqual(frontend_px_to_pdf(resolve_field_font_size({}, 20), scale), 12.0)

    def test_padding_scaled_consistently(self):
        """Verify 2 CSS px padding is converted with the same page/image scale."""
        self.assertEqual(FIELD_TEXT_PADDING_PX, 2)
        self.assertEqual(frontend_px_to_pdf(FIELD_TEXT_PADDING_PX, 1.0), 2.0)
        self.assertEqual(frontend_px_to_pdf(FIELD_TEXT_PADDING_PX, 2.0), 4.0)

    def test_wrap_field_text_preserves_newlines(self):
        """Verify pre-wrap newline handling keeps blank lines."""
        font_name = get_field_font_name()
        lines = wrap_field_text("line1\n\nline3", font_name, 12, 400)
        self.assertEqual(lines[0], "line1")
        self.assertEqual(lines[1], "")
        self.assertEqual(lines[2], "line3")

    def test_wrap_field_text_breaks_unbreakable_strings(self):
        """Verify overflow-wrap:anywhere / word-break:break-word mid-word splits."""
        font_name = get_field_font_name()
        token = "A" * 80
        lines = wrap_field_text(token, font_name, 14, 40)
        self.assertGreater(len(lines), 1)
        self.assertEqual("".join(lines), token)
        for line in lines:
            self.assertTrue(line)

    def test_long_text_clip_does_not_paint_rectangle(self):
        """Verify long unbreakable text still uses an unpainted clip path."""
        font_name = get_field_font_name()
        canvas = MagicMock()
        clip_path = MagicMock()
        canvas.beginPath.return_value = clip_path
        _draw_text_in_box(canvas, "A" * 200, 2, 2, 30, 20, 12, font_name)
        _args, kwargs = canvas.clipPath.call_args
        self.assertEqual(kwargs.get("stroke"), 0)
        self.assertEqual(kwargs.get("fill"), 0)
        canvas.rect.assert_not_called()

    def test_generate_submission_pdf_writes_file_with_bundled_font(self):
        """Verify generate_submission_pdf stores a PDF using the bundled field font."""
        submission = _make_submission(
            fields=[{"id": "answer", "label": "Answer", "fontSize": 14}],
            field_positions={"answer": {"x": 10, "y": 10, "width": 40, "height": 20}},
            form_data={"answer": "Hello world"},
        )
        file_name = generate_submission_pdf(submission)
        submission.refresh_from_db()
        self.assertTrue(submission.pdf)
        self.assertIn(f"submission_{submission.id}_v{submission.version_number}", file_name)
        pdf_bytes = submission.pdf.read()
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertIn(b"Liberation", pdf_bytes)

    def test_generate_representative_assignment_pdf(self):
        """Verify a multi-field assignment (top, narrow, long, multiline, edges) generates."""
        submission = _make_submission(
            fields=[
                {"id": "top", "label": "Top", "fontSize": 14},
                {"id": "narrow", "label": "Narrow", "fontSize": 12},
                {"id": "long", "label": "Long"},
                {"id": "multi", "label": "Multi", "fontSize": 11},
                {"id": "edge", "label": "Edge", "fontSize": 10},
            ],
            field_positions={
                "top": {"x": 5, "y": 2, "width": 40, "height": 8},
                "narrow": {"x": 50, "y": 20, "width": 8, "height": 6},
                "long": {"x": 5, "y": 40, "width": 30, "height": 10},
                "multi": {"x": 40, "y": 55, "width": 50, "height": 20},
                "edge": {"x": 90, "y": 90, "width": 9, "height": 8},
            },
            form_data={
                "top": "Text near the top",
                "narrow": "NarrowCell",
                "long": "A" * 120,
                "multi": "line one\nline two\nline three",
                "edge": "Edge",
            },
        )
        generate_submission_pdf(submission)
        submission.refresh_from_db()
        pdf_bytes = submission.pdf.read()
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertIn(b"Liberation", pdf_bytes)
