"""
Celery tasks for the NPL application, simplified to focus on span extraction
and metadata without indexing in Meilisearch.
"""
from __future__ import annotations

import time
import logging
import re
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Tuple

from concurrent.futures import ThreadPoolExecutor
from celery import shared_task
from django.conf import settings
from django.db import transaction
import numpy as np
from accounting.services.embedding_client import EmbeddingClient
from . import models, utils
import os

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# OCR and initial processing
# --------------------------------------------------------------------------- #

@shared_task
def ocr_pipeline_task(document_id: int, embedding_mode: str | None = None) -> None:
    """Extrai o texto e dispara a task de weak labelling. Registra tempo de OCR."""
    document = models.Document.objects.get(pk=document_id)
    metrics = document.processing_stats or {}
    start_ocr = time.perf_counter()

    pdf_path = document.file.path
    text = utils.extract_text_with_pypdf(pdf_path)
    document.ocr_text = text
    document.ocr_data = {"engine": "pypdf"}

    doc_type, doc_confidence = utils.classify_document_type(text)
    document.doc_type = doc_type
    document.doctype_confidence = doc_confidence

    process_number = utils.extract_process_number(text)
    if process_number:
        process, _ = models.Process.objects.get_or_create(case_number=process_number)
        document.process = process
        document.process_number_raw = process_number
        document.no_process_found = False
    else:
        document.no_process_found = True

    with transaction.atomic():
        document.save()

    end_ocr = time.perf_counter()
    # Se nenhum modo for passado, deixa para a próxima task decidir
    metrics["ocr"] = {
        "time_sec": end_ocr - start_ocr,
        "num_characters": len(text)
    }
    document.processing_stats = metrics
    document.save(update_fields=["processing_stats"])
    weak_labelling_task.delay(document.id, embedding_mode=embedding_mode)

