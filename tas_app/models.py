from django.db import models
from django.contrib.auth.models import User
from model_utils.models import TimeStampedModel
from opaque_keys.edx.django.models import CourseKeyField, UsageKeyField


STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_CHOICES = [
    (STATUS_PENDING, "Pending"),
    (STATUS_APPROVED, "Approved"),
    (STATUS_REJECTED, "Rejected"),
]


class TemplateType(TimeStampedModel):
    """
    Stores different categories for assignment templates within TAS.

    Examples:
        - Case Study
        - Essay
        - Coding Assignment
    """

    name = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Short, human-readable name of the template type (e.g., 'Case Study').",
    )
    slug = models.SlugField(
        max_length=75,
        unique=True,
        db_index=True,
        help_text="Short unique identifier for referencing the template type (e.g., 'essay').",
    )
    description = models.TextField(blank=True, default="", help_text="Extended description of the template type.")
    icon = models.ImageField(
        upload_to="tas/templates/icons/",
        null=True,
        blank=True,
        help_text="Small icon displayed in UI for this template type.",
    )
    is_active = models.BooleanField(
        default=True, help_text="Set False to disable this template type everywhere it is referenced."
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Template Type"
        verbose_name_plural = "Template Types"

    def __str__(self):
        return f"{self.name}" if self.name else f"TemplateType-{self.pk}"


class Template(TimeStampedModel):
    """
    Represents a complete assignment template within TAS.

    Holds information about background image, the associated template type,
    form fields, and layout metadata.
    """

    template_type = models.ForeignKey(
        TemplateType,
        on_delete=models.CASCADE,
        related_name="templates",
        db_index=True,
        help_text="The type/category this template belongs to.",
    )
    name = models.CharField(
        max_length=255, db_index=True, help_text="Template display name (should be unique per template type)."
    )
    description = models.TextField(blank=True, default="", help_text="Optional description of the template.")
    image = models.ImageField(
        upload_to="tas/templates/images/", null=True, blank=True, help_text="Background image for the template."
    )
    image_width = models.PositiveIntegerField(help_text="Pixel width of the background image used.")
    image_height = models.PositiveIntegerField(help_text="Pixel height of the background image used.")
    thumbnail = models.ImageField(
        upload_to="tas/templates/thumbnails/", null=True, blank=True, help_text="Thumbnail image for the template."
    )
    fields = models.JSONField(
        default=list,
        help_text="Serialized definition of dynamic form fields tied to this template. Each entry is a dict with field attributes.",
    )
    field_positions = models.JSONField(
        default=dict, help_text="Map of field keys to their layout positions on the template image."
    )
    is_public = models.BooleanField(
        default=False,
        db_index=True,
        help_text="When True, template is available to all users (otherwise permission-based).",
    )
    is_active = models.BooleanField(
        default=True, db_index=True, help_text="Inactive templates are hidden from user-facing views."
    )
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_templates",
        help_text="User who created/owns the template.",
    )

    class Meta:
        ordering = ["-created"]
        verbose_name = "TAS Template"
        verbose_name_plural = "TAS Templates"
        indexes = [
            models.Index(fields=["template_type", "is_public", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} (Type: {self.template_type.name})"

    def active_fields(self):
        """
        Returns only enabled fields from the 'fields' JSON.
        """
        return [field for field in self.fields if field.get("active", True)]

    @property
    def image_aspect_ratio(self):
        if self.image_height:
            return self.image_width / self.image_height
        return None


class Rubric(TimeStampedModel):
    """
    Stores a reusable rubric definition that can be referenced when configuring
    TemplateBlock assignments.

    - name: human-readable label for the rubric.
    - criteria: structured list of criterion objects (name, options, marks, etc.).
    - is_active: soft-delete flag; inactive rubrics are hidden from user-facing views.
    """

    name = models.TextField(
        db_index=True,
        help_text="Human-readable name of the rubric (e.g., 'Essay Rubric').",
    )
    criteria = models.JSONField(
        default=list,
        help_text="Structured list of rubric criteria. Each entry defines a criterion name, options, and marks.",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Set False to deactivate this rubric without deleting it.",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Rubric"
        verbose_name_plural = "Rubrics"

    def __str__(self):
        return self.name if self.name else f"Rubric-{self.pk}"


class TemplateBlock(TimeStampedModel):
    """
    Represents the assignment configuration for a single Open edX unit.

    A unit (usage_key + course_key) maps to exactly one TemplateBlock, which
    references a template and stores instructor-visible metadata (rubrics,
    instructions, display_name, ordering).
    """

    template = models.ForeignKey(
        Template,
        on_delete=models.CASCADE,
        related_name="template_blocks",
        db_index=True,
        help_text="Reference to the TAS template used in this block.",
    )
    usage_key = UsageKeyField(
        max_length=255, db_index=True, help_text="Opaque key identifying the Open edX XBlock unit."
    )
    course_key = CourseKeyField(max_length=255, db_index=True, help_text="Opaque key identifying the Open edX course.")
    display_name = models.CharField(max_length=255, default="Template Based Assignment")
    instructions = models.TextField(blank=True, default="")
    rubric = models.ForeignKey(
        Rubric,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="template_blocks",
        db_index=True,
        help_text="Reference to the rubric used in this block.",
    )
    feedback_options = models.JSONField(
        blank=True,
        default=list,
        help_text=(
            "Per-category predefined feedback comment options for reviewers. "
            "Shape: [{category_id, options: [{id, label}]}]."
        ),
    )
    sort_order = models.PositiveIntegerField(
        default=0, help_text="Defines the order in which templates are rendered within a unit."
    )
    assigned_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_templates",
        help_text="Identifier for the user who performed the assignment.",
    )
    assigned_at = models.DateTimeField(
        auto_now_add=True, help_text="Timestamp for when the template was assigned to the block."
    )

    class Meta:
        ordering = ["sort_order"]
        verbose_name = "TAS Template Block"
        verbose_name_plural = "TAS Template Blocks"
        indexes = [
            models.Index(fields=["usage_key", "course_key"]),
            models.Index(fields=["template", "course_key"]),
        ]
        unique_together = [("usage_key", "course_key")]

    def __str__(self):
        """
        Returns string representation showing the template name and usage key (xblock/unit).
        """
        return f"{self.template.name} - {self.usage_key}"


class Submission(TimeStampedModel):
    """
    Stores one student's submission for a specific template block.

    Enforces:
      - Only one submission per (student, course_key, usage_key) tuple.
      - Drafts can be revised; only one final submission is allowed.
      - Tracks current version and PDF snapshot if generated.
    """

    STATUS_DRAFT = "draft"
    STATUS_SUBMITTED = "submitted"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="tas_submissions",
        db_index=True,
        help_text="Reference to submitting student (Open edX user).",
    )
    template_block = models.ForeignKey(
        TemplateBlock,
        on_delete=models.CASCADE,
        db_index=True,
        help_text="Reference to the template block this submission belongs to.",
    )
    course_key = CourseKeyField(
        max_length=255, db_index=True, help_text="Open edX course key in which this submission occurs."
    )
    usage_key = UsageKeyField(
        max_length=255, db_index=True, help_text="XBlock usage key for the unit where this submission is relevant."
    )
    form_data = models.JSONField(default=dict, help_text="Current field/response data submitted by the student.")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
        help_text="Current status—either draft or submitted.",
    )
    version_number = models.PositiveIntegerField(
        default=1, help_text="Version number of the current submission. Increments on each save."
    )
    submitted_at = models.DateTimeField(
        null=True, blank=True, help_text="Timestamp when student finalized this submission (moved to 'submitted')."
    )
    pdf = models.FileField(
        upload_to="tas/submissions/pdfs/", null=True, blank=True, help_text="Path to the generated PDF, if any."
    )
    preview_pdf = models.FileField(
        upload_to="tas/submissions/previews/",
        null=True,
        blank=True,
        help_text="Student Save-as-PDF preview. Not the official submitted PDF.",
    )

    class Meta:
        ordering = ["-created"]
        verbose_name = "TAS Submission"
        verbose_name_plural = "TAS Submissions"
        unique_together = [("student", "course_key", "usage_key")]

    def __str__(self):
        """
        Returns string representation 'username - course_key - usage_key'.
        """
        return f"{self.student.username} - {self.course_key} - {self.usage_key}"

    def is_draft(self):
        """
        Returns True if this submission is currently in draft status.
        """
        return self.status == self.STATUS_DRAFT

    def is_submitted(self):
        """
        Returns True if this submission is finalized (submitted).
        """
        return self.status == self.STATUS_SUBMITTED

    def create_version_snapshot(self, include_pdf=False):
        """
        Persist an immutable snapshot for the current version_number/form_data.
        Pass include_pdf=True only when called after a submit (PDF has just been generated).
        """
        defaults = {"form_data": self.form_data}
        if include_pdf:
            defaults["pdf"] = self.pdf if self.pdf else None
        SubmissionVersion.objects.update_or_create(
            submission=self,
            version_number=self.version_number,
            defaults=defaults,
        )


