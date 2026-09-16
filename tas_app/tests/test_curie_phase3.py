"""Phase 3: trigger retry task and callback race matrix."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from unittest.mock import MagicMock, patch

from celery.exceptions import Retry
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from tas_app.curie.callback import apply_callback
from tas_app.curie.constants import (
    HUMAN_SUPERSEDED_DETAIL,
    SOURCE_HUMAN,
    TIMEOUT_ERROR_DETAIL,
    TRIGGER_EXHAUSTED_ERROR_DETAIL,
)
from tas_app.curie.delivery import attempt_trigger_delivery, retry_countdown_seconds, run_deliver_curie_trigger
from tas_app.curie.submit import CurieSubmitError, submit_student_submission
from tas_app.curie.trigger import RetryableTriggerError, TerminalTriggerError, build_trigger_payload, send_trigger
from tas_app.models import CurieReview, InstructorFeedback, STATUS_APPROVED, STATUS_PENDING, Submission
from tas_app.tests.test_curie_slice import SLICE_SETTINGS, _success_payload, _swot_submission
from tas_app.tests.test_models import InstructorFeedbackFactory, UserFactory
from tas_app.views import CurieReviewCallbackAPIView, InstructorFeedbackAPIView


def _error_payload(review, message="CURIE processing error"):
    return {
        "trigger_id": str(review.trigger_id),
        "user_id": str(review.submission.student_id),
        "submission_id": str(review.submission_id),
        "submission_version_number": review.submission_version_number,
        "result": "error",
        "error_message": message,
    }


def _post_callback(review, body, secret="test-shared-secret"):
    factory = APIRequestFactory()
    headers = {"HTTP_X_CURIE_SHARED_SECRET": secret} if secret is not None else {}
    request = factory.post(
        f"/tas/api/v1/curie/reviews/{review.trigger_id}/callback/",
        body,
        format="json",
        **headers,
    )
    return CurieReviewCallbackAPIView.as_view()(request, trigger_id=review.trigger_id)


@override_settings(**SLICE_SETTINGS)
class CurieTriggerDeliveryTest(TestCase):
    def test_retry_countdowns_jitter_around_15_60_240(self):
        self.assertEqual(retry_countdown_seconds(0, rng=lambda: 0.5), 15)
        self.assertEqual(retry_countdown_seconds(1, rng=lambda: 0.5), 60)
        self.assertEqual(retry_countdown_seconds(2, rng=lambda: 0.5), 240)

    @patch("tas_app.curie.trigger.requests.post")
    def test_send_trigger_posts_contract_url(self, mocked_post):
        mocked_post.return_value.status_code = 202
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        from tas_app.curie.trigger import build_trigger_payload

        payload = build_trigger_payload(review, submission)
        send_trigger(payload)
        mocked_post.assert_called_once()
        self.assertEqual(mocked_post.call_args.args[0], "http://curie-stub.example/api/v1/assessment-reviews/")
        self.assertEqual(mocked_post.call_args.kwargs["json"]["trigger_id"], str(review.trigger_id))

    @patch("tas_app.curie.delivery.send_trigger", side_effect=TerminalTriggerError("HTTP 400"))
    def test_terminal_4xx_fails_pending_review(self, _mocked):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        task = MagicMock()
        run_deliver_curie_trigger(task, str(review.trigger_id), "http://lms.example/cb")
        task.retry.assert_not_called()
        review.refresh_from_db()
        self.assertEqual(review.status, CurieReview.STATUS_FAILED)
        self.assertIn("HTTP 400", review.error_detail)

    @patch("tas_app.curie.delivery.send_trigger", side_effect=RetryableTriggerError("HTTP 503"))
    def test_retryable_failure_schedules_retry_same_trigger_id(self, _mocked):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        task = MagicMock()
        task.request.retries = 0
        task.retry.side_effect = Retry()
        with self.assertRaises(Retry):
            run_deliver_curie_trigger(task, str(review.trigger_id), "http://lms.example/cb")
        task.retry.assert_called_once()
        self.assertIn("countdown", task.retry.call_args.kwargs)
        review.refresh_from_db()
        self.assertEqual(review.status, CurieReview.STATUS_PENDING_EVALUATION)

    @patch("tas_app.curie.delivery.send_trigger", side_effect=RetryableTriggerError("timeout"))
    def test_exhausted_retries_mark_review_failed(self, _mocked):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        task = MagicMock()
        task.request.retries = 3
        task.max_retries = 3
        # Celery 5.5 re-raises the cause on exhaustion instead of MaxRetriesExceededError.
        task.retry.side_effect = RetryableTriggerError("timeout")
        run_deliver_curie_trigger(task, str(review.trigger_id), "http://lms.example/cb")
        task.retry.assert_not_called()
        review.refresh_from_db()
        self.assertEqual(review.status, CurieReview.STATUS_FAILED)
        self.assertIn(TRIGGER_EXHAUSTED_ERROR_DETAIL, review.error_detail)

    @patch("tas_app.curie.delivery.send_trigger")
    def test_retry_reuses_frozen_trigger_payload(self, mocked_send):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        frozen = build_trigger_payload(review, submission)
        review.trigger_payload = frozen
        review.save(update_fields=["trigger_payload", "modified"])
        submission.form_data = {"goal": "changed after the trigger was frozen"}
        submission.save(update_fields=["form_data", "modified"])
        attempt_trigger_delivery(str(review.trigger_id))
        mocked_send.assert_called_once_with(frozen)
        self.assertEqual(
            mocked_send.call_args.args[0]["form_data"]["goal"]["answer"],
            "Complete the NPTEL Python course by March 2027.",
        )


@override_settings(**SLICE_SETTINGS)
class CurieCallbackRaceTest(TestCase):
    def test_stale_callback_is_409_and_does_not_mutate(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=3)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        payload = _success_payload(review)
        payload["submission_version_number"] = 2
        response = _post_callback(review, payload)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["status"], "stale")
        review.refresh_from_db()
        self.assertEqual(review.status, CurieReview.STATUS_PENDING_EVALUATION)
        self.assertFalse(InstructorFeedback.objects.filter(submission=submission).exists())

    def test_conflicting_error_does_not_downgrade_success(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        self.assertEqual(apply_callback(review, _success_payload(review)), "applied")
        review.refresh_from_db()
        response = _post_callback(review, _error_payload(review))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["status"], "conflict")
        review.refresh_from_db()
        submission.refresh_from_db()
        self.assertEqual(review.status, CurieReview.STATUS_READY)
        self.assertEqual(review.verdict, CurieReview.VERDICT_ACCEPTED)
        self.assertEqual(submission.status, Submission.STATUS_APPROVED)

    def test_conflicting_success_payload_is_409(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        first = _success_payload(review)
        self.assertEqual(apply_callback(review, first), "applied")
        other = _success_payload(review)
        other["overall_feedback"] = "A different overall comment that still validates."
        self.assertEqual(apply_callback(review, other), "conflict")
        review.refresh_from_db()
        self.assertEqual(review.overall_feedback, first["overall_feedback"])

    def test_late_success_after_timeout_applies_when_no_human_owner(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(
            submission=submission,
            submission_version_number=2,
            status=CurieReview.STATUS_FAILED,
            error_detail=TIMEOUT_ERROR_DETAIL,
        )
        self.assertEqual(apply_callback(review, _success_payload(review)), "applied")
        review.refresh_from_db()
        submission.refresh_from_db()
        self.assertEqual(review.status, CurieReview.STATUS_READY)
        self.assertEqual(submission.status, Submission.STATUS_APPROVED)

    def test_human_owner_supersedes_late_success(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(
            submission=submission,
            submission_version_number=2,
            status=CurieReview.STATUS_FAILED,
            error_detail=TIMEOUT_ERROR_DETAIL,
        )
        InstructorFeedbackFactory(submission=submission, source=SOURCE_HUMAN, status=STATUS_PENDING)
        response = _post_callback(review, _success_payload(review))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "superseded")
        review.refresh_from_db()
        submission.refresh_from_db()
        self.assertEqual(review.status, CurieReview.STATUS_FAILED)
        self.assertIn(HUMAN_SUPERSEDED_DETAIL, review.error_detail)
        self.assertEqual(submission.status, Submission.STATUS_SUBMITTED)
        self.assertEqual(submission.feedback.source, SOURCE_HUMAN)
        self.assertEqual(submission.feedback.status, STATUS_PENDING)

    def test_error_then_success_applies_late_result(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        self.assertEqual(apply_callback(review, _error_payload(review)), "failed")
        review.refresh_from_db()
        self.assertEqual(apply_callback(review, _success_payload(review)), "applied")
        review.refresh_from_db()
        self.assertEqual(review.status, CurieReview.STATUS_READY)

    def test_success_after_commit_hook_runs_only_after_commit(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        ran = []

        def after_success(applied):
            ran.append(applied.pk)

        with self.captureOnCommitCallbacks() as callbacks:
            apply_callback(review, _success_payload(review), after_success=after_success)
            self.assertEqual(ran, [])
        for callback in callbacks:
            callback()
        self.assertEqual(ran, [review.pk])


def _post_human_feedback(submission, instructor, body):
    factory = APIRequestFactory()
    request = factory.post(
        f"/tas/api/v1/submissions/{submission.pk}/feedback/",
        body,
        format="json",
    )
    force_authenticate(request, user=instructor)
    return InstructorFeedbackAPIView.as_view()(request, pk=submission.pk)


@override_settings(**SLICE_SETTINGS)
class CurieMysqlConcurrencyTest(TransactionTestCase):
    def _skip_unless_mysql(self):
        if connection.vendor != "mysql":
            self.skipTest("select_for_update concurrency needs MySQL")

    def test_concurrent_identical_callbacks_are_applied_once(self):
        self._skip_unless_mysql()
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        payload = _success_payload(review)

        def _one(_):
            connection.close()
            return apply_callback(review, payload)

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(_one, range(2)))

        self.assertEqual(sorted(outcomes), ["applied", "replayed"])
        review.refresh_from_db()
        submission.refresh_from_db()
        self.assertEqual(review.status, CurieReview.STATUS_READY)
        self.assertEqual(submission.feedback.source, InstructorFeedback.SOURCE_CURIE)
        self.assertEqual(InstructorFeedback.objects.filter(submission=submission).count(), 1)

    def test_concurrent_conflicting_callbacks_keep_the_first_payload(self):
        self._skip_unless_mysql()
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        first = _success_payload(review)
        second = deepcopy(first)
        second["overall_feedback"] = "A different overall comment that still validates."

        def _run(payload):
            connection.close()
            return apply_callback(review, payload)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first_future = pool.submit(_run, first)
            second_future = pool.submit(_run, second)
            outcomes = sorted([first_future.result(), second_future.result()])

        self.assertEqual(outcomes, ["applied", "conflict"])
        review.refresh_from_db()
        self.assertEqual(review.status, CurieReview.STATUS_READY)
        self.assertIn(review.overall_feedback, {first["overall_feedback"], second["overall_feedback"]})

    @patch("tas_app.views._push_submission_grade")
    def test_callback_versus_human_does_not_split_feedback_and_status(self, _mocked_grade):
        self._skip_unless_mysql()
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(
            submission=submission,
            submission_version_number=2,
            status=CurieReview.STATUS_FAILED,
            error_detail=TIMEOUT_ERROR_DETAIL,
        )
        instructor = UserFactory(is_staff=True, is_superuser=True)
        human_body = {
            "rubrics": [{"title": "Quality", "score": 4}],
            "comment": "Human finalizes this attempt.",
            "status": STATUS_APPROVED,
        }

        def _callback(_):
            connection.close()
            return apply_callback(review, _success_payload(review))

        def _human(_):
            connection.close()
            response = _post_human_feedback(submission, instructor, human_body)
            return response.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            callback_future = pool.submit(_callback, None)
            human_future = pool.submit(_human, None)
            callback_outcome = callback_future.result()
            human_status = human_future.result()

        self.assertEqual(human_status, 200)
        self.assertIn(callback_outcome, {"applied", "superseded"})
        submission.refresh_from_db()
        review.refresh_from_db()
        self.assertEqual(submission.feedback.source, SOURCE_HUMAN)
        self.assertEqual(submission.feedback.status, STATUS_APPROVED)
        self.assertEqual(submission.status, STATUS_APPROVED)
        self.assertEqual(submission.feedback.comment, "Human finalizes this attempt.")
        if callback_outcome == "superseded":
            self.assertNotEqual(review.status, CurieReview.STATUS_READY)
            self.assertIn(HUMAN_SUPERSEDED_DETAIL, review.error_detail)
        else:
            self.assertEqual(review.status, CurieReview.STATUS_READY)

    @patch("tas_app.views._push_submission_grade")
    @patch("tas_app.curie.submit.generate_submission_pdf")
    @patch("tas_app.curie.celery_tasks.deliver_curie_trigger.delay")
    def test_reattempt_versus_late_success_callback_on_failed_review(
        self, _mocked_delay, _mocked_pdf, _mocked_grade
    ):
        """Legal reattempt from a failed current review vs late success on that same row."""
        self._skip_unless_mysql()
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(
            submission=submission,
            submission_version_number=2,
            status=CurieReview.STATUS_FAILED,
            error_detail=TIMEOUT_ERROR_DETAIL,
        )
        payload = _success_payload(review)
        form_data = dict(submission.form_data)
        form_data["goal"] = "Reattempt after CURIE failure."

        def _reattempt(_):
            connection.close()
            try:
                submit_student_submission(
                    pk=submission.pk,
                    student=submission.student,
                    form_data=form_data,
                )
                return "reattempt"
            except CurieSubmitError as exc:
                return f"conflict:{exc.status_code}"

        def _late(_):
            connection.close()
            return apply_callback(review, payload)

        with ThreadPoolExecutor(max_workers=2) as pool:
            reattempt_future = pool.submit(_reattempt, None)
            late_future = pool.submit(_late, None)
            reattempt_outcome = reattempt_future.result()
            callback_outcome = late_future.result()

        submission.refresh_from_db()
        review.refresh_from_db()
        reviews = list(
            CurieReview.objects.filter(submission=submission).order_by("submission_version_number")
        )
        feedback = InstructorFeedback.objects.filter(submission=submission).first()

        if callback_outcome == "applied":
            self.assertEqual(reattempt_outcome, "conflict:409")
            self.assertEqual(len(reviews), 1)
            self.assertEqual(submission.version_number, 2)
            self.assertEqual(submission.status, STATUS_APPROVED)
            self.assertEqual(review.status, CurieReview.STATUS_READY)
            self.assertIsNotNone(feedback)
            self.assertEqual(feedback.source, InstructorFeedback.SOURCE_CURIE)
            self.assertEqual(feedback.status, STATUS_APPROVED)
            self.assertEqual(submission.status, feedback.status)
        elif callback_outcome == "stale":
            self.assertEqual(reattempt_outcome, "reattempt")
            self.assertEqual(len(reviews), 2)
            self.assertEqual(submission.version_number, 3)
            self.assertEqual(submission.status, Submission.STATUS_SUBMITTED)
            self.assertEqual(reviews[0].pk, review.pk)
            self.assertEqual(reviews[0].status, CurieReview.STATUS_FAILED)
            self.assertEqual(reviews[1].status, CurieReview.STATUS_PENDING_EVALUATION)
            self.assertEqual(reviews[1].submission_version_number, 3)
            self.assertIsNone(feedback)
        else:
            self.fail(
                f"Unexpected race outcomes reattempt={reattempt_outcome} callback={callback_outcome}"
            )
