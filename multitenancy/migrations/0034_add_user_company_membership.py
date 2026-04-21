"""Add ``UserCompanyMembership`` — the explicit user↔company table.

Kept scoped on purpose: ``makemigrations`` picked up several unrelated
index/field churn on ``entity`` / ``integrationrule`` / ``substitutionrule``
/ ``importtransformationrule`` that represent pending drift from
earlier PRs. Those changes aren't ours to land here — this file is
just the membership table. Run ``makemigrations`` again in a separate
PR to capture the leftover drift.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("multitenancy", "0033_promote_platform_admins"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserCompanyMembership",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("owner", "Owner"),
                            ("manager", "Manager"),
                            ("operator", "Operator"),
                            ("viewer", "Viewer"),
                        ],
                        default="operator",
                        max_length=24,
                    ),
                ),
                ("is_primary", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="multitenancy.company",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="company_memberships",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="usercompanymembership",
            index=models.Index(fields=["user", "company"], name="mt_ucm_user_company_idx"),
        ),
        migrations.AddIndex(
            model_name="usercompanymembership",
            index=models.Index(fields=["company", "role"], name="mt_ucm_company_role_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="usercompanymembership",
            unique_together={("user", "company")},
        ),
    ]
