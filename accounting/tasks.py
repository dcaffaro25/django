from __future__ import annotations
import logging
import time
import math
import uuid
from typing import List, Callable, Optional, Sequence, Dict, Any
from decimal import Decimal

from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.conf import settings
from django.utils import timezone

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from celery.result import AsyncResult
from celery.utils.log import get_task_logger

from core.utils.jobs import job_progress
from core.models import Job

from .services.reconciliation_service import (
    ReconciliationService,
    _as_vec_list,
    q2,
    CENT,
    compute_match_scores,
    _avg_embedding,
    BankTransactionDTO,
    JournalEntryDTO,
    ReconciliationPipelineEngine,
    PipelineConfig,
    StageConfig,
)
from .models import (
    Account,
    BankTransaction,
    Transaction,
    ReconciliationTask,
    ReconciliationSuggestion,
)
from .services.embedding_client import EmbeddingClient
from multitenancy.utils import resolve_tenant

from accounting.utils import update_journal_entries_and_transaction_flags

logger = get_task_logger(__name__)
log = logging.getLogger(__name__)


# -----------------------
# Helpers
# -----------------------
def cosine_similarity(v1: Sequence[float], v2: Sequence[float]) -> float:
    """
    Safe cosine similarity helper for lists/tuples/ndarrays.
    Returns 0.0 if either vector is empty or if norms are zero.
    Uses zip to compute over min length to avoid IndexError for mismatched dims.
    """
    if not v1 or not v2:
        return 0.0
    try:
        a = [float(x) for x in v1]
        b = [float(x) for x in v2]
    except Exception:
        return 0.0

    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y

    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


CANCEL_KEY_PREFIX = "embed:cancel:"  # cache key for graceful cancel
STATE_MAP = {
    "PENDING": "PENDING",
    "RECEIVED": "RECEIVED",
    "SENT": "SENT",
    "STARTED": "STARTED",
    "PROGRESS": "PROGRESS",
    "RETRY": "RETRY",
    "SUCCESS": "SUCCESS",
    "FAILURE": "FAILURE",
    "REVOKED": "REVOKED",
}

# flush tuning
RECON_SUGGESTION_FLUSH_SIZE = int(getattr(settings, "RECON_SUGGESTION_FLUSH_SIZE", 500))
RECON_SUGGESTION_FLUSH_SECONDS = float(getattr(settings, "RECON_SUGGESTION_FLUSH_SECONDS", 30.0))
DEFAULT_SUGGESTION_FLUSH_INTERVAL = int(getattr(settings, "RECON_SUGGESTION_FLUSH_INTERVAL", 30))


# -----------------------
# Utility tasks
# -----------------------
@shared_task(bind=True)
def recalc_unposted_flags_task(self) -> dict:
    updated_count = 0
    with transaction.atomic():
        unposted_txs = (
            Transaction.objects
            .exclude(state="posted")
            .select_related("company", "currency", "entity")
            .prefetch_related("journal_entries__account__bank_account", "journal_entries__reconciliations")
        )
        for tx in unposted_txs:
            entries = list(tx.journal_entries.all())
            if entries:
                update_journal_entries_and_transaction_flags(entries)
                updated_count += 1
    return {"updated_transactions": updated_count}