class SubmissionVersion(TimeStampedModel):
    """
    Stores an immutable historical snapshot of a Submission.
    On each save or version increment of the associated Submission, a new SubmissionVersion is created.
    Enables audit trails and rollback/review of student changes.
    """

    submission = models.ForeignKey(
        Submission,
        on_delete=models.CASCADE,
        related_name="tas_submission_versions",
        help_text="Parent reference to the editable submission.",
    )
    version_number = models.PositiveIntegerField(
        help_text="Snapshot's version number (matches value on the Submission at save time)."
    )
    form_data = models.JSONField(help_text="Immutable snapshot of the form data for this version.")
    saved_at = models.DateTimeField(auto_now_add=True, help_text="Timestamp when this version was created.")
    pdf = models.FileField(
        upload_to="tas/submissions/pdfs/", null=True, blank=True, help_text="Path to the generated PDF, if any."
    )

    class Meta:
        ordering = ["-version_number"]
        verbose_name = "TAS Submission Version"
        verbose_name_plural = "TAS Submission Versions"
        unique_together = [("submission", "version_number")]

    def __str__(self):
        """
        Returns string: 'username - course_key - usage_key - v<version_number>'.
        """
        user = self.submission.student.username if self.submission and self.submission.student else "N/A"
        course = self.submission.course_key if self.submission else "N/A"
        usage = self.submission.usage_key if self.submission else "N/A"
        return f"{user} - {course} - {usage} - v{self.version_number}"


