from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tas_app", "0018_instructorfeedback_structured_feedback"),
    ]

    operations = [
        migrations.AddField(
            model_name="rubric",
            name="schema_version",
            field=models.PositiveSmallIntegerField(
                choices=[(1, "Simple categories"), (2, "Weighted components")],
                default=1,
                help_text="1 = flat criteria list; 2 = weighted sections/components.",
            ),
        ),
        migrations.AddField(
            model_name="rubric",
            name="sections",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Weighted rubric sections (schema_version 2).",
            ),
        ),
        migrations.AddField(
            model_name="rubric",
            name="template",
            field=models.ForeignKey(
                blank=True,
                help_text="Template whose fields the weighted components are linked to.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="rubrics",
                to="tas_app.template",
            ),
        ),
        migrations.AlterField(
            model_name="rubric",
            name="criteria",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Structured list of rubric criteria. Each entry defines a criterion name, options, and marks.",
            ),
        ),
    ]
