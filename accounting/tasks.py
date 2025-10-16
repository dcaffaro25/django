from __future__ import annotations
import logging
from typing import List, Callable, Optional, Sequence
from celery import shared_task
from .services.reconciliation_service import ReconciliationService
from .models import ReconciliationTask
from django.db import transaction
from django.db.models import Q
from django.conf import settings
import os


import requests
from celery import shared_task


from .services.reconciliation_service import ReconciliationService
from .models import Account, BankTransaction, Transaction, ReconciliationTask
from .services.embedding_client import EmbeddingClient

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

def _nz(s: Optional[str]) -> str:
    return " ".join((s or "").split()).strip()

def _account_text(a: Account) -> str:
    parts = [a.name, a.description, a.key_words, a.examples]
    return " | ".join(p for p in map(_nz, parts) if p)

def _tx_text(t: Transaction) -> str:
    return _nz(f"{t.description or ''} | amount={t.amount} | date={t.date}")

def _bank_text(b: BankTransaction) -> str:
    return _nz(f"{b.description or ''} | amount={b.amount} | date={b.date}")

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
    texts = [make_text(o) or " " for o in instances]

    for i in range(0, len(instances), batch_size):
        idx = list(range(i, min(i + batch_size, len(instances))))
        block_texts = [texts[j] for j in idx]
        vectors = client.embed_texts(block_texts)

        with transaction.atomic():
            for j, vec in zip(idx, vectors):
                if not vec:
                    continue
                obj = instances[j]
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
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
    soft_time_limit=600,
)
def generate_missing_embeddings(self, per_model_limit: Optional[int] = None, client_opts: Optional[dict] = None) -> dict:
    limit = int(per_model_limit or settings.EMBED_LIMIT_PER_MODEL)

    client = EmbeddingClient(
        model=(client_opts or {}).get("model", settings.EMBED_MODEL),
        timeout_s=(client_opts or {}).get("timeout_s", settings.EMBED_TIMEOUT_S),
        dim=(client_opts or {}).get("dim", settings.EMBED_DIM),
        api_key=(client_opts or {}).get("api_key"),
        num_thread=(client_opts or {}).get("num_thread", settings.EMBED_NUM_THREAD),
        keep_alive=(client_opts or {}).get("keep_alive", settings.EMBED_KEEP_ALIVE),
        base_url=(client_opts or {}).get("base_url"),   # if you want to override internal
        path=(client_opts or {}).get("path", settings.EMBED_PATH),
        extra_headers=(client_opts or {}).get("extra_headers"),
    )

    tx_list = list(
        Transaction.objects
        .filter(description_embedding__isnull=True)
        .order_by("id")
        .only("id", "description", "amount", "date")[:limit]
    )
    btx_list = list(
        BankTransaction.objects
        .filter(description_embedding__isnull=True)
        .order_by("id")
        .only("id", "description", "amount", "date")[:limit]
    )
    acc_list = list(
        Account.objects
        .filter(account_description_embedding__isnull=True)
        .order_by("id")
        .only("id", "name", "description", "key_words", "examples")[:limit]
    )

    tx_updated  = _update_embeddings_qs(client, tx_list,  _tx_text,   "description_embedding", settings.EMBED_BATCH_SIZE)
    btx_updated = _update_embeddings_qs(client, btx_list, _bank_text, "description_embedding", settings.EMBED_BATCH_SIZE)
    acc_updated = _update_embeddings_qs(client, acc_list, _account_text, "account_description_embedding", settings.EMBED_BATCH_SIZE)

    out = {
        "transactions_updated": tx_updated,
        "bank_transactions_updated": btx_updated,
        "accounts_updated": acc_updated,
        "model": client.model,
        "url": client.url,
        "dim": client.dim,
        "batch_size": settings.EMBED_BATCH_SIZE,
        "used_internal": bool(settings.EMBED_INTERNAL_HOST),
    }
    log.info("Embedding backfill result: %s", out)
    return out