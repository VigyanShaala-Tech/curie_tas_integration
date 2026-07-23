import factory
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from opaque_keys.edx.keys import CourseKey, UsageKey
from rest_framework.test import APIRequestFactory

from tas_app.models import (
    InstructorFeedback,
    InstructorFeedbackVersion,
    STATUS_APPROVED,
    Submission,
    SubmissionVersion,
    Template,
    TemplateBlock,
    TemplateType,
)
from tas_app.serializers import (
    StudentSubmissionCreateSerializer,
    StudentSubmissionPatchSerializer,
    StudentSubmissionResponseSerializer,
    StudentSubmissionSubmitSerializer,
    SubmissionVersionSerializer,
    TemplateBasicSerializer,
    TemplateSerializer,
    TemplateTypeSerializer,
)


User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"serializer_user_{n}")
    email = factory.Sequence(lambda n: f"serializer_user_{n}@example.com")


class TemplateTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TemplateType

    name = factory.Sequence(lambda n: f"Serializer Type {n}")
    slug = factory.Sequence(lambda n: f"serializer-type-{n}")
    description = "Serializer type description"


class TemplateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Template

    template_type = factory.SubFactory(TemplateTypeFactory)
    name = factory.Sequence(lambda n: f"Serializer Template {n}")
    image_width = 1024
    image_height = 768
    fields = [{"name": "answer", "active": True}]
    field_positions = {"answer": {"x": 10, "y": 10}}
    created_by = factory.SubFactory(UserFactory)


class TemplateBlockFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TemplateBlock

    template = factory.SubFactory(TemplateFactory)
    usage_key = factory.LazyFunction(lambda: UsageKey.from_string("block-v1:edX+DemoX+2026_T1+type@problem+block@s1"))
    course_key = factory.LazyFunction(lambda: CourseKey.from_string("course-v1:edX+DemoX+2026_T1"))
    assigned_by = factory.SubFactory(UserFactory)


class SubmissionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Submission

    student = factory.SubFactory(UserFactory)
    template_block = factory.SubFactory(TemplateBlockFactory)
    course_key = factory.LazyAttribute(lambda o: o.template_block.course_key)
    usage_key = factory.LazyAttribute(lambda o: o.template_block.usage_key)
    form_data = {"answer": "text"}
    status = Submission.STATUS_DRAFT
    version_number = 1


class TemplateTypeSerializerTest(TestCase):
    def test_template_type_serializer_accepts_valid_data(self):
        """Verify serializer accepts valid template type payload."""
        serializer = TemplateTypeSerializer(
            data={"name": "Essay", "slug": "essay", "description": "Desc", "is_active": True}
        )
        self.assertTrue(serializer.is_valid())

    def test_template_type_serializer_rejects_missing_name(self):
        """Verify serializer rejects payload without required name."""
        serializer = TemplateTypeSerializer(data={"slug": "essay", "description": "Desc", "is_active": True})
        self.assertFalse(serializer.is_valid())


class TemplateSerializerTest(TestCase):
    def test_template_serializer_accepts_valid_payload(self):
        """Verify serializer validates complete template payload."""
        template_type = TemplateTypeFactory()
        serializer = TemplateSerializer(
            data={
                "template_type": template_type.id,
                "name": "Template A",
                "description": "Desc",
                "image_width": 1000,
                "image_height": 500,
                "fields": [{"name": "field1"}],
                "field_positions": {"field1": {"x": 1, "y": 2}},
                "is_public": True,
                "is_active": True,
            }
        )
        self.assertTrue(serializer.is_valid())

    def test_template_serializer_rejects_wrong_field_positions_type(self):
        """Verify serializer rejects invalid field_positions data type."""
        template_type = TemplateTypeFactory()
        serializer = TemplateSerializer(
            data={
                "template_type": template_type.id,
                "name": "Template A",
                "image_width": 1000,
                "image_height": 500,
                "fields": [],
                "field_positions": ["not", "dict"],
                "is_public": True,
                "is_active": True,
            }
        )
        self.assertFalse(serializer.is_valid())


