"""Initial schema for the Sysnord agent app.

Four tables:
* ``agent_openaitokenstore`` — singleton-by-convention; holds encrypted
  OAuth tokens shared across tenants.
* ``agent_oauthauthorizationflow`` — short-lived PKCE state for one
  in-flight OAuth authorization.
* ``agent_agentconversation`` — chat thread, scoped to (user, company).
* ``agent_agentmessage`` — chat history rows.

All additive — no data migration. Apply with::

    python manage.py migrate agent
"""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("multitenancy", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="OpenAITokenStore",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("access_token_encrypted", models.BinaryField(blank=True)),
                ("refresh_token_encrypted", models.BinaryField(blank=True)),
                ("token_type", models.CharField(blank=True, default="Bearer", max_length=32)),
                ("expires_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("scopes", models.CharField(blank=True, default="", max_length=512)),
                ("account_email", models.CharField(blank=True, default="", max_length=255)),
                ("account_subject", models.CharField(blank=True, default="", max_length=255)),
                ("connected_at", models.DateTimeField(blank=True, null=True)),
                ("last_refreshed_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True, default="")),
                (
                    "connected_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="openai_token_connections",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "OpenAI token store",
                "verbose_name_plural": "OpenAI token store",
            },
        ),
        migrations.CreateModel(
            name="OAuthAuthorizationFlow",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("state", models.CharField(db_index=True, max_length=128, unique=True)),
                ("code_verifier", models.CharField(max_length=256)),
                ("redirect_uri", models.CharField(max_length=512)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "initiated_by",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="agent_oauth_flows",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.AddIndex(
            model_name="oauthauthorizationflow",
            index=models.Index(fields=["expires_at"], name="agent_oauth_expires_idx"),
        ),
        migrations.CreateModel(
            name="AgentConversation",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(blank=True, default="", max_length=255)),
                ("is_archived", models.BooleanField(db_index=True, default=False)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        to="multitenancy.company",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="agent_conversations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.AddIndex(
            model_name="agentconversation",
            index=models.Index(
                fields=["company", "user", "-updated_at"],
                name="agent_conv_co_user_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="agentconversation",
            index=models.Index(
                fields=["company", "user", "is_archived"],
                name="agent_conv_co_user_arch_idx",
            ),
        ),
        migrations.CreateModel(
            name="AgentMessage",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("user", "User"),
                            ("assistant", "Assistant"),
                            ("tool", "Tool"),
                            ("system", "System"),
                        ],
                        db_index=True,
                        max_length=16,
                    ),
                ),
                ("content", models.TextField(blank=True, default="")),
                ("tool_calls", models.JSONField(blank=True, default=list)),
                ("tool_call_id", models.CharField(blank=True, default="", max_length=128)),
                ("tool_name", models.CharField(blank=True, default="", max_length=128)),
                ("model_used", models.CharField(blank=True, default="", max_length=64)),
                ("prompt_tokens", models.IntegerField(blank=True, null=True)),
                ("completion_tokens", models.IntegerField(blank=True, null=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        to="multitenancy.company",
                    ),
                ),
                (
                    "conversation",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="messages",
                        to="agent.agentconversation",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at", "id"],
                "abstract": False,
            },
        ),
        migrations.AddIndex(
            model_name="agentmessage",
            index=models.Index(
                fields=["conversation", "created_at"],
                name="agent_msg_conv_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="agentmessage",
            index=models.Index(
                fields=["company", "role"],
                name="agent_msg_co_role_idx",
            ),
        ),
    ]
