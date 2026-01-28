# Generated manually for erp_integrations app

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("multitenancy", "0028_company_notes_entity_notes_etlpipelinelog_notes_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ERPProvider",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True, help_text="Metadata and notes about how this record was created (source, filename, function, etc.)", null=True)),
                ("slug", models.SlugField(max_length=32, unique=True)),
                ("name", models.CharField(max_length=100)),
                ("base_url", models.URLField(blank=True, max_length=255, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_created_by", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_updated_by", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="ERPAPIDefinition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True, help_text="Metadata and notes about how this record was created (source, filename, function, etc.)", null=True)),
                ("call", models.CharField(help_text="API method name (e.g. ListarContasPagar).", max_length=128)),
                ("param_schema", models.JSONField(blank=True, default=list, help_text="List of param specs: [{name, type, description, required, default}, ...].")),
                ("default_param", models.JSONField(blank=True, default=dict, help_text="Default param object used when building the request.")),
                ("description", models.CharField(blank=True, max_length=255, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_created_by", to=settings.AUTH_USER_MODEL)),
                ("provider", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="api_definitions", to="erp_integrations.erpprovider")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_updated_by", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["provider", "call"],
                "unique_together": {("provider", "call")},
            },
        ),
        migrations.CreateModel(
            name="ERPConnection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True, help_text="Metadata and notes about how this record was created (source, filename, function, etc.)", null=True)),
                ("name", models.CharField(blank=True, help_text="Optional label for this connection (e.g. 'Production Omie').", max_length=100, null=True)),
                ("app_key", models.CharField(max_length=128)),
                ("app_secret", models.CharField(max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="%(class)s_company", to="multitenancy.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_created_by", to=settings.AUTH_USER_MODEL)),
                ("provider", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="connections", to="erp_integrations.erpprovider")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_updated_by", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["company", "provider"],
                "unique_together": {("company", "provider")},
            },
        ),
    ]
