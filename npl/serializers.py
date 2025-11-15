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
    embedding_mode = serializers.ChoiceField(
        choices=models.Document.EMBEDDING_MODE_CHOICES,
        required=False,
        default=models.Document.EMBEDDING_MODE_CHOICES[0][0],
        help_text="Define como os embeddings serão gerados: all_paragraphs, spans_only ou none."
    )
    
    # NEW
    debug_mode = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Se verdadeiro, popula os campos de debug (doc_type e spans).",
    )
    
    class Meta:
        model = models.Document
        fields = ('id', 'file', 'embedding_mode', 'file_name', 'debug_mode')
        read_only_fields = ('id',)


class DocumentSerializer(serializers.ModelSerializer):
    """Detailed document representation used for listing and retrieving docs."""
    class Meta:
        model = models.Document
        fields = (
            'id',
            'process',
            'file_name',          # NEW
            'mime_type',
            'num_pages',
            'doc_type',
            'doctype_confidence',
            'doctype_debug',   # NEW
            'embedding_mode',     # (optional but usually useful)
            'debug_mode',      # NEW
            'created_at',
            'updated_at',
        )


class SpanSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Span
        fields = (
            'id',
            'document',
            'label',
            'label_subtype',
            'text',
            'page',
            'char_start',
            'char_end',
            'confidence',
            'strong_anchor_count',   # NEW
            'weak_anchor_count',     # NEW
            'negative_anchor_count', # NEW
            'anchors_pos',           # NEW
            'anchors_neg',           # NEW
            'extra',                 # NEW: holds debug payload when enabled
        )


class CourtEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CourtEvent
        fields = ('id', 'process', 'event_type', 'date', 'description')


class PricingRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.PricingRun
        fields = ('id', 'process', 'created_at', 'total_price', 'details')