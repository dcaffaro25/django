# Generated manually: rename external ERP key column to erp_id

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("erp_integrations", "0010_add_segment_tracking_to_syncruns"),
    ]

    operations = [
        migrations.RenameField(
            model_name="erpapietlmapping",
            old_name="cliente_erp_id",
            new_name="erp_id",
        ),
    ]
