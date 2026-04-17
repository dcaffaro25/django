# Generated manually: rename external ERP key column to erp_id

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0005_position_employee_per_company_unique_and_base_updated_at"),
    ]

    operations = [
        migrations.RenameField(
            model_name="accountingimpact",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="cogsallocation",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="inventoryalert",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="inventorybalance",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="inventorylayer",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="inventoryvaluationsnapshot",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="stockmovement",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="tenantcostingconfig",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="unitofmeasure",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="uomconversion",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="warehouse",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
    ]
