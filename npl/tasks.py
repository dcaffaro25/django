"""
Celery tasks for the NPL application.

Tasks encapsulate the heavy lifting required to process documents.  The OCR
pipeline extracts text using multiple OCR engines, selects the best result per
page, performs document type classification and initiates weak labelling and
embedding.  Subsequent tasks map spans to events, generate structured data
models, index the data for search and compute pricing estimates.
"""
from __future__ import annotations

import hashlib
import io
import logging
import re
from datetime import date
from typing import Any, Dict, List

import pytesseract
from celery import shared_task, group
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from decimal import Decimal
from .utils import convert_with_docling, extract_process_number, classify_document_type


import warnings

from . import models, utils

try:
    import pdfminer.high_level as pdfminer_high
except ImportError:
    pdfminer_high = None  # type: ignore

try:
    import pdfplumber
except ImportError:
    pdfplumber = None  # type: ignore

from . import models
from . import utils

logger = logging.getLogger(__name__)


def _compute_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _run_tesseract(image_bytes: bytes, lang: str = 'por+eng', psm: int = 3) -> str:
    """Run pytesseract on an image buffer with given parameters."""
    try:
        from PIL import Image
    except ImportError:
        raise RuntimeError("Pillow is required for OCR but not installed.")
    with Image.open(io.BytesIO(image_bytes)) as img:
        config = f'--psm {psm}'
        return pytesseract.image_to_string(img, lang=lang, config=config)


@shared_task
def ocr_pipeline_task(document_id: int) -> None:
    """
    Executa o OCR e a classificação inicial de um documento.

    - Converte o PDF usando Docling sempre que possível.
    - Se Docling falhar, aplica OCR multi-engine (pdfminer + Tesseract).
    - Atualiza campos de texto OCR e metadados.
    - Extrai o número do processo e vincula ao documento (criando um Process se necessário).
    - Classifica o doc_type com base em âncoras.
    - Enfileira tarefas seguintes: weak labelling, mapping events, embeddings e indexação.
    """
    document = models.Document.objects.get(pk=document_id)
    pdf_path = document.file.path

    full_text = ""
    ocr_data = {}
    try:
        # Tenta converter com Docling
        parsed_doc = convert_with_docling(pdf_path)
        # Concatena textos dos blocos
        full_text = "\n".join(block["text"] for block in parsed_doc.get("blocks", []))
        ocr_data = parsed_doc
        logger.info("Docling processou %s com sucesso", document_id)
    except Exception as e:
        logger.warning("Docling falhou para %s: %s; recorrendo ao OCR multi-engine",
                       document_id, e)
        # Fallback: OCR multi-engine
        aggregated_text_parts = []
        per_page_results = []
        # Extração de texto nativo com pdfminer (pode falhar silenciosamente)
        pdf_text = []
        try:
            from pdfminer.high_level import extract_text
            text = extract_text(pdf_path)
            pdf_text = text.split("\f")
        except Exception as e_miner:
            logger.warning("pdfminer falhou para %s: %s", document_id, e_miner)

        try:
            import pdfplumber
            from PIL import Image
            import pytesseract
        except ImportError as ie:
            logger.error("Dependências de OCR não estão instaladas: %s", ie)
            pdfplumber = None

        if pdfplumber:
            try:
                # Suprime alertas de cores inválidas em PDFs corrompidos
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore", message="Cannot set gray non-stroke color"
                    )
                    with pdfplumber.open(pdf_path) as pdf:
                        for idx, page in enumerate(pdf.pages):
                            try:
                                native = pdf_text[idx].strip() if idx < len(pdf_text) else ""
                                candidates = []
                                if native:
                                    candidates.append({
                                        "engine": "pdfminer",
                                        "profile": "native",
                                        "text": native,
                                        "confidence": 1.0,
                                    })
                                # Renderiza página para imagem (200 dpi)
                                img = page.to_image(resolution=200)
                                buf = io.BytesIO()
                                img.save(buf, format="PNG")
                                image_bytes = buf.getvalue()
                                # Perfil A (psm 3)
                                text_a = pytesseract.image_to_string(
                                    Image.open(io.BytesIO(image_bytes)),
                                    lang="por+eng",
                                    config="--psm 3"
                                )
                                candidates.append({
                                    "engine": "tesseract",
                                    "profile": "A",
                                    "text": text_a,
                                    "confidence": 0.8,
                                })
                                # Perfil B (psm 6)
                                text_b = pytesseract.image_to_string(
                                    Image.open(io.BytesIO(image_bytes)),
                                    lang="por+eng",
                                    config="--psm 6"
                                )
                                candidates.append({
                                    "engine": "tesseract",
                                    "profile": "B",
                                    "text": text_b,
                                    "confidence": 0.7,
                                })
                                # Seleciona o candidato com mais tokens jurídicos, menos caracteres inválidos etc.
                                best = max(
                                    candidates,
                                    key=lambda c: (
                                        c["confidence"]
                                        + sum(1 for t in ["art.", "§", "CPC"] if t in c["text"])
                                        - sum(1 for ch in c["text"] if not ch.isprintable())
                                    ),
                                    default={"engine": "", "profile": "", "text": "", "confidence": 0.0},
                                )
                                per_page_results.append(best)
                                aggregated_text_parts.append(best["text"])
                            except Exception as e_page:
                                logger.warning("Erro ao processar página %s do doc %s: %s",
                                               idx, document_id, e_page)
                                continue
            except Exception as e_plumber:
                logger.exception("Falha ao abrir PDF com pdfplumber para %s: %s", document_id, e_plumber)

        full_text = "\n\n".join(aggregated_text_parts)
        ocr_data = {"pages": per_page_results}

    # Atualiza o documento com o texto OCR e dados completos
    document.ocr_text = full_text
    document.ocr_data = ocr_data

    # Classifica o tipo de documento e confiança
    doc_type, doc_confidence = classify_document_type(full_text)
    document.doc_type = doc_type
    document.doctype_confidence = doc_confidence

    # Extrai o número do processo, criando/vinculando Process
    process_number = extract_process_number(full_text)
    if process_number:
        process, _ = models.Process.objects.get_or_create(case_number=process_number)
        document.process = process
        document.process_number_raw = process_number
        document.no_process_found = False
    else:
        document.no_process_found = True

    # Salva todas as alterações atomicamente
    with transaction.atomic():
        document.save()

    # Enfileira ou executa diretamente as tarefas subsequentes
    try:
        from kombu.exceptions import OperationalError
        # Weak labelling: extrai spans e sugere E-codes
        weak_labelling_task.delay(document.id)
    except OperationalError:
        # Sem broker (ex.: ambiente local) => executa inline
        weak_labelling_task(document.id)


