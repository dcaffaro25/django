# Generated manually: rename external ERP key column to erp_id

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0076_position_employee_per_company_unique_and_base_updated_at"),
    ]

    operations = [
        migrations.RenameField(
            model_name="account",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="bank",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="bankaccount",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="banktransaction",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="costcenter",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="currency",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="journalentry",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
        migrations.RenameField(
            model_name="transaction",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
    ]