@shared_task
def weak_labelling_task(document_id: int, embedding_mode: str | None = None) -> None:
    """Segmenta, embed, pontua e cria spans conforme o modo de embeddings."""
    document = models.Document.objects.get(pk=document_id)
    metrics = document.processing_stats or {}
    total_start = time.perf_counter()

    # Decide o modo de embeddings: argumento > campo do documento > variável de ambiente
    mode = (embedding_mode
            or getattr(document, "embedding_mode", None)
            or os.getenv("EMBEDDING_MODE", "all_paragraphs")).lower()
    metrics["embedding_mode"] = mode

    rules = models.SpanRule.objects.all()
    if not rules:
        logger.info("No SpanRules configured; skipping span extraction")
        return

    # 1. Segmentação em parágrafos com número de página
    seg_start = time.perf_counter()
    pages = utils.extract_pages(document.file.path)
    paragraphs = utils.segment_paragraphs_with_page(pages)
    seg_end = time.perf_counter()
    metrics["segmentation"] = {
        "num_paragraphs": len(paragraphs),
        "time_sec": seg_end - seg_start
    }

    # Configurações de embeddings
    embed_parallel = int(os.getenv("EMBED_PARALLEL_REQUESTS", 1))
    num_thread = int(os.getenv("EMBED_NUM_THREAD", 0))
    max_tokens = int(os.getenv("EMBED_TOKEN_LIMIT", 2048))
    metrics["embedding_config"] = {
        "embedding_num_thread": num_thread,
        "embedding_parallel_requests": embed_parallel,
        "embedding_token_limit": max_tokens,
        "batch_size": len(paragraphs)
    }

    # 2. Embeddings de parágrafos (apenas no modo all_paragraphs)
    para_vecs: List[np.ndarray | None] = [None] * len(paragraphs)
    embed_client = EmbeddingClient(model=settings.EMBED_MODEL, dim=settings.EMBED_DIM, num_thread=num_thread)
    if mode == "all_paragraphs":
        emb_start = time.perf_counter()

        def embed_single_paragraph(paragraph: str) -> np.ndarray:
            chunks = utils.split_text_by_tokens(paragraph, max_tokens=max_tokens)
            vecs = embed_client.embed_texts(chunks)
            arrs = [np.array(v, dtype=float) for v in vecs]
            return np.mean(arrs, axis=0)

        para_texts = [p[1] for p in paragraphs]
        with ThreadPoolExecutor(max_workers=embed_parallel) as executor:
            futures = [executor.submit(embed_single_paragraph, p) for p in para_texts]
            for idx, f in enumerate(futures):
                try:
                    para_vecs[idx] = f.result()
                except Exception as e:
                    logger.exception("Failed to embed paragraph: %s", e)
                    para_vecs[idx] = None

        emb_end = time.perf_counter()
        metrics["embedding"] = {"time_sec": emb_end - emb_start}
    else:
        metrics["embedding"] = {"time_sec": 0.0}

    # 3. Scoring e criação de spans
    total_scoring_time = 0.0
    total_span_creation_time = 0.0
    total_spans = 0

    # Usar sinônimos somente se embeddar parágrafos
    use_synonyms = (mode == "all_paragraphs")

    for rule in rules:
        scoring_start = time.perf_counter()
        scores: List[float] = []
        details_list: List[Dict[str, Any]] = []
        for idx, (offset, para, page) in enumerate(paragraphs):
            sc, det = utils.score_paragraph(
                rule, para, embed_client,
                para_vec=para_vecs[idx],
                use_synonyms=use_synonyms
            )
            scores.append(sc)
            details_list.append(det)
        scoring_end = time.perf_counter()
        total_scoring_time += scoring_end - scoring_start

        if not scores:
            continue

        max_score = max(scores)
        threshold = max_score * 0.5

        current_group: List[Tuple[int, str, int]] = []
        current_details: List[Dict[str, Any]] = []
        current_scores: List[float] = []
        
        for (offset, para, page), sc, det in zip(paragraphs, scores, details_list):
            if sc >= threshold:
                current_group.append((offset, para, page))
                current_details.append(det)
                current_scores.append(sc)
            else:
                if current_group:
                    span_time_start = time.perf_counter()
                    create_span_only(document, rule, current_group, current_details, mode, current_scores)
                    span_time_end = time.perf_counter()
                    total_span_creation_time += span_time_end - span_time_start
                    total_spans += 1
                    current_group = []
                    current_details = []
                    current_scores = []
        if current_group:
            span_time_start = time.perf_counter()
            create_span_only(document, rule, current_group, current_details, mode, current_scores)
            span_time_end = time.perf_counter()
            total_span_creation_time += span_time_end - span_time_start
            total_spans += 1

    metrics["scoring"] = {"time_sec": total_scoring_time}
    metrics["span_creation"] = {"num_spans": total_spans, "time_sec": total_span_creation_time}
    metrics["total_time_sec"] = time.perf_counter() - total_start

    document.processing_stats = metrics
    document.save(update_fields=["processing_stats"])