@shared_task
def weak_labelling_task(document_id: int) -> None:
    """Extract spans from the document and suggest event codes.

    Uses heuristics to locate sections such as report, fundamentação and
    dispositivo, then finds domain‑specific phrases for penhora, leilão, etc.
    Stores Span objects in the database and schedules embedding and indexing.
    """
    document = models.Document.objects.get(pk=document_id)
    text = document.ocr_text
    spans: List[models.Span] = []
    # Heuristics: find positions of key section headings
    patterns = [
        ('CABECALHO', r'(?i)^(.*?)(?=RELAT[ÓO]RIO|RELATORIO|RELATÓRIO)'),
        ('RELATORIO', r'(?i)RELAT[ÓO]RIO'),
        ('FUNDAMENTACAO', r'(?i)FUNDAMENTA[ÇC][ÃA]O'),
        ('DISPOSITIVO', r'(?i)DISPOSITIV[AO]'),
        ('PENHORA', r'(?i)penhora'),
        ('LEILAO', r'(?i)leil[aã]o'),
    ]
    for label, pattern in patterns:
        for m in re.finditer(pattern, text):
            start = m.start()
            end = m.end()
            snippet = text[start:end]
            span = models.Span.objects.create(
                document=document,
                label=label,
                text=snippet,
                page=0,  # page unknown when scanning the full text
                char_start=start,
                char_end=end,
                confidence=0.6,
            )
            spans.append(span)
    # After extracting spans, schedule embeddings and suggestions
    for span in spans:
        embed_span_task.delay(span.id)
    # Map to event suggestions (but don't persist events yet)
    # Suggest mapping can be stored in document.extra if desired


