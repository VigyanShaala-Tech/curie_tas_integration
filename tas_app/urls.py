from django.urls import path
from .views import TemplateTypesListView, TemplateTypesDetailView

app_name = "tas_app"

urlpatterns = [
    path("api/v1/template-types/", TemplateTypesListView.as_view(), name="template-types-list"),
    path("api/v1/template-types/<int:pk>/", TemplateTypesDetailView.as_view(), name="template-types-detail"),
]
