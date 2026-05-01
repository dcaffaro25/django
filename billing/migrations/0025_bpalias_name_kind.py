"""Add ``kind`` to ``BusinessPartnerAlias`` so the same table stores two
shapes of learned mapping:

* ``kind='cnpj'`` (legacy default) — digits-only CNPJ/CPF observed on a
  bank statement / Tx, resolving to a BP. This is what
  ``upsert_alias_suggestion`` has been writing since 0024.
* ``kind='name'`` (new) — normalized name token extracted from a Tx
  description. Used when the bank side carries no CNPJ at all (foreign
  customers, informal e-commerce flows) so the matcher has *something*
  to grip on.

The unique constraints + lookup index get the new field as a leading
component so legacy CNPJ rows and new name rows never collide on the
same string. ``alias_identifier`` widens 32→80 to fit normalized name
tokens.
"""
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0024_business_partner_alias"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="businesspartneralias",
            name="bpalias_one_accepted_per_identifier",
        ),
        migrations.RemoveConstraint(
            model_name="businesspartneralias",
            name="bpalias_unique_bp_identifier",
        ),
        migrations.RemoveIndex(
            model_name="businesspartneralias",
            name="bpalias_lookup_idx",
        ),
        migrations.AddField(
            model_name="businesspartneralias",
            name="kind",
            field=models.CharField(
                choices=[("cnpj", "CNPJ/CPF"), ("name", "Nome")],
                db_index=True,
                default="cnpj",
                help_text=(
                    "Tipo de string aprendida. ``cnpj`` → dígitos de "
                    "CNPJ/CPF (legacy, padrão). ``name`` → token de nome "
                    "normalizado extraído da descrição da transação, para "
                    "casos em que o lado banco não traz CNPJ (exportações, "
                    "PIX informal, gateways e-commerce sem CPF do cliente, "
                    "etc.)."
                ),
                max_length=8,
            ),
        ),
        migrations.AlterField(
            model_name="businesspartneralias",
            name="alias_identifier",
            field=models.CharField(
                db_index=True,
                help_text=(
                    "String identificadora que deve resolver para este BP. "
                    "Para ``kind=cnpj``: apenas dígitos do CNPJ/CPF. Para "
                    "``kind=name``: token de nome normalizado (lower, sem "
                    "acentos, espaços colapsados, máx 80 chars)."
                ),
                max_length=80,
            ),
        ),
        migrations.AddConstraint(
            model_name="businesspartneralias",
            constraint=models.UniqueConstraint(
                condition=Q(review_status="accepted"),
                fields=("company", "kind", "alias_identifier"),
                name="bpalias_one_accepted_per_identifier",
            ),
        ),
        migrations.AddConstraint(
            model_name="businesspartneralias",
            constraint=models.UniqueConstraint(
                fields=("business_partner", "kind", "alias_identifier"),
                name="bpalias_unique_bp_identifier",
            ),
        ),
        migrations.AddIndex(
            model_name="businesspartneralias",
            index=models.Index(
                fields=["company", "kind", "alias_identifier", "review_status"],
                name="bpalias_lookup_idx",
            ),
        ),
    ]
