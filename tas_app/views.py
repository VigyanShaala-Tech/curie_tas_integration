from django.utils import timezone
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from lms.djangoapps.course_api.views import LazyPageNumberPagination
from rest_framework.authentication import SessionAuthentication
from edx_rest_framework_extensions.auth.jwt.authentication import JwtAuthentication
from rest_framework.generics import ListCreateAPIView
from rest_framework import status
from rest_framework import permissions
from rest_framework.exceptions import NotFound

from .models import (
    TemplateType,
    Template,
    TemplateBlock,
    Submission,
    InstructorFeedback,
    STATUS_PENDING,
    STATUS_APPROVED,
    STATUS_REJECTED,
)
from .serializers import (
    InstructorFeedbackUpsertSerializer,
    TemplateTypeSerializer,
    TemplateSerializer,
    StudentSubmissionCreateSerializer,
    StudentSubmissionResponseSerializer,
    StudentSubmissionPatchSerializer,
    StudentSubmissionSubmitSerializer,
    SubmissionVersionSerializer,
    TemplateBlockTemplateItemSerializer,
)


class CustomizedPageNumberPagination(LazyPageNumberPagination):
    """
    Custom paginator for records. Returns 10 records per page.
    """

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 24


class TemplateTypesListView(ListCreateAPIView):
    """
    API view to retrieve list of template types or create a new template type.
    Only accessible to logged-in super admins.

    Endpoint: GET /tas/api/v1/template-types/

    GET:
        - Returns a list of TemplateType records, ordered by name for ease of use.
    POST:
        - Allows creation of new TemplateType.
        - Requires 'name', 'slug', and 'is_active' fields.
    """

    queryset = (
        TemplateType.objects.all().order_by("name").only("id", "name", "slug", "description", "icon", "is_active")
    )
    serializer_class = TemplateTypeSerializer
    permission_classes = [permissions.IsAdminUser]
    pagination_class = CustomizedPageNumberPagination
    authentication_classes = [JwtAuthentication, SessionAuthentication]

    def get_queryset(self):
        """
        Optionally restricts the returned template types,
        by filtering against 'is_active' if passed as a query param.
        """
        queryset = self.queryset
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")
        return queryset

    def perform_create(self, serializer):
        """
        Save the new template type instance. Additional logging or auditing
        could be added here if needed.
        """
        serializer.save()


