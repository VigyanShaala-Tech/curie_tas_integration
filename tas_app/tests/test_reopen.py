"""Tests for student submission reopen (PATCH action=reopen)."""

import factory
from django.contrib.auth import get_user_model
from django.test import TestCase
from opaque_keys.edx.keys import CourseKey, UsageKey
from rest_framework.test import APIRequestFactory, force_authenticate

from tas_app.models import (
    InstructorFeedback,
    STATUS_PENDING,
    STATUS_REJECTED,
    Submission,
    Template,
    TemplateBlock,
    TemplateType,
)
from tas_app.views import StudentSubmissionDetailAPIView


User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"reopen_user_{n}")
    email = factory.Sequence(lambda n: f"reopen_user_{n}@example.com")


class TemplateTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TemplateType

    name = factory.Sequence(lambda n: f"Reopen Type {n}")
    slug = factory.Sequence(lambda n: f"reopen-type-{n}")
    description = "desc"


class TemplateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Template

    template_type = factory.SubFactory(TemplateTypeFactory)
    name = factory.Sequence(lambda n: f"Reopen Template {n}")
    image_width = 1024
    image_height = 768
    fields = [{"id": "answer", "label": "Answer", "active": True}]
    field_positions = {"answer": {"x": 10, "y": 10}}
    created_by = factory.SubFactory(UserFactory)


class TemplateBlockFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TemplateBlock

    template = factory.SubFactory(TemplateFactory)
    usage_key = factory.LazyFunction(
        lambda: UsageKey.from_string("block-v1:edX+DemoX+2026_T1+type@problem+block@reopen")
    )
    course_key = factory.LazyFunction(lambda: CourseKey.from_string("course-v1:edX+DemoX+2026_T1"))
    assigned_by = factory.SubFactory(UserFactory)


class SubmissionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Submission

    student = factory.SubFactory(UserFactory)
    template_block = factory.SubFactory(TemplateBlockFactory)
    course_key = factory.LazyAttribute(lambda o: o.template_block.course_key)
    usage_key = factory.LazyAttribute(lambda o: o.template_block.usage_key)
    form_data = {"answer": "keep me"}
    status = Submission.STATUS_REJECTED
    version_number = 5


class StudentSubmissionReopenTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = StudentSubmissionDetailAPIView.as_view()

    def _patch(self, user, pk, body):
        request = self.factory.patch(f"/api/v1/student-submission/{pk}/", body, format="json")
        force_authenticate(request, user=user)
        return self.view(request, pk=pk)

    def test_reopen_rejected_sets_draft_preserves_form_data_and_version(self):
        """Verify rejected→draft reopen preserves form_data and version_number."""
        submission = SubmissionFactory(status=Submission.STATUS_REJECTED, version_number=7)
        InstructorFeedback.objects.create(
            submission=submission,
            status=STATUS_REJECTED,
            comment="Needs work",
            rubrics=[],
        )
        response = self._patch(submission.student, submission.pk, {"action": "reopen"})
        self.assertEqual(response.status_code, 200)
        submission.refresh_from_db()
        self.assertEqual(submission.status, Submission.STATUS_DRAFT)
        self.assertEqual(submission.form_data, {"answer": "keep me"})
        self.assertEqual(submission.version_number, 7)
        self.assertEqual(submission.feedback.status, STATUS_PENDING)
        self.assertEqual(response.data["status"], Submission.STATUS_DRAFT)
        self.assertEqual(response.data["form_data"], {"answer": "keep me"})

    def test_reopen_approved_rejected(self):
        """Verify approved submissions cannot be reopened."""
        submission = SubmissionFactory(status=Submission.STATUS_APPROVED)
        response = self._patch(submission.student, submission.pk, {"action": "reopen"})
        self.assertEqual(response.status_code, 400)

    def test_reopen_draft_rejected(self):
        """Verify draft submissions cannot be reopened."""
        submission = SubmissionFactory(status=Submission.STATUS_DRAFT)
        response = self._patch(submission.student, submission.pk, {"action": "reopen"})
        self.assertEqual(response.status_code, 400)

    def test_reopen_submitted_rejected(self):
        """Verify submitted (pending review) cannot be reopened."""
        submission = SubmissionFactory(status=Submission.STATUS_SUBMITTED)
        response = self._patch(submission.student, submission.pk, {"action": "reopen"})
        self.assertEqual(response.status_code, 400)