# -----------------------
# Compare engines orchestration
# -----------------------
@shared_task(bind=True)
def compare_two_engines_task(self, db_id: int, data: Dict[str, Any], tenant_id: str = None, auto_match_100: bool = False):
    """
    Orquestra duas execuções:
      - legacy: match_many_to_many_task (código existente)
      - fast: match_many_to_many_task com fast=True (nova implementação no ReconciliationService)

    Cria duas ReconciliationTask filhas, dispara as tasks em filas separadas e aguarda (poll)
    um curto período para coletar resultados; grava um resumo comparativo em parent_task.result["comparisons"].
    """
    parent_task = ReconciliationTask.objects.get(id=db_id)
    run_uuid = str(uuid.uuid4())
    now = timezone.now()

    # Base request payloads (não mutar 'data' original)
    legacy_data: Dict[str, Any] = dict(data or {})
    fast_data: Dict[str, Any] = dict(data or {})

    # Força o modo legacy/fast no payload enviado ao engine
    legacy_data.pop("fast", None)
    fast_data["fast"] = True

    # create two child rows mirroring fields used by start()
    legacy_params = {
        "origin_request_parameters": data,
        "strategy": "legacy",
        "parent_task_id": db_id,
        "run_uuid": run_uuid,
    }
    fast_params = {
        "origin_request_parameters": data,
        "strategy": "fast_v1",
        "parent_task_id": db_id,
        "run_uuid": run_uuid,
        "fast": True,
    }

    legacy_row = ReconciliationTask.objects.create(
        task_id=uuid.uuid4(),
        tenant_id=tenant_id,
        parameters=legacy_params,
        status="queued",
        config=parent_task.config,
        pipeline=parent_task.pipeline,
        config_name=parent_task.config_name,
        pipeline_name=parent_task.pipeline_name,
        soft_time_limit_seconds=parent_task.soft_time_limit_seconds,
        created_at=now,
    )

    fast_row = ReconciliationTask.objects.create(
        task_id=uuid.uuid4(),
        tenant_id=tenant_id,
        parameters=fast_params,
        status="queued",
        config=parent_task.config,
        pipeline=parent_task.pipeline,
        config_name=parent_task.config_name,
        pipeline_name=parent_task.pipeline_name,
        soft_time_limit_seconds=parent_task.soft_time_limit_seconds,
        created_at=now,
    )

    # dispatch both (optionally dedicated queues configured in Celery)
    legacy_async = match_many_to_many_task.apply_async(
        args=(legacy_row.id, legacy_data, tenant_id, auto_match_100, False),
        queue="recon_legacy",
    )
    fast_async = match_many_to_many_task.apply_async(
        args=(fast_row.id, fast_data, tenant_id, auto_match_100, True),
        queue="recon_fast",
    )

    # Poll for a short time (caller can re-query parent task later)
    max_wait_s = int(getattr(settings, "COMPARE_MAX_WAIT_S", 600))
    poll = float(getattr(settings, "COMPARE_POLL_INTERVAL_S", 2.0))
    waited = 0.0
    legacy_finished = fast_finished = False

    while waited < max_wait_s:
        if not legacy_finished:
            l_state = AsyncResult(legacy_async.id).state
            if l_state in ("SUCCESS", "FAILURE", "REVOKED", "RETRY"):
                legacy_finished = True
        if not fast_finished:
            f_state = AsyncResult(fast_async.id).state
            if f_state in ("SUCCESS", "FAILURE", "REVOKED", "RETRY"):
                fast_finished = True
        if legacy_finished and fast_finished:
            break
        time.sleep(poll)
        waited += poll

    # reload to pick stats written by child runs
    try:
        legacy_row.refresh_from_db()
    except Exception:
        legacy_row = None
    try:
        fast_row.refresh_from_db()
    except Exception:
        fast_row = None

    # build summary
    def safe_attr(obj, name):
        return getattr(obj, name) if obj is not None else None

    summary = {
        "run_uuid": run_uuid,
        "parent_task_id": db_id,
        "generated_at": timezone.now(),
        "legacy": {
            "task_id": safe_attr(legacy_row, "id"),
            "status": safe_attr(legacy_row, "status"),
            "duration_seconds": safe_attr(legacy_row, "duration_seconds"),
            "suggestion_count": safe_attr(legacy_row, "suggestion_count"),
            "time_limit_reached": bool(
                parent_task.soft_time_limit_seconds
                and safe_attr(legacy_row, "duration_seconds")
                and safe_attr(legacy_row, "duration_seconds") >= parent_task.soft_time_limit_seconds
            ),
        },
        "fast": {
            "task_id": safe_attr(fast_row, "id"),
            "status": safe_attr(fast_row, "status"),
            "duration_seconds": safe_attr(fast_row, "duration_seconds"),
            "suggestion_count": safe_attr(fast_row, "suggestion_count"),
            "time_limit_reached": bool(
                parent_task.soft_time_limit_seconds
                and safe_attr(fast_row, "duration_seconds")
                and safe_attr(fast_row, "duration_seconds") >= parent_task.soft_time_limit_seconds
            ),
        },
    }

    # Persist comparison defensively into parent_task.result["comparisons"]
    try:
        result = parent_task.result or {}
        result.setdefault("comparisons", [])
        result["comparisons"].append(summary)
        parent_task.result = result
        parent_task.updated_at = timezone.now()
        parent_task.save(update_fields=["result", "updated_at"])
    except Exception:
        log.exception("Failed saving comparison summary for task %s", db_id)

    return summary



