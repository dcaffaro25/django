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
import unicodedata
from collections import Counter
from typing import Any, Dict, Iterable, List, Tuple, Optional  

from django.conf import settings

from . import models
from docling.document_converter import DocumentConverter
import json
from pypdf import PdfReader
import numpy as np
from accounting.services.embedding_client import EmbeddingClient
import json
import os
from dataclasses import dataclass
from typing import Dict, List, TypedDict

from io import BytesIO
from typing import BinaryIO, Optional

def extract_text_from_pdf_fileobj(fileobj: BinaryIO) -> str:
    """
    Extract text from a PDF-like file object (BytesIO / InMemoryUploadedFile).
    Uses PyPDF/fitz/whatever you already use; example below with PyPDF2.
    """
    try:
        from PyPDF2 import PdfReader
        buf = BytesIO(fileobj.read())
        reader = PdfReader(buf)
        texts = []
        for page in reader.pages:
            try:
                texts.append(page.extract_text() or "")
            except Exception:
                texts.append("")
        return "\n".join(texts).strip()
    finally:
        try:
            fileobj.seek(0)
        except Exception:
            pass

def normalize_ocr_text(text: str) -> str:
    """
    Normalize OCR text to improve literal matching:
    - remove NUL
    - join hyphen + newline splits: 'palavra-\\nseguinte' -> 'palavraseguinte'
    - replace newlines with single space
    - collapse whitespace
    - lowercase
    - remove accents
    """
    if not text:
        return ""
    text = text.replace("\x00", "")
    text = re.sub(r"(\w)\s*-\s*\n\s*(\w)", r"\1\2", text)
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.strip()


class AnchorHit(TypedDict, total=False):
    anchor: str
    count: int          # for literal/regex matches
    present: bool       # for AI yes/no signals
    source: str         # "text" | "embedding" | "ai"


AnchorsByStrength = Dict[str, List[AnchorHit]]  # keys: "strong", "weak", "negative"


@dataclass
class AnchorWeights:
    strong: float = 2.0
    weak: float = 1.0
    negative: float = -100.0


def score_from_anchor_hits(hits: AnchorsByStrength, weights: AnchorWeights) -> float:
    """Compute a score given anchor hits and weights."""
    # any negative hit => auto-kill (negative weight)
    if hits.get("negative"):
        return weights.negative

    score = 0.0
    for h in hits.get("strong", []):
        score += weights.strong * int(h.get("count", 1))
    for h in hits.get("weak", []):
        score += weights.weak * int(h.get("count", 1))
    return score


def confidence_from_score(score: float) -> float:
    """Simple mapping. Keep your heuristic if you prefer."""
    if score <= 0:
        return 0.3
    if score >= 3:
        return 0.9
    return 0.6


# ---------- Strategy 1: rule_literal (normalized literal matching) ----------

def _count_occurrences(norm_hay: str, compact_hay: str, anchor: str) -> int:
    a_norm = normalize_ocr_text(anchor)
    if not a_norm:
        return 0
    c = norm_hay.count(a_norm)
    if c == 0:
        c = compact_hay.count(compact_text(a_norm))
    return c


def find_anchors_rule_literal(
    text: str,
    strong_anchors: List[str],
    weak_anchors: List[str],
    negative_anchors: List[str],
) -> AnchorsByStrength:
    norm_text = normalize_ocr_text(text)
    compact = compact_text(text)

    hits: AnchorsByStrength = {"strong": [], "weak": [], "negative": []}

    for a in strong_anchors:
        cnt = _count_occurrences(norm_text, compact, a)
        if cnt:
            hits["strong"].append({"anchor": a, "count": cnt, "source": "text"})

    for a in weak_anchors:
        cnt = _count_occurrences(norm_text, compact, a)
        if cnt:
            hits["weak"].append({"anchor": a, "count": cnt, "source": "text"})

    for a in negative_anchors:
        cnt = _count_occurrences(norm_text, compact, a)
        if cnt:
            hits["negative"].append({"anchor": a, "count": cnt, "source": "text"})

    return hits


# ---------- Strategy 2: ai_anchor (LLM-assisted presence detection) ----------

_USE_AI = os.getenv("NPL_USE_AI_ANCHOR", "false").lower() in ("1", "true", "yes")

