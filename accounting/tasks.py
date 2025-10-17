from __future__ import annotations
import logging
import time
from typing import List, Callable, Optional, Sequence
from django.core.cache import cache
from celery import shared_task, states
from celery.exceptions import Ignore
from .services.reconciliation_service import ReconciliationService
from .models import ReconciliationTask
from django.db import transaction
from django.db.models import Q
from django.conf import settings
import os


import requests


from .services.reconciliation_service import ReconciliationService
from .models import Account, BankTransaction, Transaction, ReconciliationTask
from .services.embedding_client import EmbeddingClient

log = logging.getLogger(__name__)

CANCEL_KEY_PREFIX = "embed:cancel:"  # cache key for graceful cancel

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

def _count_missing():
    return {
        "transactions": Transaction.objects.filter(description_embedding__isnull=True).count(),
        "bank_transactions": BankTransaction.objects.filter(description_embedding__isnull=True).count(),
        "accounts": Account.objects.filter(account_description_embedding__isnull=True).count(),
    }

def _prog_template(totals: dict) -> dict:
    done = {k: 0 for k in totals}
    return {
        "status": "queued",
        "started_at": time.time(),
        "model": settings.EMBED_MODEL,
        "url": f"{settings.EMBED_BASE_URL.rstrip('/')}{settings.EMBED_PATH}",
        "batch_size": settings.EMBED_BATCH_SIZE,
        "totals": totals,
        "done": done,
        "remaining": totals.copy(),
        "done_all": 0,
        "remaining_all": sum(totals.values()),
        "last_batch": None,
        "errors": [],
    }

def _bump_progress(meta: dict, cat: str, n: int):
    meta["done"][cat] += n
    meta["remaining"][cat] = max(0, meta["totals"][cat] - meta["done"][cat])
    meta["done_all"] = sum(meta["done"].values())
    meta["remaining_all"] = sum(meta["remaining"].values())
    meta["last_batch"] = {"category": cat, "n": n, "ts": time.time()}
    meta["status"] = "running"

def _check_cancel(self) -> bool:
    return bool(cache.get(f"{CANCEL_KEY_PREFIX}{self.request.id}"))

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
    
    # ---- initialize progress & totals ----
    totals = _count_missing()
    prog = _prog_template(totals)
    self.update_state(state=states.STARTED, meta=prog)
    
    # helpers
    def process_category(cat_name: str, qs, text_fn: Callable[[object], str], field_name: str) -> int:
        if _check_cancel(self):
            prog["status"] = "canceled"
            self.update_state(state=states.REVOKED, meta=prog)
            raise Ignore()

        objs = list(qs.order_by("id")[:limit])
        updated_total = 0

        for i in range(0, len(objs), settings.EMBED_BATCH_SIZE):
            if _check_cancel(self):
                prog["status"] = "canceled"
                self.update_state(state=states.REVOKED, meta=prog)
                raise Ignore()

            block = objs[i:i+settings.EMBED_BATCH_SIZE]
            texts = [text_fn(o) or " " for o in block]
            try:
                vectors = client.embed_texts(texts)
            except Exception as e:
                prog["errors"].append({"category": cat_name, "index_start": i, "err": str(e), "ts": time.time()})
                # keep going; just no update bump for this batch
                self.update_state(state="PROGRESS", meta=prog)
                continue

            batch_updated = 0
            with transaction.atomic():
                for obj, vec in zip(block, vectors):
                    if not vec:  # skip empties
                        continue
                    try:
                        setattr(obj, field_name, vec)
                        obj.save(update_fields=[field_name])
                        batch_updated += 1
                    except Exception as se:
                        prog["errors"].append({"category": cat_name, "obj_id": getattr(obj, "id", None), "err": str(se), "ts": time.time()})

            updated_total += batch_updated
            _bump_progress(prog, cat_name, batch_updated)
            self.update_state(state="PROGRESS", meta=prog)

        return updated_total
    
        # ---- process each category ----
        tx_qs  = Transaction.objects.filter(description_embedding__isnull=True).only("id", "description", "amount", "date")
        btx_qs = BankTransaction.objects.filter(description_embedding__isnull=True).only("id", "description", "amount", "date")
        acc_qs = Account.objects.filter(account_description_embedding__isnull=True).only("id", "name", "description", "key_words", "examples")
    
        tx_upd  = process_category("transactions",       tx_qs,  _tx_text,    "description_embedding")
        btx_upd = process_category("bank_transactions",  btx_qs, _bank_text,   "description_embedding")
        acc_upd = process_category("accounts",           acc_qs, _account_text,"account_description_embedding")
    
        result = {
            "transactions_updated": tx_upd,
            "bank_transactions_updated": btx_upd,
            "accounts_updated": acc_upd,
            "model": client.model,
            "url": client.url,
            "dim": client.dim,
            "batch_size": settings.EMBED_BATCH_SIZE,
            "duration_s": round(time.time() - prog["started_at"], 3),
        }
    
        prog["status"] = "completed"
        prog["finished_at"] = time.time()
        prog["result"] = result
        self.update_state(state=states.SUCCESS, meta=prog)
        log.info("Embedding backfill result: %s", result)
        return result