"""Instructor approval and feedback release for CURIE reviews."""

from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from tas_app.curie.api import AdminCurieReviewApproveAPIView, StudentCurieReviewAPIView
from tas_app.curie.callback import apply_callback
from tas_app.curie.constants import SOURCE_CURIE, SOURCE_HUMAN
from tas_app.curie.submit import submit_student_submission
from tas_app.models import (
    STATUS_APPROVED,
    STATUS_REJECTED,
    CurieReview,
    InstructorFeedback,
    InstructorFeedbackVersion,
    Submission,
)
from tas_app.tests.test_curie_phase4 import _auth, _pdf_version, _swot_submission
from tas_app.tests.test_curie_slice import SLICE_SETTINGS, _scores, _success_payload
from tas_app.tests.test_models import (
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
    StudentSubmissionDetailAPIView,
    StudentSubmissionVersionsAPIView,
    WithdrawFeedbackAPIView,
)

PUSH_GRADE = "tas_app.views._push_submission_grade"


def _submitted_with_review(version_number=2):
    """A submitted attempt with its SubmissionVersion row and a pending CURIE review."""
    submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=version_number)
    _pdf_version(submission, version_number)
    review = CurieReview.objects.create(submission=submission, submission_version_number=version_number)
    return submission, review


def _awaiting_approval(version_number=2, gate=(9, 8, 9)):
    submission, review = _submitted_with_review(version_number)
    payload = _success_payload(review)
    payload["gate_criterion_scores"] = _scores(gate)
    assert apply_callback(review, payload) == "applied"
    review.refresh_from_db()
    submission.refresh_from_db()
    return submission, review


def _approve(staff, submission, body):
    return _auth(
        AdminCurieReviewApproveAPIView.as_view(),
        staff,
        "post",
        f"/tas/api/v1/submissions/{submission.pk}/curie-review/approve/",
        pk=submission.pk,
        data=body,
    )


def _override_body(review, *, overall="Instructor-edited overall feedback.", field_score=4):
    return {
        "action": "override",
        "submission_version_number": review.submission_version_number,
        "trigger_id": str(review.trigger_id),
        "overall_feedback": overall,
        "gate_criterion_scores": _scores((7, 7, 7)),
        "field_feedback": [
            {
                "field_id": "goal",
                "comment": "Instructor: make the goal measurable.",
                "criterion_scores": _scores((field_score, field_score, field_score)),
            },
        ],
    }


def _student_get(view, submission, path, query=""):
    return _auth(view, submission.student, "get", path, pk=submission.pk, query=query)


def _queue_row(staff, submission):
    request = APIRequestFactory().get(f"/tas/api/v1/block/{submission.usage_key}/submissions/")
    force_authenticate(request, user=staff)
    response = LearnerSubmissionsAPIView.as_view()(request, usage_key=str(submission.usage_key))
    return next(row for row in response.data["results"] if row["id"] == submission.pk)


