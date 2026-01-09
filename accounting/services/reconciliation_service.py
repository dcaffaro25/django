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
from typing import Callable, Dict, Iterable, List, Optional, Union
from multitenancy.utils import resolve_tenant
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
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


@dataclass(frozen=True)
class FastItem:
    """Pre-computed metadata for fast matching paths."""
    dto: Union[BankTransactionDTO, JournalEntryDTO]
    amount: Decimal
    amount_q2: Decimal
    sign: int


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
        If both are 0/disabled, use a sensible default of 30 days.
        """
        computed = max(int(self.group_span_days or 0), int(self.avg_date_delta_days or 0))
        # Default to 30 days if no explicit constraint is set
        return computed if computed > 0 else 30



@dataclass
class PipelineConfig:
    stages: list[StageConfig] = field(default_factory=list)
    auto_apply_score: float = 1.0
    max_suggestions: int = 10000
    max_runtime_seconds: float | None = None   # NEW
    fast: bool = False
    
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


def _build_fast_items(items: Iterable[Union[BankTransactionDTO, JournalEntryDTO]]) -> List[FastItem]:
    """Return immutable metadata for each candidate to avoid recomputation downstream."""
    fast_items: List[FastItem] = []
    for dto in items:
        amt = dto.amount_base or Decimal("0")
        fast_items.append(
            FastItem(
                dto=dto,
                amount=amt,
                amount_q2=q2(amt),
                sign=_sign(amt),
            )
        )
    return fast_items


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


def compute_feasibility_bounds(
    amounts: List[Decimal],
    target: Decimal,
    tol: Decimal,
    max_group_size: int,
) -> tuple[List[bool], Optional[int]]:
    """
    Compute feasibility bounds for group sizes to avoid enumerating impossible combinations.
    
    For each group size g, computes:
    - min_sum_g: sum of g smallest amounts
    - max_sum_g: sum of g largest amounts
    
    Returns:
    - feasible: list where feasible[g] is True if size g can reach target within tolerance
    - g_min: smallest feasible group size, or None if no size is feasible
    """
    n = len(amounts)
    if n == 0:
        return [], None
    
    max_g = min(max_group_size, n)
    
    # Sort for min/max prefix sums
    amounts_asc = sorted(amounts)  # ascending for min_sum
    amounts_desc = sorted(amounts, reverse=True)  # descending for max_sum
    
    min_sum = [Decimal("0")] * (max_g + 1)  # min_sum[g] = sum of g smallest
    max_sum = [Decimal("0")] * (max_g + 1)  # max_sum[g] = sum of g largest
    
    for g in range(1, max_g + 1):
        min_sum[g] = min_sum[g - 1] + amounts_asc[g - 1]
        max_sum[g] = max_sum[g - 1] + amounts_desc[g - 1]
    
    # Compute feasibility
    feasible = [False] * (max_g + 1)
    g_min = None
    L = target - tol
    U = target + tol
    
    for g in range(1, max_g + 1):
        # Feasible if [min_sum[g], max_sum[g]] intersects [L, U]
        if max_sum[g] >= L and min_sum[g] <= U:
            feasible[g] = True
            if g_min is None:
                g_min = g
    
    return feasible, g_min


def compute_match_scores(
    *,
    embed_sim: float,           # 0–1
    amount_diff: Decimal,       # absolute difference
    amount_tol: Decimal,        # tolerance (>= 0)
    date_diff: int,             # abs difference in days
    date_tol: int,              # tolerance (>= 0)
    currency_match: float,      # 0 or 1
    weights: Dict[str, float],  # embedding/amount/date/currency weights
    worst_metrics: Optional[Dict[str, float]] = None,  # Optional worst-case metrics for outlier detection
) -> Dict[str, float]:
    """
    Return per-dimension scores (0–1) and a weighted global score.
    
    If worst_metrics is provided, applies penalties for outlier entries within groups.
    """
    # defensive guards for zero tolerances
    amt_norm = float(amount_diff / (amount_tol or CENT))
    amt_score = max(0.0, 1.0 - amt_norm)

    date_norm = float(date_diff) / float(date_tol or 1)
    date_score = max(0.0, 1.0 - date_norm)

    desc_score = max(0.0, min(1.0, float(embed_sim)))  # ensure 0–1
    curr_score = max(0.0, min(1.0, float(currency_match)))

    # Apply outlier penalties if worst_metrics provided
    outlier_penalty = 0.0
    if worst_metrics:
        # Penalty for large max_date_delta_ratio (outlier date)
        if worst_metrics.get("max_date_delta_ratio", 1.0) > 2.0:
            ratio_penalty = min(0.15, (worst_metrics["max_date_delta_ratio"] - 2.0) * 0.05)
            outlier_penalty += ratio_penalty
        
        # Penalty for very low min_embedding_sim (poor description match)
        min_sim = worst_metrics.get("min_embedding_sim", 1.0)
        if min_sim < 0.5:
            sim_penalty = (0.5 - min_sim) * 0.2  # Up to 0.1 penalty
            outlier_penalty += sim_penalty
        
        # Penalty for very large max_date_delta (absolute outlier)
        max_delta = worst_metrics.get("max_date_delta", 0)
        if max_delta > (date_tol or 1) * 2:
            delta_penalty = min(0.1, (max_delta - (date_tol or 1) * 2) / 100.0)
            outlier_penalty += delta_penalty

    w_emb = float(weights.get("embedding", 0.0))
    w_amt = float(weights.get("amount", 0.0))
    w_date = float(weights.get("date", 0.0))
    w_curr = float(weights.get("currency", 0.0))

    global_score = round(
        w_emb * desc_score +
        w_amt * amt_score +
        w_date * date_score +
        w_curr * curr_score -
        outlier_penalty,  # Subtract penalty from global score
        4,
    )
    
    # Ensure global_score doesn't go below 0
    global_score = max(0.0, global_score)

    return {
        "description_score": desc_score,
        "amount_score": amt_score,
        "date_score": date_score,
        "currency_score": curr_score,
        "global_score": global_score,
        "outlier_penalty": outlier_penalty,
    }

def compute_weighted_confidence(
    embed_sim: float,
    amount_diff: Decimal,
    amount_tol: Decimal,
    date_diff: int,
    date_tol: int,
    currency_match: float,
    weights: Dict[str, float],
    worst_metrics: Optional[Dict[str, float]] = None,
) -> float:
    scores = compute_match_scores(
        embed_sim=embed_sim,
        amount_diff=amount_diff,
        amount_tol=amount_tol,
        date_diff=date_diff,
        date_tol=date_tol,
        currency_match=currency_match,
        weights=weights,
        worst_metrics=worst_metrics,
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


def _compute_worst_match_metrics(
    bank_item: Union[BankTransactionDTO, List[BankTransactionDTO]],
    book_items: List[JournalEntryDTO],
) -> Dict[str, float]:
    """
    Compute worst-case match metrics within a group to detect outliers.
    
    Returns:
        - max_date_delta: Maximum date difference of any single book entry from bank date
        - min_embedding_sim: Minimum embedding similarity of any single book entry
        - max_date_delta_ratio: Ratio of max_date_delta to group average date delta
    """
    from math import sqrt
    
    if isinstance(bank_item, list):
        bank_date = None
        bank_embedding = None
        if bank_item:
            # For many-to-one: use weighted average of bank dates
            dates = [b.date for b in bank_item if b.date]
            amounts = [abs(b.amount_base or Decimal("0")) for b in bank_item]
            if dates and amounts:
                total_abs = sum(amounts, Decimal("0"))
                if total_abs:
                    num = sum((Decimal(d.toordinal()) * w for d, w in zip(dates, amounts)), Decimal("0"))
                    ord_ = int((num / total_abs).to_integral_value(ROUND_HALF_UP))
                    bank_date = _date.fromordinal(ord_)
            # Average embedding for bank group
            bank_embedding = _avg_embedding(bank_item)
    else:
        bank_date = bank_item.date
        bank_embedding = bank_item.embedding or []
    
    if not bank_date or not book_items:
        return {
            "max_date_delta": 9999,
            "min_embedding_sim": 0.0,
            "max_date_delta_ratio": 1.0,
        }
    
    max_date_delta = 0
    min_embedding_sim = 1.0
    date_deltas = []
    
    for book in book_items:
        if book.date:
            delta = abs((bank_date - book.date).days)
            date_deltas.append(delta)
            max_date_delta = max(max_date_delta, delta)
        
        if bank_embedding and book.embedding:
            # Compute cosine similarity
            dot = sum(a * b for a, b in zip(bank_embedding, book.embedding))
            norm_bank = sqrt(sum(a * a for a in bank_embedding))
            norm_book = sqrt(sum(b * b for b in book.embedding))
            if norm_bank and norm_book:
                sim = dot / (norm_bank * norm_book)
                min_embedding_sim = min(min_embedding_sim, sim)
    
    # Compute average date delta for ratio calculation
    avg_date_delta = sum(date_deltas) / len(date_deltas) if date_deltas else max_date_delta
    max_date_delta_ratio = max_date_delta / avg_date_delta if avg_date_delta > 0 else 1.0
    
    return {
        "max_date_delta": float(max_date_delta),
        "min_embedding_sim": float(min_embedding_sim),
        "max_date_delta_ratio": float(max_date_delta_ratio),
    }


def _check_intra_group_coherence(
    bank_item: Union[BankTransactionDTO, List[BankTransactionDTO]],
    book_items: List[JournalEntryDTO],
    stage: StageConfig,
    worst_metrics: Optional[Dict[str, float]] = None,
    strict: bool = False,
) -> tuple[bool, Optional[str]]:
    """
    Check if all entries in a group are coherent (no obvious outliers).
    
    This check is intentionally very lenient in non-strict mode - we rely more on 
    scoring penalties for outliers, and only reject truly extreme cases.
    
    Args:
        bank_item: Single bank transaction or list of bank transactions
        book_items: List of journal entries to check coherence for
        stage: Stage configuration with date tolerances
        worst_metrics: Pre-computed worst-case metrics (optional)
        strict: If False (default), only reject extreme outliers. If True, use tighter thresholds.
    
    Returns:
        (is_coherent, rejection_reason)
    """
    if len(book_items) <= 1:
        return (True, None)  # Single entry groups are always coherent
    
    # Compute worst metrics if not provided
    if worst_metrics is None:
        worst_metrics = _compute_worst_match_metrics(bank_item, book_items)
    
    # Check 1: Maximum date delta should not exceed group_span_days
    # If group_span_days is set, enforce it (this is already a user-configured constraint)
    if stage.group_span_days and stage.group_span_days > 0:
        book_dates = [b.date for b in book_items if b.date]
        if len(book_dates) >= 2:
            book_span = (max(book_dates) - min(book_dates)).days
            if book_span > stage.group_span_days:
                return (False, f"book_span_days={book_span} > group_span_days={stage.group_span_days}")
    
    # Check 2: Extreme date outliers only
    # In strict mode: 5x threshold, in lenient mode: 20x threshold (almost never rejects)
    ratio_threshold = 5.0 if strict else 20.0
    if worst_metrics["max_date_delta_ratio"] > ratio_threshold:
        return (False, f"max_date_delta_ratio={worst_metrics['max_date_delta_ratio']:.2f} > {ratio_threshold} (extreme outlier)")
    
    # NOTE: We intentionally do NOT reject based on embedding similarity here.
    # Many valid matches have low embedding similarity due to generic bank descriptions.
    # The scoring function already applies penalties for low similarity.
    
    # Check 3: Extreme date distance only (strict: 3x, lenient: 10x threshold)
    # Only reject if a single entry is extremely far from the bank date
    date_multiplier = 3.0 if strict else 10.0
    if not isinstance(bank_item, list) and stage.avg_date_delta_days and stage.avg_date_delta_days > 0:
        if worst_metrics["max_date_delta"] > stage.avg_date_delta_days * date_multiplier:
            return (False, f"max_date_delta={worst_metrics['max_date_delta']} > {date_multiplier}x avg_date_delta_days={stage.avg_date_delta_days}")
    
    return (True, None)


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

        # Thread-safe locks for parallel processing
        self._lock = threading.Lock()
        self._used_banks_lock = threading.Lock()
        self._used_books_lock = threading.Lock()

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
        
        # NEW: whether to use _fast stage handlers when available
        self.fast: bool = bool(getattr(config, "fast", False))
        
        # Thread pool size for parallel processing (default to 8, can be overridden)
        self._thread_pool_size = getattr(config, "thread_pool_size", 8)
        
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
        candidates: List[tuple[List[int], float]] = []  # (indices, score)
        
        def dfs(idx: int, chosen: List[int], current_sum: Decimal):
            nonlocal candidates
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
                
                # Check intra-group coherence before scoring
                worst_metrics = _compute_worst_match_metrics(bank, combo)
                is_coherent, reject_reason = _check_intra_group_coherence(
                    bank, combo, stage, worst_metrics
                )
                if not is_coherent:
                    return  # Skip this candidate
                
                # Calculate score for this candidate
                amount_diff = abs(q2(current_sum) - target)
                embed_sim = self._cosine_similarity(bank.embedding or [], _avg_embedding(combo))
                scores = compute_match_scores(
                    embed_sim=embed_sim,
                    amount_diff=amount_diff,
                    amount_tol=stage.amount_tol or CENT,
                    date_diff=avg_delta,
                    date_tol=stage.avg_date_delta_days or 1,
                    currency_match=1.0,
                    weights=self.stage_weights,
                    worst_metrics=worst_metrics,
                )
                score = scores["global_score"]
                candidates.append((chosen.copy(), score))
                return
    
            # branch-and-bound: reachable range
            possible_min = current_sum + rem_min[idx]
            possible_max = current_sum + rem_max[idx]
            if possible_max < lower or possible_min > upper:
                return
    
            # skip
            dfs(idx + 1, chosen, current_sum)
            # take
            dfs(idx + 1, chosen + [idx], current_sum + amounts[idx])
        
        dfs(0, [], Decimal("0"))
        
        if not candidates:
            return None
        
        # Return the best candidate by score (highest confidence)
        candidates.sort(key=lambda x: -x[1])  # Sort by score descending
        best_indices = candidates[0][0]
        return [local_books[i] for i in best_indices]
    
        
    def run(self, banks: list[BankTransactionDTO], books: list[JournalEntryDTO]) -> list[dict]:
        log.info(
            "=== PipelineEngine.run START === company_id=%s stages=%d banks=%d books=%d "
            "max_suggestions=%d max_runtime=%s fast=%s",
            self.company_id,
            len(self.config.stages),
            len(banks),
            len(books),
            self.config.max_suggestions,
            self.max_runtime_seconds,
            self.fast,
        )

        for idx, stage in enumerate(self.config.stages):
            log.info(
                ">>> Processing stage %d/%d: type=%s enabled=%s",
                idx + 1, len(self.config.stages), stage.type, stage.enabled,
            )
            
            if not stage.enabled:
                log.info("Stage %d (%s) skipped: enabled=False", idx, stage.type)
                continue
            
            if self._time_exceeded():
                log.warning(
                    "Time limit reached before stage %d (%s); stopping pipeline. "
                    "Elapsed: %.2fs / %.2fs",
                    idx, stage.type,
                    monotonic() - self._start_ts,
                    self.max_runtime_seconds or 0,
                )
                break
            
            self.stage_weights = (
                self.current_weights[idx]
                if isinstance(self.current_weights, list)
                else self.current_weights
            )
            
            base_name = f"_run_{stage.type}"
            handler = None
            
            if self.fast:
                fast_name = f"{base_name}_fast"
                handler = getattr(self, fast_name, None)
                if handler:
                    log.info(
                        "========== [FAST ENGINE] Using handler %s for stage %d (%s) ==========",
                        fast_name, idx, stage.type,
                    )
            if handler is None:
                handler = getattr(self, base_name, None)
                log.info(
                    "========== [REGULAR ENGINE] Using handler %s for stage %d (%s) ==========",
                    base_name, idx, stage.type,
                )

            win = stage.candidate_window_days

            log.info(
                "Stage %d (%s) parameters: weights=%s amount_tol=%s group_span_days=%d "
                "avg_date_delta_days=%d candidate_window_days=%d "
                "max_grp_bank=%d max_grp_book=%d banks=%d books=%d allow_mixed_signs=%s "
                "max_alternatives=%d",
                idx, stage.type, self.stage_weights, stage.amount_tol,
                stage.group_span_days, stage.avg_date_delta_days, win,
                stage.max_group_size_bank, stage.max_group_size_book,
                len(banks), len(books), stage.allow_mixed_signs,
                stage.max_alternatives_per_anchor,
            )
            
            suggestions_before = len(self.suggestions)
            used_banks_before = len(self.used_banks)
            used_books_before = len(self.used_books)
    
            if handler:
                log.info("Executing stage handler for %s", stage.type)
                stage_start = monotonic()
                handler(banks, books, stage)
                stage_duration = monotonic() - stage_start
                
                suggestions_after = len(self.suggestions)
                used_banks_after = len(self.used_banks)
                used_books_after = len(self.used_books)
                
                log.info(
                    "Stage %d (%s) completed in %.3fs: new_suggestions=%d (+%d) "
                    "used_banks=%d (+%d) used_books=%d (+%d) total_suggestions=%d",
                    idx, stage.type, stage_duration,
                    suggestions_after, suggestions_after - suggestions_before,
                    used_banks_after, used_banks_after - used_banks_before,
                    used_books_after, used_books_after - used_books_before,
                    suggestions_after,
                )
                
                if self._time_exceeded():
                    log.warning(
                        "Time limit reached after stage %d (%s); stopping pipeline. "
                        "Elapsed: %.2fs / %.2fs",
                        idx, stage.type,
                        monotonic() - self._start_ts,
                        self.max_runtime_seconds or 0,
                    )
                    break
                
                if len(self.suggestions) >= self.config.max_suggestions:
                    log.warning(
                        "Reached max_suggestions=%d at stage %d (%s); stopping.",
                        self.config.max_suggestions, idx, stage.type,
                    )
                    break
            else:
                log.warning(
                    "No handler found for stage type '%s' (checked: %s, %s_fast)",
                    stage.type, base_name, base_name,
                )
                
        total_duration = monotonic() - self._start_ts
        log.info(
            "=== PipelineEngine.run FINISHED === duration=%.3fs suggestions=%d "
            "used_banks=%d used_books=%d remaining_banks=%d remaining_books=%d",
            total_duration,
            len(self.suggestions),
            len(self.used_banks),
            len(self.used_books),
            len(banks) - len(self.used_banks),
            len(books) - len(self.used_books),
        )
        return self.suggestions[: self.config.max_suggestions]

    # ------------------------ Stage handlers ------------------------

    def _run_exact_1to1(self, banks, books, stage: StageConfig):
        log.info("_run_exact_1to1: starting with banks=%d books=%d", len(banks), len(books))
        tol = int(stage.avg_date_delta_days or 0)
        # Deterministic sorting for stable results
        banks_sorted = sorted(banks, key=lambda b: (b.date or date.min, b.id))
        books_sorted = sorted(books, key=lambda b: (b.date or date.min, b.id))
        
        matches_attempted = 0
        matches_tested = 0
        matches_found = 0
        
        for bank in banks_sorted:
            if self._time_exceeded():
                log.debug("_run_exact_1to1: time exceeded, stopping")
                return
            
            # Check inside lock for thread safety
            with self._used_banks_lock:
                if bank.id in self.used_banks:
                    continue
            
            matches_attempted += 1
            log.debug(
                "exact_1to1: testing bank_id=%d amount=%s date=%s currency_id=%d company_id=%d",
                bank.id, bank.amount_base, bank.date, bank.currency_id, bank.company_id,
            )
            
            for book in books_sorted:
                # Check inside lock for thread safety
                with self._used_books_lock:
                    if book.id in self.used_books:
                        continue
                
                matches_tested += 1
                log.debug(
                    "exact_1to1: testing pair bank_id=%d vs book_id=%d "
                    "(bank_amount=%s book_amount=%s bank_date=%s book_date=%s)",
                    bank.id, book.id,
                    bank.amount_base, book.amount_base,
                    bank.date, book.date,
                )
                
                if bank.company_id != book.company_id:
                    log.debug(
                        "exact_1to1: REJECTED bank_id=%d book_id=%d - company mismatch "
                        "(bank_company=%d book_company=%d)",
                        bank.id, book.id, bank.company_id, book.company_id,
                    )
                    continue
                if q2(bank.amount_base) != q2(book.amount_base):
                    log.debug(
                        "exact_1to1: REJECTED bank_id=%d book_id=%d - amount mismatch "
                        "(bank_amount=%s book_amount=%s)",
                        bank.id, book.id, bank.amount_base, book.amount_base,
                    )
                    continue
                if bank.currency_id != book.currency_id:
                    log.debug(
                        "exact_1to1: REJECTED bank_id=%d book_id=%d - currency mismatch "
                        "(bank_currency=%d book_currency=%d)",
                        bank.id, book.id, bank.currency_id, book.currency_id,
                    )
                    continue
                # Cross-side constraint: |bank.date - book.date| <= avg_date_delta_days
                if bank.date and book.date:
                    date_diff = abs((bank.date - book.date).days)
                    if date_diff > tol:
                        log.debug(
                            "exact_1to1: REJECTED bank_id=%d book_id=%d - date delta too large "
                            "(delta=%d tol=%d)",
                            bank.id, book.id, date_diff, tol,
                        )
                        continue
                    log.debug(
                        "exact_1to1: date check PASSED bank_id=%d book_id=%d (delta=%d tol=%d)",
                        bank.id, book.id, date_diff, tol,
                    )
                
                log.info(
                    "exact_1to1: MATCH FOUND bank_id=%d book_id=%d "
                    "(amount=%s currency=%d date_diff=%d)",
                    bank.id, book.id,
                    bank.amount_base,
                    bank.currency_id,
                    abs((bank.date - book.date).days) if (bank.date and book.date) else 0,
                )
                matches_found += 1
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
        
        log.info(
            "_run_exact_1to1: completed - matches_attempted=%d matches_tested=%d matches_found=%d",
            matches_attempted, matches_tested, matches_found,
        )

    
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

        Returns the BEST valid combination of banks by confidence score, or None.
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
        candidates: List[tuple[List[int], float]] = []  # (indices, score)

        def dfs(idx: int, chosen: List[int], current_sum: Decimal):
            nonlocal candidates

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

                # Check intra-group coherence before scoring
                worst_metrics = _compute_worst_match_metrics(combo, [book])
                is_coherent, reject_reason = _check_intra_group_coherence(
                    combo, [book], stage, worst_metrics
                )
                if not is_coherent:
                    return  # Skip this candidate

                # Calculate score for this candidate
                amount_diff = abs(q2(current_sum) - target)
                embed_sim = self._cosine_similarity(_avg_embedding(combo), book.embedding or [])
                scores = compute_match_scores(
                    embed_sim=embed_sim,
                    amount_diff=amount_diff,
                    amount_tol=stage.amount_tol or CENT,
                    date_diff=avg_delta,
                    date_tol=stage.avg_date_delta_days or 1,
                    currency_match=1.0,
                    weights=self.stage_weights,
                    worst_metrics=worst_metrics,
                )
                score = scores["global_score"]
                candidates.append((chosen.copy(), score))
                return

            # Branch-and-bound: check reachable range
            possible_min = current_sum + rem_min[idx]
            possible_max = current_sum + rem_max[idx]
            if possible_max < lower or possible_min > upper:
                return

            # Option 1: skip this item
            dfs(idx + 1, chosen, current_sum)
            # Option 2: take this item
            dfs(idx + 1, chosen + [idx], current_sum + amounts[idx])

        dfs(0, [], Decimal("0"))

        if not candidates:
            return None

        # Return the best candidate by score (highest confidence)
        candidates.sort(key=lambda x: -x[1])  # Sort by score descending
        best_indices = candidates[0][0]
        return [local_banks[i] for i in best_indices]

    def _run_one_to_many(self, banks, books, stage: StageConfig):
        """
        One bank to many books.

        Phase 1: Collect all candidate suggestions from all banks.
        Phase 2: Run global non-overlapping selection to maximize total match quality.
        
        For each bank we generate up to `stage.max_alternatives_per_anchor` best
        book-combos ranked by global match score. Then we select a non-overlapping
        set globally to avoid greedy per-anchor selection issues.
        """
        log.info(
            "[REGULAR] _run_one_to_many: START - total_banks=%d total_books=%d "
            "used_banks=%d used_books=%d",
            len(banks), len(books), len(self.used_banks), len(self.used_books),
        )
        
        available_books = [
            b for b in books
            if b.id not in self.used_books and b.company_id == self.company_id
        ]
        win = stage.candidate_window_days
        max_k = max(int(stage.max_alternatives_per_anchor or 1), 1)

        log.info(
            "[REGULAR] _run_one_to_many: filtered available_books=%d (from %d total) "
            "win=%d amount_tol=%s allow_mixed=%s max_k=%d",
            len(available_books), len(books), win, stage.amount_tol, 
            stage.allow_mixed_signs, max_k,
        )

        # Phase 1: Collect all candidates from all banks
        all_candidates: List[dict] = []

        def add_candidate(sug: dict, buf: list[dict]) -> None:
            """Add candidate with deterministic tie-breaking for stable ordering."""
            def sort_key(s):
                """Deterministic sort key for suggestions."""
                return (
                    -float(s.get("confidence_score", 0.0)),  # Higher is better
                    s.get("extra", {}).get("avg_date_delta_days_measured", 9999),  # Lower is better
                    s.get("abs_amount_diff", 999999.0),  # Lower is better
                    tuple(sorted(s.get("bank_ids", []))),  # Deterministic
                    tuple(sorted(s.get("journal_entries_ids", []))),  # Deterministic
                )
            
            score_key = sort_key(sug)
            if len(buf) < max_k:
                buf.append(sug)
                return
            worst_idx = min(range(len(buf)), key=lambda i: sort_key(buf[i]))
            worst_key = sort_key(buf[worst_idx])
            if score_key < worst_key:  # Tuple comparison: better candidate
                buf[worst_idx] = sug

        banks_processed = 0
        banks_with_candidates = 0
        total_candidates_generated = 0
        
        for bank in banks:
            if self._time_exceeded():
                log.warning("[REGULAR] _run_one_to_many: time exceeded, stopping bank processing")
                return
            if bank.id in self.used_banks:
                log.debug("[REGULAR] _run_one_to_many: bank_id=%d already used, skipping", bank.id)
                continue

            banks_processed += 1
            bank_amt = bank.amount_base or Decimal("0")
            bank_sign = _sign(bank_amt)

            log.debug(
                "[REGULAR] _run_one_to_many: processing bank_id=%d amount=%s sign=%d date=%s currency_id=%d",
                bank.id, bank_amt, bank_sign, bank.date, bank.currency_id,
            )

            # date window
            local_books = [
                b for b in available_books
                if b.date and bank.date and abs((bank.date - b.date).days) <= win
            ]
            log.debug(
                "[REGULAR] _run_one_to_many: bank_id=%d date_window filter: %d books in window (win=%d days)",
                bank.id, len(local_books), win,
            )
            if not local_books:
                log.debug("[REGULAR] _run_one_to_many: bank_id=%d no books in date window, skipping", bank.id)
                continue
            
            # Deterministic sorting: sort by (amount, id) for stable combination generation
            local_books.sort(key=lambda b: (b.amount_base or Decimal("0"), b.id))

            # sign filtering if mixed_signs is False
            if not stage.allow_mixed_signs and bank_sign != 0:
                before_sign_filter = len(local_books)
                if bank_sign > 0:
                    local_books = [b for b in local_books if (b.amount_base or Decimal("0")) >= 0]
                else:
                    local_books = [b for b in local_books if (b.amount_base or Decimal("0")) <= 0]
                log.debug(
                    "[REGULAR] _run_one_to_many: bank_id=%d sign filter: %d -> %d books (allow_mixed=%s bank_sign=%d)",
                    bank.id, before_sign_filter, len(local_books), 
                    stage.allow_mixed_signs, bank_sign,
                )
                if not local_books:
                    log.debug("[REGULAR] _run_one_to_many: bank_id=%d no books after sign filter, skipping", bank.id)
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
                    # Check intra-group coherence before scoring
                    worst_metrics = _compute_worst_match_metrics(bank, list(combo))
                    is_coherent, reject_reason = _check_intra_group_coherence(
                        bank, list(combo), stage, worst_metrics
                    )
                    if not is_coherent:
                        log.debug(
                            "[REGULAR] _run_one_to_many: bank_id=%d mixed-sign combo REJECTED - coherence check failed: %s "
                            "(book_ids=%s)",
                            bank.id, reject_reason, [b.id for b in combo],
                        )
                        combo = None  # Reject this combo
                    
                    if combo:  # Only proceed if coherence check passed
                        book_dates = [b.date for b in combo if b.date]
                        book_span = (max(book_dates) - min(book_dates)).days if len(book_dates) >= 2 else 0
                        bank_avg = bank.date
                        book_avg = self._weighted_avg_date(combo)
                        avg_delta = abs((bank_avg - book_avg).days) if (bank_avg and book_avg) else win + 1

                        # Calculate actual amount difference
                        bank_total = bank.amount_base or Decimal("0")
                        book_total = sum((b.amount_base for b in combo), Decimal("0"))
                        amount_diff = abs(q2(bank_total) - q2(book_total))

                        sim = self._cosine_similarity(bank.embedding or [], _avg_embedding(combo))
                        scores = compute_match_scores(
                            embed_sim=sim,
                            amount_diff=amount_diff,
                            amount_tol=stage.amount_tol or CENT,
                            date_diff=avg_delta,
                            date_tol=stage.avg_date_delta_days or 1,
                            currency_match=1.0,
                            weights=self.stage_weights,
                            worst_metrics=worst_metrics,
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
                    candidates.sort(key=self._deterministic_sort_key)
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

            # Feasibility pruning: compute g_min to skip infeasible sizes
            log.debug(
                "[REGULAR] _run_one_to_many: bank_id=%d computing feasibility bounds "
                "(target=%s tol=%s max_size=%d num_books=%d)",
                bank.id, target, tol, max_size, len(book_amounts),
            )
            feasible, g_min = compute_feasibility_bounds(book_amounts, target, tol, max_size)
            
            log.debug(
                "[REGULAR] _run_one_to_many: bank_id=%d feasibility result: g_min=%s feasible_sizes=%s",
                bank.id, g_min, [i for i, f in enumerate(feasible) if f] if feasible else [],
            )
            
            if g_min is None:
                # No feasible size exists - skip this bank entirely
                log.debug(
                    "[REGULAR] _run_one_to_many: bank_id=%d no feasible group size (g_min=None) "
                    "target=%s tol=%s book_amounts_range=[%s, %s]",
                    bank.id, target, tol,
                    min(book_amounts) if book_amounts else None,
                    max(book_amounts) if book_amounts else None,
                )
                if candidates:
                    log.debug(
                        "[REGULAR] _run_one_to_many: bank_id=%d adding %d candidates from mixed-sign path before skip",
                        bank.id, len(candidates),
                    )
                    all_candidates.extend(candidates)
                continue
            
            banks_with_candidates += 1
            log.debug(
                "[REGULAR] _run_one_to_many: bank_id=%d starting enumeration from g_min=%d to max_size=%d",
                bank.id, g_min, max_size,
            )
            
            # All-in shortcut: if only full group is feasible and it matches exactly
            if g_min == len(local_books):
                all_sum = sum(book_amounts)
                all_diff = abs(q2(all_sum) - target)
                if all_diff <= tol:
                    # Check date constraints for full group
                    book_dates = [b.date for b in local_books if b.date]
                    book_span = (max(book_dates) - min(book_dates)).days if len(book_dates) >= 2 else 0
                    if (not stage.group_span_days or book_span <= stage.group_span_days):
                        bank_avg = bank.date
                        book_avg = self._weighted_avg_date(local_books)
                        avg_delta = abs((bank_avg - book_avg).days) if (bank_avg and book_avg) else win + 1
                        if (not stage.avg_date_delta_days or avg_delta <= stage.avg_date_delta_days):
                            # Check intra-group coherence before accepting
                            worst_metrics = _compute_worst_match_metrics(bank, local_books)
                            is_coherent, reject_reason = _check_intra_group_coherence(
                                bank, local_books, stage, worst_metrics
                            )
                            if not is_coherent:
                                log.debug(
                                    "[REGULAR] _run_one_to_many: bank_id=%d all-in combo REJECTED - coherence check failed: %s",
                                    bank.id, reject_reason,
                                )
                                continue
                            
                            # All-in is valid - score and add
                            sim = self._cosine_similarity(bank.embedding or [], _avg_embedding(local_books))
                            scores = compute_match_scores(
                                embed_sim=sim,
                                amount_diff=all_diff,
                                amount_tol=stage.amount_tol or CENT,
                                date_diff=avg_delta,
                                date_tol=stage.avg_date_delta_days or 1,
                                currency_match=1.0,
                                weights=self.stage_weights,
                                worst_metrics=worst_metrics,
                            )
                            sug = self._make_suggestion(
                                "one_to_many",
                                [bank],
                                local_books,
                                scores["global_score"],
                                stage=stage,
                                weights=self.stage_weights,
                                component_scores=scores,
                                extra={
                                    "book_span_days_measured": book_span,
                                    "avg_date_delta_days_measured": avg_delta,
                                    "mixed_signs": False,
                                    "all_in_shortcut": True,
                                    "g_min": g_min,
                                },
                            )
                            add_candidate(sug, candidates)
                            if candidates:
                                all_candidates.extend(candidates)
                            continue  # Skip enumeration

            prefix_max: List[Decimal] = []
            if use_prefix_bounds:
                amounts_desc = sorted(book_amounts, reverse=True)
                acc = Decimal("0")
                for amt in amounts_desc:
                    acc += amt
                    prefix_max.append(acc)
                if q2(prefix_max[-1]) + tol < target:
                    if candidates:
                        all_candidates.extend(candidates)
                    continue

            # Start enumeration at g_min, not 1
            combos_tested = 0
            for size in range(g_min, max_size + 1):
                if not feasible[size]:
                    log.debug(
                        "[REGULAR] _run_one_to_many: bank_id=%d skipping size=%d (not feasible)",
                        bank.id, size,
                    )
                    continue  # Skip infeasible sizes
                if self._time_exceeded():
                    return

                if use_prefix_bounds and q2(prefix_max[size - 1]) + tol < target:
                    log.debug(
                        "[REGULAR] _run_one_to_many: bank_id=%d size=%d prefix bound check failed "
                        "(prefix_max=%s + tol=%s < target=%s)",
                        bank.id, size, prefix_max[size - 1], tol, target,
                    )
                    continue

                combos_at_size = 0
                for combo in combinations(local_books, size):
                    combos_tested += 1
                    combos_at_size += 1
                    
                    # Check inside lock for thread safety
                    with self._used_books_lock:
                        used_book_ids = [x.id for x in combo if x.id in self.used_books]
                        if used_book_ids:
                            log.debug(
                                "[REGULAR] _run_one_to_many: bank_id=%d combo size=%d rejected - "
                                "books already used: %s",
                                bank.id, size, used_book_ids,
                            )
                            continue

                    total = sum((b.amount_base for b in combo), Decimal("0"))
                    diff = abs(q2(total) - target)
                    
                    log.debug(
                        "[REGULAR] _run_one_to_many: bank_id=%d testing combo size=%d "
                        "(book_ids=%s total=%s diff=%s target=%s)",
                        bank.id, size,
                        [b.id for b in combo], total, diff, target,
                    )
                    
                    if diff > stage.amount_tol:
                        log.debug(
                            "[REGULAR] _run_one_to_many: bank_id=%d combo REJECTED - amount diff too large "
                            "(diff=%s > tol=%s)",
                            bank.id, diff, stage.amount_tol,
                        )
                        continue
                        
                    if any(b.currency_id != bank.currency_id for b in combo):
                        invalid_currencies = {
                            b.id: b.currency_id for b in combo 
                            if b.currency_id != bank.currency_id
                        }
                        log.debug(
                            "[REGULAR] _run_one_to_many: bank_id=%d combo REJECTED - currency mismatch "
                            "(bank_currency=%d invalid_book_currencies=%s)",
                            bank.id, bank.currency_id, invalid_currencies,
                        )
                        continue

                    book_dates = [b.date for b in combo if b.date]
                    book_span = (max(book_dates) - min(book_dates)).days if len(book_dates) >= 2 else 0
                    if stage.group_span_days and book_span > stage.group_span_days:
                        log.debug(
                            "[REGULAR] _run_one_to_many: bank_id=%d combo REJECTED - book span too large "
                            "(span=%d > max=%d)",
                            bank.id, book_span, stage.group_span_days,
                        )
                        continue

                    bank_avg = bank.date
                    book_avg = self._weighted_avg_date(combo)
                    avg_delta = abs((bank_avg - book_avg).days) if (bank_avg and book_avg) else win + 1
                    if stage.avg_date_delta_days and avg_delta > stage.avg_date_delta_days:
                        log.debug(
                            "[REGULAR] _run_one_to_many: bank_id=%d combo REJECTED - avg date delta too large "
                            "(delta=%d > max=%d)",
                            bank.id, avg_delta, stage.avg_date_delta_days,
                        )
                        continue

                    # Check intra-group coherence before scoring
                    worst_metrics = _compute_worst_match_metrics(bank, list(combo))
                    is_coherent, reject_reason = _check_intra_group_coherence(
                        bank, list(combo), stage, worst_metrics
                    )
                    if not is_coherent:
                        log.debug(
                            "[REGULAR] _run_one_to_many: bank_id=%d combo REJECTED - coherence check failed: %s "
                            "(book_ids=%s)",
                            bank.id, reject_reason, [b.id for b in combo],
                        )
                        continue

                    # Use the already-calculated diff as amount_diff
                    sim = self._cosine_similarity(bank.embedding or [], _avg_embedding(combo))
                    scores = compute_match_scores(
                        embed_sim=sim,
                        amount_diff=diff,
                        amount_tol=stage.amount_tol or CENT,
                        date_diff=avg_delta,
                        date_tol=stage.avg_date_delta_days or 1,
                        currency_match=1.0,
                        weights=self.stage_weights,
                        worst_metrics=worst_metrics,
                    )
                    
                    log.info(
                        "[REGULAR] _run_one_to_many: bank_id=%d VALID COMBO FOUND size=%d "
                        "(book_ids=%s score=%.4f amount_diff=%s date_delta=%d embed_sim=%.4f)",
                        bank.id, size, [b.id for b in combo],
                        scores["global_score"], diff, avg_delta, sim,
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
                    total_candidates_generated += 1
                
                log.debug(
                    "[REGULAR] _run_one_to_many: bank_id=%d size=%d completed: tested=%d combos candidates=%d",
                    bank.id, size, combos_at_size, len(candidates),
                )
            
            log.debug(
                "[REGULAR] _run_one_to_many: bank_id=%d enumeration complete: tested=%d combos candidates=%d",
                bank.id, combos_tested, len(candidates),
            )

            # Add all candidates from this bank to global collection
            if candidates:
                log.debug(
                    "[REGULAR] _run_one_to_many: bank_id=%d adding %d candidates to global pool",
                    bank.id, len(candidates),
                )
                all_candidates.extend(candidates)
        
        log.info(
            "[REGULAR] _run_one_to_many: Phase 1 complete - banks_processed=%d banks_with_candidates=%d "
            "total_candidates=%d",
            banks_processed, banks_with_candidates, len(all_candidates),
        )
        
        # Phase 2: Global selection - pick non-overlapping set
        if all_candidates:
            log.info(
                "[REGULAR] _run_one_to_many: Phase 2 starting - selecting non-overlapping set from %d candidates",
                len(all_candidates),
            )
            selected = self._global_select_non_overlapping(all_candidates)
            
            log.info(
                "[REGULAR] _run_one_to_many: Phase 2 complete - selected %d non-overlapping suggestions",
                len(selected),
            )
            
            # Record selected suggestions (these mark IDs as used) with rank=1, is_primary=True
            for rank, sug in enumerate(selected, start=1):
                # Add alternatives metadata
                bank_id = sug.get("bank_ids", [None])[0] if sug.get("bank_ids") else None
                book_ids = sug.get("journal_entries_ids", [])
                alternatives_group_id = f"bank_{bank_id}_otm" if bank_id else None
                sug["rank_among_alternatives"] = rank
                sug["alternatives_group_id"] = alternatives_group_id
                sug["is_primary"] = (rank == 1)
                sug["total_alternatives"] = len(selected)  # Will be updated with alternatives count
                
                log.info(
                    "[REGULAR] _run_one_to_many: recording selected suggestion rank=%d/%d "
                    "bank_id=%d book_ids=%s score=%.4f is_primary=%s",
                    rank, len(selected), bank_id, book_ids,
                    sug.get("confidence_score", 0.0), sug["is_primary"],
                )
                self._record(sug)
            
            # Add alternatives that weren't selected (for visibility, but don't mark as used)
            selected_bank_ids = {bid for s in selected for bid in s.get("bank_ids", [])}
            alternatives = [s for s in all_candidates if s not in selected]
            
            # Group alternatives by bank_id for max_k per anchor
            alternatives_by_bank: Dict[int, List[dict]] = {}
            for alt in alternatives:
                bank_id = alt.get("bank_ids", [None])[0] if alt.get("bank_ids") else None
                if bank_id and bank_id not in selected_bank_ids:
                    if bank_id not in alternatives_by_bank:
                        alternatives_by_bank[bank_id] = []
                    if len(alternatives_by_bank[bank_id]) < max_k - 1:  # -1 because best was selected
                        alternatives_by_bank[bank_id].append(alt)
            
            # Add alternatives to suggestions with proper ranking
            for bank_id, alt_list in alternatives_by_bank.items():
                # Sort alternatives by deterministic key
                alt_list.sort(key=self._deterministic_sort_key)
                alternatives_group_id = f"bank_{bank_id}_otm"
                total_alt_count = len(selected) + len(alt_list)  # Selected + alternatives
                
                # Update selected suggestions with correct total_alternatives
                for sug in selected:
                    if sug.get("bank_ids", [None])[0] == bank_id:
                        sug["total_alternatives"] = total_alt_count
                
                # Add alternatives with ranks starting from len(selected) + 1
                for rank_offset, alt in enumerate(alt_list, start=1):
                    alt["rank_among_alternatives"] = len(selected) + rank_offset
                    alt["alternatives_group_id"] = alternatives_group_id
                    alt["is_primary"] = False
                    alt["total_alternatives"] = total_alt_count
                    self.suggestions.append(alt)
                    if self._on_suggestion:
                        try:
                            self._on_suggestion(alt)
                        except Exception as cb_exc:
                            log.warning(
                                "on_suggestion callback failed (alt one_to_many): %s",
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
            "[REGULAR] _run_many_to_one: banks=%d books=%d win=%d amount_tol=%s allow_mixed=%s max_k=%d",
            len(banks), len(books), win, stage.amount_tol, stage.allow_mixed_signs, max_k,
        )

        def add_candidate(sug: dict, buf: list[dict]) -> None:
            """Add candidate with deterministic tie-breaking for stable ordering."""
            def sort_key(s):
                """Deterministic sort key for suggestions."""
                return (
                    -float(s.get("confidence_score", 0.0)),  # Higher is better
                    s.get("extra", {}).get("avg_date_delta_days_measured", 9999),  # Lower is better
                    s.get("abs_amount_diff", 999999.0),  # Lower is better
                    tuple(sorted(s.get("bank_ids", []))),  # Deterministic
                    tuple(sorted(s.get("journal_entries_ids", []))),  # Deterministic
                )
            
            score_key = sort_key(sug)
            if len(buf) < max_k:
                buf.append(sug)
                return
            worst_idx = min(range(len(buf)), key=lambda i: sort_key(buf[i]))
            worst_key = sort_key(buf[worst_idx])
            if score_key < worst_key:  # Tuple comparison: better candidate
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
            
            # Deterministic sorting: sort by (amount, id) for stable combination generation
            local_banks.sort(key=lambda b: (b.amount_base or Decimal("0"), b.id))

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
                    # Check intra-group coherence before scoring
                    worst_metrics = _compute_worst_match_metrics(list(combo), [book])
                    is_coherent, reject_reason = _check_intra_group_coherence(
                        list(combo), [book], stage, worst_metrics
                    )
                    if not is_coherent:
                        log.debug(
                            "[REGULAR] _run_many_to_one: book_id=%d mixed-sign combo REJECTED - coherence check failed: %s "
                            "(bank_ids=%s)",
                            book.id, reject_reason, [b.id for b in combo],
                        )
                        combo = None  # Reject this combo
                    
                    if combo:  # Only proceed if coherence check passed
                        bank_dates = [b.date for b in combo if b.date]
                        bank_span = (max(bank_dates) - min(bank_dates)).days if len(bank_dates) >= 2 else 0
                        bank_avg = self._weighted_avg_date(combo)
                        book_avg = book.date
                        avg_delta = abs((bank_avg - book_avg).days) if (bank_avg and book_avg) else win + 1

                        # Calculate actual amount difference
                        bank_total = sum((b.amount_base for b in combo), Decimal("0"))
                        book_total = book.amount_base or Decimal("0")
                        amount_diff = abs(q2(bank_total) - q2(book_total))

                        sim = self._cosine_similarity(_avg_embedding(combo), book.embedding or [])
                        scores = compute_match_scores(
                            embed_sim=sim,
                            amount_diff=amount_diff,
                            amount_tol=stage.amount_tol or CENT,
                            date_diff=avg_delta,
                            date_tol=stage.avg_date_delta_days or 1,
                            currency_match=1.0,
                            weights=self.stage_weights,
                            worst_metrics=worst_metrics,
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
                    all_candidates.extend(candidates)
                continue
                def sort_key(s):
                    return (
                        -float(s.get("confidence_score", 0.0)),  # Higher is better
                        s.get("extra", {}).get("avg_date_delta_days_measured", 9999),  # Lower is better
                        s.get("abs_amount_diff", 999999.0),  # Lower is better
                        tuple(sorted(s.get("bank_ids", []))),  # Deterministic
                        tuple(sorted(s.get("journal_entries_ids", []))),  # Deterministic
                    )
                candidates.sort(key=sort_key)
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

            # Feasibility pruning: compute g_min to skip infeasible sizes
            feasible, g_min = compute_feasibility_bounds(bank_amounts, target, tol, max_size)
            
            if g_min is None:
                # No feasible size exists - skip this book entirely
                log.debug("MTO book=%s no feasible group size (g_min=None)", book.id)
                if candidates:
                    all_candidates.extend(candidates)
                continue
            
            # All-in shortcut: if only full group is feasible and it matches exactly
            if g_min == len(local_banks):
                all_sum = sum(bank_amounts)
                all_diff = abs(q2(all_sum) - target)
                if all_diff <= tol:
                    # Check date constraints for full group
                    bank_dates = [b.date for b in local_banks if b.date]
                    bank_span = (max(bank_dates) - min(bank_dates)).days if len(bank_dates) >= 2 else 0
                    if (not stage.group_span_days or bank_span <= stage.group_span_days):
                        bank_avg = self._weighted_avg_date(local_banks)
                        book_avg = book.date
                        avg_delta = abs((bank_avg - book_avg).days) if (bank_avg and book_avg) else win + 1
                        if (not stage.avg_date_delta_days or avg_delta <= stage.avg_date_delta_days):
                            # Check intra-group coherence before accepting
                            worst_metrics = _compute_worst_match_metrics(local_banks, [book])
                            is_coherent, reject_reason = _check_intra_group_coherence(
                                local_banks, [book], stage, worst_metrics
                            )
                            if not is_coherent:
                                log.debug(
                                    "[REGULAR] _run_many_to_one: book_id=%d all-in combo REJECTED - coherence check failed: %s",
                                    book.id, reject_reason,
                                )
                                continue
                            
                            # All-in is valid - score and add
                            sim = self._cosine_similarity(_avg_embedding(local_banks), book.embedding or [])
                            scores = compute_match_scores(
                                embed_sim=sim,
                                amount_diff=all_diff,
                                amount_tol=stage.amount_tol or CENT,
                                date_diff=avg_delta,
                                date_tol=stage.avg_date_delta_days or 1,
                                currency_match=1.0,
                                weights=self.stage_weights,
                                worst_metrics=worst_metrics,
                            )
                            sug = self._make_suggestion(
                                "many_to_one",
                                local_banks,
                                [book],
                                scores["global_score"],
                                stage=stage,
                                weights=self.stage_weights,
                                component_scores=scores,
                                extra={
                                    "bank_span_days_measured": bank_span,
                                    "avg_date_delta_days_measured": avg_delta,
                                    "mixed_signs": False,
                                    "all_in_shortcut": True,
                                    "g_min": g_min,
                                },
                            )
                            add_candidate(sug, candidates)
                            if candidates:
                                all_candidates.extend(candidates)
                            continue  # Skip enumeration

            prefix_max: List[Decimal] = []
            if use_prefix_bounds:
                amounts_desc = sorted(bank_amounts, reverse=True)
                acc = Decimal("0")
                for amt in amounts_desc:
                    acc += amt
                    prefix_max.append(acc)
                if q2(prefix_max[-1]) + tol < target:
                    if candidates:
                        all_candidates.extend(candidates)
                    continue

            # Start enumeration at g_min, not 1
            for size in range(g_min, max_size + 1):
                if not feasible[size]:
                    continue  # Skip infeasible sizes
                if self._time_exceeded():
                    return

                if use_prefix_bounds and q2(prefix_max[size - 1]) + tol < target:
                    continue

                for combo in combinations(local_banks, size):
                    # Check inside lock for thread safety
                    with self._used_banks_lock:
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

                    # Check intra-group coherence before scoring
                    worst_metrics = _compute_worst_match_metrics(list(combo), [book])
                    is_coherent, reject_reason = _check_intra_group_coherence(
                        list(combo), [book], stage, worst_metrics
                    )
                    if not is_coherent:
                        log.debug(
                            "[REGULAR] _run_many_to_one: book_id=%d combo REJECTED - coherence check failed: %s "
                            "(bank_ids=%s)",
                            book.id, reject_reason, [b.id for b in combo],
                        )
                        continue

                    # Use the already-calculated diff as amount_diff
                    sim = self._cosine_similarity(_avg_embedding(combo), book.embedding or [])
                    scores = compute_match_scores(
                        embed_sim=sim,
                        amount_diff=diff,
                        amount_tol=stage.amount_tol or CENT,
                        date_diff=avg_delta,
                        date_tol=stage.avg_date_delta_days or 1,
                        currency_match=1.0,
                        weights=self.stage_weights,
                        worst_metrics=worst_metrics,
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

            # Add all candidates from this book to global collection
            if candidates:
                all_candidates.extend(candidates)
        
        # Phase 2: Global selection - pick non-overlapping set
        if all_candidates:
            selected = self._global_select_non_overlapping(all_candidates)
            
            # Record selected suggestions (these mark IDs as used) with rank=1, is_primary=True
            for rank, sug in enumerate(selected, start=1):
                # Add alternatives metadata
                book_id = sug.get("journal_entries_ids", [None])[0] if sug.get("journal_entries_ids") else None
                alternatives_group_id = f"book_{book_id}_mto" if book_id else None
                sug["rank_among_alternatives"] = rank
                sug["alternatives_group_id"] = alternatives_group_id
                sug["is_primary"] = (rank == 1)
                sug["total_alternatives"] = len(selected)  # Will be updated with alternatives count
                self._record(sug)
            
            # Add alternatives that weren't selected (for visibility, but don't mark as used)
            selected_book_ids = {jid for s in selected for jid in s.get("journal_entries_ids", [])}
            alternatives = [s for s in all_candidates if s not in selected]
            
            # Group alternatives by book_id for max_k per anchor
            alternatives_by_book: Dict[int, List[dict]] = {}
            for alt in alternatives:
                book_id = alt.get("journal_entries_ids", [None])[0] if alt.get("journal_entries_ids") else None
                if book_id and book_id not in selected_book_ids:
                    if book_id not in alternatives_by_book:
                        alternatives_by_book[book_id] = []
                    if len(alternatives_by_book[book_id]) < max_k - 1:  # -1 because best was selected
                        alternatives_by_book[book_id].append(alt)
            
            # Add alternatives to suggestions with proper ranking
            for book_id, alt_list in alternatives_by_book.items():
                # Sort alternatives by deterministic key
                alt_list.sort(key=self._deterministic_sort_key)
                alternatives_group_id = f"book_{book_id}_mto"
                total_alt_count = len(selected) + len(alt_list)  # Selected + alternatives
                
                # Update selected suggestions with correct total_alternatives
                for sug in selected:
                    if sug.get("journal_entries_ids", [None])[0] == book_id:
                        sug["total_alternatives"] = total_alt_count
                
                # Add alternatives with ranks starting from len(selected) + 1
                for rank_offset, alt in enumerate(alt_list, start=1):
                    alt["rank_among_alternatives"] = len(selected) + rank_offset
                    alt["alternatives_group_id"] = alternatives_group_id
                    alt["is_primary"] = False
                    alt["total_alternatives"] = total_alt_count
                    self.suggestions.append(alt)
                    if self._on_suggestion:
                        try:
                            self._on_suggestion(alt)
                        except Exception as cb_exc:
                            log.warning(
                                "on_suggestion callback failed (alt many_to_one): %s",
                                cb_exc,
                            )


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
        log.info(
            "_run_fuzzy_1to1: START - banks=%d books=%d used_banks=%d used_books=%d",
            len(banks), len(books), len(self.used_banks), len(self.used_books),
        )
        
        win = stage.candidate_window_days
        bin_size = max(1, min(win or 1, 7))

        max_k = max(int(stage.max_alternatives_per_anchor or 1), 1)
        
        log.info(
            "_run_fuzzy_1to1: parameters win=%d bin_size=%d max_k=%d amount_tol=%s",
            win, bin_size, max_k, stage.amount_tol,
        )

        # Indexar books por bins de data para lookup mais rápido
        available_books = [b for b in books if b.id not in self.used_books]
        log.debug(
            "_run_fuzzy_1to1: available books for binning: %d (from %d total)",
            len(available_books), len(books),
        )
        
        book_bins = build_date_bins(
            available_books,
            get_date=lambda e: e.date,
            bin_size_days=bin_size,
        )
        
        log.debug(
            "_run_fuzzy_1to1: built %d date bins for candidate lookup",
            len(book_bins),
        )

        candidates: list[dict] = []
        pairs_tested = 0
        pairs_valid = 0

        banks_processed = 0
        for bank in banks:
            if self._time_exceeded():
                log.warning("_run_fuzzy_1to1: time exceeded, stopping")
                return
            if bank.id in self.used_banks:
                log.debug("_run_fuzzy_1to1: bank_id=%d already used, skipping", bank.id)
                continue

            banks_processed += 1
            log.debug(
                "_run_fuzzy_1to1: processing bank_id=%d amount=%s date=%s currency_id=%d",
                bank.id, bank.amount_base, bank.date, bank.currency_id,
            )

            # Books "perto" em data
            candidates_in_window = list(
                iter_date_bin_candidates(bank.date, book_bins, bin_size, win)
            )
            log.debug(
                "_run_fuzzy_1to1: bank_id=%d found %d books in date window (win=%d days)",
                bank.id, len(candidates_in_window), win,
            )
            if not candidates_in_window:
                log.debug("_run_fuzzy_1to1: bank_id=%d no books in date window, skipping", bank.id)
                continue

            # Bucket por amount em torno deste bank
            buckets = build_amount_buckets(
                candidates_in_window, get_amount=lambda e: e.amount_base
            )
            log.debug(
                "_run_fuzzy_1to1: bank_id=%d built %d amount buckets",
                bank.id, len(buckets),
            )

            for book in probe_amount_buckets(
                buckets, bank.amount_base, stage.amount_tol
            ):
                pairs_tested += 1
                if book.id in self.used_books:
                    log.debug(
                        "_run_fuzzy_1to1: skipping pair bank_id=%d book_id=%d (book already used)",
                        bank.id, book.id,
                    )
                    continue

                log.debug(
                    "_run_fuzzy_1to1: testing pair bank_id=%d book_id=%d "
                    "(bank_amount=%s book_amount=%s)",
                    bank.id, book.id, bank.amount_base, book.amount_base,
                )

                # Guards básicos
                if bank.currency_id != book.currency_id:
                    log.debug(
                        "_run_fuzzy_1to1: REJECTED bank_id=%d book_id=%d - currency mismatch "
                        "(bank_currency=%d book_currency=%d)",
                        bank.id, book.id, bank.currency_id, book.currency_id,
                    )
                    continue

                a_diff = abs(q2(bank.amount_base) - q2(book.amount_base))
                if a_diff > stage.amount_tol:
                    log.debug(
                        "_run_fuzzy_1to1: REJECTED bank_id=%d book_id=%d - amount diff too large "
                        "(diff=%s > tol=%s)",
                        bank.id, book.id, a_diff, stage.amount_tol,
                    )
                    continue

                # Δ de datas
                if bank.date and book.date:
                    avg_delta = abs((bank.date - book.date).days)
                else:
                    avg_delta = (stage.avg_date_delta_days or win or 0) + 1

                if stage.avg_date_delta_days and avg_delta > stage.avg_date_delta_days:
                    log.debug(
                        "_run_fuzzy_1to1: REJECTED bank_id=%d book_id=%d - date delta too large "
                        "(delta=%d > max=%d)",
                        bank.id, book.id, avg_delta, stage.avg_date_delta_days,
                    )
                    continue

                embed_sim = self._cosine_similarity(
                    bank.embedding or [], book.embedding or []
                )
                log.debug(
                    "_run_fuzzy_1to1: pair bank_id=%d book_id=%d passed all checks "
                    "(amount_diff=%s date_delta=%d embed_sim=%.4f)",
                    bank.id, book.id, a_diff, avg_delta, embed_sim,
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

                pairs_valid += 1
                log.info(
                    "_run_fuzzy_1to1: VALID CANDIDATE bank_id=%d book_id=%d "
                    "(score=%.4f amount_diff=%s date_delta=%d embed_sim=%.4f)",
                    bank.id, book.id, scores["global_score"], a_diff, avg_delta, embed_sim,
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

        log.info(
            "_run_fuzzy_1to1: candidate generation complete - banks_processed=%d "
            "pairs_tested=%d pairs_valid=%d total_candidates=%d",
            banks_processed, pairs_tested, pairs_valid, len(candidates),
        )
        
        if not candidates:
            log.info("_run_fuzzy_1to1: no valid candidates found, returning")
            return

        # GLOBAL SELECTION: melhores pares não sobrepostos
        log.info(
            "_run_fuzzy_1to1: Phase 2 - global selection starting with %d candidates",
            len(candidates),
        )
        
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
        primary_selected = 0
        skipped_overlap = 0

        for idx, c in enumerate(candidates):
            bank = c["bank"]
            book = c["book"]

            if (
                bank.id in self.used_banks
                or book.id in self.used_books
                or bank.id in local_used_banks
                or book.id in local_used_books
            ):
                skipped_overlap += 1
                log.debug(
                    "_run_fuzzy_1to1: skipping candidate %d/%d bank_id=%d book_id=%d "
                    "(already used in global selection)",
                    idx + 1, len(candidates), bank.id, book.id,
                )
                continue

            scores = c["scores"]
            weights = c["weights"]

            log.info(
                "_run_fuzzy_1to1: selecting primary pair %d bank_id=%d book_id=%d "
                "(score=%.4f rank=%d/%d)",
                primary_selected + 1, bank.id, book.id, scores["global_score"],
                idx + 1, len(candidates),
            )

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
            primary_selected += 1

            local_used_banks.add(bank.id)
            local_used_books.add(book.id)
            primary_pairs.add((bank.id, book.id))

            if len(self.suggestions) >= self.config.max_suggestions:
                log.warning(
                    "_run_fuzzy_1to1: reached max_suggestions=%d, stopping selection",
                    self.config.max_suggestions,
                )
                break
        
        log.info(
            "_run_fuzzy_1to1: Phase 2 complete - primary_selected=%d skipped_overlap=%d",
            primary_selected, skipped_overlap,
        )

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
            "[REGULAR] _run_many_to_many: banks=%d books=%d win=%d amount_tol=%s allow_mixed=%s max_k=%d",
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
    
                            # Use the already-calculated diff as amount_diff
                            scores = compute_match_scores(
                                embed_sim=embed_sim,
                                amount_diff=diff,
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
                candidates.sort(key=self._deterministic_sort_key)
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



    # ------------------------ Internal helpers ------------------------

    def _deterministic_sort_key(self, s: dict) -> tuple:
        """
        Deterministic sort key for suggestions to ensure stable ordering.
        Returns a tuple for comparison: smaller tuple = better candidate.
        """
        return (
            -float(s.get("confidence_score", 0.0)),  # Higher is better (negated)
            s.get("extra", {}).get("avg_date_delta_days_measured", 9999),  # Lower is better
            s.get("abs_amount_diff", 999999.0),  # Lower is better
            tuple(sorted(s.get("bank_ids", []))),  # Deterministic
            tuple(sorted(s.get("journal_entries_ids", []))),  # Deterministic
        )
    
    def _global_select_non_overlapping(self, candidates: List[dict]) -> List[dict]:
        """
        Select a non-overlapping set of suggestions from candidates using greedy selection.
        Sorted by confidence score, picks candidates that don't conflict with already-selected ones.
        
        Returns the selected suggestions in order of selection.
        """
        if not candidates:
            log.debug("_global_select_non_overlapping: no candidates provided")
            return []
        
        log.debug(
            "_global_select_non_overlapping: starting with %d candidates",
            len(candidates),
        )
        
        # Sort by deterministic key (best first)
        candidates_sorted = sorted(candidates, key=self._deterministic_sort_key)
        
        selected: List[dict] = []
        used_bank_ids: set[int] = set()
        used_book_ids: set[int] = set()
        skipped_overlap = 0
        
        for idx, candidate in enumerate(candidates_sorted):
            bank_ids = set(candidate.get("bank_ids", []))
            book_ids = set(candidate.get("journal_entries_ids", []))
            score = candidate.get("confidence_score", 0.0)
            
            # Skip if any ID is already used
            overlapping_banks = bank_ids & used_bank_ids
            overlapping_books = book_ids & used_book_ids
            if overlapping_banks or overlapping_books:
                skipped_overlap += 1
                log.debug(
                    "_global_select_non_overlapping: skipping candidate %d/%d "
                    "(score=%.4f bank_ids=%s book_ids=%s overlaps: banks=%s books=%s)",
                    idx + 1, len(candidates_sorted), score,
                    list(bank_ids), list(book_ids),
                    list(overlapping_banks), list(overlapping_books),
                )
                continue
            
            selected.append(candidate)
            used_bank_ids.update(bank_ids)
            used_book_ids.update(book_ids)
            
            log.debug(
                "_global_select_non_overlapping: selected candidate %d/%d "
                "(score=%.4f bank_ids=%s book_ids=%s) total_selected=%d",
                idx + 1, len(candidates_sorted), score,
                list(bank_ids), list(book_ids), len(selected),
            )
        
        log.info(
            "_global_select_non_overlapping: completed - selected=%d skipped_overlap=%d "
            "from total=%d candidates",
            len(selected), skipped_overlap, len(candidates),
        )
        
        return selected

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
        Thread-safe version for parallel processing.
        
        Performs atomic check-and-set: verifies IDs are not already used before marking.
        """
        bank_ids = suggestion["bank_ids"]
        book_ids = suggestion["journal_entries_ids"]
        bank_key = tuple(sorted(bank_ids))
        book_key = tuple(sorted(book_ids))
        key = (bank_key, book_key)
        match_type = suggestion.get("match_type", "unknown")
        score = suggestion.get("confidence_score", 0.0)

        log.debug(
            "_record: attempting to record suggestion type=%s bank_ids=%s book_ids=%s score=%.4f",
            match_type, bank_ids, book_ids, score,
        )

        with self._lock:
            if key in self._seen_groups:
                log.info(
                    "_record: SKIPPING duplicate suggestion type=%s banks=%s books=%s "
                    "(already seen in this run)",
                    match_type, bank_key, book_key,
                )
                return

            # Atomic check: verify no IDs are already used (race condition guard)
            with self._used_banks_lock:
                used_bank_ids = [bid for bid in bank_ids if bid in self.used_banks]
                if used_bank_ids:
                    log.info(
                        "_record: SKIPPING suggestion type=%s banks=%s books=%s "
                        "- bank_ids already used: %s",
                        match_type, bank_ids, book_ids, used_bank_ids,
                    )
                    return
            
            with self._used_books_lock:
                used_book_ids = [jid for jid in book_ids if jid in self.used_books]
                if used_book_ids:
                    log.info(
                        "_record: SKIPPING suggestion type=%s banks=%s books=%s "
                        "- book_ids already used: %s",
                        match_type, bank_ids, book_ids, used_book_ids,
                    )
                    return

            self._seen_groups.add(key)

            log.info(
                "_record: RECORDING suggestion type=%s bank_ids=%s book_ids=%s "
                "confidence=%.4f total_suggestions=%d",
                match_type, bank_ids, book_ids, score, len(self.suggestions) + 1,
            )

            self.suggestions.append(suggestion)
            
            # Mark as used atomically
            with self._used_banks_lock:
                before_banks = len(self.used_banks)
                self.used_banks.update(bank_ids)
                log.debug(
                    "_record: marked %d banks as used (total used now: %d)",
                    len(bank_ids), len(self.used_banks),
                )
            with self._used_books_lock:
                before_books = len(self.used_books)
                self.used_books.update(book_ids)
                log.debug(
                    "_record: marked %d books as used (total used now: %d)",
                    len(book_ids), len(self.used_books),
                )

        # Dispara callback (para persistência incremental, etc.)
        if self._on_suggestion:
            try:
                self._on_suggestion(suggestion)
                log.debug("_record: on_suggestion callback executed successfully")
            except Exception as cb_exc:
                log.warning("_record: on_suggestion callback failed: %s", cb_exc, exc_info=True)

    # ----------------------------------------------------------------------
    # Adaptive strategy selection and candidate preparation
    # ----------------------------------------------------------------------
    def _adaptive_select_strategy(
        self,
        banks: List[BankTransactionDTO],
        books: List[JournalEntryDTO],
        stage: StageConfig,
    ) -> dict:
        """
        Determine the best search strategy and parameters based on data size and characteristics.
        
        Returns a dict with fields:
          - strategy:   "exact", "branch_and_bound", "beam", etc.
          - max_size:   maximum subset size to explore (books or banks)
          - max_cands:  maximum number of local candidates to retain after pre-filtering
          - beam_width: beam width for beam search (if used)
        """
        n_banks = len(banks)
        n_books = len(books)
        # Count non-zero and mixed-sign samples
        bank_signs = [_sign(b.amount_base) for b in banks]
        book_signs = [_sign(e.amount_base) for e in books]
        has_mixed_banks = 1 in bank_signs and -1 in bank_signs
        has_mixed_books = 1 in book_signs and -1 in book_signs
        
        # Base result
        result = {
            "strategy": "exact",
            "max_size": max(stage.max_group_size_book, stage.max_group_size_bank),
            "max_cands": None,
            "beam_width": None,
        }
        
        # Decide candidate cap: larger sets require pruning
        # Be generous with candidates - better to have more and filter later
        if n_books > 100 or n_banks > 100:
            result["max_cands"] = 128  # keep more local candidates for very large sets
        elif n_books > 40 or n_banks > 40:
            result["max_cands"] = 96
        elif n_books > 20 or n_banks > 20:
            result["max_cands"] = 64
        
        # Set a beam width for heuristic search
        # Larger data sets use a moderate beam; smaller sets use exact search
        if (n_books > 50 or n_banks > 50) and not has_mixed_books and not has_mixed_banks:
            # data too large for full enumeration, use beam search
            result["strategy"] = "beam"
            result["beam_width"] = 10
            result["max_size"] = stage.max_group_size_book
        else:
            result["strategy"] = "exact"
    
        return result
    
    def _prepare_candidates(
        self,
        bank: BankTransactionDTO,
        books: List[JournalEntryDTO],
        stage: StageConfig,
        max_local: Optional[int] = None,
    ) -> List[JournalEntryDTO]:
        """
        Select candidate books near the bank in date and currency, with optional cap.
        
        Handles same-sign filtering and returns a list sorted by (amount diff, date diff).
        For small amounts, prioritizes same-day matches using date-based grouping.
        """
        win = stage.candidate_window_days
        bank_amt = bank.amount_base or Decimal("0")
        bank_sign = _sign(bank_amt)
        abs_bank_amt = abs(bank_amt)
        
        # Filter by company, date window, and currency
        local_books = [
            b for b in books
            if b.company_id == self.company_id
            and b.currency_id == bank.currency_id
            and b.date and bank.date
            and abs((b.date - bank.date).days) <= win
        ]
        
        # Filter by sign if mixed signs are not allowed
        if not stage.allow_mixed_signs and bank_sign != 0:
            if bank_sign > 0:
                local_books = [b for b in local_books if _sign(b.amount_base) >= 0]
            else:
                local_books = [b for b in local_books if _sign(b.amount_base) <= 0]
        
        # If no cap or small list, return all
        if not max_local or len(local_books) <= max_local:
            return local_books
        
        # Date-based grouping optimization for small amounts
        # Small amounts are more likely to match on the same day
        SMALL_AMOUNT_THRESHOLD = Decimal("1000.00")  # Consider amounts < $1000 as "small"
        USE_DATE_GROUPING = abs_bank_amt < SMALL_AMOUNT_THRESHOLD
        
        if USE_DATE_GROUPING and bank.date:
            log.debug(
                "[FAST] OTM_FAST bank=%s using date_grouping (amount=%s < threshold=%s) candidates=%s",
                bank.id,
                abs_bank_amt,
                SMALL_AMOUNT_THRESHOLD,
                len(local_books),
            )
            # Group candidates by date proximity: same day, ±1 day, ±2 days, etc.
            target_date = bank.date
            grouped_by_date: Dict[int, List[JournalEntryDTO]] = {}
            
            for b in local_books:
                if not b.date:
                    continue
                date_diff = abs((b.date - target_date).days)
                grouped_by_date.setdefault(date_diff, []).append(b)
            
            # Prioritize same-day matches, then ±1 day, ±2 days, etc.
            target = q2(bank_amt)
            result: List[JournalEntryDTO] = []
            same_day_count = len(grouped_by_date.get(0, []))
            
            for date_diff in sorted(grouped_by_date.keys()):
                same_date_group = grouped_by_date[date_diff]
                # Within each date group, sort by amount difference
                same_date_group.sort(key=lambda b: abs(q2(b.amount_base or Decimal("0")) - target))
                result.extend(same_date_group)
                
                # Early exit if we have enough candidates from same/close dates
                if len(result) >= max_local:
                    log.debug(
                        "[FAST] OTM_FAST bank=%s date_grouping: same_day=%s total_selected=%s from_date_diff=%s",
                        bank.id,
                        same_day_count,
                        len(result),
                        date_diff,
                    )
                    break
            
            # If we still need more, fill from remaining groups
            if len(result) < max_local:
                remaining = [b for b in local_books if b not in result]
                remaining.sort(key=lambda b: (
                    abs((b.date - target_date).days) if b.date else 9999,
                    abs(q2(b.amount_base or Decimal("0")) - target)
                ))
                result.extend(remaining[:max_local - len(result)])
            
            return result[:max_local]
        
        # Otherwise sort by combined (amount diff, date diff) and cap
        target = q2(bank_amt)
        def sort_key(b):
            amt_diff = abs(q2(b.amount_base or Decimal("0")) - target)
            date_diff = abs((b.date - bank.date).days) if b.date and bank.date else 9999
            return (amt_diff, date_diff)
        
        local_sorted = sorted(local_books, key=sort_key)
        return local_sorted[:max_local]
    
    def _evaluate_and_record_candidates(
        self,
        match_type: str,
        bank: BankTransactionDTO,
        combos: List[List[JournalEntryDTO]],
        stage: StageConfig,
        extra_info: Optional[dict] = None,
    ) -> None:
        """
        Given a list of book combos for a single bank, compute scores, sort, and record suggestions.
        
        extra_info: additional data to include in the suggestion's 'extra' field
        """
        candidates: List[dict] = []
        rejected_by_date = 0
        rejected_by_coherence = 0
        total_combos = len(combos)
        
        for combo in combos:
            # Compute measured spans and weighted avg date delta
            book_dates = [b.date for b in combo if b.date]
            book_span = (max(book_dates) - min(book_dates)).days if len(book_dates) >= 2 else 0
            bank_avg_date = bank.date
            books_avg_date = self._weighted_avg_date(combo)
            avg_delta = abs((bank_avg_date - books_avg_date).days) if bank_avg_date and books_avg_date else stage.candidate_window_days + 1
            
            # Skip if out of date range
            if stage.avg_date_delta_days and avg_delta > stage.avg_date_delta_days:
                rejected_by_date += 1
                continue
            
            # Check intra-group coherence before scoring (lenient mode)
            worst_metrics = _compute_worst_match_metrics(bank, combo)
            is_coherent, reject_reason = _check_intra_group_coherence(
                bank, combo, stage, worst_metrics, strict=False
            )
            if not is_coherent:
                rejected_by_coherence += 1
                log.debug(
                    "[FAST] _evaluate_and_record_candidates: bank_id=%d combo REJECTED - coherence check failed: %s "
                    "(book_ids=%s)",
                    bank.id, reject_reason, [b.id for b in combo],
                )
                continue
            
            # Calculate actual amount difference
            bank_total = bank.amount_base or Decimal("0")
            book_total = sum((b.amount_base for b in combo), Decimal("0"))
            amount_diff = abs(q2(bank_total) - q2(book_total))
            
            # Cosine similarity
            sim = self._cosine_similarity(bank.embedding or [], _avg_embedding(combo))
            scores = compute_match_scores(
                embed_sim=sim,
                amount_diff=amount_diff,
                amount_tol=stage.amount_tol or CENT,
                date_diff=avg_delta,
                date_tol=stage.avg_date_delta_days or 1,
                currency_match=1.0,
                weights=self.stage_weights,
                worst_metrics=worst_metrics,
            )
            suggestion = self._make_suggestion(
                match_type,
                [bank],
                combo,
                scores["global_score"],
                stage=stage,
                weights=self.stage_weights,
                component_scores=scores,
                extra={
                    "book_span_days_measured": book_span,
                    "avg_date_delta_days_measured": avg_delta,
                    "mixed_signs": extra_info.get("mixed_signs") if extra_info else False,
                    "engine": extra_info.get("engine") if extra_info else "fast_v2",
                },
            )
            candidates.append(suggestion)
        
        # Log summary of filtering
        if total_combos > 0:
            log.debug(
                "[FAST] _evaluate_and_record_candidates: bank_id=%d processed=%d accepted=%d rejected_date=%d rejected_coherence=%d",
                bank.id, total_combos, len(candidates), rejected_by_date, rejected_by_coherence
            )
        
        # Sort candidates and record up to max_alternatives_per_anchor
        if not candidates:
            if total_combos > 0:
                log.info(
                    "[FAST] _evaluate_and_record_candidates: bank_id=%d ALL %d combos rejected (date=%d coherence=%d)",
                    bank.id, total_combos, rejected_by_date, rejected_by_coherence
                )
            return
        candidates.sort(key=self._deterministic_sort_key)
        best = candidates[0]
        self._record(best)
        for alt in candidates[1:stage.max_alternatives_per_anchor]:
            self.suggestions.append(alt)
            if self._on_suggestion:
                try:
                    self._on_suggestion(alt)
                except Exception as cb_exc:
                    log.warning("on_suggestion callback failed: %s", cb_exc)
    
    # ----------------------------------------------------------------------
    # Fast variants (placed at the bottom of ReconciliationPipelineEngine)
    # ----------------------------------------------------------------------
    def _process_one_bank_otm_fast(
        self,
        bank: BankTransactionDTO,
        books: List[JournalEntryDTO],
        stage: StageConfig,
        max_local: Optional[int],
        beam_width: Optional[int],
        strategy: str,
    ) -> None:
        """
        Process a single bank for one-to-many matching (thread-safe helper).
        """
        # Check if already used (thread-safe check)
        with self._used_banks_lock:
            if bank.id in self.used_banks:
                return
        
        # Pre-select candidate books for this bank
        local_books = self._prepare_candidates(bank, books, stage, max_local=max_local)
        # Only apply embedding preselection if we have many candidates AND good embeddings
        # Be more generous - use 64 instead of 32 and only filter when we have way too many
        if bank.embedding and len(local_books) > stage.max_group_size_book * 8:
            before_count = len(local_books)
            top_k = min(before_count, (max_local or before_count), 64)
            local_books = preselect_candidates_by_embedding(bank, local_books, top_k=top_k)
            log.debug(
                "[FAST] OTM_FAST bank=%s embedding preselect: before=%s after=%s top_k=%s",
                bank.id, before_count, len(local_books), top_k
            )
        if not local_books:
            log.debug("[FAST] OTM_FAST bank=%s no candidates survived prefilter", bank.id)
            return
        book_items = _build_fast_items(local_books)
        log.debug(
            "[FAST] OTM_FAST bank=%s amount=%s candidates=%s max_group=%s",
            bank.id,
            bank.amount_base,
            len(book_items),
            stage.max_group_size_book,
        )
        
        combos: List[List[JournalEntryDTO]] = []
        target = q2(bank.amount_base or Decimal("0"))
        
        # Mixed-sign check
        book_signs = [item.sign for item in book_items]
        has_mixed_books = (1 in book_signs and -1 in book_signs)
        if has_mixed_books and not stage.allow_mixed_signs:
            log.debug("[FAST] OTM_FAST bank=%s mixed_signs_blocked", bank.id)
        
        # Path 1: Mixed-sign via DFS if allowed
        if has_mixed_books and stage.allow_mixed_signs:
            log.debug("[FAST] OTM_FAST bank=%s entering mixed-sign DFS path", bank.id)
            subset = self._find_mixed_one_to_many_group(bank, [item.dto for item in book_items], stage)
            if subset:
                combos.append(list(subset))
                log.debug("[FAST] OTM_FAST bank=%s mixed DFS produced group size=%s", bank.id, len(subset))
            else:
                log.debug("[FAST] OTM_FAST bank=%s mixed DFS produced no group", bank.id)
        
        # Path 2: Same-sign / bounded search
        # Generate candidate combos up to max_group_size
        max_size = min(stage.max_group_size_book, len(book_items))
        
        # Feasibility pruning: compute g_min to skip infeasible sizes
        book_amounts = [item.amount for item in book_items]
        tol = stage.amount_tol or Decimal("0")
        feasible, g_min = compute_feasibility_bounds(book_amounts, target, tol, max_size)
        
        if g_min is None:
            # No feasible size exists - skip this bank entirely
            log.debug("[FAST] OTM_FAST bank=%s no feasible group size (g_min=None)", bank.id)
            if combos:
                # Still process mixed-sign results if any
                pass
            else:
                return
        
        # All-in shortcut: if only full group is feasible and it matches exactly
        if g_min == len(book_items):
            all_sum = sum(book_amounts)
            all_diff = abs(q2(all_sum) - target)
            if all_diff <= tol:
                # Check date constraints for full group
                book_dates = [item.dto.date for item in book_items if item.dto.date]
                book_span = (max(book_dates) - min(book_dates)).days if len(book_dates) >= 2 else 0
                if (not stage.group_span_days or book_span <= stage.group_span_days):
                    bank_avg = bank.date
                    book_avg = self._weighted_avg_date([item.dto for item in book_items])
                    avg_delta = abs((bank_avg - book_avg).days) if (bank_avg and book_avg) else stage.candidate_window_days + 1
                    if (not stage.avg_date_delta_days or avg_delta <= stage.avg_date_delta_days):
                        # All-in is valid - add to combos
                        combos.append([item.dto for item in book_items])
                        log.debug("[FAST] OTM_FAST bank=%s all-in shortcut: n=%s sum=%s diff=%s", bank.id, len(book_items), all_sum, all_diff)
                        # Continue to scoring/recording below
        
        if strategy == "exact" or max_size <= 2:
            # Full enumeration for small groups
            log.debug("[FAST] OTM_FAST bank=%s using exact enumeration max_size=%s g_min=%s", bank.id, max_size, g_min)
            # Start enumeration at g_min, not 1
            for size in range(g_min if g_min else 1, max_size + 1):
                if not feasible[size]:
                    continue  # Skip infeasible sizes
                if self._time_exceeded():
                    return
                for combo in combinations(book_items, size):
                    total = sum((c.amount for c in combo), Decimal("0"))
                    diff = abs(q2(total) - target)
                    if diff > stage.amount_tol:
                        continue
                    combo_dtos = [c.dto for c in combo]
                    log.debug(
                        "[FAST] OTM_FAST bank=%s exact_combo size=%s total=%s diff=%s members=%s",
                        bank.id,
                        size,
                        total,
                        diff,
                        [(d.id, d.amount_base, d.date) for d in combo_dtos],
                    )
                    combos.append(combo_dtos)
        else:
            # Beam search for larger groups
            # Start with 1-book combos, then expand
            log.debug(
                "[FAST] OTM_FAST bank=%s using beam_search max_size=%s beam_width=%s",
                bank.id,
                max_size,
                beam_width,
            )
            beam: List[tuple[Decimal, tuple[int, ...]]] = []
            for idx, item in enumerate(book_items):
                diff = abs(item.amount_q2 - target)
                if diff <= stage.amount_tol:
                    beam.append((item.amount, (idx,)))
                    log.debug(
                        "[FAST] OTM_FAST bank=%s beam_seed idx=%s amount=%s diff=%s book_id=%s",
                        bank.id,
                        idx,
                        item.amount,
                        diff,
                        item.dto.id,
                    )
            # Record any single-book hits immediately
            recorded_state_keys: set[tuple[int, ...]] = set()
            initial_hits = [
                state for state in beam if abs(q2(state[0]) - target) <= stage.amount_tol
            ]
            if initial_hits:
                recorded_state_keys = {state[1] for state in initial_hits}
                combos_from_hits = [[book_items[i].dto for i in state[1]] for state in initial_hits]
                combos.extend(combos_from_hits)
                for combo_dtos in combos_from_hits:
                    log.debug(
                        "[FAST] OTM_FAST bank=%s beam_hit total=%s members=%s",
                        bank.id,
                        sum((dto.amount_base for dto in combo_dtos), Decimal("0")),
                        [(d.id, d.amount_base, d.date) for d in combo_dtos],
                    )
            if max_size <= 1:
                log.debug("[FAST] OTM_FAST bank=%s max_size<=1 skipping beam expansion", bank.id)
            else:
                # Expand beam
                for depth in range(2, max_size + 1):
                    if self._time_exceeded():
                        return
                    next_beam: List[tuple[Decimal, tuple[int, ...]]] = []
                    for partial_sum, idxs in beam:
                        for idx, item in enumerate(book_items):
                            if idx in idxs:
                                continue
                            new_total = partial_sum + item.amount
                            diff = abs(q2(new_total) - target)
                            if diff <= stage.amount_tol:
                                next_idxs = idxs + (idx,)
                                next_beam.append((new_total, next_idxs))
                                log.debug(
                                    "[FAST] OTM_FAST bank=%s beam_extend depth=%s total=%s diff=%s members=%s",
                                    bank.id,
                                    depth,
                                    new_total,
                                    diff,
                                    [(book_items[i].dto.id, book_items[i].amount, book_items[i].dto.date) for i in next_idxs],
                                )
                    # Score partial combos by amount difference and trim beam
                    next_beam.sort(key=lambda state: abs(q2(state[0]) - target))
                    beam = next_beam[:beam_width]
            combos_from_beam = [
                [book_items[i].dto for i in state[1]]
                for state in beam
                if state[1] not in recorded_state_keys
            ]
            for combo_dtos in combos_from_beam:
                log.debug(
                    "[FAST] OTM_FAST bank=%s beam_combo total=%s members=%s",
                    bank.id,
                    sum((dto.amount_base for dto in combo_dtos), Decimal("0")),
                    [(d.id, d.amount_base, d.date) for d in combo_dtos],
                )
            combos.extend(combos_from_beam)
            log.debug("[FAST] OTM_FAST bank=%s beam combos=%s", bank.id, len(combos_from_beam))

            # If beam search failed to find anything, fall back to branch-and-bound subset search
            if not combos:
                amounts = [item.amount_q2 for item in book_items]
                bb_indices = branch_and_bound_subset(
                    amounts=amounts,
                    target=target,
                    tolerance=stage.amount_tol,
                    max_size=stage.max_group_size_book,
                )
                if bb_indices:
                    bb_combo = [book_items[i].dto for i in bb_indices]
                    total_bb = sum((b.amount_base for b in bb_combo), Decimal("0"))
                    diff_bb = abs(q2(total_bb) - target)
                    log.debug(
                        "[FAST] OTM_FAST bank=%s branch_and_bound hit total=%s diff=%s members=%s",
                        bank.id,
                        total_bb,
                        diff_bb,
                        [(d.id, d.amount_base, d.date) for d in bb_combo],
                    )
                    combos.append(bb_combo)
        
        log.debug(
            "[FAST] OTM_FAST bank=%s combos_ready=%s detail=%s",
            bank.id,
            len(combos),
            [
                {
                    "book_ids": [b.id for b in combo],
                    "amounts": [b.amount_base for b in combo],
                    "dates": [b.date for b in combo],
                    "total": sum((b.amount_base for b in combo), Decimal("0")),
                    "diff": abs(q2(sum((b.amount_base for b in combo), Decimal("0"))) - target),
                }
                for combo in combos[:5]
            ],
        )
        self._evaluate_and_record_candidates(
            match_type="one_to_many",
            bank=bank,
            combos=combos,
            stage=stage,
            extra_info={"mixed_signs": has_mixed_books, "engine": "beam" if strategy == "beam" else "exact"},
        )
    
    def _run_one_to_many_fast(self, banks, books, stage: StageConfig):
        """
        Improved fast variant for one-to-many matching.
        
        Uses adaptive strategy selection (exact vs beam search) and candidate pruning.
        Now processes banks in parallel using ThreadPoolExecutor.
        """
        # Determine strategy parameters
        strategy_cfg = self._adaptive_select_strategy(banks, books, stage)
        max_local = strategy_cfg.get("max_cands")
        beam_width = strategy_cfg.get("beam_width")
        strategy   = strategy_cfg.get("strategy")
        log.debug(
            "[FAST] OTM_FAST stage=%s strategy=%s max_local=%s beam_width=%s tol=%s mixed=%s threads=%s",
            stage.type,
            strategy,
            max_local,
            beam_width,
            stage.amount_tol,
            stage.allow_mixed_signs,
            self._thread_pool_size,
        )
        
        # Filter out already-used banks (thread-safe check)
        available_banks = []
        with self._used_banks_lock:
            for bank in banks:
                if bank.id not in self.used_banks:
                    available_banks.append(bank)
        
        if not available_banks:
            log.debug("[FAST] OTM_FAST no available banks to process")
            return
        
        # Process banks in parallel
        with ThreadPoolExecutor(max_workers=self._thread_pool_size) as executor:
            futures = {
                executor.submit(
                    self._process_one_bank_otm_fast,
                    bank,
                    books,
                    stage,
                    max_local,
                    beam_width,
                    strategy,
                ): bank.id
                for bank in available_banks
            }
            
            for future in as_completed(futures):
                bank_id = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    log.error("[FAST] OTM_FAST bank=%s processing failed: %s", bank_id, exc, exc_info=True)
                if self._time_exceeded():
                    log.debug("[FAST] OTM_FAST time limit reached, cancelling remaining tasks")
                    break
    
    def _process_one_book_mto_fast(
        self,
        book: JournalEntryDTO,
        banks: List[BankTransactionDTO],
        stage: StageConfig,
        max_local: Optional[int],
        beam_width: Optional[int],
        strategy: str,
    ) -> None:
        """
        Process a single book for many-to-one matching (thread-safe helper).
        """
        # Check if already used (thread-safe check)
        with self._used_books_lock:
            if book.id in self.used_books:
                return
        
        # Pre-select candidate banks for this book
        win = stage.candidate_window_days
        with self._used_banks_lock:
            used_banks_snapshot = self.used_banks.copy()
        local_banks = [
            b for b in banks
            if b.id not in used_banks_snapshot
            and b.company_id == self.company_id
            and b.currency_id == book.currency_id
            and b.date and book.date
            and abs((b.date - book.date).days) <= win
        ]
        if not local_banks:
            log.debug("[FAST] MTO_FAST book=%s no banks in window", book.id)
            return
        
        # Filter by sign if mixed signs not allowed
        book_sign = _sign(book.amount_base or Decimal("0"))
        if not stage.allow_mixed_signs and book_sign != 0:
            before = len(local_banks)
            if book_sign > 0:
                local_banks = [b for b in local_banks if _sign(b.amount_base) >= 0]
            else:
                local_banks = [b for b in local_banks if _sign(b.amount_base) <= 0]
            log.debug(
                "[FAST] MTO_FAST book=%s filtered_by_sign before=%s after=%s book_sign=%s",
                book.id,
                before,
                len(local_banks),
                book_sign,
            )
        
        # Cap local banks if necessary
        if max_local and len(local_banks) > max_local:
            target = q2(book.amount_base or Decimal("0"))
            book_amt = book.amount_base or Decimal("0")
            abs_book_amt = abs(book_amt)
            
            # Date-based grouping optimization for small amounts
            SMALL_AMOUNT_THRESHOLD = Decimal("1000.00")
            USE_DATE_GROUPING = abs_book_amt < SMALL_AMOUNT_THRESHOLD
            
            if USE_DATE_GROUPING and book.date:
                # Group candidates by date proximity: same day, ±1 day, ±2 days, etc.
                target_date = book.date
                grouped_by_date: Dict[int, List[BankTransactionDTO]] = {}
                
                for b in local_banks:
                    if not b.date:
                        continue
                    date_diff = abs((b.date - target_date).days)
                    grouped_by_date.setdefault(date_diff, []).append(b)
                
                # Prioritize same-day matches, then ±1 day, ±2 days, etc.
                result: List[BankTransactionDTO] = []
                
                for date_diff in sorted(grouped_by_date.keys()):
                    same_date_group = grouped_by_date[date_diff]
                    # Within each date group, sort by amount difference
                    same_date_group.sort(key=lambda b: abs(q2(b.amount_base or Decimal("0")) - target))
                    result.extend(same_date_group)
                    
                    # Early exit if we have enough candidates from same/close dates
                    if len(result) >= max_local:
                        break
                
                # If we still need more, fill from remaining groups
                if len(result) < max_local:
                    remaining = [b for b in local_banks if b not in result]
                    remaining.sort(key=lambda b: (
                        abs((b.date - target_date).days) if b.date else 9999,
                        abs(q2(b.amount_base or Decimal("0")) - target)
                    ))
                    result.extend(remaining[:max_local - len(result)])
                
                local_banks = result[:max_local]
                log.debug(
                    "[FAST] MTO_FAST book=%s date_grouped trimmed_candidates to=%s max_local=%s (small_amount=%s)",
                    book.id,
                    len(local_banks),
                    max_local,
                    abs_book_amt < SMALL_AMOUNT_THRESHOLD,
                )
            else:
                def sort_key(b):
                    amt_diff = abs(q2(b.amount_base or Decimal("0")) - target)
                    date_diff = abs((b.date - book.date).days) if b.date and book.date else 9999
                    return (amt_diff, date_diff)
                local_banks = sorted(local_banks, key=sort_key)[:max_local]
                log.debug(
                    "[FAST] MTO_FAST book=%s trimmed_candidates to=%s max_local=%s",
                    book.id,
                    len(local_banks),
                    max_local,
                )
        
        bank_items = _build_fast_items(local_banks)
        bank_signs = [item.sign for item in bank_items]
        has_mixed_banks = (1 in bank_signs and -1 in bank_signs)
        
        combos: List[List[BankTransactionDTO]] = []
        target = q2(book.amount_base or Decimal("0"))
        
        # Path 1: Mixed-sign via DFS
        if has_mixed_banks and not stage.allow_mixed_signs:
            log.debug("[FAST] MTO_FAST book=%s mixed_signs_blocked", book.id)
        if has_mixed_banks and stage.allow_mixed_signs:
            log.debug("[FAST] MTO_FAST book=%s entering mixed-sign DFS path", book.id)
            subset = self._find_mixed_many_to_one_group(book, [item.dto for item in bank_items], stage)
            if subset:
                combos.append(list(subset))
                log.debug("[FAST] MTO_FAST book=%s mixed DFS produced group size=%s", book.id, len(subset))
            else:
                log.debug("[FAST] MTO_FAST book=%s mixed DFS produced no group", book.id)
        
        # Path 2: Same-sign / bounded search
        max_size = min(stage.max_group_size_bank, len(bank_items))
        
        # Feasibility pruning: compute g_min to skip infeasible sizes
        bank_amounts = [item.amount for item in bank_items]
        tol = stage.amount_tol or Decimal("0")
        feasible, g_min = compute_feasibility_bounds(bank_amounts, target, tol, max_size)
        
        if g_min is None:
            # No feasible size exists - skip this book entirely
            log.debug("[FAST] MTO_FAST book=%s no feasible group size (g_min=None)", book.id)
            if combos:
                # Still process mixed-sign results if any
                pass
            else:
                return
        
        # All-in shortcut: if only full group is feasible and it matches exactly
        if g_min == len(bank_items):
            all_sum = sum(bank_amounts)
            all_diff = abs(q2(all_sum) - target)
            if all_diff <= tol:
                # Check date constraints for full group
                bank_dates = [item.dto.date for item in bank_items if item.dto.date]
                bank_span = (max(bank_dates) - min(bank_dates)).days if len(bank_dates) >= 2 else 0
                if (not stage.group_span_days or bank_span <= stage.group_span_days):
                    bank_avg = self._weighted_avg_date([item.dto for item in bank_items])
                    book_avg = book.date
                    avg_delta = abs((bank_avg - book_avg).days) if (bank_avg and book_avg) else win + 1
                    if (not stage.avg_date_delta_days or avg_delta <= stage.avg_date_delta_days):
                        # All-in is valid - add to combos
                        combos.append([item.dto for item in bank_items])
                        log.debug("[FAST] MTO_FAST book=%s all-in shortcut: n=%s sum=%s diff=%s", book.id, len(bank_items), all_sum, all_diff)
                        # Continue to scoring/recording below
        
        if strategy == "exact" or max_size <= 2:
            # Full enumeration
            log.debug("[FAST] MTO_FAST book=%s using exact enumeration max_size=%s g_min=%s", book.id, max_size, g_min)
            # Start enumeration at g_min, not 1
            for size in range(g_min if g_min else 1, max_size + 1):
                if not feasible[size]:
                    continue  # Skip infeasible sizes
                if self._time_exceeded():
                    return
                for combo in combinations(bank_items, size):
                    total = sum((c.amount for c in combo), Decimal("0"))
                    diff = abs(q2(total) - target)
                    if diff > stage.amount_tol:
                        continue
                    combo_dtos = [c.dto for c in combo]
                    log.debug(
                        "[FAST] MTO_FAST book=%s exact_combo size=%s total=%s diff=%s members=%s",
                        book.id,
                        size,
                        total,
                        diff,
                        [(d.id, d.amount_base, d.date) for d in combo_dtos],
                    )
                    combos.append(combo_dtos)
        else:
            # Beam search
            log.debug(
                "[FAST] MTO_FAST book=%s using beam_search max_size=%s beam_width=%s",
                book.id,
                max_size,
                beam_width,
            )
            beam: List[tuple[Decimal, tuple[int, ...]]] = []
            for idx, item in enumerate(bank_items):
                diff = abs(item.amount_q2 - target)
                if diff <= stage.amount_tol:
                    beam.append((item.amount, (idx,)))
                    log.debug(
                        "[FAST] MTO_FAST book=%s beam_seed idx=%s amount=%s diff=%s bank_id=%s",
                        book.id,
                        idx,
                        item.amount,
                        diff,
                        item.dto.id,
                    )
            recorded_state_keys: set[tuple[int, ...]] = set()
            initial_hits = [
                state for state in beam if abs(q2(state[0]) - target) <= stage.amount_tol
            ]
            if initial_hits:
                recorded_state_keys = {state[1] for state in initial_hits}
                combos_from_hits = [[bank_items[i].dto for i in state[1]] for state in initial_hits]
                combos.extend(combos_from_hits)
                for combo_dtos in combos_from_hits:
                    log.debug(
                        "[FAST] MTO_FAST book=%s beam_hit total=%s members=%s",
                        book.id,
                        sum((dto.amount_base for dto in combo_dtos), Decimal("0")),
                        [(d.id, d.amount_base, d.date) for d in combo_dtos],
                    )
            if max_size <= 1:
                log.debug("[FAST] MTO_FAST book=%s max_size<=1 skipping beam expansion", book.id)
            else:
                for depth in range(2, max_size + 1):
                    if self._time_exceeded():
                        return
                    next_beam: List[tuple[Decimal, tuple[int, ...]]] = []
                    for partial_sum, idxs in beam:
                        for idx, item in enumerate(bank_items):
                            if idx in idxs:
                                continue
                            new_total = partial_sum + item.amount
                            diff = abs(q2(new_total) - target)
                            if diff <= stage.amount_tol:
                                next_idxs = idxs + (idx,)
                                next_beam.append((new_total, next_idxs))
                                log.debug(
                                    "[FAST] MTO_FAST book=%s beam_extend depth=%s total=%s diff=%s members=%s",
                                    book.id,
                                    depth,
                                    new_total,
                                    diff,
                                    [(bank_items[i].dto.id, bank_items[i].amount, bank_items[i].dto.date) for i in next_idxs],
                                )
                    next_beam.sort(key=lambda state: abs(q2(state[0]) - target))
                    beam = next_beam[:beam_width]
            combos_from_beam = [
                [bank_items[i].dto for i in state[1]]
                for state in beam
                if state[1] not in recorded_state_keys
            ]
            for combo_dtos in combos_from_beam:
                log.debug(
                    "[FAST] MTO_FAST book=%s beam_combo total=%s members=%s",
                    book.id,
                    sum((dto.amount_base for dto in combo_dtos), Decimal("0")),
                    [(d.id, d.amount_base, d.date) for d in combo_dtos],
                )
            combos.extend(combos_from_beam)
            log.debug("[FAST] MTO_FAST book=%s beam combos=%s", book.id, len(beam))
        
        # Evaluate suggestions
        candidates: List[dict] = []
        rejected_by_date = 0
        rejected_by_coherence = 0
        total_combos = len(combos)
        
        for combo in combos:
            bank_dates = [b.date for b in combo if b.date]
            bank_span = (max(bank_dates) - min(bank_dates)).days if len(bank_dates) >= 2 else 0
            bank_avg_date = self._weighted_avg_date(combo)
            book_avg_date = book.date
            avg_delta = abs((bank_avg_date - book_avg_date).days) if bank_avg_date and book_avg_date else stage.candidate_window_days + 1
            if stage.avg_date_delta_days and avg_delta > stage.avg_date_delta_days:
                rejected_by_date += 1
                continue
            
            # Check intra-group coherence before scoring (lenient mode)
            worst_metrics = _compute_worst_match_metrics(combo, [book])
            is_coherent, reject_reason = _check_intra_group_coherence(
                combo, [book], stage, worst_metrics, strict=False
            )
            if not is_coherent:
                rejected_by_coherence += 1
                log.debug(
                    "[FAST] MTO_FAST book_id=%d combo REJECTED - coherence check failed: %s "
                    "(bank_ids=%s)",
                    book.id, reject_reason, [b.id for b in combo],
                )
                continue
            
            # Calculate actual amount difference
            bank_total = sum((b.amount_base for b in combo), Decimal("0"))
            book_total = book.amount_base or Decimal("0")
            amount_diff = abs(q2(bank_total) - q2(book_total))
            
            sim = self._cosine_similarity(_avg_embedding(combo), book.embedding or [])
            scores = compute_match_scores(
                embed_sim=sim,
                amount_diff=amount_diff,
                amount_tol=stage.amount_tol or CENT,
                date_diff=avg_delta,
                date_tol=stage.avg_date_delta_days or 1,
                currency_match=1.0,
                weights=self.stage_weights,
                worst_metrics=worst_metrics,
            )
            suggestion = self._make_suggestion(
                "many_to_one",
                combo,
                [book],
                scores["global_score"],
                stage=stage,
                weights=self.stage_weights,
                component_scores=scores,
                extra={
                    "bank_span_days_measured": bank_span,
                    "avg_date_delta_days_measured": avg_delta,
                    "mixed_signs": has_mixed_banks,
                    "engine": "beam" if strategy == "beam" else "exact",
                },
            )
            candidates.append(suggestion)
        
        # Log summary of filtering
        if total_combos > 0:
            log.debug(
                "[FAST] MTO_FAST book=%s processed=%d accepted=%d rejected_date=%d rejected_coherence=%d",
                book.id, total_combos, len(candidates), rejected_by_date, rejected_by_coherence
            )
        
        # Sort and record top suggestions
        log.debug(
            "[FAST] MTO_FAST book=%s combos_ready=%s candidates_ready=%s detail=%s",
            book.id,
            len(combos),
            len(candidates),
            [
                {
                    "bank_ids": [b.id for b in combo],
                    "amounts": [b.amount_base for b in combo],
                    "dates": [b.date for b in combo],
                    "total": sum((b.amount_base for b in combo), Decimal("0")),
                    "diff": abs(q2(sum((b.amount_base for b in combo), Decimal("0"))) - target),
                }
                for combo in combos[:5]
            ],
        )
        if not candidates and total_combos > 0:
            log.info(
                "[FAST] MTO_FAST book=%s ALL %d combos rejected (date=%d coherence=%d)",
                book.id, total_combos, rejected_by_date, rejected_by_coherence
            )
        if candidates:
            candidates.sort(key=self._deterministic_sort_key)
            best = candidates[0]
            self._record(best)
            for alt in candidates[1:stage.max_alternatives_per_anchor]:
                with self._lock:
                    self.suggestions.append(alt)
                if self._on_suggestion:
                    try:
                        self._on_suggestion(alt)
                    except Exception as cb_exc:
                        log.warning("on_suggestion callback failed: %s", cb_exc)
    
    def _run_many_to_one_fast(self, banks, books, stage: StageConfig):
        """
        Improved fast variant for many-to-one matching.
        
        Uses adaptive strategy selection, candidate pruning, and optional beam search.
        Now processes books in parallel using ThreadPoolExecutor.
        """
        # Determine strategy parameters
        strategy_cfg = self._adaptive_select_strategy(banks, books, stage)
        max_local = strategy_cfg.get("max_cands")
        beam_width = strategy_cfg.get("beam_width")
        strategy   = strategy_cfg.get("strategy")
        log.debug(
            "[FAST] MTO_FAST stage=%s strategy=%s max_local=%s beam_width=%s tol=%s mixed=%s threads=%s",
            stage.type,
            strategy,
            max_local,
            beam_width,
            stage.amount_tol,
            stage.allow_mixed_signs,
            self._thread_pool_size,
        )
        
        # Filter out already-used books (thread-safe check)
        available_books = []
        with self._used_books_lock:
            for book in books:
                if book.id not in self.used_books:
                    available_books.append(book)
        
        if not available_books:
            log.debug("[FAST] MTO_FAST no available books to process")
            return
        
        # Process books in parallel
        with ThreadPoolExecutor(max_workers=self._thread_pool_size) as executor:
            futures = {
                executor.submit(
                    self._process_one_book_mto_fast,
                    book,
                    banks,
                    stage,
                    max_local,
                    beam_width,
                    strategy,
                ): book.id
                for book in available_books
            }
            
            for future in as_completed(futures):
                book_id = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    log.error("[FAST] MTO_FAST book=%s processing failed: %s", book_id, exc, exc_info=True)
                if self._time_exceeded():
                    log.debug("[FAST] MTO_FAST time limit reached, cancelling remaining tasks")
                    break
    
    def _run_many_to_many_fast(self, banks, books, stage: StageConfig):
        """
        Improved fast variant for many-to-many matching.
        
        Uses adaptive strategy selection and candidate preselection for both banks and books.
        """
        # Determine global strategy parameters
        strategy_cfg = self._adaptive_select_strategy(banks, books, stage)
        max_local_banks = strategy_cfg.get("max_cands") or 64
        max_local_books = strategy_cfg.get("max_cands") or 64
        beam_width = strategy_cfg.get("beam_width")
        strategy   = strategy_cfg.get("strategy")
        log.debug(
            "[FAST] MTM_FAST stage=%s strategy=%s max_local_banks=%s max_local_books=%s beam_width=%s tol=%s",
            stage.type,
            strategy,
            max_local_banks,
            max_local_books,
            beam_width,
            stage.amount_tol,
        )
        
        # Sort by date for window extraction
        banks_sorted = sorted([b for b in banks if b.company_id == self.company_id], key=lambda b: b.date)
        books_sorted = sorted([e for e in books if e.company_id == self.company_id], key=lambda e: e.date)
        win = stage.candidate_window_days
        
        for anchor_bank in banks_sorted:
            if self._time_exceeded():
                return
            if anchor_bank.id in self.used_banks:
                continue
            
            anchor_amt = anchor_bank.amount_base or Decimal("0")
            anchor_sign = _sign(anchor_amt)
            
            # Extract date windows
            start = anchor_bank.date - timedelta(days=win)
            end   = anchor_bank.date + timedelta(days=win)
            local_banks = [b for b in banks_sorted if start <= b.date <= end]
            local_books = [e for e in books_sorted if start <= e.date <= end]
            log.debug(
                "[FAST] MTM_FAST anchor_bank=%s window_days=%s banks=%s books=%s",
                anchor_bank.id,
                win,
                len(local_banks),
                len(local_books),
            )
            
            # Filter by sign if mixed not allowed
            if not stage.allow_mixed_signs and anchor_sign != 0:
                before_banks = len(local_banks)
                before_books = len(local_books)
                if anchor_sign > 0:
                    local_banks = [b for b in local_banks if _sign(b.amount_base) >= 0]
                    local_books = [e for e in local_books if _sign(e.amount_base) >= 0]
                else:
                    local_banks = [b for b in local_banks if _sign(b.amount_base) <= 0]
                    local_books = [e for e in local_books if _sign(e.amount_base) <= 0]
                log.debug(
                    "[FAST] MTM_FAST anchor_bank=%s sign_filter applied banks:%s->%s books:%s->%s",
                    anchor_bank.id,
                    before_banks,
                    len(local_banks),
                    before_books,
                    len(local_books),
                )
            
            # Cap local banks and books
            if len(local_banks) > max_local_banks:
                target = q2(anchor_amt)
                def sort_key(b):
                    amt_diff = abs(q2(b.amount_base or Decimal("0")) - target)
                    date_diff = abs((b.date - anchor_bank.date).days) if b.date and anchor_bank.date else 9999
                    return (amt_diff, date_diff)
                local_banks = [anchor_bank] + sorted(
                    [b for b in local_banks if b.id != anchor_bank.id],
                    key=sort_key
                )[:max_local_banks - 1]
                log.debug(
                    "[FAST] MTM_FAST anchor_bank=%s trimmed banks to=%s",
                    anchor_bank.id,
                    len(local_banks),
                )
            if len(local_books) > max_local_books:
                target = q2(anchor_amt)
                def sort_key(e):
                    amt_diff = abs(q2(e.amount_base or Decimal("0")) - target)
                    date_diff = abs((e.date - anchor_bank.date).days) if e.date and anchor_bank.date else 9999
                    return (amt_diff, date_diff)
                local_books = sorted(local_books, key=sort_key)[:max_local_books]
                log.debug(
                    "[FAST] MTM_FAST anchor_bank=%s trimmed books to=%s",
                    anchor_bank.id,
                    len(local_books),
                )
            
            # Generate candidate bank groups
            bank_groups = []
            max_bank_size = min(stage.max_group_size_bank, len(local_banks))
            if strategy == "exact" or max_bank_size <= 2:
                for i in range(1, max_bank_size + 1):
                    for combo in combinations(local_banks, i):
                        if anchor_bank.id != min(b.id for b in combo):
                            continue
                        if any(bc.id in self.used_banks for bc in combo):
                            continue
                        bank_groups.append(combo)
                log.debug(
                    "[FAST] MTM_FAST anchor_bank=%s exact bank_groups=%s",
                    anchor_bank.id,
                    len(bank_groups),
                )
            else:
                # Beam search on bank side
                bank_beam = [[anchor_bank]]
                log.debug(
                    "[FAST] MTM_FAST anchor_bank=%s beam bank search max_size=%s beam=%s",
                    anchor_bank.id,
                    max_bank_size,
                    beam_width,
                )
                for depth in range(2, max_bank_size + 1):
                    if self._time_exceeded():
                        return
                    next_beam = []
                    for combo in bank_beam:
                        partial_sum = sum((b.amount_base for b in combo), Decimal("0"))
                        for b in local_banks:
                            if b.id in [x.id for x in combo]:
                                continue
                            new_combo = combo + [b]
                            sum_bank = partial_sum + b.amount_base
                            if abs(q2(sum_bank) - q2(sum_bank)) <= stage.amount_tol:
                                next_beam.append(new_combo)
                    next_beam.sort(key=lambda c: abs(q2(sum((x.amount_base for x in c), Decimal("0"))) - q2(sum((x.amount_base for x in c), Decimal("0")))))
                    bank_beam = next_beam[:beam_width]
                bank_groups.extend(bank_beam)
                log.debug(
                    "[FAST] MTM_FAST anchor_bank=%s beam bank_groups=%s",
                    anchor_bank.id,
                    len(bank_beam),
                )
            
            # Evaluate each bank group with book groups
            for bank_combo in bank_groups:
                if self._time_exceeded():
                    return
                sum_bank = sum((b.amount_base for b in bank_combo), Decimal("0"))
                target   = q2(sum_bank)
                
                # Build book groups
                book_groups = []
                max_book_size = min(stage.max_group_size_book, len(local_books))
                if strategy == "exact" or max_book_size <= 2:
                    for j in range(1, max_book_size + 1):
                        for book_combo in combinations(local_books, j):
                            if any(bk.id in self.used_books for bk in book_combo):
                                continue
                            total_book = sum((e.amount_base for e in book_combo), Decimal("0"))
                            diff = abs(q2(total_book) - target)
                            if diff > stage.amount_tol:
                                continue
                            if any(b.currency_id != e.currency_id for b in bank_combo for e in book_combo):
                                continue
                            book_groups.append(book_combo)
                    log.debug(
                        "[FAST] MTM_FAST anchor_bank=%s bank_combo=%s exact book_groups=%s",
                        anchor_bank.id,
                        [b.id for b in bank_combo],
                        len(book_groups),
                    )
                else:
                    # Beam search on book side
                    book_beam = []
                    log.debug(
                        "[FAST] MTM_FAST anchor_bank=%s bank_combo=%s beam book search max_size=%s beam=%s",
                        anchor_bank.id,
                        [b.id for b in bank_combo],
                        max_book_size,
                        beam_width,
                    )
                    for e in local_books:
                        diff = abs(q2(e.amount_base or Decimal("0")) - target)
                        if diff <= stage.amount_tol:
                            book_beam.append([e])
                    for depth in range(2, max_book_size + 1):
                        if self._time_exceeded():
                            return
                        next_beam = []
                        for combo in book_beam:
                            partial_sum = sum((e.amount_base for e in combo), Decimal("0"))
                            for e in local_books:
                                if e.id in [x.id for x in combo]:
                                    continue
                                new_combo = combo + [e]
                                total_book = partial_sum + e.amount_base
                                diff = abs(q2(total_book) - target)
                                if diff <= stage.amount_tol:
                                    next_beam.append(new_combo)
                        next_beam.sort(key=lambda c: abs(q2(sum((x.amount_base for x in c), Decimal("0"))) - target))
                        book_beam = next_beam[:beam_width]
                    book_groups.extend(book_beam)
                    log.debug(
                        "[FAST] MTM_FAST anchor_bank=%s bank_combo=%s beam book_groups=%s",
                        anchor_bank.id,
                        [b.id for b in bank_combo],
                        len(book_beam),
                    )
                
                # Score and record suggestions
                for book_combo in book_groups:
                    bank_dates = [b.date for b in bank_combo if b.date]
                    book_dates = [e.date for e in book_combo if e.date]
                    bank_span = (max(bank_dates) - min(bank_dates)).days if len(bank_dates) >= 2 else 0
                    book_span = (max(book_dates) - min(book_dates)).days if len(book_dates) >= 2 else 0
                    bank_avg  = self._weighted_avg_date(bank_combo)
                    book_avg  = self._weighted_avg_date(book_combo)
                    avg_delta = abs((bank_avg - book_avg).days) if bank_avg and book_avg else stage.candidate_window_days + 1
                    if stage.avg_date_delta_days and avg_delta > stage.avg_date_delta_days:
                        continue
                    
                    # Check intra-group coherence before scoring
                    # For many-to-many, check coherence of both bank and book groups
                    worst_metrics_bank = _compute_worst_match_metrics(bank_combo, book_combo)
                    worst_metrics_book = _compute_worst_match_metrics(book_combo, bank_combo)
                    # Use the worst of both sides
                    worst_metrics = {
                        "max_date_delta": max(worst_metrics_bank["max_date_delta"], worst_metrics_book["max_date_delta"]),
                        "min_embedding_sim": min(worst_metrics_bank["min_embedding_sim"], worst_metrics_book["min_embedding_sim"]),
                        "max_date_delta_ratio": max(worst_metrics_bank["max_date_delta_ratio"], worst_metrics_book["max_date_delta_ratio"]),
                    }
                    
                    # Check coherence for both groups (lenient mode)
                    is_coherent_bank, reject_reason_bank = _check_intra_group_coherence(
                        bank_combo, book_combo, stage, worst_metrics_bank, strict=False
                    )
                    is_coherent_book, reject_reason_book = _check_intra_group_coherence(
                        book_combo, bank_combo, stage, worst_metrics_book, strict=False
                    )
                    if not is_coherent_bank or not is_coherent_book:
                        log.debug(
                            "[FAST] MTM_FAST anchor_bank=%d combo REJECTED - coherence check failed: bank=%s book=%s "
                            "(bank_ids=%s book_ids=%s)",
                            anchor_bank.id, reject_reason_bank, reject_reason_book,
                            [b.id for b in bank_combo], [e.id for e in book_combo],
                        )
                        continue
                    
                    # Calculate actual amount difference
                    bank_total = sum((b.amount_base for b in bank_combo), Decimal("0"))
                    book_total = sum((e.amount_base for e in book_combo), Decimal("0"))
                    amount_diff = abs(q2(bank_total) - q2(book_total))
                    
                    emb_bank = _avg_embedding(bank_combo)
                    emb_book = _avg_embedding(book_combo)
                    sim = self._cosine_similarity(emb_bank, emb_book)
                    scores = compute_match_scores(
                        embed_sim=sim,
                        amount_diff=amount_diff,
                        amount_tol=stage.amount_tol or CENT,
                        date_diff=avg_delta,
                        date_tol=stage.avg_date_delta_days or 1,
                        currency_match=1.0,
                        weights=self.stage_weights,
                        worst_metrics=worst_metrics,
                    )
                    suggestion = self._make_suggestion(
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
                            "engine": "beam" if strategy == "beam" else "exact",
                        },
                    )
                    self._record(suggestion)
                    log.debug(
                        "[FAST] MTM_FAST anchor_bank=%s recorded bank_combo=%s book_combo=%s score=%s",
                        anchor_bank.id,
                        [b.id for b in bank_combo],
                        [e.id for e in book_combo],
                        scores["global_score"],
                    )
                    # Only keep the best N per anchor
                    if len(self.suggestions) >= self.config.max_suggestions:
                        return

