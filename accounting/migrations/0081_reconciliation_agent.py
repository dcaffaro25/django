"""Add ReconciliationAgentRun + ReconciliationAgentDecision tables.

These back the autonomous reconciliation agent (see
``accounting/services/reconciliation_agent_service.py`` and
``accounting/management/commands/run_reconciliation_agent.py``). The two
tables are append-only: every run leaves a row, every per-bank-tx outcome
leaves a row. Both are scoped to ``company`` and indexed on the columns the
admin/UI will want to filter on (status, outcome, started_at).
"""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0080_report_cache_updated_at_indexes"),
        ("multitenancy", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReconciliationAgentRun",
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
                ("started_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("running", "Running"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="running",
                        max_length=16,
                    ),
                ),
                ("auto_accept_threshold", models.DecimalField(decimal_places=4, max_digits=5)),
                ("ambiguity_gap", models.DecimalField(decimal_places=4, max_digits=5)),
                ("min_confidence", models.DecimalField(decimal_places=4, max_digits=5)),
                ("dry_run", models.BooleanField(default=False)),
                ("bank_account_id", models.IntegerField(blank=True, null=True)),
                ("date_from", models.DateField(blank=True, null=True)),
                ("date_to", models.DateField(blank=True, null=True)),
                ("bank_tx_limit", models.IntegerField(blank=True, null=True)),
                ("triggered_by", models.CharField(blank=True, default="", max_length=64)),
                ("n_candidates", models.IntegerField(default=0)),
                ("n_auto_accepted", models.IntegerField(default=0)),
                ("n_ambiguous", models.IntegerField(default=0)),
                ("n_no_match", models.IntegerField(default=0)),
                ("n_errors", models.IntegerField(default=0)),
                ("error_message", models.TextField(blank=True, default="")),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        to="multitenancy.company",
                    ),
                ),
                (
                    "triggered_by_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="reconciliation_agent_runs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.AddIndex(
            model_name="reconciliationagentrun",
            index=models.Index(
                fields=["company", "-started_at"], name="acc_recon_agent_run_co_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="reconciliationagentrun",
            index=models.Index(
                fields=["company", "status"], name="acc_recon_agent_run_st_idx"
            ),
        ),
        migrations.CreateModel(
            name="ReconciliationAgentDecision",
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
                    "outcome",
                    models.CharField(
                        choices=[
                            ("auto_accepted", "Auto-accepted match"),
                            ("ambiguous", "Ambiguous — human review needed"),
                            ("no_match", "No suggestion above min_confidence"),
                            (
                                "not_applicable",
                                "Top suggestion not auto-acceptable (e.g. unbalanced)",
                            ),
                            ("error", "Tool/service error"),
                        ],
                        db_index=True,
                        max_length=24,
                    ),
                ),
                (
                    "top_confidence",
                    models.DecimalField(blank=True, decimal_places=4, max_digits=6, null=True),
                ),
                (
                    "second_confidence",
                    models.DecimalField(blank=True, decimal_places=4, max_digits=6, null=True),
                ),
                ("suggestion_payload", models.JSONField(blank=True, default=dict)),
                ("error_message", models.TextField(blank=True, default="")),
                (
                    "bank_transaction",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="agent_decisions",
                        to="accounting.banktransaction",
                    ),
                ),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        to="multitenancy.company",
                    ),
                ),
                (
                    "reconciliation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="agent_decisions",
                        to="accounting.reconciliation",
                    ),
                ),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="decisions",
                        to="accounting.reconciliationagentrun",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.AddIndex(
            model_name="reconciliationagentdecision",
            index=models.Index(
                fields=["company", "outcome"], name="acc_recon_agent_dec_co_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="reconciliationagentdecision",
            index=models.Index(
                fields=["run", "outcome"], name="acc_recon_agent_dec_run_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="reconciliationagentdecision",
            index=models.Index(
                fields=["bank_transaction"], name="acc_recon_agent_dec_bt_idx"
            ),
        ),
    ]
