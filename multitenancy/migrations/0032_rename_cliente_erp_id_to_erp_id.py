# Generated manually: rename external ERP key column to erp_id

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("multitenancy", "0031_importtransformationrule_erp_import_options"),
    ]

    operations = [
        migrations.RenameField(
            model_name="entity",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="integrationrule",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="substitutionrule",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
    ]
