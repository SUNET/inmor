from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("entities", "0002_subordinate_additional_claims"),
    ]

    operations = [
        migrations.AlterField(
            model_name="subordinate",
            name="metadata",
            field=models.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name="subordinate",
            name="forced_metadata",
            field=models.JSONField(default=dict),
        ),
    ]
