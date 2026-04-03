# Generated manually for boleto/CNPJ reconciliation fields

import django.contrib.postgres.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0072_add_cliente_erp_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="numero_boleto",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Número do boleto associado a este lançamento contábil.",
                max_length=50,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="transaction",
            name="cnpj",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="CNPJ da contraparte para conciliação.",
                max_length=14,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="banktransaction",
            name="numeros_boleto",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(max_length=50),
                blank=True,
                default=list,
                help_text="Lista de números de boleto extraídos desta movimentação bancária.",
                size=None,
            ),
        ),
        migrations.AddField(
            model_name="banktransaction",
            name="cnpj",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="CNPJ da contraparte para conciliação.",
                max_length=14,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="reconciliationconfig",
            name="require_cnpj_match",
            field=models.BooleanField(
                default=False,
                help_text="When True, only allow matches where non-empty bank and book CNPJs are equal.",
            ),
        ),
    ]