def _call_openai_for_anchors(text: str, strong: List[str], weak: List[str], neg: List[str]) -> Dict:
    """
    Call OpenAI to judge presence/absence of anchors, tolerant to OCR distortion.
    If OPENAI_API_KEY or NPL_USE_AI_ANCHOR is not set, returns empty detections.
    """
    if not _USE_AI or not os.getenv("OPENAI_API_KEY"):
        return {"strong": {}, "weak": {}, "negative": {}}

    try:
        # Lazy import to avoid hard dependency when disabled
        from openai import OpenAI
        client = OpenAI()

        anchor_list = {
            "strong": strong,
            "weak": weak,
            "negative": neg,
        }

        prompt = (
            "You are given OCR text from Brazilian legal documents. "
            "For each anchor, answer if it appears in the text, even if distorted by OCR.\n\n"
            "Return STRICT JSON with keys 'strong', 'weak', 'negative', each mapping to an object "
            "where keys are anchors and values are true/false.\n\n"
            f"Anchors: {json.dumps(anchor_list, ensure_ascii=False)}\n\n"
            f"Text:\n{text}"
        )

        completion = client.chat.completions.create(
            model=os.getenv("NPL_AI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = completion.choices[0].message["content"]
        return json.loads(content)
    except Exception:
        return {"strong": {}, "weak": {}, "negative": {}}


def find_anchors_ai(
    text: str,
    strong_anchors: List[str],
    weak_anchors: List[str],
    negative_anchors: List[str],
) -> AnchorsByStrength:
    result = _call_openai_for_anchors(text, strong_anchors, weak_anchors, negative_anchors)

    hits: AnchorsByStrength = {"strong": [], "weak": [], "negative": []}
    for strength in ("strong", "weak", "negative"):
        detected = result.get(strength, {}) or {}
        for anchor, present in detected.items():
            if present:
                hits[strength].append({"anchor": anchor, "present": True, "source": "ai"})
    return hits








def compact_text(text: str) -> str:
    """
    More aggressive: remove ALL whitespace after normalize_ocr_text.
    Useful for OCR where letters are spaced apart: 'p e n h o r a'.
    """
    t = normalize_ocr_text(text)
    return re.sub(r"\s+", "", t)

def extract_text_with_pypdf(pdf_path: str) -> str:
    """Extrai texto de cada página usando pypdf e remove NUL bytes."""
    reader = PdfReader(pdf_path)
    text_chunks: List[str] = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        text_chunks.append(page_text)
    full = "\n".join(text_chunks)
    return full.replace("\x00", "")

def extract_pages(pdf_path: str) -> List[Tuple[int, str]]:
    """Extrai cada página do PDF como (número_da_página, texto)."""
    reader = PdfReader(pdf_path)
    pages = []
    for idx, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append((idx, text.replace('\x00', '')))
    return pages

def segment_paragraphs_with_page(pages: List[Tuple[int, str]]) -> List[Tuple[int, str, int]]:
    """
    Divide cada texto de página em parágrafos.
    Retorna lista de (offset, parágrafo, número_da_página).
    """
    paragraphs = []
    for page_num, text in pages:
        offset = 0
        for para in re.split(r"\n\s*\n", text):
            para = para.strip()
            if para:
                pos = text.find(para, offset)
                paragraphs.append((pos, para, page_num))
                offset = pos + len(para)
    return paragraphs

def split_text_by_tokens(text: str, max_tokens: int = 2048) -> List[str]:
    """Divide um texto em chunks que não excedem o limite aproximado de tokens."""
    words = text.split()
    if len(words) <= max_tokens:
        return [text.strip()]
    sentences = re.split(r'(?<=[\.\!\?])\s+', text)
    chunks: List[str] = []
    current_chunk: List[str] = []
    current_tokens = 0
    for sent in sentences:
        sent_tokens = len(sent.split())
        if current_tokens + sent_tokens > max_tokens and current_chunk:
            chunks.append(" ".join(current_chunk))
            current_chunk = [sent]
            current_tokens = sent_tokens
        else:
            current_chunk.append(sent)
            current_tokens += sent_tokens
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    return chunks

def score_paragraph(
    rule,
    para_text: str,
    embed_client: EmbeddingClient,
    para_vec: Optional[np.ndarray] = None,
    sim_threshold: float = 0.5,
    use_synonyms: bool = True,
) -> Tuple[float, Dict[str, Any]]:
    """
    Calcula um score para um parágrafo combinando:
      - Âncoras fortes: +2 por ocorrência literal.
      - Âncoras fracas: +1 por ocorrência literal.
      - Sinônimos de âncoras fortes: +1 * similaridade (se use_synonyms=True).
      - Âncoras negativas: score = -100 (descarta).
    """
    lowered = para_text.lower()
    details: Dict[str, List[Dict[str, Any]]] = {
        "strong_literal": [],
        "weak_literal": [],
        "strong_synonyms": [],
        "weak_synonyms": [],
        "negative_matches": [],
    }
    score = 0.0
    for neg in rule.negative_anchor_list():
        if neg and neg.lower() in lowered:
            details["negative_matches"].append({"anchor": neg})
            return -100.0, details

    para_vec_cache: Optional[np.ndarray] = para_vec
    def ensure_para_vec() -> np.ndarray:
        nonlocal para_vec_cache
        if para_vec_cache is None:
            para_vec_cache = np.array(embed_client.embed_one(para_text), dtype=float)
        return para_vec_cache

    def cos_sim(a: np.ndarray, b: np.ndarray) -> float:
        denom = (np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0:
            return 0.0
        return float(np.dot(a, b) / denom)

    # Âncoras fortes
    for idx, strong in enumerate(rule.strong_anchor_list()):
        if not strong:
            continue
        count = lowered.count(strong.lower())
        if count:
            score += 2.0 * count
            details["strong_literal"].append({"anchor": strong, "count": count})
        elif use_synonyms and rule.anchor_embeddings and idx < len(rule.anchor_embeddings):
            try:
                pv = ensure_para_vec()
                anc_vec = np.array(rule.anchor_embeddings[idx], dtype=float)
                sim = cos_sim(pv, anc_vec)
                if sim >= sim_threshold:
                    score += 1.0 * sim
                    details["strong_synonyms"].append({"anchor": strong, "sim": sim})
            except Exception:
                pass

    # Âncoras fracas
    for weak in rule.weak_anchor_list():
        if not weak:
            continue
        count = lowered.count(weak.lower())
        if count:
            score += 1.0 * count
            details["weak_literal"].append({"anchor": weak, "count": count})

    return score, details

def convert_with_docling(pdf_path: str) -> dict:
    """Converte um PDF usando Docling e retorna JSON estruturado."""
    converter = DocumentConverter()
    result = converter.convert(pdf_path)
    doc = result.document
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

def classify_document_type_with_debug(text: str):
    """
    Versão com debug: para cada DocTypeRule, informa âncoras encontradas,
    pesos usados, score e confiança.
    """
    lowered = text.lower()

    STRONG_W = 2.0
    WEAK_W = 1.0
    NEG_W = -100.0

    debug_rows: List[Dict[str, Any]] = []

    best_type = "DESPACHO_MERO_EXPEDIENTE"
    best_conf = 0.3
    best_score = float("-inf")

    rules = list(models.DocTypeRule.objects.all())
    if not rules:
        # sem regras configuradas – comportamento antigo
        return best_type, best_conf, []

    for rule in rules:
        strong_anchors = _split_anchors(rule.anchors_strong)
        weak_anchors = _split_anchors(rule.anchors_weak)
        negative_anchors = _split_anchors(rule.anchors_negative)

        strong_matches = [a for a in strong_anchors if a and a in lowered]
        weak_matches = [a for a in weak_anchors if a and a in lowered]
        negative_matches = [a for a in negative_anchors if a and a in lowered]

        if negative_matches:
            score = NEG_W
        else:
            score = STRONG_W * len(strong_matches) + WEAK_W * len(weak_matches)

        if strong_matches and not negative_matches:
            conf = 0.9
        elif weak_matches and not negative_matches:
            conf = 0.6
        else:
            conf = 0.3

        debug_rows.append({
            "doc_type": rule.doc_type,
            "description": rule.description,
            "anchors": {
                "strong": strong_matches,
                "weak": weak_matches,
                "negative": negative_matches,
            },
            "weights": {
                "strong": STRONG_W,
                "weak": WEAK_W,
                "negative": NEG_W,
            },
            "score": score,
            "confidence": conf,
        })

        # escolhe o melhor tipo ignorando regras com âncoras negativas
        if not negative_matches and score > best_score:
            best_score = score
            best_type = rule.doc_type
            best_conf = conf

    # fallback se todas as regras forem descartadas por negativo
    if best_score == float("-inf"):
        best_type, best_conf = "DESPACHO_MERO_EXPEDIENTE", 0.3

    return best_type, best_conf, debug_rows

def classify_document_type(text: str):
    """
    Wrapper compatível com a versão antiga: retorna apenas (doc_type, confiança).
    """
    doc_type, conf, _ = classify_document_type_with_debug(text)
    return doc_type, conf


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