@override_settings(**SLICE_SETTINGS)
class CurieCallbackAwaitsApprovalTest(TestCase):
    def setUp(self):
        self.staff = UserFactory(is_staff=True, is_superuser=True)

    @patch(PUSH_GRADE)
    def test_callback_generates_review_awaiting_approval(self, mocked_grade):
        submission, review = _submitted_with_review()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(apply_callback(review, _success_payload(review)), "applied")
        review.refresh_from_db()
        submission.refresh_from_db()
        self.assertEqual(review.status, CurieReview.STATUS_READY_FOR_APPROVAL)
        self.assertEqual(review.verdict, CurieReview.VERDICT_ACCEPTED)
        self.assertTrue(review.field_feedback)
        self.assertTrue(review.overall_feedback)
        # Not published: no projection, no status change, no grade.
        self.assertEqual(submission.status, Submission.STATUS_SUBMITTED)
        self.assertFalse(InstructorFeedback.objects.filter(submission=submission).exists())
        self.assertIsNone(review.approved_at)
        self.assertEqual(review.published_source, "")
        mocked_grade.assert_not_called()

    def test_student_apis_hide_unapproved_review(self):
        submission, _review = _awaiting_approval()
        base = f"/tas/api/v1/student-submission/{submission.pk}/"

        review_response = _student_get(StudentCurieReviewAPIView.as_view(), submission, f"{base}curie-review/")
        self.assertEqual(review_response.status_code, 200)
        data = review_response.data
        self.assertEqual(data["status"], CurieReview.STATUS_READY_FOR_APPROVAL)
        self.assertIsNone(data["verdict"])
        self.assertEqual(data["overall_feedback"], "")
        self.assertEqual(data["field_feedback"], [])
        self.assertIsNone(data["star_rating"])
        self.assertIsNone(data["feedback_source"])

        detail = _student_get(StudentSubmissionDetailAPIView.as_view(), submission, base)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["status"], Submission.STATUS_SUBMITTED)
        self.assertEqual(detail.data["curie_review_status"], CurieReview.STATUS_READY_FOR_APPROVAL)
        self.assertIsNone(detail.data["feedback"])

        versions = _student_get(StudentSubmissionVersionsAPIView.as_view(), submission, f"{base}versions/")
        self.assertEqual(versions.status_code, 200)
        for version in versions.data["versions"]:
            self.assertIsNone(version["verdict"])
            self.assertIsNone(version["star_rating"])
            self.assertEqual(version["instructor_comment"], "")
        self.assertNotIn("Strong submission overall", str(versions.data))

    def test_instructor_can_view_review_awaiting_approval(self):
        submission, review = _awaiting_approval()
        response = _auth(
            LearnerSubmissionDetailAPIView.as_view(),
            self.staff,
            "get",
            f"/tas/api/v1/submissions/{submission.pk}/",
            pk=submission.pk,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], Submission.STATUS_SUBMITTED)
        curie = response.data["curie_review"]
        self.assertEqual(curie["status"], CurieReview.STATUS_READY_FOR_APPROVAL)
        self.assertTrue(curie["awaiting_approval"])
        self.assertEqual(curie["verdict"], CurieReview.VERDICT_ACCEPTED)
        self.assertEqual(curie["overall_feedback"], review.overall_feedback)
        self.assertEqual(curie["trigger_id"], str(review.trigger_id))
        self.assertIn("criterion_scores", curie["field_feedback"][0])
        self.assertIsNotNone(curie["gate_score"])
        self.assertIsNone(curie["approval"])

        row = _queue_row(self.staff, submission)
        self.assertEqual(row["status"], Submission.STATUS_SUBMITTED)
        self.assertEqual(row["curie_review_status"], CurieReview.STATUS_READY_FOR_APPROVAL)
        self.assertEqual(row["feedback_source"], SOURCE_CURIE)
        self.assertFalse(row["instructor_form_locked"])

    def test_legacy_feedback_endpoint_is_closed_while_awaiting_approval(self):
        submission, _review = _awaiting_approval()
        response = _auth(
            InstructorFeedbackAPIView.as_view(),
            self.staff,
            "post",
            f"/tas/api/v1/submissions/{submission.pk}/feedback/",
            pk=submission.pk,
            data={"rubrics": [], "comment": "manual", "status": STATUS_APPROVED},
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(InstructorFeedback.objects.filter(submission=submission).exists())


@override_settings(**SLICE_SETTINGS)
class CurieApproveTest(TestCase):
    def setUp(self):
        self.staff = UserFactory(is_staff=True, is_superuser=True)

    @patch(PUSH_GRADE)
    def test_approve_unchanged_publishes_curie_output(self, mocked_grade):
        submission, review = _awaiting_approval()
        with self.captureOnCommitCallbacks(execute=True):
            response = _approve(self.staff, submission, {
                "action": "approve",
                "submission_version_number": review.submission_version_number,
                "trigger_id": str(review.trigger_id),
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["outcome"], "approved")
        self.assertEqual(response.data["approval"]["published_source"], SOURCE_CURIE)
        self.assertEqual(response.data["approval"]["approved_by"], self.staff.username)

        review.refresh_from_db()
        submission.refresh_from_db()
        self.assertEqual(review.status, CurieReview.STATUS_APPROVED)
        self.assertEqual(review.approved_by, self.staff)
        self.assertIsNotNone(review.approved_at)
        self.assertFalse(review.approval_modified)
        self.assertEqual(review.published_source, SOURCE_CURIE)
        self.assertEqual(review.approved_verdict, CurieReview.VERDICT_ACCEPTED)
        self.assertEqual(review.approved_overall_feedback, review.overall_feedback)
        self.assertEqual(review.approved_field_feedback, review.field_feedback)

        feedback = submission.feedback
        self.assertEqual(feedback.source, SOURCE_CURIE)
        self.assertIsNone(feedback.instructor)
        self.assertEqual(feedback.status, STATUS_APPROVED)
        self.assertEqual(submission.status, Submission.STATUS_APPROVED)
        self.assertEqual(len(feedback.rubrics), 3)
        snapshot = feedback.tas_instructor_feedback_versions.get()
        self.assertEqual(snapshot.submission_version.version_number, review.submission_version_number)
        mocked_grade.assert_called_once()
        self.assertEqual(mocked_grade.call_args.kwargs["curie_trigger_id"], str(review.trigger_id))

    @patch(PUSH_GRADE)
    def test_approve_unchanged_rejected_verdict_marks_reattempt_without_grade(self, mocked_grade):
        submission, review = _awaiting_approval(gate=(5, 5, 4))
        with self.captureOnCommitCallbacks(execute=True):
            response = _approve(self.staff, submission, {
                "action": "approve",
                "submission_version_number": review.submission_version_number,
            })
        self.assertEqual(response.status_code, 200)
        submission.refresh_from_db()
        self.assertEqual(submission.status, Submission.STATUS_REJECTED)
        self.assertEqual(submission.feedback.status, STATUS_REJECTED)
        mocked_grade.assert_not_called()

    @patch(PUSH_GRADE)
    def test_edit_and_approve_publishes_edited_content_as_human(self, mocked_grade):
        submission, review = _awaiting_approval()
        original_fields = list(review.field_feedback)
        original_overall = review.overall_feedback
        with self.captureOnCommitCallbacks(execute=True):
            response = _approve(self.staff, submission, _override_body(review, field_score=4))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["outcome"], "approved")

        review.refresh_from_db()
        submission.refresh_from_db()
        self.assertEqual(review.status, CurieReview.STATUS_APPROVED)
        self.assertTrue(review.approval_modified)
        self.assertEqual(review.published_source, SOURCE_HUMAN)
        self.assertEqual(review.approved_by, self.staff)
        self.assertEqual(review.approved_overall_feedback, "Instructor-edited overall feedback.")
        goal = next(item for item in review.approved_field_feedback if item["field_id"] == "goal")
        self.assertEqual(goal["comment"], "Instructor: make the goal measurable.")
        self.assertEqual(goal["weight"], 1)
        # Untouched fields keep CURIE's text; CURIE's original output stays intact.
        strength = next(item for item in review.approved_field_feedback if item["field_id"] == "strength")
        self.assertEqual(strength["comment"], "Strength is evidenced.")
        self.assertEqual(review.field_feedback, original_fields)
        self.assertEqual(review.overall_feedback, original_overall)
        # Goal now scores 4 < 6, so existing verdict rules reject the attempt.
        self.assertEqual(review.approved_verdict, CurieReview.VERDICT_REJECTED)
        self.assertEqual(submission.status, Submission.STATUS_REJECTED)

        feedback = submission.feedback
        self.assertEqual(feedback.source, SOURCE_HUMAN)
        self.assertEqual(feedback.instructor, self.staff)
        self.assertEqual(feedback.status, STATUS_REJECTED)
        self.assertIn("Instructor-edited overall feedback.", feedback.comment)
        mocked_grade.assert_not_called()

    def test_override_sets_source_to_human_in_queue_and_detail(self):
        submission, review = _awaiting_approval()
        with patch(PUSH_GRADE):
            _approve(self.staff, submission, _override_body(review, field_score=9))
        row = _queue_row(self.staff, submission)
        self.assertEqual(row["curie_review_status"], CurieReview.STATUS_APPROVED)
        self.assertEqual(row["feedback_source"], SOURCE_HUMAN)
        self.assertEqual(row["status"], Submission.STATUS_APPROVED)

        detail = _auth(
            LearnerSubmissionDetailAPIView.as_view(),
            self.staff,
            "get",
            f"/tas/api/v1/submissions/{submission.pk}/",
            pk=submission.pk,
        )
        approval = detail.data["curie_review"]["approval"]
        self.assertEqual(approval["published_source"], SOURCE_HUMAN)
        self.assertTrue(approval["approval_modified"])
        self.assertEqual(approval["overall_feedback"], "Instructor-edited overall feedback.")
        self.assertEqual(detail.data["feedback"]["source"], SOURCE_HUMAN)

    def test_student_receives_approved_feedback(self):
        submission, review = _awaiting_approval()
        with patch(PUSH_GRADE):
            _approve(self.staff, submission, _override_body(review, field_score=9))
        base = f"/tas/api/v1/student-submission/{submission.pk}/"

        data = _student_get(StudentCurieReviewAPIView.as_view(), submission, f"{base}curie-review/").data
        self.assertEqual(data["status"], CurieReview.STATUS_APPROVED)
        self.assertEqual(data["verdict"], CurieReview.VERDICT_ACCEPTED)
        self.assertEqual(data["overall_feedback"], "Instructor-edited overall feedback.")
        self.assertEqual(data["feedback_source"], SOURCE_HUMAN)
        self.assertTrue(data["approval_modified"])
        goal = next(item for item in data["field_feedback"] if item["field_id"] == "goal")
        self.assertEqual(goal["comment"], "Instructor: make the goal measurable.")
        self.assertNotIn("criterion_scores", goal)
        self.assertIsNotNone(data["star_rating"])

        detail = _student_get(StudentSubmissionDetailAPIView.as_view(), submission, base).data
        self.assertEqual(detail["status"], Submission.STATUS_APPROVED)
        self.assertEqual(detail["curie_review_status"], CurieReview.STATUS_APPROVED)
        self.assertEqual(detail["feedback"]["rubrics"], [])
        self.assertEqual(detail["feedback"]["verdict"], CurieReview.VERDICT_ACCEPTED)
        self.assertTrue(detail["feedback"]["approval_modified"])
        self.assertNotIn("marks", str(detail["feedback"]))

        versions = _student_get(StudentSubmissionVersionsAPIView.as_view(), submission, f"{base}versions/").data
        current = next(v for v in versions["versions"] if v["version_number"] == submission.version_number)
        self.assertEqual(current["verdict"], CurieReview.VERDICT_ACCEPTED)
        self.assertEqual(current["feedback_source"], SOURCE_HUMAN)

    def test_status_updates_in_queue_after_unchanged_approval(self):
        submission, review = _awaiting_approval()
        self.assertEqual(_queue_row(self.staff, submission)["curie_review_status"], "ready_for_approval")
        with patch(PUSH_GRADE):
            _approve(self.staff, submission, {
                "action": "approve",
                "submission_version_number": review.submission_version_number,
            })
        row = _queue_row(self.staff, submission)
        self.assertEqual(row["curie_review_status"], CurieReview.STATUS_APPROVED)
        self.assertEqual(row["status"], Submission.STATUS_APPROVED)
        self.assertEqual(row["feedback_status"], STATUS_APPROVED)
        self.assertEqual(row["feedback_source"], SOURCE_CURIE)

    @patch(PUSH_GRADE)
    def test_duplicate_approval_is_safe(self, mocked_grade):
        submission, review = _awaiting_approval()
        body = {"action": "approve", "submission_version_number": review.submission_version_number}
        with self.captureOnCommitCallbacks(execute=True):
            first = _approve(self.staff, submission, body)
        with self.captureOnCommitCallbacks(execute=True):
            second = _approve(self.staff, submission, body)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["outcome"], "already_approved")
        self.assertEqual(mocked_grade.call_count, 1)
        self.assertEqual(
            InstructorFeedbackVersion.objects.filter(instructor_feedback__submission=submission).count(), 1
        )

        other_staff = UserFactory(is_staff=True)
        conflicting = _approve(other_staff, submission, _override_body(review))
        self.assertEqual(conflicting.status_code, 409)
        self.assertEqual(conflicting.data["code"], "already_approved")
        review.refresh_from_db()
        self.assertEqual(review.approved_by, self.staff)
        self.assertEqual(review.published_source, SOURCE_CURIE)

    def test_identical_override_replay_is_idempotent(self):
        submission, review = _awaiting_approval()
        body = _override_body(review)
        with patch(PUSH_GRADE):
            self.assertEqual(_approve(self.staff, submission, body).status_code, 200)
            replay = _approve(self.staff, submission, body)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.data["outcome"], "already_approved")

    def test_withdraw_and_legacy_grading_blocked_after_approval(self):
        submission, review = _awaiting_approval()
        with patch(PUSH_GRADE):
            _approve(self.staff, submission, _override_body(review, field_score=9))
        withdraw = _auth(
            WithdrawFeedbackAPIView.as_view(),
            self.staff,
            "post",
            f"/tas/api/v1/submissions/{submission.pk}/feedback/withdraw/",
            pk=submission.pk,
        )
        self.assertEqual(withdraw.status_code, 403)
        submission.refresh_from_db()
        self.assertEqual(submission.status, Submission.STATUS_APPROVED)

    def test_override_validation_errors_do_not_publish(self):
        submission, review = _awaiting_approval()
        body = _override_body(review)
        body["field_feedback"][0]["criterion_scores"] = _scores((11, 5, 5))
        response = _approve(self.staff, submission, body)
        self.assertEqual(response.status_code, 400)
        body = _override_body(review)
        body["field_feedback"] = [{"field_id": "unknown", "comment": "x", "criterion_scores": _scores((5, 5, 5))}]
        self.assertEqual(_approve(self.staff, submission, body).status_code, 400)
        body = _override_body(review, overall="  ")
        self.assertEqual(_approve(self.staff, submission, body).status_code, 400)
        review.refresh_from_db()
        self.assertEqual(review.status, CurieReview.STATUS_READY_FOR_APPROVAL)
        self.assertFalse(InstructorFeedback.objects.filter(submission=submission).exists())

    def test_non_staff_cannot_approve(self):
        submission, review = _awaiting_approval()
        body = {"action": "approve", "submission_version_number": review.submission_version_number}
        self.assertEqual(_approve(submission.student, submission, body).status_code, 403)
        review.refresh_from_db()
        self.assertEqual(review.status, CurieReview.STATUS_READY_FOR_APPROVAL)

    def test_pending_review_cannot_be_approved(self):
        submission, review = _submitted_with_review()
        response = _approve(self.staff, submission, {
            "action": "approve",
            "submission_version_number": review.submission_version_number,
        })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "not_ready")