# ----------------------------------------------------------------------
#  Advanced matching strategies
#
#  The following utility functions implement additional strategies for
#  matching sets of transactions.  They are not currently wired into
#  the default pipeline, but provide building blocks for future
#  enhancements such as branch‑and‑bound search, beam search, vector
#  embedding based pre‑selection and parallel execution.  These
#  functions operate on simple Python types (lists of Decimal amounts
#  and DTO objects) and return either combinations of indices or sets
#  of candidate JournalEntryDTOs to be considered by higher level
#  matching logic.

from concurrent.futures import ThreadPoolExecutor, as_completed
import heapq
import itertools


def branch_and_bound_subset(amounts: List[Decimal], target: Decimal, tolerance: Decimal = Decimal("0.00"),
                            max_size: Optional[int] = None) -> Optional[List[int]]:
    """
    Find a subset of `amounts` whose sum is within +/- `tolerance` of `target` using a
    depth‑first branch‑and‑bound search.  The function returns a list of indices
    into the original `amounts` list or None if no valid combination is found.

    Parameters
    ----------
    amounts: List[Decimal]
        A list of Decimal amounts.  Negative values are allowed.
    target: Decimal
        The target sum that the selected subset should approximate.
    tolerance: Decimal
        The allowed absolute difference between the subset sum and the target.  A
        zero tolerance means exact matching.
    max_size: Optional[int]
        Maximum number of elements allowed in the subset.  If None, no limit is
        enforced.  This can be used to limit the depth of the search to keep
        combinatorial explosion in check.

    Returns
    -------
    Optional[List[int]]
        A list of indices of amounts that sum to within tolerance of the target,
        or None if no such subset exists.
    """
    n = len(amounts)
    if n == 0:
        return None

    # Normalize inputs
    amounts = [Decimal(x) for x in amounts]
    target = Decimal(target)
    tol = Decimal(tolerance) if tolerance is not None else Decimal("0")

    # Sort indices by absolute value descending to improve pruning.  We need to
    # track original indices to reconstruct the subset later.
    indexed = list(enumerate(amounts))
    indexed.sort(key=lambda x: abs(x[1]), reverse=True)
    sorted_indices, sorted_amounts = zip(*indexed)

    # Precompute remaining min/max sums from each position.  For each i,
    # rem_min[i] is the sum of all negative numbers from i onward, and
    # rem_max[i] is the sum of all positive numbers from i onward.  These
    # bounds allow us to prune branches that cannot reach the target ± tol.
    rem_min = [Decimal("0")] * (n + 1)
    rem_max = [Decimal("0")] * (n + 1)
    for i in range(n - 1, -1, -1):
        amt = sorted_amounts[i]
        if amt >= 0:
            rem_max[i] = rem_max[i + 1] + amt
            rem_min[i] = rem_min[i + 1]
        else:
            rem_min[i] = rem_min[i + 1] + amt
            rem_max[i] = rem_max[i + 1]

    result: Optional[List[int]] = None

    def dfs(idx: int, chosen: List[int], current_sum: Decimal):
        nonlocal result
        if result is not None:
            return
        # If we exceeded the optional group size, stop exploring
        if max_size is not None and len(chosen) > max_size:
            return
        # If we've considered all items, check if the sum is within tolerance
        if idx == n:
            if chosen and (target - tol) <= current_sum <= (target + tol):
                result = chosen.copy()
            return
        # Calculate bounds on the sum reachable with remaining items
        # The best we can do is current_sum + rem_min[idx] (if all remaining are negative)
        # or current_sum + rem_max[idx] (if all remaining are positive)
        min_possible = current_sum + rem_min[idx]
        max_possible = current_sum + rem_max[idx]
        # If the interval [min_possible, max_possible] does not intersect [target - tol, target + tol]
        # then prune this branch
        if max_possible < (target - tol) or min_possible > (target + tol):
            return
        # Branch 1: skip current item
        dfs(idx + 1, chosen, current_sum)
        if result is not None:
            return
        # Branch 2: include current item
        dfs(idx + 1, chosen + [idx], current_sum + sorted_amounts[idx])

    dfs(0, [], Decimal("0"))
    if result is None:
        return None
    # Translate sorted indices back to original indices
    return [sorted_indices[i] for i in result]


