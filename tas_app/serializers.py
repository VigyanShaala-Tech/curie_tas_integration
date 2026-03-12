from rest_framework import serializers
from .models import TemplateType, Template


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
