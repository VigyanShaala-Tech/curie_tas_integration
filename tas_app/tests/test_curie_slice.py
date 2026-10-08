"""Thin-slice trigger payload and callback view tests."""

from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from tas_app.curie.callback import apply_callback
from tas_app.curie.trigger import build_trigger_form_data, build_trigger_payload, maybe_start_curie_review
from tas_app.models import CurieReview, InstructorFeedback, Submission
from tas_app.tests.test_models import SubmissionFactory, TemplateBlockFactory, TemplateFactory, TemplateTypeFactory
from tas_app.views import CurieReviewCallbackAPIView, StudentSubmissionSubmitAPIView


SWOT_FIELDS = [
    {"id": "goal", "label": "Goal Definition - Short-Term STEM Goal", "active": True},
    {"id": "strength", "label": "Strengths (Internal)", "active": True},
    {"id": "contribution", "label": "Contribution to Something Larger (reflection)", "active": True},
]


def _scores(values):
    names = ("Task Relevance", "Reasoning / Understanding", "Specificity & Evidence")
    return [{"criterion": name, "score": value, "max_score": 10} for name, value in zip(names, values)]


def _success_payload(review):
    if not review.trigger_payload:
        review.trigger_payload = build_trigger_payload(review, review.submission)
        review.save(update_fields=["trigger_payload", "modified"])
    return {
        "trigger_id": str(review.trigger_id),
        "user_id": str(review.submission.student_id),
        "submission_id": str(review.submission_id),
        "submission_version_number": review.submission_version_number,
        "result": "success",
        "gate_criterion_scores": _scores((9, 8, 9)),
        "field_feedback": [
            {
                "field_id": "goal",
                "weight": 1,
                "comment": "Goal is specific.",
                "criterion_scores": _scores((9, 8, 9)),
            },
            {
                "field_id": "strength",
                "weight": 1,
                "comment": "Strength is evidenced.",
                "criterion_scores": _scores((9, 8, 9)),
            },
            {
                "field_id": "contribution",
                "weight": 0,
                "comment": "Keep this reflection.",
                "criterion_scores": _scores((9, 8, 9)),
            },
        ],
        "overall_feedback": "Strong submission overall. Your answers form a coherent SWOT.",
    }


SLICE_SETTINGS = dict(
    CURIE_ENABLED=True,
    CURIE_TRIGGER_URL="http://curie-stub.example/api/v1/assessment-reviews/",
    CURIE_CALLBACK_BASE_URL="http://lms.example",
    CURIE_AUTH_HEADER_NAME="X-Curie-Shared-Secret",
    CURIE_SHARED_SECRET="test-shared-secret",
    CURIE_CONNECT_TIMEOUT_SECONDS=3,
    CURIE_REQUEST_TIMEOUT_SECONDS=10,
    CURIE_REVIEW_TIMEOUT_SECONDS=300,
    CURIE_REVIEW_MAX_WAIT_SECONDS=1800,
    CURIE_COMPONENT_PASS_THRESHOLD=6.0,
)


def _swot_submission(**kwargs):
    template_type = TemplateTypeFactory(slug="swot", name="SWOT")
    template = TemplateFactory(template_type=template_type, fields=SWOT_FIELDS)
    block = TemplateBlockFactory(template=template, curie_enabled=True)
    defaults = dict(
        template_block=block,
        form_data={
            "goal": "Complete the NPTEL Python course by March 2027.",
            "strength": "I led my robotics team through a wiring failure.",
            "contribution": "I will share course notes with my peers.",
        },
        status=Submission.STATUS_DRAFT,
        version_number=1,
    )
    defaults.update(kwargs)
    return SubmissionFactory(**defaults)


