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

from .utils import (
    AnchorWeights,
    find_anchors_rule_literal, find_anchors_ai,
    score_from_anchor_hits, confidence_from_score,
)

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# OCR and initial processing
# --------------------------------------------------------------------------- #

_USE_AI = os.getenv("NPL_USE_AI_ANCHOR", "false").lower() in ("1", "true", "yes")

@shared_task
def ocr_pipeline_task(document_id: int, embedding_mode: str | None = None) -> None:
    document = models.Document.objects.get(pk=document_id)

    # --- OCR extraction as you already do ---
    pdf_path = document.file.path
    text = utils.extract_text_with_pypdf(pdf_path)  # keep your existing function
    document.ocr_text = text
    document.ocr_data = {"engine": "pypdf"}

    # --- DocType classification using BOTH strategies (anchor finding -> scoring) ---
    rules = list(models.DocTypeRule.objects.all())
    weights = AnchorWeights()
    doc_type_anchors: Dict[str, List[Dict[str, Any]]] = {"rule_literal": [], "ai_anchor": []}

    best_rule = None
    best_score = float("-inf")
    best_conf = 0.0
    best_strategy = models.Document.DOC_STRATEGY_RULE_LITERAL

    for rule in rules:
        strong = [a.strip() for a in rule.anchors_strong.split(";") if a.strip()]
        weak = [a.strip() for a in rule.anchors_weak.split(";") if a.strip()]
        neg = [a.strip() for a in rule.anchors_negative.split(";") if a.strip()]

        # Strategy 1: rule_literal
        hits_rule = find_anchors_rule_literal(text, strong, weak, neg)
        score_rule = score_from_anchor_hits(hits_rule, weights)
        conf_rule = confidence_from_score(score_rule)
        doc_type_anchors["rule_literal"].append({
            "doc_type": rule.doc_type, "rule_id": rule.id,
            "anchors": hits_rule, "score": score_rule, "confidence": conf_rule,
        })

        # Strategy 2: ai_anchor (optional)
        if _USE_AI or document.debug_mode:
            hits_ai = find_anchors_ai(text, strong, weak, neg)
            score_ai = score_from_anchor_hits(hits_ai, weights)
            conf_ai = confidence_from_score(score_ai)
            doc_type_anchors["ai_anchor"].append({
                "doc_type": rule.doc_type, "rule_id": rule.id,
                "anchors": hits_ai, "score": score_ai, "confidence": conf_ai,
            })

        # choose the “displayed” doc_type using rule_literal (you can change this later)
        if score_rule > best_score:
            best_score = score_rule
            best_conf = conf_rule
            best_rule = rule
            best_strategy = models.Document.DOC_STRATEGY_RULE_LITERAL

    if best_rule:
        document.doc_type = best_rule.doc_type
    document.doc_type_strategy = best_strategy
    document.doctype_confidence = best_conf
    document.doc_type_anchors = doc_type_anchors

    # Keep your existing doctype_debug when debug_mode:
    if getattr(document, "debug_mode", False):
        document.doctype_debug = {
            "weights": {"strong": weights.strong, "weak": weights.weak, "negative": weights.negative},
            "rules": doc_type_anchors["rule_literal"],  # or include both if you prefer
        }
    else:
        document.doctype_debug = None

    document.save()

    # --- Kick off spans pipeline as before ---
    weak_labelling_task.delay(document.id, embedding_mode=embedding_mode)

