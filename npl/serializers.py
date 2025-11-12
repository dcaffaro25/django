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
        default=models.Document.EMBEDDING_MODE_CHOICES[0][0],  # "all_paragraphs"
        help_text="Define como os embeddings serão gerados: all_paragraphs, spans_only ou none."
    )

    class Meta:
        model = models.Document
        # Inclui embedding_mode no payload
        fields = ('id', 'file', 'embedding_mode')
        read_only_fields = ('id',)


class DocumentSerializer(serializers.ModelSerializer):
    """Detailed document representation used for listing and retrieving docs."""
    class Meta:
        model = models.Document
        fields = (
            'id',
            'process',
            'mime_type',
            'num_pages',
            'doc_type',
            'doctype_confidence',
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
        )


class CourtEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CourtEvent
        fields = ('id', 'process', 'event_type', 'date', 'description')


class PricingRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.PricingRun
        fields = ('id', 'process', 'created_at', 'total_price', 'details')