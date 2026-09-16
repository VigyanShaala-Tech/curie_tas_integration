from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey, UsageKey
from rest_framework import serializers

from .models import (
    CurieReview,
    InstructorFeedback,
    Rubric,
    Submission,
    Template,
    TemplateType,
    TemplateBlock,
    STATUS_CHOICES,
)


class TemplateTypeSerializer(serializers.ModelSerializer):
    """Serializer for TemplateType model."""

    class Meta:
        model = TemplateType
        fields = ["id", "name", "slug", "description", "icon", "is_active"]
        read_only_fields = ["id"]


class TemplateSerializer(serializers.ModelSerializer):
    """Serializer for Template model."""

    class Meta:
        model = Template
        fields = [
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
        ]
        read_only_fields = ["id"]


class RubricSerializer(serializers.ModelSerializer):
    """Serializer for Rubric model."""

    class Meta:
        model = Rubric
        fields = ["id", "name", "criteria", "is_active"]
        read_only_fields = ["id"]


class StudentSubmissionCreateSerializer(serializers.Serializer):
    """
    Validates payload for creating or updating the current user's Submission
    for a course / XBlock usage key (one row per student per block).
    """

    template_block_id = serializers.IntegerField()
    course_key = serializers.CharField()
    usage_key = serializers.CharField()
    form_data = serializers.JSONField()
    status = serializers.ChoiceField(choices=Submission.STATUS_CHOICES, default=Submission.STATUS_DRAFT)
    pdf = serializers.FileField(required=False, allow_null=True)

    def validate_course_key(self, value):
        try:
            return CourseKey.from_string(value.strip())
        except InvalidKeyError as exc:
            raise serializers.ValidationError("Invalid course_key.") from exc

    def validate_usage_key(self, value):
        try:
            return UsageKey.from_string(value.strip())
        except InvalidKeyError as exc:
            raise serializers.ValidationError("Invalid usage_key.") from exc

    def validate(self, attrs):
        template_block_id = attrs.get("template_block_id")
        course_key = attrs.get("course_key")
        usage_key = attrs.get("usage_key")

        try:
            template_block = TemplateBlock.objects.select_related("template__template_type").get(
                pk=template_block_id
            )
        except (TemplateBlock.DoesNotExist, ValueError, TypeError) as exc:
            raise serializers.ValidationError({"template_block_id": "Invalid template_block_id."}) from exc

        if template_block.course_key != course_key:
            raise serializers.ValidationError(
                {"course_key": "course_key does not match the provided template_block_id."}
            )

        if template_block.usage_key != usage_key:
            raise serializers.ValidationError({"usage_key": "usage_key does not match the provided template_block_id."})

        attrs["template_block"] = template_block
        return attrs


