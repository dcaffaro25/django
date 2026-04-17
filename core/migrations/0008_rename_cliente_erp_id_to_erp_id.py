# Generated manually: rename external ERP key column to erp_id

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_position_employee_per_company_unique_and_base_updated_at"),
    ]

    operations = [
        migrations.RenameField(
            model_name="financialindex",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="financialindexquoteforecast",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="indexquote",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
    ]
