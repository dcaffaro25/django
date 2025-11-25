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
from celery import shared_task
from celery.result import AsyncResult
from django.utils import timezone
from .models import ReconciliationTask
#from .tasks import match_many_to_many_task  # task existente
#from .tasks import RECON_SUGGESTION_FLUSH_SECONDS, DEFAULT_SUGGESTION_FLUSH_INTERVAL
from typing import Dict, Any
from decimal import Decimal
import uuid
import requests
from celery.utils.log import get_task_logger
logger = get_task_logger(__name__)

from .services.reconciliation_service import ReconciliationService, _as_vec_list, q2, CENT, compute_match_scores, _avg_embedding
from .models import Account, BankTransaction, Transaction, ReconciliationTask
from .services.embedding_client import EmbeddingClient
from multitenancy.utils import resolve_tenant  # <-- NOVO IMPORT

log = logging.getLogger(__name__)

from accounting.utils import update_journal_entries_and_transaction_flags
import math
from typing import List, Sequence



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
)
from .models import (
    Account,
    BankTransaction,
    Transaction,
    ReconciliationTask,
    ReconciliationSuggestion,
    # JournalEntry model referenced below if applicable
)
from .services.embedding_client import EmbeddingClient
from multitenancy.utils import resolve_tenant

from accounting.utils import update_journal_entries_and_transaction_flags

log = logging.getLogger(__name__)
logger = get_task_logger(__name__)

# ---- small helpers ----
def cosine_similarity(v1: Sequence[float], v2: Sequence[float]) -> float:
    """
    Safe cosine similarity helper for lists/tuples/ndarrays.
    Returns 0.0 if either vector is empty or if norms are zero.
    """
    if not v1 or not v2:
        return 0.0
    try:
        a = [float(x) for x in v1]
        b = [float(x) for x in v2]
    except Exception:
        return 0.0

    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    # zip intentionally truncates to shortest; OK for embeddings
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


def weighted_avg_date(items) -> Optional[timezone.datetime]:
    """
    Compute weighted average date for a list of DTOs that have a `.date`
    and `.amount_base` (Decimal). Returns None if no dates available.
    Weight by absolute amount.
    """
    total = Decimal("0")
    acc_ts = 0.0
    count = 0
    for it in items:
        if getattr(it, "date", None) is None:
            continue
        amt = Decimal(q2(getattr(it, "amount_base", 0)))
        w = abs(amt)
        if w == 0:
            continue
        acc_ts += w * float(it.date.timestamp())
        total += w
        count += 1
    if total == 0 or count == 0:
        return None
    avg_ts = acc_ts / float(total)
    return timezone.datetime.fromtimestamp(avg_ts, tz=timezone.get_current_timezone())


# Constants / defaults
CANCEL_KEY_PREFIX = "embed:cancel:"  # cache key for graceful cancel
STATE_MAP = {
    "PENDING":  "PENDING",
    "RECEIVED": "RECEIVED",
    "SENT":     "SENT",
    "STARTED":  "STARTED",
    "PROGRESS": "PROGRESS",
    "RETRY":    "RETRY",
    "SUCCESS":  "SUCCESS",
    "FAILURE":  "FAILURE",
    "REVOKED":  "REVOKED",
}

RECON_SUGGESTION_FLUSH_SIZE = int(getattr(settings, "RECON_SUGGESTION_FLUSH_SIZE", 500))
RECON_SUGGESTION_FLUSH_SECONDS = float(getattr(settings, "RECON_SUGGESTION_FLUSH_SECONDS", 30.0))
DEFAULT_SUGGESTION_FLUSH_INTERVAL = int(getattr(settings, "RECON_SUGGESTION_FLUSH_INTERVAL", 30))


@shared_task(bind=True)
def recalc_unposted_flags_task(self) -> dict:
    updated_count = 0
    with transaction.atomic():
        unposted_txs = (
            Transaction.objects
            .exclude(state='posted')
            .select_related('company', 'currency', 'entity')
            .prefetch_related('journal_entries__account__bank_account', 'journal_entries__reconciliations')
        )
        for tx in unposted_txs:
            entries = list(tx.journal_entries.all())
            if entries:
                update_journal_entries_and_transaction_flags(entries)
                updated_count += 1
    return {"updated_transactions": updated_count}