def beam_search_subsets(amounts: List[Decimal], target: Decimal, tolerance: Decimal = Decimal("0.00"),
                        beam_width: int = 5, max_size: Optional[int] = None) -> Optional[List[int]]:
    """
    Heuristic beam search for subset sum.  Maintains only the top `beam_width` partial
    combinations at each depth, scoring them by absolute difference to the target.
    Returns indices of a subset that sums within tolerance of the target, or None.

    Parameters
    ----------
    amounts: List[Decimal]
        Candidate amounts to choose from.
    target: Decimal
        The desired total.
    tolerance: Decimal
        Allowed deviation from the target.
    beam_width: int
        How many partial solutions to keep at each depth.
    max_size: Optional[int]
        Maximum size of subsets considered.  If None, no size limit.

    Returns
    -------
    Optional[List[int]]
        Indices of selected items, or None if not found.
    """
    n = len(amounts)
    if n == 0:
        return None
    amounts = [Decimal(x) for x in amounts]
    target = Decimal(target)
    tol = Decimal(tolerance)
    # Each entry in the beam is (score, current_sum, chosen_indices, next_index)
    # where score is heuristic (abs difference to target).
    initial_state = (abs(target), Decimal("0"), [], 0)
    beam: List[tuple] = [initial_state]
    while beam:
        new_beam: List[tuple] = []
        for score, current_sum, chosen, next_idx in beam:
            if current_sum >= (target - tol) and current_sum <= (target + tol) and chosen:
                return chosen
            if next_idx >= n:
                continue
            # Option 1: skip the next item
            new_beam.append((abs(current_sum - target), current_sum, chosen, next_idx + 1))
            # Option 2: take the next item (if size limit permits)
            if max_size is None or len(chosen) < max_size:
                new_sum = current_sum + amounts[next_idx]
                new_score = abs(new_sum - target)
                new_beam.append((new_score, new_sum, chosen + [next_idx], next_idx + 1))
        # Keep only the top beam_width states by smallest score (closest to target)
        if not new_beam:
            break
        new_beam.sort(key=lambda x: x[0])
        beam = new_beam[:beam_width]
    return None


