"""Phase 2 — chat attachments.

Creates ``agent_agentmessageattachment`` for files uploaded inside an
agent conversation (PDFs, NF-e XMLs, OFX, images). Linked to
``AgentMessage`` (nullable while the upload is in flight, attached
once the chat call lands) and ``AgentConversation``.

Files live on Railway Volume mounted at ``settings.MEDIA_ROOT``.
Depends on the audit-models migration only because we share Django's
migration ordering for the ``agent`` app.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("agent", "0005_agent_audit_models"),
        ("multitenancy", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AgentMessageAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True, null=True, help_text="Metadata and notes about how this record was created (source, filename, function, etc.)")),
                ("file", models.FileField(upload_to="agent/attachments/%Y/%m/")),
                ("filename", models.CharField(max_length=255)),
                ("content_type", models.CharField(blank=True, default="", max_length=128)),
                ("size_bytes", models.PositiveIntegerField(default=0)),
                ("kind", models.CharField(choices=[("nfe_xml", "NF-e / NFCe XML"), ("ofx", "OFX bank statement"), ("pdf", "PDF document"), ("image", "Image (PNG/JPEG/etc.)"), ("other", "Other / unsupported")], db_index=True, default="other", max_length=16)),
                ("extracted_text", models.TextField(blank=True, default="", help_text="Cached output of the parser/OCR step. Empty until ingest_document runs.")),
                ("extraction_error", models.CharField(blank=True, default="", max_length=400)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="%(class)s_company", to="multitenancy.company")),
                ("conversation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attachments", to="agent.agentconversation")),
                ("message", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="attachments", to="agent.agentmessage", help_text="Null while the file is uploaded but not yet attached to a message.")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_created_by", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_updated_by", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.AddIndex(
            model_name="agentmessageattachment",
            index=models.Index(fields=["conversation", "-created_at"], name="agent_attach_conv_a8f2c1_idx"),
        ),
        migrations.AddIndex(
            model_name="agentmessageattachment",
            index=models.Index(fields=["company", "kind"], name="agent_attach_co_kind_b3d4e5_idx"),
        ),
    ]
