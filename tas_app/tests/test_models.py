import factory
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from opaque_keys.edx.keys import CourseKey, UsageKey

from tas_app.models import (
    InstructorFeedback,
    InstructorFeedbackVersion,
    Submission,
    SubmissionVersion,
    Template,
    TemplateBlock,
    TemplateType,
    STATUS_APPROVED,
    STATUS_PENDING,
)


User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user_{n}")
    email = factory.Sequence(lambda n: f"user_{n}@example.com")


class TemplateTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TemplateType

    name = factory.Sequence(lambda n: f"Type {n}")
    slug = factory.Sequence(lambda n: f"type-{n}")
    description = "Template type description"
    is_active = True


class TemplateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Template

    template_type = factory.SubFactory(TemplateTypeFactory)
    name = factory.Sequence(lambda n: f"Template {n}")
    description = "Template description"
    image_width = 1200
    image_height = 800
    fields = [{"name": "answer", "active": True}, {"name": "hidden", "active": False}]
    field_positions = {"answer": {"x": 20, "y": 30}}
    is_public = False
    is_active = True
    created_by = factory.SubFactory(UserFactory)


class TemplateBlockFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TemplateBlock

    template = factory.SubFactory(TemplateFactory)
    usage_key = factory.LazyFunction(lambda: UsageKey.from_string("block-v1:edX+DemoX+2026_T1+type@problem+block@tas1"))
    course_key = factory.LazyFunction(lambda: CourseKey.from_string("course-v1:edX+DemoX+2026_T1"))
    display_name = "Template Based Assignment"
    instructions = "Read and submit"
    rubrics = [{"title": "Quality", "max_score": 10}]
    sort_order = 0
    assigned_by = factory.SubFactory(UserFactory)


class SubmissionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Submission

    student = factory.SubFactory(UserFactory)
    template_block = factory.SubFactory(TemplateBlockFactory)
    course_key = factory.LazyAttribute(lambda o: o.template_block.course_key)
    usage_key = factory.LazyAttribute(lambda o: o.template_block.usage_key)
    form_data = {"answer": "draft"}
    status = Submission.STATUS_DRAFT
    version_number = 1


class SubmissionVersionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SubmissionVersion

    submission = factory.SubFactory(SubmissionFactory)
    version_number = 1
    form_data = {"answer": "snapshot"}


class InstructorFeedbackFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = InstructorFeedback

    submission = factory.SubFactory(SubmissionFactory)
    instructor = factory.SubFactory(UserFactory)
    rubrics = [{"title": "Quality", "score": 8}]
    comment = "Solid work."
    status = STATUS_PENDING


class TemplateTypeModelTest(TestCase):
    def test_template_type_str_returns_name(self):
        """Verify TemplateType string representation returns name."""
        template_type = TemplateTypeFactory(name="Essay")
        self.assertEqual(str(template_type), "Essay")

    def test_template_type_name_unique_constraint_raises_integrity_error(self):
        """Verify duplicate TemplateType name violates unique constraint."""
        TemplateTypeFactory(name="Case Study")
        with self.assertRaises(IntegrityError):
            TemplateTypeFactory(name="Case Study")

    def test_template_type_meta_ordering_is_name(self):
        """Verify TemplateType default ordering is by name ascending."""
        self.assertEqual(TemplateType._meta.ordering, ["name"])


class TemplateModelTest(TestCase):
    def test_template_str_includes_type_name(self):
        """Verify Template string representation includes template type."""
        template = TemplateFactory(name="Main", template_type__name="Essay")
        self.assertEqual(str(template), "Main (Type: Essay)")

    def test_template_active_fields_filters_inactive_fields(self):
        """Verify active_fields excludes field entries marked inactive."""
        template = TemplateFactory(fields=[{"name": "a", "active": True}, {"name": "b", "active": False}])
        self.assertEqual(template.active_fields(), [{"name": "a", "active": True}])

    def test_template_image_aspect_ratio_computed_correctly(self):
        """Verify image_aspect_ratio returns width divided by height."""
        template = TemplateFactory(image_width=1000, image_height=500)
        self.assertEqual(template.image_aspect_ratio, 2)

    def test_template_image_aspect_ratio_returns_none_when_height_missing(self):
        """Verify image_aspect_ratio returns None when image height is zero."""
        template = TemplateFactory(image_width=1000, image_height=0)
        self.assertIsNone(template.image_aspect_ratio)

    def test_template_meta_contains_expected_composite_index(self):
        """Verify Template meta has template_type/is_public/is_active index."""
        index_fields = [tuple(index.fields) for index in Template._meta.indexes]
        self.assertIn(("template_type", "is_public", "is_active"), index_fields)