@override_settings(**SLICE_SETTINGS)
class CurieTriggerPayloadTest(TestCase):
    def test_form_data_uses_label_and_answer_objects(self):
        submission = _swot_submission()
        payload = build_trigger_form_data(submission)
        self.assertEqual(
            payload["goal"],
            {
                "label": "Goal Definition - Short-Term STEM Goal",
                "answer": "Complete the NPTEL Python course by March 2027.",
            },
        )
        self.assertEqual(payload["contribution"]["answer"], "I will share course notes with my peers.")

    def test_trigger_payload_has_contract_fields_only(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        payload = build_trigger_payload(review, submission)
        self.assertEqual(
            set(payload),
            {
                "trigger_id",
                "user_id",
                "origin",
                "user_query",
                "assignment_type",
                "assignment_id",
                "submission_id",
                "submission_version_number",
                "course_id",
                "usage_key",
                "form_data",
                "callback_url",
            },
        )
        self.assertIsNone(payload["user_query"])
        self.assertEqual(payload["origin"], "tas")
        self.assertEqual(payload["assignment_type"], "swot")
        self.assertEqual(payload["submission_version_number"], 2)
        self.assertEqual(
            payload["callback_url"],
            f"http://lms.example/tas/api/v1/curie/reviews/{review.trigger_id}/callback/",
        )

    @patch("tas_app.curie.celery_tasks.deliver_curie_trigger.delay")
    def test_eligible_submit_creates_pending_review_and_enqueues_trigger(self, mocked_delay):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        with self.captureOnCommitCallbacks(execute=True):
            review = maybe_start_curie_review(submission)
        self.assertIsNotNone(review)
        self.assertEqual(review.status, CurieReview.STATUS_PENDING_EVALUATION)
        mocked_delay.assert_called_once()
        self.assertEqual(mocked_delay.call_args.args[0], str(review.trigger_id))

    def test_disabled_block_does_not_create_review(self):
        submission = _swot_submission()
        submission.template_block.curie_enabled = False
        submission.template_block.save()
        self.assertIsNone(maybe_start_curie_review(submission))
        self.assertEqual(CurieReview.objects.count(), 0)


@override_settings(**SLICE_SETTINGS)
class CurieCallbackViewTest(TestCase):
    def _post(self, trigger_id, body, secret="test-shared-secret"):
        factory = APIRequestFactory()
        headers = {}
        if secret is not None:
            headers["HTTP_X_CURIE_SHARED_SECRET"] = secret
        request = factory.post(
            f"/tas/api/v1/curie/reviews/{trigger_id}/callback/",
            body,
            format="json",
            **headers,
        )
        return CurieReviewCallbackAPIView.as_view()(request, trigger_id=trigger_id)

    def test_rejects_missing_secret(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        response = self._post(review.trigger_id, _success_payload(review), secret=None)
        self.assertEqual(response.status_code, 401)

    def test_success_callback_projects_instructor_feedback(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        response = self._post(review.trigger_id, _success_payload(review))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "applied")
        review.refresh_from_db()
        submission.refresh_from_db()
        self.assertEqual(review.status, CurieReview.STATUS_READY)
        self.assertEqual(review.verdict, CurieReview.VERDICT_ACCEPTED)
        feedback = submission.feedback
        self.assertEqual(feedback.source, InstructorFeedback.SOURCE_CURIE)
        self.assertEqual(feedback.status, "approved")
        self.assertEqual(submission.status, Submission.STATUS_APPROVED)
        self.assertIn("Strong submission overall", feedback.comment)

    def test_gate_failure_projects_feedback_as_rejected(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        payload = _success_payload(review)
        payload["gate_criterion_scores"] = _scores((5, 5, 4))

        response = self._post(review.trigger_id, payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "applied")
        review.refresh_from_db()
        submission.refresh_from_db()
        self.assertEqual(review.status, CurieReview.STATUS_READY)
        self.assertEqual(review.verdict, CurieReview.VERDICT_REJECTED)
        self.assertEqual(len(review.field_feedback), len(SWOT_FIELDS))
        self.assertEqual(submission.status, Submission.STATUS_REJECTED)
        self.assertEqual(submission.feedback.source, InstructorFeedback.SOURCE_CURIE)
        self.assertEqual(submission.feedback.status, "rejected")

    def test_duplicate_success_callback_is_replayed(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        payload = _success_payload(review)
        self.assertEqual(apply_callback(review, payload), "applied")
        review.refresh_from_db()
        self.assertEqual(apply_callback(review, payload), "replayed")


@override_settings(**SLICE_SETTINGS)
class CurieSubmitHookTest(TestCase):
    @patch("tas_app.curie.celery_tasks.deliver_curie_trigger.delay")
    def test_submit_endpoint_starts_curie_review(self, mocked_delay):
        submission = _swot_submission(status=Submission.STATUS_DRAFT, version_number=1)
        factory = APIRequestFactory()
        request = factory.post(
            f"/tas/api/v1/student-submission/{submission.pk}/submit/",
            {"form_data": submission.form_data},
            format="json",
        )
        force_authenticate(request, user=submission.student)
        with patch("tas_app.curie.submit.generate_submission_pdf"):
            with self.captureOnCommitCallbacks(execute=True):
                response = StudentSubmissionSubmitAPIView.as_view()(request, pk=submission.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CurieReview.objects.filter(submission=submission).count(), 1)
        mocked_delay.assert_called_once()
