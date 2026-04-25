from django.urls import path
from .views import (
    InstructorFeedbackAPIView,
    LearnerSubmissionDetailAPIView,
    LearnerSubmissionsAPIView,
    RubricsAPIView,
    RubricsDetailView,
    RubricsListView,
    StudentSubmissionCreateAPIView,
    StudentSubmissionDetailAPIView,
    StudentSubmissionPdfAPIView,
    StudentSubmissionSubmitAPIView,
    StudentSubmissionVersionsAPIView,
    TemplateBlockDetailView,
    TemplateTypesDetailView,
    TemplateTypesListView,
    TemplatesDetailView,
    TemplatesListView,
)

app_name = "tas_app"

urlpatterns = [
    path("api/v1/template-types/", TemplateTypesListView.as_view(), name="template-types-list"),
    path("api/v1/template-types/<int:pk>/", TemplateTypesDetailView.as_view(), name="template-types-detail"),
    path("api/v1/templates/", TemplatesListView.as_view(), name="templates-list"),
    path("api/v1/templates/<int:pk>/", TemplatesDetailView.as_view(), name="templates-detail"),
    path("api/v1/rubrics/", RubricsListView.as_view(), name="rubrics-list"),
    path("api/v1/rubrics/<int:pk>/", RubricsDetailView.as_view(), name="rubrics-detail"),
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
    path(
        "api/v1/student-submission/<int:pk>/",
        StudentSubmissionDetailAPIView.as_view(),
        name="student-submission-detail",
    ),
    path(
        "api/v1/student-submission/<int:pk>/submit/",
        StudentSubmissionSubmitAPIView.as_view(),
        name="student-submission-submit",
    ),
    path(
        "api/v1/student-submission/<int:pk>/pdf/",
        StudentSubmissionPdfAPIView.as_view(),
        name="student-submission-pdf",
    ),
    path(
        "api/v1/student-submission/<int:pk>/versions/",
        StudentSubmissionVersionsAPIView.as_view(),
        name="student-submission-versions",
    ),
    # Instructor: List ALL submissions for a given usage_key (block)
    path(
        "api/v1/block/<path:usage_key>/submissions/",
        LearnerSubmissionsAPIView.as_view(),
        name="block-submissions-list",
    ),
    # Instructor: Retrieve details of a specific learner submission (for assessment)
    path(
        "api/v1/submissions/<int:pk>/",
        LearnerSubmissionDetailAPIView.as_view(),
        name="submission-detail",
    ),
    # Instructor: Get rubrics for a given template block (pk is TemplateBlock id)
    path(
        "api/v1/block/<path:usage_key>/rubrics/",
        RubricsAPIView.as_view(),
        name="block-rubrics",
    ),
    # Instructor: Submit feedback for a specific learner submission (assess + feedback)
    path(
        "api/v1/submissions/<int:pk>/feedback/",
        InstructorFeedbackAPIView.as_view(),
        name="submission-feedback",
    ),
]
