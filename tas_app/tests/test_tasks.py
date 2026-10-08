import factory
from types import SimpleNamespace
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from opaque_keys.edx.keys import CourseKey, UsageKey
from unittest.mock import patch

from tas_app.models import CurieReview, Submission, Template, TemplateBlock, TemplateType


User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"task_user_{n}")
    email = factory.Sequence(lambda n: f"task_user_{n}@example.com")


class TemplateTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TemplateType

    name = factory.Sequence(lambda n: f"Task Type {n}")
    slug = factory.Sequence(lambda n: f"task-type-{n}")


class TemplateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Template

    template_type = factory.SubFactory(TemplateTypeFactory)
    name = factory.Sequence(lambda n: f"Task Template {n}")
    image_width = 100
    image_height = 100
    fields = []
    field_positions = {}
    created_by = factory.SubFactory(UserFactory)


class TemplateBlockFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TemplateBlock

    template = factory.SubFactory(TemplateFactory)
    usage_key = factory.LazyFunction(lambda: UsageKey.from_string("block-v1:edX+DemoX+2026_T1+type@problem+block@tsk"))
    course_key = factory.LazyFunction(lambda: CourseKey.from_string("course-v1:edX+DemoX+2026_T1"))
    assigned_by = factory.SubFactory(UserFactory)


class SubmissionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Submission

    student = factory.SubFactory(UserFactory)
    template_block = factory.SubFactory(TemplateBlockFactory)
    course_key = factory.LazyAttribute(lambda o: o.template_block.course_key)
    usage_key = factory.LazyAttribute(lambda o: o.template_block.usage_key)
    form_data = {"answer": "task"}


class CeleryConfigurationTest(TestCase):
    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_celery_eager_setting_enabled_for_task_tests(self):
        """Verify CELERY_TASK_ALWAYS_EAGER is explicitly enabled in task tests."""
        from django.conf import settings

        self.assertTrue(settings.CELERY_TASK_ALWAYS_EAGER)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("tas_app.models.Submission.create_version_snapshot")
    def test_task_like_side_effect_can_be_mocked(self, create_snapshot_mock):
        """Verify async-like side effects are mockable for isolated task testing."""
        submission = SubmissionFactory()
        submission.create_version_snapshot()
        create_snapshot_mock.assert_called_once()

    @patch("tas_app.tasks.create_new_event_transaction_id", return_value="event-id")
    @patch("tas_app.tasks.set_event_transaction_type")
    @patch("tas_app.tasks.recalculate_subsection_grade_v3.apply_async")
    @patch("tas_app.tasks.StudentModule.objects.update_or_create")
    def test_successful_curie_grade_push_marks_review_published(
        self,
        mocked_update,
        _mocked_recalculate,
        _mocked_event_type,
        _mocked_event_id,
    ):
        from django.utils import timezone

        from tas_app.tasks import push_grade_to_lms

        submission = SubmissionFactory()
        review = CurieReview.objects.create(
            submission=submission,
            submission_version_number=submission.version_number,
        )
        mocked_update.return_value = (SimpleNamespace(modified=timezone.now()), True)

        push_grade_to_lms.run(
            usage_key_str=str(submission.usage_key),
            course_key_str=str(submission.course_key),
            student_id=submission.student_id,
            earned=24,
            max_possible=30,
            curie_trigger_id=str(review.trigger_id),
        )

        review.refresh_from_db()
        self.assertIsNotNone(review.grade_published_at)
