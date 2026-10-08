from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import model_utils.fields
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("tas_app", "0012_submission_preview_pdf"),
    ]

    operations = [
        migrations.AddField(
            model_name="instructorfeedback",
            name="source",
            field=models.CharField(
                choices=[("human", "Human"), ("curie", "CURIE")],
                db_index=True,
                default="human",
                help_text="Who currently owns this compatibility projection: a human grader or CURIE.",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="templateblock",
            name="curie_enabled",
            field=models.BooleanField(
                default=False,
                help_text="When true and CURIE_ENABLED is on, this assignment is eligible for CURIE review.",
            ),
        ),
        migrations.CreateModel(
            name="CurieReview",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "created",
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now, editable=False, verbose_name="created"
                    ),
                ),
                (
                    "modified",
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now, editable=False, verbose_name="modified"
                    ),
                ),
                (
                    "submission_version_number",
                    models.PositiveIntegerField(
                        help_text="Submission.version_number at submit time. Not a student-facing attempt ordinal."
                    ),
                ),
                (
                    "trigger_id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Idempotency key sent on trigger and echoed on callback.",
                        unique=True,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending_evaluation", "Pending evaluation"),
                            ("ready", "Ready"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="pending_evaluation",
                        max_length=32,
                    ),
                ),
                (
                    "verdict",
                    models.CharField(
                        blank=True,
                        choices=[("accepted", "Accepted"), ("rejected", "Rejected")],
                        help_text="TAS-computed accept/reject. Null until a success callback is applied.",
                        max_length=16,
                        null=True,
                    ),
                ),
                (
                    "gate_criterion_scores",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="Overall SWOT Coherence & Alignment scores: [{criterion, score, max_score}].",
                    ),
                ),
                (
                    "field_feedback",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="Per-field CURIE comments and criterion scores for every successful review.",
                    ),
                ),
                ("overall_feedback", models.TextField(blank=True, default="")),
                (
                    "error_detail",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Integration error detail. Set only when status is failed.",
                    ),
                ),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "submission",
                    models.ForeignKey(
                        help_text="Submission this review belongs to. Identity flows through this relation.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="curie_reviews",
                        to="tas_app.submission",
                    ),
                ),
            ],
            options={
                "verbose_name": "CURIE Review",
                "verbose_name_plural": "CURIE Reviews",
                "ordering": ["-requested_at"],
            },
        ),
        migrations.AddIndex(
            model_name="curiereview",
            index=models.Index(fields=["submission", "status"], name="tas_app_cur_submiss_7e4f1a_idx"),
        ),
        migrations.AddIndex(
            model_name="curiereview",
            index=models.Index(fields=["status", "requested_at"], name="tas_app_cur_status_4c8b2d_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="curiereview",
            unique_together={("submission", "submission_version_number")},
        ),
    ]
