# BusinessPartnerAlias — string CNPJ/CPF → BP resolver hints.
#
# Aditivo apenas. Populado por hooks à medida que o usuário aceita
# reconciliações onde o lado bancário traz um CNPJ que não resolve para
# nenhum BP cadastrado (caso típico: adquirentes/marketplaces).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0023_business_partner_groups"),
        ("multitenancy", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BusinessPartnerAlias",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True, null=True, help_text="Metadata and notes about how this record was created (source, filename, function, etc.)")),
                ("alias_identifier", models.CharField(
                    max_length=32, db_index=True,
                    help_text=(
                        "Dígitos do CNPJ/CPF observado externamente (extrato/descrição) "
                        "que devem resolver para este BP. Sempre normalizado para apenas "
                        "dígitos antes de gravar."
                    ),
                )),
                ("review_status", models.CharField(
                    max_length=10, default="suggested", db_index=True,
                    choices=[("suggested", "Sugerido"), ("accepted", "Aceito"), ("rejected", "Rejeitado")],
                )),
                ("source", models.CharField(
                    max_length=32, default="bank_reconciliation",
                    help_text="Como esta sugestão foi gerada.",
                )),
                ("confidence", models.DecimalField(max_digits=4, decimal_places=3, default=0)),
                ("hit_count", models.PositiveIntegerField(default=1)),
                ("last_used_at", models.DateTimeField(null=True, blank=True)),
                ("evidence", models.JSONField(default=list, blank=True)),
                ("reviewed_at", models.DateTimeField(null=True, blank=True)),
                ("business_partner", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="aliases",
                    to="billing.businesspartner",
                )),
                ("company", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="businesspartneralias_company",
                    to="multitenancy.company",
                )),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="businesspartneralias_created_by",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("updated_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="businesspartneralias_updated_by",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("reviewed_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="bp_aliases_reviewed",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name": "Apelido de Parceiro",
                "verbose_name_plural": "Apelidos de Parceiros",
            },
        ),
        migrations.AddConstraint(
            model_name="businesspartneralias",
            constraint=models.UniqueConstraint(
                fields=("company", "alias_identifier"),
                condition=Q(review_status="accepted"),
                name="bpalias_one_accepted_per_identifier",
            ),
        ),
        migrations.AddConstraint(
            model_name="businesspartneralias",
            constraint=models.UniqueConstraint(
                fields=("business_partner", "alias_identifier"),
                name="bpalias_unique_bp_identifier",
            ),
        ),
        migrations.AddIndex(
            model_name="businesspartneralias",
            index=models.Index(
                fields=["company", "alias_identifier", "review_status"],
                name="bpalias_lookup_idx",
            ),
        ),
    ]