def preselect_candidates_by_embedding(
    bank: BankTransactionDTO,
    books: List[JournalEntryDTO],
    top_k: int = 10,
    generic_terms: Optional[Iterable[str]] = None,
    similarity_threshold: float = 0.3,
) -> List[JournalEntryDTO]:
    """
    Pre‑select candidate JournalEntryDTOs for a given bank transaction by comparing
    embedding similarity and filtering out obviously unrelated entries.

    Parameters
    ----------
    bank: BankTransactionDTO
        The transaction to match against.
    books: List[JournalEntryDTO]
        All available journal entries.
    top_k: int
        Maximum number of book entries to return based on embedding similarity.
    generic_terms: Optional[Iterable[str]]
        List of generic keywords that indicate a bank description is too broad
        (e.g. 'boleto', 'transferência').  If the bank description contains
        any of these, this function returns all books within the same date
        window instead of filtering by embedding similarity.
    similarity_threshold: float
        Minimum cosine similarity required to consider a book entry as a
        candidate.  If fewer than top_k exceed the threshold, the top
        candidates by similarity are returned regardless.

    Returns
    -------
    List[JournalEntryDTO]
        A list of journal entries likely to match the bank transaction.
    """
    # If there is no embedding or the description is too generic, return all
    # books for this bank (to be filtered later by other criteria).
    if not bank.embedding:
        return books[:]
    desc_lower = (bank.description or "").lower()
    if generic_terms:
        for term in generic_terms:
            if term.lower() in desc_lower:
                return books[:]
    # Compute similarity for each book
    scored: List[tuple] = []
    for b in books:
        if not b.embedding:
            continue
        # Use the cosine similarity method defined on the engine for consistency
        sim = 0.0
        try:
            # Approximate dot product and norms manually
            dot = sum(float(x) * float(y) for x, y in zip(bank.embedding, b.embedding))
            norm_bank = sum(float(x) * float(x) for x in bank.embedding) ** 0.5
            norm_book = sum(float(y) * float(y) for y in b.embedding) ** 0.5
            if norm_bank and norm_book:
                sim = dot / (norm_bank * norm_book)
        except Exception:
            sim = 0.0
        if sim >= similarity_threshold:
            scored.append((sim, b))
    # If we found enough above threshold, return the top_k by similarity
    if len(scored) >= top_k:
        scored.sort(key=lambda x: x[0], reverse=True)
        return [b for _, b in scored[:top_k]]
    # Otherwise, return top_k by similarity regardless of threshold
    # including those below threshold to ensure we always have candidates
    scored.sort(key=lambda x: x[0], reverse=True)
    return [b for _, b in scored[:top_k]]


