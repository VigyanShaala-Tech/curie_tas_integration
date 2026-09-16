"""Learner, instructor, and admin CURIE read endpoints."""

from __future__ import annotations

from rest_framework import permissions, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView
from edx_rest_framework_extensions.auth.jwt.authentication import JwtAuthentication

from tas_app.curie.reads import learner_review_payload, resolve_review_for_read, staff_review_payload
from tas_app.models import Submission


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
