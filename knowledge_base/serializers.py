"""
DRF serializers for knowledge base API endpoints.
"""
from rest_framework import serializers
from .models import KnowledgeBase, KnowledgeDocument, Answer, AnswerFeedback


class KnowledgeBaseSerializer(serializers.ModelSerializer):
    """Serializer for KnowledgeBase CRUD operations."""
    
    documents_count = serializers.IntegerField(source='documents.count', read_only=True)
    
    class Meta:
        model = KnowledgeBase
        fields = [
            'id', 'name', 'gemini_store_name', 'company', 'created_at', 'updated_at',
            'documents_count'
        ]
        read_only_fields = ['id', 'gemini_store_name', 'created_at', 'updated_at']


class KnowledgeDocumentSerializer(serializers.ModelSerializer):
    """Serializer for KnowledgeDocument listing and detail views."""
    
    class Meta:
        model = KnowledgeDocument
        fields = [
            'id', 'knowledge_base', 'source_document', 'filename', 'status',
            'error', 'gemini_doc_name', 'metadata', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'status', 'error', 'gemini_doc_name', 'created_at', 'updated_at'
        ]


class DocumentUploadSerializer(serializers.Serializer):
    """
    Serializer for document upload/import.
    Supports both file upload and importing existing npl.Document records.
    """
    file = serializers.FileField(required=False, help_text="File to upload")
    source_document_id = serializers.IntegerField(
        required=False,
        help_text="ID of existing npl.Document to import"
    )
    filename = serializers.CharField(
        required=False,
        help_text="Optional filename override"
    )


class AskRequestSerializer(serializers.Serializer):
    """Serializer for ask question request."""
    question = serializers.CharField(
        required=True,
        help_text="Question to ask against the knowledge base"
    )


class CitationSerializer(serializers.Serializer):
    """Serializer for citation structure."""
    document_name = serializers.CharField()
    uri_or_store_ref = serializers.CharField()
    start_index = serializers.IntegerField(required=False, allow_null=True)
    end_index = serializers.IntegerField(required=False, allow_null=True)
    page = serializers.IntegerField(required=False, allow_null=True)
    excerpt = serializers.CharField(required=False, allow_null=True)


class AskResponseSerializer(serializers.Serializer):
    """Serializer for ask question response."""
    answer_id = serializers.IntegerField()
    answer_text = serializers.CharField()
    citations = CitationSerializer(many=True)
    grounding_metadata = serializers.DictField()


class AnswerFeedbackSerializer(serializers.ModelSerializer):
    """Serializer for answer feedback."""
    
    class Meta:
        model = AnswerFeedback
        fields = ['id', 'answer', 'rating', 'comment', 'missing_info', 'created_at']
        read_only_fields = ['id', 'created_at']