class StudentSubmissionCreateSerializerTest(TestCase):
    def test_create_serializer_accepts_matching_block_course_usage(self):
        """Verify serializer validates payload when keys match template block."""
        block = TemplateBlockFactory()
        serializer = StudentSubmissionCreateSerializer(
            data={
                "template_block_id": str(block.id),
                "course_key": str(block.course_key),
                "usage_key": str(block.usage_key),
                "form_data": {"answer": "ok"},
                "status": Submission.STATUS_DRAFT,
            }
        )
        self.assertTrue(serializer.is_valid())

    def test_create_serializer_rejects_invalid_course_key(self):
        """Verify serializer rejects invalid course key format."""
        block = TemplateBlockFactory()
        serializer = StudentSubmissionCreateSerializer(
            data={
                "template_block_id": str(block.id),
                "course_key": "bad-course-key",
                "usage_key": str(block.usage_key),
                "form_data": {"answer": "ok"},
                "status": Submission.STATUS_DRAFT,
            }
        )
        self.assertFalse(serializer.is_valid())

    def test_create_serializer_rejects_invalid_usage_key(self):
        """Verify serializer rejects invalid usage key format."""
        block = TemplateBlockFactory()
        serializer = StudentSubmissionCreateSerializer(
            data={
                "template_block_id": str(block.id),
                "course_key": str(block.course_key),
                "usage_key": "bad-usage-key",
                "form_data": {"answer": "ok"},
                "status": Submission.STATUS_DRAFT,
            }
        )
        self.assertFalse(serializer.is_valid())

    def test_create_serializer_rejects_mismatched_course_key(self):
        """Verify serializer rejects when course key does not match block."""
        block = TemplateBlockFactory()
        serializer = StudentSubmissionCreateSerializer(
            data={
                "template_block_id": str(block.id),
                "course_key": "course-v1:edX+Another+2026_T1",
                "usage_key": str(block.usage_key),
                "form_data": {"answer": "ok"},
                "status": Submission.STATUS_DRAFT,
            }
        )
        self.assertFalse(serializer.is_valid())

    def test_create_serializer_rejects_unknown_template_block(self):
        """Verify serializer rejects unknown template block id."""
        serializer = StudentSubmissionCreateSerializer(
            data={
                "template_block_id": "999999",
                "course_key": "course-v1:edX+DemoX+2026_T1",
                "usage_key": "block-v1:edX+DemoX+2026_T1+type@problem+block@none",
                "form_data": {"answer": "ok"},
                "status": Submission.STATUS_DRAFT,
            }
        )
        self.assertFalse(serializer.is_valid())


class StudentSubmissionPatchSerializerTest(TestCase):
    def test_reopen_action_is_valid_alone(self):
        """Verify reopen action validates without form_data."""
        serializer = StudentSubmissionPatchSerializer(data={"action": "reopen"})
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_reopen_rejects_form_data(self):
        """Verify reopen cannot be combined with form_data."""
        serializer = StudentSubmissionPatchSerializer(
            data={"action": "reopen", "form_data": {"a": "1"}}
        )
        self.assertFalse(serializer.is_valid())

    def test_empty_body_is_invalid(self):
        """Verify empty PATCH body is rejected."""
        serializer = StudentSubmissionPatchSerializer(data={})
        self.assertFalse(serializer.is_valid())

    def test_form_data_alone_is_valid(self):
        """Verify form_data PATCH still validates."""
        serializer = StudentSubmissionPatchSerializer(data={"form_data": {"a": "1"}})
        self.assertTrue(serializer.is_valid(), serializer.errors)


@override_settings(MEDIA_URL="/media/")
class StudentSubmissionResponseSerializerTest(TestCase):
    def setUp(self):
        self.request_factory = APIRequestFactory()

    def test_response_serializer_returns_blank_pdf_url_without_pdf(self):
        """Verify response serializer returns empty pdf_url when no PDF exists."""
        submission = SubmissionFactory(pdf=None)
        serializer = StudentSubmissionResponseSerializer(submission)
        self.assertEqual(serializer.data["pdf_url"], "")

    def test_response_serializer_builds_absolute_pdf_url_with_request(self):
        """Verify response serializer builds absolute URL with request context."""
        submission = SubmissionFactory()
        submission.pdf = SimpleUploadedFile("answer.pdf", b"pdf-bytes", content_type="application/pdf")
        submission.save()
        request = self.request_factory.get("/")
        serializer = StudentSubmissionResponseSerializer(submission, context={"request": request})
        self.assertIn("http://testserver/media/", serializer.data["pdf_url"])


