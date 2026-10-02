from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("desk", "0001_initial"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="offsetsubmission",
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddIndex(
            model_name="offsetsubmission",
            index=models.Index(
                fields=["tool_code", "-created_at", "-id"],
                name="offs_tool_recent_idx",
            ),
        ),
    ]
