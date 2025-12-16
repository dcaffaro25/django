"""
DRF views for knowledge base API endpoints.
"""
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.views.generic import TemplateView

from multitenancy.mixins import ScopedQuerysetMixin
from .models import KnowledgeBase, KnowledgeDocument, Answer, AnswerFeedback
from .serializers import (
    KnowledgeBaseSerializer,
    KnowledgeDocumentSerializer,
    DocumentUploadSerializer,
    AskRequestSerializer,
    AskResponseSerializer,
    AnswerFeedbackSerializer,
)
from .services.gemini_service import GeminiFileSearchService, MAX_FILE_SIZE_BYTES
from .tasks import index_document_task, import_existing_documents_task

logger = logging.getLogger(__name__)


class KnowledgeBaseIndexView(TemplateView):
    """Template view for the knowledge base UI."""
    template_name = 'knowledge_base/index.html'


class KnowledgeBaseViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    """
    ViewSet for KnowledgeBase CRUD operations.
    Includes custom actions for asking questions and uploading documents.
    """
    queryset = KnowledgeBase.objects.all()
    serializer_class = KnowledgeBaseSerializer
    permission_classes = [IsAuthenticated]
    
    def perform_create(self, serializer):
        """Create knowledge base and initialize Gemini File Search Store."""
        kb = serializer.save(company=self.request.tenant)
        
        # Create Gemini File Search Store
        try:
            service = GeminiFileSearchService()
            display_name = f"{kb.company.subdomain}_{kb.name}_{kb.id}"
            store_name = service.create_store(display_name=display_name)
            kb.gemini_store_name = store_name
            kb.save(update_fields=['gemini_store_name'])
            logger.info(f"Created knowledge base {kb.id} with store {store_name}")
        except Exception as e:
            logger.error(f"Failed to create Gemini store for KB {kb.id}: {e}")
            # Don't fail creation, but log error
            # Store will be created on first document upload if needed
    
    @action(detail=True, methods=['post'], url_path='ask')
    def ask(self, request, pk=None):
        """
        Ask a question against the knowledge base.
        
        POST /api/knowledge-bases/{id}/ask/
        Body: {"question": "..."}
        """
        kb = self.get_object()
        serializer = AskRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        question = serializer.validated_data['question']
        
        # Check if knowledge base has a store
        if not kb.gemini_store_name:
            return Response(
                {'error': 'Knowledge base has no documents indexed yet.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            service = GeminiFileSearchService()
            result = service.ask(store_name=kb.gemini_store_name, question=question)
            
            # Create Answer record
            answer = Answer.objects.create(
                knowledge_base=kb,
                question=question,
                answer_text=result['answer_text'],
                grounding_metadata=result['grounding_metadata'],
                company=kb.company
            )
            
            # Build response
            response_data = {
                'answer_id': answer.id,
                'answer_text': result['answer_text'],
                'citations': result['citations'],
                'grounding_metadata': result['grounding_metadata'],
            }
            
            response_serializer = AskResponseSerializer(data=response_data)
            response_serializer.is_valid(raise_exception=True)
            
            return Response(response_serializer.validated_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Failed to answer question for KB {kb.id}: {e}")
            return Response(
                {'error': f'Failed to generate answer: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], url_path='documents')
    def upload_documents(self, request, pk=None):
        """
        Upload or import documents into the knowledge base.
        
        POST /api/knowledge-bases/{id}/documents/
        Body (multipart/form-data):
          - file: File to upload (optional if source_document_id provided)
          - source_document_id: ID of existing npl.Document to import (optional)
          - filename: Optional filename override
        """
        kb = self.get_object()
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        file = serializer.validated_data.get('file')
        source_document_id = serializer.validated_data.get('source_document_id')
        filename = serializer.validated_data.get('filename')
        
        if not file and not source_document_id:
            return Response(
                {'error': 'Either file or source_document_id must be provided.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Ensure Gemini store exists
        if not kb.gemini_store_name:
            try:
                service = GeminiFileSearchService()
                display_name = f"{kb.company.subdomain}_{kb.name}_{kb.id}"
                store_name = service.create_store(display_name=display_name)
                kb.gemini_store_name = store_name
                kb.save(update_fields=['gemini_store_name'])
            except Exception as e:
                return Response(
                    {'error': f'Failed to create Gemini store: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        try:
            # Handle file upload
            if file:
                # Validate file size
                if hasattr(file, 'size') and file.size > MAX_FILE_SIZE_BYTES:
                    return Response(
                        {
                            'error': f'File size ({file.size / 1024 / 1024:.2f} MB) exceeds '
                                   f'maximum allowed size (20 MB)'
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                filename = filename or getattr(file, 'name', 'uploaded_file')
                source_document = None
            else:
                # Import existing document
                from npl.models import Document as NPLDocument
                source_document = get_object_or_404(NPLDocument, id=source_document_id)
                filename = filename or source_document.file_name or f"document_{source_document_id}"
                file = None
            
            # Create KnowledgeDocument
            kb_doc = KnowledgeDocument.objects.create(
                knowledge_base=kb,
                source_document=source_document,
                filename=filename,
                company=kb.company,
                status='queued',
                metadata={
                    'file_size': getattr(file, 'size', None) if file else None,
                    'mime_type': getattr(file, 'content_type', None) if file else None,
                }
            )
            
            # If file was uploaded, we need to store it temporarily or pass to task
            # For now, we'll store it in the source_document if available
            # In production, you might want to use a temp storage solution
            if file and not source_document:
                # Store file temporarily - in a real implementation, use proper temp storage
                # For now, create a temporary npl.Document to hold the file
                from npl.models import Document as NPLDocument
                temp_doc = NPLDocument.objects.create(
                    file_name=filename,
                    file=file,
                    store_file=True,
                    company=kb.company,
                )
                kb_doc.source_document = temp_doc
                kb_doc.save(update_fields=['source_document'])
            
            # Queue indexing task
            index_document_task.delay(kb_doc.id)
            
            doc_serializer = KnowledgeDocumentSerializer(kb_doc)
            return Response(doc_serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Failed to upload document to KB {kb.id}: {e}")
            return Response(
                {'error': f'Failed to upload document: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class KnowledgeDocumentViewSet(ScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    """
    Read-only ViewSet for listing and viewing KnowledgeDocuments.
    """
    queryset = KnowledgeDocument.objects.all()
    serializer_class = KnowledgeDocumentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter documents by knowledge_base if provided."""
        qs = super().get_queryset()
        kb_id = self.request.query_params.get('knowledge_base')
        if kb_id:
            qs = qs.filter(knowledge_base_id=kb_id)
        return qs


class AnswerFeedbackView(viewsets.ModelViewSet):
    """
    ViewSet for answer feedback.
    """
    queryset = AnswerFeedback.objects.all()
    serializer_class = AnswerFeedbackSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter by answer if provided."""
        qs = super().get_queryset()
        answer_id = self.request.query_params.get('answer')
        if answer_id:
            qs = qs.filter(answer_id=answer_id)
        return qs
