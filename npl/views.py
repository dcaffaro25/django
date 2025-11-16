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

from django.utils.dateparse import parse_date
from django.db.models import Count, Q
from . import models
from . import serializers
from . import tasks
from . import utils

from django.conf import settings
from rest_framework import permissions
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny  # adjust to your needs
from rest_framework.response import Response
from rest_framework import generics

from . import models, serializers, tasks

class DocumentUploadView(generics.CreateAPIView):
    """
    POST /documents/upload/
    Body: file (required), store_file?(default False), file_name?, embedding_mode?, debug_mode?
    Behavior:
      - OCR is extracted immediately from the uploaded stream.
      - By default the file is NOT stored; if store_file=true, keep it.
      - Then we queue classification + spans from OCR text.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = serializers.DocumentUploadSerializer

    def perform_create(self, serializer):
        uploaded_file = self.request.FILES["file"]
        debug_mode = bool(self.request.data.get("debug_mode", False))
        store_file = bool(self.request.data.get("store_file", False))
        embedding_mode = self.request.data.get("embedding_mode") or getattr(models.Document, "EMBEDDING_MODE_CHOICES", (("all_paragraphs","all_paragraphs"),))[0][0]
        file_name = self.request.data.get("file_name") or getattr(uploaded_file, "name", "")

        # 1) OCR directly from the uploaded stream (no need to persist)
        ocr_text = utils.extract_text_from_pdf_fileobj(uploaded_file)

        # 2) Build save kwargs
        save_kwargs = dict(
            file_name=file_name,
            debug_mode=debug_mode,
            store_file=store_file,
            embedding_mode=embedding_mode,
            ocr_text=ocr_text,
            ocr_data={"engine": "pypdf"},
            mime_type=getattr(uploaded_file, "content_type", "") or "",
        )
        # 3) Optionally persist the file if store_file=True
        if store_file:
            save_kwargs["file"] = uploaded_file

        # 4) Create the document
        doc = serializer.save(**save_kwargs)

        # 5) Queue classification + spans (no OCR step needed)
        tasks.rerun_doctype_and_spans_task.delay(doc.id, embedding_mode=embedding_mode)



    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        response.data = {'document_id': response.data['id'], 'status': 'accepted'}
        return response

class DocumentViewSet(viewsets.ModelViewSet):
    queryset = models.Document.objects.all().order_by("-id")
    serializer_class = serializers.DocumentSerializer
    permission_classes = [permissions.AllowAny]
    
    def get_serializer_class(self):
        if self.action == "list":
            return serializers.DocumentListItemSerializer
        return serializers.DocumentSerializer
    
    @action(detail=True, methods=["post"])
    def re_ocr(self, request, pk=None):
        """
        Re-OCR this document by uploading a file again (does NOT require stored file).
        Body: file (required), store_file?(default False)
        """
        doc = self.get_object()
        if "file" not in request.FILES:
            return Response({"detail": "Missing file."}, status=status.HTTP_400_BAD_REQUEST)

        uploaded_file = request.FILES["file"]
        store_file = bool(request.data.get("store_file", False))

        # OCR from stream
        ocr_text = utils.extract_text_from_pdf_fileobj(uploaded_file)

        # Update doc OCR
        doc.ocr_text = ocr_text
        doc.ocr_data = {"engine": "pypdf", "re_ocr": True}
        doc.store_file = store_file

        # Optionally persist file
        if store_file:
            doc.file = uploaded_file
            doc.file_name = getattr(uploaded_file, "name", doc.file_name or "")
            doc.mime_type = getattr(uploaded_file, "content_type", "") or doc.mime_type
        else:
            # Ensure file field is cleared if previously stored and user opts out now
            doc.file = None

        doc.save(update_fields=["ocr_text", "ocr_data", "store_file", "file", "file_name", "mime_type"])

        # Re-run doc_type + spans from OCR text
        embedding_mode = request.data.get("embedding_mode") or getattr(doc, "embedding_mode", "all_paragraphs")
        tasks.rerun_doctype_and_spans_task.delay(doc.id, embedding_mode=embedding_mode)
        return Response({"status": "queued", "action": "re_ocr"}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def rerun_full_pipeline(self, request, pk=None):
        """
        Only works if the file is stored (store_file=True). Otherwise, ask client to use re_ocr.
        """
        doc = self.get_object()
        if not doc.store_file or not doc.file:
            return Response(
                {"detail": "This document has no stored file. Use /re_ocr to upload a file and re-run OCR."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        embedding_mode = request.data.get("embedding_mode") or getattr(doc, "embedding_mode", "all_paragraphs")
        tasks.rerun_full_pipeline_task.delay(doc.id, embedding_mode=embedding_mode)
        return Response({"status": "queued", "action": "rerun_full_pipeline"}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def rerun_doctype_spans(self, request, pk=None):
        doc = self.get_object()
        embedding_mode = request.data.get("embedding_mode") or getattr(doc, "embedding_mode", "all_paragraphs")
        tasks.rerun_doctype_and_spans_task.delay(doc.id, embedding_mode=embedding_mode)
        return Response({"status": "queued", "action": "rerun_doctype_spans"}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def recalc_span_scores(self, request, pk=None):
        """
        Body (optional): {"weights": {"strong": 2.5, "weak": 1.0, "negative": -100.0}}
        """
        doc = self.get_object()
        weights = (request.data or {}).get("weights") or {}
        tasks.recalc_span_scores_task.delay(doc.id, weights_dict=weights)
        return Response({"status": "queued", "action": "recalc_span_scores", "weights": weights}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def recalc_doc_type_scores(self, request, pk=None):
        """
        Body (optional): {"weights": {...}, "prefer_strategy": "rule_literal"|"ai_anchor"}
        """
        doc = self.get_object()
        body = request.data or {}
        weights = body.get("weights") or {}
        prefer_strategy = body.get("prefer_strategy")
        tasks.recalc_doc_type_scores_task.delay(doc.id, weights_dict=weights, prefer_strategy=prefer_strategy)
        return Response({"status": "queued", "action": "recalc_doc_type_scores", "weights": weights, "prefer_strategy": prefer_strategy}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def toggle_debug(self, request, pk=None):
        doc = self.get_object()
        doc.debug_mode = bool(request.data.get("debug_mode", not doc.debug_mode))
        doc.save(update_fields=["debug_mode"])
        return Response({"id": doc.id, "debug_mode": doc.debug_mode})

    @action(detail=True, methods=["get"])
    def anchors(self, request, pk=None):
        """
        Inspect document's doc_type anchors (both strategies) and spans grouped by strategy.
        """
        doc = self.get_object()
        spans = models.Span.objects.filter(document=doc).order_by("page", "id")

        payload = {
            "document_id": doc.id,
            "doc_type": {
                "type": doc.doc_type,
                "strategy": doc.doc_type_strategy,
                "confidence": doc.doctype_confidence,
                "anchors": doc.doc_type_anchors or {},
            },
            "spans": [],
        }
        for s in spans:
            payload["spans"].append({
                "id": s.id,
                "label": s.label,
                "page": s.page,
                "strategy": s.span_strategy,
                "confidence": s.confidence,
                "anchors_pos": s.anchors_pos,
                "anchors_neg": s.anchors_neg,
                "extra": s.extra,  # contains per-strategy anchors/scores
            })
        return Response(payload)

class DocumentListView(generics.ListAPIView):
    """
    GET /documents/list/
    Returns a paginated, filterable list of documents.
    Query params:
      - q: search in file_name and doc_type. (use &search_ocr=1 to include OCR text)
      - search_ocr: 0/1 (default 0). If 1, includes ocr_text in search (slower).
      - process_id: int
      - doc_type: single or comma-separated list (e.g. DECISAO,DESPACHO)
      - strategy: doc_type_strategy filter (rule_literal|ai_anchor)
      - debug_mode: 0/1
      - store_file: 0/1
      - has_spans: 0/1
      - created_from, created_to: YYYY-MM-DD
      - ordering: one of (-created_at, created_at, -doctype_confidence, doctype_confidence, -id, id)
    Pagination uses your DRF default settings.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = serializers.DocumentListItemSerializer

    def _to_bool(self, v):
        if v is None:
            return None
        return str(v).strip().lower() in {"1", "true", "t", "yes", "y", "on"}

    def get_queryset(self):
        qs = (
            models.Document.objects
            .select_related("process")
            .annotate(span_count=Count("spans"))
            .order_by("-id")
        )

        p = self.request.query_params

        # Basic filters
        process_id = p.get("process_id")
        if process_id:
            qs = qs.filter(process_id=process_id)

        doc_type = p.get("doc_type")
        if doc_type:
            items = [x.strip() for x in doc_type.split(",") if x.strip()]
            qs = qs.filter(doc_type__in=items)

        strategy = p.get("strategy")
        if strategy in {models.Document.DOC_STRATEGY_RULE_LITERAL, models.Document.DOC_STRATEGY_AI_ANCHOR}:
            qs = qs.filter(doc_type_strategy=strategy)

        debug_mode = self._to_bool(p.get("debug_mode"))
        if debug_mode is not None:
            qs = qs.filter(debug_mode=debug_mode)

        store_file = self._to_bool(p.get("store_file"))
        if store_file is not None:
            qs = qs.filter(store_file=store_file)

        has_spans = self._to_bool(p.get("has_spans"))
        if has_spans is True:
            qs = qs.filter(spans__isnull=False).distinct()
        elif has_spans is False:
            qs = qs.filter(spans__isnull=True)

        # Date range
        created_from = p.get("created_from")
        if created_from:
            d = parse_date(created_from)
            if d:
                qs = qs.filter(created_at__date__gte=d)

        created_to = p.get("created_to")
        if created_to:
            d = parse_date(created_to)
            if d:
                qs = qs.filter(created_at__date__lte=d)

        # Free text search
        q = p.get("q", "").strip()
        if q:
            search_ocr = self._to_bool(p.get("search_ocr"))  # default False
            q_filter = Q(file_name__icontains=q) | Q(doc_type__icontains=q)
            if search_ocr:
                # Warning: includes OCR text; can be slower on large tables
                q_filter = q_filter | Q(ocr_text__icontains=q)
            qs = qs.filter(q_filter)

        # Ordering
        ordering = p.get("ordering", "-id")
        allowed = {"-created_at", "created_at", "-doctype_confidence", "doctype_confidence", "-id", "id"}
        if ordering in allowed:
            qs = qs.order_by(ordering, "-id" if ordering != "-id" else "-created_at")

        return qs

