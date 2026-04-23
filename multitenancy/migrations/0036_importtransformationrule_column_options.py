from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('multitenancy', '0035_v2_import_session'),
    ]

    operations = [
        migrations.AddField(
            model_name='importtransformationrule',
            name='column_options',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    'Per-column hints keyed by target field name. '
                    'Example: {"amount": {"skip_substitutions": true}}. '
                    'Supported flags: skip_substitutions (bool) — when true, '
                    'the substitution engine performs zero rule lookups on '
                    'this field.'
                ),
            ),
        ),
    ]
