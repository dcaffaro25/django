"""Phase 1 expansion — saved agent playbooks.

Creates ``agent_agentplaybook`` for named, reusable agent
configurations. First kind is ``recon`` (saved knobs for
``run_reconciliation_agent``); the schema is JSON-keyed so future
kinds (document import, fiscal close, etc.) share the same table.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        # Originally depended on the local-only ``0007_merge_20260504_1229``
        # which was generated when ``makemigrations --merge`` was run
        # locally to reconcile the BaseModel rollout migrations
        # (``0003_rename_…``) with this branch's ``0003_conversation_config``.
        # That merge migration is intentionally untracked because Railway
        # already has the BaseModel fields applied out-of-band; depending
        # on it here breaks deploys with NodeNotFoundError. Pointing
        # straight at ``0006`` lets the new model land cleanly without
        # entangling the merge graph.
        ("agent", "0006_agentmessageattachment"),
        ("multitenancy", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AgentPlaybook",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True, null=True, help_text="Metadata and notes about how this record was created (source, filename, function, etc.)")),
                ("name", models.CharField(max_length=80)),
                ("kind", models.CharField(choices=[("recon", "Reconciliation auto-accept")], db_index=True, default="recon", max_length=16)),
                ("description", models.CharField(blank=True, default="", max_length=255)),
                ("params", models.JSONField(blank=True, default=dict, help_text="Kind-specific params. For 'recon': auto_accept_threshold, ambiguity_gap, min_confidence, bank_account_id, date_from, date_to, limit.")),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("schedule_cron", models.CharField(blank=True, default="", max_length=64)),
                ("last_run_at", models.DateTimeField(blank=True, null=True)),
                ("last_run_summary", models.JSONField(blank=True, default=dict)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="%(class)s_company", to="multitenancy.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_created_by", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_updated_by", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["company", "kind", "name"],
                "unique_together": {("company", "name")},
            },
        ),
        migrations.AddIndex(
            model_name="agentplaybook",
            index=models.Index(fields=["company", "kind", "is_active"], name="agent_play_co_kind_d4e8f1_idx"),
        ),
        migrations.AddIndex(
            model_name="agentplaybook",
            index=models.Index(fields=["company", "-last_run_at"], name="agent_play_co_last_a3b5c7_idx"),
        ),
    ]