class TemplateTypesDetailView(APIView):
    """
    API view to retrieve, update, and 'delete' (soft-delete) a template type by id.
    Only accessible to logged-in super admins.

    GET:
        - Returns the detail of a TemplateType record for the given id (pk).
    PATCH:
        - Partially updates the TemplateType.
    DELETE:
        - Soft-deletes the TemplateType (sets is_active=False).
    """

    permission_classes = [permissions.IsAdminUser]
    authentication_classes = [JwtAuthentication, SessionAuthentication]

    def get_object(self, pk):
        try:
            return TemplateType.objects.only("id", "name", "slug", "description", "icon", "is_active").get(pk=pk)
        except TemplateType.DoesNotExist:
            raise NotFound("TemplateType not found.")

    def get(self, request, pk):
        """
        Retrieve the details of the specified TemplateType.
        """
        template_type = self.get_object(pk)
        serializer = TemplateTypeSerializer(template_type)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        """
        Partially update the TemplateType instance.
        """
        template_type = self.get_object(pk)
        serializer = TemplateTypeSerializer(template_type, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        """
        Soft delete: Set is_active to False instead of deleting the object.
        """
        template_type = self.get_object(pk)
        if not template_type.is_active:
            return Response({"detail": "TemplateType is already inactive."}, status=status.HTTP_400_BAD_REQUEST)
        template_type.is_active = False
        template_type.save(update_fields=["is_active", "modified"])
        return Response(status=status.HTTP_200_OK)


class TemplatesListView(ListCreateAPIView):
    """
    API view to retrieve list of templates.
    Only accessible to logged-in super admins.

    Endpoint: GET /tas/api/v1/templates/

    GET:
        - Returns a list of Template records, ordered by name for ease of use.
    """

    queryset = (
        Template.objects.all()
        .order_by("name")
        .only(
            "id",
            "template_type",
            "name",
            "description",
            "image",
            "image_width",
            "image_height",
            "thumbnail",
            "fields",
            "field_positions",
            "is_public",
            "is_active",
        )
    )
    serializer_class = TemplateSerializer
    permission_classes = [permissions.IsAdminUser]
    pagination_class = CustomizedPageNumberPagination
    authentication_classes = [JwtAuthentication, SessionAuthentication]

    def get_queryset(self):
        """
        Optionally restricts the returned template types,
        by filtering against 'is_active' if passed as a query param.
        """
        queryset = self.queryset
        template_type = self.request.query_params.get("template_type")
        if template_type is not None:
            queryset = queryset.filter(template_type=template_type)
        return queryset

    def perform_create(self, serializer):
        """
        Save the new template type instance. Additional logging or auditing
        could be added here if needed.
        """
        serializer.save(created_by=self.request.user)


class TemplatesDetailView(APIView):
    """
    API view to retrieve, update, and 'delete' (soft-delete) a template by id.
    Only accessible to logged-in super admins.

    Endpoint: GET /tas/api/v1/templates/<int:pk>/

    GET:
        - Returns the detail of a Template record for the given id (pk).
    PUT:
        - Full updates the Template.
    PATCH:
        - Partially updates the Template.
    DELETE:
        - Soft-deletes the Template (sets is_active=False).
    """

    authentication_classes = [JwtAuthentication, SessionAuthentication]

    def get_permissions(self):
        # Students can GET a template; only admins can modify/delete
        if self.request.method == 'GET':
            return [permissions.IsAuthenticated()]
        return [permissions.IsAdminUser()]

    def get_object(self, pk):
        try:
            return Template.objects.only(
                "id",
                "template_type",
                "name",
                "description",
                "image",
                "image_width",
                "image_height",
                "thumbnail",
                "fields",
                "field_positions",
                "is_public",
                "is_active",
            ).get(pk=pk)
        except Template.DoesNotExist:
            raise NotFound("Template not found.")

    def get(self, request, pk):
        """
        Retrieve the details of the specified Template.
        """
        template = self.get_object(pk)
        serializer = TemplateSerializer(template, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk):
        """
        Full update the Template instance.
        """
        template = self.get_object(pk)
        serializer = TemplateSerializer(template, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        """
        Partially update the Template instance.
        """
        template = self.get_object(pk)
        serializer = TemplateSerializer(template, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        """
        Soft delete: Set is_active to False instead of deleting the object.
        """
        template = self.get_object(pk)
        if not template.is_active:
            return Response({"detail": "Template is already inactive."}, status=status.HTTP_400_BAD_REQUEST)
        template.is_active = False
        template.save(update_fields=["is_active", "modified"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class TemplateBlockDetailView(APIView):
    """
    API view to retrieve details for a TemplateBlock associated with the given usage_key.

    - Only accessible to authenticated users.
    - Returns the TemplateBlock's usage_key, course_id, and detailed template info.

    Endpoint: GET /tas/api/v1/blocks/<usage_key>/templates/

    Response:
        {
            "usage_key": "<str:usage_key>",
            "course_id": "<str:course_key>",
            "templates": { ... }
        }
    """

    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JwtAuthentication, SessionAuthentication]

    def get(self, request, usage_key):
        """
        Retrieve the details of the TemplateBlock for the specified usage_key.
        - Returns a 404 response if the TemplateBlock does not exist.
        - Serializes the TemplateBlock including its template.
        """
        template_block = get_object_or_404(
            TemplateBlock.objects.select_related("template", "template__template_type"),
            usage_key=usage_key,
        )

        # Serialize the TemplateBlock with embedded template info,
        # and provide the request context for absolute URLs
        templates_data = TemplateBlockTemplateItemSerializer(template_block, context={"request": request}).data

        # Structure the response dictionary
        data = {
            "usage_key": str(template_block.usage_key),
            "course_id": str(template_block.course_key),
            "templates": templates_data,
        }
        return Response(data, status=status.HTTP_200_OK)


class LearnerSubmissionsAPIView(APIView):
    """
    API view for admins to list learner submissions for a given block (usage_key).
    - Accessible only to admin users.
    - Returns paginated list of submission summaries for the specified usage_key.
    """

    permission_classes = [permissions.IsAdminUser]
    authentication_classes = [JwtAuthentication, SessionAuthentication]

    def get(self, request, usage_key):
        """
        GET /api/v1/block/<usage_key>/submissions/
        Returns a paginated list of submissions for the specified block.
        """
        # Use select_related to reduce DB queries when accessing related User and feedback
        submissions_qs = (
            Submission.objects.filter(usage_key=usage_key)
            .select_related("student", "feedback")
            .order_by("-submitted_at")
        )

        # Use custom paginator for paginating results
        paginator = CustomizedPageNumberPagination()
        page = paginator.paginate_queryset(submissions_qs, request)

        # Build the summary response for each submission in the page
        results = []
        for sub in page:
            try:
                feedback_status = sub.feedback.status
            except Exception:
                feedback_status = None
            results.append({
                "id": sub.id,
                "username": sub.student.username,
                "submission_date": sub.submitted_at,
                "status": sub.status,
                "version_number": sub.version_number,
                "feedback_status": feedback_status,
            })

        # Return a paginated response
        return paginator.get_paginated_response(results)


class LearnerSubmissionDetailAPIView(APIView):
    """
    API View to retrieve detailed information about a specific learner's submission.
    - Only accessible by admin users.
    - Returns all relevant fields, including student info, keys, answers, and PDF link.
    """

    # Enforce admin-only permissions and JWT/session authentication
    permission_classes = [permissions.IsAdminUser]
    authentication_classes = [JwtAuthentication, SessionAuthentication]

    def get(self, request, pk):
        """
        GET /api/v1/submissions/<pk>/
        Returns detailed information about the specified submission.

        Response Example:
        {
            "id": 123,
            "username": "student1",
            "course_key": "course-v1:edX+Demo+2024_T1",
            "usage_key": "block-v1:edX+Demo+2024_T1+type@tas+block@abc123",
            "submission_date": "2024-06-07T14:34:56Z",
            "status": "submitted",
            "version": 2,
            "form_data": {...},
            "pdf": "https://.../media/submission/123/file.pdf"
        }
        """
        # Use select_related to optimize query for student (User) object
        try:
            submission = (
                Submission.objects
                .select_related("student", "feedback")
                .get(id=pk)
            )
        except Submission.DoesNotExist:
            return Response({"detail": "Submission not found"}, status=status.HTTP_404_NOT_FOUND)

        # Build absolute PDF URL if a file exists, else None
        pdf_url = request.build_absolute_uri(submission.pdf.url) if submission.pdf else None

        # Include feedback + version history if present (OneToOne: submission.feedback)
        feedback_data = None
        try:
            fb = submission.feedback
            versions = list(
                fb.tas_instructor_feedback_versions
                .order_by("-version_number")
                .values("version_number", "status", "comment", "rubrics", "created")
            )
            feedback_data = {
                "status": fb.status,
                "comment": fb.comment,
                "rubrics": fb.rubrics,
                "versions": versions,
            }
        except Exception:
            pass

        # Include submission version history — only submitted versions (have a PDF)
        version_history = []
        for v in submission.tas_submission_versions.exclude(pdf="").exclude(pdf=None).order_by("-version_number"):
            v_pdf_url = request.build_absolute_uri(v.pdf.url) if v.pdf else None
            version_history.append({
                "version_number": v.version_number,
                "saved_at": v.saved_at,
                "form_data": v.form_data,
                "pdf_url": v_pdf_url,
            })

        # Prepare response payload
        data = {
            "id": submission.id,
            "username": submission.student.username,
            "course_key": str(submission.course_key),
            "usage_key": str(submission.usage_key),
            "submission_date": submission.submitted_at,
            "status": submission.status,
            "version": submission.version_number,
            "form_data": submission.form_data,
            "pdf": pdf_url,
            "feedback": feedback_data,
            "version_history": version_history,
        }

        return Response(data, status=status.HTTP_200_OK)


class RubricsAPIView(APIView):
    """
    API View for instructors/admins to retrieve rubric information for a given TemplateBlock.
    - Only accessible by admin users (course staff, staff, or superusers).
    - Returns the block's display name, instructions, and rubric definitions.

    Endpoint: GET /api/v1/block/<usage_key>/rubrics/

    Response Example:
        {
            "display_name": "Peer Assessment Block",
            "instructions": "Follow these steps ...",
            "rubrics": [{...}, ...]
        }
    """

    # Restrict access to admin users only.
    permission_classes = [permissions.IsAdminUser]
    authentication_classes = [JwtAuthentication, SessionAuthentication]

    def get(self, request, usage_key):
        """
        Retrieve rubrics and metadata for the given TemplateBlock by usage_key.
        Returns 404 if the block does not exist.
        """
        # Use .only() to fetch just the needed fields for optimization
        try:
            block = TemplateBlock.objects.only("display_name", "instructions", "rubrics").get(usage_key=usage_key)
        except TemplateBlock.DoesNotExist:
            return Response(
                {"detail": "Template block with specified usage_key not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        data = {
            "display_name": block.display_name,
            "instructions": block.instructions,
            "rubrics": block.rubrics,
        }

        return Response(data, status=status.HTTP_200_OK)


class InstructorFeedbackAPIView(APIView):
    """
    API View for instructors/admins to submit feedback for a specific learner's submission.

    - Access restricted to admin users (course staff, staff, or superusers).
    - Creates a new InstructorFeedback record or updates an existing one for the given submission.

    Endpoint: POST /api/v1/submissions/<pk>/feedback/

    Sample Request:
        {
            "rubrics": [...],       # (list) Rubric assessment details
            "comment": "",          # (str) Free text instructor comment
            "status": "pending"     # (str, optional) Status for the feedback ("pending", etc.)
        }

    Response:
        {
            "message": "...",
            "created": true         # (bool) True if new feedback was created, False if updated
        }
    """

    # Ensure only admin users can access this view
    permission_classes = [permissions.IsAdminUser]
    authentication_classes = [JwtAuthentication, SessionAuthentication]

    def post(self, request, pk):
        """
        Creates or updates InstructorFeedback for the specified Submission.
        Returns appropriate response if submission does not exist.
        """
        # Validate existence of the referenced Submission
        try:
            submission = Submission.objects.only("id").get(id=pk)
        except Submission.DoesNotExist:
            return Response({"detail": "Submission not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = InstructorFeedbackUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        submission_status = validated_data.get("status", STATUS_PENDING)
        # Use update_or_create for atomic create or update logic
        feedback, created = InstructorFeedback.objects.update_or_create(
            submission=submission,
            defaults={
                "instructor": request.user,
                "rubrics": validated_data.get("rubrics", []),
                "comment": validated_data.get("comment", ""),
                "status": submission_status,
            },
        )
        feedback.create_version_snapshot()
        if submission_status in [STATUS_APPROVED, STATUS_REJECTED]:
            submission.status = submission_status
            submission.save()
        # Return explicit success response with creation status
        return Response(
            {
                "message": "Feedback saved successfully.",
                "created": created,
            },
            status=status.HTTP_200_OK,
        )


class StudentSubmissionCreateAPIView(APIView):
    """
    Create or update the authenticated learner's submission for a TAS XBlock.

    One row per (student, course_key, usage_key). Each save increments ``version_number``.
    After ``status`` is ``submitted``, further edits are rejected (409).

    Endpoint: POST /tas/api/v1/student-submission/

    Expected JSON (or multipart with the same keys plus optional ``pdf`` file):

    - ``template_block_id`` (str): TemplateBlock primary key
    - ``course_key`` (str): Open edX course id string
    - ``usage_key`` (str): XBlock usage key string
    - ``form_data`` (object): field responses
    - ``status`` (optional): ``draft`` (default) or ``submitted``
    - ``pdf`` (optional): uploaded file when using multipart/form-data
    """

    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JwtAuthentication, SessionAuthentication]

    def post(self, request):
        serializer = StudentSubmissionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        template_block = serializer.validated_data["template_block"]
        course_key = serializer.validated_data["course_key"]
        usage_key = serializer.validated_data["usage_key"]
        form_data = serializer.validated_data["form_data"]
        new_status = serializer.validated_data["status"]
        pdf_file = serializer.validated_data.get("pdf")

        submission, created = self._create_or_update_submission(
            request_user=request.user,
            template_block=template_block,
            course_key=course_key,
            usage_key=usage_key,
            form_data=form_data,
            new_status=new_status,
            pdf_file=pdf_file,
        )

        out = StudentSubmissionResponseSerializer(submission, context={"request": request})
        return Response(
            out.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @staticmethod
    def _create_or_update_submission(
        request_user, template_block, course_key, usage_key, form_data, new_status, pdf_file
    ):
        now = timezone.now()

        try:
            with transaction.atomic():
                submission = (
                    Submission.objects.select_for_update()
                    .filter(student=request_user, course_key=course_key, usage_key=usage_key)
                    .first()
                )
                created = submission is None

                if submission and submission.status == Submission.STATUS_SUBMITTED:
                    return submission, False

                if submission:
                    # If submission is rejected/approved, just return it as-is (student is viewing)
                    if submission.status not in (Submission.STATUS_DRAFT,):
                        return submission, False

                    submission.template_block = template_block
                    # Only overwrite form_data if the caller sent real data.
                    # An empty dict means "get existing draft" — preserve saved answers.
                    if form_data:
                        submission.form_data = form_data
                    submission.status = new_status
                    submission.version_number += 1
                    if pdf_file:
                        submission.pdf = pdf_file
                    if new_status == Submission.STATUS_SUBMITTED:
                        submission.submitted_at = now
                    submission.save()
                else:
                    submission = Submission.objects.create(
                        student=request_user,
                        template_block=template_block,
                        course_key=course_key,
                        usage_key=usage_key,
                        form_data=form_data,
                        status=new_status,
                        version_number=1,
                        submitted_at=now if new_status == Submission.STATUS_SUBMITTED else None,
                        pdf=pdf_file if pdf_file else None,
                    )

                submission.create_version_snapshot()
                return submission, created
        except IntegrityError:
            # Retry once in case of race on unique constraint.
            with transaction.atomic():
                submission = Submission.objects.select_for_update().get(
                    student=request_user,
                    course_key=course_key,
                    usage_key=usage_key,
                )
                if submission.status == Submission.STATUS_SUBMITTED:
                    return submission, False
                if submission.status not in (Submission.STATUS_DRAFT,):
                    return submission, False
                submission.template_block = template_block
                if form_data:
                    submission.form_data = form_data
                submission.status = new_status
                submission.version_number += 1
                if pdf_file:
                    submission.pdf = pdf_file
                if new_status == Submission.STATUS_SUBMITTED:
                    submission.submitted_at = now
                submission.save()
                submission.create_version_snapshot()
                return submission, False


class StudentSubmissionDetailAPIView(APIView):
    """
    API View for handling a student's own submission (retrieve and update/draft-save).
    - GET: Retrieve the student's submission by primary key.
    - PATCH: Update submission's form data or PDF, if not submitted/finalized.
    Only the owning student can access their own submission.
    """

    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JwtAuthentication, SessionAuthentication]

    def get_object(self, request, pk):
        """
        Helper to safely fetch a submission belonging to the current user.
        Raises 404 if submission does not exist or does not belong to the user.
        """
        try:
            return Submission.objects.get(pk=pk, student=request.user)
        except Submission.DoesNotExist:
            raise NotFound("Submission not found.")

    def get(self, request, pk):
        """
        GET /student-submission/<pk>/
        Returns the student's submission data in detail.
        """
        submission = self.get_object(request, pk)
        serializer = StudentSubmissionResponseSerializer(submission, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        """
        PATCH /student-submission/<pk>/
        Allows the student to update form_data or PDF if the submission is still in DRAFT status.
        Increments version and stores a new version snapshot.
        Returns 409 if already submitted.
        """
        submission = self.get_object(request, pk)
        if submission.status == Submission.STATUS_SUBMITTED:
            return Response(
                {"detail": "This submission is already finalized and cannot be changed."},
                status=status.HTTP_409_CONFLICT,
            )

        # Validate partial update data (form_data and/or pdf)
        serializer = StudentSubmissionPatchSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        # Apply updates if provided
        if "form_data" in serializer.validated_data:
            submission.form_data = serializer.validated_data["form_data"]
        if "pdf" in serializer.validated_data:
            submission.pdf = serializer.validated_data["pdf"]

        # Increment version, save, and snapshot
        submission.version_number += 1
        submission.status = Submission.STATUS_DRAFT
        submission.save()
        submission.create_version_snapshot()

        try:
            feedback = InstructorFeedback.objects.get(submission=submission)
            feedback.status = STATUS_PENDING
            feedback.save()
        except InstructorFeedback.DoesNotExist:
            pass

        out = StudentSubmissionResponseSerializer(submission, context={"request": request})
        return Response(out.data, status=status.HTTP_200_OK)


class StudentSubmissionSubmitAPIView(APIView):
    """
    API View to submit (finalize) a draft submission.
    - POST: Moves a DRAFT submission to SUBMITTED status, increments version, records submitted_at timestamp.
    """

    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JwtAuthentication, SessionAuthentication]

    def post(self, request, pk):
        """
        POST /student-submission/<pk>/submit/
        Finalizes the student's submission if currently in draft.
        Returns 409 if already submitted.
        """
        try:
            submission = Submission.objects.get(pk=pk, student=request.user)
        except Submission.DoesNotExist:
            raise NotFound("Submission not found.")

        if submission.status == Submission.STATUS_SUBMITTED:
            return Response(
                {"detail": "This submission is already submitted."},
                status=status.HTTP_409_CONFLICT,
            )

        # Finalize submission
        submission.status = Submission.STATUS_SUBMITTED
        submission.version_number += 1
        submission.submitted_at = timezone.now()
        submission.save()

        # Generate PDF before snapshot so pdf is captured in version history
        try:
            from .pdf_generator import generate_submission_pdf
            generate_submission_pdf(submission)
        except Exception as exc:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning("PDF generation failed for submission %s: %s", submission.pk, exc)

        submission.create_version_snapshot(include_pdf=True)

        serializer = StudentSubmissionSubmitSerializer(submission, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class StudentSubmissionVersionsAPIView(APIView):
    """
    API View to list all versions (history) of a student's submission.
    - GET: Returns all version snapshots of the submission in reverse order.
    """

    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JwtAuthentication, SessionAuthentication]

    def get(self, request, pk):
        """
        GET /student-submission/<pk>/versions/
        Retrieves all versioned snapshots for the student's submission, latest first.
        """
        try:
            submission = Submission.objects.get(pk=pk, student=request.user)
        except Submission.DoesNotExist:
            raise NotFound("Submission not found.")

        versions_qs = submission.tas_submission_versions.all().order_by("-version_number")
        serializer = SubmissionVersionSerializer(versions_qs, many=True)
        return Response(
            {
                "submission_id": str(submission.id),
                "versions": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class StudentSubmissionPdfAPIView(APIView):
    """
    API View to get the PDF artifact of a student's submission (if generated).
    - GET: Returns absolute PDF URL if available, else reports generation in progress.
    """

    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JwtAuthentication, SessionAuthentication]

    def get(self, request, pk):
        """
        GET /student-submission/<pk>/pdf/
        Returns: {"pdf_url": <url>} if PDF exists, else {"status": "generating"}
        """
        try:
            submission = Submission.objects.get(pk=pk, student=request.user)
        except Submission.DoesNotExist:
            raise NotFound("Submission not found.")

        if submission.pdf:
            # Build absolute URL for client access
            pdf_url = submission.pdf.url
            absolute_pdf_url = request.build_absolute_uri(pdf_url)
            return Response({"pdf_url": absolute_pdf_url}, status=status.HTTP_200_OK)

        # PDF is not yet available (still generating or not triggered)
        return Response(
            {
                "status": "generating",
                "pdf_url": None,
            },
            status=status.HTTP_202_ACCEPTED,
        )
