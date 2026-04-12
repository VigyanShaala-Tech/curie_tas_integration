from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey, UsageKey
from rest_framework import serializers

from .models import Submission, Template, TemplateType


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


class StudentSubmissionCreateSerializer(serializers.Serializer):
    """
    Validates payload for creating or updating the current user's Submission
    for a course / XBlock usage key (one row per student per block).
    """

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


class StudentSubmissionResponseSerializer(serializers.ModelSerializer):
    """Serialized Submission returned after a successful create/update."""

    class Meta:
        model = Submission
        fields = [
            "id",
            "course_key",
            "usage_key",
            "form_data",
            "status",
            "version_number",
            "submitted_at",
            "pdf",
        ]
        read_only_fields = [
            "id",
            "course_key",
            "usage_key",
            "form_data",
            "status",
            "version_number",
            "submitted_at",
            "pdf",
        ]
