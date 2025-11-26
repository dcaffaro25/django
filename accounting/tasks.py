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
      - fast: match_many_to_many_fast_task (nova implementação aqui)

    Cria duas ReconciliationTask filhas, dispara as tasks em filas separadas e aguarda (poll)
    um curto período para coletar resultados; grava um resumo comparativo em parent_task.result["comparisons"].
    """
    parent_task = ReconciliationTask.objects.get(id=db_id)
    run_uuid = str(uuid.uuid4())
    now = timezone.now()

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
        args=(legacy_row.id, data, tenant_id, auto_match_100),
        queue="recon_legacy",
    )
    fast_async = match_many_to_many_fast_task.apply_async(
        args=(fast_row.id, data, tenant_id, auto_match_100),
        queue="recon_fast",
    )

    # Poll for a short time (non-blocking caller can re-query parent task)
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
            "time_limit_reached": bool(parent_task.soft_time_limit_seconds and safe_attr(legacy_row, "duration_seconds") and safe_attr(legacy_row, "duration_seconds") >= parent_task.soft_time_limit_seconds),
        },
        "fast": {
            "task_id": safe_attr(fast_row, "id"),
            "status": safe_attr(fast_row, "status"),
            "duration_seconds": safe_attr(fast_row, "duration_seconds"),
            "suggestion_count": safe_attr(fast_row, "suggestion_count"),
            "time_limit_reached": bool(parent_task.soft_time_limit_seconds and safe_attr(fast_row, "duration_seconds") and safe_attr(fast_row, "duration_seconds") >= parent_task.soft_time_limit_seconds),
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
# Fast match implementation
# -----------------------
@shared_task(bind=True)
def match_many_to_many_fast_task(self, db_id: int, data: Dict[str, Any], tenant_id: str = None, auto_match_100: bool = False):
    """
    Fast alternative runner for heavy 1-to-M / M-to-1 / M-to-M cases.
    Strategy:
      - prefilter by date window + currency
      - prefilter top-K by embedding similarity
      - prune by amount closeness to MAX_CANDIDATES
      - attempt subset-sum bitset DP when all amounts non-negative and N <= MAX_DP
      - fallback to beam-search (greedy beam)
      - persist suggestions incrementally as ReconciliationSuggestion rows
    This function keeps the public behavior of producing ReconciliationSuggestion rows and
    updating a ReconciliationTask row but does not mutate the existing legacy functions.
    """
    # Local imports (models/services already imported at top for type resolution)
    from .services.reconciliation_service import BankTransactionDTO, JournalEntryDTO

    # Tunables (override in settings if needed)
    K_EMBED = int(getattr(settings, "FAST_PREFILTER_TOPK_EMBED", 120))
    MAX_CANDIDATES = int(getattr(settings, "FAST_MAX_CANDIDATES", 60))
    MAX_DP = int(getattr(settings, "FAST_MAX_DP", 60))
    BEAM_SIZE = int(getattr(settings, "FAST_BEAM_SIZE", 200))
    MAX_TIME_PER_BANK = float(getattr(settings, "FAST_MAX_TIME_PER_BANK", 5.0))
    GLOBAL_HARD_TIMEOUT = float(getattr(settings, "FAST_GLOBAL_HARD_TIMEOUT", 15 * 60))

    task_row = ReconciliationTask.objects.get(id=db_id)
    task_row.status = "running"
    task_row.updated_at = timezone.now()
    task_row.save(update_fields=["status", "updated_at"])

    start_ts = time.time()

    # build DTOs (reuse similar queryset logic as legacy
    company_id = data.get("company_id")
    if company_id is None and tenant_id:
        try:
            company_obj = resolve_tenant(tenant_id)
            company_id = getattr(company_obj, "id", None)
        except Exception:
            company_id = None

    bank_ids = data.get("bank_ids") or []
    book_ids = data.get("book_ids") or []

    bank_qs = BankTransaction.objects.exclude(reconciliations__status__in=["matched", "approved"]).filter(company_id=company_id)
    if bank_ids:
        bank_qs = bank_qs.filter(id__in=bank_ids)
    book_qs = (
        Transaction.objects.select_related("currency")
        .filter(journal_entries__account__bank_account__isnull=False)
    )
    # For fairness with legacy: use JournalEntry model as books (import earlier)
    # But if JournalEntry model exists under another name, adapt accordingly.
    # Here we rely on JournalEntry query done previously in legacy service; to remain consistent, use JournalEntry from models if available.
    try:
        from .models import JournalEntry  # type: ignore
        book_qs = JournalEntry.objects.exclude(reconciliations__status__in=["matched", "approved"]).filter(company_id=company_id, account__bank_account__isnull=False)
        if book_ids:
            book_qs = book_qs.filter(id__in=book_ids)
    except Exception:
        # Fallback: if JournalEntry not available, try to infer via Transaction's journal_entries (less ideal)
        book_qs = Transaction.objects.none()

    banks = [
        BankTransactionDTO(
            id=b.id,
            company_id=b.company_id,
            date=b.date,
            amount=b.amount,
            currency_id=b.currency_id,
            description=b.description,
            embedding=_as_vec_list(getattr(b, "description_embedding", None)),
        )
        for b in bank_qs
    ]

    books = [
        JournalEntryDTO(
            id=j.id,
            company_id=j.company_id,
            transaction_id=getattr(j, "transaction_id", None),
            date=getattr(j, "date", None) or (getattr(getattr(j, "transaction", None), "date", None)),
            effective_amount=getattr(j, "get_effective_amount", lambda: None)() if hasattr(j, "get_effective_amount") else getattr(j, "amount", 0),
            #amount_base=getattr(j, "get_effective_amount", lambda: 0)(),  # expected by DP helpers
            currency_id=(getattr(getattr(j, "transaction", None), "currency_id", None) if getattr(j, "transaction", None) else None),
            description=(getattr(getattr(j, "transaction", None), "description", "") if getattr(j, "transaction", None) else ""),
            embedding=_as_vec_list(getattr(getattr(j, "transaction", None), "description_embedding", None)),
        )
        for j in book_qs
    ]

    # Helper top-k by embedding
    def topk_by_embedding(anchor_vec, candidates, k):
        if not anchor_vec:
            return list(range(min(k, len(candidates))))
        sims = []
        for i, c in enumerate(candidates):
            try:
                s = cosine_similarity(anchor_vec, (c.embedding or []))
            except Exception:
                s = 0.0
            sims.append((i, s))
        # stable sort: primary by score desc, secondary by index asc (prefer smaller index)
        sims.sort(key=lambda t: (t[1], -t[0]), reverse=True)
        return [i for i, _ in sims[:k]]

    # subset-sum bitset DP returning list of index lists (works for non-negative ints)
    def subset_sum_bitset_indices(items, target_dec: Decimal, tol_dec: Decimal, max_card: int):
        # items: list of DTOs with .amount_base
        try:
            cents = [int(q2(getattr(it, "effective_amount", 0)) / CENT) for it in items]
        except Exception:
            cents = [int(q2(getattr(it, "effective_amount", 0)) / CENT) if getattr(it, "effective_amount", None) is not None else 0 for it in items]
        target = int(q2(target_dec) / CENT)
        tol = int(q2(tol_dec) / CENT)
        total = sum(cents)
        if target - tol > total or target + tol < 0:
            return []
        # safety guard
        if total > 5_000_000:
            # DP would be too memory heavy; fallback
            return []
        dp = 1  # bitset with dp[0] = 1
        parents = {}
        sizes = {0: 0}
        for idx, val in enumerate(cents):
            if val < 0:
                # DP bitset expects non-negative; caller should avoid calling DP for mixed signs
                continue
            shifted = dp << val
            new = shifted & ~dp
            if new:
                s = new
                while s:
                    lowbit = s & -s
                    sum_pos = lowbit.bit_length() - 1
                    prev = sum_pos - val
                    prev_size = sizes.get(prev)
                    if prev_size is not None and prev_size + 1 <= max_card:
                        if sum_pos not in parents:
                            parents[sum_pos] = (idx, prev)
                            sizes[sum_pos] = prev_size + 1
                    s &= s - 1
            dp |= shifted
        results = []
        low = max(0, target - tol)
        high = min(total, target + tol)
        for s in range(low, high + 1):
            if (dp >> s) & 1:
                # reconstruct
                cur = s
                combo = []
                while cur != 0:
                    if cur not in parents:
                        combo = []
                        break
                    idx, prev = parents[cur]
                    combo.append(idx)
                    cur = prev
                if combo:
                    results.append(list(reversed(combo)))
        return results

    # beam search fallback (simple)
    def beam_search_indices(items, target_dec: Decimal, tol_dec: Decimal, max_card: int, beam_size=BEAM_SIZE):
        target = q2(target_dec)
        ranked = sorted(enumerate(items), key=lambda x: abs(q2(getattr(x[1], "effective_amount", 0)) - target))
        beam = [(Decimal("0.00"), [])]
        for idx, item in ranked:
            new_beam = list(beam)
            for s, idxs in beam:
                if len(idxs) + 1 > max_card:
                    continue
                s2 = s + q2(getattr(item, "effective_amount", Decimal("0.00")))
                idxs2 = idxs + [idx]
                new_beam.append((s2, idxs2))
            new_beam.sort(key=lambda t: abs(t[0] - target))
            beam = new_beam[:beam_size]
        tol = q2(tol_dec)
        solutions = [idxs for s, idxs in beam if abs(s - target) <= tol]
        return solutions

    suggestions_out: List[Dict[str, Any]] = []
    task_start = time.time()

    for bank in banks:
        # global timeout guard
        if time.time() - task_start > GLOBAL_HARD_TIMEOUT:
            log.warning("match_many_to_many_fast_task %s: global hard timeout reached", db_id)
            break
        bank_start = time.time()

        # prefilter: date window and currency
        win_days = int(data.get("date_window_days", 365) or 365)
        local_books = [
            b for b in books
            if b.currency_id == bank.currency_id and getattr(b, "date", None) and getattr(bank, "date", None)
            and abs((bank.date - b.date).days) <= win_days
        ]
        if not local_books:
            continue

        # prefilter by embedding top-K
        top_idx = topk_by_embedding(bank.embedding or [], local_books, K_EMBED)
        local_books = [local_books[i] for i in top_idx]

        # reduce by amount closeness if still too many
        if len(local_books) > MAX_CANDIDATES:
            local_books.sort(key=lambda b: abs(q2(getattr(b, "effective_amount", 0)) - q2(getattr(bank, "amount", 0))))
            local_books = local_books[:MAX_CANDIDATES]

        # decide DP vs beam
        book_amounts = [q2(getattr(b, "effective_amount", 0)) for b in local_books]
        all_non_negative = all(a >= 0 for a in book_amounts)
        amt_tol = Decimal(str(data.get("amount_tolerance", "0.00") or "0.00"))
        max_group = int(data.get("max_group_size_book", 5) or 5)
        combos_idx = []

        try:
            if all_non_negative and len(local_books) <= MAX_DP:
                combos_idx = subset_sum_bitset_indices(local_books, getattr(bank, "amount", Decimal("0.00")), amt_tol, max_group)
                if not combos_idx:
                    combos_idx = beam_search_indices(local_books, getattr(bank, "amount", Decimal("0.00")), amt_tol, max_group, beam_size=BEAM_SIZE)
            else:
                combos_idx = beam_search_indices(local_books, getattr(bank, "amount", Decimal("0.00")), amt_tol, max_group, beam_size=BEAM_SIZE)
        except Exception:
            log.exception("Error deriving combos for bank %s; falling back to greedy", bank.id)
            # fallback: try single-best by amount closeness
            if local_books:
                combos_idx = [[0]]

        # time guard per bank
        if time.time() - bank_start > MAX_TIME_PER_BANK:
            log.debug("match_many_to_many_fast_task %s: skipping heavy processing for bank %s due to time-per-bank guard", db_id, bank.id)
            continue

        # convert combos -> suggestions
        for idxs in combos_idx:
            combo_books = [local_books[i] for i in idxs]
            try:
                sim = cosine_similarity(bank.embedding or [], _avg_embedding(combo_books))
            except Exception:
                sim = 0.0

            # local weighted avg date helper
            def _weighted_avg_date(items):
                total = Decimal("0.00")
                for it in items:
                    try:
                        total += q2(getattr(it, "effective_amount", Decimal("0.00")))
                    except Exception:
                        pass
                if total == Decimal("0.00"):
                    return None
                weighted = 0.0
                for it in items:
                    if not getattr(it, "date", None):
                        continue
                    try:
                        w = float(q2(getattr(it, "effective_amount", Decimal("0.00"))) / total)
                    except Exception:
                        w = 0.0
                    weighted += it.date.toordinal() * w
                try:
                    return timezone.datetime.fromordinal(int(round(weighted))).date()
                except Exception:
                    return None

            date_avg = _weighted_avg_date(combo_books)
            date_diff = abs((bank.date - date_avg).days) if (bank.date and date_avg) else 0

            amount_sum = q2(sum(getattr(b, "effective_amount", 0) for b in combo_books))
            amount_diff = abs(amount_sum - q2(getattr(bank, "amount", Decimal("0.00"))))

            scores = compute_match_scores(
                embed_sim=sim,
                amount_diff=amount_diff,
                amount_tol=amt_tol,
                date_diff=date_diff,
                date_tol=int(data.get("avg_date_delta_days", 1) or 1),
                currency_match=1.0,
                weights={"embedding": 0.5, "amount": 0.35, "date": 0.1, "currency": 0.05},
            )

            sug = {
                "match_type": "one_to_many_fast",
                "bank_ids": [bank.id],
                "journal_entries_ids": [getattr(b, "id", None) for b in combo_books],
                "confidence_score": float(scores.get("global_score", 0.0)),
                "abs_amount_diff": float(amount_diff),
                "component_scores": scores,
            }

            # persist suggestion row (defensive)
            try:
                rs = ReconciliationSuggestion(
                    task=task_row,
                    company_id=getattr(bank, "company_id", None),
                    match_type=sug["match_type"],
                    confidence_score=sug["confidence_score"],
                    abs_amount_diff=sug["abs_amount_diff"],
                    bank_ids=sug["bank_ids"],
                    journal_entry_ids=sug["journal_entries_ids"],
                    payload=sug,
                )
                rs.save()
            except Exception:
                log.exception("Failed saving fast suggestion for bank %s", bank.id)
            suggestions_out.append(sug)

    # finalize task_row stats
    try:
        task_row.suggestion_count = ReconciliationSuggestion.objects.filter(task=task_row).count()
    except Exception:
        task_row.suggestion_count = len(suggestions_out)
    task_row.duration_seconds = time.time() - start_ts
    task_row.status = "completed"
    task_row.updated_at = timezone.now()
    task_row.save(update_fields=["suggestion_count", "duration_seconds", "status", "updated_at"])

    # optionally auto-apply 100% confidence suggestions using existing utility
    if auto_match_100 and suggestions_out:
        try:
            ReconciliationService._apply_auto_matches_100(suggestions_out)
        except Exception:
            log.exception("Failed applying auto_match_100 for fast run %s", db_id)

    return {"suggestions": suggestions_out, "stats": {"suggestion_count": len(suggestions_out), "duration_seconds": task_row.duration_seconds}}


# -----------------------
# Legacy wrapper (unchanged behaviour, but hardened)
# -----------------------
@shared_task(bind=True)
def match_many_to_many_task(self, db_id, data, tenant_id=None, auto_match_100=False):
    """
    Wrapper that calls ReconciliationService.match_many_to_many with streaming on_suggestion callback.
    Persists suggestions in batches and updates the ReconciliationTask object incrementally.
    """
    task_obj = ReconciliationTask.objects.get(id=db_id)

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
            data,
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
