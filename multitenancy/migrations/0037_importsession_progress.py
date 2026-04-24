# Generated for Phase 6.z-e — live progress snapshot.
#
# Adds ImportSession.progress (JSONField, default=dict) so Celery
# workers can write stage-level progress outside any atomic block.
# The polling frontend reads it as part of the session detail payload
# to render a live progress strip during analyze + commit.
#
# Default dict, nullable-safe — existing rows read as empty progress.
# No data migration needed.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("multitenancy", "0036_importtransformationrule_column_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="importsession",
            name="progress",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Phase 6.z-e — live progress snapshot written at "
                    "stage boundaries outside the commit atomic block. "
                    "Keys: stage (parsing / detecting / dry_run / "
                    "materializing_rules / writing / done), sheets_done "
                    "/ sheets_total, current_sheet, errors_so_far, "
                    "updated_at. Empty dict on non-running sessions. "
                    "Intra-commit row-level progress requires a separate "
                    "DB connection (future iteration)."
                ),
            ),
        ),
    ]
