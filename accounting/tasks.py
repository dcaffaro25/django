from __future__ import annotations
import logging
import time
from typing import List, Callable, Optional, Sequence
from django.core.cache import cache
from celery import shared_task, states
from celery.exceptions import Ignore, SoftTimeLimitExceeded
from .services.reconciliation_service import ReconciliationService
from .models import ReconciliationTask, ReconciliationSuggestion
from django.db import transaction
from django.db.models import Q
from django.conf import settings
import os
from django.utils import timezone

from core.utils.jobs import job_progress
from core.models import Job

import requests
from celery.utils.log import get_task_logger
logger = get_task_logger(__name__)

from .services.reconciliation_service import ReconciliationService
from .models import Account, BankTransaction, Transaction, ReconciliationTask
from .services.embedding_client import EmbeddingClient
from multitenancy.utils import resolve_tenant  # <-- NOVO IMPORT

log = logging.getLogger(__name__)

from accounting.utils import update_journal_entries_and_transaction_flags

@shared_task(bind=True)
def recalc_unposted_flags_task(self) -> dict:
    """
    Iterate over all transactions where state != 'posted' and recompute the
    is_balanced / is_reconciled flags on each journal entry and its parent
    transaction.  Returns a count of updated transactions.
    """
    updated_count = 0
    # Use a single transaction for consistency
    with transaction.atomic():
        unposted_txs = (
            Transaction.objects
            .exclude(state='posted')
            .select_related('company', 'currency', 'entity')
            .prefetch_related('journal_entries__account__bank_account',
                              'journal_entries__reconciliations')
        )
        for tx in unposted_txs:
            # Gather all journal entries for this transaction
            entries = list(tx.journal_entries.all())
            if entries:
                # This helper recomputes is_cash, is_reconciled on each JE,
                # and is_balanced, is_reconciled on the transaction
                update_journal_entries_and_transaction_flags(entries)
                updated_count += 1
    return {"updated_transactions": updated_count}

CANCEL_KEY_PREFIX = "embed:cancel:"  # cache key for graceful cancel
STATE_MAP = {
    "PENDING":  "PENDING",
    "RECEIVED": "RECEIVED",
    "SENT":     "SENT",
    "STARTED":  "STARTED",
    "PROGRESS": "PROGRESS",   # our custom state while updating meta
    "RETRY":    "RETRY",
    "SUCCESS":  "SUCCESS",
    "FAILURE":  "FAILURE",
    "REVOKED":  "REVOKED",
}

# NOVO: parâmetros padrão do flush incremental de sugestões
RECON_SUGGESTION_FLUSH_SIZE = int(getattr(settings, "RECON_SUGGESTION_FLUSH_SIZE", 500))
RECON_SUGGESTION_FLUSH_SECONDS = float(getattr(settings, "RECON_SUGGESTION_FLUSH_SECONDS", 30.0))

DEFAULT_SUGGESTION_FLUSH_INTERVAL = int(getattr(settings, "RECON_SUGGESTION_FLUSH_INTERVAL", 30))