def subset_sum_candidates(
    bank: BankTransactionDTO,
    books: List[JournalEntryDTO],
    stage: StageConfig,
    method: str = "branch",
    beam_width: int = 5,
) -> List[JournalEntryDTO]:
    """
    Given a single bank transaction and a list of candidate journal entries,
    attempt to find a subset of books whose sums match the bank amount within
    tolerance using one of the available subset algorithms.

    This utility wraps the lower level branch‑and‑bound and beam search
    functions, translating from DTOs into amounts and back again.

    Parameters
    ----------
    bank: BankTransactionDTO
        The bank transaction to match.
    books: List[JournalEntryDTO]
        Candidate journal entries (already filtered by date, currency, etc.).
    stage: StageConfig
        Provides the amount tolerance and max_group_size_book for this stage.
    method: str
        Either 'branch' or 'beam' to select the underlying search algorithm.
    beam_width: int
        Beam width to use if method == 'beam'.

    Returns
    -------
    List[JournalEntryDTO]
        A list of journal entries forming a valid group if found, otherwise empty.
    """
    amounts = [b.amount_base or Decimal("0") for b in books]
    target = q2(bank.amount_base)
    tol = stage.amount_tol or Decimal("0")
    max_size = stage.max_group_size_book
    idxs: Optional[List[int]] = None
    if method == "beam":
        idxs = beam_search_subsets(amounts, target, tol, beam_width=beam_width, max_size=max_size)
    else:
        # Default to branch‑and‑bound
        idxs = branch_and_bound_subset(amounts, target, tolerance=tol, max_size=max_size)
    if idxs is None:
        return []
    return [books[i] for i in idxs]


