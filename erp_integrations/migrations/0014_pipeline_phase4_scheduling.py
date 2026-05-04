# Sandbox API plan, Phase 4 — scheduled routines.
#
# Adds the columns the scheduler needs:
#   ERPSyncPipeline:
#     * is_paused              — soft-disable without losing the schedule
#     * incremental_config     — JSON spec for the watermark filter
#     * last_high_watermark    — DateTime of the latest "change date" we
#                                successfully imported
#   ERPSyncPipelineRun:
#     * triggered_by           — schedule / manual / api / sandbox
#     * incremental_window_start / _end — visibility into what window the
#                                         scheduler used for this run
#
# Purely additive: every column has a default / null=True so the
# migration is safe on tenants with existing pipelines and runs.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_integrations', '0013_api_definition_phase1_metadata'),
    ]

    operations = [
        migrations.AddField(
            model_name='erpsyncpipeline',
            name='is_paused',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='erpsyncpipeline',
            name='incremental_config',
            field=models.JSONField(blank=True, default=None, null=True),
        ),
        migrations.AddField(
            model_name='erpsyncpipeline',
            name='last_high_watermark',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='erpsyncpipelinerun',
            name='triggered_by',
            field=models.CharField(
                choices=[
                    ('schedule', 'Scheduled (Celery beat)'),
                    ('manual', 'Manual (UI)'),
                    ('api', 'API (programmatic)'),
                    ('sandbox', 'Sandbox preview'),
                ],
                default='manual',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='erpsyncpipelinerun',
            name='incremental_window_start',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='erpsyncpipelinerun',
            name='incremental_window_end',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
