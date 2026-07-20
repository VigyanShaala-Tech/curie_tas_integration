from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tas_app", "0009_templateblock_rubric_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="templateblock",
            name="feedback_options",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "Per-category predefined feedback comment options for reviewers. "
                    "Shape: [{category_id, options: [{id, label}]}]."
                ),
            ),
        ),
    ]
