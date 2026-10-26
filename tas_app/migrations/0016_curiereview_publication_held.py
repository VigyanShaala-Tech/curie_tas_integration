from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tas_app", "0015_curie_review_grade_published_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="curiereview",
            name="publication_held",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Successful review is awaiting instructor publication and is private to staff."
                ),
            ),
        ),
    ]
