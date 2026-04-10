from django.contrib import admin
from .models import (
    TemplateType,
    Template,
    TemplateBlock,
    Submission,
    SubmissionVersion,
    InstructorFeedback,
)


@admin.register(TemplateType)
class TemplateTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active")
    search_fields = ("name", "slug")
    list_filter = ("is_active",)
    ordering = ("name",)


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "template_type", "is_public", "is_active", "created_by", "created")
    search_fields = ("name", "template_type__name", "created_by__username")
    list_filter = ("template_type", "is_public", "is_active")
    raw_id_fields = ("created_by",)
    date_hierarchy = "created"
    ordering = ("-created",)


@admin.register(TemplateBlock)
class TemplateBlockAdmin(admin.ModelAdmin):
    list_display = ("template", "display_name", "usage_key", "course_key", "sort_order", "assigned_by", "assigned_at")
    search_fields = ("template__name", "usage_key", "course_key")
    list_filter = ("template", "course_key")
    raw_id_fields = ("template", "assigned_by")
    ordering = ("-assigned_at","course_key", "usage_key", "sort_order")


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("student", "course_key", "usage_key", "status", "version_number", "submitted_at", "created")
    search_fields = ("student__username", "course_key", "usage_key")
    list_filter = ("status", "course_key")
    raw_id_fields = ("student",)
    date_hierarchy = "created"
    ordering = ("-created",)


@admin.register(SubmissionVersion)
class SubmissionVersionAdmin(admin.ModelAdmin):
    list_display = ("submission", "version_number", "saved_at")
    search_fields = ("submission__student__username",)
    raw_id_fields = ("submission",)
    date_hierarchy = "saved_at"
    ordering = ("-saved_at",)

@admin.register(InstructorFeedback)
class InstructorFeedbackAdmin(admin.ModelAdmin):

    list_display = ("submission", "instructor", "status", "created",)
    search_fields = ("submission__student__username",)
    list_filter = ("status",)
    raw_id_fields = ("submission", "instructor",)
    ordering = ("-created",)