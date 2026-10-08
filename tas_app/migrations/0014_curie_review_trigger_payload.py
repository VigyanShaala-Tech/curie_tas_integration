from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tas_app", "0013_curie_review"),
    ]

    operations = [
        migrations.AddField(
            model_name="curiereview",
            name="trigger_payload",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Canonical TAS→CURIE trigger body frozen at submit. Retries must reuse this object.",
            ),
        ),
    ]
