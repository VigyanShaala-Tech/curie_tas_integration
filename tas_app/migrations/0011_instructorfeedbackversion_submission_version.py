# Generated manually for REQ-008

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tas_app", "0010_templateblock_feedback_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="instructorfeedbackversion",
            name="submission_version",
            field=models.ForeignKey(
                blank=True,
                help_text="Submission version this feedback snapshot applies to, when known.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="feedback_versions",
                to="tas_app.submissionversion",
            ),
        ),
    ]
