"""
Utility functions for the NPL application.

This module contains helper functions for document type classification,
mapping spans to event codes and performing hybrid search combining
sparse (BM25) and dense (embedding) methods.  Simple heuristics are used to
illustrate the pipeline; these can be replaced with more sophisticated models.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Tuple, Optional  

from django.conf import settings

from . import models
from docling.document_converter import DocumentConverter
import json

def convert_with_docling(pdf_path: str) -> dict:
    """
    Converte um PDF usando Docling e retorna o JSON estruturado.
    """
    converter = DocumentConverter()
    # Etapa 2: converte o documento
    result = converter.convert(pdf_path)
    # Etapa 3: obtém o objeto DoclingDocument
    doc = result.document
    # Etapa 4: exporta para JSON (string)
    json_str = doc.export_to_json()
    return json.loads(json_str)

def _split_anchors(text: str) -> List[str]:
    """Divide o campo de âncoras em uma lista, ignorando vazios e espaços."""
    return [a.strip().lower() for a in text.split(';') if a.strip()]

def extract_process_number(text: str) -> Optional[str]:
    """
    Extrai o número do processo do texto usando padrões CNJ.

    Retorna o primeiro número encontrado no formato CNJ (0000000-00.0000.0.00.0000)
    ou uma sequência de 20 dígitos, ou None se nada for encontrado.
    """
    patterns = [
        r'\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b',  # formato CNJ com pontos
        r'\b\d{20}\b',                                # 20 dígitos contínuos
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(0)
    return None

def classify_document_type(text: str) -> Tuple[str, float]:
    """
    Classifica o tipo de documento lendo as regras do banco.
    - Confiança alta (0.9) se encontrar âncora forte.
    - Confiança moderada (0.6) se encontrar âncora fraca.
    - Caso contrário, retorna tipo genérico com confiança baixa (0.3).
    """
    lowered = text.lower()

    # Verificar âncoras fortes e negativas primeiro
    for rule in models.DocTypeRule.objects.all():
        negative_anchors = _split_anchors(rule.anchors_negative)
        if any(neg in lowered for neg in negative_anchors):
            continue  # ignora este tipo se houver âncora negativa

        strong_anchors = _split_anchors(rule.anchors_strong)
        if any(strong in lowered for strong in strong_anchors):
            return rule.doc_type, 0.9

    # Em seguida, procurar âncoras fracas
    for rule in models.DocTypeRule.objects.all():
        weak_anchors = _split_anchors(rule.anchors_weak)
        if any(weak in lowered for weak in weak_anchors):
            return rule.doc_type, 0.6

    # Nenhuma regra aplicada: retorna tipo padrão
    return "DESPACHO_MERO_EXPEDIENTE", 0.3


def map_span_to_event_codes(span: models.Span) -> List[str]:
    """Map a span to one or more event codes using rule heuristics."""
    text = span.text.lower()
    codes: List[str] = []
    if '523' in text:
        codes.extend(['E010', 'E012'])
    if 'penhora' in text:
        codes.append('E032')
    if 'leil' in text:
        # differentiate by round if possible
        codes.append('E067')
    if 'arremata' in text:
        codes.append('E068')
    if 'suspens' in text and '921' in text:
        codes.append('E099')
    return codes


def _bm25_score(query_tokens: List[str], document_tokens: List[str]) -> float:
    """Compute a simple BM25‑like score using term frequency and idf approximations."""
    # For demonstration we use a simplified formula: tf * idf
    if not document_tokens:
        return 0.0
    term_counts = Counter(document_tokens)
    score = 0.0
    for token in query_tokens:
        tf = term_counts.get(token, 0)
        if tf:
            # assume idf = 1 for rare tokens else 0.5
            idf = 1.0 if len(token) > 3 else 0.5
            score += (tf / len(document_tokens)) * idf
    return score


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def _embed_text(text: str) -> List[float]:
    """Generate an embedding for the given text using the same model as DenseA.

    This function uses the first configured embedding model.  If no model is
    available, a simple bag‑of‑words vector is returned based on token counts.
    """
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        model = SentenceTransformer(settings.EMBEDDING_MODEL_A)
        vec = model.encode(text, normalize_embeddings=True).tolist()
        return vec
    except Exception:
        # Fallback: vector of term frequencies for letters a‑z
        text = text.lower()
        counts = [text.count(chr(ord('a') + i)) for i in range(26)]
        return [c / max(len(text), 1) for c in counts]


def _rrf(ranks: List[List[int]], k: int = 60) -> Dict[int, float]:
    """Compute Reciprocal Rank Fusion (RRF) scores for document IDs.

    Based on Cormack et al., RRF combines multiple ranked lists by summing
    ``1/(k + rank)`` for each document.  Documents not present in a list are
    ignored.  The constant ``k`` mitigates the impact of high ranks.
    """
    scores: Dict[int, float] = {}
    for rank_list in ranks:
        for rank, doc_id in enumerate(rank_list, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return scores


def hybrid_search(query: str, filters: Dict[str, Any], top_k: int = 10) -> List[Dict[str, Any]]:
    """Perform hybrid search over spans combining BM25 and dense embeddings.

    The function loads spans from the database, computes lexical and dense scores
    and combines them via Reciprocal Rank Fusion.  Filters can restrict
    candidate spans by label, label_subtype, event_code or process.
    """
    # Fetch candidates from database
    spans = models.Span.objects.all()
    if 'label' in filters:
        spans = spans.filter(label__iexact=filters['label'])
    if 'process_id' in filters:
        spans = spans.filter(document__process_id=filters['process_id'])
    query_tokens = re.findall(r'\w+', query.lower())
    # Precompute query embedding
    query_vec = _embed_text(query)
    # Compute scores and maintain lists of ranked IDs
    bm25_ranked: List[Tuple[int, float]] = []
    dense_ranked: List[Tuple[int, float]] = []
    for span in spans:
        doc_tokens = re.findall(r'\w+', span.text.lower())
        bm25 = _bm25_score(query_tokens, doc_tokens)
        # Use first embedding for dense similarity
        embeddings = list(span.embeddings.all())
        dense_sim = 0.0
        if embeddings:
            dense_vec = embeddings[0].vector
            dense_sim = _cosine_similarity(query_vec, dense_vec)
        bm25_ranked.append((span.id, bm25))
        dense_ranked.append((span.id, dense_sim))
    # Sort by score descending
    bm25_ranked.sort(key=lambda x: x[1], reverse=True)
    dense_ranked.sort(key=lambda x: x[1], reverse=True)
    # Create rank lists of span IDs
    bm25_ids = [span_id for span_id, _ in bm25_ranked[:top_k * 5]]
    dense_ids = [span_id for span_id, _ in dense_ranked[:top_k * 5]]
    # Compute RRF scores
    rrf_scores = _rrf([bm25_ids, dense_ids])
    # Build final list of candidate span IDs sorted by RRF
    ranked_span_ids = sorted(rrf_scores.keys(), key=lambda sid: rrf_scores[sid], reverse=True)[:top_k]
    results: List[Dict[str, Any]] = []
    for sid in ranked_span_ids:
        span = models.Span.objects.get(pk=sid)
        snippet = span.text[:200]
        results.append({
            'span_id': span.id,
            'document_id': span.document_id,
            'process_id': span.document.process_id,
            'label': span.label,
            'score': rrf_scores[sid],
            'snippet': snippet,
        })
    return results