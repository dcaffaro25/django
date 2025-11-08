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
    """Endpoint to upload a PDF and trigger OCR + classification."""
    serializer_class = serializers.DocumentUploadSerializer

    def perform_create(self, serializer):
        doc = serializer.save()
        # Kick off asynchronous OCR + classification after committing the record
        tasks.ocr_pipeline_task.delay(doc.id)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        response.data = {'document_id': response.data['id'], 'status': 'accepted'}
        return response


class WeakLabelView(APIView):
    """Endpoint to perform weak labelling (span extraction and E‑code suggestions)."""
    def post(self, request, pk: int):
        document = get_object_or_404(models.Document, pk=pk)
        tasks.weak_labelling_task.delay(document.id)
        return Response({'document_id': document.id, 'status': 'labeling_scheduled'})


class ApplyEventsView(APIView):
    """Apply suggested events (E‑codes) to a document."""
    def post(self, request, pk: int):
        document = get_object_or_404(models.Document, pk=pk)
        tasks.apply_events_task.delay(document.id)
        return Response({'document_id': document.id, 'status': 'event_mapping_scheduled'})


class SpanListView(generics.ListAPIView):
    """List spans for a document."""
    serializer_class = serializers.SpanSerializer

    def get_queryset(self):
        document_id = self.kwargs['pk']
        return models.Span.objects.filter(document_id=document_id).order_by('page', 'char_start')


class SearchView(APIView):
    """Hybrid search endpoint combining BM25 and dense embeddings."""
    def post(self, request):
        query = request.data.get('query', '')
        filters = request.data.get('filters', {})
        top_k = int(request.data.get('top_k', 10))
        results = utils.hybrid_search(query=query, filters=filters, top_k=top_k)
        return Response({'query': query, 'results': results})


class PricingRunView(APIView):
    """Run pricing for a process based on events and structured data."""
    def post(self, request):
        process_id = request.data.get('process_id')
        process = get_object_or_404(models.Process, pk=process_id)
        tasks.pricing_task.delay(process.id)
        return Response({'process_id': process.id, 'status': 'pricing_scheduled'})