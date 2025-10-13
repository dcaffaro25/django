from celery import shared_task
from .services.reconciliation_service import ReconciliationService
from .models import ReconciliationTask

@shared_task(bind=True)
def match_many_to_many_task(self, db_id, data, tenant_id=None, auto_match_100=False):
    task_obj = ReconciliationTask.objects.get(id=db_id)
    try:
        task_obj.status = "running"
        task_obj.save(update_fields=["status", "updated_at"])
        result = ReconciliationService.match_many_to_many(data, tenant_id, auto_match_100=auto_match_100)
        task_obj.status = "completed"
        task_obj.result = result
        task_obj.save(update_fields=["status", "result", "updated_at"])
        return result
    except Exception as e:
        task_obj.status = "failed"
        task_obj.error_message = str(e)
        task_obj.save(update_fields=["status", "error_message", "updated_at"])
        raise


"""
Celery tasks for generating and updating vector embeddings via the
Railway Auth Proxy -> Embedding Gemma (Ollama-compatible) service.

Environment variables expected in the Celery/Django worker:
  EMBED_BASE_URL   # e.g. "http://auth-proxy.railway.internal:80"
  EMBED_API_KEY    # the same value you configured in the proxy (API_KEY)
  EMBED_MODEL      # default: "embeddinggemma:300m"
  EMBED_TIMEOUT_S  # default: 20
  EMBED_DIM        # default: 768
  EMBED_BATCH_SIZE # default: 128
  EMBED_LIMIT_PER_MODEL # per run limit, default: 2000
"""

from __future__ import annotations

import os
import math
import logging
from typing import Iterable, List, Sequence, Optional, Callable

import requests
from celery import shared_task
from django.db.models import Q
from django.db import transaction

from .models import Account, BankTransaction, Transaction

log = logging.getLogger(__name__)

# -------- Configuration --------
EMBED_BASE_URL   = os.getenv("EMBED_BASE_URL", "http://auth-proxy.railway.internal:80")
EMBED_PATH       = os.getenv("EMBED_PATH", "/api/embeddings")
EMBED_URL        = EMBED_BASE_URL.rstrip("/") + EMBED_PATH
EMBED_API_KEY    = os.getenv("EMBED_API_KEY")
EMBED_MODEL      = os.getenv("EMBED_MODEL", "embeddinggemma:300m")
EMBED_TIMEOUT    = float(os.getenv("EMBED_TIMEOUT_S", "20"))
EMBED_DIM        = int(os.getenv("EMBED_DIM", "768"))
BATCH_SIZE       = max(1, int(os.getenv("EMBED_BATCH_SIZE", "128")))
LIMIT_PER_MODEL  = max(1, int(os.getenv("EMBED_LIMIT_PER_MODEL", "2000")))

# Single shared session (connection pooling)
_session = requests.Session()
# Primary auth header for the proxy
if EMBED_API_KEY:
    _session.headers.update({"x-api-key": EMBED_API_KEY})
# Keep Bearer for compatibility with other gateways (harmless if unused)
if EMBED_API_KEY:
    _session.headers.update({"Authorization": f"Bearer {EMBED_API_KEY}"})
_session.headers.update({"content-type": "application/json"})


# -------- Helpers --------
def _chunk(seq: Sequence, size: int) -> Iterable[Sequence]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]

def _fit_dim(vec: Sequence[float] | None, dim: int) -> Optional[List[float]]:
    if vec is None:
        return None
    if len(vec) == dim:
        return list(vec)
    if len(vec) > dim:
        # Truncate excess dimensions (safer than failing)
        return list(vec[:dim])
    # Pad with zeros if shorter
    return list(vec) + [0.0] * (dim - len(vec))

def _normalize_text(s: str | None) -> str:
    return " ".join((s or "").split()).strip()

def _account_text(a: Account) -> str:
    parts = [a.name, a.description, a.key_words, a.examples]
    return " | ".join(p for p in map(_normalize_text, parts) if p)

def _tx_text(t: Transaction) -> str:
    # Enrich with amount & date helps clustering
    return _normalize_text(f"{t.description or ''} | amount={t.amount} | date={t.date}")

def _bank_text(b: BankTransaction) -> str:
    return _normalize_text(f"{b.description or ''} | amount={b.amount} | date={b.date}")

