"""Serializers for :mod:`accounting.reports` models."""

from pydantic import ValidationError as PydanticValidationError
from rest_framework import serializers

from .models import ReportInstance, ReportTemplate
from .services.document_schema import validate_document


class ReportTemplateSerializer(serializers.ModelSerializer):
    """Write-capable serializer for :class:`ReportTemplate`.

    Runs pydantic validation on the ``document`` field. On failure, translates
    pydantic's errors into DRF's ``ValidationError`` format so the client gets
    a clean JSON error with field-level paths.
    """

    class Meta:
        model = ReportTemplate
        fields = [
            "id",
            "name",
            "report_type",
            "description",
            "document",
            "is_active",
            "is_default",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_document(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("document must be a JSON object")
        try:
            validate_document(value)
        except PydanticValidationError as exc:
            # Surface pydantic errors as a structured list — the frontend can
            # map each entry to its corresponding form control.
            raise serializers.ValidationError(
                [
                    {
                        "loc": ".".join(str(p) for p in err.get("loc", [])),
                        "msg": err.get("msg", ""),
                        "type": err.get("type", ""),
                    }
                    for err in exc.errors()
                ]
            )
        return value

    def validate(self, attrs):
        # Cross-field: if document.report_type is set, it must match the
        # top-level report_type column (they're denormalized for query speed).
        doc = attrs.get("document")
        report_type = attrs.get("report_type")
        if doc and report_type and doc.get("report_type") and doc["report_type"] != report_type:
            raise serializers.ValidationError({
                "report_type": f"document.report_type ({doc['report_type']}) does not match "
                               f"column report_type ({report_type})",
            })
        return attrs


class ReportInstanceSerializer(serializers.ModelSerializer):
    """Read-heavy serializer for :class:`ReportInstance`.

    Create is handled by the ``/save/`` endpoint rather than the standard POST
    to the instances collection; the default writer is used only for metadata
    updates (``status``, ``notes``).
    """

    template_name = serializers.CharField(source="template.name", read_only=True)
    generated_by_name = serializers.CharField(
        source="generated_by.get_full_name",
        read_only=True,
    )

    class Meta:
        model = ReportInstance
        fields = [
            "id",
            "template",
            "template_name",
            "template_snapshot",
            "name",
            "report_type",
            "periods",
            "result",
            "status",
            "generated_by",
            "generated_by_name",
            "generated_at",
            "notes",
        ]
        read_only_fields = [
            "id",
            "template_snapshot",
            "periods",
            "result",
            "report_type",
            "generated_by",
            "generated_at",
            "template_name",
            "generated_by_name",
        ]


class ReportInstanceListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for instance listings — omits the big JSON blobs."""

    template_name = serializers.CharField(source="template.name", read_only=True)
    generated_by_name = serializers.CharField(
        source="generated_by.get_full_name",
        read_only=True,
    )

    class Meta:
        model = ReportInstance
        fields = [
            "id",
            "template",
            "template_name",
            "name",
            "report_type",
            "status",
            "generated_by",
            "generated_by_name",
            "generated_at",
            "notes",
        ]
        read_only_fields = fields
