from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tas_app", "0014_curie_review_trigger_payload"),
    ]

    operations = [
        migrations.AddField(
            model_name="curiereview",
            name="grade_published_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the accepted CURIE grade was successfully written to the LMS grade store.",
                null=True,
            ),
        ),
    ]