class SpanViewSet(viewsets.ModelViewSet):
    queryset = models.Span.objects.all().order_by("document_id", "page", "id")
    serializer_class = serializers.SpanSerializer
    permission_classes = [permissions.AllowAny]


class DocTypeRuleViewSet(viewsets.ModelViewSet):
    queryset = models.DocTypeRule.objects.all().order_by("id")
    serializer_class = serializers.DocTypeRuleSerializer
    permission_classes = [permissions.AllowAny]


class SpanRuleViewSet(viewsets.ModelViewSet):
    queryset = models.SpanRule.objects.all().order_by("id")
    serializer_class = serializers.SpanRuleSerializer
    permission_classes = [permissions.AllowAny]


# Optional: read-only embeddings
try:
    class SpanEmbeddingViewSet(viewsets.ReadOnlyModelViewSet):
        queryset = models.SpanEmbedding.objects.all().order_by("id")
        serializer_class = serializers.SpanEmbeddingSerializer
        permission_classes = [permissions.AllowAny]
except Exception:
    SpanEmbeddingViewSet = None

class DocumentRerunFullPipelineView(APIView):
    """
    Reexecuta OCR + classificação + spans a partir do PDF original.
    POST /documents/<id>/rerun_full_pipeline/
    """
    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAuthenticated]  # ajuste conforme sua auth

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
    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAuthenticated]  # ajuste conforme sua auth

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
    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAuthenticated]  # ajuste conforme sua política de acesso

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