@shared_task(bind=True)
def compare_two_engines_task(self, db_id: int, data: Dict[str, Any], tenant_id: str = None, auto_match_100: bool = False):
    """
    Spin up two child runs (legacy + fast) and persist a short comparison in parent.meta.
    """
    parent_task = ReconciliationTask.objects.get(id=db_id)
    run_uuid = str(uuid.uuid4())
    now = timezone.now()

    legacy_params = {
        "origin_request_parameters": data,
        "strategy": "legacy",
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

    fast_params = {
        "origin_request_parameters": data,
        "strategy": "fast_v1",
        "parent_task_id": db_id,
        "run_uuid": run_uuid,
    }
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

    legacy_async = match_many_to_many_task.apply_async(
        args=(legacy_row.id, data, tenant_id, auto_match_100),
        queue="recon_legacy",
    )
    fast_async = match_many_to_many_fast_task.apply_async(
        args=(fast_row.id, data, tenant_id, auto_match_100),
        queue="recon_fast",
    )

    max_wait_s = 600
    poll = 2
    waited = 0
    legacy_finished = fast_finished = False

    while waited < max_wait_s:
        if not legacy_finished:
            state = AsyncResult(legacy_async.id).state
            if state in ("SUCCESS", "FAILURE", "REVOKED", "RETRY"):
                legacy_finished = True
        if not fast_finished:
            state = AsyncResult(fast_async.id).state
            if state in ("SUCCESS", "FAILURE", "REVOKED", "RETRY"):
                fast_finished = True
        if legacy_finished and fast_finished:
            break
        time.sleep(poll)
        waited += poll

    legacy_row.refresh_from_db()
    fast_row.refresh_from_db()

    summary = {
        "run_uuid": run_uuid,
        "parent_task_id": db_id,
        "generated_at": timezone.now(),
        "legacy": {
            "task_id": legacy_row.id,
            "status": legacy_row.status,
            "duration_seconds": getattr(legacy_row, "duration_seconds", None),
            "suggestion_count": getattr(legacy_row, "suggestion_count", None),
            "time_limit_reached": (
                parent_task.soft_time_limit_seconds is not None
                and legacy_row.duration_seconds
                and legacy_row.duration_seconds >= parent_task.soft_time_limit_seconds
            ),
        },
        "fast": {
            "task_id": fast_row.id,
            "status": fast_row.status,
            "duration_seconds": getattr(fast_row, "duration_seconds", None),
            "suggestion_count": getattr(fast_row, "suggestion_count", None),
            "time_limit_reached": (
                parent_task.soft_time_limit_seconds is not None
                and fast_row.duration_seconds
                and fast_row.duration_seconds >= parent_task.soft_time_limit_seconds
            ),
        },
    }

    try:
        meta = parent_task.meta or {}
        meta.setdefault("comparisons", [])
        meta["comparisons"].append(summary)
        parent_task.meta = meta
        parent_task.updated_at = timezone.now()
        parent_task.save(update_fields=["meta", "updated_at"])
    except Exception:
        log.exception("Failed saving comparison summary for task %s", db_id)

    return summary


@shared_task(bind=True)
def match_many_to_many_fast_task(self, db_id: int, data: Dict[str, Any], tenant_id: str = None, auto_match_100: bool = False):
    """
    Fast alternative runner:
      - prefilter (embed top-K + amount closeness + date window)
      - subset-sum bitset for same-sign when possible
      - beam search fallback for mixed-sign or when DP not feasible
      - persist suggestions as ReconciliationSuggestion (same schema)
    """
    # Local imports to avoid module-level cost (keeps worker import light)
    from .models import BankTransaction as _BankTransactionModel, JournalEntry as _JournalEntryModel

    K_EMBED = int(getattr(settings, "FAST_PREFILTER_TOPK_EMBED", 120))
    MAX_CANDIDATES = int(getattr(settings, "FAST_MAX_CANDIDATES", 60))
    MAX_DP = int(getattr(settings, "FAST_MAX_DP", 60))
    BEAM_SIZE = int(getattr(settings, "FAST_BEAM_SIZE", 200))

    task_row = ReconciliationTask.objects.get(id=db_id)
    task_row.status = "running"
    task_row.save(update_fields=["status", "updated_at"])

    start_ts = time.time()

    # resolve company_id robustly
    company_id = data.get("company_id")
    if company_id is None and tenant_id:
        try:
            company_obj = resolve_tenant(tenant_id)
            company_id = getattr(company_obj, "id", None)
        except Exception:
            company_id = None

    bank_ids = data.get("bank_ids", []) or []
    book_ids = data.get("book_ids", []) or []

    bank_qs = BankTransaction.objects.exclude(reconciliations__status__in=["matched", "approved"]).filter(company_id=company_id)
    if bank_ids:
        bank_qs = bank_qs.filter(id__in=bank_ids)
    book_qs = _JournalEntryModel.objects.exclude(reconciliations__status__in=["matched", "approved"]).filter(company_id=company_id, account__bank_account__isnull=False)
    if book_ids:
        book_qs = book_qs.filter(id__in=book_ids)

    # create DTOs and ensure attribute `amount_base` exists (legacy expectation)
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
    # Ensure we map field name `amount_base` for compatibility with subset/beam helpers
    books = []
    for j in book_qs:
        je_dto = JournalEntryDTO(
            id=j.id,
            company_id=j.company_id,
            transaction_id=j.transaction_id,
            date=j.date or (getattr(j, "transaction").date if getattr(j, "transaction", None) else None),
            effective_amount=j.get_effective_amount(),
            currency_id=(getattr(j, "transaction").currency_id if getattr(j, "transaction", None) else None),
            description=(getattr(j, "transaction").description if getattr(j, "transaction", None) else ""),
            embedding=_as_vec_list(getattr(getattr(j, "transaction", None), "description_embedding", None)),
        )
        # normalize attribute name expected downstream
        setattr(je_dto, "amount_base", getattr(je_dto, "effective_amount", None))
        books.append(je_dto)

    # helpers
    def topk_by_embedding(anchor_vec, candidates, k):
        if not anchor_vec:
            return []
        # Protect k
        k = max(0, int(k))
        if k == 0:
            return []
        sims = [(i, cosine_similarity(anchor_vec, (getattr(c, "embedding", None) or []))) for i, c in enumerate(candidates)]
        sims.sort(key=lambda t: t[1], reverse=True)
        top = sims[:min(k, len(sims))]
        return [i for i, _ in top]

    def subset_sum_bitset_indices(items, target_dec: Decimal, tol_dec: Decimal, max_card: int):
        # items: list of DTOs with .amount_base; returns list of index-lists
        if not items:
            return []
        cents = [int(q2(getattr(it, "amount_base", 0)) / CENT) for it in items]
        target = int(q2(target_dec) / CENT)
        tol = int(q2(tol_dec) / CENT)
        total = sum(cents)
        if target - tol > total or target + tol < 0:
            return []
        # limit DP size by total bits; if too large, bail out
        if total > 2000000:
            # avoid excessive memory/time; return empty so fallback beam will run
            return []
        dp = 1
        parents = {}
        sizes = {0: 0}
        for idx, val in enumerate(cents):
            if val < 0:
                # negative amounts not supported by this simple bitset approach
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

    def beam_search_indices(items, target_dec: Decimal, tol_dec: Decimal, max_card: int, beam_size=BEAM_SIZE):
        if not items:
            return []
        target = q2(target_dec)
        ranked = sorted(enumerate(items), key=lambda x: abs(q2(getattr(x[1], "amount_base", 0)) - target))
        beam = [(Decimal("0.00"), [])]
        for idx, item in ranked:
            new_beam = list(beam)
            for s, idxs in beam:
                if len(idxs) + 1 > max_card:
                    continue
                s2 = s + q2(getattr(item, "amount_base", 0))
                idxs2 = idxs + [idx]
                new_beam.append((s2, idxs2))
            new_beam.sort(key=lambda t: abs(t[0] - target))
            beam = new_beam[:beam_size]
        tol = q2(tol_dec)
        solutions = [idxs for s, idxs in beam if abs(s - target) <= tol]
        return solutions

    suggestions_out = []
    # iterate anchors
    for bank in banks:
        win_days = int(data.get("date_window_days", 365) or 365)
        local_books = [
            b for b in books
            if getattr(b, "currency_id", None) == getattr(bank, "currency_id", None)
            and getattr(b, "date", None) and getattr(bank, "date", None)
            and abs((bank.date - b.date).days) <= win_days
        ]
        if not local_books:
            continue

        # top-K embedding prefilter (guard k)
        top_k = min(K_EMBED, max(0, len(local_books)))
        top_idx = topk_by_embedding(bank.embedding or [], local_books, top_k)
        if top_idx:
            local_books = [local_books[i] for i in top_idx]
        # reduce by amount closeness
        if len(local_books) > MAX_CANDIDATES:
            local_books.sort(key=lambda b: abs(q2(getattr(b, "amount_base", 0)) - q2(getattr(bank, "amount", 0))))
            local_books = local_books[:MAX_CANDIDATES]

        book_amounts = [q2(getattr(b, "amount_base", 0)) for b in local_books]
        all_non_negative = all(a >= 0 for a in book_amounts)

        # extract tolerances and limits from data safely
        amount_tol = Decimal(str(data.get("amount_tolerance", "0.00") or "0.00"))
        max_group_books = int(data.get("max_group_size_book", 5) or 5)

        if all_non_negative and len(local_books) <= MAX_DP:
            combos_idx = subset_sum_bitset_indices(local_books, bank.amount, amount_tol, max_group_books)
        else:
            combos_idx = beam_search_indices(local_books, bank.amount, amount_tol, max_group_books, beam_size=BEAM_SIZE)

        # convert combos to suggestions
        for idxs in combos_idx:
            combo_books = [local_books[i] for i in idxs]
            avg_emb = _avg_embedding(combo_books)
            sim = cosine_similarity(bank.embedding or [], avg_emb)
            sum_books = sum(q2(getattr(b, "amount_base", 0)) for b in combo_books)
            amount_diff = abs(sum_books - q2(getattr(bank, "amount", 0)))
            avg_date = weighted_avg_date(combo_books)
            date_diff = abs((bank.date - avg_date).days) if (bank.date and avg_date) else 0

            scores = compute_match_scores(
                embed_sim=sim,
                amount_diff=float(amount_diff),
                amount_tol=float(amount_tol),
                date_diff=int(date_diff),
                date_tol=int(data.get("avg_date_delta_days", 1) or 1),
                currency_match=1.0,
                weights={"embedding": 0.5, "amount": 0.35, "date": 0.1, "currency": 0.05},
            )

            sug = {
                "match_type": "one_to_many_fast",
                "bank_ids": [bank.id],
                "journal_entries_ids": [b.id for b in combo_books],
                "confidence_score": float(scores.get("global_score", 0.0)),
                "abs_amount_diff": float(amount_diff),
                "component_scores": scores,
            }
            # persist suggestion row
            try:
                rs = ReconciliationSuggestion(
                    task=task_row,
                    company_id=bank.company_id,
                    match_type=sug["match_type"],
                    confidence_score=sug["confidence_score"],
                    abs_amount_diff=sug["abs_amount_diff"],
                    bank_ids=sug["bank_ids"],
                    journal_entry_ids=sug["journal_entries_ids"],
                    payload=sug,
                )
                rs.save()
                suggestions_out.append(sug)
            except Exception:
                log.exception("Failed persisting fast suggestion for task %s bank=%s", db_id, bank.id)

    # finalize
    task_row.suggestion_count = ReconciliationSuggestion.objects.filter(task=task_row).count()
    task_row.duration_seconds = time.time() - start_ts
    task_row.status = "completed"
    task_row.updated_at = timezone.now()
    task_row.save(update_fields=["suggestion_count", "duration_seconds", "status", "updated_at"])

    if auto_match_100:
        try:
            ReconciliationService._apply_auto_matches_100(suggestions_out)
        except Exception:
            log.exception("Auto-apply fast suggestions failed for task %s", db_id)

    return {"suggestions": suggestions_out, "stats": {"suggestion_count": len(suggestions_out), "duration_seconds": task_row.duration_seconds}}


@shared_task(bind=True)
def match_many_to_many_task(self, db_id, data, tenant_id=None, auto_match_100=False):
    """
    Legacy wrapper kept unchanged in semantics; small defensive fixes for company_id resolution.
    """
    task_obj = ReconciliationTask.objects.get(id=db_id)

    company_id = data.get("company_id", None) if isinstance(data, dict) else None
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
            log.exception("Failed to flush suggestions buffer for task %s", db_id)

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
        if now - last_flush_ts >= flush_interval:
            flush_buffer()

    try:
        task_obj.status = "running"
        task_obj.save(update_fields=["status", "updated_at"])
        logger.info("Task %s started: bank_ids=%s book_ids=%s config_id=%s pipeline_id=%s",
                    db_id, data.get("bank_ids") if isinstance(data, dict) else None,
                    data.get("book_ids") if isinstance(data, dict) else None,
                    data.get("config_id") if isinstance(data, dict) else None,
                    data.get("pipeline_id") if isinstance(data, dict) else None)

        result = ReconciliationService.match_many_to_many(
            data,
            tenant_id,
            auto_match_100=auto_match_100,
            on_suggestion=on_suggestion,
        )

        flush_buffer(force=True)

        suggestions = result.get("suggestions", []) or []
        auto_info = result.get("auto_match", {}) or {}
        stats = result.get("stats", {}) or {}

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

        # process auto-applied
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

        logger.info("Task %s completed: %d suggestions, %d auto-applied",
                    db_id, len(suggestions), auto_info.get("applied", 0))

        # persist stats
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


# --- remaining utility functions retained as before (not changed) ---
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
                except Exception:
                    log.warning("Failed saving embedding for %s id=%s", obj.__class__.__name__, getattr(obj, "id", None))
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