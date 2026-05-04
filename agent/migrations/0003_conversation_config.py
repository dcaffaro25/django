"""Add per-conversation agent config: model + reasoning_effort + include_page_context."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agent", "0002_openaitokenstore_chatgpt_account_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="agentconversation",
            name="model",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="agentconversation",
            name="reasoning_effort",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Default"),
                    ("minimal", "Minimal"),
                    ("low", "Low"),
                    ("medium", "Medium"),
                    ("high", "High"),
                ],
                default="",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="agentconversation",
            name="include_page_context",
            field=models.BooleanField(default=False),
        ),
    ]
