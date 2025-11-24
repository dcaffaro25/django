"""
embedding_service.py

This module provides the core logic for running reconciliation with
user‑calibratable weights on embedding similarity, amount, currency and
date.  It does not define any Django models; instead, it uses simple
data classes (DTOs) to carry data into a configurable matching engine.
"""

from __future__ import annotations
from time import monotonic
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from itertools import combinations
from typing import Callable, Dict, Iterable, List, Optional
from multitenancy.utils import resolve_tenant
#from .embedding_service import BankTransactionDTO, JournalEntryDTO, run_single_config, run_pipeline
from datetime import date as _date

# accounting/services/reconciliation_service.py

from collections.abc import Sequence

from typing import Dict, List, Optional, Callable  # <-- adicionar Callable



from django.db import transaction
from django.db.models import Q

from ..models import (
    BankTransaction,
    JournalEntry,
    Reconciliation,
    ReconciliationConfig,
    ReconciliationPipeline,
)


import logging

log = logging.getLogger("recon")

# ----------------------------------------------------------------------
#  DTOs for matching
# ----------------------------------------------------------------------
@dataclass
class BankTransactionDTO:
    id: int
    company_id: int
    date: date
    amount: Decimal
    currency_id: int
    description: str
    embedding: Optional[List[float]] = None

    @property
    def amount_base(self) -> Decimal:
        """Return the amount converted to base currency (stub)."""
        return self.amount


@dataclass
class JournalEntryDTO:
    id: int
    company_id: int
    transaction_id: int
    date: date
    effective_amount: Decimal
    currency_id: int
    description: str
    embedding: Optional[List[float]] = None

    @property
    def amount_base(self) -> Decimal:
        return self.effective_amount


# ----------------------------------------------------------------------
#  Stage and pipeline configuration
# ----------------------------------------------------------------------
@dataclass
class StageConfig:
    type: str
    enabled: bool = True
    max_group_size_bank: int = 1
    max_group_size_book: int = 1
    amount_tol: Decimal = Decimal("0")

    # NEW — split the old date tolerance into two independent knobs
    group_span_days: int = 0          # max day span allowed INSIDE a group (bank OR book)
    avg_date_delta_days: int = 0      # max |Δ| between weighted-average dates of the bank and book groups

    # optional weight overrides (None → inherit from config or default)
    embedding_weight: float | None = None
    amount_weight: float | None = None
    currency_weight: float | None = None
    date_weight: float | None = None
    
    # NEW: whether we allow mixed-sign amounts inside a group
    allow_mixed_signs: bool = False
    
    # NEW: number of alternatives to keep per anchor (bank/book)
    # 1 = only best; 3 = best + 2 alternatives, etc.
    max_alternatives_per_anchor: int = 2
    
    @property
    def candidate_window_days(self) -> int:
        """
        Cheap pre-filter window used to limit search breadth.
        We use the looser (max) of group_span_days and avg_date_delta_days.
        """
        return max(int(self.group_span_days or 0), int(self.avg_date_delta_days or 0), 0)



@dataclass
class PipelineConfig:
    stages: list[StageConfig] = field(default_factory=list)
    auto_apply_score: float = 1.0
    max_suggestions: int = 10000
    max_runtime_seconds: float | None = None   # NEW

# ----------------------------------------------------------------------
#  Utility functions
# ----------------------------------------------------------------------
CENT = Decimal("0.01")

def _sign(x: Decimal | None) -> int:
    if x is None:
        return 0
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0

def _as_vec_list(vec) -> Optional[List[float]]:
    """
    Return a plain list[float] for any pgvector/ndarray/list-like input,
    or None if the field is missing. Never uses truthiness of arrays.
    """
    if vec is None:
        return None
    # memoryview -> bytes (pgvector sometimes)
    if isinstance(vec, memoryview):
        try:
            vec = list(vec.tobytes())  # fall back to raw bytes if needed
        except Exception:
            vec = list(vec)
    try:
        return [float(x) for x in list(vec)]
    except Exception:
        try:
            # Some vector types are already iterable but not list()-able
            if isinstance(vec, Sequence):
                return [float(x) for x in vec]
        except Exception:
            pass
    return None

def q2(x: Decimal | None) -> Decimal:
    """Quantise a Decimal to two decimal places using standard rounding."""
    if x is None:
        return Decimal("0.00")
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_UP)


