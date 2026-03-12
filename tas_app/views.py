from rest_framework.views import APIView
from rest_framework.response import Response
from lms.djangoapps.course_api.views import LazyPageNumberPagination
from rest_framework.authentication import SessionAuthentication
from edx_rest_framework_extensions.auth.jwt.authentication import JwtAuthentication
from rest_framework.generics import ListCreateAPIView
from rest_framework import status
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.exceptions import NotFound

from .models import TemplateType, Template
from .serializers import TemplateTypeSerializer, TemplateSerializer


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
        template_type.save()
        return Response(
            {"detail": "TemplateType has been deactivated (soft deleted)."}, status=status.HTTP_204_NO_CONTENT
        )


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
        serializer.save()


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

    permission_classes = [permissions.IsAdminUser]
    authentication_classes = [JwtAuthentication, SessionAuthentication]

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
        serializer = TemplateSerializer(template)
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
        template.save()
        return Response({"detail": "Template has been deactivated (soft deleted)."}, status=status.HTTP_204_NO_CONTENT)