@shared_task(bind=True)
def match_many_to_many_task(self, db_id, data, tenant_id=None, auto_match_100=False):
    """
    Celery task wrapper that calls ReconciliationService.match_many_to_many
    with an incremental on_suggestion callback. Persists suggestions in
    batches and updates the ReconciliationTask object as we go.
    """
    task_obj = ReconciliationTask.objects.get(id=db_id)

    # ---- NOVO: resolver company_id independentemente do ReconciliationTask model ----
    # Prefer explicit company in payload -> resolve tenant -> fallback None
    company_id = None
    try:
        company_id = data.get("company_id", None)
    except Exception:
        company_id = None

    if company_id is None:
        try:
            # tenant_id é o que vem do request/context; resolve_tenant retorna company/tenant object
            if tenant_id:
                company_obj = resolve_tenant(tenant_id)
                company_id = getattr(company_obj, "id", None)
        except Exception:
            company_id = None

    flush_interval = DEFAULT_SUGGESTION_FLUSH_INTERVAL

    # buffer for pending suggestion model instances to bulk_create
    buffer: List[ReconciliationSuggestion] = []
    last_flush_ts = time.monotonic()

    def flush_buffer(force=False):
        nonlocal buffer, last_flush_ts
        if not buffer:
            return
        try:
            ReconciliationSuggestion.objects.bulk_create(buffer, batch_size=1000)
            # after inserting we clear buffer and update counts on task object
            created = len(buffer)
            buffer = []
            task_obj.suggestion_count = (task_obj.suggestion_count or 0) + created
            task_obj.updated_at = timezone.now()
            task_obj.save(update_fields=["suggestion_count", "updated_at"])
            last_flush_ts = time.monotonic()
            log.debug("Flushed %d suggestions for task %s", created, db_id)
        except Exception as e:
            log.exception("Failed to flush suggestions buffer for task %s: %s", db_id, e)
            # don't raise — best effort flush

    # callback to receive each suggestion as produced by the engine
    def on_suggestion(s: dict) -> None:
        nonlocal buffer, last_flush_ts, company_id
        try:
            # Prefer company_id provided inside suggestion payload, else fallback to outer-resolved company_id
            sugg_company_id = s.get("company_id") or company_id

            # build a lightweight ReconciliationSuggestion instance (not saved yet)
            rs = ReconciliationSuggestion(
                task=task_obj,
                company_id=sugg_company_id,
                match_type=s.get("match_type", "") or "",
                confidence_score=s.get("confidence_score", 0.0) or 0.0,
                abs_amount_diff=s.get("abs_amount_diff", 0.0) or 0.0,
                bank_ids=s.get("bank_ids", []) or [],
                journal_entry_ids=s.get("journal_entries_ids", []) or [],
                payload=s,
            )
            buffer.append(rs)
        except Exception as e:
            # Defensive: never let a single suggestion crash the whole task
            log.exception("Error buffering suggestion for task %s: %s", db_id, e)

        now = time.monotonic()
        if now - last_flush_ts >= flush_interval:
            flush_buffer()

    try:
        task_obj.status = "running"
        task_obj.save(update_fields=["status", "updated_at"])

        logger.info("Task %s started: bank_ids=%s book_ids=%s config_id=%s pipeline_id=%s",
                    db_id, data.get("bank_ids"), data.get("book_ids"),
                    data.get("config_id"), data.get("pipeline_id"))

        # Call service with streaming callback
        result = ReconciliationService.match_many_to_many(
            data,
            tenant_id,
            auto_match_100=auto_match_100,
            on_suggestion=on_suggestion,
        )

        # final flush of buffered suggestions
        flush_buffer(force=True)

        suggestions = result.get("suggestions", []) or []
        auto_info = result.get("auto_match", {}) or {}
        stats = result.get("stats", {}) or {}

        # If suggestions were created incrementally above, we still create any that
        # remain in suggestions list (defensive: avoid duplicates)
        to_create = []
        for s in suggestions:
            bank_ids = s.get("bank_ids", []) or []
            journal_ids = s.get("journal_entries_ids", []) or []
            # Use an equality check on both arrays to avoid duplicates (works with ArrayField)
            exists = ReconciliationSuggestion.objects.filter(
                task=task_obj,
                bank_ids=bank_ids,
                journal_entry_ids=journal_ids
            ).exists()
            if not exists:
                to_create.append(
                    ReconciliationSuggestion(
                        task=task_obj,
                        company_id=stats.get("company_id") or company_id,
                        match_type=s.get("match_type", "") or "",
                        confidence_score=s.get("confidence_score", 0.0) or 0.0,
                        abs_amount_diff=s.get("abs_amount_diff", 0.0) or 0.0,
                        bank_ids=bank_ids,
                        journal_entry_ids=journal_ids,
                        payload=s,
                    )
                )
        if to_create:
            ReconciliationSuggestion.objects.bulk_create(to_create, batch_size=1000)
            task_obj.suggestion_count = (task_obj.suggestion_count or 0) + len(to_create)
            task_obj.save(update_fields=["suggestion_count", "updated_at"])

        # Process auto-applied details (label persisted suggestions), same logic as before
        details = auto_info.get("details", []) or []
        if details:
            accepted_map = {}
            for entry in details:
                if "reconciliation_id" not in entry:
                    continue
                key = (
                    tuple(sorted(entry.get("bank_ids", []))),
                    tuple(sorted(entry.get("journal_ids", []))),
                )
                accepted_map[key] = entry["reconciliation_id"]

            if accepted_map:
                task_suggestions = list(
                    ReconciliationSuggestion.objects.filter(task=task_obj)
                )

                to_update = []
                for row in task_suggestions:
                    key = (tuple(sorted(row.bank_ids)), tuple(sorted(row.journal_entry_ids)))
                    if key in accepted_map:
                        row.status = "accepted"
                        row.decision_source = "auto_100"
                        row.decision_at = timezone.now()
                        row.reconciliation_id = accepted_map[key]
                        to_update.append(row)

                if to_update:
                    ReconciliationSuggestion.objects.bulk_update(
                        to_update,
                        ["status", "decision_source", "decision_at", "reconciliation"],
                        batch_size=500,
                    )

        logger.info(
            "Task %s completed: %d suggestions, %d auto-applied",
            db_id,
            len(suggestions),
            auto_info.get("applied", 0),
        )

        # ---- persist stats into ReconciliationTask ----
        task_obj.suggestion_count = int(stats.get("suggestion_count", task_obj.suggestion_count or 0))
        task_obj.bank_candidates = int(stats.get("bank_candidates", 0))
        task_obj.journal_candidates = int(stats.get("journal_candidates", 0))
        task_obj.matched_bank_transactions = int(stats.get("matched_bank_transactions", 0))
        task_obj.matched_journal_entries = int(stats.get("matched_journal_entries", 0))
        task_obj.duration_seconds = stats.get("duration_seconds")
        task_obj.soft_time_limit_seconds = stats.get("time_limit_seconds")
        task_obj.auto_match_enabled = bool(auto_info.get("enabled", False))
        task_obj.auto_match_applied = int(auto_info.get("applied", 0))
        task_obj.auto_match_skipped = int(auto_info.get("skipped", 0))
        task_obj.stats = stats
        task_obj.result = result
        task_obj.status = "completed"
        task_obj.updated_at = timezone.now()
        task_obj.save(update_fields=[
            "status", "result", "stats", "suggestion_count", "bank_candidates", "journal_candidates",
            "matched_bank_transactions", "matched_journal_entries", "duration_seconds",
            "soft_time_limit_seconds", "auto_match_enabled", "auto_match_applied", "auto_match_skipped", "updated_at",
        ])

        return result

    except SoftTimeLimitExceeded as e:
        # Celery soft time limit hit: mark task as failed, try final flush
        log.warning("Recon task %s soft-timeout: %s", db_id, e)
        try:
            flush_buffer(force=True)
        except Exception:
            pass
        task_obj.status = "failed"
        task_obj.error_message = f"Soft time limit exceeded in Celery worker: {e}"
        task_obj.updated_at = timezone.now()
        task_obj.save(update_fields=["status", "error_message", "updated_at"])
        raise

    except Exception as e:
        log.exception("Recon task %s raised exception: %s", db_id, e)
        try:
            flush_buffer(force=True)
        except Exception:
            pass
        task_obj.status = "failed"
        task_obj.error_message = str(e)
        task_obj.updated_at = timezone.now()
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

