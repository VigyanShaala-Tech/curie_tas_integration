from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tas_app", "0017_instructorfeedback_submission_version_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="instructorfeedback",
            name="structured_feedback",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "CURIE-shaped field and criterion feedback authored by a human override. "
                    "Empty for legacy manual feedback and CURIE compatibility projections."
                ),
            ),
        ),
        migrations.AddField(
            model_name="instructorfeedbackversion",
            name="structured_feedback",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Immutable CURIE-shaped human feedback snapshot, when present.",
            ),
        ),
    ]
