"""
Serializers for the NPL app.

These classes convert model instances to and from JSON for use with the Django
REST framework.  They also perform validation on incoming data.  Additional
serializers can be created for more granular control of nested relations if
needed.
"""
from rest_framework import serializers
from . import models


class DocumentUploadSerializer(serializers.ModelSerializer):
    """
    Serializer para envio de PDF. Permite especificar opcionalmente o modo de embeddings.
    """
    
    file = serializers.FileField(write_only=True, required=True)
    
    embedding_mode = serializers.ChoiceField(
        choices=getattr(models.Document, "EMBEDDING_MODE_CHOICES", (("all_paragraphs", "all_paragraphs"),)),
        required=False,
        default=lambda: getattr(models.Document, "EMBEDDING_MODE_CHOICES", (("all_paragraphs", "all_paragraphs"),))[0][0],
    )
    
    # NEW
    debug_mode = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Se verdadeiro, popula os campos de debug (doc_type e spans).",
    )
    
    file_name = serializers.CharField(required=False, allow_blank=True)
    
    store_file = serializers.BooleanField(required=False, default=False)  # NEW (default: do not store)
    
    class Meta:
        model = models.Document
        fields = ("id", "file", "file_name", "store_file", "embedding_mode", "debug_mode")
        read_only_fields = ("id",)


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Document
        fields = (
            "id", "file_name", "store_file",
            "mime_type", "num_pages",
            "doc_type", "doc_type_strategy", "doctype_confidence",
            "doc_type_anchors", "doctype_debug",
            "embedding_mode", "debug_mode",
            "created_at", "updated_at",
        )


class DocumentListItemSerializer(serializers.ModelSerializer):
    """Lean serializer for list views (fast table rendering)."""
    span_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = models.Document
        fields = (
            "id",
            "file_name",
            "doc_type",
            "doc_type_strategy",
            "doctype_confidence",
            "debug_mode",
            "store_file",
            "process",          # process id; change to nested if you want case_number
            "created_at",
            "updated_at",
            "span_count",
        )

class SpanSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Span
        fields = (
            "id", "document", "label", "text", "page",
            "char_start", "char_end", "confidence",
            "span_strategy",
            "strong_anchor_count", "weak_anchor_count", "negative_anchor_count",
            "anchors_pos", "anchors_neg",
            "extra",
        )


class DocTypeRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.DocTypeRule
        fields = "__all__"


class SpanRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.SpanRule
        fields = "__all__"

class SpanEmbeddingSerializer(serializers.ModelSerializer):
    class Meta:
        model = getattr(models, "SpanEmbedding", None)
        if model is None:
            fields = ()
        else:
            fields = "__all__"

class CourtEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CourtEvent
        fields = ('id', 'process', 'event_type', 'date', 'description')


class PricingRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.PricingRun
        fields = ('id', 'process', 'created_at', 'total_price', 'details')