@shared_task
def weak_labelling_task(document_id: int, embedding_mode: str | None = None) -> None:
    """
    Create spans using:
      - Strategy 1: rule_literal (your current implementation)
      - Strategy 2: ai_anchor (additional spans for comparison)
    """
    document = models.Document.objects.get(pk=document_id)
    text = document.ocr_text or ""
    metrics = document.processing_stats or {}
    total_start = time.perf_counter()

    # Idempotency: clear old spans & embeddings
    models.SpanEmbedding.objects.filter(span__document=document).delete()
    models.Span.objects.filter(document=document).delete()

    # Determine mode as you currently do
    mode = (embedding_mode or getattr(document, "embedding_mode", None) or os.getenv("EMBEDDING_MODE", "all_paragraphs")).lower()
    metrics["embedding_mode"] = mode

    rules = list(models.SpanRule.objects.all())

    # Use your existing text segmentation / paragraph grouping
    paragraphs = utils.segment_into_paragraphs(text)  # keep your own function
    grouped = utils.group_paragraphs(paragraphs, mode=mode)  # keep your own function

    weights = AnchorWeights()

    # --- Strategy 1: rule_literal spans ---
    for group in grouped:
        snippet = " ".join(p["text"] for p in group)
        first_page = group[0]["page"]
        for rule in rules:
            strong = rule.strong_anchor_list()
            weak = rule.weak_anchor_list()
            neg = rule.negative_anchor_list()

            hits = find_anchors_rule_literal(snippet, strong, weak, neg)
            if not (hits["strong"] or hits["weak"] or hits["negative"]):
                continue

            score = score_from_anchor_hits(hits, weights)
            conf = confidence_from_score(score)

            # Flatten anchors for quick UI
            anchors_pos = [h["anchor"] for h in hits["strong"]] + [h["anchor"] for h in hits["weak"]]
            anchors_neg = [h["anchor"] for h in hits["negative"]]

            span = models.Span.objects.create(
                document=document,
                label=rule.label,
                text=snippet,
                page=first_page,
                char_start=0, char_end=0,
                confidence=conf,
                span_strategy=models.Span.STRATEGY_RULE_LITERAL,
                strong_anchor_count=len(hits["strong"]),
                weak_anchor_count=len(hits["weak"]),
                negative_anchor_count=len(hits["negative"]),
                anchors_pos=anchors_pos, anchors_neg=anchors_neg,
                extra={
                    "anchors": {"rule_literal": hits},
                    "scores": {"rule_literal": {"weights": {"strong": weights.strong, "weak": weights.weak, "negative": weights.negative},
                                                "score": score, "confidence": conf}},
                    "embedding_mode": mode,
                },
            )
            if mode != "none" and hasattr(utils, "embed_span_task"):
                utils.embed_span_task.delay(span.id)

    # --- Strategy 2: ai_anchor spans (optional) ---
    if _USE_AI or document.debug_mode:
        for group in grouped:
            snippet = " ".join(p["text"] for p in group)
            first_page = group[0]["page"]
            for rule in rules:
                strong = rule.strong_anchor_list()
                weak = rule.weak_anchor_list()
                neg = rule.negative_anchor_list()

                hits_ai = find_anchors_ai(snippet, strong, weak, neg)
                if not (hits_ai["strong"] or hits_ai["weak"] or hits_ai["negative"]):
                    continue

                score_ai = score_from_anchor_hits(hits_ai, weights)
                conf_ai = confidence_from_score(score_ai)

                anchors_pos = [h["anchor"] for h in hits_ai["strong"]] + [h["anchor"] for h in hits_ai["weak"]]
                anchors_neg = [h["anchor"] for h in hits_ai["negative"]]

                span = models.Span.objects.create(
                    document=document,
                    label=rule.label,
                    text=snippet,
                    page=first_page,
                    char_start=0, char_end=0,
                    confidence=conf_ai,
                    span_strategy=models.Span.STRATEGY_AI_ANCHOR,
                    strong_anchor_count=len(hits_ai["strong"]),
                    weak_anchor_count=len(hits_ai["weak"]),
                    negative_anchor_count=len(hits_ai["negative"]),
                    anchors_pos=anchors_pos, anchors_neg=anchors_neg,
                    extra={
                        "anchors": {"ai_anchor": hits_ai},
                        "scores": {"ai_anchor": {"weights": {"strong": weights.strong, "weak": weights.weak, "negative": weights.negative},
                                                 "score": score_ai, "confidence": conf_ai}},
                        "embedding_mode": mode,
                    },
                )
                if mode != "none" and hasattr(utils, "embed_span_task"):
                    utils.embed_span_task.delay(span.id)

    metrics["total_seconds"] = round(time.perf_counter() - total_start, 3)
    document.processing_stats = metrics
    document.save(update_fields=["processing_stats"])

