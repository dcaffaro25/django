# Add cnpj_root (8-digit base) to BusinessPartner so matrix↔branch
# matching works without expensive substring queries.

from django.db import migrations, models


def populate_cnpj_root(apps, schema_editor):
    """Backfill cnpj_root from identifier in chunks via bulk_update."""
    BusinessPartner = apps.get_model("billing", "BusinessPartner")
    qs = BusinessPartner.objects.exclude(identifier__isnull=True).exclude(identifier="")
    chunk = []
    CHUNK_SIZE = 2000
    for bp in qs.only("id", "identifier").iterator(chunk_size=CHUNK_SIZE):
        digits = "".join(ch for ch in (bp.identifier or "") if ch.isdigit())
        if len(digits) != 14:
            continue
        bp.cnpj_root = digits[:8]
        chunk.append(bp)
        if len(chunk) >= CHUNK_SIZE:
            BusinessPartner.objects.bulk_update(chunk, ["cnpj_root"])
            chunk = []
    if chunk:
        BusinessPartner.objects.bulk_update(chunk, ["cnpj_root"])


def reverse(apps, schema_editor):
    pass  # field is dropped by RemoveField in reverse migration


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0020_nf_link_invoice_relations_partner_accounts"),
    ]

    operations = [
        migrations.AddField(
            model_name="businesspartner",
            name="cnpj_root",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text=(
                    "Primeiros 8 dígitos do CNPJ — a 'raiz' que une "
                    "matriz e filiais de uma mesma pessoa jurídica. "
                    "Auto-populado pelo save() quando identifier tem 14 dígitos."
                ),
                max_length=8,
            ),
        ),
        migrations.AddIndex(
            model_name="businesspartner",
            index=models.Index(
                fields=["company", "cnpj_root"],
                name="bp_company_cnpjroot_idx",
            ),
        ),
        migrations.RunPython(populate_cnpj_root, reverse),
    ]
