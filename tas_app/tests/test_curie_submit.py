"""Phase 2 atomic submit: form_data, locks, cap, legal source, trigger-on-commit."""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from tas_app.curie.constants import MAX_SUBMISSION_ATTEMPTS, SOURCE_CURIE, SOURCE_HUMAN, STATUS_FAILED
from tas_app.curie.submit import CurieSubmitError, submit_student_submission
from tas_app.models import CurieReview, STATUS_PENDING, Submission, SubmissionVersion
from tas_app.tests.test_curie_slice import SLICE_SETTINGS, _swot_submission
from tas_app.tests.test_models import InstructorFeedbackFactory
from tas_app.views import StudentSubmissionSubmitAPIView


def _post_submit(submission, form_data=None):
    factory = APIRequestFactory()
    payload = {}
    if form_data is not None:
        payload["form_data"] = form_data
    request = factory.post(
        f"/tas/api/v1/student-submission/{submission.pk}/submit/",
        payload,
        format="json",
    )
    force_authenticate(request, user=submission.student)
    with patch("tas_app.curie.submit.generate_submission_pdf"):
        return StudentSubmissionSubmitAPIView.as_view()(request, pk=submission.pk)


@override_settings(**SLICE_SETTINGS)
class CurieAtomicSubmitTest(TestCase):
    @patch("tas_app.curie.celery_tasks.deliver_curie_trigger.delay")
    def test_form_data_is_authoritative_and_creates_pending_review(self, mocked_send):
        submission = _swot_submission(form_data={"goal": "old"})
        new_data = {"goal": "Finish the NPTEL course by March 2027.", "strength": "led the team"}
        with self.captureOnCommitCallbacks(execute=True):
            response = _post_submit(submission, new_data)
        self.assertEqual(response.status_code, 200)
        submission.refresh_from_db()
        self.assertEqual(submission.status, Submission.STATUS_SUBMITTED)
        self.assertEqual(submission.version_number, 2)
        self.assertEqual(submission.form_data["goal"], new_data["goal"])
        review = CurieReview.objects.get(submission=submission)
        self.assertEqual(review.status, CurieReview.STATUS_PENDING_EVALUATION)
        self.assertEqual(review.submission_version_number, 2)
        mocked_send.assert_called_once()
        self.assertEqual(mocked_send.call_args.args, (str(review.trigger_id),))
        from tas_app.curie.trigger import build_trigger_payload

        payload = build_trigger_payload(review, submission)
        self.assertEqual(payload["form_data"]["goal"]["answer"], new_data["goal"])
        self.assertEqual(review.trigger_payload["trigger_id"], str(review.trigger_id))
        self.assertEqual(review.trigger_payload["form_data"]["goal"]["answer"], new_data["goal"])

    def test_approved_cannot_resubmit(self):
        submission = _swot_submission(status=Submission.STATUS_APPROVED, version_number=2)
        CurieReview.objects.create(
            submission=submission,
            submission_version_number=2,
            status=CurieReview.STATUS_READY,
            verdict=CurieReview.VERDICT_ACCEPTED,
        )
        InstructorFeedbackFactory(submission=submission, source=SOURCE_CURIE, status="approved")
        response = _post_submit(submission, {"goal": "try again"})
        self.assertEqual(response.status_code, 409)
        self.assertIn("cannot be resubmitted", response.data["detail"])
        submission.refresh_from_db()
        self.assertEqual(submission.version_number, 2)
        self.assertEqual(CurieReview.objects.filter(submission=submission).count(), 1)

    def test_pending_submit_does_not_allocate_a_second_attempt(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        CurieReview.objects.create(submission=submission, submission_version_number=2)
        response = _post_submit(submission, {"goal": "duplicate"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(CurieReview.objects.filter(submission=submission).count(), 1)
        submission.refresh_from_db()
        self.assertEqual(submission.version_number, 2)

    def test_attempt_cap_returns_409_without_new_review(self):
        submission = _swot_submission(status=Submission.STATUS_REJECTED, version_number=11)
        InstructorFeedbackFactory(submission=submission, source=SOURCE_CURIE, status="rejected")
        for version in range(2, 2 + MAX_SUBMISSION_ATTEMPTS):
            CurieReview.objects.create(
                submission=submission,
                submission_version_number=version,
                status=CurieReview.STATUS_READY,
                verdict=CurieReview.VERDICT_REJECTED,
            )
        response = _post_submit(submission, {"goal": "one more"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["detail"], "Submission attempt cap reached.")
        self.assertEqual(response.data["max_attempts"], MAX_SUBMISSION_ATTEMPTS)
        self.assertEqual(response.data["attempt_count"], MAX_SUBMISSION_ATTEMPTS)
        self.assertEqual(CurieReview.objects.filter(submission=submission).count(), MAX_SUBMISSION_ATTEMPTS)
        submission.refresh_from_db()
        self.assertEqual(submission.version_number, 11)

    def test_failed_reviews_do_not_consume_cap(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        CurieReview.objects.create(
            submission=submission,
            submission_version_number=2,
            status=STATUS_FAILED,
        )
        with patch("tas_app.curie.celery_tasks.deliver_curie_trigger.delay"):
            with self.captureOnCommitCallbacks(execute=True):
                response = _post_submit(submission, {"goal": "retry after failure"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CurieReview.objects.filter(submission=submission).count(), 2)
        submission.refresh_from_db()
        self.assertEqual(submission.version_number, 3)

    def test_human_rejected_cannot_use_curie_submit(self):
        submission = _swot_submission(status=Submission.STATUS_REJECTED, version_number=2)
        InstructorFeedbackFactory(submission=submission, source=SOURCE_HUMAN, status="rejected")
        response = _post_submit(submission, {"goal": "curie path"})
        self.assertEqual(response.status_code, 409)
        self.assertIn("human-graded", response.data["detail"])
        self.assertEqual(CurieReview.objects.filter(submission=submission).count(), 0)

    def test_withdrawn_human_feedback_blocks_curie_submit(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        CurieReview.objects.create(
            submission=submission,
            submission_version_number=2,
            status=STATUS_FAILED,
        )
        InstructorFeedbackFactory(submission=submission, source=SOURCE_HUMAN, status=STATUS_PENDING)
        response = _post_submit(submission, {"goal": "after withdraw"})
        self.assertEqual(response.status_code, 409)
        self.assertIn("human-graded", response.data["detail"])
        self.assertEqual(CurieReview.objects.filter(submission=submission).count(), 1)
        submission.refresh_from_db()
        self.assertEqual(submission.version_number, 2)

    def test_human_owned_draft_cannot_curie_submit(self):
        submission = _swot_submission(status=Submission.STATUS_DRAFT, version_number=3)
        InstructorFeedbackFactory(submission=submission, source=SOURCE_HUMAN, status=STATUS_PENDING)
        response = _post_submit(submission, {"goal": "draft after human reopen"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(CurieReview.objects.filter(submission=submission).count(), 0)

    def test_initial_curie_submit_requires_form_data(self):
        submission = _swot_submission()
        response = _post_submit(submission)
        self.assertEqual(response.status_code, 400)
        self.assertIn("form_data", response.data["detail"])
        submission.refresh_from_db()
        self.assertEqual(submission.status, Submission.STATUS_DRAFT)
        self.assertEqual(CurieReview.objects.count(), 0)

    def test_initial_curie_submit_rejects_non_object_form_data(self):
        submission = _swot_submission()
        factory = APIRequestFactory()
        request = factory.post(
            f"/tas/api/v1/student-submission/{submission.pk}/submit/",
            {"form_data": "not-an-object"},
            format="json",
        )
        force_authenticate(request, user=submission.student)
        with patch("tas_app.curie.submit.generate_submission_pdf"):
            response = StudentSubmissionSubmitAPIView.as_view()(request, pk=submission.pk)
        self.assertEqual(response.status_code, 400)

    def test_reattempt_requires_form_data(self):
        submission = _swot_submission(status=Submission.STATUS_REJECTED, version_number=2)
        InstructorFeedbackFactory(submission=submission, source=SOURCE_CURIE, status="rejected")
        CurieReview.objects.create(
            submission=submission,
            submission_version_number=2,
            status=CurieReview.STATUS_READY,
            verdict=CurieReview.VERDICT_REJECTED,
        )
        response = _post_submit(submission)
        self.assertEqual(response.status_code, 400)
        submission.refresh_from_db()
        self.assertEqual(submission.version_number, 2)

    @override_settings(CURIE_ENABLED=False)
    def test_legacy_path_when_curie_is_off(self):
        submission = _swot_submission()
        with patch("tas_app.curie.celery_tasks.deliver_curie_trigger.delay") as mocked_send:
            response = _post_submit(submission, {"goal": "legacy answers"})
        self.assertEqual(response.status_code, 200)
        submission.refresh_from_db()
        self.assertEqual(submission.status, Submission.STATUS_SUBMITTED)
        self.assertEqual(submission.form_data["goal"], "legacy answers")
        self.assertEqual(CurieReview.objects.count(), 0)
        mocked_send.assert_not_called()

    @override_settings(CURIE_ENABLED=False)
    def test_legacy_path_still_rejects_already_submitted(self):
        submission = _swot_submission(status=Submission.STATUS_SUBMITTED, version_number=2)
        response = _post_submit(submission)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(CurieReview.objects.count(), 0)

    @override_settings(CURIE_ENABLED=False)
    def test_legacy_path_allows_submit_without_form_data(self):
        submission = _swot_submission(form_data={"goal": "already saved"})
        response = _post_submit(submission)
        self.assertEqual(response.status_code, 200)
        submission.refresh_from_db()
        self.assertEqual(submission.form_data["goal"], "already saved")
        self.assertEqual(CurieReview.objects.count(), 0)

    @patch("tas_app.curie.celery_tasks.deliver_curie_trigger.delay")
    def test_success_path_snapshots_form_data_and_pdf(self, mocked_send):
        submission = _swot_submission(form_data={"goal": "old"})
        new_data = {"goal": "Authoritative final answers."}

        def _fake_pdf(sub, dest_field="pdf"):
            getattr(sub, dest_field).save("submit.pdf", ContentFile(b"%PDF-1.4 test"), save=True)

        with patch("tas_app.curie.submit.generate_submission_pdf", side_effect=_fake_pdf):
            with self.captureOnCommitCallbacks(execute=True):
                factory = APIRequestFactory()
                request = factory.post(
                    f"/tas/api/v1/student-submission/{submission.pk}/submit/",
                    {"form_data": new_data},
                    format="json",
                )
                force_authenticate(request, user=submission.student)
                response = StudentSubmissionSubmitAPIView.as_view()(request, pk=submission.pk)
        self.assertEqual(response.status_code, 200)
        submission.refresh_from_db()
        self.assertEqual(submission.version_number, 2)
        self.assertTrue(submission.pdf)
        snapshot = SubmissionVersion.objects.get(submission=submission, version_number=2)
        self.assertEqual(snapshot.form_data, new_data)
        self.assertTrue(snapshot.pdf)
        self.assertEqual(CurieReview.objects.filter(submission=submission).count(), 1)
        mocked_send.assert_called_once()


@override_settings(**SLICE_SETTINGS)
class CurieConcurrentSubmitTest(TransactionTestCase):
    @patch("tas_app.curie.celery_tasks.deliver_curie_trigger.delay")
    def test_trigger_is_not_sent_if_the_transaction_rolls_back(self, mocked_send):
        submission = _swot_submission()
        try:
            with transaction.atomic():
                with patch("tas_app.curie.submit.generate_submission_pdf"):
                    submit_student_submission(
                        pk=submission.pk,
                        student=submission.student,
                        form_data={"goal": "rolled back"},
                    )
                raise RuntimeError("force rollback")
        except RuntimeError:
            pass
        mocked_send.assert_not_called()
        submission.refresh_from_db()
        self.assertEqual(submission.status, Submission.STATUS_DRAFT)
        self.assertEqual(CurieReview.objects.count(), 0)

    def test_concurrent_submits_create_one_attempt_and_review(self):
        if connection.vendor != "mysql":
            self.skipTest("select_for_update concurrency needs MySQL")
        submission = _swot_submission()
        form_data = {"goal": "concurrent"}

        def _one_submit():
            connection.close()
            with patch("tas_app.curie.submit.generate_submission_pdf"):
                with patch("tas_app.curie.celery_tasks.deliver_curie_trigger.delay"):
                    try:
                        submit_student_submission(
                            pk=submission.pk,
                            student=submission.student,
                            form_data=form_data,
                        )
                        return "ok"
                    except CurieSubmitError:
                        return "conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: _one_submit(), range(2)))

        self.assertEqual(sorted(outcomes), ["conflict", "ok"])
        self.assertEqual(CurieReview.objects.filter(submission_id=submission.pk).count(), 1)
        submission.refresh_from_db()
        self.assertEqual(submission.version_number, 2)
        self.assertEqual(submission.status, Submission.STATUS_SUBMITTED)