def create_span_only(document, rule, group, details_list, embedding_mode, scores):
    """
    Cria um Span a partir de um grupo de parágrafos, associando a primeira página e
    gravando as contagens de âncoras.
    """
    # Constrói o snippet a partir das partes, ao invés de usar offsets globais
    snippet = " ".join([para for _, para, _ in group])
    first_page = group[0][2]  # página do primeiro parágrafo

    combined_details = {
        "strong_literal": [],
        "weak_literal": [],
        "strong_synonyms": [],
        "weak_synonyms": [],
        "negative_matches": [],
    }
    for det in details_list:
        for key in combined_details:
            combined_details[key].extend(det.get(key, []))

    anchors_pos = []
    anchors_neg = []
    snippet_lower = snippet.lower()
    for anc in rule.strong_anchor_list() + rule.weak_anchor_list():
        if anc:
            for m in re.finditer(re.escape(anc.lower()), snippet_lower):
                anchors_pos.append(anc)#{"anchor": anc, "pos": m.start()})
    for neg in rule.negative_anchor_list():
        if neg:
            for m in re.finditer(re.escape(neg.lower()), snippet_lower):
                anchors_neg.append(neg)#{"anchor": neg, "pos": m.start()})

    # Contagem de âncoras para diagnóstico
    strong_count = len(combined_details["strong_literal"]) + len(combined_details["strong_synonyms"])
    weak_count = len(combined_details["weak_literal"]) + len(combined_details["weak_synonyms"])
    negative_count = len(combined_details["negative_matches"])

    
    # Score agregado (exemplo: soma das pontuações dos parágrafos)
    span_score = sum(scores) if scores else 0.0

    # Cálculo de confiança usando score e contagens, caso deseje
    # Por exemplo, normalizar pelo número de parágrafos:
    if scores:
        confidence = min(1.0, max(0.0, span_score / (len(scores) * max(1.0, max(scores)))))
    else:
        confidence = min(1.0, 0.5 + 0.1 * len(group))

    span = models.Span.objects.create(
        document=document,
        label=rule.label,
        text=snippet,
        page=first_page,
        char_start=0,
        char_end=0,
        confidence=confidence,
        anchors_pos=anchors_pos,
        anchors_neg=anchors_neg,
        strong_anchor_count = strong_count,
        weak_anchor_count = weak_count,
        negative_anchor_count = negative_count,
        extra={
            "score_details": combined_details,
            "embedding_mode": embedding_mode,
        },
    )

    if embedding_mode != "none":
        embed_span_task.delay(span.id)

@shared_task
def embed_span_task(span_id: int) -> None:
    """Gera o embedding de um span, se necessário."""
    span = models.Span.objects.get(pk=span_id)
    embed_client = EmbeddingClient(model=settings.EMBED_MODEL, dim=settings.EMBED_DIM)
    try:
        vec = embed_client.embed_one(span.text)
    except Exception as e:
        logger.exception("embedding failed for span %s: %s", span_id, e)
        vec = [0.0] * settings.EMBED_DIM
    models.SpanEmbedding.objects.create(
        span=span,
        model_name=settings.EMBED_MODEL,
        dim=len(vec),
        vector=vec,
        version="v0",
    )

# --------------------------------------------------------------------------- #
# Events and pricing remain unchanged
# --------------------------------------------------------------------------- #

@shared_task
def apply_events_task(document_id: int) -> None:
    """Map spans to events and create structured models."""
    document = models.Document.objects.get(pk=document_id)
    if not document.process:
        logger.warning("apply_events_task called for document %s without process; skipping", document_id)
        return
    spans = document.spans.all()
    for span in spans:
        codes = utils.map_span_to_event_codes(span)
        for code in codes:
            event_type, _ = models.EventType.objects.get_or_create(code=code, defaults={"description": code})
            event = models.CourtEvent.objects.create(
                process=document.process,
                event_type=event_type,
                date=date.today(),
                description=f"Event derived from span {span.label}",
            )
            models.CourtEventEvidence.objects.create(
                event=event,
                span=span,
                document=document,
                evidence_confidence=span.confidence,
                notes="auto",
            )
            if code.startswith("E032") or "PENHORA" in span.label.upper():
                models.Seizure.objects.create(
                    event=event,
                    span=span,
                    subtype=span.label_subtype,
                    amount=None,
                    asset_identifier="",
                    status="ordenada",
                )

@shared_task
def pricing_task(process_id: int) -> None:
    """Calculate a pricing estimate for a process based on events."""
    process = models.Process.objects.get(pk=process_id)
    events = process.events.all()
    total = Decimal("0.00")
    details: Dict[str, Any] = {}
    for event in events:
        code = event.event_type.code
        if code in ("E010", "E012"):
            total += Decimal("0.20")
            details[code] = "uplift_20pct"
        elif code.startswith("E032"):
            total += Decimal("0.05")
            details[code] = "penhora"
        else:
            total += Decimal("0.01")
            details[code] = "base"
    models.PricingRun.objects.create(process=process, details=details, total_price=total)
    models.ProcessPricing.objects.create(process=process, price=total)
