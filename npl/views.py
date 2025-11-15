"""
API views for the NPL app.

These class‑based views handle the core endpoints of the pipeline: uploading
documents, performing weak labelling, listing spans, running hybrid search and
calculating pricing.  Heavy processing is delegated to Celery tasks to keep
HTTP requests responsive.
"""
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView

from . import models
from . import serializers
from . import tasks
from . import utils


class DocumentUploadView(generics.CreateAPIView):
    permission_classes = []
    """Endpoint to upload a PDF and trigger OCR + classification."""
    serializer_class = serializers.DocumentUploadSerializer

    def perform_create(self, serializer):
        embedding_mode = (
            self.request.data.get("embedding_mode")
            or serializer.validated_data.get("embedding_mode")
        )
        debug_mode = serializer.validated_data.get("debug_mode", False)
        
        uploaded_file = self.request.FILES.get('file')
        original_name = getattr(uploaded_file, 'name', '') if uploaded_file else ''

        doc = serializer.save(
            embedding_mode=embedding_mode,
            file_name=original_name,  # NEW
            debug_mode=debug_mode
        )
        tasks.ocr_pipeline_task.delay(doc.id, embedding_mode=embedding_mode)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        response.data = {'document_id': response.data['id'], 'status': 'accepted'}
        return response

class DocumentRerunFullPipelineView(APIView):
    """
    Reexecuta OCR + classificação + spans a partir do PDF original.
    POST /documents/<id>/rerun_full_pipeline/
    """
    permission_classes = []  # ajuste conforme sua auth

    def post(self, request, pk):
        doc = get_object_or_404(models.Document, pk=pk)
        embedding_mode = request.data.get('embedding_mode') or doc.embedding_mode
        tasks.rerun_full_pipeline_task.delay(doc.id, embedding_mode=embedding_mode)
        return Response(
            {"document_id": doc.id, "status": "queued", "action": "rerun_full_pipeline"},
            status=status.HTTP_202_ACCEPTED,
        )


class DocumentRerunDoctypeSpansView(APIView):
    """
    Recalcula apenas doc_type + spans usando o OCR já salvo.
    POST /documents/<id>/rerun_doctype_spans/
    """
    permission_classes = []  # ajuste conforme sua auth

    def post(self, request, pk):
        doc = get_object_or_404(models.Document, pk=pk)
        embedding_mode = request.data.get('embedding_mode') or doc.embedding_mode
        tasks.rerun_doctype_and_spans_task.delay(doc.id, embedding_mode=embedding_mode)
        return Response(
            {"document_id": doc.id, "status": "queued", "action": "rerun_doctype_spans"},
            status=status.HTTP_202_ACCEPTED,
        )


class EmbeddingModeUpdateView(APIView):
    """
    API para atualizar o embedding_mode de um Document.
    Não permite retroceder para um modo menos sofisticado.
    """
    permission_classes = []  # ajuste conforme sua política de acesso

    MODES = ['none', 'spans_only', 'all_paragraphs']

    def patch(self, request, pk):
        doc = get_object_or_404(models.Document, pk=pk)
        new_mode = request.data.get('embedding_mode', '').lower()
        if new_mode not in self.MODES:
            return Response({"error": "Invalid embedding_mode"}, status=status.HTTP_400_BAD_REQUEST)

        current_mode = doc.embedding_mode or 'all_paragraphs'
        # Verifica se a transição é "para frente" na cadeia de modos
        if self.MODES.index(new_mode) < self.MODES.index(current_mode):
            return Response(
                {"error": "Cannot regress to a less sophisticated embedding mode"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if new_mode == current_mode:
            return Response({"message": "Mode unchanged", "embedding_mode": current_mode})

        # Atualiza o documento
        doc.embedding_mode = new_mode
        doc.save(update_fields=['embedding_mode'])

        # Dispara tarefas conforme a transição
        if current_mode == 'none' and new_mode == 'spans_only':
            # Gerar embeddings dos spans existentes
            for span in doc.spans.all():
                tasks.embed_span_task.delay(span.id)
        elif new_mode == 'all_paragraphs':
            # Reexecuta o pipeline em modo all_paragraphs para gerar embeddings de parágrafos
            # e reclassificar/reestruturar spans.
            tasks.weak_labelling_task.delay(doc.id, embedding_mode=new_mode)

        return Response({"embedding_mode": new_mode}, status=status.HTTP_200_OK)

class WeakLabelView(APIView):
    permission_classes = []
    """Endpoint to perform weak labelling (span extraction and E‑code suggestions)."""
    def post(self, request, pk: int):
        document = get_object_or_404(models.Document, pk=pk)
        tasks.weak_labelling_task.delay(document.id)
        return Response({'document_id': document.id, 'status': 'labeling_scheduled'})


class ApplyEventsView(APIView):
    permission_classes = []
    """Apply suggested events (E‑codes) to a document."""
    def post(self, request, pk: int):
        document = get_object_or_404(models.Document, pk=pk)
        tasks.apply_events_task.delay(document.id)
        return Response({'document_id': document.id, 'status': 'event_mapping_scheduled'})


class SpanListView(generics.ListAPIView):
    permission_classes = []
    """List spans for a document."""
    serializer_class = serializers.SpanSerializer

    def get_queryset(self):
        document_id = self.kwargs['pk']
        return models.Span.objects.filter(document_id=document_id).order_by('page', 'char_start')


class SearchView(APIView):
    permission_classes = []
    """Hybrid search endpoint combining BM25 and dense embeddings."""
    def post(self, request):
        query = request.data.get('query', '')
        filters = request.data.get('filters', {})
        top_k = int(request.data.get('top_k', 10))
        results = utils.hybrid_search(query=query, filters=filters, top_k=top_k)
        return Response({'query': query, 'results': results})


class PricingRunView(APIView):
    permission_classes = []
    """Run pricing for a process based on events and structured data."""
    def post(self, request):
        process_id = request.data.get('process_id')
        process = get_object_or_404(models.Process, pk=process_id)
        tasks.pricing_task.delay(process.id)
        return Response({'process_id': process.id, 'status': 'pricing_scheduled'})