class InstructorFeedback(TimeStampedModel):
    """
    Model to store instructor feedback on a student's submission.

    - Each submission can have one InstructorFeedback (enforced via OneToOneField).
    - Stores rubric scores/data, instructor comments, and overall feedback status.
    - Instructors are tracked via a ForeignKey to the User model.
    """

    submission = models.OneToOneField(
        Submission,
        on_delete=models.CASCADE,
        related_name="feedback",
        help_text="The student submission this feedback belongs to. One-to-one relationship.",
    )
    instructor = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Instructor who provided this feedback.",
        related_name="given_feedbacks",
    )
    rubrics = models.JSONField(
        default=list,
        blank=True,
        help_text="Rubric items, ratings, or scores as structured data.",
    )
    comment = models.TextField(
        blank=True,
        help_text="Free-form instructor comments about the submission.",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        help_text="Current feedback status: pending, approved, or rejected.",
        db_index=True,
    )

    class Meta:
        verbose_name = "Instructor Feedback"
        verbose_name_plural = "Instructor Feedbacks"
        ordering = ["-created"]  # Show most recently created feedback first

    def __str__(self):
        """
        Returns a human-readable summary of the feedback for admin/debug.
        """
        submission_str = str(self.submission) if self.submission else "N/A"
        status_str = dict(STATUS_CHOICES).get(self.status, self.status)
        return f"{submission_str} (Feedback: {status_str})"

    def create_version_snapshot(self):
        """
        Persist an immutable snapshot for the current rubrics/comment/status.
        Auto-increments version_number each time it is called.
        Links the snapshot to the submission version under review when present.
        """
        existing_version = InstructorFeedbackVersion.objects.all().count()
        submission_version = SubmissionVersion.objects.filter(
            submission=self.submission,
            version_number=self.submission.version_number,
        ).first()
        InstructorFeedbackVersion.objects.create(
            instructor_feedback=self,
            version_number=existing_version + 1,
            instructor=self.instructor,
            rubrics=self.rubrics,
            comment=self.comment,
            status=self.status,
            submission_version=submission_version,
        )


class InstructorFeedbackVersion(TimeStampedModel):
    """
    Stores an immutable historical snapshot of a InstructorFeedback.
    On each save or version increment of the associated InstructorFeedback, a new InstructorFeedbackVersion is created.
    Enables audit trails and rollback/review of student changes.
    """

    instructor_feedback = models.ForeignKey(
        InstructorFeedback,
        on_delete=models.CASCADE,
        related_name="tas_instructor_feedback_versions",
        help_text="Parent reference to the editable instructor feedback.",
    )
    submission_version = models.ForeignKey(
        SubmissionVersion,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="feedback_versions",
        help_text="Submission version this feedback snapshot applies to, when known.",
    )
    version_number = models.PositiveIntegerField(
        help_text="Snapshot's version number (matches value on the InstructorFeedback at save time)."
    )
    instructor = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Instructor who provided this feedback.",
        related_name="given_instructor_feedback_versions",
    )
    rubrics = models.JSONField(
        default=list,
        blank=True,
        help_text="Rubric items, ratings, or scores as structured data.",
    )
    comment = models.TextField(
        blank=True,
        help_text="Free-form instructor comments about the submission.",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        help_text="Current feedback status: pending, approved, or rejected.",
        db_index=True,
    )

    class Meta:
        ordering = ["-version_number"]
        verbose_name = "TAS Instructor Feedback Version"
        verbose_name_plural = "TAS Instructor Feedback Versions"
        unique_together = [("instructor_feedback", "version_number")]

    def __str__(self):
        """
        Returns string: 'instructor - v<version_number>'.
        """
        instructor = (
            self.instructor_feedback.instructor.username
            if self.instructor_feedback and self.instructor_feedback.instructor
            else "N/A"
        )
        return f"{instructor} - v{self.version_number}"
