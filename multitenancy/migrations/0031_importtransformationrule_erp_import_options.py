# Generated manually for ERP import behavior on transformation rules

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('multitenancy', '0030_position_employee_per_company_unique_and_base_updated_at'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='importtransformationrule',
            name='multitenanc_company_001fdc_idx',
        ),
        migrations.RemoveField(
            model_name='importtransformationrule',
            name='cliente_erp_id',
        ),
        migrations.AddField(
            model_name='importtransformationrule',
            name='erp_key_coalesce',
            field=models.BooleanField(
                default=True,
                help_text=(
                    'When True, a mapped cliente_erp_id on each imported row also drives upsert/delete '
                    'the same way as a dedicated __erp_id column. Set False to only use __erp_id for ERP-key matching.'
                ),
            ),
        ),
        migrations.AddField(
            model_name='importtransformationrule',
            name='erp_duplicate_behavior',
            field=models.CharField(
                choices=[
                    ('update', 'Update existing row when the same ERP key is found'),
                    ('skip', 'Skip row when a row with the same ERP key already exists'),
                    ('error', 'Fail the row when a row with the same ERP key already exists'),
                ],
                default='update',
                help_text=(
                    'When an import row resolves to an existing record by ERP key '
                    '(__erp_id or coalesced cliente_erp_id), choose update, skip, or error.'
                ),
                max_length=20,
            ),
        ),
    ]
