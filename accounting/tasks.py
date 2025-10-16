from __future__ import annotations
from celery import shared_task
from .services.reconciliation_service import ReconciliationService
from .models import ReconciliationTask
import logging
import os
from typing import Callable, List, Optional, Sequence

import requests
from celery import shared_task
from django.db import transaction
from django.db.models import Q

from .services.reconciliation_service import ReconciliationService
from .models import Account, BankTransaction, Transaction, ReconciliationTask

log = logging.getLogger(__name__)
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


# Env defaults
DEF_BASE_URL   = os.getenv("EMBED_BASE_URL", "https://embedding-service.up.railway.app")
DEF_PATH       = os.getenv("EMBED_PATH", "/api/embeddings")
DEF_API_KEY    = os.getenv("EMBED_API_KEY")  # optional
DEF_MODEL      = os.getenv("EMBED_MODEL", "nomic-embed-text")
DEF_TIMEOUT    = float(os.getenv("EMBED_TIMEOUT_S", "30"))
DEF_DIM        = int(os.getenv("EMBED_DIM", "768"))
DEF_BATCH_SIZE = max(1, int(os.getenv("EMBED_BATCH_SIZE", "128")))
DEF_LIMIT      = max(1, int(os.getenv("EMBED_LIMIT_PER_MODEL", "2000")))
DEF_KEEP_ALIVE = os.getenv("EMBED_KEEP_ALIVE", "45m")
NUM_THREAD  = int(os.getenv("EMBED_NUM_THREAD", "8"))

def _nz(s: Optional[str]) -> str:
    return " ".join((s or "").split()).strip()

def _account_text(a: Account) -> str:
    parts = [a.name, a.description, a.key_words, a.examples]
    return " | ".join(p for p in map(_nz, parts) if p)

def _tx_text(t: Transaction) -> str:
    return _nz(f"{t.description or ''} | amount={t.amount} | date={t.date}")

def _bank_text(b: BankTransaction) -> str:
    return _nz(f"{b.description or ''} | amount={b.amount} | date={b.date}")


class EmbeddingClient:
    """
    Calls an Ollama-compatible /api/embeddings endpoint.
    Tries batch {'input': [...]} first, falls back to per-item {'prompt': '...'}.
    Supports response shapes: {"embedding":[...]}, {"embeddings":[...]}, {"data":[{"embedding":[...]}...]}
    """
    def __init__(
        self,
        base_url: str = DEF_BASE_URL,
        path: str = DEF_PATH,
        model: str = DEF_MODEL,
        api_key: Optional[str] = DEF_API_KEY,
        timeout_s: float = DEF_TIMEOUT,
        dim: int = DEF_DIM,
        extra_headers: Optional[dict] = None,
    ):
        self.url = (base_url.rstrip("/") + path) if path else base_url.rstrip("/")
        self.model = model
        self.timeout = timeout_s
        self.dim = dim

        self.session = requests.Session()
        self.session.headers.update({"content-type": "application/json"})
        if api_key:
            self.session.headers.update({
                "Authorization": f"Bearer {api_key}",
                "X-API-Key": api_key,
            })
        if extra_headers:
            self.session.headers.update(extra_headers)

    @staticmethod
    def _fit_dim(vec: Sequence[float] | None, dim: int) -> Optional[List[float]]:
        if vec is None:
            return None
        if len(vec) == dim:
            return list(vec)
        if len(vec) > dim:
            return list(vec[:dim])
        return list(vec) + [0.0] * (dim - len(vec))

    @staticmethod
    def _parse_json(resp_json):
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
            if "embedding" in resp_json and isinstance(resp_json["embedding"], list):
                return [resp_json["embedding"]]  # single vector wrapped into list
        raise ValueError(f"Unexpected embedding response: {resp_json!r}")

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        # Try batch first
        '''
        try:
            r = self.session.post(
                self.url, 
                json={
                    "model": self.model, 
                    "prompt": texts, 
                    "options": {"num_thread": NUM_THREAD},
                    "keep_alive": DEF_KEEP_ALIVE
                    }, 
                timeout=self.timeout)
            
            r.raise_for_status()
            vectors = self._parse_json(r.json())
            if len(vectors) == len(texts) and all(vectors):
                return [self._fit_dim(v, self.dim) for v in vectors]
        except Exception:
            pass  # fall back to per-item
        '''
        # Fallback: per-item 'prompt' (works reliably with embeddinggemma)
        out: List[List[float]] = []
        for t in texts:
            t = _nz(t)
            if not t:
                out.append([]); continue
            rr = self.session.post(self.url, json={"model": self.model, "prompt": t, "options": {"num_thread": NUM_THREAD}, "keep_alive": DEF_KEEP_ALIVE}, timeout=self.timeout)
            rr.raise_for_status()
            vv = self._parse_json(rr.json())
            if not vv or not vv[0]:
                raise RuntimeError("Embedding service returned empty vector")
            out.append(self._fit_dim(vv[0], self.dim))
        return out
        