@shared_task
def rerun_doctype_and_spans_task(document_id: int, embedding_mode: str | None = None) -> None:
    """
    Recompute doc_type + spans using only the OCR text previously saved.
    This is the default flow because we don't persist the file unless store_file=True.
    """
    document = models.Document.objects.get(pk=document_id)
    text = document.ocr_text or ""
    rules = list(models.DocTypeRule.objects.all())
    weights = AnchorWeights()
    doc_type_anchors: Dict[str, List[Dict[str, Any]]] = {"rule_literal": [], "ai_anchor": []}

    best_rule = None
    best_score = float("-inf")
    best_conf = 0.0
    best_strategy = models.Document.DOC_STRATEGY_RULE_LITERAL

    for rule in rules:
        strong = [a.strip() for a in rule.anchors_strong.split(";") if a.strip()]
        weak = [a.strip() for a in rule.anchors_weak.split(";") if a.strip()]
        neg = [a.strip() for a in rule.anchors_negative.split(";") if a.strip()]

        hits_rule = find_anchors_rule_literal(text, strong, weak, neg)
        score_rule = score_from_anchor_hits(hits_rule, weights)
        conf_rule = confidence_from_score(score_rule)
        doc_type_anchors["rule_literal"].append({
            "doc_type": rule.doc_type, "rule_id": rule.id,
            "anchors": hits_rule, "score": score_rule, "confidence": conf_rule,
        })
        if score_rule > best_score:
            best_score = score_rule
            best_conf = conf_rule
            best_rule = rule
            best_strategy = models.Document.DOC_STRATEGY_RULE_LITERAL

        if _USE_AI or document.debug_mode:
            hits_ai = find_anchors_ai(text, strong, weak, neg)
            score_ai = score_from_anchor_hits(hits_ai, weights)
            conf_ai = confidence_from_score(score_ai)
            doc_type_anchors["ai_anchor"].append({
                "doc_type": rule.doc_type, "rule_id": rule.id,
                "anchors": hits_ai, "score": score_ai, "confidence": conf_ai,
            })

    if best_rule:
        document.doc_type = best_rule.doc_type
    document.doc_type_strategy = best_strategy
    document.doctype_confidence = best_conf
    document.doc_type_anchors = doc_type_anchors

    if getattr(document, "debug_mode", False):
        document.doctype_debug = {
            "weights": {"strong": weights.strong, "weak": weights.weak, "negative": weights.negative},
            "rules": doc_type_anchors["rule_literal"],
        }
    else:
        document.doctype_debug = None

    document.save(update_fields=["doc_type", "doc_type_strategy", "doctype_confidence", "doc_type_anchors", "doctype_debug"])

    # Clear old spans and re-run weak labelling
    models.SpanEmbedding.objects.filter(span__document=document).delete()
    models.Span.objects.filter(document=document).delete()
    weak_labelling_task.delay(document.id, embedding_mode=embedding_mode)

@shared_task
def rerun_full_pipeline_task(document_id: int, embedding_mode: str | None = None) -> None:
    """Re-run from scratch (OCR + doc_type + spans)."""
    document = models.Document.objects.get(pk=document_id)
    if not document.store_file or not document.file:
        # No stored file; can't re-OCR without reupload
        return
    
    models.SpanEmbedding.objects.filter(span__document=document).delete()
    models.Span.objects.filter(document=document).delete()
    document.ocr_text = ''
    document.ocr_data = {}
    document.doc_type = ''
    document.doc_type_strategy = models.Document.DOC_STRATEGY_RULE_LITERAL
    document.doctype_confidence = 0.0
    document.doc_type_anchors = None
    document.processing_stats = {}
    document.save(update_fields=["ocr_text", "ocr_data", "doc_type", "doc_type_strategy", "doctype_confidence", "doc_type_anchors", "processing_stats"])
    mode = (embedding_mode or getattr(document, "embedding_mode", None) or "all_paragraphs")
    ocr_pipeline_task.delay(document.id, embedding_mode=mode)