class StudentSubmissionResponseSerializer(serializers.ModelSerializer):
    """Serialized Submission returned after a successful create/update."""

    template_block_id = serializers.SerializerMethodField()
    student_id = serializers.SerializerMethodField()
    course_id = serializers.SerializerMethodField()
    pdf_url = serializers.SerializerMethodField()
    feedback = serializers.SerializerMethodField()
    curie_review_status = serializers.SerializerMethodField()
    is_slow_pending = serializers.SerializerMethodField()
    submission_attempt_count = serializers.SerializerMethodField()
    at_max_attempts = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(source="created", read_only=True)
    updated_at = serializers.DateTimeField(source="modified", read_only=True)

    class Meta:
        model = Submission
        fields = [
            "id",
            "template_block_id",
            "student_id",
            "course_id",
            "usage_key",
            "form_data",
            "status",
            "version_number",
            "submitted_at",
            "pdf_url",
            "feedback",
            "curie_review_status",
            "is_slow_pending",
            "submission_attempt_count",
            "at_max_attempts",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_template_block_id(self, obj):
        return str(obj.template_block_id) if obj.template_block_id else ""

    def get_student_id(self, obj):
        return obj.student.username if obj.student_id else ""

    def get_course_id(self, obj):
        return str(obj.course_key)

    def get_pdf_url(self, obj):
        if not obj.pdf:
            return ""
        request = self.context.get("request")
        pdf_url = obj.pdf.url
        return request.build_absolute_uri(pdf_url) if request else pdf_url

    def get_feedback(self, obj):
        try:
            fb = obj.feedback
        except InstructorFeedback.DoesNotExist:
            return None

        payload = {
            "status": fb.status,
            "comment": fb.comment,
            "source": fb.source,
        }
        if fb.source != InstructorFeedback.SOURCE_CURIE:
            payload["rubrics"] = fb.rubrics
            return payload

        from tas_app.curie.reads import learner_field_entries, reviews_for

        payload["rubrics"] = []
        reviews = reviews_for(obj)
        review = next(
            (
                item
                for item in reviews
                if item.submission_version_number == obj.version_number
                and item.status == CurieReview.STATUS_READY
            ),
            None,
        )
        if review is None:
            review = next(
                (item for item in reviews if item.status == CurieReview.STATUS_READY),
                None,
            )
        if review is not None:
            payload["field_feedback"] = learner_field_entries(review.field_feedback)
            payload["verdict"] = review.verdict
        return payload

    def get_curie_review_status(self, obj):
        return self._curie_fields(obj)["curie_review_status"]

    def get_is_slow_pending(self, obj):
        return self._curie_fields(obj)["is_slow_pending"]

    def get_submission_attempt_count(self, obj):
        return self._curie_fields(obj)["submission_attempt_count"]

    def get_at_max_attempts(self, obj):
        return self._curie_fields(obj)["at_max_attempts"]

    def _curie_fields(self, obj):
        cached = getattr(obj, "_curie_read_fields", None)
        if cached is None:
            from tas_app.curie.reads import submission_curie_fields

            cached = submission_curie_fields(obj)
            obj._curie_read_fields = cached
        return cached


class StudentSubmissionPatchSerializer(serializers.Serializer):
    """
    PATCH body for student submissions.

    Branches:
      - { "action": "reopen" } — reopen a rejected submission to draft (no form write)
      - { "form_data" and/or "pdf" } — save draft content (existing behavior)
    """

    action = serializers.ChoiceField(choices=["reopen"], required=False)
    form_data = serializers.JSONField(required=False)
    pdf = serializers.FileField(required=False, allow_null=True)

    def validate(self, attrs):
        action = attrs.get("action")
        has_content = "form_data" in attrs or "pdf" in attrs

        if action == "reopen":
            if has_content:
                raise serializers.ValidationError(
                    "Reopen cannot include form_data or pdf. Send only {\"action\": \"reopen\"}."
                )
            return attrs

        if not has_content:
            raise serializers.ValidationError(
                "Provide form_data and/or pdf, or {\"action\": \"reopen\"}."
            )
        return attrs


class StudentSubmissionSubmitSerializer(serializers.ModelSerializer):
    pdf_url = serializers.SerializerMethodField()

    class Meta:
        model = Submission
        fields = ["id", "status", "version_number", "submitted_at", "pdf_url"]
        read_only_fields = fields

    def get_pdf_url(self, obj):
        if not obj.pdf:
            return None
        request = self.context.get("request")
        pdf_url = obj.pdf.url
        return request.build_absolute_uri(pdf_url) if request else pdf_url


class SubmissionVersionSerializer(serializers.Serializer):
    """
    Student-facing submitted version history entry.

    Includes linked instructor feedback when a real FK relationship exists.
    Does not expose rubric scores/marks.
    """

    version_number = serializers.IntegerField()
    submitted_at = serializers.DateTimeField(source="saved_at")
    feedback_available = serializers.SerializerMethodField()
    feedback_unavailable_reason = serializers.SerializerMethodField()
    feedback_status = serializers.SerializerMethodField()
    instructor_comment = serializers.SerializerMethodField()
    pdf_url = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    attempt_number = serializers.SerializerMethodField()
    curie_review_status = serializers.SerializerMethodField()
    feedback_source = serializers.SerializerMethodField()
    verdict = serializers.SerializerMethodField()
    star_rating = serializers.SerializerMethodField()
    # Legacy fields retained for backward compatibility with existing clients.
    form_data = serializers.JSONField()
    saved_at = serializers.DateTimeField()

    def _latest_linked_feedback(self, obj):
        if hasattr(obj, "_cached_latest_linked_feedback"):
            return obj._cached_latest_linked_feedback
        prefetched = getattr(obj, "_prefetched_objects_cache", {}).get("feedback_versions")
        if prefetched is not None:
            linked = prefetched[0] if prefetched else None
        else:
            linked = next(iter(obj.feedback_versions.all()), None)
        obj._cached_latest_linked_feedback = linked
        return linked

    def get_feedback_available(self, obj):
        return self._latest_linked_feedback(obj) is not None

    def get_feedback_unavailable_reason(self, obj):
        if self._latest_linked_feedback(obj) is not None:
            return None
        current_version = self.context.get("current_version_number")
        if current_version is not None and obj.version_number == current_version:
            return "pending"
        return "unlinked_historical"

    def get_feedback_status(self, obj):
        linked = self._latest_linked_feedback(obj)
        return linked.status if linked else None

    def get_instructor_comment(self, obj):
        linked = self._latest_linked_feedback(obj)
        return linked.comment if linked else ""

    def _absolute_pdf_url(self, obj):
        if not obj.pdf:
            return None
        request = self.context.get("request")
        pdf_url = obj.pdf.url
        return request.build_absolute_uri(pdf_url) if request else pdf_url

    def get_pdf_url(self, obj):
        return self._absolute_pdf_url(obj)

    def get_download_url(self, obj):
        return self._absolute_pdf_url(obj)

    def _curie_summary(self, obj):
        return (self.context.get("curie_summaries") or {}).get(obj.version_number) or {}

    def get_attempt_number(self, obj):
        return (self.context.get("attempt_by_version") or {}).get(obj.version_number)

    def get_curie_review_status(self, obj):
        return self._curie_summary(obj).get("status")

    def get_feedback_source(self, obj):
        linked = self._latest_linked_feedback(obj)
        if linked is None:
            return None
        if linked.instructor_id is not None:
            return InstructorFeedback.SOURCE_HUMAN
        if self._curie_summary(obj):
            return InstructorFeedback.SOURCE_CURIE
        return InstructorFeedback.SOURCE_HUMAN

    def get_verdict(self, obj):
        return self._curie_summary(obj).get("verdict")

    def get_star_rating(self, obj):
        return self._curie_summary(obj).get("star_rating")


class TemplateTypeBasicSerializer(serializers.ModelSerializer):
    """
    Basic serializer for TemplateType model.
    Serializes only the 'slug' and 'name' fields for concise, nested usage.
    """

    class Meta:
        model = TemplateType
        fields = ["slug", "name"]


class TemplateBasicSerializer(serializers.ModelSerializer):
    """
    Basic serializer for the Template model, appropriate for nested use or lists.
    - Embeds a simplified TemplateType.
    - Adds computed absolute thumbnail URL if a thumbnail exists.
    """

    template_type = TemplateTypeBasicSerializer(read_only=True)
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = Template
        fields = ["id", "name", "template_type", "thumbnail_url", "image_width", "image_height"]

    def get_thumbnail_url(self, obj):
        """
        Returns the absolute thumbnail URL if available, else None.
        Uses request context to make the URL absolute.
        """
        if not obj.thumbnail:
            return None
        request = self.context.get("request")
        thumbnail_url = obj.thumbnail.url
        return request.build_absolute_uri(thumbnail_url) if request else thumbnail_url


class TemplateBlockTemplateItemSerializer(serializers.ModelSerializer):
    """
    Serializer for TemplateBlock with embedded template detail.
    - Returns the block's primary key as a string for frontend safety.
    - Includes 'sort_order' to handle block ordering.
    - Embeds the basic template info.
    """

    template_block_id = serializers.SerializerMethodField()
    template = TemplateBasicSerializer(read_only=True)

    class Meta:
        model = TemplateBlock
        fields = ["template_block_id", "sort_order", "template"]

    def get_template_block_id(self, obj):
        """
        Returns the TemplateBlock primary key (id) as a string.
        """
        return str(obj.id)


class InstructorFeedbackUpsertSerializer(serializers.Serializer):
    """Validate instructor feedback payload for create/update operations."""

    rubrics = serializers.JSONField(required=False)
    comment = serializers.CharField(required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=STATUS_CHOICES, required=False)

    def validate_rubrics(self, value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError("rubrics must be a list.")
        return value


class FeedbackOptionSerializer(serializers.Serializer):
    """A single predefined feedback comment option."""

    id = serializers.CharField(max_length=64)
    label = serializers.CharField(max_length=2000)


class CategoryFeedbackConfigSerializer(serializers.Serializer):
    """Predefined feedback options for one rubric category."""

    category_id = serializers.CharField(max_length=255)
    options = FeedbackOptionSerializer(many=True)


class BlockFeedbackOptionsSerializer(serializers.Serializer):
    """Payload for reading/writing per-block predefined feedback options."""

    categories = CategoryFeedbackConfigSerializer(many=True)

    def validate_categories(self, value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError("categories must be a list.")
        return value