# -----------------------
# Legacy wrapper (unchanged behaviour, but hardened)
# -----------------------
@shared_task(bind=True)
def match_many_to_many_task(self, db_id, data, tenant_id=None, auto_match_100=False, fast=False):
    """
    Wrapper that calls ReconciliationService.match_many_to_many with streaming on_suggestion callback.
    Persists suggestions in batches and updates the ReconciliationTask object incrementally.
    """
    task_obj = ReconciliationTask.objects.get(id=db_id)
    
    # local copy so we don't mutate the caller's dict
    request_data: Dict[str, Any] = dict(data or {})
    
    # resolve company id defensively
    company_id = None
    try:
        company_id = data.get("company_id", None)
    except Exception:
        company_id = None

    if company_id is None and tenant_id:
        try:
            company_obj = resolve_tenant(tenant_id)
            company_id = getattr(company_obj, "id", None)
        except Exception:
            company_id = None
    
    # derive 'fast' from task.strategy when not explicitly set
    strategy = getattr(task_obj, "strategy", None)
    if strategy in ("fast", "fast_v1") and not request_data.get("fast"):
        request_data["fast"] = True
    elif "fast" not in request_data:
        # make it explicit for the engine (defaults to legacy path)
        request_data["fast"] = False
    
    request_data["fast"] = fast
    
    
    flush_interval = DEFAULT_SUGGESTION_FLUSH_INTERVAL
    buffer: List[ReconciliationSuggestion] = []
    last_flush_ts = time.monotonic()

    def flush_buffer(force=False):
        nonlocal buffer, last_flush_ts
        if not buffer:
            return
        try:
            ReconciliationSuggestion.objects.bulk_create(buffer, batch_size=1000)
            created = len(buffer)
            buffer = []
            task_obj.suggestion_count = (task_obj.suggestion_count or 0) + created
            task_obj.updated_at = timezone.now()
            task_obj.save(update_fields=["suggestion_count", "updated_at"])
            last_flush_ts = time.monotonic()
            log.debug("Flushed %d suggestions for task %s", created, db_id)
        except Exception:
            log.exception("Failed flushing suggestions buffer for task %s", db_id)

    def on_suggestion(s: dict) -> None:
        nonlocal buffer, last_flush_ts, company_id
        try:
            sugg_company_id = s.get("company_id") or company_id
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
        except Exception:
            log.exception("Error buffering suggestion for task %s", db_id)

        now = time.monotonic()
        if now - last_flush_ts >= flush_interval or len(buffer) >= RECON_SUGGESTION_FLUSH_SIZE:
            flush_buffer()

    try:
        task_obj.status = "running"
        task_obj.updated_at = timezone.now()
        task_obj.save(update_fields=["status", "updated_at"])

        logger.info("Task %s started: bank_ids=%s book_ids=%s config_id=%s pipeline_id=%s",
                    db_id, data.get("bank_ids"), data.get("book_ids"),
                    data.get("config_id"), data.get("pipeline_id"))

        result = ReconciliationService.match_many_to_many(
            request_data,
            tenant_id,
            auto_match_100=auto_match_100,
            on_suggestion=on_suggestion,
        )

        # final flush
        flush_buffer(force=True)

        suggestions = result.get("suggestions", []) or []
        auto_info = result.get("auto_match", {}) or {}
        stats = result.get("stats", {}) or {}

        # create any remaining suggestions defensively (avoid duplicates when possible)
        to_create = []
        for s in suggestions:
            bank_ids = s.get("bank_ids", []) or []
            journal_ids = s.get("journal_entries_ids", []) or []
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

        # Process auto-applied (if engine returned auto match details)
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
                task_suggestions = list(ReconciliationSuggestion.objects.filter(task=task_obj))
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

        # persist stats into task row
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


# -----------------------
# Small utility helpers used elsewhere (kept here for convenience)
# -----------------------
def _nz(s: Optional[str]) -> str:
    return " ".join((s or "").split()).strip()


def _account_text(a: Account) -> str:
    parts = [a.name, a.description, a.key_words, a.examples]
    return " | ".join(p for p in map(_nz, parts) if p)


def _tx_text(t: Transaction) -> str:
    return _nz(f"{t.description or ''} | amount={t.amount} | date={t.date}")


def _bank_text(b: BankTransaction) -> str:
    return _nz(f"{b.description or ''} | amount={b.amount} | date={b.date}")


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
        base_url=(client_opts or {}).get("base_url"),
        path=(client_opts or {}).get("path", settings.EMBED_PATH),
        extra_headers=(client_opts or {}).get("extra_headers"),
    )

    tx_qs = Transaction.objects.filter(description_embedding__isnull=True).order_by("id").only("id", "description", "amount", "date")[:limit]
    btx_qs = BankTransaction.objects.filter(description_embedding__isnull=True).order_by("id").only("id", "description", "amount", "date")[:limit]
    acc_qs = Account.objects.filter(account_description_embedding__isnull=True).order_by("id").only("id", "name", "description", "key_words", "examples")[:limit]

    tx_list, btx_list, acc_list = list(tx_qs), list(btx_qs), list(acc_qs)

    totals = {
        "transactions": len(tx_list),
        "bank_transactions": len(btx_list),
        "accounts": len(acc_list),
    }
    total = sum(totals.values())
    done = 0
    by_cat_done = {"transactions": 0, "bank_transactions": 0, "accounts": 0}

    job_progress(self, done=done, total=total, by_category={**totals, **{f"{k}_done": 0 for k in totals}})

    def _run_cat(objs, text_fn, field_name, key):
        nonlocal done, by_cat_done
        if not objs:
            return 0
        updated = 0
        for i in range(0, len(objs), settings.EMBED_BATCH_SIZE):
            block = objs[i:i + settings.EMBED_BATCH_SIZE]
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

    tx_updated = _run_cat(tx_list, _tx_text, "description_embedding", "transactions")
    btx_updated = _run_cat(btx_list, _bank_text, "description_embedding", "bank_transactions")
    acc_updated = _run_cat(acc_list, _account_text, "account_description_embedding", "accounts")

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