def match_in_parallel(
    banks: List[BankTransactionDTO],
    books: List[JournalEntryDTO],
    stage: StageConfig,
    worker_fn: Callable[[BankTransactionDTO, List[JournalEntryDTO], StageConfig], List[JournalEntryDTO]],
    max_workers: int = 4,
) -> List[dict]:
    """
    Perform matching of multiple bank transactions against the same set of book entries
    using a worker function in parallel.  Each worker receives a bank transaction
    and should return a list of JournalEntryDTOs forming a potential match.  The
    function collects suggestions into the unified format used by
    ReconciliationPipelineEngine._make_suggestion (match_type 'parallel').

    Parameters
    ----------
    banks: List[BankTransactionDTO]
        Bank transactions to match.
    books: List[JournalEntryDTO]
        Candidate journal entries (should already be filtered for date/currency).
    stage: StageConfig
        Stage configuration providing tolerances and group limits.
    worker_fn: Callable
        A function taking (bank, books, stage) and returning list[JournalEntryDTO]
        representing a match.  Typically, this will call subset_sum_candidates
        with either branch‑and‑bound or beam search.
    max_workers: int
        Maximum number of concurrent workers.

    Returns
    -------
    List[dict]
        A list of suggestion dictionaries compatible with the Reconciliation
        pipeline.
    """
    suggestions: List[dict] = []
    used_banks: set[int] = set()
    used_books: set[int] = set()
    def task(bank: BankTransactionDTO) -> Optional[dict]:
        # Skip if already matched (another worker may have used it)
        if bank.id in used_banks:
            return None
        # Filter books to those not used yet and matching company/currency
        local_books = [b for b in books if b.id not in used_books and b.company_id == bank.company_id and b.currency_id == bank.currency_id]
        if not local_books:
            return None
        combo = worker_fn(bank, local_books, stage)
        if not combo:
            return None
        # Mark used items
        used_banks.add(bank.id)
        used_books.update([b.id for b in combo])
        # Build suggestion dict
        extra = {
            "parallel": True,
            "worker": worker_fn.__name__
        }
        # Local helper to assemble stats (using small helper function)
        sum_bank = float(q2(bank.amount_base))
        sum_books = float(q2(sum((e.amount_base for e in combo), Decimal("0"))))
        abs_diff = float(abs(sum_bank - sum_books))
        sugg = {
            "match_type": "parallel",
            "bank_ids": [bank.id],
            "journal_entries_ids": [b.id for b in combo],
            "bank_stats": {
                "count": 1,
                "sum_amount": sum_bank,
                "min_date": bank.date.isoformat() if bank.date else None,
                "weighted_avg_date": bank.date.isoformat() if bank.date else None,
                "max_date": bank.date.isoformat() if bank.date else None,
            },
            "book_stats": {
                "count": len(combo),
                "sum_amount": sum_books,
                "min_date": min(b.date for b in combo).isoformat() if combo else None,
                "weighted_avg_date": None,
                "max_date": max(b.date for b in combo).isoformat() if combo else None,
            },
            "bank_lines": f"BANK#{bank.id} | {bank.date.isoformat() if bank.date else 'N/A'} | {q2(bank.amount_base)} | {bank.description}",
            "book_lines": "\n".join([
                f"BOOK#{e.id} | {e.date.isoformat() if e.date else 'N/A'} | {q2(e.amount_base)} | {e.description}"
                for e in combo
            ]),
            "abs_amount_diff": abs_diff,
            "confidence_score": 1.0,
            "confidence_weights": {
                "embedding": 0.0,
                "amount": 1.0,
                "currency": 0.0,
                "date": 0.0,
            },
            "match_parameters": {
                "amount_tolerance": float(stage.amount_tol),
                "max_group_size_bank": 1,
                "max_group_size_book": stage.max_group_size_book,
                "parallel": True,
            },
            "extra": extra,
        }
        return sugg
    # Use ThreadPoolExecutor to process multiple banks concurrently
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_bank = {executor.submit(task, bank): bank for bank in banks}
        for future in as_completed(future_to_bank):
            res = future.result()
            if res:
                suggestions.append(res)
    return suggestions

