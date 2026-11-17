from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tas_app", "0015_curie_review_grade_published_at"),
    ]

    operations = [
        migrations.AlterField(
            model_name="curiereview",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending_evaluation", "Pending evaluation"),
                    ("ready", "Ready (auto-published)"),
                    ("ready_for_approval", "Ready for approval"),
                    ("approved", "Approved"),
                    ("failed", "Failed"),
                ],
                db_index=True,
                default="pending_evaluation",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="curiereview",
            name="approved_by",
            field=models.ForeignKey(
                blank=True,
                help_text="Instructor who released this review to the learner.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="approved_curie_reviews",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="curiereview",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="curiereview",
            name="approval_modified",
            field=models.BooleanField(
                default=False,
                help_text="True when the instructor edited the CURIE output before releasing it.",
            ),
        ),
        migrations.AddField(
            model_name="curiereview",
            name="published_source",
            field=models.CharField(
                blank=True,
                choices=[("human", "Human"), ("curie", "CURIE")],
                default="",
                help_text="curie when released unchanged, human when the instructor overrode it.",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="curiereview",
            name="approved_verdict",
            field=models.CharField(
                blank=True,
                choices=[("accepted", "Accepted"), ("rejected", "Rejected")],
                help_text="Verdict computed from the released content.",
                max_length=16,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="curiereview",
            name="approved_gate_criterion_scores",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="curiereview",
            name="approved_field_feedback",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="curiereview",
            name="approved_overall_feedback",
            field=models.TextField(blank=True, default=""),
        ),
    ]
