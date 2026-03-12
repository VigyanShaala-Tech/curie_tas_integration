from django.urls import path
from .views import *

app_name = "tas_app"

urlpatterns = [
    path("api/v1/template-types/", TemplateTypesListView.as_view(), name="template-types-list"),
    path("api/v1/template-types/<int:pk>/", TemplateTypesDetailView.as_view(), name="template-types-detail"),
    path("api/v1/templates/", TemplatesListView.as_view(), name="templates-list"),
    path("api/v1/templates/<int:pk>/", TemplatesDetailView.as_view(), name="templates-detail"),
]
