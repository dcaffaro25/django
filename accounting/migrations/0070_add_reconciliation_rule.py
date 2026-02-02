# Generated manually for ReconciliationRule model

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounting", "0069_add_performance_indexes"),
        ("multitenancy", "0028_company_notes_entity_notes_etlpipelinelog_notes_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReconciliationRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True, null=True)),
                ("name", models.CharField(max_length=255)),
                ("rule_type", models.CharField(
                    choices=[
                        ("description_pattern", "Description Pattern"),
                        ("numeric_pattern", "Numeric Pattern (invoice/ref)"),
                        ("entity_match", "Entity/Counterpart Match"),
                    ],
                    max_length=32,
                )),
                ("bank_pattern", models.CharField(max_length=500)),
                ("book_pattern", models.CharField(max_length=500)),
                ("extraction_groups", models.JSONField(default=dict)),
                ("sample_count", models.PositiveIntegerField(default=0)),
                ("accuracy_score", models.DecimalField(blank=True, decimal_places=4, max_digits=5, null=True)),
                ("status", models.CharField(
                    choices=[
                        ("proposed", "Proposed"),
                        ("validated", "Validated"),
                        ("rejected", "Rejected"),
                        ("active", "Active"),
                    ],
                    db_index=True,
                    default="proposed",
                    max_length=16,
                )),
                ("validated_at", models.DateTimeField(blank=True, null=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reconciliationrule_company", to="multitenancy.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reconciliationrule_created_by", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reconciliationrule_updated_by", to=settings.AUTH_USER_MODEL)),
                ("validated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reconciliation_rules_validated", to=settings.AUTH_USER_MODEL)),
                ("sample_suggestions", models.ManyToManyField(blank=True, related_name="derived_rules", to="accounting.reconciliationsuggestion")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["company", "rule_type"], name="accounting__company_rule_t_idx"),
                    models.Index(fields=["company", "status"], name="accounting__company_status_idx"),
                ],
            },
        ),
    ]
