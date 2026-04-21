"""Create ``ErrorReport`` — the aggregation / issue table.

Kept scoped to just this model. ``makemigrations`` tried to sweep in
an index-rename cascade + the old ``financialindex`` / ``indexquote``
drift; not ours to land here.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0009_add_user_activity"),
    ]

    operations = [
        migrations.CreateModel(
            name="ErrorReport",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("fingerprint", models.CharField(db_index=True, max_length=64, unique=True)),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("frontend", "frontend"),
                            ("backend_drf", "backend_drf"),
                            ("backend_django", "backend_django"),
                            ("celery", "celery"),
                        ],
                        db_index=True,
                        max_length=24,
                    ),
                ),
                ("error_class", models.CharField(blank=True, default="", max_length=128)),
                ("message", models.TextField(blank=True, default="")),
                ("sample_stack", models.TextField(blank=True, default="")),
                ("path", models.CharField(blank=True, default="", max_length=512)),
                ("method", models.CharField(blank=True, default="", max_length=8)),
                ("status_code", models.PositiveIntegerField(blank=True, null=True)),
                ("count", models.PositiveIntegerField(default=0)),
                ("affected_users", models.PositiveIntegerField(default=0)),
                ("first_seen_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("last_seen_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("is_resolved", models.BooleanField(default=False)),
                ("is_reopened", models.BooleanField(default=False)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("resolution_note", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "resolved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="resolved_errors",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-last_seen_at"]},
        ),
        migrations.AddIndex(
            model_name="errorreport",
            index=models.Index(fields=["kind", "-last_seen_at"], name="core_errrep_kind_last_idx"),
        ),
        migrations.AddIndex(
            model_name="errorreport",
            index=models.Index(fields=["is_resolved", "-last_seen_at"], name="core_errrep_res_last_idx"),
        ),
        migrations.AddIndex(
            model_name="errorreport",
            index=models.Index(fields=["-count"], name="core_errrep_count_idx"),
        ),
    ]
