# Generated manually: rename external ERP key column to erp_id

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("hr", "0018_position_employee_per_company_unique_and_base_updated_at"),
    ]

    operations = [
        migrations.RenameField(
            model_name="bonus",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="employee",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="kpi",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="position",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="recurringadjustment",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="timetracking",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
    ]
