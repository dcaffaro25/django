# Sandbox API plan, Phase 1.
#
# Two pieces in one migration:
#   1. Auto-generated index rename on ErpApiEtlMapping that
#      ``makemigrations`` produced after the ``erp_id`` rename in 0011
#      shook out all the index hashes. Functionally a no-op, but Django
#      needs it on the chain so the model state matches what
#      ``ErpApiEtlMapping.Meta.indexes`` declares today.
#   2. The Phase-1 metadata columns on ERPAPIDefinition that drive the
#      structured editor and the test-call surface: ``version``,
#      ``source``, ``documentation_url``, ``last_tested_*``,
#      ``auth_strategy``, ``pagination_spec``, ``records_path``.
#
# Purely additive on the ERPAPIDefinition side (every new column has a
# default), so the migration is safe to apply on tenants with existing
# api definitions. No data migration needed.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_integrations', '0012_add_pipeline_models'),
    ]

    operations = [
        # ---- 1) ErpApiEtlMapping index rename ----
        migrations.RemoveIndex(
            model_name='erpapietlmapping',
            name='erp_integra_company_8d637e_idx',
        ),
        migrations.AddIndex(
            model_name='erpapietlmapping',
            index=models.Index(
                fields=['company', 'erp_id'],
                name='erp_integra_company_d2a479_idx',
            ),
        ),

        # ---- 2) Phase-1 metadata on ERPAPIDefinition ----
        migrations.AddField(
            model_name='erpapidefinition',
            name='version',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='erpapidefinition',
            name='source',
            field=models.CharField(
                choices=[
                    ('manual', 'Criada manualmente'),
                    ('imported', 'Importada de arquivo'),
                    ('discovered', 'Descoberta via URL'),
                ],
                default='manual',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='erpapidefinition',
            name='documentation_url',
            field=models.URLField(blank=True, max_length=512, null=True),
        ),
        migrations.AddField(
            model_name='erpapidefinition',
            name='last_tested_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='erpapidefinition',
            name='last_test_outcome',
            field=models.CharField(
                blank=True,
                choices=[
                    ('', '—'),
                    ('success', 'Sucesso'),
                    ('error', 'Erro'),
                    ('auth_fail', 'Falha de autenticação'),
                ],
                default='',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='erpapidefinition',
            name='last_test_error',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='erpapidefinition',
            name='auth_strategy',
            field=models.CharField(
                choices=[
                    ('provider_default', 'Padrão do provedor'),
                    ('query_params', 'Query params'),
                    ('bearer_header', 'Bearer (Authorization header)'),
                    ('basic', 'Basic auth'),
                    ('custom_template', 'Template customizado'),
                ],
                default='provider_default',
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name='erpapidefinition',
            name='pagination_spec',
            field=models.JSONField(blank=True, default=None, null=True),
        ),
        migrations.AddField(
            model_name='erpapidefinition',
            name='records_path',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]
