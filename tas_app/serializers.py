from rest_framework import serializers
from .models import TemplateType


class TemplateTypeSerializer(serializers.ModelSerializer):
    """Serializer for TemplateType model."""

    class Meta:
        model = TemplateType
        fields = ["id", "name", "slug", "description", "icon", "is_active"]
        read_only_fields = ["id"]
