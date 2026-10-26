"""Manual publication gate for completed CURIE reviews."""

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from tas_app.curie.api import AdminCurieReviewAPIView, StudentCurieReviewAPIView
from tas_app.curie.callback import apply_callback
from tas_app.curie.reads import history_curie_summaries, submission_curie_fields
from tas_app.curie.settings import auto_publish
from tas_app.models import CurieReview, InstructorFeedback, Submission
from tas_app.serializers import StudentSubmissionResponseSerializer, SubmissionVersionSerializer
from tas_app.tests.test_curie_phase3 import _post_human_feedback
from tas_app.tests.test_curie_slice import (
    SLICE_SETTINGS,
    _scores,
    _success_payload,
    _swot_submission,
)
from tas_app.tests.test_models import UserFactory


MANUAL_SETTINGS = {**SLICE_SETTINGS, "CURIE_AUTO_PUBLISH": False}


def _auth(view, user, method, path, pk):
    request = getattr(APIRequestFactory(), method)(path, format="json")
    force_authenticate(request, user=user)
    return view(request, pk=pk)


@override_settings(**MANUAL_SETTINGS)
class CurieManualPublishTest(TestCase):
    def setUp(self):
        self.staff = UserFactory(is_staff=True, is_superuser=True)
        self.submission = _swot_submission(
            status=Submission.STATUS_SUBMITTED,
            version_number=2,
        )
        self.review = CurieReview.objects.create(
            submission=self.submission,
            submission_version_number=2,
        )

    def _store_success(self, payload=None):
        result = apply_callback(self.review, payload or _success_payload(self.review))
        self.review.refresh_from_db()
        self.submission.refresh_from_db()
        return result

    def _publish(self):
        return _auth(
            AdminCurieReviewAPIView.as_view(),
            self.staff,
            "post",
            f"/tas/api/v1/submissions/{self.submission.pk}/curie-review/",
            self.submission.pk,
        )

    def test_setting_disables_automatic_publication(self):
        self.assertFalse(auto_publish())

    def test_callback_stores_ready_review_without_projection_or_grade(self):
        after_success = []
        outcome = apply_callback(
            self.review,
            _success_payload(self.review),
            after_success=lambda review: after_success.append(review.pk),
        )
        self.review.refresh_from_db()
        self.submission.refresh_from_db()

        self.assertEqual(outcome, "held")
        self.assertEqual(self.review.status, CurieReview.STATUS_READY)
        self.assertEqual(self.review.verdict, CurieReview.VERDICT_ACCEPTED)
        self.assertTrue(self.review.publication_held)
        self.assertEqual(self.submission.status, Submission.STATUS_SUBMITTED)
        self.assertFalse(InstructorFeedback.objects.filter(submission=self.submission).exists())
        self.assertIsNone(self.review.grade_published_at)
        self.assertEqual(after_success, [])

    def test_learner_sees_pending_without_private_feedback(self):
        self._store_success()
        response = _auth(
            StudentCurieReviewAPIView.as_view(),
            self.submission.student,
            "get",
            f"/tas/api/v1/student-submission/{self.submission.pk}/curie-review/",
            self.submission.pk,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], CurieReview.STATUS_PENDING_EVALUATION)
        self.assertTrue(response.data["awaiting_instructor_approval"])
        self.assertIsNone(response.data["verdict"])
        self.assertEqual(response.data["overall_feedback"], "")
        self.assertEqual(response.data["field_feedback"], [])
        self.assertIsNone(response.data["star_rating"])
        self.assertTrue(submission_curie_fields(self.submission)["awaiting_instructor_approval"])
        summaries = history_curie_summaries(self.submission)
        self.assertTrue(summaries[2]["awaiting_instructor_approval"])
        self.assertTrue(
            StudentSubmissionResponseSerializer(self.submission).data[
                "awaiting_instructor_approval"
            ]
        )
        self.submission.create_version_snapshot()
        version = self.submission.tas_submission_versions.get(version_number=2)
        self.assertTrue(
            SubmissionVersionSerializer(
                version,
                context={"curie_summaries": summaries},
            ).data["awaiting_instructor_approval"]
        )

    def test_staff_sees_ready_review_and_approval_state(self):
        self._store_success()
        response = _auth(
            AdminCurieReviewAPIView.as_view(),
            self.staff,
            "get",
            f"/tas/api/v1/submissions/{self.submission.pk}/curie-review/",
            self.submission.pk,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], CurieReview.STATUS_READY)
        self.assertTrue(response.data["awaiting_instructor_approval"])
        self.assertEqual(response.data["verdict"], CurieReview.VERDICT_ACCEPTED)
        self.assertTrue(response.data["field_feedback"])

    def test_publish_accepted_review_creates_curie_projection_and_queues_grade(self):
        self._store_success()
        with patch("tas_app.views._push_submission_grade") as push_grade:
            with patch(
                "tas_app.curie.projection.transaction.on_commit",
                side_effect=lambda callback: callback(),
            ):
                response = self._publish()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "published")
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, Submission.STATUS_APPROVED)
        self.assertEqual(self.submission.feedback.source, InstructorFeedback.SOURCE_CURIE)
        self.assertEqual(self.submission.feedback.status, "approved")
        push_grade.assert_called_once()
        self.review.refresh_from_db()
        self.assertFalse(self.review.publication_held)

    def test_publish_rejected_review_creates_projection_without_grade(self):
        payload = _success_payload(self.review)
        payload["gate_criterion_scores"] = _scores((5, 5, 4))
        self._store_success(payload)
        with patch("tas_app.views._push_submission_grade") as push_grade:
            with patch(
                "tas_app.curie.projection.transaction.on_commit",
                side_effect=lambda callback: callback(),
            ):
                response = self._publish()

        self.assertEqual(response.status_code, 200)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, Submission.STATUS_REJECTED)
        self.assertEqual(self.submission.feedback.source, InstructorFeedback.SOURCE_CURIE)
        push_grade.assert_not_called()

    def test_publish_is_idempotent(self):
        self._store_success()
        with patch("tas_app.views.push_grade_to_lms.delay"):
            with self.captureOnCommitCallbacks(execute=True):
                first = self._publish()
            second = self._publish()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            InstructorFeedback.objects.filter(submission=self.submission).count(),
            1,
        )

    def test_publish_replay_requeues_only_a_missing_accepted_grade(self):
        self._store_success()
        with patch("tas_app.views._push_submission_grade"):
            with patch(
                "tas_app.curie.projection.transaction.on_commit",
                side_effect=lambda callback: callback(),
            ):
                self._publish()

        with patch("tas_app.views._push_submission_grade") as push_grade:
            with patch(
                "tas_app.curie.api.transaction.on_commit",
                side_effect=lambda callback: callback(),
            ):
                response = self._publish()
        self.assertEqual(response.status_code, 200)
        push_grade.assert_called_once()

        CurieReview.objects.filter(pk=self.review.pk).update(
            grade_published_at=timezone.now()
        )
        with patch("tas_app.views._push_submission_grade") as push_grade:
            response = self._publish()
        self.assertEqual(response.status_code, 200)
        push_grade.assert_not_called()

    def test_human_override_blocks_later_curie_publication(self):
        self._store_success()
        response = _post_human_feedback(
            self.submission,
            self.staff,
            {
                "status": "rejected",
                "comment": "Instructor override.",
                "rubrics": [],
            },
        )
        self.assertEqual(response.status_code, 200)

        publish_response = self._publish()
        self.assertEqual(publish_response.status_code, 409)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, Submission.STATUS_REJECTED)
        self.assertEqual(self.submission.feedback.source, InstructorFeedback.SOURCE_HUMAN)

    def test_switching_auto_publish_on_does_not_release_a_held_review(self):
        payload = _success_payload(self.review)
        self.assertEqual(self._store_success(payload), "held")

        with override_settings(CURIE_AUTO_PUBLISH=True):
            self.assertEqual(apply_callback(self.review, payload), "replayed")

        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, Submission.STATUS_SUBMITTED)
        self.assertFalse(InstructorFeedback.objects.filter(submission=self.submission).exists())


class CurieAutoPublishDefaultTest(TestCase):
    def test_auto_publish_defaults_to_true(self):
        with override_settings():
            self.assertTrue(auto_publish())