@shared_task
def recalc_span_scores_task(document_id: int, weights_dict: dict | None = None) -> None:
    """
    Recalculate span scores/confidence from stored anchors (no OCR/AI calls).
    """
    document = models.Document.objects.get(pk=document_id)
    weights = AnchorWeights(**(weights_dict or {}))
    spans = models.Span.objects.filter(document=document)

    for span in spans:
        extra = span.extra or {}
        anchors_section = extra.get("anchors", {})
        if span.span_strategy == models.Span.STRATEGY_RULE_LITERAL:
            hits = anchors_section.get("rule_literal") or {"strong": [], "weak": [], "negative": []}
            strategy_key = "rule_literal"
        elif span.span_strategy == models.Span.STRATEGY_AI_ANCHOR:
            hits = anchors_section.get("ai_anchor") or {"strong": [], "weak": [], "negative": []}
            strategy_key = "ai_anchor"
        else:
            continue

        score = score_from_anchor_hits(hits, weights)
        conf = confidence_from_score(score)

        scores_section = extra.get("scores", {})
        scores_section[strategy_key] = {
            "weights": {"strong": weights.strong, "weak": weights.weak, "negative": weights.negative},
            "score": score,
            "confidence": conf,
        }
        extra["scores"] = scores_section

        span.confidence = conf
        span.extra = extra
        span.save(update_fields=["confidence", "extra"])

@shared_task
def recalc_doc_type_scores_task(document_id: int, weights_dict: dict | None = None, prefer_strategy: str | None = None) -> None:
    """
    Recalculate doc_type scores/confidence from stored doc_type_anchors.
    Optionally change the preferred display strategy ('rule_literal' or 'ai_anchor').
    """
    document = models.Document.objects.get(pk=document_id)
    weights = AnchorWeights(**(weights_dict or {}))
    anchors = document.doc_type_anchors or {}

    # Re-score
    best_rule = None
    best_score = float("-inf")
    best_conf = 0.0
    display_strategy = prefer_strategy or document.doc_type_strategy or models.Document.DOC_STRATEGY_RULE_LITERAL

    # Always re-evaluate rule_literal; ai_anchor if present
    rescored = {"rule_literal": [], "ai_anchor": []}

    for strategy in ("rule_literal", "ai_anchor"):
        for row in anchors.get(strategy, []):
            hits = row.get("anchors", {"strong": [], "weak": [], "negative": []})
            score = score_from_anchor_hits(hits, weights)
            conf = confidence_from_score(score)
            row["score"] = score
            row["confidence"] = conf
            rescored[strategy].append(row)

            # choose displayed doc_type according to 'display_strategy'
            if strategy == display_strategy and score > best_score:
                best_score = score
                best_conf = conf
                best_rule = row

    document.doc_type_anchors = rescored
    if best_rule:
        document.doc_type = best_rule["doc_type"]
    document.doc_type_strategy = display_strategy
    document.doctype_confidence = best_conf
    document.save(update_fields=["doc_type", "doc_type_strategy", "doctype_confidence", "doc_type_anchors"])

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

    if scores:
        confidence = min(1.0, max(0.0, span_score / (len(scores) * max(1.0, max(scores)))))
    else:
        confidence = min(1.0, 0.5 + 0.1 * len(group))

    # NEW: construir payload de debug somente se o documento estiver em modo debug
    debug_payload = None
    if getattr(document, "debug_mode", False):
        debug_payload = {
            "rule": {
                "id": rule.id,
                "label": rule.label,
                "doc_type": rule.doc_type.doc_type,
                "description": rule.description,
            },
            "anchors": {
                # você pode normalizar ou apenas repassar as estruturas já usadas
                "strong": {
                    "literal": combined_details["strong_literal"],
                    "synonyms": combined_details["strong_synonyms"],
                },
                "weak": {
                    "literal": combined_details["weak_literal"],
                    "synonyms": combined_details["weak_synonyms"],
                },
                "negative": combined_details["negative_matches"],
            },
            "weights": {
                "strong_literal": 2.0,
                "weak_literal": 1.0,
                "strong_synonym": 1.0,
                "negative": -100.0,
            },
            "scores": {
                "paragraph_scores": scores,
                "span_score": span_score,
            },
        }

    extra = {
        "score_details": combined_details,
        "embedding_mode": embedding_mode,
    }
    if debug_payload is not None:
        extra["debug"] = debug_payload

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
        strong_anchor_count=strong_count,
        weak_anchor_count=weak_count,
        negative_anchor_count=negative_count,
        extra=extra,
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
