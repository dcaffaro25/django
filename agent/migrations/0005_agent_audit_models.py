"""Phase 0/1 audit infrastructure.

Creates two new tables:
* ``agent_agenttoolcalllog`` — one row per tool invocation (read or write).
* ``agent_agentwriteaudit`` — one row per attempted write, including
  dry-runs, so the operator has a paper trail before live writes are
  enabled.

Depends on ``0003_conversation_config`` (which is on origin/Railway) —
NOT on ``0003_rename_…`` or ``0004_merge_…`` which are local-only at
the time of writing.

Both new models inherit ``TenantAwareBaseModel``, so the CreateModel
operations below include the full ``BaseModel`` field set
(``created_by``/``updated_by``/``is_deleted``/``notes`` plus
``created_at``/``updated_at``). The tables are created fresh on every
target — the operations don't touch any pre-existing schema.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("agent", "0003_conversation_config"),
        ("multitenancy", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AgentToolCallLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True, null=True, help_text="Metadata and notes about how this record was created (source, filename, function, etc.)")),
                ("tool_name", models.CharField(max_length=128, db_index=True)),
                ("tool_domain", models.CharField(blank=True, default="", max_length=32, help_text="Domain tag from the ToolDef (recon/fiscal/external/meta/erp/internal).")),
                ("args_summary", models.CharField(blank=True, default="", max_length=400, help_text="Truncated JSON of args; never store full args (PII).")),
                ("status", models.CharField(choices=[("ok", "OK"), ("error", "Exception"), ("warn", "Handled error"), ("rejected", "Rejected by policy")], db_index=True, max_length=16)),
                ("error_type", models.CharField(blank=True, default="", max_length=128)),
                ("error_message", models.CharField(blank=True, default="", max_length=500)),
                ("latency_ms", models.IntegerField(blank=True, null=True)),
                ("response_size_bytes", models.IntegerField(blank=True, null=True)),
                ("iteration", models.IntegerField(blank=True, null=True, help_text="Which agent_runtime iteration this call belongs to (1..AGENT_MAX_TOOL_ITERATIONS).")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="%(class)s_company", to="multitenancy.company")),
                ("conversation", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="tool_calls", to="agent.agentconversation", help_text="Null for tool calls outside a chat conversation (raw MCP, mgmt cmd).")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="agent_tool_calls", to=settings.AUTH_USER_MODEL)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_created_by", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_updated_by", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddIndex(
            model_name="agenttoolcalllog",
            index=models.Index(fields=["company", "-created_at"], name="agent_agent_company_e1f2a8_idx"),
        ),
        migrations.AddIndex(
            model_name="agenttoolcalllog",
            index=models.Index(fields=["tool_name", "status", "-created_at"], name="agent_agent_tool_na_b0c4d2_idx"),
        ),
        migrations.AddIndex(
            model_name="agenttoolcalllog",
            index=models.Index(fields=["conversation", "-created_at"], name="agent_agent_convers_7d8e9f_idx"),
        ),
        migrations.CreateModel(
            name="AgentWriteAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True, null=True, help_text="Metadata and notes about how this record was created (source, filename, function, etc.)")),
                ("tool_name", models.CharField(db_index=True, max_length=128)),
                ("target_model", models.CharField(blank=True, default="", max_length=128, help_text="e.g. 'accounting.JournalEntry'")),
                ("target_ids", models.JSONField(blank=True, default=list, help_text="PKs touched by the write — empty list means 'creating new'.")),
                ("args_summary", models.CharField(blank=True, default="", max_length=400)),
                ("before_state", models.JSONField(blank=True, default=dict)),
                ("after_state", models.JSONField(blank=True, default=dict)),
                ("status", models.CharField(choices=[("dry_run", "Dry-run only (no DB change)"), ("proposed", "Awaiting user confirmation"), ("applied", "Applied"), ("rejected", "Rejected"), ("failed", "Failed during apply"), ("undone", "Undone")], db_index=True, max_length=16)),
                ("error_type", models.CharField(blank=True, default="", max_length=128)),
                ("error_message", models.CharField(blank=True, default="", max_length=500)),
                ("undo_token", models.CharField(blank=True, default="", max_length=64, help_text="Random token the user can pass to undo_* tools to reverse this write.")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="%(class)s_company", to="multitenancy.company")),
                ("conversation", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="write_audits", to="agent.agentconversation")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="agent_write_audits", to=settings.AUTH_USER_MODEL)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_created_by", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_updated_by", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddIndex(
            model_name="agentwriteaudit",
            index=models.Index(fields=["company", "-created_at"], name="agent_agent_company_a1b2c3_idx"),
        ),
        migrations.AddIndex(
            model_name="agentwriteaudit",
            index=models.Index(fields=["tool_name", "status", "-created_at"], name="agent_agent_tool_na_d4e5f6_idx"),
        ),
        migrations.AddIndex(
            model_name="agentwriteaudit",
            index=models.Index(fields=["conversation", "-created_at"], name="agent_agent_convers_g7h8i9_idx"),
        ),
        migrations.AddIndex(
            model_name="agentwriteaudit",
            index=models.Index(fields=["target_model", "status"], name="agent_agent_target__j0k1l2_idx"),
        ),
    ]