@override_settings(**SLICE_SETTINGS)
class CurieApprovalVersioningTest(TestCase):
    def setUp(self):
        self.staff = UserFactory(is_staff=True, is_superuser=True)

    def test_older_review_cannot_overwrite_newer_attempt(self):
        submission, old_review = _awaiting_approval(version_number=2)
        # A newer attempt exists (e.g. data repaired or resubmitted after a failure).
        Submission.objects.filter(pk=submission.pk).update(version_number=3)
        newer = CurieReview.objects.create(submission=submission, submission_version_number=3)

        response = _approve(self.staff, submission, {
            "action": "approve",
            "submission_version_number": 2,
            "trigger_id": str(old_review.trigger_id),
        })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "stale")
        old_review.refresh_from_db()
        newer.refresh_from_db()
        submission.refresh_from_db()
        self.assertEqual(old_review.status, CurieReview.STATUS_READY_FOR_APPROVAL)
        self.assertEqual(newer.status, CurieReview.STATUS_PENDING_EVALUATION)
        self.assertEqual(submission.status, Submission.STATUS_SUBMITTED)
        self.assertFalse(InstructorFeedback.objects.filter(submission=submission).exists())

        # Mismatched trigger for the current version is also refused.
        mismatch = _approve(self.staff, submission, {
            "action": "approve",
            "submission_version_number": 3,
            "trigger_id": str(old_review.trigger_id),
        })
        self.assertEqual(mismatch.status_code, 409)

    @patch("tas_app.curie.celery_tasks.deliver_curie_trigger.delay")
    @patch("tas_app.curie.submit.generate_submission_pdf")
    def test_resubmission_after_edit_and_approve_starts_new_lifecycle(self, _pdf, _delay):
        submission, review = _awaiting_approval(version_number=2)
        with patch(PUSH_GRADE):
            _approve(self.staff, submission, _override_body(review, field_score=4))
        submission.refresh_from_db()
        self.assertEqual(submission.status, Submission.STATUS_REJECTED)
        self.assertEqual(submission.feedback.source, SOURCE_HUMAN)

        with self.captureOnCommitCallbacks(execute=True):
            submit_student_submission(
                pk=submission.pk,
                student=submission.student,
                form_data=dict(submission.form_data, goal="A measurable goal for the reattempt."),
            )
        submission.refresh_from_db()
        self.assertEqual(submission.version_number, 3)
        self.assertEqual(submission.status, Submission.STATUS_SUBMITTED)
        new_review = CurieReview.objects.get(submission=submission, submission_version_number=3)
        self.assertEqual(new_review.status, CurieReview.STATUS_PENDING_EVALUATION)

        # Late callback for the old attempt is stale; the new attempt's callback applies.
        self.assertEqual(apply_callback(review, _success_payload(review)), "stale")
        self.assertEqual(apply_callback(new_review, _success_payload(new_review)), "applied")
        new_review.refresh_from_db()
        review.refresh_from_db()
        self.assertEqual(new_review.status, CurieReview.STATUS_READY_FOR_APPROVAL)
        self.assertEqual(review.status, CurieReview.STATUS_APPROVED)

        # The previous release stays as history; the new attempt is hidden until approved.
        detail = _student_get(
            StudentSubmissionDetailAPIView.as_view(),
            submission,
            f"/tas/api/v1/student-submission/{submission.pk}/",
        ).data
        self.assertEqual(detail["curie_review_status"], CurieReview.STATUS_READY_FOR_APPROVAL)
        self.assertIsNone(detail["feedback"])
        history = _student_get(
            StudentCurieReviewAPIView.as_view(),
            submission,
            f"/tas/api/v1/student-submission/{submission.pk}/curie-review/",
            query="?version=2",
        ).data
        self.assertEqual(history["status"], CurieReview.STATUS_APPROVED)
        self.assertEqual(history["overall_feedback"], "Instructor-edited overall feedback.")

    def test_existing_ready_reviews_are_not_modified(self):
        """Legacy auto-published reviews keep status ready and stay visible."""
        submission = _swot_submission(status=Submission.STATUS_APPROVED, version_number=2)
        review = CurieReview.objects.create(
            submission=submission,
            submission_version_number=2,
            status=CurieReview.STATUS_READY,
            verdict=CurieReview.VERDICT_ACCEPTED,
            gate_criterion_scores=_scores((9, 9, 9)),
            field_feedback=[{
                "field_id": "goal",
                "weight": 1,
                "comment": "Legacy comment.",
                "criterion_scores": _scores((9, 9, 9)),
            }],
            overall_feedback="Legacy overall.",
        )
        data = _student_get(
            StudentCurieReviewAPIView.as_view(),
            submission,
            f"/tas/api/v1/student-submission/{submission.pk}/curie-review/",
        ).data
        self.assertEqual(data["status"], CurieReview.STATUS_READY)
        self.assertEqual(data["overall_feedback"], "Legacy overall.")
        self.assertEqual(data["feedback_source"], SOURCE_CURIE)
        response = _approve(self.staff, submission, {
            "action": "approve",
            "submission_version_number": 2,
        })
        self.assertEqual(response.status_code, 409)
        review.refresh_from_db()
        self.assertEqual(review.status, CurieReview.STATUS_READY)


