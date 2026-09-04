"""Tests for POST /student-submission/<pk>/preview-pdf/ (APK Save as PDF)."""

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from opaque_keys.edx.keys import CourseKey, UsageKey
from rest_framework.test import APIRequestFactory, force_authenticate

from tas_app.models import Submission, Template, TemplateBlock, TemplateType
from tas_app.views import StudentSubmissionPreviewPdfAPIView


User = get_user_model()


def _unique(prefix):
    return f"{prefix}{uuid.uuid4().hex[:10]}"


def _make_draft_submission(form_data=None):
    user = User.objects.create_user(
        username=_unique("prevuser"),
        email=f"{_unique('prev')}@example.com",
        password="password",
    )
    template_type = TemplateType.objects.create(
        name=_unique("Preview Type"),
        slug=_unique("preview-type"),
    )
    template = Template.objects.create(
        template_type=template_type,
        name=_unique("Preview Template"),
        image_width=800,
        image_height=1000,
        fields=[{"id": "answer", "label": "Answer", "fontSize": 14}],
        field_positions={"answer": {"x": 10, "y": 10, "width": 40, "height": 20}},
        created_by=user,
    )
    usage_key = UsageKey.from_string(
        f"block-v1:edX+DemoX+2026_T1+type@problem+block@{_unique('prev')}"
    )
    course_key = CourseKey.from_string("course-v1:edX+DemoX+2026_T1")
    block = TemplateBlock.objects.create(
        template=template,
        usage_key=usage_key,
        course_key=course_key,
        assigned_by=user,
    )
    submission = Submission.objects.create(
        student=user,
        template_block=block,
        course_key=course_key,
        usage_key=usage_key,
        form_data=form_data or {"answer": "draft answer"},
        status=Submission.STATUS_DRAFT,
        version_number=2,
    )
    return submission


class StudentSubmissionPreviewPdfTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = StudentSubmissionPreviewPdfAPIView.as_view()

    def _post(self, user, pk, body=None):
        request = self.factory.post(
            f"/api/v1/student-submission/{pk}/preview-pdf/",
            body or {},
            format="json",
        )
        if user is not None:
            force_authenticate(request, user=user)
        return self.view(request, pk=pk)

    def test_owner_preview_keeps_draft_and_does_not_write_official_pdf(self):
        """Verify preview PDF is stored separately; status and version stay draft."""
        submission = _make_draft_submission()
        version_before = submission.version_number
        response = self._post(submission.student, submission.pk, {"form_data": {"answer": "new preview"}})
        self.assertEqual(response.status_code, 200)
        self.assertIn("preview_pdf_url", response.data)
        self.assertIn("/media/", response.data["preview_pdf_url"])

        submission.refresh_from_db()
        self.assertEqual(submission.status, Submission.STATUS_DRAFT)
        self.assertEqual(submission.version_number, version_before)
        self.assertEqual(submission.form_data, {"answer": "new preview"})
        self.assertTrue(submission.preview_pdf)
        self.assertFalse(submission.pdf)
        self.assertFalse(submission.tas_submission_versions.exists())

    def test_other_user_receives_404(self):
        """Verify another authenticated user cannot generate a preview PDF."""
        submission = _make_draft_submission()
        other = User.objects.create_user(
            username=_unique("other"),
            email=f"{_unique('other')}@example.com",
            password="password",
        )
        response = self._post(other, submission.pk, {"form_data": {"answer": "steal"}})
        self.assertEqual(response.status_code, 404)
        submission.refresh_from_db()
        self.assertFalse(submission.preview_pdf)
        self.assertEqual(submission.form_data, {"answer": "draft answer"})

    def test_anonymous_receives_401(self):
        """Verify unauthenticated preview-pdf requests are rejected."""
        submission = _make_draft_submission()
        response = self._post(None, submission.pk, {"form_data": {"answer": "anon"}})
        self.assertIn(response.status_code, (401, 403))
        submission.refresh_from_db()
        self.assertFalse(submission.preview_pdf)