def _parse_embeddings(resp_json) -> List[List[float]]:
    """
    Supports both:
      {"embeddings": [[...], [...], ...]}
      {"data": [{"embedding":[...]}, ...]}
    """
    if isinstance(resp_json, dict):
        if "embeddings" in resp_json and isinstance(resp_json["embeddings"], list):
            return resp_json["embeddings"]
        if "data" in resp_json and isinstance(resp_json["data"], list):
            out = []
            for row in resp_json["data"]:
                if isinstance(row, dict) and "embedding" in row:
                    out.append(row["embedding"])
            if out:
                return out
    raise ValueError(f"Unexpected embeddings response schema: {resp_json!r}")

def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Calls the proxy -> Ollama /api/embeddings with Gemma model.
    Returns a list of vectors aligned with 'texts'.
    """
    if not texts:
        return []
    if not EMBED_API_KEY:
        raise RuntimeError("EMBED_API_KEY is not set, cannot call embedding service.")

    payload = {"model": EMBED_MODEL, "input": texts}

    r = _session.post(EMBED_URL, json=payload, timeout=EMBED_TIMEOUT)
    r.raise_for_status()
    vectors = _parse_embeddings(r.json())

    if len(vectors) != len(texts):
        # Defensive: keep alignment guarantees
        raise RuntimeError(f"Embedding count mismatch: got {len(vectors)} for {len(texts)} inputs.")

    # Fit dimension for pgvector field
    return [ _fit_dim(v, EMBED_DIM) for v in vectors ]


def _update_embeddings_qs(
    instances: List,
    make_text: Callable[[object], str],
    field_name: str,
) -> int:
    """
    Batch-embeds 'instances' and writes vectors to 'field_name'.
    """
    if not instances:
        return 0

    updated = 0
    # Build text payloads
    texts = [make_text(obj) for obj in instances]
    # Replace empty texts with a single space to avoid API errors; we will skip saving if empty.
    text_mask = [bool(t) for t in texts]
    texts_to_embed = [t if t else " " for t in texts]

    for block in _chunk(list(range(len(instances))), BATCH_SIZE):
        block_texts = [texts_to_embed[i] for i in block]
        # Call API for the block
        vectors = embed_texts(block_texts)

        with transaction.atomic():
            for idx, vec in zip(block, vectors):
                if not text_mask[idx]:
                    continue  # skip empty original text
                obj = instances[idx]
                if vec is None:
                    continue
                try:
                    setattr(obj, field_name, vec)
                    obj.save(update_fields=[field_name])
                    updated += 1
                except Exception as e:
                    log.warning("Failed saving embedding for %s id=%s: %s",
                                obj.__class__.__name__, getattr(obj, "id", None), e)

    return updated


# -------- Celery task --------
@shared_task(
    bind=True,
    autoretry_for=(requests.RequestException, RuntimeError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
    soft_time_limit=600,
)
def generate_missing_embeddings(self, per_model_limit: int | None = None) -> dict:
    """
    Periodic task that scans for rows missing embeddings and backfills them.
    Limits are applied per model to keep each run bounded.
    """
    limit = int(per_model_limit or LIMIT_PER_MODEL)

    # ---- Transactions ----
    tx_qs = (Transaction.objects
             .filter(Q(description_embedding__isnull=True) | Q(description_embedding=[]))
             .order_by("id")
             .only("id", "description", "amount", "date")[:limit])
    tx_list = list(tx_qs)
    tx_updated = _update_embeddings_qs(tx_list, _tx_text, "description_embedding")

    # ---- Bank Transactions ----
    btx_qs = (BankTransaction.objects
              .filter(Q(description_embedding__isnull=True) | Q(description_embedding=[]))
              .order_by("id")
              .only("id", "description", "amount", "date")[:limit])
    btx_list = list(btx_qs)
    btx_updated = _update_embeddings_qs(btx_list, _bank_text, "description_embedding")

    # ---- Accounts ----
    acc_qs = (Account.objects
              .filter(Q(account_description_embedding__isnull=True) | Q(account_description_embedding=[]))
              .order_by("id")
              .only("id", "name", "description", "key_words", "examples")[:limit])
    acc_list = list(acc_qs)
    acc_updated = _update_embeddings_qs(acc_list, _account_text, "account_description_embedding")

    result = {
        "transactions_updated": tx_updated,
        "bank_transactions_updated": btx_updated,
        "accounts_updated": acc_updated,
        "batch_size": BATCH_SIZE,
        "dim": EMBED_DIM,
        "model": EMBED_MODEL,
        "url": EMBED_URL,
    }
    log.info("Embedding backfill result: %s", result)
    return result