@override_settings(**SLICE_SETTINGS)
class HumanWorkflowUnaffectedTest(TestCase):
    def setUp(self):
        self.staff = UserFactory(is_staff=True, is_superuser=True)

    def _non_curie_submission(self):
        template_type = TemplateTypeFactory(slug="essay", name="Essay")
        block = TemplateBlockFactory(template=TemplateFactory(template_type=template_type), curie_enabled=False)
        return SubmissionFactory(template_block=block, status=Submission.STATUS_SUBMITTED, version_number=1)

    def test_human_grading_of_non_curie_submission_still_works(self):
        submission = self._non_curie_submission()
        with patch(PUSH_GRADE) as mocked_grade:
            response = _auth(
                InstructorFeedbackAPIView.as_view(),
                self.staff,
                "post",
                f"/tas/api/v1/submissions/{submission.pk}/feedback/",
                pk=submission.pk,
                data={"rubrics": [], "comment": "Well done.", "status": STATUS_APPROVED},
            )
        self.assertEqual(response.status_code, 200)
        submission.refresh_from_db()
        self.assertEqual(submission.status, Submission.STATUS_APPROVED)
        self.assertEqual(submission.feedback.source, SOURCE_HUMAN)
        mocked_grade.assert_called_once()

        detail = _student_get(
            StudentSubmissionDetailAPIView.as_view(),
            submission,
            f"/tas/api/v1/student-submission/{submission.pk}/",
        ).data
        self.assertEqual(detail["feedback"]["comment"], "Well done.")
        self.assertIsNone(detail["curie_review_status"])

        with patch("tas_app.views._clear_submission_grade"):
            withdraw = _auth(
                WithdrawFeedbackAPIView.as_view(),
                self.staff,
                "post",
                f"/tas/api/v1/submissions/{submission.pk}/feedback/withdraw/",
                pk=submission.pk,
            )
        self.assertEqual(withdraw.status_code, 200)

    def test_human_grading_after_curie_failure_still_works(self):
        submission, review = _submitted_with_review()
        review.status = CurieReview.STATUS_FAILED
        review.save(update_fields=["status", "modified"])
        with patch(PUSH_GRADE):
            response = _auth(
                InstructorFeedbackAPIView.as_view(),
                self.staff,
                "post",
                f"/tas/api/v1/submissions/{submission.pk}/feedback/",
                pk=submission.pk,
                data={"rubrics": [], "comment": "Graded manually.", "status": STATUS_REJECTED},
            )
        self.assertEqual(response.status_code, 200)
        submission.refresh_from_db()
        self.assertEqual(submission.feedback.source, SOURCE_HUMAN)
        self.assertEqual(submission.status, Submission.STATUS_REJECTED)
        # Human ownership is still permanent for legacy grading: late CURIE output is superseded.
        self.assertEqual(apply_callback(review, _success_payload(review)), "superseded")
