"""Phase 4: CURIE read APIs, timeout-on-read, and legacy write guards."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from tas_app.curie.api import AdminCurieReviewAPIView, StudentCurieReviewAPIView
from tas_app.curie.callback import apply_callback
from tas_app.curie.constants import LEARNER_FAILURE_DETAIL, SOURCE_CURIE, SOURCE_HUMAN, TIMEOUT_ERROR_DETAIL
from tas_app.curie.scoring import star_rating
from tas_app.models import (
    CurieReview,
    InstructorFeedback,
    InstructorFeedbackVersion,
    STATUS_APPROVED,
    STATUS_REJECTED,
    Submission,
    SubmissionVersion,
    TemplateType,
)
from tas_app.tests.test_curie_phase3 import _post_human_feedback, _success_payload
from tas_app.tests.test_curie_slice import SLICE_SETTINGS, SWOT_FIELDS, _scores
from tas_app.tests.test_models import (
    InstructorFeedbackFactory,
    SubmissionFactory,
    TemplateBlockFactory,
    TemplateFactory,
    TemplateTypeFactory,
    UserFactory,
)
from tas_app.views import (
    InstructorFeedbackAPIView,
    LearnerSubmissionDetailAPIView,
    LearnerSubmissionsAPIView,
    StudentSubmissionCreateAPIView,
    StudentSubmissionDetailAPIView,
    StudentSubmissionVersionsAPIView,
    WithdrawFeedbackAPIView,
)


def _swot_submission(**kwargs):
    template_type = TemplateType.objects.filter(slug="swot").first()
    if template_type is None:
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


def _ready_review(submission, version_number=None, field_values=(9, 8, 9)):
    version_number = submission.version_number if version_number is None else version_number
    fields = [
        {
            "field_id": "goal",
            "weight": 1,
            "comment": "Goal is specific.",
            "criterion_scores": _scores(field_values),
        },
        {
            "field_id": "contribution",
            "weight": 0,
            "comment": "Keep this reflection.",
            "criterion_scores": _scores(field_values),
        },
    ]
    return CurieReview.objects.create(
        submission=submission,
        submission_version_number=version_number,
        status=CurieReview.STATUS_READY,
        verdict=CurieReview.VERDICT_ACCEPTED,
        gate_criterion_scores=_scores(field_values),
        field_feedback=fields,
        overall_feedback="Strong submission overall.",
        completed_at=timezone.now(),
    )


def _pdf_version(submission, version_number):
    version = SubmissionVersion.objects.create(
        submission=submission,
        version_number=version_number,
        form_data=submission.form_data,
    )
    version.pdf.save(f"v{version_number}.pdf", ContentFile(b"%PDF-test"), save=True)
    return version


def _auth(view, user, method, path, pk=None, data=None, query=""):
    factory = APIRequestFactory()
    handler = getattr(factory, method)
    kwargs = {}
    if data is not None:
        kwargs["data"] = data
        kwargs["format"] = "json"
    request = handler(f"{path}{query}", **kwargs)
    force_authenticate(request, user=user)
    if pk is None:
        return view(request)
    return view(request, pk=pk)


def _age_pending(review, seconds=1800):
    CurieReview.objects.filter(pk=review.pk).update(
        requested_at=timezone.now() - timedelta(seconds=seconds)
    )


def _assert_timed_out_without_projection(test, submission, review):
    review.refresh_from_db()
    submission.refresh_from_db()
    test.assertEqual(review.status, CurieReview.STATUS_FAILED)
    test.assertEqual(review.error_detail, TIMEOUT_ERROR_DETAIL)
    test.assertEqual(submission.status, Submission.STATUS_SUBMITTED)
    test.assertFalse(InstructorFeedback.objects.filter(submission=submission).exists())


@override_settings(**SLICE_SETTINGS)
class CurieLearnerReadApiTest(TestCase):
    def test_owner_gets_current_review_without_raw_scores(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = _ready_review(submission)
        response = _auth(
            StudentCurieReviewAPIView.as_view(),
            submission.student,
            "get",
            f"/tas/api/v1/student-submission/{submission.pk}/curie-review/",
            pk=submission.pk,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], CurieReview.STATUS_READY)
        self.assertEqual(response.data["verdict"], CurieReview.VERDICT_ACCEPTED)
        self.assertEqual(response.data["star_rating"], star_rating(review.field_feedback))
        self.assertNotIn("criterion_scores", response.data["field_feedback"][0])
        self.assertEqual(response.data["field_feedback"][0]["color"], "good")
        self.assertIsNone(response.data["field_feedback"][1]["color"])
        self.assertNotIn("trigger_id", response.data)

    def test_student_detail_does_not_leak_curie_scores(self):
        submission = _swot_submission(status=Submission.STATUS_APPROVED, version_number=2)
        review = _ready_review(submission)
        InstructorFeedbackFactory(
            submission=submission,
            source=SOURCE_CURIE,
            status=STATUS_APPROVED,
            rubrics=[{"criterion": "Task Relevance", "marks": 8.66}],
            comment=review.overall_feedback,
        )
        response = _auth(
            StudentSubmissionDetailAPIView.as_view(),
            submission.student,
            "get",
            f"/tas/api/v1/student-submission/{submission.pk}/",
            pk=submission.pk,
        )
        self.assertEqual(response.status_code, 200)
        feedback = response.data["feedback"]
        self.assertEqual(feedback["source"], SOURCE_CURIE)
        self.assertEqual(feedback["rubrics"], [])
        self.assertEqual(feedback["verdict"], CurieReview.VERDICT_ACCEPTED)
        self.assertNotIn("criterion_scores", feedback["field_feedback"][0])
        self.assertNotIn("marks", str(feedback))
        self.assertEqual(feedback["field_feedback"][0]["color"], "good")

    def test_version_query_returns_historical_review(self):
        submission = _swot_submission(status=Submission.STATUS_REJECTED, version_number=4)
        old = _ready_review(submission, version_number=2, field_values=(5, 5, 5))
        _ready_review(submission, version_number=4)
        response = _auth(
            StudentCurieReviewAPIView.as_view(),
            submission.student,
            "get",
            f"/tas/api/v1/student-submission/{submission.pk}/curie-review/",
            pk=submission.pk,
            query="?version=2",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["submission_version_number"], 2)
        self.assertEqual(response.data["verdict"], old.verdict)
        self.assertEqual(response.data["field_feedback"][0]["color"], "needs_revision")

    def test_other_student_cannot_read_review(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        _ready_review(submission)
        other = UserFactory()
        response = _auth(
            StudentCurieReviewAPIView.as_view(),
            other,
            "get",
            f"/tas/api/v1/student-submission/{submission.pk}/curie-review/",
            pk=submission.pk,
        )
        self.assertEqual(response.status_code, 404)

    def test_timeout_on_read_marks_pending_failed_without_projection(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        CurieReview.objects.filter(pk=review.pk).update(requested_at=timezone.now() - timedelta(seconds=1800))
        response = _auth(
            StudentCurieReviewAPIView.as_view(),
            submission.student,
            "get",
            f"/tas/api/v1/student-submission/{submission.pk}/curie-review/",
            pk=submission.pk,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], CurieReview.STATUS_FAILED)
        self.assertEqual(response.data["error_detail"], LEARNER_FAILURE_DETAIL)
        self.assertNotIn(TIMEOUT_ERROR_DETAIL, str(response.data))
        review.refresh_from_db()
        submission.refresh_from_db()
        self.assertEqual(review.status, CurieReview.STATUS_FAILED)
        self.assertEqual(submission.status, Submission.STATUS_SUBMITTED)
        self.assertFalse(InstructorFeedback.objects.filter(submission=submission).exists())

    def test_student_detail_exposes_status_attempt_count_and_slow_flag(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        CurieReview.objects.filter(pk=review.pk).update(requested_at=timezone.now() - timedelta(seconds=300))
        response = _auth(
            StudentSubmissionDetailAPIView.as_view(),
            submission.student,
            "get",
            f"/tas/api/v1/student-submission/{submission.pk}/",
            pk=submission.pk,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["curie_review_status"], CurieReview.STATUS_PENDING_EVALUATION)
        self.assertTrue(response.data["is_slow_pending"])
        self.assertEqual(response.data["submission_attempt_count"], 1)
        self.assertFalse(response.data["at_max_attempts"])


@override_settings(**SLICE_SETTINGS)
class CurieTimeoutReadApiTest(TestCase):
    def setUp(self):
        self.staff = UserFactory(is_staff=True, is_superuser=True)

    def test_student_detail_persists_timeout(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        _age_pending(review)
        response = _auth(
            StudentSubmissionDetailAPIView.as_view(),
            submission.student,
            "get",
            f"/tas/api/v1/student-submission/{submission.pk}/",
            pk=submission.pk,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["curie_review_status"], CurieReview.STATUS_FAILED)
        self.assertFalse(response.data["is_slow_pending"])
        _assert_timed_out_without_projection(self, submission, review)

    def test_versions_persist_timeout(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        version = _pdf_version(submission, 2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        _age_pending(review)
        response = _auth(
            StudentSubmissionVersionsAPIView.as_view(),
            submission.student,
            "get",
            f"/tas/api/v1/student-submission/{submission.pk}/versions/",
            pk=submission.pk,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["versions"][0]["curie_review_status"], CurieReview.STATUS_FAILED)
        self.assertEqual(version.version_number, 2)
        _assert_timed_out_without_projection(self, submission, review)

    def test_instructor_detail_persists_timeout(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        _age_pending(review)
        response = _auth(
            LearnerSubmissionDetailAPIView.as_view(),
            self.staff,
            "get",
            f"/tas/api/v1/submissions/{submission.pk}/",
            pk=submission.pk,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["curie_review"]["status"], CurieReview.STATUS_FAILED)
        self.assertEqual(response.data["curie_review"]["error_detail"], TIMEOUT_ERROR_DETAIL)
        self.assertFalse(response.data["curie_review"]["instructor_form_locked"])
        _assert_timed_out_without_projection(self, submission, review)

    def test_admin_review_persists_timeout(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        _age_pending(review)
        response = _auth(
            AdminCurieReviewAPIView.as_view(),
            self.staff,
            "get",
            f"/tas/api/v1/submissions/{submission.pk}/curie-review/",
            pk=submission.pk,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], CurieReview.STATUS_FAILED)
        self.assertEqual(response.data["error_detail"], TIMEOUT_ERROR_DETAIL)
        _assert_timed_out_without_projection(self, submission, review)

    def test_timeout_read_is_idempotent(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        _age_pending(review)
        first = _auth(
            StudentCurieReviewAPIView.as_view(),
            submission.student,
            "get",
            f"/tas/api/v1/student-submission/{submission.pk}/curie-review/",
            pk=submission.pk,
        )
        second = _auth(
            StudentCurieReviewAPIView.as_view(),
            submission.student,
            "get",
            f"/tas/api/v1/student-submission/{submission.pk}/curie-review/",
            pk=submission.pk,
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["status"], CurieReview.STATUS_FAILED)
        self.assertEqual(second.data["status"], CurieReview.STATUS_FAILED)
        self.assertEqual(second.data["error_detail"], LEARNER_FAILURE_DETAIL)
        _assert_timed_out_without_projection(self, submission, review)


@override_settings(**SLICE_SETTINGS)
class CurieHistoryReadApiTest(TestCase):
    def test_versions_include_batched_review_summaries_and_attempt_numbers(self):
        submission = _swot_submission(status=Submission.STATUS_REJECTED, version_number=4)
        _pdf_version(submission, 2)
        _pdf_version(submission, 4)
        first = _ready_review(submission, version_number=2, field_values=(9, 8, 9))
        CurieReview.objects.create(
            submission=submission,
            submission_version_number=4,
            status=CurieReview.STATUS_FAILED,
            error_detail="trigger exhausted",
        )
        response = _auth(
            StudentSubmissionVersionsAPIView.as_view(),
            submission.student,
            "get",
            f"/tas/api/v1/student-submission/{submission.pk}/versions/",
            pk=submission.pk,
        )
        self.assertEqual(response.status_code, 200)
        versions = response.data["versions"]
        self.assertEqual(len(versions), 2)
        newest, oldest = versions
        self.assertEqual(newest["version_number"], 4)
        self.assertEqual(newest["attempt_number"], 2)
        self.assertEqual(newest["curie_review_status"], CurieReview.STATUS_FAILED)
        self.assertIsNone(newest["star_rating"])
        self.assertEqual(oldest["attempt_number"], 1)
        self.assertEqual(oldest["curie_review_status"], CurieReview.STATUS_READY)
        self.assertEqual(oldest["verdict"], first.verdict)
        self.assertEqual(oldest["star_rating"], star_rating(first.field_feedback))

    def test_versions_feedback_source_prefers_human_override_over_ready_curie(self):
        submission = _swot_submission(status=Submission.STATUS_APPROVED, version_number=2)
        version = _pdf_version(submission, 2)
        _ready_review(submission, version_number=2, field_values=(9, 8, 9))
        instructor = UserFactory()
        feedback = InstructorFeedbackFactory(
            submission=submission,
            source=SOURCE_HUMAN,
            status=STATUS_APPROVED,
            instructor=instructor,
            comment="Instructor override.",
            rubrics=[],
        )
        InstructorFeedbackVersion.objects.create(
            instructor_feedback=feedback,
            submission_version=version,
            version_number=1,
            instructor=None,
            comment="CURIE copy.",
            status=STATUS_APPROVED,
            rubrics=[],
        )
        InstructorFeedbackVersion.objects.create(
            instructor_feedback=feedback,
            submission_version=version,
            version_number=2,
            instructor=instructor,
            comment="Instructor override.",
            status=STATUS_APPROVED,
            rubrics=[],
        )
        response = _auth(
            StudentSubmissionVersionsAPIView.as_view(),
            submission.student,
            "get",
            f"/tas/api/v1/student-submission/{submission.pk}/versions/",
            pk=submission.pk,
        )
        self.assertEqual(response.status_code, 200)
        row = response.data["versions"][0]
        self.assertEqual(row["curie_review_status"], CurieReview.STATUS_READY)
        self.assertEqual(row["feedback_source"], SOURCE_HUMAN)
        self.assertEqual(row["instructor_comment"], "Instructor override.")

    def test_history_lookup_does_not_fan_out_one_query_per_attempt(self):
        def _count_for(attempt_count):
            submission = _swot_submission(
                status=Submission.STATUS_SUBMITTED,
                version_number=attempt_count * 2,
            )
            feedback = InstructorFeedbackFactory(
                submission=submission,
                source=SOURCE_CURIE,
                status=STATUS_APPROVED,
                rubrics=[],
            )
            for index in range(1, attempt_count + 1):
                version_number = index * 2
                version = _pdf_version(submission, version_number)
                _ready_review(submission, version_number=version_number)
                InstructorFeedbackVersion.objects.create(
                    instructor_feedback=feedback,
                    submission_version=version,
                    version_number=index,
                    comment="ok",
                    status=STATUS_APPROVED,
                    rubrics=[],
                )
            view = StudentSubmissionVersionsAPIView.as_view()
            request = APIRequestFactory().get(
                f"/tas/api/v1/student-submission/{submission.pk}/versions/"
            )
            force_authenticate(request, user=submission.student)
            with CaptureQueriesContext(connection) as captured:
                response = view(request, pk=submission.pk)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.data["versions"]), attempt_count)
            return [
                query["sql"]
                for query in captured.captured_queries
                if query["sql"].lstrip().startswith("SELECT")
            ]

        small = _count_for(3)
        large = _count_for(6)
        self.assertEqual(len(small), len(large), (small, large))
        self.assertLessEqual(len(large), 8, large)


@override_settings(**SLICE_SETTINGS)
class CurieInstructorAdminReadApiTest(TestCase):
    def setUp(self):
        self.staff = UserFactory(is_staff=True, is_superuser=True)

    def test_instructor_detail_includes_source_locked_flag_and_raw_scores(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        pending = CurieReview.objects.create(submission=submission, submission_version_number=2)
        response = _auth(
            LearnerSubmissionDetailAPIView.as_view(),
            self.staff,
            "get",
            f"/tas/api/v1/submissions/{submission.pk}/",
            pk=submission.pk,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["feedback"])
        self.assertTrue(response.data["curie_review"]["instructor_form_locked"])
        self.assertEqual(response.data["curie_review"]["status"], CurieReview.STATUS_PENDING_EVALUATION)

        pending.status = CurieReview.STATUS_READY
        pending.verdict = CurieReview.VERDICT_ACCEPTED
        pending.gate_criterion_scores = _scores((9, 8, 9))
        pending.field_feedback = [
            {
                "field_id": "goal",
                "weight": 1,
                "comment": "Goal is specific.",
                "criterion_scores": _scores((9, 8, 9)),
            }
        ]
        pending.overall_feedback = "Strong submission overall."
        pending.completed_at = timezone.now()
        pending.save()
        InstructorFeedbackFactory(
            submission=submission,
            source=SOURCE_CURIE,
            status=STATUS_APPROVED,
            comment=pending.overall_feedback,
        )
        submission.status = Submission.STATUS_APPROVED
        submission.save(update_fields=["status"])
        response = _auth(
            LearnerSubmissionDetailAPIView.as_view(),
            self.staff,
            "get",
            f"/tas/api/v1/submissions/{submission.pk}/",
            pk=submission.pk,
        )
        self.assertEqual(response.data["feedback"]["source"], SOURCE_CURIE)
        self.assertFalse(response.data["curie_review"]["instructor_form_locked"])
        self.assertIn("criterion_scores", response.data["curie_review"]["field_feedback"][0])
        self.assertEqual(response.data["curie_review"]["trigger_id"], str(pending.trigger_id))
        self.assertIsNotNone(response.data["curie_review"]["gate_score"])

    def test_admin_diagnostics_endpoint_is_staff_only(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        _ready_review(submission)
        student_response = _auth(
            AdminCurieReviewAPIView.as_view(),
            submission.student,
            "get",
            f"/tas/api/v1/submissions/{submission.pk}/curie-review/",
            pk=submission.pk,
        )
        self.assertEqual(student_response.status_code, 403)

    def test_admin_diagnostics_returns_trigger_and_gate_scores(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = _ready_review(submission)
        staff_response = _auth(
            AdminCurieReviewAPIView.as_view(),
            self.staff,
            "get",
            f"/tas/api/v1/submissions/{submission.pk}/curie-review/",
            pk=submission.pk,
        )
        self.assertEqual(staff_response.status_code, 200)
        self.assertEqual(staff_response.data["trigger_id"], str(review.trigger_id))
        self.assertIn("gate_criterion_scores", staff_response.data)

    @patch("tas_app.views.bulk_cohort_form_metadata_by_user_ids", return_value={})
    def test_queue_exposes_source_and_pending_lock(self, _mocked_meta):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        CurieReview.objects.create(submission=submission, submission_version_number=2)
        request = APIRequestFactory().get(f"/tas/api/v1/block/{submission.usage_key}/submissions/")
        force_authenticate(request, user=self.staff)
        response = LearnerSubmissionsAPIView.as_view()(request, usage_key=str(submission.usage_key))
        self.assertEqual(response.status_code, 200)
        row = response.data["results"][0]
        self.assertEqual(row["curie_review_status"], CurieReview.STATUS_PENDING_EVALUATION)
        self.assertTrue(row["instructor_form_locked"])
        self.assertIsNone(row["feedback_source"])


@override_settings(**SLICE_SETTINGS)
class CurieLegacyWriteGuardTest(TestCase):
    def setUp(self):
        self.staff = UserFactory(is_staff=True, is_superuser=True)

    def test_create_with_submitted_is_rejected_when_curie_eligible(self):
        submission = _swot_submission()
        block = submission.template_block
        payload = {
            "template_block_id": block.pk,
            "course_key": str(block.course_key),
            "usage_key": str(block.usage_key),
            "form_data": {"goal": "x"},
            "status": Submission.STATUS_SUBMITTED,
        }
        response = _auth(
            StudentSubmissionCreateAPIView.as_view(),
            submission.student,
            "post",
            "/tas/api/v1/student-submission/",
            data=payload,
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("submit endpoint", response.data["detail"])

    def test_patch_approved_or_rejected_cannot_return_to_draft(self):
        approved = _swot_submission(status=Submission.STATUS_APPROVED, version_number=2)
        rejected = _swot_submission(status=Submission.STATUS_REJECTED, version_number=2)
        for submission in (approved, rejected):
            response = _auth(
                StudentSubmissionDetailAPIView.as_view(),
                submission.student,
                "patch",
                f"/tas/api/v1/student-submission/{submission.pk}/",
                pk=submission.pk,
                data={"form_data": {"goal": "edit"}},
            )
            self.assertEqual(response.status_code, 409)
            submission.refresh_from_db()
            self.assertNotEqual(submission.status, Submission.STATUS_DRAFT)

    def test_reopen_is_blocked_for_curie_owned_feedback(self):
        submission = _swot_submission(status=Submission.STATUS_REJECTED, version_number=2)
        _ready_review(submission)
        InstructorFeedbackFactory(submission=submission, source=SOURCE_CURIE, status=STATUS_REJECTED)
        response = _auth(
            StudentSubmissionDetailAPIView.as_view(),
            submission.student,
            "patch",
            f"/tas/api/v1/student-submission/{submission.pk}/",
            pk=submission.pk,
            data={"action": "reopen"},
        )
        self.assertEqual(response.status_code, 409)
        submission.refresh_from_db()
        self.assertEqual(submission.status, Submission.STATUS_REJECTED)

    def test_withdraw_of_curie_owned_feedback_is_forbidden(self):
        submission = _swot_submission(status=Submission.STATUS_APPROVED, version_number=2)
        InstructorFeedbackFactory(submission=submission, source=SOURCE_CURIE, status=STATUS_APPROVED)
        response = _auth(
            WithdrawFeedbackAPIView.as_view(),
            self.staff,
            "post",
            f"/tas/api/v1/submissions/{submission.pk}/feedback/withdraw/",
            pk=submission.pk,
        )
        self.assertEqual(response.status_code, 403)
        submission.refresh_from_db()
        self.assertEqual(submission.feedback.status, STATUS_APPROVED)
        self.assertEqual(submission.feedback.source, SOURCE_CURIE)

    def test_withdraw_of_human_feedback_still_works(self):
        submission = _swot_submission(status=Submission.STATUS_APPROVED, version_number=2)
        InstructorFeedbackFactory(submission=submission, source=SOURCE_HUMAN, status=STATUS_APPROVED)
        with patch("tas_app.views._clear_submission_grade"):
            response = _auth(
                WithdrawFeedbackAPIView.as_view(),
                self.staff,
                "post",
                f"/tas/api/v1/submissions/{submission.pk}/feedback/withdraw/",
                pk=submission.pk,
            )
        self.assertEqual(response.status_code, 200)
        submission.refresh_from_db()
        self.assertEqual(submission.feedback.source, SOURCE_HUMAN)
        self.assertEqual(submission.status, Submission.STATUS_SUBMITTED)

    def test_instructor_post_is_locked_while_pending_and_unlocked_after_timeout(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        body = {"rubrics": [], "comment": "manual", "status": STATUS_APPROVED}
        pending = _auth(
            InstructorFeedbackAPIView.as_view(),
            self.staff,
            "post",
            f"/tas/api/v1/submissions/{submission.pk}/feedback/",
            pk=submission.pk,
            data=body,
        )
        self.assertEqual(pending.status_code, 409)
        self.assertFalse(InstructorFeedback.objects.filter(submission=submission).exists())

        CurieReview.objects.filter(pk=review.pk).update(requested_at=timezone.now() - timedelta(seconds=1800))
        with patch("tas_app.views._push_submission_grade"):
            unlocked = _auth(
                InstructorFeedbackAPIView.as_view(),
                self.staff,
                "post",
                f"/tas/api/v1/submissions/{submission.pk}/feedback/",
                pk=submission.pk,
                data=body,
            )
        self.assertEqual(unlocked.status_code, 200)
        submission.refresh_from_db()
        self.assertEqual(submission.feedback.source, SOURCE_HUMAN)
        review.refresh_from_db()
        self.assertEqual(review.status, CurieReview.STATUS_FAILED)


@override_settings(CURIE_ENABLED=False)
class CurieLegacyCreateStillAllowedWhenDisabledTest(TestCase):
    def test_create_with_submitted_remains_legal_when_curie_is_off(self):
        submission = _swot_submission()
        block = submission.template_block
        payload = {
            "template_block_id": block.pk,
            "course_key": str(block.course_key),
            "usage_key": str(block.usage_key),
            "form_data": {"goal": "legacy submit"},
            "status": Submission.STATUS_SUBMITTED,
        }
        # Same student/block unique row already exists as draft; update in place.
        response = _auth(
            StudentSubmissionCreateAPIView.as_view(),
            submission.student,
            "post",
            "/tas/api/v1/student-submission/",
            data=payload,
        )
        self.assertIn(response.status_code, (200, 201))
        submission.refresh_from_db()
        self.assertEqual(submission.status, Submission.STATUS_SUBMITTED)


@override_settings(**SLICE_SETTINGS)
class CurieMysqlPhase4ConcurrencyTest(TransactionTestCase):
    def _skip_unless_mysql(self):
        if connection.vendor != "mysql":
            self.skipTest("select_for_update concurrency needs MySQL")

    def test_concurrent_timeout_reads_fail_the_review_once(self):
        self._skip_unless_mysql()
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        _age_pending(review)
        student = submission.student
        pk = submission.pk

        def _read(_):
            connection.close()
            return _auth(
                StudentCurieReviewAPIView.as_view(),
                student,
                "get",
                f"/tas/api/v1/student-submission/{pk}/curie-review/",
                pk=pk,
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(_read, range(2)))

        self.assertEqual(sorted(statuses), [200, 200])
        _assert_timed_out_without_projection(self, submission, review)

    @patch("tas_app.views._push_submission_grade")
    def test_pending_instructor_post_versus_callback(self, _mocked_grade):
        self._skip_unless_mysql()
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        instructor = UserFactory(is_staff=True, is_superuser=True)
        human_body = {
            "rubrics": [{"title": "Quality", "score": 4}],
            "comment": "Human tries to grade while pending.",
            "status": STATUS_APPROVED,
        }

        def _callback(_):
            connection.close()
            return apply_callback(review, _success_payload(review))

        def _human(_):
            connection.close()
            return _post_human_feedback(submission, instructor, human_body).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            callback_future = pool.submit(_callback, None)
            human_future = pool.submit(_human, None)
            callback_outcome = callback_future.result()
            human_status = human_future.result()

        submission.refresh_from_db()
        review.refresh_from_db()
        self.assertEqual(InstructorFeedback.objects.filter(submission=submission).count(), 1)
        self.assertEqual(submission.feedback.status, submission.status)
        if human_status == 409:
            self.assertEqual(callback_outcome, "applied")
            self.assertEqual(submission.feedback.source, SOURCE_CURIE)
            self.assertEqual(submission.status, Submission.STATUS_APPROVED)
        else:
            self.assertEqual(human_status, 200)
            self.assertEqual(submission.feedback.source, SOURCE_HUMAN)
            self.assertEqual(submission.status, STATUS_APPROVED)
            self.assertIn(callback_outcome, {"applied", "superseded"})
