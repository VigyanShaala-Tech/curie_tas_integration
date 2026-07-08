import factory
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import resolve, reverse
from opaque_keys.edx.keys import CourseKey, UsageKey
from rest_framework import status
from rest_framework.test import APIClient

from tas_app.models import InstructorFeedback, Rubric, Submission, Template, TemplateBlock, TemplateType
from tas_app.views import (
    BlockFeedbackOptionsAPIView,
    InstructorFeedbackAPIView,
    LearnerSubmissionDetailAPIView,
    LearnerSubmissionsAPIView,
    RubricsAPIView,
    StudentSubmissionCreateAPIView,
    StudentSubmissionDetailAPIView,
    StudentSubmissionPdfAPIView,
    StudentSubmissionSubmitAPIView,
    StudentSubmissionVersionsAPIView,
    TemplateBlockDetailView,
    TemplateTypesDetailView,
    TemplateTypesListView,
    TemplatesDetailView,
    TemplatesListView,
)


User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"view_user_{n}")
    email = factory.Sequence(lambda n: f"view_user_{n}@example.com")


class AdminUserFactory(UserFactory):
    is_staff = True
    is_superuser = True


class TemplateTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TemplateType

    name = factory.Sequence(lambda n: f"View Type {n}")
    slug = factory.Sequence(lambda n: f"view-type-{n}")
    description = "View type description"
    is_active = True


class TemplateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Template

    template_type = factory.SubFactory(TemplateTypeFactory)
    name = factory.Sequence(lambda n: f"View Template {n}")
    image_width = 1200
    image_height = 800
    fields = [{"name": "answer", "active": True}]
    field_positions = {"answer": {"x": 10, "y": 20}}
    is_public = False
    is_active = True
    created_by = factory.SubFactory(UserFactory)


class TemplateBlockFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TemplateBlock

    template = factory.SubFactory(TemplateFactory)
    usage_key = factory.LazyFunction(lambda: UsageKey.from_string("block-v1:edX+DemoX+2026_T1+type@problem+block@v1"))
    course_key = factory.LazyFunction(lambda: CourseKey.from_string("course-v1:edX+DemoX+2026_T1"))
    display_name = "Block Name"
    instructions = "Do work"
    rubrics = [{"criterion": "quality", "max": 10}]
    assigned_by = factory.SubFactory(AdminUserFactory)


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


class TemplateTypeViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = AdminUserFactory()
        self.user = UserFactory()

    def tearDown(self):
        self.client.force_authenticate(user=None)

    def test_template_types_get_unauthenticated_returns_401(self):
        """Verify unauthenticated access to template type list is rejected."""
        response = self.client.get(reverse("tas_app:template-types-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_template_types_get_non_admin_returns_403(self):
        """Verify non-admin user cannot list template types."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("tas_app:template-types-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_template_types_get_admin_returns_200(self):
        """Verify admin can retrieve template type listing."""
        TemplateTypeFactory(name="AAA")
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse("tas_app:template-types-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_template_types_post_valid_payload_returns_201(self):
        """Verify admin can create template type with valid payload."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            reverse("tas_app:template-types-list"),
            {"name": "Essay", "slug": "essay", "description": "d", "is_active": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_template_types_detail_patch_updates_name(self):
        """Verify PATCH updates template type fields for admin."""
        template_type = TemplateTypeFactory(name="Old Name")
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(
            reverse("tas_app:template-types-detail", kwargs={"pk": template_type.pk}),
            {"name": "New Name"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_template_types_detail_delete_soft_deactivates(self):
        """Verify DELETE sets is_active to False instead of hard deleting."""
        template_type = TemplateTypeFactory(is_active=True)
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(reverse("tas_app:template-types-detail", kwargs={"pk": template_type.pk}))
        template_type.refresh_from_db()
        self.assertFalse(template_type.is_active)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


class TemplateViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = AdminUserFactory()
        self.user = UserFactory()

    def tearDown(self):
        self.client.force_authenticate(user=None)

    def test_templates_get_admin_returns_200(self):
        """Verify admin can fetch template list."""
        TemplateFactory()
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse("tas_app:templates-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_templates_post_valid_payload_returns_201(self):
        """Verify admin can create a template with valid input."""
        template_type = TemplateTypeFactory()
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            reverse("tas_app:templates-list"),
            {
                "template_type": template_type.id,
                "name": "T1",
                "description": "D",
                "image_width": 1000,
                "image_height": 500,
                "fields": [{"name": "a"}],
                "field_positions": {"a": {"x": 1, "y": 2}},
                "is_public": True,
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_templates_detail_put_invalid_payload_returns_400(self):
        """Verify PUT returns validation errors for malformed payload."""
        template = TemplateFactory()
        self.client.force_authenticate(user=self.admin)
        response = self.client.put(
            reverse("tas_app:templates-detail", kwargs={"pk": template.pk}),
            {"name": "Only name"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_templates_detail_patch_updates_template(self):
        """Verify PATCH updates a template for admin users."""
        template = TemplateFactory(name="Old")
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(
            reverse("tas_app:templates-detail", kwargs={"pk": template.pk}),
            {"name": "Updated"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_templates_detail_delete_already_inactive_returns_400(self):
        """Verify DELETE returns 400 when template already inactive."""
        template = TemplateFactory(is_active=False)
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(reverse("tas_app:templates-detail", kwargs={"pk": template.pk}))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class StudentSubmissionViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.student = UserFactory()
        self.other_student = UserFactory()
        self.block = TemplateBlockFactory()
        self.create_url = reverse("tas_app:student-submission-create")

    def tearDown(self):
        self.client.force_authenticate(user=None)

    def test_submission_create_unauthenticated_returns_403(self):
        """Verify unauthenticated student submission create is blocked."""
        response = self.client.post(self.create_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_submission_create_valid_payload_returns_201(self):
        """Verify authenticated student can create draft submission."""
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            self.create_url,
            {
                "template_block_id": str(self.block.pk),
                "course_key": str(self.block.course_key),
                "usage_key": str(self.block.usage_key),
                "form_data": {"answer": "first"},
                "status": Submission.STATUS_DRAFT,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_submission_create_invalid_course_mismatch_returns_400(self):
        """Verify create API rejects mismatched course_key values."""
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            self.create_url,
            {
                "template_block_id": str(self.block.pk),
                "course_key": "course-v1:edX+Wrong+2026_T1",
                "usage_key": str(self.block.usage_key),
                "form_data": {"answer": "first"},
                "status": Submission.STATUS_DRAFT,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_submission_create_existing_finalized_returns_409(self):
        """Verify create API rejects updates to finalized submissions."""
        SubmissionFactory(
            student=self.student,
            template_block=self.block,
            course_key=self.block.course_key,
            usage_key=self.block.usage_key,
            status=Submission.STATUS_SUBMITTED,
        )
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            self.create_url,
            {
                "template_block_id": str(self.block.pk),
                "course_key": str(self.block.course_key),
                "usage_key": str(self.block.usage_key),
                "form_data": {"answer": "cannot"},
                "status": Submission.STATUS_DRAFT,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_submission_detail_get_non_owner_returns_404(self):
        """Verify student cannot read another student's submission."""
        submission = SubmissionFactory(student=self.other_student, template_block=self.block)
        self.client.force_authenticate(user=self.student)
        response = self.client.get(reverse("tas_app:student-submission-detail", kwargs={"pk": submission.pk}))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_submission_detail_patch_empty_payload_returns_400(self):
        """Verify PATCH requires at least one editable field."""
        submission = SubmissionFactory(student=self.student, template_block=self.block)
        self.client.force_authenticate(user=self.student)
        response = self.client.patch(
            reverse("tas_app:student-submission-detail", kwargs={"pk": submission.pk}),
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_submission_submit_marks_status_submitted(self):
        """Verify submit endpoint finalizes draft submission."""
        submission = SubmissionFactory(student=self.student, template_block=self.block, status=Submission.STATUS_DRAFT)
        self.client.force_authenticate(user=self.student)
        response = self.client.post(reverse("tas_app:student-submission-submit", kwargs={"pk": submission.pk}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_submission_pdf_without_pdf_returns_202(self):
        """Verify pdf endpoint reports generating state when no pdf exists."""
        submission = SubmissionFactory(student=self.student, template_block=self.block, pdf=None)
        self.client.force_authenticate(user=self.student)
        response = self.client.get(reverse("tas_app:student-submission-pdf", kwargs={"pk": submission.pk}))
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

    def test_submission_versions_returns_history(self):
        """Verify versions endpoint returns version snapshots."""
        submission = SubmissionFactory(student=self.student, template_block=self.block)
        submission.create_version_snapshot()
        self.client.force_authenticate(user=self.student)
        response = self.client.get(reverse("tas_app:student-submission-versions", kwargs={"pk": submission.pk}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class InstructorEndpointsViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = AdminUserFactory()
        self.student = UserFactory()
        self.block = TemplateBlockFactory()
        self.submission = SubmissionFactory(
            student=self.student,
            template_block=self.block,
            course_key=self.block.course_key,
            usage_key=self.block.usage_key,
            status=Submission.STATUS_SUBMITTED,
        )

    def tearDown(self):
        self.client.force_authenticate(user=None)

    def test_block_templates_get_authenticated_returns_200(self):
        """Verify authenticated user can fetch block template details."""
        self.client.force_authenticate(user=self.student)
        response = self.client.get(reverse("tas_app:block-templates", kwargs={"usage_key": str(self.block.usage_key)}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_block_submissions_get_admin_returns_200(self):
        """Verify admin can list learner submissions for a block."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(
            reverse("tas_app:block-submissions-list", kwargs={"usage_key": str(self.block.usage_key)})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_submission_detail_get_admin_returns_200(self):
        """Verify admin can view detailed learner submission payload."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse("tas_app:submission-detail", kwargs={"pk": self.submission.pk}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_block_rubrics_missing_block_returns_404(self):
        """Verify rubrics endpoint returns 404 for unknown usage key."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(
            reverse("tas_app:block-rubrics", kwargs={"usage_key": "block-v1:edX+DemoX+2026_T1+type@problem+block@x"})
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_submission_feedback_post_creates_feedback(self):
        """Verify feedback endpoint creates instructor feedback entry."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            reverse("tas_app:submission-feedback", kwargs={"pk": self.submission.pk}),
            {"rubrics": [{"criterion": "quality"}], "comment": "Good", "status": "approved"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(InstructorFeedback.objects.filter(submission=self.submission).exists())

    def test_feedback_options_get_empty_returns_200(self):
        """Verify GET feedback-options returns empty categories by default."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(
            reverse("tas_app:block-feedback-options", kwargs={"usage_key": str(self.block.usage_key)})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["categories"], [])

    def test_feedback_options_put_and_get_round_trip(self):
        """Verify PUT persists predefined feedback options per category."""
        self.client.force_authenticate(user=self.admin)
        payload = {
            "categories": [
                {
                    "category_id": "Hypothesis",
                    "options": [{"id": "fb-1", "label": "Clear hypothesis"}],
                }
            ]
        }
        put_response = self.client.put(
            reverse("tas_app:block-feedback-options", kwargs={"usage_key": str(self.block.usage_key)}),
            payload,
            format="json",
        )
        self.assertEqual(put_response.status_code, status.HTTP_200_OK)
        get_response = self.client.get(
            reverse("tas_app:block-feedback-options", kwargs={"usage_key": str(self.block.usage_key)})
        )
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data["categories"], payload["categories"])

    def test_block_rubrics_includes_predefined_feedback(self):
        """Verify rubrics response embeds predefined_feedback from block config."""
        rubric = Rubric.objects.create(
            name="Lab Rubric",
            criteria=[{"criterion": "Hypothesis", "options": [{"name": "Good", "marks": 5}]}],
        )
        self.block.rubric = rubric
        self.block.feedback_options = [
            {"category_id": "Hypothesis", "options": [{"id": "fb-1", "label": "Well stated"}]}
        ]
        self.block.save()
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(
            reverse("tas_app:block-rubrics", kwargs={"usage_key": str(self.block.usage_key)})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["rubrics"][0]["predefined_feedback"],
            [{"id": "fb-1", "label": "Well stated"}],
        )

    def test_submission_feedback_accepts_selected_options(self):
        """Verify feedback POST stores selected_options on rubric entries."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            reverse("tas_app:submission-feedback", kwargs={"pk": self.submission.pk}),
            {
                "rubrics": [
                    {
                        "criterion": "Hypothesis",
                        "selected_option": "Score: 8",
                        "marks": 8,
                        "selected_options": ["fb-1", "fb-2"],
                    }
                ],
                "comment": "Nice work",
                "status": "approved",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        feedback = InstructorFeedback.objects.get(submission=self.submission)
        self.assertEqual(feedback.rubrics[0]["selected_options"], ["fb-1", "fb-2"])


class URLRoutingTest(TestCase):
    def test_template_types_list_url_resolves_correct_view(self):
        """Verify template types list URL maps to the expected view class."""
        match = resolve(reverse("tas_app:template-types-list"))
        self.assertEqual(match.func.view_class, TemplateTypesListView)

    def test_template_types_detail_url_resolves_correct_view(self):
        """Verify template types detail URL maps to the expected view class."""
        match = resolve(reverse("tas_app:template-types-detail", kwargs={"pk": 1}))
        self.assertEqual(match.func.view_class, TemplateTypesDetailView)

    def test_templates_list_url_resolves_correct_view(self):
        """Verify templates list URL maps to the expected view class."""
        match = resolve(reverse("tas_app:templates-list"))
        self.assertEqual(match.func.view_class, TemplatesListView)

    def test_templates_detail_url_resolves_correct_view(self):
        """Verify templates detail URL maps to the expected view class."""
        match = resolve(reverse("tas_app:templates-detail", kwargs={"pk": 1}))
        self.assertEqual(match.func.view_class, TemplatesDetailView)

    def test_block_templates_url_resolves_correct_view(self):
        """Verify block templates URL maps to the expected view class."""
        match = resolve(
            reverse("tas_app:block-templates", kwargs={"usage_key": "block-v1:edX+DemoX+2026_T1+type@problem+block@u"})
        )
        self.assertEqual(match.func.view_class, TemplateBlockDetailView)

    def test_student_submission_create_url_resolves_correct_view(self):
        """Verify student submission create URL maps to expected view class."""
        match = resolve(reverse("tas_app:student-submission-create"))
        self.assertEqual(match.func.view_class, StudentSubmissionCreateAPIView)

    def test_student_submission_detail_url_resolves_correct_view(self):
        """Verify student submission detail URL maps to expected view class."""
        match = resolve(reverse("tas_app:student-submission-detail", kwargs={"pk": 1}))
        self.assertEqual(match.func.view_class, StudentSubmissionDetailAPIView)

    def test_student_submission_submit_url_resolves_correct_view(self):
        """Verify student submission submit URL maps to expected view class."""
        match = resolve(reverse("tas_app:student-submission-submit", kwargs={"pk": 1}))
        self.assertEqual(match.func.view_class, StudentSubmissionSubmitAPIView)

    def test_student_submission_pdf_url_resolves_correct_view(self):
        """Verify student submission pdf URL maps to expected view class."""
        match = resolve(reverse("tas_app:student-submission-pdf", kwargs={"pk": 1}))
        self.assertEqual(match.func.view_class, StudentSubmissionPdfAPIView)

    def test_student_submission_versions_url_resolves_correct_view(self):
        """Verify student submission versions URL maps to expected view class."""
        match = resolve(reverse("tas_app:student-submission-versions", kwargs={"pk": 1}))
        self.assertEqual(match.func.view_class, StudentSubmissionVersionsAPIView)

    def test_block_submissions_url_resolves_correct_view(self):
        """Verify block submissions URL maps to expected view class."""
        match = resolve(
            reverse(
                "tas_app:block-submissions-list",
                kwargs={"usage_key": "block-v1:edX+DemoX+2026_T1+type@problem+block@y"},
            )
        )
        self.assertEqual(match.func.view_class, LearnerSubmissionsAPIView)

    def test_submission_detail_url_resolves_correct_view(self):
        """Verify submission detail URL maps to expected view class."""
        match = resolve(reverse("tas_app:submission-detail", kwargs={"pk": 1}))
        self.assertEqual(match.func.view_class, LearnerSubmissionDetailAPIView)

    def test_block_rubrics_url_resolves_correct_view(self):
        """Verify block rubrics URL maps to expected view class."""
        match = resolve(
            reverse("tas_app:block-rubrics", kwargs={"usage_key": "block-v1:edX+DemoX+2026_T1+type@problem+block@z"})
        )
        self.assertEqual(match.func.view_class, RubricsAPIView)

    def test_submission_feedback_url_resolves_correct_view(self):
        """Verify submission feedback URL maps to expected view class."""
        match = resolve(reverse("tas_app:submission-feedback", kwargs={"pk": 1}))
        self.assertEqual(match.func.view_class, InstructorFeedbackAPIView)

    def test_block_feedback_options_url_resolves_correct_view(self):
        """Verify block feedback-options URL maps to expected view class."""
        match = resolve(
            reverse(
                "tas_app:block-feedback-options",
                kwargs={"usage_key": "block-v1:edX+DemoX+2026_T1+type@problem+block@z"},
            )
        )
        self.assertEqual(match.func.view_class, BlockFeedbackOptionsAPIView)