class TemplateBlockModelTest(TestCase):
    def test_template_block_str_includes_template_and_usage_key(self):
        """Verify TemplateBlock string representation contains template and usage_key."""
        block = TemplateBlockFactory(template__name="My Template")
        self.assertEqual(str(block), f"My Template - {block.usage_key}")

    def test_template_block_unique_together_usage_and_course_enforced(self):
        """Verify duplicate usage_key/course_key pair raises validation error."""
        block = TemplateBlockFactory()
        duplicate = TemplateBlockFactory.build(
            usage_key=block.usage_key,
            course_key=block.course_key,
        )
        with self.assertRaises(ValidationError):
            duplicate.validate_unique()

    def test_template_block_meta_ordering_is_sort_order(self):
        """Verify TemplateBlock ordering uses sort_order field."""
        self.assertEqual(TemplateBlock._meta.ordering, ["sort_order"])


class SubmissionModelTest(TestCase):
    def test_submission_is_draft_returns_true_for_draft_status(self):
        """Verify is_draft returns True for draft submissions."""
        submission = SubmissionFactory(status=Submission.STATUS_DRAFT)
        self.assertTrue(submission.is_draft())

    def test_submission_is_submitted_returns_true_for_submitted_status(self):
        """Verify is_submitted returns True for submitted submissions."""
        submission = SubmissionFactory(status=Submission.STATUS_SUBMITTED)
        self.assertTrue(submission.is_submitted())

    def test_submission_create_version_snapshot_creates_snapshot(self):
        """Verify create_version_snapshot persists the current submission version."""
        submission = SubmissionFactory(version_number=3, form_data={"answer": "v3"})
        submission.create_version_snapshot()
        exists = SubmissionVersion.objects.filter(submission=submission, version_number=3).exists()
        self.assertTrue(exists)

    def test_submission_create_version_snapshot_updates_existing_snapshot(self):
        """Verify create_version_snapshot updates existing snapshot for same version."""
        submission = SubmissionFactory(version_number=2, form_data={"answer": "old"})
        SubmissionVersionFactory(submission=submission, version_number=2, form_data={"answer": "before"})
        submission.form_data = {"answer": "updated"}
        submission.create_version_snapshot()
        snapshot = SubmissionVersion.objects.get(submission=submission, version_number=2)
        self.assertEqual(snapshot.form_data, {"answer": "updated"})

    def test_submission_unique_together_student_course_usage_enforced(self):
        """Verify one submission per student/course/usage key is enforced."""
        submission = SubmissionFactory()
        duplicate = SubmissionFactory.build(
            student=submission.student,
            course_key=submission.course_key,
            usage_key=submission.usage_key,
        )
        with self.assertRaises(ValidationError):
            duplicate.validate_unique()


class SubmissionVersionModelTest(TestCase):
    def test_submission_version_str_contains_version_suffix(self):
        """Verify SubmissionVersion string contains version marker."""
        version = SubmissionVersionFactory(version_number=5)
        self.assertIn("v5", str(version))

    def test_submission_version_unique_together_submission_version_enforced(self):
        """Verify duplicate submission/version pair violates unique together."""
        version = SubmissionVersionFactory(version_number=1)
        duplicate = SubmissionVersionFactory.build(submission=version.submission, version_number=1)
        with self.assertRaises(ValidationError):
            duplicate.validate_unique()

    def test_submission_version_meta_ordering_descending_version(self):
        """Verify SubmissionVersion ordering is descending by version_number."""
        self.assertEqual(SubmissionVersion._meta.ordering, ["-version_number"])


class InstructorFeedbackModelTest(TestCase):
    def test_instructor_feedback_str_includes_human_status(self):
        """Verify InstructorFeedback string uses readable status text."""
        feedback = InstructorFeedbackFactory(status=STATUS_APPROVED)
        self.assertIn("Approved", str(feedback))

    def test_instructor_feedback_one_to_one_submission_enforced(self):
        """Verify only one feedback record can exist per submission."""
        feedback = InstructorFeedbackFactory()
        with self.assertRaises(IntegrityError):
            InstructorFeedbackFactory(submission=feedback.submission)

    def test_instructor_feedback_meta_ordering_descending_created(self):
        """Verify InstructorFeedback ordering returns newest first."""
        self.assertEqual(InstructorFeedback._meta.ordering, ["-created"])

    def test_create_version_snapshot_links_submission_version(self):
        """Verify feedback snapshots link to the matching submission version."""
        submission = SubmissionFactory(version_number=4)
        submission_version = SubmissionVersionFactory(submission=submission, version_number=4)
        feedback = InstructorFeedbackFactory(submission=submission, comment="Linked comment")
        feedback.create_version_snapshot()
        snapshot = InstructorFeedbackVersion.objects.get(instructor_feedback=feedback)
        self.assertEqual(snapshot.submission_version_id, submission_version.id)
        self.assertEqual(snapshot.comment, "Linked comment")

    def test_create_version_snapshot_allows_null_submission_version(self):
        """Verify feedback snapshots leave submission_version null when none exists."""
        submission = SubmissionFactory(version_number=2)
        feedback = InstructorFeedbackFactory(submission=submission)
        feedback.create_version_snapshot()
        snapshot = InstructorFeedbackVersion.objects.get(instructor_feedback=feedback)
        self.assertIsNone(snapshot.submission_version)
