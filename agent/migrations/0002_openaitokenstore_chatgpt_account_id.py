"""Add ``chatgpt_account_id`` to :class:`OpenAITokenStore`.

The Codex Responses API requires this value as the ``chatgpt-account-id``
header on every call. Pulled from the ``https://api.openai.com/auth``
claim of the access_token JWT. Existing rows (if any) get an empty string;
they'll be repopulated next time the token is refreshed or re-imported.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agent", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="openaitokenstore",
            name="chatgpt_account_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