# ------------------------------------------------------------
# Função adaptativa para selecionar algoritmo/parametrização
# ------------------------------------------------------------

def adaptive_match_candidates(
    bank: BankTransactionDTO,
    books: List[JournalEntryDTO],
    stage: StageConfig,
    *,
    generic_terms: Optional[Iterable[str]] = None,
    top_k_factor: float = 0.5,
    min_top_k: int = 10,
    beam_width_base: int = 5,
    soft_time_limit: Optional[float] = None,
    verbose: bool = False,
) -> List[JournalEntryDTO]:
    """
    Escolhe dinamicamente o algoritmo e parâmetros de matching mais adequados
    para um banco e um conjunto de livros, com base na quantidade de candidatos,
    tamanho máximo do grupo e qualidade da descrição.

    Heurísticas usadas:
      * Se o conjunto de candidatos é pequeno (≤15) ou o grupo máximo é ≤2,
        usa branch-and-bound com busca exata.
      * Para conjuntos médios (≤50) e grupos até 3, ainda usa branch-and-bound,
        mas aplica pré-selecção por embeddings se a descrição for informativa.
      * Para conjuntos grandes (>50) ou grupos ≥4, usa beam search
        com feixe ajustado ao número de candidatos.
      * Se a descrição contém termos genéricos (e.g. 'boleto'), ignora embeddings.
      * Se há soft_time_limit e muitos candidatos, prefere beam search.
    Parâmetros:
      bank: lançamento bancário para conciliar.
      books: lista de JournalEntryDTO filtrados por data/moeda/empresa.
      stage: StageConfig com tolerância de valor e tamanho de grupo.
      generic_terms: lista de termos que tornam a descrição genérica.
      top_k_factor: fração de candidatos mantida na pré-selecção (>=0).
      min_top_k: mínimo de candidatos na pré-selecção.
      beam_width_base: base do feixe para beam search (≥1).
      soft_time_limit: limite de tempo (em segundos) para preferir heurística.
      verbose: imprime decisões no log/console (opcional).
    Retorna:
      Lista de JournalEntryDTO que corresponde ao banco, ou [] se nenhum.
    """
    # Se não há livros, retorna vazio
    if not books:
        return []
    n_books = len(books)
    max_group = stage.max_group_size_book

    # Verifica se descrição do banco é genérica
    desc_lower = (bank.description or "").lower()
    generic = False
    if generic_terms:
        for term in generic_terms:
            if term.lower() in desc_lower:
                generic = True
                break

    # Aplica pré-selecção por embeddings se não genérica e houver embedding
    candidates: List[JournalEntryDTO] = books
    if not generic and bank.embedding and n_books > min_top_k:
        top_k = max(min_top_k, int(n_books * top_k_factor))
        candidates = preselect_candidates_by_embedding(
            bank,
            books,
            top_k=top_k,
            generic_terms=generic_terms,
        )
        if verbose:
            log.debug(f"Pré-selecionados {len(candidates)} de {n_books} livros para banco {bank.id}")

    n_candidates = len(candidates)

    # Decide o método de busca (branch ou beam)
    method = "branch"
    beam_width = beam_width_base

    # Grandes conjuntos ou grupos grandes => beam
    if (max_group or 0) >= 4 or n_candidates > 50:
        method = "beam"
    elif n_candidates > 30 and (max_group or 0) >= 3:
        method = "beam"
    # Limite de tempo => beam search se muitos candidatos
    if soft_time_limit is not None and n_candidates > 20:
        method = "beam"

    # Ajusta largura do feixe
    if method == "beam":
        beam_width = max(beam_width_base, n_candidates // 10 + 1)
        if verbose:
            log.debug(f"Usando beam search (beam_width={beam_width}) para banco {bank.id}")
    else:
        if verbose:
            log.debug(f"Usando branch-and-bound para banco {bank.id}")

    # Executa a procura de subconjunto com o método escolhido
    match = subset_sum_candidates(bank, candidates, stage, method=method, beam_width=beam_width)
    return match or []


# ----------------------------------------------------------------------
# Helper functions to run a single config or a pipeline
# ----------------------------------------------------------------------
def run_single_config(cfg: object,
                      banks: List[BankTransactionDTO],
                      books: List[JournalEntryDTO],
                      company_id: int,
                      on_suggestion: Optional[Callable[[dict], None]] = None,
                      fast: bool = False,
                      ) -> List[dict]:
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

    log.info(
        "[%s] run_single_config: creating PipelineConfig with fast=%s cfg_id=%s stage_type=%s",
        "FAST" if fast else "REGULAR", fast, getattr(cfg, "id", None), stage_type,
    )
    pipe_cfg = PipelineConfig(
        stages=[stage],
        auto_apply_score=float(getattr(cfg, "min_confidence", 1.0)),
        max_suggestions=getattr(cfg, "max_suggestions", 10000),
        max_runtime_seconds=max_runtime,   # <-- use None when soft_limit is 0 or invalid
        fast=fast,
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


def run_pipeline(
    pipeline: object,
    banks: List[BankTransactionDTO],
    books: List[JournalEntryDTO],
    on_suggestion: Optional[Callable[[dict], None]] = None,
    fast: bool = False,
) -> List[dict]:
    """
    Execute a multi-stage pipeline.
    """
    stage_configs: list[StageConfig] = []
    weight_list: list[dict[str, float]] = []

    log.debug(
        "run_pipeline: pipeline_id=%s company_id=%s stages_db=%d "
        "auto_apply_score=%s max_suggestions=%s fast=%s",
        getattr(pipeline, "id", None),
        pipeline.company_id,
        pipeline.stages.count() if hasattr(pipeline.stages, "count") else None,
        getattr(pipeline, "auto_apply_score", None),
        getattr(pipeline, "max_suggestions", None),
        fast,
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
        fast=fast,
    )

    log.debug(
        "run_pipeline: built %d StageConfig(s); soft_time_limit=%s fast=%s",
        len(stage_configs), soft_limit, fast,
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
        
        log.info(
            "match_many_to_many: building candidate sets company_id=%s "
            "bank_ids_provided=%d book_ids_provided=%d",
            company_id, len(bank_ids) if bank_ids else 0, len(book_ids) if book_ids else 0,
        )
        
        bank_qs = (
            BankTransaction.objects
            .exclude(reconciliations__status__in=["matched", "approved"])
            .filter(company_id=company_id)
            .only("id", "company_id", "date", "amount", "currency_id", "description", "description_embedding")
        )
        bank_count_initial = bank_qs.count()
        log.info(
            "match_many_to_many: initial unmatched bank transactions (company_id=%s): %d",
            company_id, bank_count_initial,
        )
        
        if bank_ids:
            bank_qs = bank_qs.filter(id__in=bank_ids)
            filtered_count = bank_qs.count()
            log.info(
                "match_many_to_many: filtered bank transactions by provided IDs (%d ids) "
                "for company_id=%s: %d records remain",
                len(bank_ids),
                company_id,
                filtered_count,
            )
        else:
            log.info(
                "match_many_to_many: no bank_ids provided; using all unmatched bank transactions "
                "for company_id=%s (%d records)",
                company_id,
                bank_count_initial,
            )
        
        book_qs = (
            JournalEntry.objects
            .exclude(reconciliations__status__in=["matched", "approved"])
            .filter(company_id=company_id)
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
        
        # ------------------------------------------------------------------
        # Convert querysets to DTOs, EXCLUINDO amount == 0
        # ------------------------------------------------------------------
        log.info("match_many_to_many: converting bank transactions to DTOs...")
        candidate_bank: List[BankTransactionDTO] = []
        skipped_zero_bank = 0
        skipped_no_embedding = 0

        for tx in bank_qs:
            amt = tx.amount or Decimal("0")
            # usamos q2 para garantir consistência com o resto do engine
            if q2(amt) == Decimal("0.00"):
                skipped_zero_bank += 1
                log.debug(
                    "match_many_to_many: skipping bank tx_id=%d (zero amount: %s)",
                    tx.id, amt,
                )
                continue

            embedding = _as_vec_list(getattr(tx, "description_embedding", None))
            if not embedding:
                skipped_no_embedding += 1

            candidate_bank.append(
                BankTransactionDTO(
                    id=tx.id,
                    company_id=tx.company_id,
                    date=tx.date,
                    amount=amt,
                    currency_id=tx.currency_id,
                    description=tx.description,
                    embedding=embedding,
                )
            )

        log.info(
            "match_many_to_many: created %d BankTransactionDTOs "
            "(skipped %d with zero amount, %d without embedding)",
            len(candidate_bank), skipped_zero_bank, skipped_no_embedding,
        )
        for dto in candidate_bank[:5]:
            log.info(
                "match_many_to_many: BankDTO sample: id=%s amount=%s date=%s "
                "currency_id=%s company_id=%s has_embedding=%s",
                dto.id, dto.amount, dto.date, dto.currency_id, dto.company_id,
                bool(dto.embedding),
            )
        
        log.info("match_many_to_many: converting journal entries to DTOs...")
        candidate_book: List[JournalEntryDTO] = []
        skipped_zero_book = 0
        skipped_no_embedding = 0

        for je in book_qs:
            tr = getattr(je, "transaction", None)
            tr_date = je.date or (tr.date if tr else None)
            tr_curr_id = tr.currency_id if tr else None
            tr_desc = tr.description if tr else ""
            tr_vec = _as_vec_list(getattr(tr, "description_embedding", None)) if tr else None

            eff_amt = je.get_effective_amount()
            if eff_amt is None:
                # sem valor efetivo → não tentamos conciliar agora
                skipped_zero_book += 1
                log.debug(
                    "match_many_to_many: skipping journal entry_id=%d (no effective amount)",
                    je.id,
                )
                continue
            if q2(eff_amt) == Decimal("0.00"):
                # valor efetivo 0 → fora desta etapa de conciliação
                skipped_zero_book += 1
                log.debug(
                    "match_many_to_many: skipping journal entry_id=%d (zero effective amount: %s)",
                    je.id, eff_amt,
                )
                continue
        
            if not tr_vec:
                skipped_no_embedding += 1

            candidate_book.append(
                JournalEntryDTO(
                    id=je.id,
                    company_id=je.company_id,
                    transaction_id=je.transaction_id,
                    date=tr_date,
                    effective_amount=eff_amt,
                    currency_id=tr_curr_id,
                    description=tr_desc,
                    embedding=tr_vec,
                )
            )
        
        log.info(
            "match_many_to_many: created %d JournalEntryDTOs "
            "(skipped %d with zero/no effective_amount, %d without embedding)",
            len(candidate_book), skipped_zero_book, skipped_no_embedding,
        )
        for dto in candidate_book[:5]:
            log.info(
                "match_many_to_many: BookDTO sample: id=%s tx_id=%s amount=%s date=%s "
                "currency_id=%s company_id=%s has_embedding=%s",
                dto.id, dto.transaction_id, dto.effective_amount,
                dto.date, dto.currency_id, dto.company_id, bool(dto.embedding),
            )
        
        use_fast = bool(data.get("fast", False))
        
        log.info(
            "match_many_to_many: starting matching engine "
            "config_id=%s pipeline_id=%s fast=%s banks=%d books=%d",
            config_id, pipeline_id, use_fast, len(candidate_bank), len(candidate_book),
        )
        
        # Run the appropriate matching engine and capture soft limit
        soft_time_limit = None
        matching_start = monotonic()
        if pipeline_id:
            log.info(
                "match_many_to_many: using pipeline_id=%s fast=%s",
                pipeline_id, use_fast,
            )
            pipe_obj = ReconciliationPipeline.objects.get(id=pipeline_id)
            suggestions = run_pipeline(
                pipe_obj,
                candidate_bank,
                candidate_book,
                on_suggestion=on_suggestion,
                fast=use_fast,
            )
            soft_time_limit = getattr(pipe_obj, "soft_time_limit_seconds", None)
        else:
            log.info(
                "match_many_to_many: using config_id=%s fast=%s",
                config_id, use_fast,
            )
            cfg_obj = ReconciliationConfig.objects.get(id=config_id)
            suggestions = run_single_config(
                cfg_obj,
                candidate_bank,
                candidate_book,
                company_id,
                on_suggestion=on_suggestion,
                fast=use_fast,
            )
            soft_time_limit = getattr(cfg_obj, "soft_time_limit_seconds", None)
        
        matching_duration = monotonic() - matching_start
        log.info(
            "match_many_to_many: matching engine completed in %.3fs - suggestions=%d",
            matching_duration, len(suggestions),
        )

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
            "Recon task: company=%s config_id=%s pipeline_id=%s banks=%d books=%d suggestions=%d duration=%.3fs (skipped_zero_bank=%d, skipped_zero_book=%d)",
            company_id, config_id, pipeline_id,
            bank_candidate_count, book_candidate_count,
            suggestion_count, duration,
            skipped_zero_bank, skipped_zero_book,
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

            # Check for preexisting matches (idempotency guard)
            # First check: any bank or book already matched
            if BankTransaction.objects.filter(
                id__in=bank_ids, reconciliations__status__in=["matched", "approved"]
            ).exists() or JournalEntry.objects.filter(
                id__in=book_ids, reconciliations__status__in=["matched", "approved"]
            ).exists():
                skipped += 1
                details.append({"reason": "already_matched", "suggestion": s})
                log.debug("Skipping auto-match suggestion because already matched/approved in DB: %s", s)
                continue
            
            # Second check: exact duplicate - same bank_ids + journal_ids combination already exists
            # This prevents creating duplicate reconciliations on reruns
            bank_ids_set = set(bank_ids)
            book_ids_set = set(book_ids)
            existing_recon = Reconciliation.objects.filter(
                bank_transactions__id__in=bank_ids
            ).prefetch_related('bank_transactions', 'journal_entries').first()
            
            if existing_recon:
                # Check if this reconciliation has the exact same bank and journal IDs
                existing_bank_ids = {bt.id for bt in existing_recon.bank_transactions.all()}
                existing_book_ids = {je.id for je in existing_recon.journal_entries.all()}
                if existing_bank_ids == bank_ids_set and existing_book_ids == book_ids_set:
                    skipped += 1
                    details.append({"reason": "exact_duplicate", "suggestion": s, "existing_recon_id": existing_recon.id})
                    log.debug(
                        "Skipping auto-match suggestion: exact duplicate of reconciliation id=%s (banks=%s, journals=%s)",
                        existing_recon.id, bank_ids, book_ids
                    )
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

            # Build notes metadata for automatic reconciliation
            from multitenancy.utils import build_notes_metadata
            
            reconciliation_notes = build_notes_metadata(
                source='Reconciliation',
                function='ReconciliationService._apply_auto_matches_100',
                reconciliation_type='automatic',
                auto_match_confidence='100%',
                bank_ids=', '.join(str(bid) for bid in bank_ids),
                journal_ids=', '.join(str(jid) for jid in book_ids),
            )

            recon = Reconciliation.objects.create(
                status=status_value,
                company_id=company_id,
                notes=reconciliation_notes,
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