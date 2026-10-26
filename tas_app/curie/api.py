"""Learner, instructor, and admin CURIE read endpoints."""

from __future__ import annotations

from django.db import transaction
from rest_framework import permissions, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView
from edx_rest_framework_extensions.auth.jwt.authentication import JwtAuthentication

from tas_app.curie.projection import publish_curie_review
from tas_app.curie.reads import learner_review_payload, resolve_review_for_read, staff_review_payload
from tas_app.models import CurieReview, InstructorFeedback, Submission


def _parse_version(request) -> int | None:
    raw = request.query_params.get("version")
    if raw in (None, ""):
        return None
    try:
        version = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("version must be a positive integer.") from exc
    if version < 1:
        raise ValueError("version must be a positive integer.")
    return version


class StudentCurieReviewAPIView(APIView):
    """GET the current or historical CurieReview for the owning learner."""

    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JwtAuthentication, SessionAuthentication]

    def get(self, request, pk):
        try:
            submission = Submission.objects.prefetch_related("curie_reviews").get(
                pk=pk, student=request.user
            )
        except Submission.DoesNotExist:
            raise NotFound("Submission not found.")

        try:
            version = _parse_version(request)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        review = resolve_review_for_read(submission, version)
        if review is None:
            raise NotFound("CURIE review not found.")
        return Response(learner_review_payload(review), status=status.HTTP_200_OK)


class AdminCurieReviewAPIView(APIView):
    """GET staff diagnostics for a submission's current or historical CurieReview."""

    permission_classes = [permissions.IsAdminUser]
    authentication_classes = [JwtAuthentication, SessionAuthentication]

    def get(self, request, pk):
        try:
            submission = Submission.objects.prefetch_related("curie_reviews").get(pk=pk)
        except Submission.DoesNotExist:
            return Response({"detail": "Submission not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            version = _parse_version(request)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        review = resolve_review_for_read(submission, version)
        if review is None:
            return Response({"detail": "CURIE review not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(staff_review_payload(review), status=status.HTTP_200_OK)

    def post(self, request, pk):
        """Publish the current stored CURIE result unchanged."""
        with transaction.atomic():
            try:
                submission = (
                    Submission.objects.select_for_update()
                    .select_related("template_block__rubric", "feedback")
                    .get(pk=pk)
                )
            except Submission.DoesNotExist:
                return Response(
                    {"detail": "Submission not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            review = (
                CurieReview.objects.select_for_update()
                .filter(
                    submission=submission,
                    submission_version_number=submission.version_number,
                )
                .first()
            )
            if review is None:
                return Response(
                    {"detail": "CURIE review not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            def push_grade_after_publish():
                if review.verdict != CurieReview.VERDICT_ACCEPTED:
                    return
                refreshed = Submission.objects.select_related(
                    "template_block__rubric", "feedback"
                ).get(pk=submission.pk)
                from tas_app.views import _push_submission_grade

                _push_submission_grade(
                    refreshed,
                    refreshed.feedback.rubrics,
                    curie_trigger_id=str(review.trigger_id),
                )

            try:
                source = submission.feedback.source
            except InstructorFeedback.DoesNotExist:
                source = None

            if source == InstructorFeedback.SOURCE_HUMAN:
                return Response(
                    {"detail": "Instructor feedback already owns this submission."},
                    status=status.HTTP_409_CONFLICT,
                )
            if source == InstructorFeedback.SOURCE_CURIE:
                if review.grade_published_at is None:
                    transaction.on_commit(push_grade_after_publish)
                return Response({"status": "published"}, status=status.HTTP_200_OK)
            if review.status != CurieReview.STATUS_READY:
                return Response(
                    {"detail": "CURIE review is not ready to publish."},
                    status=status.HTTP_409_CONFLICT,
                )
            if submission.status != Submission.STATUS_SUBMITTED:
                return Response(
                    {"detail": "Submission is not awaiting review publication."},
                    status=status.HTTP_409_CONFLICT,
                )

            publish_curie_review(
                review,
                submission,
                after_commit=push_grade_after_publish,
            )
        return Response({"status": "published"}, status=status.HTTP_200_OK)
