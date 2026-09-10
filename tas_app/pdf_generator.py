"""
PDF generation for TAS submissions.

Uses reportlab to embed the template background image and overlay
student-filled field values at the correct percentage-based positions.

Layout contract (must stay aligned with frontend-app-template-assignment
src/tas/utils/fieldLayout.ts and FieldOverlay.tsx):

- Coordinates: field_positions as top-left percentages of image_width x image_height
- Font size: field.fontSize ?? max(10, min(20, fieldHeightPx * 0.6))
- Padding: 2px (content inset); do not copy overlay UI borders into the PDF
- Line-height: 1.3
- Color: #111827
- Weight: 400 (regular)
- Wrapping: white-space:pre-wrap; overflow-wrap:anywhere; word-break:break-word
- Overflow: hidden via INVISIBLE clip only (clipPath stroke=0, fill=0; never paint a field rect)
- Font: bundled Liberation Sans Regular (Arial-metric). Host OS fonts are
  recovery-only if the bundled TTF is missing.
"""

import io
import logging
from pathlib import Path

from django.core.files.base import ContentFile
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

logger = logging.getLogger(__name__)

# Inspected frontend values from fieldLayout.ts
FIELD_TEXT_PADDING_PX = 2
FIELD_TEXT_LINE_HEIGHT = 1.3
FIELD_TEXT_COLOR_RGB = (0.067, 0.094, 0.153)  # #111827
FIELD_FONT_NAME = "TASFieldFont"
BUNDLED_FONT_FILENAME = "LiberationSans-Regular.ttf"
BUNDLED_FONT_PATH = Path(__file__).resolve().parent / "fonts" / BUNDLED_FONT_FILENAME
_HELVETICA_FALLBACK = "Helvetica"

_registered_font_name = None

def bundled_font_path():
    """Absolute path to the project-controlled Liberation Sans Regular TTF."""
    return BUNDLED_FONT_PATH

def resolve_field_font_size(field, field_height_px):
    """
    Match frontend resolveFieldFontSize / calculateFontSize.

    Compute in frontend/image CSS pixels: field.fontSize when set;
    otherwise max(10, min(20, field_height_px * 0.6)).
    Convert the result to PDF units with frontend_px_to_pdf().
    """
    explicit = field.get("fontSize") if isinstance(field, dict) else None
    if explicit is not None and explicit != "":
        try:
            return float(explicit)
        except (TypeError, ValueError):
            pass
    return max(10.0, min(20.0, float(field_height_px) * 0.6))

def image_to_pdf_scale(image_size, page_size):
    """Isotropic scale from template image pixels to PDF page units."""
    image_size = float(image_size)
    if image_size <= 0:
        return 1.0
    return float(page_size) / image_size

def frontend_px_to_pdf(px, scale):
    """Convert a frontend CSS-px length into PDF units using page/image scale."""
    return float(px) * float(scale)

def _recovery_font_paths():
    """System TTFs used only when the bundled font cannot be loaded."""
    return (
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/msttcorefonts/Arial.ttf"),
        Path("/usr/share/fonts/truetype/msttcorefonts/arial.ttf"),
    )

def get_field_font_name():
    """
    Register and return the PDF field font name.

    Normal path: bundled LiberationSans-Regular.ttf as TASFieldFont.
    Recovery: system TTF, then ReportLab Helvetica, with a warning.
    """
    global _registered_font_name
    if _registered_font_name:
        return _registered_font_name

    bundled = bundled_font_path()
    if bundled.is_file():
        pdfmetrics.registerFont(TTFont(FIELD_FONT_NAME, str(bundled)))
        _registered_font_name = FIELD_FONT_NAME
        return _registered_font_name

    logger.warning(
        "Bundled TAS PDF font missing at %s; using recovery font path",
        bundled,
    )
    for path in _recovery_font_paths():
        if path.is_file():
            try:
                pdfmetrics.registerFont(TTFont(FIELD_FONT_NAME, str(path)))
                _registered_font_name = FIELD_FONT_NAME
                logger.warning("Registered recovery PDF font from %s", path)
                return _registered_font_name
            except Exception:  # noqa: BLE001
                logger.warning("Failed to register recovery PDF font %s", path, exc_info=True)

    logger.warning("Falling back to ReportLab Helvetica for TAS PDF fields")
    _registered_font_name = _HELVETICA_FALLBACK
    return _registered_font_name

def _break_overlong_token(token, font_name, font_size, max_width):
    """Split a token that is wider than the box (overflow-wrap: anywhere)."""
    if max_width <= 0:
        return [token] if token else [""]

    chunks = []
    current = ""
    for char in token:
        trial = current + char
        if current and pdfmetrics.stringWidth(trial, font_name, font_size) > max_width:
            chunks.append(current)
            current = char
        else:
            current = trial
    if current:
        chunks.append(current)
    return chunks or [""]

