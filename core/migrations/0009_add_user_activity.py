"""Create ``UserActivitySession`` + ``UserActivityEvent``.

Scoped to just these two tables. ``makemigrations`` tried to sweep in
unrelated index churn on ``financialindex`` / ``indexquote`` /
``financialindexquoteforecast`` — that's drift from earlier PRs and
doesn't belong here. Someone else's follow-up should capture it.

Depends on multitenancy ``0034_add_user_company_membership`` so the
FKs to ``Company`` and the platform-admin surface from PR 2 are in
place — the activity tables don't strictly need UserCompanyMembership
but threading the ordering avoids a concurrent-merge footgun.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_rename_cliente_erp_id_to_erp_id"),
        ("multitenancy", "0034_add_user_company_membership"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserActivitySession",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("session_key", models.CharField(db_index=True, max_length=64, unique=True)),
                ("started_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("last_heartbeat_at", models.DateTimeField(auto_now_add=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("focused_ms", models.BigIntegerField(default=0)),
                ("idle_ms", models.BigIntegerField(default=0)),
                ("user_agent", models.CharField(blank=True, default="", max_length=512)),
                ("viewport_width", models.PositiveIntegerField(blank=True, null=True)),
                ("viewport_height", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "company",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="multitenancy.company",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="activity_sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="UserActivityEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("page_view", "page_view"),
                            ("heartbeat", "heartbeat"),
                            ("action", "action"),
                            ("error", "error"),
                            ("search", "search"),
                        ],
                        db_index=True,
                        max_length=16,
                    ),
                ),
                ("area", models.CharField(blank=True, db_index=True, default="", max_length=64)),
                ("path", models.CharField(blank=True, default="", max_length=512)),
                ("action", models.CharField(blank=True, default="", max_length=64)),
                ("target_model", models.CharField(blank=True, default="", max_length=64)),
                ("target_id", models.CharField(blank=True, default="", max_length=64)),
                ("duration_ms", models.PositiveIntegerField(blank=True, null=True)),
                ("meta", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "company",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="multitenancy.company",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="core.useractivitysession",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="activity_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="useractivitysession",
            index=models.Index(fields=["user", "-started_at"], name="core_uas_user_start_idx"),
        ),
        migrations.AddIndex(
            model_name="useractivitysession",
            index=models.Index(fields=["company", "-started_at"], name="core_uas_company_start_idx"),
        ),
        migrations.AddIndex(
            model_name="useractivityevent",
            index=models.Index(fields=["user", "-created_at"], name="core_uae_user_created_idx"),
        ),
        migrations.AddIndex(
            model_name="useractivityevent",
            index=models.Index(fields=["company", "-created_at"], name="core_uae_company_created_idx"),
        ),
        migrations.AddIndex(
            model_name="useractivityevent",
            index=models.Index(fields=["area", "-created_at"], name="core_uae_area_created_idx"),
        ),
        migrations.AddIndex(
            model_name="useractivityevent",
            index=models.Index(fields=["kind", "-created_at"], name="core_uae_kind_created_idx"),
        ),
        migrations.AddIndex(
            model_name="useractivityevent",
            index=models.Index(fields=["user", "area", "-created_at"], name="core_uae_user_area_idx"),
        ),
    ]
