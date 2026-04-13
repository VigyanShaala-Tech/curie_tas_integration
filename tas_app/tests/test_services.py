import factory
from django.contrib.auth import get_user_model
from django.test import TestCase
from opaque_keys.edx.keys import CourseKey, UsageKey
from unittest.mock import MagicMock, patch

from tas_app.models import Submission, Template, TemplateBlock, TemplateType
from tas_app.permissions import IsSuperAdmin
from tas_app.signals.handlers import delete_tas_data_on_unit_delete


User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"service_user_{n}")
    email = factory.Sequence(lambda n: f"service_user_{n}@example.com")


class AdminUserFactory(UserFactory):
    is_staff = True
    is_superuser = True


class TemplateTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TemplateType

    name = factory.Sequence(lambda n: f"Service Type {n}")
    slug = factory.Sequence(lambda n: f"service-type-{n}")


class TemplateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Template

    template_type = factory.SubFactory(TemplateTypeFactory)
    name = factory.Sequence(lambda n: f"Service Template {n}")
    image_width = 100
    image_height = 100
    fields = []
    field_positions = {}
    created_by = factory.SubFactory(UserFactory)


class TemplateBlockFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TemplateBlock

    template = factory.SubFactory(TemplateFactory)
    usage_key = factory.LazyFunction(lambda: UsageKey.from_string("block-v1:edX+DemoX+2026_T1+type@problem+block@srv"))
    course_key = factory.LazyFunction(lambda: CourseKey.from_string("course-v1:edX+DemoX+2026_T1"))
    assigned_by = factory.SubFactory(AdminUserFactory)


class SubmissionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Submission

    student = factory.SubFactory(UserFactory)
    template_block = factory.SubFactory(TemplateBlockFactory)
    course_key = factory.LazyAttribute(lambda o: o.template_block.course_key)
    usage_key = factory.LazyAttribute(lambda o: o.template_block.usage_key)
    form_data = {"answer": "service"}


class IsSuperAdminPermissionTest(TestCase):
    def setUp(self):
        self.permission = IsSuperAdmin()
        self.view = MagicMock()

    def test_super_admin_user_has_permission(self):
        """Verify IsSuperAdmin allows authenticated superusers."""
        request = MagicMock(user=AdminUserFactory())
        self.assertTrue(self.permission.has_permission(request, self.view))

    def test_non_super_admin_user_denied(self):
        """Verify IsSuperAdmin denies authenticated non-superusers."""
        request = MagicMock(user=UserFactory())
        self.assertFalse(self.permission.has_permission(request, self.view))

    def test_anonymous_user_denied(self):
        """Verify IsSuperAdmin denies anonymous users."""
        anonymous_user = MagicMock(is_authenticated=False, is_superuser=False)
        request = MagicMock(user=anonymous_user)
        self.assertFalse(self.permission.has_permission(request, self.view))


class DeleteTasDataSignalServiceTest(TestCase):
    @patch("tas_app.signals.handlers.TemplateBlock.objects.filter")
    @patch("tas_app.signals.handlers.SubmissionVersion.objects.filter")
    @patch("tas_app.signals.handlers.InstructorFeedback.objects.filter")
    @patch("tas_app.signals.handlers.Submission.objects.filter")
    def test_delete_handler_deletes_related_data_for_usage_key(
        self,
        submission_filter_mock,
        feedback_filter_mock,
        version_filter_mock,
        block_filter_mock,
    ):
        """Verify signal handler deletes feedback, versions, submissions, and blocks for usage key."""
        submission_one = MagicMock()
        submission_two = MagicMock()
        submissions_qs = MagicMock()
        submissions_qs.__iter__.return_value = iter([submission_one, submission_two])
        submission_filter_mock.return_value = submissions_qs

        delete_tas_data_on_unit_delete(usage_key="block-v1:edX+DemoX+2026_T1+type@problem+block@srv")

        self.assertTrue(feedback_filter_mock.called)
        self.assertTrue(version_filter_mock.called)
        submissions_qs.delete.assert_called_once()
        block_filter_mock.return_value.delete.assert_called_once()

    @patch("tas_app.signals.handlers.Submission.objects.filter")
    def test_delete_handler_without_usage_key_skips_deletion(self, submission_filter_mock):
        """Verify signal handler exits early when usage_key is missing."""
        delete_tas_data_on_unit_delete(usage_key=None)
        submission_filter_mock.assert_not_called()

    @patch("tas_app.signals.handlers.TemplateBlock.objects.filter")
    @patch("tas_app.signals.handlers.Submission.objects.filter")
    def test_delete_handler_handles_exceptions_gracefully(self, submission_filter_mock, block_filter_mock):
        """Verify signal handler swallows internal exceptions to avoid signal crash."""
        submissions_qs = MagicMock()
        submissions_qs.__iter__.return_value = iter([])
        submissions_qs.delete.side_effect = RuntimeError("delete failed")
        submission_filter_mock.return_value = submissions_qs

        delete_tas_data_on_unit_delete(usage_key="block-v1:edX+DemoX+2026_T1+type@problem+block@srv")

        block_filter_mock.assert_not_called()
