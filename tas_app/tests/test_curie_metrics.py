"""Phase 8 operational metrics: trigger, callback, timeout, latency."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from celery.exceptions import Retry
from django.test import TestCase, override_settings
from django.utils import timezone

from tas_app.curie.callback import apply_callback
from tas_app.curie.constants import TIMEOUT_ERROR_DETAIL, TRIGGER_EXHAUSTED_ERROR_DETAIL
from tas_app.curie.delivery import run_deliver_curie_trigger
from tas_app.curie.timeout import persist_timeout_if_due
from tas_app.curie.trigger import RetryableTriggerError, send_trigger
from tas_app.models import CurieReview, Submission
from tas_app.tests.test_curie_phase3 import _error_payload
from tas_app.tests.test_curie_slice import SLICE_SETTINGS, _success_payload, _swot_submission


@override_settings(**SLICE_SETTINGS)
class CurieMetricsTest(TestCase):
    @patch("tas_app.curie.metrics.increment")
    @patch("tas_app.curie.trigger.requests.post")
    def test_trigger_accepted_increments(self, mocked_post, mocked_inc):
        mocked_post.return_value.status_code = 202
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        from tas_app.curie.trigger import build_trigger_payload

        send_trigger(build_trigger_payload(review, submission))
        mocked_inc.assert_any_call("curie.trigger.accepted")

    @patch("tas_app.curie.metrics.increment")
    @patch("tas_app.curie.delivery.send_trigger", side_effect=RetryableTriggerError("HTTP 429"))
    def test_trigger_retried_increments(self, _mocked_send, mocked_inc):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        task = MagicMock()
        task.request.retries = 0
        task.max_retries = 3
        task.retry.side_effect = Retry()
        with self.assertRaises(Retry):
            run_deliver_curie_trigger(task, str(review.trigger_id), "http://lms.example/cb")
        mocked_inc.assert_any_call("curie.trigger.retried")

    @patch("tas_app.curie.metrics.increment")
    @patch("tas_app.curie.delivery.send_trigger", side_effect=RetryableTriggerError("HTTP 500"))
    def test_trigger_exhausted_increments(self, _mocked_send, mocked_inc):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        task = MagicMock()
        task.request.retries = 3
        task.max_retries = 3
        task.retry.side_effect = RetryableTriggerError("HTTP 500")
        run_deliver_curie_trigger(task, str(review.trigger_id), "http://lms.example/cb")
        mocked_inc.assert_any_call("curie.trigger.exhausted")
        review.refresh_from_db()
        self.assertIn(TRIGGER_EXHAUSTED_ERROR_DETAIL, review.error_detail)

    @patch("tas_app.curie.metrics.accumulate")
    @patch("tas_app.curie.metrics.increment")
    def test_callback_outcomes_and_latency(self, mocked_inc, mocked_acc):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        self.assertEqual(apply_callback(review, _success_payload(review)), "applied")
        mocked_inc.assert_any_call("curie.callback.applied")
        self.assertTrue(mocked_acc.called)
        self.assertEqual(mocked_acc.call_args.args[0], "curie.callback.latency_seconds")

        self.assertEqual(apply_callback(review, _success_payload(review)), "replayed")
        mocked_inc.assert_any_call("curie.callback.replayed")

        other = _success_payload(review)
        other["overall_feedback"] = "A different overall comment that still validates."
        self.assertEqual(apply_callback(review, other), "conflict")
        mocked_inc.assert_any_call("curie.callback.conflict")

        stale = _success_payload(review)
        stale["submission_version_number"] = 1
        self.assertEqual(apply_callback(review, stale), "stale")
        mocked_inc.assert_any_call("curie.callback.stale")

    @patch("tas_app.curie.metrics.increment")
    def test_callback_failed_and_superseded(self, mocked_inc):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        self.assertEqual(apply_callback(review, _error_payload(review)), "failed")
        mocked_inc.assert_any_call("curie.callback.failed")

        from tas_app.curie.constants import SOURCE_HUMAN
        from tas_app.tests.test_models import InstructorFeedbackFactory, SubmissionFactory, UserFactory

        late = SubmissionFactory(
            student=UserFactory(),
            template_block=submission.template_block,
            form_data=submission.form_data,
            status=Submission.STATUS_SUBMITTED,
            version_number=2,
        )
        failed = CurieReview.objects.create(
            submission=late,
            submission_version_number=2,
            status=CurieReview.STATUS_FAILED,
            error_detail=TIMEOUT_ERROR_DETAIL,
        )
        InstructorFeedbackFactory(submission=late, source=SOURCE_HUMAN, status="pending")
        self.assertEqual(apply_callback(failed, _success_payload(failed)), "superseded")
        mocked_inc.assert_any_call("curie.callback.superseded")

    @patch("tas_app.curie.metrics.increment")
    def test_timeout_increments_once(self, mocked_inc):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        review = CurieReview.objects.create(submission=submission, submission_version_number=2)
        CurieReview.objects.filter(pk=review.pk).update(
            requested_at=timezone.now() - timedelta(seconds=1801)
        )
        review.refresh_from_db()
        persist_timeout_if_due(review)
        mocked_inc.assert_any_call("curie.timeout")
        mocked_inc.reset_mock()
        review.refresh_from_db()
        persist_timeout_if_due(review)
        mocked_inc.assert_not_called()
