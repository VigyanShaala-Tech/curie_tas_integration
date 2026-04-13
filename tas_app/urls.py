from django.urls import path
from .views import *

app_name = "tas_app"

urlpatterns = [
    path("api/v1/template-types/", TemplateTypesListView.as_view(), name="template-types-list"),
    path("api/v1/template-types/<int:pk>/", TemplateTypesDetailView.as_view(), name="template-types-detail"),
    path("api/v1/templates/", TemplatesListView.as_view(), name="templates-list"),
    path("api/v1/templates/<int:pk>/", TemplatesDetailView.as_view(), name="templates-detail"),
    path(
        "api/v1/blocks/<path:usage_key>/templates/",
        TemplateBlockDetailView.as_view(),
        name="block-templates",
    ),
    # Create or update the current student's submission (draft / submit)
    path(
        "api/v1/student-submission/",
        StudentSubmissionCreateAPIView.as_view(),
        name="student-submission-create",
    ),
    # Get list of learner submissions for a given UsageKey
    path(
        "api/v1/submissions/<path:usage_key>/",
        LearnerSubmissionsAPIView.as_view(),
        name="submissions",
    ),
    # Get details of a specific learner submission
    path(
        "api/v1/submission-detail/<int:pk>/",
        LearnerSubmissionDetailAPIView.as_view(),
        name="submission-detail",
    ),
    # Get rubrics for a given template
    path(
        "api/v1/rubrics/<path:pk>/",
        RubricsAPIView.as_view(),
    ),
    # Create instructor feedback for a given submission
    path(
        "api/v1/submit-feedback/<int:pk>/",
        InstructorFeedbackAPIView.as_view(),
        name="instructor-feedback",
    ),
]
