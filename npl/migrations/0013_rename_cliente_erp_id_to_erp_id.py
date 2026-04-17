# Generated manually: rename external ERP key column to erp_id

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("npl", "0012_add_cliente_erp_id"),
    ]

    operations = [
        migrations.RenameField(
            model_name="doctyperule",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="spanrule",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
    ]
