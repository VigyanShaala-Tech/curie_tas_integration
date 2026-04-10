from django.urls import path
from .views import *

app_name = "tas_app"

urlpatterns = [
    path("api/v1/template-types/", TemplateTypesListView.as_view(), name="template-types-list"),
    path("api/v1/template-types/<int:pk>/", TemplateTypesDetailView.as_view(), name="template-types-detail"),
    path("api/v1/templates/", TemplatesListView.as_view(), name="templates-list"),
    path("api/v1/templates/<int:pk>/", TemplatesDetailView.as_view(), name="templates-detail"),

    path("api/v1/learner-submissions/<path:pk>/", LearnerSubmissionsAPIView.as_view(), name="learner-submissions",),
    path("api/v1/learner-submission-detail/<int:pk>/", LearnerSubmissionDetailAPIView.as_view(), name="learner-submission-detail",),
    path("api/v1/rubrics/<path:pk>/", RubricsAPIView.as_view(),),
    path("api/v1/instructor-feedback/<int:pk>/", InstructorFeedbackAPIView.as_view(), name="instructor-feedback",),
]