# Critic acknowledgement workflow + denormalized critics_count on Invoice.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0021_businesspartner_cnpj_root"),
        ("multitenancy", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoice",
            name="critics_count",
            field=models.IntegerField(
                default=0,
                db_index=True,
                help_text="Número de críticas não-aceitas atualmente registradas para esta fatura.",
            ),
        ),
        migrations.AddField(
            model_name="invoice",
            name="critics_count_by_severity",
            field=models.JSONField(
                blank=True, default=dict,
                help_text='Contagens por severidade: {"error": N, "warning": M, "info": K}.',
            ),
        ),
        migrations.CreateModel(
            name="CriticAcknowledgement",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True)),
                ("kind", models.CharField(
                    db_index=True, max_length=64,
                    help_text="Critic kind from critics_service (e.g. unit_price_drift).",
                )),
                ("subject_type", models.CharField(
                    max_length=32,
                    help_text="'invoice' / 'nota_fiscal' / 'nota_fiscal_item' — matches Critic.subject_type.",
                )),
                ("subject_id", models.IntegerField(
                    db_index=True,
                    help_text="ID of the subject record the critic refers to.",
                )),
                ("note", models.TextField(blank=True)),
                ("acknowledged_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="critic_acks",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("company", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="criticacknowledgement_company",
                    to="multitenancy.company",
                )),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="criticacknowledgement_created_by",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("updated_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="criticacknowledgement_updated_by",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("invoice", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="critic_acknowledgements",
                    to="billing.invoice",
                )),
            ],
            options={
                "verbose_name": "Aceite de Crítica",
                "verbose_name_plural": "Aceites de Críticas",
            },
        ),
        migrations.AddConstraint(
            model_name="criticacknowledgement",
            constraint=models.UniqueConstraint(
                fields=("company", "invoice", "kind", "subject_type", "subject_id"),
                name="billing_critic_ack_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="criticacknowledgement",
            index=models.Index(
                fields=["company", "invoice", "kind"],
                name="bill_critack_inv_kind_idx",
            ),
        ),
    ]