def _job_update(task, **fields):
    """Best-effort Job row update for this Celery task."""
    try:
        Job.objects.filter(task_id=task.request.id).update(**fields)
    except Exception:
        pass

def _progress_meta(totals_by_cat, done_by_cat):
    total_all = sum(totals_by_cat.values())
    done_all = sum(done_by_cat.values())
    return {
        "totals": totals_by_cat,
        "done": done_by_cat,
        "remaining": {k: max(totals_by_cat[k] - done_by_cat.get(k, 0), 0) for k in totals_by_cat},
        "done_all": done_all,
        "remaining_all": max(total_all - done_all, 0),
    }

def _publish_progress(task, totals_by_cat, done_by_cat, extra=None):
    meta = _progress_meta(totals_by_cat, done_by_cat)
    if extra:
        meta.update(extra)
    # 1) Celery (for live polling)
    task.update_state(state="PROGRESS", meta=meta)
    # 2) DB row (for dashboards)
    _job_update(
        task,
        state=STATE_MAP["PROGRESS"],
        total=sum(totals_by_cat.values()),
        done=sum(done_by_cat.values()),
        by_category=meta,
        meta=extra or None,
    )

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
    soft_time_limit=600,
)
def generate_missing_embeddings(self, per_model_limit: Optional[int] = None, client_opts: Optional[dict] = None) -> dict:
    from core.models import Job
    Job.objects.filter(task_id=self.request.id).update(kind="embeddings.backfill")
    
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
    
    # Build querysets
    tx_qs  = Transaction.objects.filter(description_embedding__isnull=True).order_by("id").only("id","description","amount","date")[:limit]
    btx_qs = BankTransaction.objects.filter(description_embedding__isnull=True).order_by("id").only("id","description","amount","date")[:limit]
    acc_qs = Account.objects.filter(account_description_embedding__isnull=True).order_by("id").only("id","name","description","key_words","examples")[:limit]

    tx_list, btx_list, acc_list = list(tx_qs), list(btx_qs), list(acc_qs)

    # Totals for progress
    totals = {
        "transactions": len(tx_list),
        "bank_transactions": len(btx_list),
        "accounts": len(acc_list),
    }
    total = sum(totals.values())
    done = 0
    by_cat_done = {"transactions": 0, "bank_transactions": 0, "accounts": 0}

    # Initial progress snapshot
    job_progress(self, done=done, total=total, by_category={**totals, **{f"{k}_done":0 for k in totals}})

    # Process each category in batches; update progress per batch
    def _run_cat(objs, text_fn, field_name, key):
        nonlocal done, by_cat_done
        if not objs:
            return 0
        updated = 0
        for i in range(0, len(objs), settings.EMBED_BATCH_SIZE):
            block = objs[i:i+settings.EMBED_BATCH_SIZE]
            vectors = client.embed_texts([text_fn(o) or " " for o in block])
            with transaction.atomic():
                for o, vec in zip(block, vectors):
                    if not vec:
                        continue
                    setattr(o, field_name, vec)
                    o.save(update_fields=[field_name])
                    updated += 1
                    done += 1
                    by_cat_done[key] += 1
            # progress tick
            by_snapshot = {
                "transactions": totals["transactions"],
                "transactions_done": by_cat_done["transactions"],
                "bank_transactions": totals["bank_transactions"],
                "bank_transactions_done": by_cat_done["bank_transactions"],
                "accounts": totals["accounts"],
                "accounts_done": by_cat_done["accounts"],
            }
            job_progress(self, done=done, total=total, by_category=by_snapshot)
        return updated

    tx_updated  = _run_cat(tx_list,  _tx_text,   "description_embedding",          "transactions")
    btx_updated = _run_cat(btx_list, _bank_text, "description_embedding",          "bank_transactions")
    acc_updated = _run_cat(acc_list, _account_text, "account_description_embedding","accounts")

    result = {
        "transactions_updated": tx_updated,
        "bank_transactions_updated": btx_updated,
        "accounts_updated": acc_updated,
        "model": client.model,
        "url": client.url,
        "dim": client.dim,
        "batch_size": settings.EMBED_BATCH_SIZE,
        "total_requested": total,
        "total_done": done,
    }
    return result