# Module-level default client + thin wrappers for reuse in views/tests
_default_client = EmbeddingClient()

def embed_texts(texts: List[str]) -> List[List[float]]:
    return _default_client.embed_texts(texts)

def embed_one(text: str) -> List[float]:
    vecs = _default_client.embed_texts([text])
    if not vecs or not vecs[0]:
        raise RuntimeError("empty embedding from backend")
    return vecs[0]


def _update_embeddings_qs(
    client: EmbeddingClient,
    instances: List,
    make_text: Callable[[object], str],
    field_name: str,
    batch_size: int,
) -> int:
    if not instances:
        return 0

    updated = 0
    texts = [make_text(obj) or " " for obj in instances]

    for i in range(0, len(instances), batch_size):
        block_idx = list(range(i, min(i + batch_size, len(instances))))
        block_texts = [texts[j] for j in block_idx]
        vectors = client.embed_texts(block_texts)

        with transaction.atomic():
            for idx, vec in zip(block_idx, vectors):
                if not vec:
                    continue
                obj = instances[idx]
                try:
                    setattr(obj, field_name, vec)
                    obj.save(update_fields=[field_name])
                    updated += 1
                except Exception as e:
                    log.warning("Failed saving embedding for %s id=%s: %s",
                                obj.__class__.__name__, getattr(obj, "id", None), e)
    return updated


@shared_task(
    bind=True,
    autoretry_for=(requests.RequestException, RuntimeError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
    soft_time_limit=600,
)
def generate_missing_embeddings(self, per_model_limit: Optional[int] = None, client_opts: Optional[dict] = None) -> dict:
    limit = int(per_model_limit or DEF_LIMIT)

    co = client_opts or {}
    client = EmbeddingClient(
        base_url=co.get("base_url", DEF_BASE_URL),
        path=co.get("path", DEF_PATH),
        model=co.get("model", DEF_MODEL),
        api_key=co.get("api_key", DEF_API_KEY),
        timeout_s=float(co.get("timeout_s", DEF_TIMEOUT)),
        dim=int(co.get("dim", DEF_DIM)),
        extra_headers=co.get("extra_headers"),
    )

    # Transactions (only check NULL; pgvector won’t store empty lists)
    tx_list = list(
        Transaction.objects
        .filter(description_embedding__isnull=True)
        .order_by("id")
        .only("id", "description", "amount", "date")[:limit]
    )
    tx_updated = _update_embeddings_qs(client, tx_list, _tx_text, "description_embedding", DEF_BATCH_SIZE)

    # Bank transactions
    btx_list = list(
        BankTransaction.objects
        .filter(description_embedding__isnull=True)
        .order_by("id")
        .only("id", "description", "amount", "date")[:limit]
    )
    btx_updated = _update_embeddings_qs(client, btx_list, _bank_text, "description_embedding", DEF_BATCH_SIZE)

    # Accounts
    acc_list = list(
        Account.objects
        .filter(account_description_embedding__isnull=True)
        .order_by("id")
        .only("id", "name", "description", "key_words", "examples")[:limit]
    )
    acc_updated = _update_embeddings_qs(client, acc_list, _account_text, "account_description_embedding", DEF_BATCH_SIZE)

    out = {
        "transactions_updated": tx_updated,
        "bank_transactions_updated": btx_updated,
        "accounts_updated": acc_updated,
        "model": client.model,
        "url": client.url,
        "dim": client.dim,
        "batch_size": DEF_BATCH_SIZE,
    }
    log.info("Embedding backfill result: %s", out)
    return out