@shared_task
def embed_span_task(span_id: int) -> None:
    """Generate dense embeddings for a span using two models.

    If sentence‑transformers is available, produce actual embeddings.  Otherwise
    generate random vectors of fixed dimension to allow the rest of the pipeline
    to function.  The vectors are saved in SpanEmbedding records.
    """
    span = models.Span.objects.get(pk=span_id)
    text = span.text
    model_names = [settings.EMBEDDING_MODEL_A, settings.EMBEDDING_MODEL_B]
    dims = [384, 384]
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception:
        SentenceTransformer = None  # type: ignore
    vectors: List[List[float]] = []
    if SentenceTransformer:
        for model_name in model_names:
            try:
                model = SentenceTransformer(model_name)
                vec = model.encode(text, normalize_embeddings=True).tolist()
                vectors.append(vec)
            except Exception as e:
                logger.exception("embedding failed for %s: %s", model_name, e)
                vectors.append([0.0] * dims[0])
    else:
        import random
        for _ in model_names:
            vec = [random.random() for _ in range(dims[0])]
            vectors.append(vec)
    for model_name, vec in zip(model_names, vectors):
        models.SpanEmbedding.objects.create(
            span=span,
            model_name=model_name,
            dim=len(vec),
            vector=vec,
            version='v0'
        )
    # After embedding, index the span for search
    index_span_task.delay(span.id)


@shared_task
def index_span_task(span_id: int) -> None:
    """Index a span into the search engine (Meilisearch)."""
    span = models.Span.objects.get(pk=span_id)
    doc = span.document
    record = {
        'id': f"span-{span.id}",
        'document_id': doc.id,
        'process_id': doc.process_id,
        'label': span.label,
        'label_subtype': span.label_subtype,
        'text': span.text,
    }
    # Add dense vectors
    embeddings = {embed.model_name: embed.vector for embed in span.embeddings.all()}
    record.update({f'vec_{k}': v for k, v in embeddings.items()})
    # Send to Meilisearch index
    try:
        import requests
        host = settings.SEARCH_HOST.rstrip('/')
        index_name = 'spans'
        url = f"{host}/indexes/{index_name}/documents"
        # Create index if necessary
        requests.post(f"{host}/indexes", json={'uid': index_name})
        resp = requests.post(url, json=[record])
        resp.raise_for_status()
    except Exception as e:
        logger.warning("Failed to index span %s: %s", span.id, e)


@shared_task
def apply_events_task(document_id: int) -> None:
    """Map spans to E‑code events and create structured models."""
    document = models.Document.objects.get(pk=document_id)
    # Se não houver processo, não é possível mapear eventos
    if not document.process:
        logger.warning(
            "apply_events_task chamado para documento %s sem processo; ignorando",
            document_id
        )
        return
    spans = document.spans.all()
    for span in spans:
        codes = utils.map_span_to_event_codes(span)
        for code in codes:
            event_type, _ = models.EventType.objects.get_or_create(code=code, defaults={'description': code})
            event = models.CourtEvent.objects.create(
                process=document.process,
                event_type=event_type,
                date=date.today(),
                description=f"Event derived from span {span.label}"
            )
            models.CourtEventEvidence.objects.create(
                event=event,
                span=span,
                document=document,
                evidence_confidence=span.confidence,
                notes='auto'
            )
            # Create structured models if applicable
            if code.startswith('E032') or 'PENHORA' in span.label.upper():
                models.Seizure.objects.create(
                    event=event,
                    span=span,
                    subtype=span.label_subtype,
                    amount=None,
                    asset_identifier='',
                    status='ordenada',
                )


@shared_task
def pricing_task(process_id: int) -> None:
    """Calculate a pricing estimate for a process based on events."""
    process = models.Process.objects.get(pk=process_id)
    events = process.events.all()
    total = Decimal('0.00')
    details: Dict[str, Any] = {}
    for event in events:
        code = event.event_type.code
        # Uplifts and penalties simplified
        if code in ('E010', 'E012'):
            # 523 arts. 523: uplift 10% +10%
            total += Decimal('0.20')
            details[code] = 'uplift_20pct'
        elif code.startswith('E032'):
            total += Decimal('0.05')
            details[code] = 'penhora'
        else:
            total += Decimal('0.01')
            details[code] = 'base'
    pricing = models.PricingRun.objects.create(process=process, details=details, total_price=total)
    models.ProcessPricing.objects.create(process=process, price=total)