from django.db import migrations, models


def backfill_feedback_submission_versions(apps, schema_editor):
    InstructorFeedback = apps.get_model("tas_app", "InstructorFeedback")
    InstructorFeedbackVersion = apps.get_model("tas_app", "InstructorFeedbackVersion")

    for feedback in InstructorFeedback.objects.select_related("submission").iterator():
        latest_snapshot = (
            InstructorFeedbackVersion.objects.filter(
                instructor_feedback_id=feedback.pk,
                submission_version__isnull=False,
            )
            .select_related("submission_version")
            .order_by("-version_number")
            .first()
        )
        feedback.submission_version_number = (
            latest_snapshot.submission_version.version_number
            if latest_snapshot is not None
            else feedback.submission.version_number
        )
        feedback.save(update_fields=["submission_version_number"])


class Migration(migrations.Migration):

    dependencies = [
        ("tas_app", "0016_curiereview_publication_held"),
    ]

    operations = [
        migrations.AddField(
            model_name="instructorfeedback",
            name="submission_version_number",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Submission version to which this active feedback projection applies.",
                null=True,
            ),
        ),
        migrations.RunPython(
            backfill_feedback_submission_versions,
            migrations.RunPython.noop,
        ),
    ]