def wrap_field_text(text, font_name, font_size, max_width):
    """
    Wrap text like FieldOverlay / print HTML:

    white-space: pre-wrap (preserve newlines)
    wrap on spaces first; mid-word break when a token exceeds max_width
    (overflow-wrap: anywhere / word-break: break-word).
    """
    lines = []
    # str.split("\n") keeps empty paragraphs from consecutive newlines.
    for paragraph in (text or "").split("\n"):
        lines.extend(_wrap_paragraph(paragraph, font_name, font_size, max_width))
    return lines

def _wrap_paragraph(paragraph, font_name, font_size, max_width):
    if paragraph == "":
        return [""]
    if max_width <= 0:
        return [paragraph]

    words = paragraph.split(" ")
    lines = []
    current = None

    for word in words:
        if current is None:
            candidate = word
        else:
            candidate = current + " " + word

        if pdfmetrics.stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
            continue

        if current is not None:
            lines.append(current)
            current = None

        if pdfmetrics.stringWidth(word, font_name, font_size) <= max_width:
            current = word
            continue

        chunks = _break_overlong_token(word, font_name, font_size, max_width)
        lines.extend(chunks[:-1])
        current = chunks[-1]

    if current is not None:
        lines.append(current)
    elif not lines:
        lines.append("")
    return lines

def _draw_text_in_box(c, text, x, y, width, height, font_size, font_name):
    """
    Draw wrapped text inside a box and clip overflow without painting the box.

    x, y is bottom-left of the content box in reportlab coordinates.
    clipPath must use stroke=0, fill=0 so the rectangle is not filled/stroked.
    """
    c.saveState()
    clip_path = c.beginPath()
    clip_path.rect(x, y, width, height)
    # Invisible clip only. fill=1 would paint the field (black by default).
    c.clipPath(clip_path, stroke=0, fill=0)

    c.setFillColorRGB(*FIELD_TEXT_COLOR_RGB)
    c.setFont(font_name, font_size)

    lines = wrap_field_text(text, font_name, font_size, width)
    line_height = font_size * FIELD_TEXT_LINE_HEIGHT
    current_y = y + height - font_size
    for line in lines:
        if current_y < y:
            break
        c.drawString(x, current_y, line)
        current_y -= line_height

    c.restoreState()

def generate_submission_pdf(submission, dest_field="pdf"):
    """
    Generates a PDF for the given Submission and saves it onto dest_field
    ('pdf' = official submit artifact, 'preview_pdf' = Save as PDF preview).

    The PDF page size matches the template's natural image dimensions (pixels → points).
    Field values are placed using the same percentage coordinates as the frontend.
    """
    if dest_field not in ("pdf", "preview_pdf"):
        raise ValueError("dest_field must be 'pdf' or 'preview_pdf'")

    template = submission.template_block.template
    form_data = submission.form_data or {}
    fields = template.fields or []
    field_positions = template.field_positions or {}

    image_w = float(template.image_width or 794)
    image_h = float(template.image_height or 1123)

    # 1 template image pixel == 1 PDF point == 1 frontend CSS px on the
    # natural-size canvas / Save as PDF page. Do not apply 72/96.
    page_w = image_w
    page_h = image_h
    scale = image_to_pdf_scale(image_w, page_w)

    font_name = get_field_font_name()
    padding_pdf = frontend_px_to_pdf(FIELD_TEXT_PADDING_PX, scale)

    buffer = io.BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=(page_w, page_h))

    # ── Background image ──────────────────────────────────────────────────────
    if template.image:
        image_path = template.image.path
        try:
            img_reader = ImageReader(image_path)
            c.drawImage(
                img_reader,
                0,
                0,
                width=page_w,
                height=page_h,
                preserveAspectRatio=True,
                anchor="c",
            )
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

        x = (float(pos.get("x") or 0) / 100.0) * page_w
        y_top = (float(pos.get("y") or 0) / 100.0) * page_h
        w = (float(pos.get("width") or 0) / 100.0) * page_w
        h = (float(pos.get("height") or 0) / 100.0) * page_h
        if w <= 0 or h <= 0:
            continue

        y_bottom = page_h - y_top - h

        field_height_px = (float(pos.get("height") or 0) / 100.0) * image_h
        font_size_px = resolve_field_font_size(field, field_height_px)
        font_size_pdf = frontend_px_to_pdf(font_size_px, scale)

        content_x = x + padding_pdf
        content_y = y_bottom + padding_pdf
        content_w = max(0.0, w - padding_pdf * 2)
        content_h = max(0.0, h - padding_pdf * 2)

        _draw_text_in_box(
            c, value, content_x, content_y, content_w, content_h, font_size_pdf, font_name
        )

    c.save()
    buffer.seek(0)

    if dest_field == "preview_pdf":
        file_name = f"preview_{submission.id}.pdf"
    else:
        file_name = f"submission_{submission.id}_v{submission.version_number}.pdf"

    getattr(submission, dest_field).save(file_name, ContentFile(buffer.read()), save=True)
    return file_name
