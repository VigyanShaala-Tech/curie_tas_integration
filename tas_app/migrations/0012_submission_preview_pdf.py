# Generated for APK Save-as-PDF preview (does not replace official submission.pdf)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tas_app", "0011_instructorfeedbackversion_submission_version"),
    ]

    operations = [
        migrations.AddField(
            model_name="submission",
            name="preview_pdf",
            field=models.FileField(
                blank=True,
                help_text="Student Save-as-PDF preview. Not the official submitted PDF.",
                null=True,
                upload_to="tas/submissions/previews/",
            ),
        ),
    ]
