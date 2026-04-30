# Generated manually for the NF↔Tx link feature, Invoice fiscal-status,
# Invoice↔NF M2M, BusinessPartner posting accounts, BillingTenantConfig
# and tenant-scoped ProductService.code uniqueness.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0019_rename_cliente_erp_id_to_erp_id"),
        ("multitenancy", "0001_initial"),
        ("accounting", "0080_report_cache_updated_at_indexes"),
    ]

    operations = [
        # ============================================================
        # ProductService: tenant-scoped uniqueness on code (was global)
        # ============================================================
        migrations.AlterField(
            model_name="productservice",
            name="code",
            field=models.CharField(db_index=True, max_length=100),
        ),
        migrations.AddConstraint(
            model_name="productservice",
            constraint=models.UniqueConstraint(
                fields=("company", "code"),
                name="billing_ps_company_code_uniq",
            ),
        ),

        # ============================================================
        # BusinessPartner posting accounts
        # ============================================================
        migrations.AddField(
            model_name="businesspartner",
            name="receivable_account",
            field=models.ForeignKey(
                blank=True,
                help_text="Conta A/R deste cliente (vendas).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="accounting.account",
            ),
        ),
        migrations.AddField(
            model_name="businesspartner",
            name="payable_account",
            field=models.ForeignKey(
                blank=True,
                help_text="Conta A/P deste fornecedor (compras).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="accounting.account",
            ),
        ),

        # ============================================================
        # Invoice: contract FK + fiscal_status + cache markers
        # ============================================================
        migrations.AddField(
            model_name="invoice",
            name="contract",
            field=models.ForeignKey(
                blank=True,
                help_text="Contrato-mãe que originou esta fatura (recorrência).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="invoices",
                to="billing.contract",
            ),
        ),
        migrations.AddField(
            model_name="invoice",
            name="fiscal_status",
            field=models.CharField(
                choices=[
                    ("pending_nf", "Pendente de NF"),
                    ("invoiced", "Faturada (NF emitida)"),
                    ("partially_returned", "Devolvida parcialmente"),
                    ("fully_returned", "Devolvida"),
                    ("fiscally_cancelled", "NF cancelada"),
                    ("mixed", "Misto (múltiplas NFs com estados diferentes)"),
                ],
                default="pending_nf",
                db_index=True,
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="invoice",
            name="fiscal_status_computed_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="Última vez que o cache de fiscal_status foi recalculado.",
            ),
        ),
        migrations.AddField(
            model_name="invoice",
            name="has_pending_corrections",
            field=models.BooleanField(
                default=False,
                help_text="True quando alguma NF vinculada teve uma CCe desde o último review.",
            ),
        ),
        migrations.AddIndex(
            model_name="invoice",
            index=models.Index(
                fields=["company", "fiscal_status"],
                name="billing_inv_company_fiscal_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="invoice",
            index=models.Index(
                fields=["company", "status"],
                name="billing_inv_company_status_idx",
            ),
        ),

        # ============================================================
        # InvoiceNFLink (through-model do M:N Invoice ↔ NotaFiscal)
        # ============================================================
        migrations.CreateModel(
            name="InvoiceNFLink",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True)),
                ("relation_type", models.CharField(
                    choices=[
                        ("normal", "Normal"),
                        ("devolucao", "Devolução"),
                        ("complementar", "Complementar"),
                        ("ajuste", "Ajuste"),
                    ],
                    db_index=True,
                    default="normal",
                    max_length=16,
                )),
                ("allocated_amount", models.DecimalField(
                    blank=True,
                    decimal_places=2,
                    help_text="Valor da NF coberto por esta Invoice (para casos parciais).",
                    max_digits=15,
                    null=True,
                )),
                ("company", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="invoicenflink_company",
                    to="multitenancy.company",
                )),
                ("created_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="invoicenflink_created_by",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("updated_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="invoicenflink_updated_by",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("invoice", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="nf_attachments",
                    to="billing.invoice",
                )),
                ("nota_fiscal", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="invoice_attachments",
                    to="billing.notafiscal",
                )),
            ],
            options={
                "verbose_name": "Vínculo Invoice ↔ NF",
                "verbose_name_plural": "Vínculos Invoice ↔ NF",
            },
        ),
        migrations.AddConstraint(
            model_name="invoicenflink",
            constraint=models.UniqueConstraint(
                fields=("company", "invoice", "nota_fiscal"),
                name="billing_invnflink_company_inv_nf_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="invoicenflink",
            index=models.Index(fields=["company", "invoice"], name="billing_invnflink_inv_idx"),
        ),
        migrations.AddIndex(
            model_name="invoicenflink",
            index=models.Index(fields=["company", "nota_fiscal"], name="billing_invnflink_nf_idx"),
        ),
        migrations.AddIndex(
            model_name="invoicenflink",
            index=models.Index(fields=["company", "relation_type"], name="billing_invnflink_rel_idx"),
        ),

        # ============================================================
        # NFTransactionLink (M:N entre Transaction e NotaFiscal)
        # ============================================================
        migrations.CreateModel(
            name="NFTransactionLink",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True)),
                ("allocated_amount", models.DecimalField(
                    blank=True, decimal_places=2, max_digits=15, null=True,
                    help_text=(
                        "Valor da NF coberto por esta Tx (para casos parciais). "
                        "Quando vazio o operador deve assumir que a Tx cobre integralmente a NF."
                    ),
                )),
                ("confidence", models.DecimalField(
                    decimal_places=3, default=0, max_digits=4,
                    help_text="Confiança do match (0..1). 0 = manual sem sinal.",
                )),
                ("method", models.CharField(
                    choices=[
                        ("nf_number", "Match por nf_number"),
                        ("description_regex", "Regex em description"),
                        ("bank_description", "Regex em BankTransaction"),
                        ("manual", "Manual"),
                        ("backfill", "Backfill"),
                    ],
                    db_index=True,
                    default="nf_number",
                    max_length=32,
                )),
                ("matched_fields", models.JSONField(
                    blank=True, default=list,
                    help_text='Lista dos campos que casaram, ex: ["nf_number","cnpj","date","amount"].',
                )),
                ("review_status", models.CharField(
                    choices=[
                        ("suggested", "Sugerido"),
                        ("accepted", "Aceito"),
                        ("rejected", "Rejeitado"),
                    ],
                    db_index=True,
                    default="suggested",
                    max_length=16,
                )),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("tx_amount_snapshot", models.DecimalField(
                    blank=True, decimal_places=2, max_digits=15, null=True,
                )),
                ("nf_valor_snapshot", models.DecimalField(
                    blank=True, decimal_places=2, max_digits=15, null=True,
                )),
                ("company", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="nftransactionlink_company",
                    to="multitenancy.company",
                )),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="nftransactionlink_created_by",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("updated_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="nftransactionlink_updated_by",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("transaction", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="nf_links",
                    to="accounting.transaction",
                )),
                ("nota_fiscal", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="transaction_links",
                    to="billing.notafiscal",
                )),
                ("reviewed_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="nf_links_reviewed",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name": "Vínculo NF ↔ Transação",
                "verbose_name_plural": "Vínculos NF ↔ Transação",
            },
        ),
        migrations.AddConstraint(
            model_name="nftransactionlink",
            constraint=models.UniqueConstraint(
                fields=("company", "transaction", "nota_fiscal"),
                name="billing_nflink_company_tx_nf_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="nftransactionlink",
            index=models.Index(fields=["company", "review_status"], name="billing_nflink_rev_idx"),
        ),
        migrations.AddIndex(
            model_name="nftransactionlink",
            index=models.Index(fields=["company", "nota_fiscal", "review_status"], name="billing_nflink_nf_rev_idx"),
        ),
        migrations.AddIndex(
            model_name="nftransactionlink",
            index=models.Index(fields=["company", "transaction", "review_status"], name="billing_nflink_tx_rev_idx"),
        ),
        migrations.AddIndex(
            model_name="nftransactionlink",
            index=models.Index(fields=["company", "method"], name="billing_nflink_method_idx"),
        ),

        # ============================================================
        # Invoice ↔ NotaFiscal M2M declaration (via through=InvoiceNFLink)
        # ============================================================
        migrations.AddField(
            model_name="invoice",
            name="notas_fiscais",
            field=models.ManyToManyField(
                blank=True,
                related_name="invoices",
                through="billing.InvoiceNFLink",
                to="billing.notafiscal",
            ),
        ),

        # ============================================================
        # BillingTenantConfig (singleton per-tenant)
        # ============================================================
        migrations.CreateModel(
            name="BillingTenantConfig",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True)),
                ("auto_create_invoice_from_nf", models.BooleanField(
                    default=False,
                    help_text=(
                        "Ao importar uma NF (saída, finalidade=normal) tenta casar com "
                        "uma Invoice existente; se não houver match, cria uma Invoice."
                    ),
                )),
                ("auto_create_invoice_for_finalidades", models.JSONField(
                    blank=True, default=list,
                    help_text=(
                        "Quais finalidades disparam auto-criação. Default vazio = apenas "
                        "1=Normal. Lista de inteiros como [1,2]."
                    ),
                )),
                ("auto_create_invoice_for_tipos", models.JSONField(
                    blank=True, default=list,
                    help_text=(
                        "Quais tipo_operacao disparam auto-criação. Default vazio = apenas "
                        "1=Saída. Lista de inteiros como [0,1]."
                    ),
                )),
                ("auto_link_nf_to_transactions", models.BooleanField(
                    default=True,
                    help_text=(
                        "Quando true, o NF importer chama nf_link_service para sugerir "
                        "links com Transactions existentes."
                    ),
                )),
                ("auto_accept_link_above", models.DecimalField(
                    decimal_places=3, default=1.001, max_digits=4,
                    help_text=(
                        "Confiança a partir da qual o link é aceito automaticamente "
                        "(sem revisão humana). Default 1.001 = nunca aceitar sozinho."
                    ),
                )),
                ("link_date_window_days", models.SmallIntegerField(
                    default=7,
                    help_text="Tolerância em dias entre Transaction.date e NotaFiscal.data_emissao no matching.",
                )),
                ("link_amount_tolerance_pct", models.DecimalField(
                    decimal_places=4, default=0.01, max_digits=5,
                    help_text="Tolerância proporcional para casamento de valor (0.01 = 1%).",
                )),
                ("company", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="billingtenantconfig_company",
                    to="multitenancy.company",
                )),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="billingtenantconfig_created_by",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("updated_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="billingtenantconfig_updated_by",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("default_receivable_account", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+",
                    to="accounting.account",
                    help_text="A/R default — usado quando BusinessPartner.receivable_account está vazio.",
                )),
                ("default_payable_account", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+",
                    to="accounting.account",
                    help_text="A/P default — usado quando BusinessPartner.payable_account está vazio.",
                )),
            ],
            options={
                "verbose_name": "Configuração de Faturamento",
                "verbose_name_plural": "Configurações de Faturamento",
            },
        ),
        migrations.AddConstraint(
            model_name="billingtenantconfig",
            constraint=models.UniqueConstraint(
                fields=("company",),
                name="billing_tenantconfig_company_uniq",
            ),
        ),
    ]