def build_date_bins(items: Iterable[object], get_date: Callable[[object], Optional[date]],
                    bin_size_days: int) -> Dict[int, List[object]]:
    """Bucket items into coarse bins keyed by date.toordinal() / bin_size_days."""
    from collections import defaultdict
    bins: Dict[int, List[object]] = defaultdict(list)
    for it in items:
        d = get_date(it)
        if not d:
            continue
        bins[d.toordinal() // bin_size_days].append(it)
    return bins


def iter_date_bin_candidates(target_date: date, bins: Dict[int, List[object]],
                              bin_size_days: int, tol_days: int) -> Iterable[object]:
    """Yield all items in bins whose date range intersects target_date ± tol_days."""
    if not target_date:
        return []
    start_bin = (target_date - timedelta(days=tol_days)).toordinal() // bin_size_days
    end_bin = (target_date + timedelta(days=tol_days)).toordinal() // bin_size_days
    for b in range(start_bin, end_bin + 1):
        for it in bins.get(b, []):
            yield it


def build_amount_buckets(items: Iterable[object], get_amount: Callable[[object], Decimal]) -> Dict[Decimal, List[object]]:
    """Bucket items by their quantised amount for fast approximate lookup."""
    from collections import defaultdict
    buckets: Dict[Decimal, List[object]] = defaultdict(list)
    for it in items:
        buckets[q2(get_amount(it))].append(it)
    return buckets


def probe_amount_buckets(buckets: Dict[Decimal, List[object]], base_amt: Decimal,
                         amount_tol: Decimal) -> Iterable[object]:
    """Yield items from buckets whose keys fall within ±amount_tol of base_amt."""
    step = CENT
    tol_steps = int((amount_tol / step).to_integral_value())
    base = q2(base_amt)
    for k in range(-tol_steps, tol_steps + 1):
        yield from buckets.get(q2(base + step * k), [])


def compute_match_scores(
    *,
    embed_sim: float,           # 0–1
    amount_diff: Decimal,       # absolute difference
    amount_tol: Decimal,        # tolerance (>= 0)
    date_diff: int,             # abs difference in days
    date_tol: int,              # tolerance (>= 0)
    currency_match: float,      # 0 or 1
    weights: Dict[str, float],  # embedding/amount/date/currency weights
) -> Dict[str, float]:
    """
    Return per-dimension scores (0–1) and a weighted global score.
    """
    # defensive guards for zero tolerances
    amt_norm = float(amount_diff / (amount_tol or CENT))
    amt_score = max(0.0, 1.0 - amt_norm)

    date_norm = float(date_diff) / float(date_tol or 1)
    date_score = max(0.0, 1.0 - date_norm)

    desc_score = max(0.0, min(1.0, float(embed_sim)))  # ensure 0–1
    curr_score = max(0.0, min(1.0, float(currency_match)))

    w_emb = float(weights.get("embedding", 0.0))
    w_amt = float(weights.get("amount", 0.0))
    w_date = float(weights.get("date", 0.0))
    w_curr = float(weights.get("currency", 0.0))

    global_score = round(
        w_emb * desc_score +
        w_amt * amt_score +
        w_date * date_score +
        w_curr * curr_score,
        4,
    )

    return {
        "description_score": desc_score,
        "amount_score": amt_score,
        "date_score": date_score,
        "currency_score": curr_score,
        "global_score": global_score,
    }

def compute_weighted_confidence(
    embed_sim: float,
    amount_diff: Decimal,
    amount_tol: Decimal,
    date_diff: int,
    date_tol: int,
    currency_match: float,
    weights: Dict[str, float],
) -> float:
    scores = compute_match_scores(
        embed_sim=embed_sim,
        amount_diff=amount_diff,
        amount_tol=amount_tol,
        date_diff=date_diff,
        date_tol=date_tol,
        currency_match=currency_match,
        weights=weights,
    )
    return scores["global_score"]

def _avg_embedding(items):
    vecs = [it.embedding for it in items if it.embedding]
    if not vecs:
        return []
    dim = len(vecs[0])
    sums = [0.0] * dim
    for v in vecs:
        for i, x in enumerate(v):
            sums[i] += x
    return [s / len(vecs) for s in sums]

# ----------------------------------------------------------------------
# Reconciliation pipeline engine
# ----------------------------------------------------------------------
class ReconciliationPipelineEngine:
    """
    Executes a sequence of matching stages on in-memory DTOs.  Supports exact,
    fuzzy, one-to-many, many-to-one and many-to-many matching with asymmetric
    group sizes and weighted confidence scoring.
    """
    def __init__(
        self,
        company_id: int,
        config: PipelineConfig,
        on_suggestion: Optional[Callable[[dict], None]] = None,  # <-- NOVO
    ):
        self.company_id = company_id
        self.config = config
        self.suggestions: List[dict] = []
        self.used_banks: set[int] = set()
        self.used_books: set[int] = set()

        self._seen_groups: set[tuple[tuple[int, ...], tuple[int, ...]]] = set()

        # callback opcional para stream de sugestões
        self._on_suggestion = on_suggestion

        # Per-stage or global weights; set externally before calling run()
        self.current_weights: Dict[str, float] | List[Dict[str, float]] = {
            "embedding": 0.50,
            "amount":    0.35,
            "currency":  0.10,
            "date":      0.05,
        }

        # Soft runtime limit support
        self.max_runtime_seconds: float | None = config.max_runtime_seconds
        self._start_ts: float = monotonic()
    
    def _time_exceeded(self) -> bool:
        """
        Return True if the configured soft time limit (if any) has been exceeded.
        """
        if not self.max_runtime_seconds:
            return False
        return (monotonic() - self._start_ts) >= self.max_runtime_seconds
    
    def _find_mixed_one_to_many_group(
        self,
        bank: BankTransactionDTO,
        local_books: List[JournalEntryDTO],
        stage: StageConfig,
    ) -> Optional[List[JournalEntryDTO]]:
        """
        Branch-and-bound search for a subset of `local_books` (mixed-sign amounts)
        whose sum matches bank.amount_base within the given tolerance.
    
        Applies:
          - amount tolerance (as a band [target - tol, target + tol])
          - currency check
          - group_span_days (books)
          - avg_date_delta_days between bank.date and weighted avg of book dates
        """
        n = len(local_books)
        if n == 0:
            return None
    
        amounts: List[Decimal] = [(b.amount_base or Decimal("0")) for b in local_books]
        target = q2(bank.amount_base)
        tol = stage.amount_tol or Decimal("0")
    
        # remaining min/max sums from each index
        rem_min = [Decimal("0")] * (n + 1)
        rem_max = [Decimal("0")] * (n + 1)
        for i in range(n - 1, -1, -1):
            a = amounts[i]
            if a >= 0:
                rem_max[i] = rem_max[i + 1] + a
                rem_min[i] = rem_min[i + 1]
            else:
                rem_min[i] = rem_min[i + 1] + a
                rem_max[i] = rem_max[i + 1]
    
        lower = target - tol
        upper = target + tol
        result_indices: Optional[List[int]] = None
    
        def dfs(idx: int, chosen: List[int], current_sum: Decimal):
            nonlocal result_indices
            if result_indices is not None:
                return
            if len(chosen) > stage.max_group_size_book:
                return
    
            if idx == n:
                if not chosen:
                    return
                if not (lower <= q2(current_sum) <= upper):
                    return
    
                combo = [local_books[i] for i in chosen]
    
                # currency check
                if any(b.currency_id != bank.currency_id for b in combo):
                    return
    
                # intra-side span (books)
                dates = [b.date for b in combo if b.date]
                book_span = (max(dates) - min(dates)).days if len(dates) >= 2 else 0
                if stage.group_span_days and book_span > stage.group_span_days:
                    return
    
                # cross-side avg date delta
                bank_avg = bank.date
                book_avg = self._weighted_avg_date(combo)
                win = stage.candidate_window_days
                avg_delta = abs((bank_avg - book_avg).days) if (bank_avg and book_avg) else win + 1
                if stage.avg_date_delta_days and avg_delta > stage.avg_date_delta_days:
                    return
    
                result_indices = chosen.copy()
                return
    
            # branch-and-bound: reachable range
            possible_min = current_sum + rem_min[idx]
            possible_max = current_sum + rem_max[idx]
            if possible_max < lower or possible_min > upper:
                return
    
            # skip
            dfs(idx + 1, chosen, current_sum)
            if result_indices is not None:
                return
            # take
            dfs(idx + 1, chosen + [idx], current_sum + amounts[idx])
    
        dfs(0, [], Decimal("0"))
    
        if result_indices is None:
            return None
        return [local_books[i] for i in result_indices]
    
        
    def run(self, banks: list[BankTransactionDTO], books: list[JournalEntryDTO]) -> list[dict]:
        log.debug(
            "PipelineEngine.run: company_id=%s stages=%d banks=%d books=%d max_suggestions=%d max_runtime=%s",
            self.company_id,
            len(self.config.stages),
            len(banks),
            len(books),
            self.config.max_suggestions,
            self.max_runtime_seconds,
        )

        for idx, stage in enumerate(self.config.stages):
            if not stage.enabled:
                log.debug("Stage %d (%s) skipped: enabled=False", idx, stage.type)
                continue
            
            if self._time_exceeded():
                log.debug(
                    "Time limit reached before stage %d (%s); stopping pipeline.",
                    idx, stage.type,
                )
                break
            
            self.stage_weights = (
                self.current_weights[idx]
                if isinstance(self.current_weights, list)
                else self.current_weights
            )
            
            handler = getattr(self, f"_run_{stage.type}", None)
            win = stage.candidate_window_days

            log.debug(
                "Stage %d (%s): weights=%s amount_tol=%s group_span_days=%d "
                "avg_date_delta_days=%d candidate_window_days=%d "
                "max_grp_bank=%d max_grp_book=%d banks=%d books=%d allow_mixed_signs=%s",
                idx, stage.type, self.stage_weights, stage.amount_tol,
                stage.group_span_days, stage.avg_date_delta_days, win,
                stage.max_group_size_bank, stage.max_group_size_book,
                len(banks), len(books), stage.allow_mixed_signs,
            )
    
            if handler:
                handler(banks, books, stage)
                
                if self._time_exceeded():
                    log.debug(
                        "Time limit reached after stage %d (%s); stopping pipeline.",
                        idx, stage.type,
                    )
                    break
                
                if len(self.suggestions) >= self.config.max_suggestions:
                    log.debug(
                        "Reached max_suggestions=%d at stage %d (%s); stopping.",
                        self.config.max_suggestions, idx, stage.type,
                    )
                    break
                
        log.debug(
            "PipelineEngine.run finished: suggestions=%d used_banks=%d used_books=%d",
            len(self.suggestions), len(self.used_banks), len(self.used_books),
        )
        return self.suggestions[: self.config.max_suggestions]

    # ------------------------ Stage handlers ------------------------

    def _run_exact_1to1(self, banks, books, stage: StageConfig):
        tol = int(stage.avg_date_delta_days or 0)
        for bank in banks:
            if self._time_exceeded():
                return
            
            if bank.id in self.used_banks:
                continue
            for book in books:
                if book.id in self.used_books:
                    continue
                if bank.company_id != book.company_id:
                    continue
                if q2(bank.amount_base) != q2(book.amount_base):
                    continue
                if bank.currency_id != book.currency_id:
                    continue
                # Cross-side constraint: |bank.date - book.date| <= avg_date_delta_days
                if bank.date and book.date and abs((bank.date - book.date).days) > tol:
                    continue
                self._record(
                    self._make_suggestion(
                        "exact_1to1",
                        [bank],
                        [book],
                        1.0,
                        stage=stage,
                        weights=self.stage_weights,
                    )
                )
                break

    def _run_one_to_many_legacy(self, banks, books, stage: StageConfig):
        available_books = [b for b in books if b.id not in self.used_books and b.company_id == self.company_id]
        win = stage.candidate_window_days
    
        for bank in banks:
            if self._time_exceeded():
                return
            
            if bank.id in self.used_banks:
                continue
    
            # cheap prefilter around the bank date
            local_books = [b for b in available_books if abs((bank.date - b.date).days) <= win]
    
            for size in range(1, stage.max_group_size_book + 1):
                for combo in combinations(local_books, size):
                    # live 'used' pruning (book side)
                    if any(x.id in self.used_books for x in combo):
                        continue
    
                    total = sum((b.amount_base for b in combo), Decimal("0"))
                    if q2(total) != q2(bank.amount_base):
                        continue
                    if any(b.currency_id != bank.currency_id for b in combo):
                        continue
    
                    # INTRA-side: span constraint ONLY for the grouped side (books)
                    book_dates = [b.date for b in combo if b.date]
                    book_span = (max(book_dates) - min(book_dates)).days if len(book_dates) >= 2 else 0
                    if stage.group_span_days and book_span > stage.group_span_days:
                        continue
    
                    # CROSS-side: weighted-avg date delta
                    bank_avg = bank.date
                    book_avg = self._weighted_avg_date(combo)
                    avg_delta = abs((bank_avg - book_avg).days) if (bank_avg and book_avg) else win + 1
                    if stage.avg_date_delta_days and avg_delta > stage.avg_date_delta_days:
                        continue
    
                    sim = self._cosine_similarity(bank.embedding or [], _avg_embedding(combo))
                    scores = compute_match_scores(
                        embed_sim=sim,
                        amount_diff=Decimal("0"),
                        amount_tol=stage.amount_tol or CENT,
                        date_diff=avg_delta,
                        date_tol=stage.avg_date_delta_days or 1,
                        currency_match=1.0,
                        weights=self.stage_weights,
                    )
                    self._record(
                        self._make_suggestion(
                            "one_to_many",
                            [bank],
                            list(combo),
                            scores["global_score"],
                            stage=stage,
                            weights=self.stage_weights,
                            component_scores=scores,
                            extra={
                                "book_span_days_measured": book_span,
                                "avg_date_delta_days_measured": avg_delta,
                            },
                        )
                    )
                    return
    
    
    
    def _find_mixed_many_to_one_group(
        self,
        book: JournalEntryDTO,
        local_banks: List[BankTransactionDTO],
        stage: StageConfig,
    ) -> Optional[List[BankTransactionDTO]]:
        """
        Branch-and-bound search for a subset of `local_banks` (mixed-sign amounts)
        whose sum matches book.amount_base within the given tolerance.

        Uses rem_min/rem_max bounds to prune branches. Applies:
          - amount tolerance
          - currency check
          - group_span_days (banks)
          - avg_date_delta_days between bank-group weighted avg date and book.date

        Returns the FIRST valid combination of banks, or None.
        """
        n = len(local_banks)
        if n == 0:
            return None

        amounts: List[Decimal] = [
            (b.amount_base or Decimal("0")) for b in local_banks
        ]
        target = q2(book.amount_base)
        tol = stage.amount_tol or Decimal("0")

        # Precompute remaining min/max sums from each index
        rem_min = [Decimal("0")] * (n + 1)
        rem_max = [Decimal("0")] * (n + 1)
        for i in range(n - 1, -1, -1):
            a = amounts[i]
            if a >= 0:
                rem_max[i] = rem_max[i + 1] + a
                rem_min[i] = rem_min[i + 1]
            else:
                rem_min[i] = rem_min[i + 1] + a
                rem_max[i] = rem_max[i + 1]

        lower = target - tol
        upper = target + tol
        result_indices: Optional[List[int]] = None

        def dfs(idx: int, chosen: List[int], current_sum: Decimal):
            nonlocal result_indices

            if result_indices is not None:
                return

            if len(chosen) > stage.max_group_size_bank:
                return

            if idx == n:
                if not chosen:
                    return
                if not (lower <= q2(current_sum) <= upper):
                    return

                combo = [local_banks[i] for i in chosen]

                # Currency check
                if any(b.currency_id != book.currency_id for b in combo):
                    return

                # INTRA-side span constraint for banks
                dates = [b.date for b in combo if b.date]
                bank_span = (max(dates) - min(dates)).days if len(dates) >= 2 else 0
                if stage.group_span_days and bank_span > stage.group_span_days:
                    return

                # CROSS-side avg date delta
                bank_avg = self._weighted_avg_date(combo)
                book_avg = book.date
                win = stage.candidate_window_days
                avg_delta = abs((bank_avg - book_avg).days) if (bank_avg and book_avg) else win + 1
                if stage.avg_date_delta_days and avg_delta > stage.avg_date_delta_days:
                    return

                result_indices = chosen.copy()
                return

            # Branch-and-bound: check reachable range
            possible_min = current_sum + rem_min[idx]
            possible_max = current_sum + rem_max[idx]
            if possible_max < lower or possible_min > upper:
                return

            # Option 1: skip this item
            dfs(idx + 1, chosen, current_sum)
            if result_indices is not None:
                return

            # Option 2: take this item
            dfs(idx + 1, chosen + [idx], current_sum + amounts[idx])

        dfs(0, [], Decimal("0"))

        if result_indices is None:
            return None

        return [local_banks[i] for i in result_indices]

    def _run_one_to_many(self, banks, books, stage: StageConfig):
        """
        One bank to many books.

        For each bank we choose up to `stage.max_alternatives_per_anchor` best
        book-combos ranked by global match score, and return them all as
        separate suggestions.

        Only the *best* suggestion per bank is marked as used via `_record`;
        the other alternatives are appended directly to `self.suggestions`
        without touching `used_banks` / `used_books`.
        """
        available_books = [
            b for b in books
            if b.id not in self.used_books and b.company_id == self.company_id
        ]
        win = stage.candidate_window_days
        max_k = max(int(stage.max_alternatives_per_anchor or 1), 1)

        log.debug(
            "_run_one_to_many: banks=%d books=%d win=%d amount_tol=%s allow_mixed=%s max_k=%d",
            len(banks), len(books), win, stage.amount_tol, stage.allow_mixed_signs, max_k,
        )

        def add_candidate(sug: dict, buf: list[dict]) -> None:
            score = float(sug.get("confidence_score", 0.0))
            if len(buf) < max_k:
                buf.append(sug)
                return
            worst_idx = min(range(len(buf)), key=lambda i: float(buf[i].get("confidence_score", 0.0)))
            if score > float(buf[worst_idx].get("confidence_score", 0.0)):
                buf[worst_idx] = sug

        for bank in banks:
            if self._time_exceeded():
                return
            if bank.id in self.used_banks:
                continue

            bank_amt = bank.amount_base or Decimal("0")
            bank_sign = _sign(bank_amt)

            # date window
            local_books = [
                b for b in available_books
                if b.date and bank.date and abs((bank.date - b.date).days) <= win
            ]
            if not local_books:
                continue

            # sign filtering if mixed_signs is False
            if not stage.allow_mixed_signs and bank_sign != 0:
                if bank_sign > 0:
                    local_books = [b for b in local_books if (b.amount_base or Decimal("0")) >= 0]
                else:
                    local_books = [b for b in local_books if (b.amount_base or Decimal("0")) <= 0]
                if not local_books:
                    continue

            book_amounts = [(b.amount_base or Decimal("0")) for b in local_books]
            if not book_amounts:
                continue

            has_pos = any(a > 0 for a in book_amounts)
            has_neg = any(a < 0 for a in book_amounts)
            mixed_signs = has_pos and has_neg

            candidates: list[dict] = []

            # ---- PATH 1: mixed-sign search (only if allowed) ----
            if mixed_signs and stage.allow_mixed_signs:
                combo = self._find_mixed_one_to_many_group(bank, local_books, stage)
                if combo:
                    book_dates = [b.date for b in combo if b.date]
                    book_span = (max(book_dates) - min(book_dates)).days if len(book_dates) >= 2 else 0
                    bank_avg = bank.date
                    book_avg = self._weighted_avg_date(combo)
                    avg_delta = abs((bank_avg - book_avg).days) if (bank_avg and book_avg) else win + 1

                    sim = self._cosine_similarity(bank.embedding or [], _avg_embedding(combo))
                    scores = compute_match_scores(
                        embed_sim=sim,
                        amount_diff=Decimal("0"),
                        amount_tol=stage.amount_tol or CENT,
                        date_diff=avg_delta,
                        date_tol=stage.avg_date_delta_days or 1,
                        currency_match=1.0,
                        weights=self.stage_weights,
                    )
                    sug = self._make_suggestion(
                        "one_to_many",
                        [bank],
                        list(combo),
                        scores["global_score"],
                        stage=stage,
                        weights=self.stage_weights,
                        component_scores=scores,
                        extra={
                            "book_span_days_measured": book_span,
                            "avg_date_delta_days_measured": avg_delta,
                            "mixed_signs": True,
                        },
                    )
                    add_candidate(sug, candidates)

            # ---- PATH 2: same-sign / bounded search ----
            target = q2(bank_amt)
            tol = stage.amount_tol or Decimal("0")

            min_possible = sum(a for a in book_amounts if a < 0)
            max_possible = sum(a for a in book_amounts if a > 0)
            L = target - tol
            U = target + tol
            if U < min_possible or L > max_possible:
                if candidates:
                    candidates.sort(key=lambda s: float(s["confidence_score"]), reverse=True)
                    best = candidates[0]
                    self._record(best)
                    for alt in candidates[1:]:
                        self.suggestions.append(alt)
                        if self._on_suggestion:
                            try:
                                self._on_suggestion(alt)
                            except Exception as cb_exc:
                                log.warning(
                                    "on_suggestion callback failed (alt one_to_many): %s",
                                    cb_exc,
                                )
                continue

            all_non_negative = all(a >= 0 for a in book_amounts)
            use_prefix_bounds = all_non_negative and target >= 0

            max_size = min(stage.max_group_size_book, len(local_books))

            prefix_max: List[Decimal] = []
            if use_prefix_bounds:
                amounts_desc = sorted(book_amounts, reverse=True)
                acc = Decimal("0")
                for amt in amounts_desc:
                    acc += amt
                    prefix_max.append(acc)
                if q2(prefix_max[-1]) + tol < target:
                    if candidates:
                        candidates.sort(key=lambda s: float(s["confidence_score"]), reverse=True)
                        best = candidates[0]
                        self._record(best)
                        for alt in candidates[1:]:
                            self.suggestions.append(alt)
                            if self._on_suggestion:
                                try:
                                    self._on_suggestion(alt)
                                except Exception as cb_exc:
                                    log.warning(
                                        "on_suggestion callback failed (alt many_to_many): %s",
                                        cb_exc,
                                    )
                    continue

            for size in range(1, max_size + 1):
                if self._time_exceeded():
                    return

                if use_prefix_bounds and q2(prefix_max[size - 1]) + tol < target:
                    continue

                for combo in combinations(local_books, size):
                    if any(x.id in self.used_books for x in combo):
                        continue

                    total = sum((b.amount_base for b in combo), Decimal("0"))
                    diff = abs(q2(total) - target)
                    if diff > stage.amount_tol:
                        continue
                    if any(b.currency_id != bank.currency_id for b in combo):
                        continue

                    book_dates = [b.date for b in combo if b.date]
                    book_span = (max(book_dates) - min(book_dates)).days if len(book_dates) >= 2 else 0
                    if stage.group_span_days and book_span > stage.group_span_days:
                        continue

                    bank_avg = bank.date
                    book_avg = self._weighted_avg_date(combo)
                    avg_delta = abs((bank_avg - book_avg).days) if (bank_avg and book_avg) else win + 1
                    if stage.avg_date_delta_days and avg_delta > stage.avg_date_delta_days:
                        continue

                    sim = self._cosine_similarity(bank.embedding or [], _avg_embedding(combo))
                    scores = compute_match_scores(
                        embed_sim=sim,
                        amount_diff=Decimal("0"),
                        amount_tol=stage.amount_tol or CENT,
                        date_diff=avg_delta,
                        date_tol=stage.avg_date_delta_days or 1,
                        currency_match=1.0,
                        weights=self.stage_weights,
                    )
                    sug = self._make_suggestion(
                        "one_to_many",
                        [bank],
                        list(combo),
                        scores["global_score"],
                        stage=stage,
                        weights=self.stage_weights,
                        component_scores=scores,
                        extra={
                            "book_span_days_measured": book_span,
                            "avg_date_delta_days_measured": avg_delta,
                            "mixed_signs": False,
                        },
                    )
                    add_candidate(sug, candidates)

            if candidates:
                candidates.sort(key=lambda s: float(s["confidence_score"]), reverse=True)
                best = candidates[0]
                self._record(best)
                for alt in candidates[1:]:
                    self.suggestions.append(alt)
                    if self._on_suggestion:
                        try:
                            self._on_suggestion(alt)
                        except Exception as cb_exc:
                            log.warning(
                                "on_suggestion callback failed (alt many_to_many): %s",
                                cb_exc,
                            )


    
    def _run_many_to_one(self, banks, books, stage: StageConfig):
        """
        Many banks to one book.

        For each book, keep up to `stage.max_alternatives_per_anchor` best
        bank-combos, record the best (affecting used_*), and add the rest as
        plain suggestions.
        """
        available_banks = [
            b for b in banks
            if b.id not in self.used_banks and b.company_id == self.company_id
        ]
        win = stage.candidate_window_days
        max_k = max(int(stage.max_alternatives_per_anchor or 1), 1)

        log.debug(
            "_run_many_to_one: banks=%d books=%d win=%d amount_tol=%s allow_mixed=%s max_k=%d",
            len(banks), len(books), win, stage.amount_tol, stage.allow_mixed_signs, max_k,
        )

        def add_candidate(sug: dict, buf: list[dict]) -> None:
            score = float(sug.get("confidence_score", 0.0))
            if len(buf) < max_k:
                buf.append(sug)
                return
            worst_idx = min(range(len(buf)), key=lambda i: float(buf[i].get("confidence_score", 0.0)))
            if score > float(buf[worst_idx].get("confidence_score", 0.0)):
                buf[worst_idx] = sug

        for book in books:
            if self._time_exceeded():
                return
            if book.id in self.used_books:
                continue

            book_amt = book.amount_base or Decimal("0")
            book_sign = _sign(book_amt)

            local_banks = [
                b for b in available_banks
                if b.date and book.date and abs((b.date - book.date).days) <= win
            ]
            if not local_banks:
                continue

            bank_amounts = [(b.amount_base or Decimal("0")) for b in local_banks]
            if not bank_amounts:
                continue

            has_pos = any(a > 0 for a in bank_amounts)
            has_neg = any(a < 0 for a in bank_amounts)
            mixed_signs = has_pos and has_neg

            if not stage.allow_mixed_signs and book_sign != 0:
                if book_sign > 0:
                    local_banks = [b for b in local_banks if (b.amount_base or Decimal("0")) >= 0]
                else:
                    local_banks = [b for b in local_banks if (b.amount_base or Decimal("0")) <= 0]
                if not local_banks:
                    continue
                bank_amounts = [(b.amount_base or Decimal("0")) for b in local_banks]
                has_pos = any(a > 0 for a in bank_amounts)
                has_neg = any(a < 0 for a in bank_amounts)
                mixed_signs = has_pos and has_neg

            candidates: list[dict] = []

            # ---- PATH 1: mixed-sign via DFS ----
            if mixed_signs and stage.allow_mixed_signs:
                combo = self._find_mixed_many_to_one_group(book, local_banks, stage)
                if combo:
                    bank_dates = [b.date for b in combo if b.date]
                    bank_span = (max(bank_dates) - min(bank_dates)).days if len(bank_dates) >= 2 else 0
                    bank_avg = self._weighted_avg_date(combo)
                    book_avg = book.date
                    avg_delta = abs((bank_avg - book_avg).days) if (bank_avg and book_avg) else win + 1

                    sim = self._cosine_similarity(_avg_embedding(combo), book.embedding or [])
                    scores = compute_match_scores(
                        embed_sim=sim,
                        amount_diff=Decimal("0"),
                        amount_tol=stage.amount_tol or CENT,
                        date_diff=avg_delta,
                        date_tol=stage.avg_date_delta_days or 1,
                        currency_match=1.0,
                        weights=self.stage_weights,
                    )
                    sug = self._make_suggestion(
                        "many_to_one",
                        list(combo),
                        [book],
                        scores["global_score"],
                        stage=stage,
                        weights=self.stage_weights,
                        component_scores=scores,
                        extra={
                            "bank_span_days_measured": bank_span,
                            "avg_date_delta_days_measured": avg_delta,
                            "mixed_signs": True,
                        },
                    )
                    add_candidate(sug, candidates)

            # ---- PATH 2: same-sign bounded search ----
            target = q2(book_amt)
            tol = stage.amount_tol or Decimal("0")

            min_possible = sum(a for a in bank_amounts if a < 0)
            max_possible = sum(a for a in bank_amounts if a > 0)
            L = target - tol
            U = target + tol
            if U < min_possible or L > max_possible:
                if candidates:
                    candidates.sort(key=lambda s: float(s["confidence_score"]), reverse=True)
                    best = candidates[0]
                    self._record(best)
                    for alt in candidates[1:]:
                        self.suggestions.append(alt)
                        if self._on_suggestion:
                            try:
                                self._on_suggestion(alt)
                            except Exception as cb_exc:
                                log.warning(
                                    "on_suggestion callback failed (alt many_to_one): %s",
                                    cb_exc,
                                )
                continue

            all_non_negative = all(a >= 0 for a in bank_amounts)
            use_prefix_bounds = all_non_negative and target >= 0

            max_size = min(stage.max_group_size_bank, len(local_banks))

            prefix_max: List[Decimal] = []
            if use_prefix_bounds:
                amounts_desc = sorted(bank_amounts, reverse=True)
                acc = Decimal("0")
                for amt in amounts_desc:
                    acc += amt
                    prefix_max.append(acc)
                if q2(prefix_max[-1]) + tol < target:
                    if candidates:
                        candidates.sort(key=lambda s: float(s["confidence_score"]), reverse=True)
                        best = candidates[0]
                        self._record(best)
                        for alt in candidates[1:]:
                            self.suggestions.append(alt)
                            if self._on_suggestion:
                                try:
                                    self._on_suggestion(alt)
                                except Exception as cb_exc:
                                    log.warning(
                                        "on_suggestion callback failed (alt many_to_many): %s",
                                        cb_exc,
                                    )
                    continue

            for size in range(1, max_size + 1):
                if self._time_exceeded():
                    return

                if use_prefix_bounds and q2(prefix_max[size - 1]) + tol < target:
                    continue

                for combo in combinations(local_banks, size):
                    if any(x.id in self.used_banks for x in combo):
                        continue

                    total = sum((b.amount_base for b in combo), Decimal("0"))
                    diff = abs(q2(total) - target)
                    if diff > stage.amount_tol:
                        continue
                    if any(b.currency_id != book.currency_id for b in combo):
                        continue

                    bank_dates = [b.date for b in combo if b.date]
                    bank_span = (max(bank_dates) - min(bank_dates)).days if len(bank_dates) >= 2 else 0
                    if stage.group_span_days and bank_span > stage.group_span_days:
                        continue

                    bank_avg = self._weighted_avg_date(combo)
                    book_avg = book.date
                    avg_delta = abs((bank_avg - book_avg).days) if (bank_avg and book_avg) else win + 1
                    if stage.avg_date_delta_days and avg_delta > stage.avg_date_delta_days:
                        continue

                    sim = self._cosine_similarity(_avg_embedding(combo), book.embedding or [])
                    scores = compute_match_scores(
                        embed_sim=sim,
                        amount_diff=Decimal("0"),
                        amount_tol=stage.amount_tol or CENT,
                        date_diff=avg_delta,
                        date_tol=stage.avg_date_delta_days or 1,
                        currency_match=1.0,
                        weights=self.stage_weights,
                    )
                    sug = self._make_suggestion(
                        "many_to_one",
                        list(combo),
                        [book],
                        scores["global_score"],
                        stage=stage,
                        weights=self.stage_weights,
                        component_scores=scores,
                        extra={
                            "bank_span_days_measured": bank_span,
                            "avg_date_delta_days_measured": avg_delta,
                            "mixed_signs": False,
                        },
                    )
                    add_candidate(sug, candidates)

            if candidates:
                candidates.sort(key=lambda s: float(s["confidence_score"]), reverse=True)
                best = candidates[0]
                self._record(best)
                for alt in candidates[1:]:
                    self.suggestions.append(alt)
                    if self._on_suggestion:
                        try:
                            self._on_suggestion(alt)
                        except Exception as cb_exc:
                            log.warning(
                                "on_suggestion callback failed (alt many_to_many): %s",
                                cb_exc,
                            )


    
    def _run_many_to_one_legacy(self, banks, books, stage: StageConfig):
        available_banks = [b for b in banks if b.id not in self.used_banks and b.company_id == self.company_id]
        win = stage.candidate_window_days
    
        for book in books:
            if self._time_exceeded():
                return
            
            if book.id in self.used_books:
                continue
    
            local_banks = [b for b in available_banks if abs((b.date - book.date).days) <= win]
    
            for size in range(1, stage.max_group_size_bank + 1):
                for combo in combinations(local_banks, size):
                    # FIX: check against used_banks (not used_books)
                    if any(x.id in self.used_banks for x in combo):
                        continue
    
                    total = sum((b.amount_base for b in combo), Decimal("0"))
                    if q2(total) != q2(book.amount_base):
                        continue
                    if any(b.currency_id != book.currency_id for b in combo):
                        continue
    
                    # INTRA-side: span constraint ONLY for the grouped side (banks)
                    bank_dates = [b.date for b in combo if b.date]
                    bank_span = (max(bank_dates) - min(bank_dates)).days if len(bank_dates) >= 2 else 0
                    if stage.group_span_days and bank_span > stage.group_span_days:
                        continue
    
                    # CROSS-side: weighted-avg date delta
                    bank_avg = self._weighted_avg_date(combo)
                    book_avg = book.date
                    avg_delta = abs((bank_avg - book_avg).days) if (bank_avg and book_avg) else win + 1
                    if stage.avg_date_delta_days and avg_delta > stage.avg_date_delta_days:
                        continue
    
                    sim = self._cosine_similarity(_avg_embedding(combo), book.embedding or [])
                    scores = compute_match_scores(
                        embed_sim=sim,
                        amount_diff=Decimal("0"),
                        amount_tol=stage.amount_tol or CENT,
                        date_diff=avg_delta,
                        date_tol=stage.avg_date_delta_days or 1,
                        currency_match=1.0,
                        weights=self.stage_weights,
                    )
                    self._record(
                        self._make_suggestion(
                            "many_to_one",
                            list(combo),
                            [book],
                            scores["global_score"],
                            stage=stage,
                            weights=self.stage_weights,
                            component_scores=scores,
                            extra={
                                "bank_span_days_measured": bank_span,
                                "avg_date_delta_days_measured": avg_delta,
                            },
                        )
                    )
                    return

    def _run_fuzzy_1to1(self, banks, books, stage: StageConfig):
        """
        Fuzzy 1-to-1 matching with global non-overlapping selection.

        Passos:
          1) Gerar todos os candidatos (bank, book) válidos com score
          2) Ordenar por global_score (e tie-breakers)
          3) Escolher um conjunto global de pares não sobrepostos (primários)
          4) Opcionalmente adicionar alternativas por bank, até
             stage.max_alternatives_per_anchor (sem marcar used_*).
        """
        win = stage.candidate_window_days
        bin_size = max(1, min(win or 1, 7))

        max_k = max(int(stage.max_alternatives_per_anchor or 1), 1)

        # Indexar books por bins de data para lookup mais rápido
        book_bins = build_date_bins(
            [b for b in books if b.id not in self.used_books],
            get_date=lambda e: e.date,
            bin_size_days=bin_size,
        )

        candidates: list[dict] = []

        for bank in banks:
            if self._time_exceeded():
                return
            if bank.id in self.used_banks:
                continue

            # Books "perto" em data
            candidates_in_window = list(
                iter_date_bin_candidates(bank.date, book_bins, bin_size, win)
            )
            if not candidates_in_window:
                continue

            # Bucket por amount em torno deste bank
            buckets = build_amount_buckets(
                candidates_in_window, get_amount=lambda e: e.amount_base
            )

            for book in probe_amount_buckets(
                buckets, bank.amount_base, stage.amount_tol
            ):
                if book.id in self.used_books:
                    continue

                # Guards básicos
                if bank.currency_id != book.currency_id:
                    continue

                a_diff = abs(q2(bank.amount_base) - q2(book.amount_base))
                if a_diff > stage.amount_tol:
                    continue

                # Δ de datas
                if bank.date and book.date:
                    avg_delta = abs((bank.date - book.date).days)
                else:
                    avg_delta = (stage.avg_date_delta_days or win or 0) + 1

                if stage.avg_date_delta_days and avg_delta > stage.avg_date_delta_days:
                    continue

                embed_sim = self._cosine_similarity(
                    bank.embedding or [], book.embedding or []
                )

                weights = {
                    "embedding": stage.embedding_weight
                    if stage.embedding_weight is not None
                    else self.stage_weights["embedding"],
                    "amount": stage.amount_weight
                    if stage.amount_weight is not None
                    else self.stage_weights["amount"],
                    "currency": stage.currency_weight
                    if stage.currency_weight is not None
                    else self.stage_weights["currency"],
                    "date": stage.date_weight
                    if stage.date_weight is not None
                    else self.stage_weights["date"],
                }

                scores = compute_match_scores(
                    embed_sim=embed_sim,
                    amount_diff=a_diff,
                    amount_tol=stage.amount_tol,
                    date_diff=avg_delta,
                    date_tol=stage.avg_date_delta_days or 1,
                    currency_match=1.0,
                    weights=weights,
                )

                candidates.append(
                    {
                        "bank": bank,
                        "book": book,
                        "scores": scores,
                        "weights": weights,
                        "embed_sim": float(embed_sim),
                        "amount_diff": float(a_diff),
                        "avg_delta": int(avg_delta),
                    }
                )

        if not candidates:
            return

        # GLOBAL SELECTION: melhores pares não sobrepostos
        candidates.sort(
            key=lambda c: (
                c["scores"]["global_score"],
                -abs(c["avg_delta"]),
                -abs(c["amount_diff"]),
            ),
            reverse=True,
        )

        local_used_banks: set[int] = set()
        local_used_books: set[int] = set()
        primary_pairs: set[tuple[int, int]] = set()  # (bank_id, book_id) primário

        for c in candidates:
            bank = c["bank"]
            book = c["book"]

            if (
                bank.id in self.used_banks
                or book.id in self.used_books
                or bank.id in local_used_banks
                or book.id in local_used_books
            ):
                continue

            scores = c["scores"]
            weights = c["weights"]

            suggestion = self._make_suggestion(
                "fuzzy_1to1",
                [bank],
                [book],
                scores["global_score"],
                stage=stage,
                weights=weights,
                component_scores=scores,
                extra={
                    "embed_similarity": c["embed_sim"],
                    "amount_diff": c["amount_diff"],
                    "avg_date_delta_days_measured": c["avg_delta"],
                    "currency_match": 1.0,
                },
            )

            self._record(suggestion)

            local_used_banks.add(bank.id)
            local_used_books.add(book.id)
            primary_pairs.add((bank.id, book.id))

            if len(self.suggestions) >= self.config.max_suggestions:
                break

        # Se max_k == 1, comportamento antigo: só um par por bank
        if max_k <= 1:
            return

        # Alternativas por bank (sem mexer em used_* global)
        per_bank_count: dict[int, int] = {
            bank_id: 1 for (bank_id, _) in primary_pairs
        }

        for c in candidates:
            if self._time_exceeded():
                return

            bank = c["bank"]
            book = c["book"]
            b_id = bank.id
            j_id = book.id

            # limite por bank
            current = per_bank_count.get(b_id, 0)
            if current >= max_k:
                continue

            # não repetir o par primário
            if (b_id, j_id) in primary_pairs:
                continue

            scores = c["scores"]
            weights = c["weights"]

            alt_suggestion = self._make_suggestion(
                "fuzzy_1to1",
                [bank],
                [book],
                scores["global_score"],
                stage=stage,
                weights=weights,
                component_scores=scores,
                extra={
                    "embed_similarity": c["embed_sim"],
                    "amount_diff": c["amount_diff"],
                    "avg_date_delta_days_measured": c["avg_delta"],
                    "currency_match": 1.0,
                    "alternative_for_bank": b_id,
                },
            )

            self.suggestions.append(alt_suggestion)
            per_bank_count[b_id] = current + 1

            if self._on_suggestion:
                try:
                    self._on_suggestion(alt_suggestion)
                except Exception as cb_exc:
                    log.warning(
                        "on_suggestion callback failed (alt fuzzy_1to1): %s", cb_exc
                    )

            if len(self.suggestions) >= self.config.max_suggestions:
                return


    
    def _run_many_to_many(self, banks, books, stage: StageConfig):
        """
        Many-to-many matching with amount-based pruning.

        For each anchor bank we choose up to `stage.max_alternatives_per_anchor`
        best (bank_combo, book_combo) pairs ranked by global score.

        Only the best per anchor is marked via `_record` (affecting used_*);
        the others are appended directly to `self.suggestions`.
        """
        sorted_banks = [b for b in banks if b.company_id == self.company_id]
        sorted_banks.sort(key=lambda b: b.date)
        sorted_books = [e for e in books if e.company_id == self.company_id]
        sorted_books.sort(key=lambda e: e.date)
    
        win = stage.candidate_window_days
        max_k = max(int(stage.max_alternatives_per_anchor or 1), 1)

        log.debug(
            "_run_many_to_many: banks=%d books=%d win=%d amount_tol=%s allow_mixed=%s max_k=%d",
            len(sorted_banks), len(sorted_books), win, stage.amount_tol, stage.allow_mixed_signs, max_k,
        )

        def add_candidate(sug: dict, buf: list[dict]) -> None:
            score = float(sug.get("confidence_score", 0.0))
            if len(buf) < max_k:
                buf.append(sug)
                return
            worst_idx = min(range(len(buf)), key=lambda i: float(buf[i].get("confidence_score", 0.0)))
            if score > float(buf[worst_idx].get("confidence_score", 0.0)):
                buf[worst_idx] = sug
    
        for bank in sorted_banks:
            if self._time_exceeded():
                return
            if bank.id in self.used_banks:
                continue

            bank_amt = bank.amount_base or Decimal("0")
            bank_sign = _sign(bank_amt)
    
            start = bank.date - timedelta(days=win)
            end = bank.date + timedelta(days=win)
            bank_window = [b for b in sorted_banks if start <= b.date <= end]
            book_window = [e for e in sorted_books if start <= e.date <= end]
            if not bank_window or not book_window:
                continue

            if not stage.allow_mixed_signs and bank_sign != 0:
                if bank_sign > 0:
                    bank_window = [b for b in bank_window if (b.amount_base or Decimal("0")) >= 0]
                    book_window = [e for e in book_window if (e.amount_base or Decimal("0")) >= 0]
                else:
                    bank_window = [b for b in bank_window if (b.amount_base or Decimal("0")) <= 0]
                    book_window = [e for e in book_window if (e.amount_base or Decimal("0")) <= 0]
                if not bank_window or not book_window:
                    continue

            candidates: list[dict] = []
            tol = stage.amount_tol or Decimal("0")
    
            for i in range(1, min(stage.max_group_size_bank, len(bank_window)) + 1):
                if self._time_exceeded():
                    return

                for bank_combo in combinations(bank_window, i):
                    if self._time_exceeded():
                        return
                    if bank.id != min(b.id for b in bank_combo):
                        continue
                    if any(bc.id in self.used_banks for bc in bank_combo):
                        continue
    
                    sum_bank = sum((b.amount_base for b in bank_combo), Decimal("0"))
                    target = q2(sum_bank)

                    book_amounts = [e.amount_base for e in book_window if e.amount_base is not None]
                    if not book_amounts:
                        continue

                    min_possible = sum(a for a in book_amounts if a < 0)
                    max_possible = sum(a for a in book_amounts if a > 0)
                    L = target - tol
                    U = target + tol
                    if U < min_possible or L > max_possible:
                        continue

                    all_non_negative = all(a >= 0 for a in book_amounts)
                    use_prefix_bounds = all_non_negative and target >= 0

                    book_prefix_max: List[Decimal] = []
                    if use_prefix_bounds:
                        book_amounts_desc = sorted(book_amounts, reverse=True)
                        acc = Decimal("0")
                        for amt in book_amounts_desc:
                            acc += amt
                            book_prefix_max.append(acc)
                        if q2(book_prefix_max[-1]) + tol < target:
                            continue
    
                    max_book_group_size = min(stage.max_group_size_book, len(book_window))

                    for j in range(1, max_book_group_size + 1):
                        if self._time_exceeded():
                            return

                        if use_prefix_bounds and q2(book_prefix_max[j - 1]) + tol < target:
                            continue

                        for book_combo in combinations(book_window, j):
                            if self._time_exceeded():
                                return
                            if any(bk.id in self.used_books for bk in book_combo):
                                continue
    
                            sum_book = sum((e.amount_base for e in book_combo), Decimal("0"))
                            diff = abs(q2(sum_book) - target)
                            if diff > stage.amount_tol:
                                continue
                            if any(b.currency_id != e.currency_id for b in bank_combo for e in book_combo):
                                continue
    
                            bank_span = self._date_span_days(bank_combo)
                            book_span = self._date_span_days(book_combo)
                            if stage.group_span_days:
                                if bank_span > stage.group_span_days:
                                    continue
                                if book_span > stage.group_span_days:
                                    continue
    
                            bank_avg = self._weighted_avg_date(bank_combo)
                            book_avg = self._weighted_avg_date(book_combo)
                            avg_delta = abs((bank_avg - book_avg).days) if (bank_avg and book_avg) else win + 1
                            if stage.avg_date_delta_days and avg_delta > stage.avg_date_delta_days:
                                continue
    
                            emb_bank = _avg_embedding(bank_combo)
                            emb_book = _avg_embedding(book_combo)
                            embed_sim = self._cosine_similarity(emb_bank, emb_book)
    
                            scores = compute_match_scores(
                                embed_sim=embed_sim,
                                amount_diff=Decimal("0"),
                                amount_tol=stage.amount_tol or CENT,
                                date_diff=avg_delta,
                                date_tol=stage.avg_date_delta_days or 1,
                                currency_match=1.0,
                                weights=self.stage_weights,
                            )
    
                            sug = self._make_suggestion(
                                "many_to_many",
                                list(bank_combo),
                                list(book_combo),
                                scores["global_score"],
                                stage=stage,
                                weights=self.stage_weights,
                                component_scores=scores,
                                extra={
                                    "bank_span_days_measured": bank_span,
                                    "book_span_days_measured": book_span,
                                    "avg_date_delta_days_measured": avg_delta,
                                    "mixed_signs_allowed": stage.allow_mixed_signs,
                                },
                            )
                            add_candidate(sug, candidates)

            if candidates:
                candidates.sort(key=lambda s: float(s["confidence_score"]), reverse=True)
                best = candidates[0]
                self._record(best)
                for alt in candidates[1:]:
                    self.suggestions.append(alt)
                    if self._on_suggestion:
                        try:
                            self._on_suggestion(alt)
                        except Exception as cb_exc:
                            log.warning(
                                "on_suggestion callback failed (alt many_to_many): %s",
                                cb_exc,
                            )


    
    def _run_many_to_many_legacy(self, banks, books, stage: StageConfig):
        # Copy & sort (company-filtered)
        sorted_banks = [b for b in banks if b.company_id == self.company_id]
        sorted_banks.sort(key=lambda b: b.date)
        sorted_books = [e for e in books if e.company_id == self.company_id]
        sorted_books.sort(key=lambda e: e.date)
    
        win = stage.candidate_window_days
        log.debug("Starting many-to-many company=%d banks=%d books=%d win=%d",
                  self.company_id, len(sorted_banks), len(sorted_books), win)
    
        for bank in sorted_banks:
            if self._time_exceeded():
                return
            
            if bank.id in self.used_banks:
                continue
    
            start = bank.date - timedelta(days=win)
            end   = bank.date + timedelta(days=win)
            bank_window = [b for b in sorted_banks if start <= b.date <= end]
            book_window = [e for e in sorted_books if start <= e.date <= end]
    
            for i in range(1, min(stage.max_group_size_bank, len(bank_window)) + 1):
                for bank_combo in combinations(bank_window, i):
                    # anchor to avoid duplicates
                    if bank.id != min(b.id for b in bank_combo):
                        continue
                    if any(bc.id in self.used_banks for bc in bank_combo):
                        continue
    
                    sum_bank = sum((b.amount_base for b in bank_combo), Decimal("0"))
    
                    for j in range(1, min(stage.max_group_size_book, len(book_window)) + 1):
                        for book_combo in combinations(book_window, j):
                            if any(bk.id in self.used_books for bk in book_combo):
                                continue
    
                            sum_book = sum((e.amount_base for e in book_combo), Decimal("0"))
                            if q2(sum_bank) != q2(sum_book):
                                continue
                            if any(b.currency_id != e.currency_id for b in bank_combo for e in book_combo):
                                continue
    
                            # INTRA-side spans (separate checks)
                            bank_span = self._date_span_days(bank_combo)
                            book_span = self._date_span_days(book_combo)
                            if stage.group_span_days:
                                if bank_span > stage.group_span_days:
                                    continue
                                if book_span > stage.group_span_days:
                                    continue
    
                            # CROSS-side weighted-avg delta
                            bank_avg = self._weighted_avg_date(bank_combo)
                            book_avg = self._weighted_avg_date(book_combo)
                            avg_delta = abs((bank_avg - book_avg).days) if (bank_avg and book_avg) else win + 1
                            if stage.avg_date_delta_days and avg_delta > stage.avg_date_delta_days:
                                continue
    
                            emb_bank = _avg_embedding(bank_combo)
                            emb_book = _avg_embedding(book_combo)
                            embed_sim = self._cosine_similarity(emb_bank, emb_book)
    
                            scores = compute_match_scores(
                                embed_sim=embed_sim,
                                amount_diff=Decimal("0"),
                                amount_tol=stage.amount_tol or CENT,
                                date_diff=avg_delta,
                                date_tol=stage.avg_date_delta_days or 1,
                                currency_match=1.0,
                                weights=self.stage_weights,
                            )
    
                            self._record(
                                self._make_suggestion(
                                    "many_to_many",
                                    list(bank_combo),
                                    list(book_combo),
                                    scores["global_score"],
                                    stage=stage,
                                    weights=self.stage_weights,
                                    component_scores=scores,
                                    extra={
                                        "bank_span_days_measured": bank_span,
                                        "book_span_days_measured": book_span,
                                        "avg_date_delta_days_measured": avg_delta,
                                    },
                                )
                            )

    # ------------------------ Internal helpers ------------------------

    def _date_span_days(self, items) -> int:
        dates = [it.date for it in items if it.date]
        return (max(dates) - min(dates)).days if len(dates) >= 2 else 0

    def _weighted_avg_date(self, items) -> Optional[date]:
        pairs = [(it.date, abs(it.amount_base)) for it in items if it.date and it.amount_base is not None]
        if not pairs:
            return None
        total_abs = sum((w for _, w in pairs), Decimal("0"))
        if not total_abs:
            return None
        num = sum((Decimal(d.toordinal()) * w for d, w in pairs), Decimal("0"))
        ord_ = int((num / total_abs).to_integral_value(ROUND_HALF_UP))
        return _date.fromordinal(ord_)
    
    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        if not v1 or not v2:
            return 0.0
        from math import sqrt
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = sqrt(sum(a * a for a in v1))
        norm2 = sqrt(sum(b * b for b in v2))
        return dot / (norm1 * norm2) if norm1 and norm2 else 0.0
    
    def _aggregate_group_stats(self, items, *, is_bank: bool) -> dict:
        """
        Compute descriptive statistics and formatted lines for a group of
        BankTransactionDTOs or JournalEntryDTOs.
        """
        from datetime import date as _date

        amounts: List[Decimal] = []
        dates: List[date] = []
        for it in items:
            amt = it.amount_base
            if amt is not None:
                amounts.append(amt)
            if it.date:
                dates.append(it.date)

        count = len(items)
        sum_amount = sum(amounts, Decimal("0")) if amounts else Decimal("0")

        min_date = min(dates) if dates else None
        max_date = max(dates) if dates else None

        weighted_avg_date = None
        if dates and amounts:
            pairs = [(it.date, abs(it.amount_base)) for it in items if it.date and it.amount_base is not None]
            total_abs = sum((w for _, w in pairs), Decimal("0"))
            if total_abs:
                num = sum((Decimal(d.toordinal()) * w for d, w in pairs), Decimal("0"))
                ord_ = int((num / total_abs).to_integral_value(ROUND_HALF_UP))
                weighted_avg_date = _date.fromordinal(ord_)

        lines = []
        for it in items:
            d = it.date.isoformat() if it.date else "N/A"
            v = q2(it.amount_base)
            desc = (it.description or "").replace("\n", " ").strip()
            prefix = "BANK" if is_bank else "BOOK"
            lines.append(f"{prefix}#{it.id} | {d} | {v} | {desc}")

        return {
            "count": count,
            "sum_amount": float(q2(sum_amount)),
            "min_date": min_date.isoformat() if min_date else None,
            "max_date": max_date.isoformat() if max_date else None,
            "weighted_avg_date": weighted_avg_date.isoformat() if weighted_avg_date else None,
            "lines_text": "\n".join(lines),
        }
    
    def _make_suggestion(
        self,
        match_type: str,
        bank_items: List[BankTransactionDTO],
        book_items: List[JournalEntryDTO],
        conf: float,
        *,
        stage: StageConfig | None = None,
        weights: Optional[Dict[str, float]] = None,
        extra: Optional[Dict[str, object]] = None,
        component_scores: Optional[Dict[str, float]] = None,
    ) -> dict:
        """
        Build a rich suggestion payload for front-end / API consumption.
        """
        weights = weights or getattr(self, "stage_weights", self.current_weights)

        bank_stats = self._aggregate_group_stats(bank_items, is_bank=True)
        book_stats = self._aggregate_group_stats(book_items, is_bank=False)

        sum_bank = Decimal(str(bank_stats["sum_amount"]))
        sum_book = Decimal(str(book_stats["sum_amount"]))
        abs_diff = float(q2(abs(sum_bank - sum_book)))

        match_params = {}
        if stage is not None:
            match_params = {
                "amount_tolerance": float(stage.amount_tol),
                "date_group_span_days": int(stage.group_span_days),
                "date_avg_delta_days": int(stage.avg_date_delta_days),
                "max_group_size_bank": int(stage.max_group_size_bank),
                "max_group_size_book": int(stage.max_group_size_book),
            }

        suggestion = {
            "match_type": match_type,
            "bank_ids": [b.id for b in bank_items],
            "journal_entries_ids": [e.id for e in book_items],
            "bank_stats": {
                "count": bank_stats["count"],
                "sum_amount": bank_stats["sum_amount"],
                "min_date": bank_stats["min_date"],
                "weighted_avg_date": bank_stats["weighted_avg_date"],
                "max_date": bank_stats["max_date"],
            },
            "book_stats": {
                "count": book_stats["count"],
                "sum_amount": book_stats["sum_amount"],
                "min_date": book_stats["min_date"],
                "weighted_avg_date": book_stats["weighted_avg_date"],
                "max_date": book_stats["max_date"],
            },
            "bank_lines": bank_stats["lines_text"],
            "book_lines": book_stats["lines_text"],
            "abs_amount_diff": abs_diff,
            "confidence_score": float(conf),
            "confidence_weights": {
                "embedding": float(weights.get("embedding", 0.0)),
                "amount": float(weights.get("amount", 0.0)),
                "currency": float(weights.get("currency", 0.0)),
                "date": float(weights.get("date", 0.0)),
            },
            "match_parameters": match_params,
        }

        if component_scores:
            suggestion["component_scores"] = component_scores

        if extra:
            suggestion["extra"] = extra

        return suggestion

    def _record(self, suggestion: dict) -> None:
        """
        Record a suggestion and mark participating IDs as used, but skip exact duplicates.
        A duplicate is any suggestion with the same set of bank_ids and book_ids.
        """
        bank_key = tuple(sorted(suggestion["bank_ids"]))
        book_key = tuple(sorted(suggestion["journal_entries_ids"]))
        key = (bank_key, book_key)

        if key in self._seen_groups:
            log.debug(
                "Skipping duplicate suggestion: banks=%s books=%s",
                bank_key,
                book_key,
            )
            return

        self._seen_groups.add(key)

        log.debug(
            "Recording suggestion: type=%s, bank_ids=%s, journal_ids=%s, confidence=%.4f",
            suggestion["match_type"],
            suggestion["bank_ids"],
            suggestion["journal_entries_ids"],
            suggestion["confidence_score"],
        )

        self.suggestions.append(suggestion)
        self.used_banks.update(suggestion["bank_ids"])
        self.used_books.update(suggestion["journal_entries_ids"])

        # Dispara callback (para persistência incremental, etc.)
        if self._on_suggestion:
            try:
                self._on_suggestion(suggestion)
            except Exception as cb_exc:
                log.warning("on_suggestion callback failed: %s", cb_exc)




# ----------------------------------------------------------------------
# Helper functions to run a single config or a pipeline
# ----------------------------------------------------------------------
def run_single_config(cfg: object,
                      banks: List[BankTransactionDTO],
                      books: List[JournalEntryDTO],
                      company_id: int,
                      on_suggestion: Optional[Callable[[dict], None]] = None) -> List[dict]:
    """
    Execute a single ReconciliationConfig using the pipeline engine.
    """

    # determine type for a single-stage config:
    if cfg.max_group_size_bank == 1 and cfg.max_group_size_book > 1:
        stage_type = "one_to_many"
    elif cfg.max_group_size_bank > 1 and cfg.max_group_size_book == 1:
        stage_type = "many_to_one"
    elif cfg.max_group_size_bank > 1 and cfg.max_group_size_book > 1:
        stage_type = "many_to_many"
    elif cfg.amount_tolerance > 0 or (
        getattr(cfg, "group_span_days", 0) > 0
        or getattr(cfg, "avg_date_delta_days", 0) > 0
    ):
        stage_type = "fuzzy_1to1"
    else:
        stage_type = "exact_1to1"
    
    soft_limit = getattr(cfg, "soft_time_limit_seconds", None)
    allow_mixed = bool(getattr(cfg, "allow_mixed_signs", False))
    max_alts = int(getattr(cfg, "max_alternatives_per_match", 1) or 1)
    
    log.debug(
        "run_single_config: cfg_id=%s company_id=%s stage_type=%s "
        "max_group_size_bank=%d max_group_size_book=%d "
        "amount_tolerance=%s group_span_days=%s avg_date_delta_days=%s "
        "allow_mixed_signs=%s soft_time_limit=%s max_alternatives=%d",
        getattr(cfg, "id", None), company_id, stage_type,
        cfg.max_group_size_bank, cfg.max_group_size_book,
        cfg.amount_tolerance, getattr(cfg, "group_span_days", None),
        getattr(cfg, "avg_date_delta_days", None),
        allow_mixed, soft_limit, max_alts,
    )

    stage = StageConfig(
        type=stage_type,
        max_group_size_bank=cfg.max_group_size_bank,
        max_group_size_book=cfg.max_group_size_book,
        amount_tol=cfg.amount_tolerance,
        group_span_days=getattr(cfg, "group_span_days", 0),
        avg_date_delta_days=getattr(cfg, "avg_date_delta_days", 0),
        allow_mixed_signs=allow_mixed,
        max_alternatives_per_anchor=max_alts,
    )
    
    log.debug("run_single_config: StageConfig=%s", stage)
    
    max_runtime = None
    try:
        if soft_limit is not None and float(soft_limit) > 0:
            max_runtime = float(soft_limit)
    except Exception:
        max_runtime = None

    pipe_cfg = PipelineConfig(
        stages=[stage],
        auto_apply_score=float(getattr(cfg, "min_confidence", 1.0)),
        max_suggestions=getattr(cfg, "max_suggestions", 10000),
        max_runtime_seconds=max_runtime,   # <-- use None when soft_limit is 0 or invalid
    )
    engine = ReconciliationPipelineEngine(
        company_id=company_id,
        config=pipe_cfg,
        on_suggestion=on_suggestion,  # <-- NOVO
    )
    engine.current_weights = {
        "embedding": float(getattr(cfg, "embedding_weight", 0.50)),
        "amount":    float(getattr(cfg, "amount_weight",    0.35)),
        "currency":  float(getattr(cfg, "currency_weight",  0.10)),
        "date":      float(getattr(cfg, "date_weight",      0.05)),
    }
    suggestions = engine.run(banks, books)
    min_conf = float(getattr(cfg, "min_confidence", 0))
    if min_conf:
        suggestions = [s for s in suggestions if s["confidence_score"] >= min_conf]
    log.debug(
        "run_single_config: cfg_id=%s produced %d suggestions (min_conf=%.3f)",
        getattr(cfg, "id", None), len(suggestions), min_conf,
    )
    return suggestions


def run_pipeline(pipeline: object,
                 banks: List[BankTransactionDTO],
                 books: List[JournalEntryDTO],
                 on_suggestion: Optional[Callable[[dict], None]] = None) -> List[dict]:
    """
    Execute a multi-stage pipeline.
    """
    stage_configs: list[StageConfig] = []
    weight_list: list[dict[str, float]] = []

    log.debug(
        "run_pipeline: pipeline_id=%s company_id=%s stages_db=%d auto_apply_score=%s max_suggestions=%s",
        getattr(pipeline, "id", None),
        pipeline.company_id,
        pipeline.stages.count() if hasattr(pipeline.stages, "count") else None,
        getattr(pipeline, "auto_apply_score", None),
        getattr(pipeline, "max_suggestions", None),
    )

    for idx, stage_obj in enumerate(pipeline.stages.select_related("config").order_by("order")):
        cfg = stage_obj.config
        if not stage_obj.enabled:
            log.debug("run_pipeline: stage[%d] disabled; skipping", idx)
            continue

        span = stage_obj.group_span_days if stage_obj.group_span_days is not None else getattr(cfg, "group_span_days", 0)
        delta = stage_obj.avg_date_delta_days if stage_obj.avg_date_delta_days is not None else getattr(cfg, "avg_date_delta_days", 0)

        eff_bank_size = stage_obj.max_group_size_bank or cfg.max_group_size_bank
        eff_book_size = stage_obj.max_group_size_book or cfg.max_group_size_book
        eff_amount_tol = (
            stage_obj.amount_tolerance
            if stage_obj.amount_tolerance is not None
            else cfg.amount_tolerance
        )

        if eff_bank_size == 1 and eff_book_size > 1:
            stage_type = "one_to_many"
        elif eff_bank_size > 1 and eff_book_size == 1:
            stage_type = "many_to_one"
        elif eff_bank_size > 1 and eff_book_size > 1:
            stage_type = "many_to_many"
        elif eff_amount_tol > 0 or (span > 0 or delta > 0):
            stage_type = "fuzzy_1to1"
        else:
            stage_type = "exact_1to1"

        allow_mixed = getattr(stage_obj, "allow_mixed_signs", None)
        if allow_mixed is None:
            allow_mixed = getattr(cfg, "allow_mixed_signs", False)

        max_alts = getattr(stage_obj, "max_alternatives_per_match", None)
        if max_alts is None:
            max_alts = getattr(cfg, "max_alternatives_per_match", 1)

        log.debug(
            "run_pipeline: stage[%d] db_stage_id=%s order=%s cfg_id=%s type=%s "
            "cfg_group_span=%s stage_group_span=%s -> span=%s "
            "cfg_avg_delta=%s stage_avg_delta=%s -> delta=%s "
            "max_group_size_bank=%s max_group_size_book=%s "
            "allow_mixed_signs=%s max_alternatives=%s eff_amount_tol=%s",
            idx,
            getattr(stage_obj, "id", None),
            getattr(stage_obj, "order", None),
            getattr(cfg, "id", None),
            stage_type,
            getattr(cfg, "group_span_days", None),
            getattr(stage_obj, "group_span_days", None),
            span,
            getattr(cfg, "avg_date_delta_days", None),
            getattr(stage_obj, "avg_date_delta_days", None),
            delta,
            eff_bank_size,
            eff_book_size,
            allow_mixed,
            max_alts,
            eff_amount_tol,
        )

        stage_conf = StageConfig(
            type=stage_type,
            enabled=True,
            max_group_size_bank=eff_bank_size,
            max_group_size_book=eff_book_size,
            amount_tol=eff_amount_tol,
            group_span_days=span,
            avg_date_delta_days=delta,
            embedding_weight=float(getattr(stage_obj, "embedding_weight", None))
            if getattr(stage_obj, "embedding_weight", None) is not None
            else float(cfg.embedding_weight),
            amount_weight=float(getattr(stage_obj, "amount_weight", None))
            if getattr(stage_obj, "amount_weight", None) is not None
            else float(cfg.amount_weight),
            currency_weight=float(getattr(stage_obj, "currency_weight", None))
            if getattr(stage_obj, "currency_weight", None) is not None
            else float(cfg.currency_weight),
            date_weight=float(getattr(stage_obj, "date_weight", None))
            if getattr(stage_obj, "date_weight", None) is not None
            else float(cfg.date_weight),
            allow_mixed_signs=bool(allow_mixed),
            max_alternatives_per_anchor=int(max_alts or 1),
        )

        log.debug("run_pipeline: stage[%d] StageConfig=%s", idx, stage_conf)

        stage_configs.append(stage_conf)
        weight_list.append(
            {
                "embedding": float(getattr(stage_obj, "embedding_weight", None))
                if getattr(stage_obj, "embedding_weight", None) is not None
                else float(cfg.embedding_weight),
                "amount": float(getattr(stage_obj, "amount_weight", None))
                if getattr(stage_obj, "amount_weight", None) is not None
                else float(cfg.amount_weight),
                "currency": float(getattr(stage_obj, "currency_weight", None))
                if getattr(stage_obj, "currency_weight", None) is not None
                else float(cfg.currency_weight),
                "date": float(getattr(stage_obj, "date_weight", None))
                if getattr(stage_obj, "date_weight", None) is not None
                else float(cfg.date_weight),
            }
        )

    soft_limit = getattr(pipeline, "soft_time_limit_seconds", None)

    max_runtime = None
    try:
        if soft_limit is not None and float(soft_limit) > 0:
            max_runtime = float(soft_limit)
    except Exception:
        max_runtime = None

    pipe_cfg = PipelineConfig(
        stages=stage_configs,
        auto_apply_score=float(pipeline.auto_apply_score),
        max_suggestions=pipeline.max_suggestions,
        max_runtime_seconds=max_runtime,
    )

    log.debug(
        "run_pipeline: built %d StageConfig(s); soft_time_limit=%s",
        len(stage_configs), soft_limit,
    )

    engine = ReconciliationPipelineEngine(
        company_id=pipeline.company_id,
        config=pipe_cfg,
        on_suggestion=on_suggestion,  # <-- NOVO
    )
    engine.current_weights = weight_list
    return engine.run(banks, books)




class ReconciliationService:
    """
    High-level service to run reconciliation using either a single configuration
    or a multi-stage pipeline.  No legacy matching functions are used.
    """

    @staticmethod
    def match_many_to_many(
        data: Dict[str, object],
        tenant_id: Optional[str] = None,
        *,
        auto_match_100: bool = False,
        on_suggestion: Optional[Callable[[dict], None]] = None,
    ) -> Dict[str, object]:
        """
        Execute reconciliation based on a config_id or pipeline_id in `data`.
        It refuses to run if neither is provided.

        Returns:
          {
            "suggestions": [...],
            "auto_match": {...},
            "stats": {...}
          }
        """
        start_ts = monotonic()

        config_id = data.get("config_id")
        pipeline_id = data.get("pipeline_id")
        if not (config_id or pipeline_id):
            raise ValueError("Either config_id or pipeline_id must be provided")
        
        company_id = resolve_tenant(tenant_id).id

        # Build candidate QuerySets
        bank_ids = data.get("bank_ids", [])
        book_ids = data.get("book_ids", [])
        bank_qs = (
            BankTransaction.objects
            .exclude(reconciliations__status__in=["matched", "approved"])
            .filter(company_id=company_id)
            .only("id", "company_id", "date", "amount", "currency_id", "description", "description_embedding")
        )
        bank_count_initial = bank_qs.count()
        log.debug(
            "Initial unmatched bank transactions count (company_id=%s): %d",
            company_id, bank_count_initial,
        )
        
        if bank_ids:
            bank_qs = bank_qs.filter(id__in=bank_ids)
            filtered_count = bank_qs.count()
            log.debug(
                "Filtered bank transactions by provided IDs (%d ids) for company_id=%s: %d records remain",
                len(bank_ids),
                company_id,
                filtered_count,
            )
        else:
            log.debug(
                "No bank_ids provided; using all unmatched bank transactions for company_id=%s (%d records)",
                company_id,
                bank_count_initial,
            )
        
        book_qs = (
            JournalEntry.objects
            .exclude(reconciliations__status__in=["matched", "approved"])
            .filter(company_id=company_id)              # <- NOVO: escopo por company
            .filter(account__bank_account__isnull=False)
            .select_related("transaction")
            .only(
                "id", "company_id", "transaction_id", "date",
                "debit_amount", "credit_amount", "account_id",
                "transaction__date", "transaction__currency_id",
                "transaction__description", "transaction__description_embedding",
            )
        )
        book_count_initial = book_qs.count()
        log.debug(
            "Initial unmatched journal entries count (company_id=%s): %d",
            company_id,
            book_count_initial,
        )

        if book_ids:
            book_qs = book_qs.filter(id__in=book_ids)
            filtered_book_count = book_qs.count()
            log.debug(
                "Filtered journal entries by provided IDs (%d ids) for company_id=%s: %d records remain",
                len(book_ids),
                company_id,
                filtered_book_count,
            )
        else:
            log.debug(
                "No book_ids provided; using all unmatched journal entries for company_id=%s (%d records)",
                company_id,
                book_count_initial,
            )

        # Only consider journal entries that belong to a bank account
        pre_account_count = book_qs.count()
        book_qs = book_qs.filter(account__bank_account__isnull=False)
        post_account_count = book_qs.count()
        log.debug(
            "Filtered journal entries to those linked to bank accounts: %d records remain (from %d)",
            post_account_count,
            pre_account_count,
        )
        
        # Convert querysets to DTOs
        candidate_bank: List[BankTransactionDTO] = [
            BankTransactionDTO(
                id=tx.id,
                company_id=tx.company_id,
                date=tx.date,
                amount=tx.amount,
                currency_id=tx.currency_id,
                description=tx.description,
                embedding=_as_vec_list(getattr(tx, "description_embedding", None)),
            )
            for tx in bank_qs
        ]
        
        log.debug("Created %d BankTransactionDTOs", len(candidate_bank))
        for dto in candidate_bank[:10]:
            log.debug(
                "BankDTO: id=%s, amount=%s, date=%s, currency_id=%s, company_id=%s",
                dto.id, dto.amount, dto.date, dto.currency_id, dto.company_id,
            )
        
        candidate_book: List[JournalEntryDTO] = []
        for je in book_qs:
            tr = getattr(je, "transaction", None)
            tr_date = je.date or (tr.date if tr else None)
            tr_curr_id = tr.currency_id if tr else None
            tr_desc = tr.description if tr else ""
            tr_vec = _as_vec_list(getattr(tr, "description_embedding", None)) if tr else None
        
            candidate_book.append(
                JournalEntryDTO(
                    id=je.id,
                    company_id=je.company_id,
                    transaction_id=je.transaction_id,
                    date=tr_date,
                    effective_amount=je.get_effective_amount(),
                    currency_id=tr_curr_id,
                    description=tr_desc,
                    embedding=tr_vec,
                )
            )
        
        log.debug("Created %d JournalEntryDTOs", len(candidate_book))
        for dto in candidate_book[:10]:
            log.debug(
                "BookDTO: id=%s, tx_id=%s, amount=%s, date=%s, currency_id=%s, company_id=%s",
                dto.id, dto.transaction_id, dto.effective_amount,
                dto.date, dto.currency_id, dto.company_id,
            )

        # Run the appropriate matching engine and capture soft limit
        soft_time_limit = None
        if pipeline_id:
            log.debug("match_many_to_many: using pipeline_id=%s", pipeline_id)
            pipe_obj = ReconciliationPipeline.objects.get(id=pipeline_id)
            suggestions = run_pipeline(
                pipe_obj,
                candidate_bank,
                candidate_book,
                on_suggestion=on_suggestion,  # <-- NOVO
            )
            soft_time_limit = getattr(pipe_obj, "soft_time_limit_seconds", None)
        else:
            log.debug("match_many_to_many: using config_id=%s", config_id)
            cfg_obj = ReconciliationConfig.objects.get(id=config_id)
            suggestions = run_single_config(
                cfg_obj,
                candidate_bank,
                candidate_book,
                company_id,
                on_suggestion=on_suggestion,  # <-- NOVO
            )
            soft_time_limit = getattr(cfg_obj, "soft_time_limit_seconds", None)

        # Auto-apply matches with confidence 1.0
        auto_info = {"enabled": bool(auto_match_100), "applied": 0, "skipped": 0, "details": []}
        if auto_match_100:
            auto_info = ReconciliationService._apply_auto_matches_100(suggestions)

        duration = monotonic() - start_ts

        # ---------------------- stats aggregation ----------------------
        suggestion_count = len(suggestions)
        bank_candidate_count = len(candidate_bank)
        book_candidate_count = len(candidate_book)

        matched_bank_ids: set[int] = set()
        matched_book_ids: set[int] = set()
        match_type_counts: Dict[str, int] = {}
        confidences: List[float] = []
        abs_diffs: List[float] = []

        for s in suggestions:
            mt = s.get("match_type", "unknown")
            match_type_counts[mt] = match_type_counts.get(mt, 0) + 1

            for bid in s.get("bank_ids", []):
                matched_bank_ids.add(bid)
            for jid in s.get("journal_entries_ids", []):
                matched_book_ids.add(jid)

            try:
                confidences.append(float(s.get("confidence_score", 0.0)))
            except Exception:
                pass
            try:
                abs_diffs.append(float(s.get("abs_amount_diff", 0.0)))
            except Exception:
                pass

        def _percentile(sorted_vals: List[float], p: float) -> Optional[float]:
            if not sorted_vals:
                return None
            k = (len(sorted_vals) - 1) * p
            f = int(k)
            c = min(f + 1, len(sorted_vals) - 1)
            if f == c:
                return sorted_vals[f]
            d0 = sorted_vals[f] * (c - k)
            d1 = sorted_vals[c] * (k - f)
            return d0 + d1

        conf_min = conf_max = conf_avg = conf_p50 = conf_p90 = None
        perfect_conf = 0
        if confidences:
            confidences_sorted = sorted(confidences)
            conf_min = confidences_sorted[0]
            conf_max = confidences_sorted[-1]
            conf_avg = sum(confidences_sorted) / len(confidences_sorted)
            conf_p50 = _percentile(confidences_sorted, 0.5)
            conf_p90 = _percentile(confidences_sorted, 0.9)
            perfect_conf = sum(1 for c in confidences_sorted if abs(c - 1.0) < 1e-9)

        diff_min = diff_max = diff_avg = None
        if abs_diffs:
            diffs_sorted = sorted(abs_diffs)
            diff_min = diffs_sorted[0]
            diff_max = diffs_sorted[-1]
            diff_avg = sum(diffs_sorted) / len(diffs_sorted)

        stats: Dict[str, object] = {
            "company_id": company_id,
            "config_id": config_id,
            "pipeline_id": pipeline_id,
            "duration_seconds": round(duration, 3),
            "time_limit_seconds": soft_time_limit,
            "time_limit_reached": bool(soft_time_limit and duration >= soft_time_limit),

            "bank_candidates": bank_candidate_count,
            "journal_candidates": book_candidate_count,

            "suggestion_count": suggestion_count,
            "match_types": match_type_counts,

            "matched_bank_transactions": len(matched_bank_ids),
            "matched_journal_entries": len(matched_book_ids),
            "bank_coverage_ratio": float(len(matched_bank_ids) / bank_candidate_count) if bank_candidate_count else 0.0,
            "journal_coverage_ratio": float(len(matched_book_ids) / book_candidate_count) if book_candidate_count else 0.0,

            "confidence_stats": {
                "min": conf_min,
                "max": conf_max,
                "avg": conf_avg,
                "p50": conf_p50,
                "p90": conf_p90,
                "perfect_1_0_count": perfect_conf,
            },

            "amount_diff_stats": {
                "min": diff_min,
                "max": diff_max,
                "avg": diff_avg,
            },

            "auto_match": {
                "enabled": auto_info["enabled"],
                "applied": auto_info["applied"],
                "skipped": auto_info["skipped"],
            },
        }

        log.info(
            "Recon task: company=%s config_id=%s pipeline_id=%s banks=%d books=%d suggestions=%d duration=%.3fs",
            company_id, config_id, pipeline_id,
            bank_candidate_count, book_candidate_count,
            suggestion_count, duration,
        )
        
        return {
            "suggestions": suggestions,
            "auto_match": auto_info,
            "stats": stats,
        }

    # ------------------------------------------------------------------
    # Auto-match persistence
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def _apply_auto_matches_100(
        suggestions: List[dict],
        status_value: str = "matched"
    ) -> Dict[str, object]:
        """
        Persist suggestions with confidence_score == 1.0 into Reconciliation records.
        Ensures no overlaps.  Returns counts and details.
        """
        applied = 0
        skipped = 0
        details = []
        used_banks: set[int] = set()
        used_books: set[int] = set()
        
        log.debug("Auto-match 100%% process starting for %d suggestions", len(suggestions))
        
        for s in suggestions:
            if float(s.get("confidence_score", 0)) != 1.0:
                continue
            bank_ids = s.get("bank_ids", [])
            book_ids = s.get("journal_entries_ids", [])
            if not bank_ids or not book_ids:
                skipped += 1
                details.append({"reason": "empty_ids", "suggestion": s})
                log.debug("Skipping auto-match suggestion (empty IDs): %s", s)
                continue
            if any(b in used_banks for b in bank_ids) or any(j in used_books for j in book_ids):
                skipped += 1
                details.append({"reason": "overlap_in_batch", "suggestion": s})
                log.debug("Skipping auto-match suggestion due to overlap in batch: %s", s)
                continue

            # Check for preexisting matches
            if BankTransaction.objects.filter(
                id__in=bank_ids, reconciliations__status__in=["matched", "approved"]
            ).exists() or JournalEntry.objects.filter(
                id__in=book_ids, reconciliations__status__in=["matched", "approved"]
            ).exists():
                skipped += 1
                details.append({"reason": "already_matched", "suggestion": s})
                log.debug("Skipping auto-match suggestion because already matched/approved in DB: %s", s)
                continue

            bank_objs = list(BankTransaction.objects.filter(id__in=bank_ids))
            book_objs = list(JournalEntry.objects.filter(id__in=book_ids))
            company_ids = {b.company_id for b in bank_objs} | {j.company_id for j in book_objs}
            if len(company_ids) != 1:
                skipped += 1
                details.append({"reason": "company_unresolved", "suggestion": s})
                log.debug("Skipping auto-match suggestion due to multiple company IDs: %s", s)
                continue
            company_id = company_ids.pop()

            recon = Reconciliation.objects.create(
                status=status_value,
                company_id=company_id,
                notes="auto_match_100",
            )
            recon.bank_transactions.add(*bank_objs)
            recon.journal_entries.add(*book_objs)
            applied += 1
            used_banks.update(bank_ids)
            used_books.update(book_ids)
            details.append({"reconciliation_id": recon.id, "bank_ids": bank_ids, "journal_ids": book_ids})
            log.debug("Auto-matched reconciliation created: id=%s (banks=%s, journals=%s)", recon.id, bank_ids, book_ids)
            
        log.debug("Auto-match 100%% results: %d applied, %d skipped", applied, skipped)
        for entry in details:
            if "reason" in entry:
                log.debug("Auto-match skipped detail: reason=%s, suggestion=%s", 
                          entry["reason"], entry.get("suggestion"))
            else:
                log.debug("Auto-match applied detail: reconciliation_id=%s, bank_ids=%s, journal_ids=%s", 
                          entry.get("reconciliation_id"), entry.get("bank_ids"), entry.get("journal_ids"))
            
        return {
            "enabled": True,
            "applied": applied,
            "skipped": skipped,
            "details": details,
        }