class StudentSubmissionSubmitSerializerTest(TestCase):
    def test_submit_serializer_returns_none_pdf_url_without_pdf(self):
        """Verify submit serializer returns None when pdf is absent."""
        submission = SubmissionFactory(pdf=None)
        serializer = StudentSubmissionSubmitSerializer(submission)
        self.assertIsNone(serializer.data["pdf_url"])


@override_settings(MEDIA_URL="/media/")
class SubmissionVersionSerializerTest(TestCase):
    def setUp(self):
        self.request_factory = APIRequestFactory()

    def _make_version(self, version_number=2, with_pdf=True):
        submission = SubmissionFactory(version_number=version_number)
        version = SubmissionVersion.objects.create(
            submission=submission,
            version_number=version_number,
            form_data={"answer": "v"},
        )
        if with_pdf:
            version.pdf = SimpleUploadedFile("v.pdf", b"pdf-bytes", content_type="application/pdf")
            version.save()
        return submission, version

    def test_linked_feedback_marks_available(self):
        """Verify linked feedback sets feedback_available and clears unavailable reason."""
        submission, version = self._make_version(version_number=3)
        feedback = InstructorFeedback.objects.create(
            submission=submission,
            comment="Nice work",
            status=STATUS_APPROVED,
            rubrics=[],
        )
        InstructorFeedbackVersion.objects.create(
            instructor_feedback=feedback,
            submission_version=version,
            version_number=1,
            comment="Nice work",
            status=STATUS_APPROVED,
            rubrics=[],
        )
        request = self.request_factory.get("/")
        data = SubmissionVersionSerializer(
            version,
            context={"request": request, "current_version_number": submission.version_number},
        ).data
        self.assertTrue(data["feedback_available"])
        self.assertIsNone(data["feedback_unavailable_reason"])
        self.assertEqual(data["feedback_status"], STATUS_APPROVED)
        self.assertEqual(data["instructor_comment"], "Nice work")
        self.assertIn("http://testserver/media/", data["pdf_url"])
        self.assertEqual(data["pdf_url"], data["download_url"])
        self.assertEqual(data["submitted_at"], data["saved_at"])

    def test_current_version_without_link_is_pending(self):
        """Verify current unlinked version reports pending."""
        submission, version = self._make_version(version_number=5)
        data = SubmissionVersionSerializer(
            version,
            context={"current_version_number": submission.version_number},
        ).data
        self.assertFalse(data["feedback_available"])
        self.assertEqual(data["feedback_unavailable_reason"], "pending")
        self.assertIsNone(data["feedback_status"])
        self.assertEqual(data["instructor_comment"], "")

    def test_historical_unlinked_version_reason(self):
        """Verify older unlinked versions report unlinked_historical."""
        submission, version = self._make_version(version_number=1)
        submission.version_number = 4
        submission.save(update_fields=["version_number"])
        data = SubmissionVersionSerializer(
            version,
            context={"current_version_number": submission.version_number},
        ).data
        self.assertFalse(data["feedback_available"])
        self.assertEqual(data["feedback_unavailable_reason"], "unlinked_historical")


@override_settings(MEDIA_URL="/media/")
class TemplateBasicSerializerTest(TestCase):
    def setUp(self):
        self.request_factory = APIRequestFactory()

    def test_template_basic_serializer_returns_none_thumbnail_url_without_thumbnail(self):
        """Verify basic serializer returns None when thumbnail is missing."""
        template = TemplateFactory(thumbnail=None)
        serializer = TemplateBasicSerializer(template)
        self.assertIsNone(serializer.data["thumbnail_url"])

    def test_template_basic_serializer_builds_absolute_thumbnail_url(self):
        """Verify basic serializer returns absolute thumbnail URL with request context."""
        template = TemplateFactory()
        template.thumbnail = SimpleUploadedFile("thumb.png", b"png-bytes", content_type="image/png")
        template.save()
        request = self.request_factory.get("/")
        serializer = TemplateBasicSerializer(template, context={"request": request})
        self.assertIn("http://testserver/media/", serializer.data["thumbnail_url"])
