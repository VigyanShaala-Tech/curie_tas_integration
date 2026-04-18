"""
PDF generation for TAS submissions.

Uses reportlab to embed the template background image and overlay
student-filled field values at the correct percentage-based positions.
"""

import io
import logging

from django.core.files.base import ContentFile
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

logger = logging.getLogger(__name__)


def generate_submission_pdf(submission):
    """
    Generates a PDF for the given Submission, saves it to submission.pdf,
    and returns the saved file name.

    The PDF page size matches the template's natural image dimensions (pixels → points).
    Field values are placed using the same percentage coordinates as the frontend.
    """
    template = submission.template_block.template
    form_data = submission.form_data or {}
    fields = template.fields or []
    field_positions = template.field_positions or {}

    image_w = template.image_width or 794
    image_h = template.image_height or 1123

    # reportlab uses points (72 pt = 1 inch). We treat pixels as points for consistency.
    page_w = float(image_w)
    page_h = float(image_h)

    buffer = io.BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=(page_w, page_h))

    # ── Background image ──────────────────────────────────────────────────────
    if template.image:
        image_path = template.image.path
        try:
            img_reader = ImageReader(image_path)
            c.drawImage(img_reader, 0, 0, width=page_w, height=page_h, preserveAspectRatio=True, anchor="c")
        except Exception:
            logger.warning("PDF background image missing or unreadable for submission %s", submission.id)

    # ── Field values ──────────────────────────────────────────────────────────
    # reportlab origin is bottom-left; frontend uses top-left percentages.
    for field in fields:
        field_id = field.get("id")
        value = form_data.get(field_id, "")
        if not value or not field_id:
            continue

        pos = field_positions.get(field_id)
        if not pos:
            continue

        # Convert % → points (flip Y axis: reportlab Y=0 is bottom)
        x = (pos["x"] / 100.0) * page_w
        y_top = (pos["y"] / 100.0) * page_h
        w = (pos["width"] / 100.0) * page_w
        h = (pos["height"] / 100.0) * page_h

        # reportlab y is from bottom
        y_bottom = page_h - y_top - h

        font_size = min(max(7, h * 0.55), 24)
        c.setFont("Helvetica", font_size)
        c.setFillColorRGB(0.067, 0.094, 0.153)  # #111827

        # Draw text with word wrap inside the field box
        _draw_text_in_box(c, value, x + 2, y_bottom + 2, w - 4, h - 4, font_size)

    c.save()
    buffer.seek(0)

    file_name = f"submission_{submission.id}_v{submission.version_number}.pdf"
    submission.pdf.save(file_name, ContentFile(buffer.read()), save=True)
    return file_name


def _draw_text_in_box(c, text, x, y, width, height, font_size):
    """
    Draws text inside a box, wrapping lines that are too long.
    x, y is bottom-left of the box in reportlab coordinates.
    """
    from reportlab.lib.utils import simpleSplit

    lines = []
    for paragraph in text.split("\n"):
        wrapped = simpleSplit(paragraph, "Helvetica", font_size, width)
        lines.extend(wrapped if wrapped else [""])

    line_height = font_size * 1.3
    # Start from top of box, draw downward
    current_y = y + height - font_size
    for line in lines:
        if current_y < y:
            break
        c.drawString(x, current_y, line)
        current_y -= line_height
