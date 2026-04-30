# BusinessPartnerGroup + BusinessPartnerGroupMembership.
#
# Aditivo apenas — duas tabelas novas com constraints e indexes. Sem data
# migration: Groups são populados pelos hooks (nf_link_service.accept_link,
# reconciliation finalize, attach_invoice_to_nf) à medida que o usuário
# aceita vínculos. Backfill a partir de NFTransactionLinks já aceitos é
# uma management command separada (próximo milestone).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0022_critic_acknowledgement_and_invoice_critics_count"),
        ("multitenancy", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BusinessPartnerGroup",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True, null=True, help_text="Metadata and notes about how this record was created (source, filename, function, etc.)")),  # inherited BaseModel.notes
                ("name", models.CharField(
                    max_length=255,
                    help_text="Nome de exibição do grupo (geralmente o do primary_partner).",
                )),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True, db_index=True)),
                ("company", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="businesspartnergroup_company",
                    to="multitenancy.company",
                )),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="businesspartnergroup_created_by",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("updated_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="businesspartnergroup_updated_by",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("primary_partner", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="primary_of_group",
                    to="billing.businesspartner",
                    help_text="BP que representa o grupo nas listagens consolidadas.",
                )),
            ],
            options={
                "verbose_name": "Grupo de Parceiros",
                "verbose_name_plural": "Grupos de Parceiros",
            },
        ),
        migrations.AddConstraint(
            model_name="businesspartnergroup",
            constraint=models.UniqueConstraint(
                fields=("company", "primary_partner"),
                name="bpgroup_one_primary_per_partner",
            ),
        ),
        migrations.AddIndex(
            model_name="businesspartnergroup",
            index=models.Index(
                fields=["company", "is_active"],
                name="bpgroup_company_active_idx",
            ),
        ),
        migrations.CreateModel(
            name="BusinessPartnerGroupMembership",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True, null=True, help_text="Metadata and notes about how this record was created (source, filename, function, etc.)")),  # inherited BaseModel.notes
                ("role", models.CharField(
                    max_length=10, default="member",
                    choices=[("primary", "Primário"), ("member", "Membro")],
                )),
                ("review_status", models.CharField(
                    max_length=10, default="suggested", db_index=True,
                    choices=[("suggested", "Sugerido"), ("accepted", "Aceito"), ("rejected", "Rejeitado")],
                )),
                ("confidence", models.DecimalField(
                    max_digits=4, decimal_places=3, default=0,
                    help_text="Confiança máxima entre as evidências acumuladas (0..1).",
                )),
                ("hit_count", models.PositiveIntegerField(
                    default=1,
                    help_text=(
                        "Quantos sinais distintos sustentam esta sugestão. "
                        "Ao atingir o threshold (default 3) o membership promove "
                        "automaticamente para 'accepted'."
                    ),
                )),
                ("evidence", models.JSONField(
                    default=list, blank=True,
                    help_text=(
                        "Histórico de sinais que sustentam a sugestão: lista de "
                        '{"method", "source_id", "at", "confidence", "kind"}.'
                    ),
                )),
                ("reviewed_at", models.DateTimeField(null=True, blank=True)),
                ("business_partner", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="group_memberships",
                    to="billing.businesspartner",
                )),
                ("group", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="memberships",
                    to="billing.businesspartnergroup",
                )),
                ("company", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="businesspartnergroupmembership_company",
                    to="multitenancy.company",
                )),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="businesspartnergroupmembership_created_by",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("updated_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="businesspartnergroupmembership_updated_by",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("reviewed_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="bp_group_memberships_reviewed",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name": "Membro de Grupo",
                "verbose_name_plural": "Membros de Grupos",
            },
        ),
        migrations.AddConstraint(
            model_name="businesspartnergroupmembership",
            constraint=models.UniqueConstraint(
                fields=("group", "business_partner"),
                name="bpgm_unique_group_partner",
            ),
        ),
        migrations.AddConstraint(
            model_name="businesspartnergroupmembership",
            constraint=models.UniqueConstraint(
                fields=("business_partner",),
                condition=Q(review_status="accepted"),
                name="bpgm_one_accepted_per_partner",
            ),
        ),
        migrations.AddConstraint(
            model_name="businesspartnergroupmembership",
            constraint=models.UniqueConstraint(
                fields=("group",),
                condition=Q(role="primary"),
                name="bpgm_one_primary_per_group",
            ),
        ),
        migrations.AddIndex(
            model_name="businesspartnergroupmembership",
            index=models.Index(
                fields=["company", "business_partner", "review_status"],
                name="bpgm_company_bp_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="businesspartnergroupmembership",
            index=models.Index(
                fields=["group", "role"],
                name="bpgm_group_role_idx",
            ),
        ),
    ]
