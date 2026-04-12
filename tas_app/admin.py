"""
Django admin configuration for tas_app.

This file customizes the Django admin interface for the following models:
- TemplateType
- Template
- TemplateBlock
- Submission
- SubmissionVersion
- InstructorFeedback

Each admin class customizes list display, search fields, filtering, ordering,
and raw field selectors to improve data management for staff users.
"""

from django.contrib import admin
from .models import (
    TemplateType,
    Template,
    TemplateBlock,
    Submission,
    SubmissionVersion,
    InstructorFeedback,
)


# -------------------------------
# Admin configuration for TemplateType model
# -------------------------------
@admin.register(TemplateType)
class TemplateTypeAdmin(admin.ModelAdmin):
    # Fields to display in the admin list view
    list_display = ("name", "slug", "is_active")
    # Enable searching by name and slug
    search_fields = ("name", "slug")
    # Enable filtering by active status
    list_filter = ("is_active",)
    # Default ordering by name
    ordering = ("name",)


# -------------------------------
# Admin configuration for Template model
# -------------------------------
@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    # Fields to display in the list view
    list_display = ("name", "template_type", "is_public", "is_active", "created_by", "created")
    # Enable searching by template name, type name, and creator username
    search_fields = ("name", "template_type__name", "created_by__username")
    # Allow filtering by template type, public status, and active status
    list_filter = ("template_type", "is_public", "is_active")
    # Use raw widget for created_by to optimize user lookup for large datasets
    raw_id_fields = ("created_by",)
    # Show a date hierarchy for efficient navigation
    date_hierarchy = "created"
    # Order by newest first
    ordering = ("-created",)


# -------------------------------
# Admin configuration for TemplateBlock model
# -------------------------------
@admin.register(TemplateBlock)
class TemplateBlockAdmin(admin.ModelAdmin):
    # Fields to display in the list view for better block management
    list_display = ("template", "display_name", "usage_key", "course_key", "sort_order", "assigned_by", "assigned_at")
    # Enable searching by related template name, usage key, and course key
    search_fields = ("template__name", "usage_key", "course_key")
    # Filter by template and course for easy navigation
    list_filter = ("template", "course_key")
    # Use raw_id_fields for related fields to aid in performance
    raw_id_fields = ("template", "assigned_by")
    # Order by assignment time, course, usage, and sort order
    ordering = ("-assigned_at", "course_key", "usage_key", "sort_order")


# -------------------------------
# Admin configuration for Submission model
# -------------------------------
@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    # Main fields for quick review of submission state
    list_display = ("student", "course_key", "usage_key", "status", "version_number", "submitted_at", "created")
    # Enable search by student username, course key, and usage key
    search_fields = ("student__username", "course_key", "usage_key")
    # Filter by submission status and course
    list_filter = ("status", "course_key")
    # Use raw_id_fields for student foreign keys
    raw_id_fields = ("student",)
    # Add date hierarchy for creation time
    date_hierarchy = "created"
    # Order by creation date (descending)
    ordering = ("-created",)


# -------------------------------
# Admin configuration for SubmissionVersion model
# -------------------------------
@admin.register(SubmissionVersion)
class SubmissionVersionAdmin(admin.ModelAdmin):
    # View submission, version, and save time in list display
    list_display = ("submission", "version_number", "saved_at")
    # Enable search by student's username on the related submission
    search_fields = ("submission__student__username",)
    # Use raw id widget for submission field
    raw_id_fields = ("submission",)
    # Date hierarchy for save time
    date_hierarchy = "saved_at"
    # Newest save first
    ordering = ("-saved_at",)


# -------------------------------
# Admin configuration for InstructorFeedback model
# -------------------------------
@admin.register(InstructorFeedback)
class InstructorFeedbackAdmin(admin.ModelAdmin):
    # Display core feedback info (related submission and instructor)
    list_display = (
        "submission",
        "instructor",
        "status",
        "created",
    )
    # Search by student username via submission relation
    search_fields = ("submission__student__username",)
    # Filter feedback entries by status
    list_filter = ("status",)
    # Use raw_id_fields for foreign keys to support big user tables
    raw_id_fields = (
        "submission",
        "instructor",
    )
    # Show newest feedback first
    ordering = ("-created",)
