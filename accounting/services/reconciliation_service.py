"""
embedding_service.py

This module provides the core logic for running reconciliation with
user‑calibratable weights on embedding similarity, amount, currency and
date.  It does not define any Django models; instead, it uses simple
data classes (DTOs) to carry data into a configurable matching engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from itertools import combinations
from typing import Callable, Dict, Iterable, List, Optional
from multitenancy.utils import resolve_tenant
#from .embedding_service import BankTransactionDTO, JournalEntryDTO, run_single_config, run_pipeline


# accounting/services/reconciliation_service.py


from typing import Dict, List, Optional

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
    date_tol: int = 0
    # optional weight overrides (None → inherit from config or default)
    embedding_weight: float | None = None
    amount_weight: float | None = None
    currency_weight: float | None = None
    date_weight: float | None = None


@dataclass
class PipelineConfig:
    stages: List[StageConfig] = field(default_factory=list)
    auto_apply_score: float = 1.0
    max_suggestions: int = 1000


# ----------------------------------------------------------------------
#  Utility functions
# ----------------------------------------------------------------------
CENT = Decimal("0.01")

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


def compute_weighted_confidence(
    embed_sim: float,
    amount_diff: Decimal,
    amount_tol: Decimal,
    date_diff: int,
    date_tol: int,
    currency_match: float,
    weights: Dict[str, float],
) -> float:
    """
    Calculate a composite confidence score using user-defined weights.
    Weights should sum to 1.0.  The components are:
    - embed_sim: similarity of text embeddings (0–1)
    - amount_diff: absolute difference between amounts (Decimal)
    - date_diff: absolute difference between dates (int days)
    - currency_match: 1.0 if currencies match else 0.0
    The amount and date differences are normalised by their tolerances.
    """
    amt_score = max(0.0, 1 - float(amount_diff / (amount_tol or CENT)))
    date_score = max(0.0, 1 - float(date_diff) / float(date_tol or 1))
    return round(
        weights.get("embedding", 0.0) * embed_sim +
        weights.get("amount", 0.0)    * amt_score +
        weights.get("currency", 0.0)  * currency_match +
        weights.get("date", 0.0)      * date_score,
        4,
    )

# ----------------------------------------------------------------------
# Reconciliation pipeline engine
# ----------------------------------------------------------------------
class ReconciliationPipelineEngine:
    """
    Executes a sequence of matching stages on in-memory DTOs.  Supports exact,
    fuzzy, one-to-many, many-to-one and many-to-many matching with asymmetric
    group sizes and weighted confidence scoring.
    """
    def __init__(self, company_id: int, config: PipelineConfig):
        self.company_id = company_id
        self.config = config
        self.suggestions: List[dict] = []
        self.used_banks: set[int] = set()
        self.used_books: set[int] = set()
        # Per-stage or global weights; set externally before calling run()
        self.current_weights: Dict[str, float] | List[Dict[str, float]] = {
            "embedding": 0.50,
            "amount":    0.35,
            "currency":  0.10,
            "date":      0.05,
        }

    def run(self, banks: List[BankTransactionDTO], books: List[JournalEntryDTO]) -> List[dict]:
        """Execute each enabled stage and return suggestions up to the configured limit."""
        
        log.debug("Executing reconciliation pipeline: %d stages to run, up to %d suggestions", 
          len(self.config.stages), self.config.max_suggestions)
        
        for idx, stage in enumerate(self.config.stages):
            if not stage.enabled:
                log.debug("Skipping stage %d (%s): disabled", idx, stage.type)
                continue
            if isinstance(self.current_weights, list):
                self.stage_weights = self.current_weights[idx]
            else:
                self.stage_weights = self.current_weights
            handler = getattr(self, f"_run_{stage.type}", None)
            
            log.debug("Stage %d (%s) started with weights %s and tolerances: amount_tol=%s, date_tol=%d, max_group_size_bank=%d, max_group_size_book=%d, banks=%d, books=%d",
              idx, stage.type, self.stage_weights, stage.amount_tol, stage.date_tol, 
              stage.max_group_size_bank, stage.max_group_size_book,
              len(banks), len(books))
            
            if handler:
                handler(banks, books, stage)
                log.debug("Stage %d (%s) completed: total suggestions so far = %d", 
                          idx, stage.type, len(self.suggestions))
                if len(self.suggestions) >= self.config.max_suggestions:
                    log.debug("Reached max_suggestions (%d); breaking out of pipeline at stage %d", 
                              self.config.max_suggestions, idx)
                    break
        return self.suggestions[: self.config.max_suggestions]

    # Stage handlers
    def _run_exact_1to1(self, banks, books, stage: StageConfig):
        for bank in banks:
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
                if bank.date and book.date and abs((bank.date - book.date).days) > stage.date_tol:
                    continue
                suggestion = self._make_suggestion("exact_1to1", [bank.id], [book.id], 1.0)
                self._record(suggestion)
                break

    def _run_one_to_many(self, banks, books, stage: StageConfig):
        available_books = [b for b in books if b.id not in self.used_books and b.company_id == self.company_id]
        for bank in banks:
            if bank.id in self.used_banks:
                continue
            for size in range(1, stage.max_group_size_book + 1):
                for combo in combinations(available_books, size):
                    total = sum((b.amount_base for b in combo), Decimal("0"))
                    if q2(total) != q2(bank.amount_base):
                        continue
                    if any(b.currency_id != bank.currency_id for b in combo):
                        continue
                    if any(abs((bank.date - b.date).days) > stage.date_tol for b in combo):
                        continue
                    suggestion = self._make_suggestion("one_to_many", [bank.id], [b.id for b in combo], 1.0)
                    self._record(suggestion)
                    return

    def _run_many_to_one(self, banks, books, stage: StageConfig):
        available_banks = [b for b in banks if b.id not in self.used_banks and b.company_id == self.company_id]
        for book in books:
            if book.id in self.used_books:
                continue
            for size in range(1, stage.max_group_size_bank + 1):
                for combo in combinations(available_banks, size):
                    total = sum((b.amount_base for b in combo), Decimal("0"))
                    if q2(total) != q2(book.amount_base):
                        continue
                    if any(b.currency_id != book.currency_id for b in combo):
                        continue
                    if any(abs((b.date - book.date).days) > stage.date_tol for b in combo):
                        continue
                    suggestion = self._make_suggestion("many_to_one", [b.id for b in combo], [book.id], 1.0)
                    self._record(suggestion)
                    return

    def _run_fuzzy_1to1(self, banks, books, stage: StageConfig):
        bin_size = max(1, min(stage.date_tol, 7))
        book_bins = build_date_bins(
            [b for b in books if b.id not in self.used_books],
            get_date=lambda e: e.date,
            bin_size_days=bin_size,
        )
        for bank in banks:
            if bank.id in self.used_banks:
                continue
            candidates = list(iter_date_bin_candidates(bank.date, book_bins, bin_size, stage.date_tol))
            buckets = build_amount_buckets(candidates, get_amount=lambda e: e.amount_base)
            for book in probe_amount_buckets(buckets, bank.amount_base, stage.amount_tol):
                if book.id in self.used_books:
                    continue
                currency_match = 1.0 if bank.currency_id == book.currency_id else 0.0
                d_diff = abs((bank.date - book.date).days) if bank.date and book.date else stage.date_tol + 1
                if d_diff > stage.date_tol:
                    continue
                a_diff = abs(q2(bank.amount_base) - q2(book.amount_base))
                if a_diff > stage.amount_tol:
                    continue
                embed_sim = self._cosine_similarity(bank.embedding or [], book.embedding or [])
                weights = {
                    "embedding": stage.embedding_weight if stage.embedding_weight is not None else self.stage_weights["embedding"],
                    "amount":    stage.amount_weight    if stage.amount_weight    is not None else self.stage_weights["amount"],
                    "currency":  stage.currency_weight  if stage.currency_weight  is not None else self.stage_weights["currency"],
                    "date":      stage.date_weight      if stage.date_weight      is not None else self.stage_weights["date"],
                }
                conf = compute_weighted_confidence(
                    embed_sim, a_diff, stage.amount_tol, d_diff, stage.date_tol, currency_match, weights
                )
                suggestion = self._make_suggestion("fuzzy_1to1", [bank.id], [book.id], conf)
                self._record(suggestion)

    def _run_many_to_many(self, banks, books, stage: StageConfig):
        sorted_banks = [b for b in banks if b.id not in self.used_banks and b.company_id == self.company_id]
        sorted_banks.sort(key=lambda b: b.date)
        sorted_books = [e for e in books if e.id not in self.used_books and e.company_id == self.company_id]
        sorted_books.sort(key=lambda e: e.date)
        
        log.debug("Starting many-to-many reconciliation stage na company %d: %d banks, %d sorted banks, %d books, %d sorted books", self.company_id, len(banks), len(sorted_banks), len(books), len(sorted_books))
    
        for bank in sorted_banks:
            start = bank.date - timedelta(days=stage.date_tol)
            end = bank.date + timedelta(days=stage.date_tol)
            bank_window = [b for b in sorted_banks if start <= b.date <= end]
            book_window = [e for e in sorted_books if start <= e.date <= end]
    
            log.debug("Bank %s: date=%s, amount=%.2f, currency=%s, window banks=%d, window books=%d", 
                      bank.id, bank.date, bank.amount, bank.currency_id, len(bank_window), len(book_window))
    
            for i in range(1, min(stage.max_group_size_bank, len(bank_window)) + 1):
                for bank_combo in combinations(bank_window, i):
                    sum_bank = sum((b.amount_base for b in bank_combo), Decimal("0"))
    
                    for j in range(1, min(stage.max_group_size_book, len(book_window)) + 1):
                        for book_combo in combinations(book_window, j):
                            sum_book = sum((e.amount_base for e in book_combo), Decimal("0"))
    
                            #log.debug("Trying bank combo IDs %s (sum=%.2f) vs book combo IDs %s (sum=%.2f)", 
                            #          [b.id for b in bank_combo], sum_bank, [e.id for e in book_combo], sum_book)
    
                            if q2(sum_bank) != q2(sum_book):
                                #log.debug("Amount mismatch: bank=%.2f, book=%.2f", q2(sum_bank), q2(sum_book))
                                continue
    
                            if any(b.currency_id != e.currency_id for b in bank_combo for e in book_combo):
                                #log.debug("Currency mismatch found in combination; skipping")
                                continue
    
                            all_dates = [b.date for b in bank_combo] + [e.date for e in book_combo]
                            if (max(all_dates) - min(all_dates)).days > stage.date_tol:
                                #log.debug("Date range too wide in combo: min=%s, max=%s, span=%d days", 
                                #          min(all_dates), max(all_dates), (max(all_dates) - min(all_dates)).days)
                                continue
    
                            suggestion = self._make_suggestion(
                                "many_to_many",
                                [b.id for b in bank_combo],
                                [e.id for e in book_combo],
                                1.0,
                            )
                            log.debug("Recording valid suggestion: bank_ids=%s, journal_ids=%s", 
                                      suggestion["bank_ids"], suggestion["journal_entries_ids"])
                            self._record(suggestion)


    # Internal helpers
    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        if not v1 or not v2:
            return 0.0
        from math import sqrt
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = sqrt(sum(a * a for a in v1))
        norm2 = sqrt(sum(b * b for b in v2))
        return dot / (norm1 * norm2) if norm1 and norm2 else 0.0

    def _make_suggestion(self, match_type: str, bank_ids: List[int],
                         book_ids: List[int], conf: float) -> dict:
        return {
            "match_type": match_type,
            "bank_ids": bank_ids,
            "journal_entries_ids": book_ids,
            "confidence_score": float(conf),
        }

    def _record(self, suggestion: dict) -> None:
        """Record a suggestion and mark the participating IDs as used."""
        log.debug("Recording suggestion: type=%s, bank_ids=%s, journal_ids=%s, confidence=%.4f",
              suggestion["match_type"], suggestion["bank_ids"], suggestion["journal_entries_ids"], suggestion["confidence_score"])
        self.suggestions.append(suggestion)
        self.used_banks.update(suggestion["bank_ids"])
        self.used_books.update(suggestion["journal_entries_ids"])


# ----------------------------------------------------------------------
# Helper functions to run a single config or a pipeline
# ----------------------------------------------------------------------
def run_single_config(cfg: object,
                      banks: List[BankTransactionDTO],
                      books: List[JournalEntryDTO],
                      company_id: int) -> List[dict]:
    """
    Execute a single ReconciliationConfig using the pipeline engine.

    The ``cfg`` object should define:
      - strategy
      - amount_tolerance
      - date_tolerance_days
      - max_group_size_bank
      - max_group_size_book
      - embedding_weight, amount_weight, currency_weight, date_weight
      - min_confidence (used as auto_apply_score)
      - max_suggestions

    It must not refer to any legacy strategy or group size field.
    """
    
    
    # determine type for a single-stage config:
    if cfg.max_group_size_bank > 1 or cfg.max_group_size_book > 1:
        stage_type = "many_to_many"
    elif cfg.amount_tolerance > 0 or cfg.date_tolerance_days > 0:
        stage_type = "fuzzy_1to1"
    else:
        stage_type = "exact_1to1"
    
    log.debug("Running single config (ID=%s) for company %s: determined stage_type=%s", 
          getattr(cfg, "id", None), company_id, stage_type)
    
    log.debug("Created %d BankTransactionDTOs", len(banks))
    for dto in banks[:10]:  # limit to first 10 for brevity
        log.debug("BankDTO: id=%s, amount=%s, date=%s, currency_id=%s, company_id=%s",
                  dto.id, dto.amount, dto.date, dto.currency_id, dto.company_id)
    
    log.debug("Created %d JournalEntryDTOs", len(books))
    for dto in books[:10]:  # again, limit to avoid noise
        log.debug("BookDTO: id=%s, tx_id=%s, amount=%s, date=%s, currency_id=%s, company_id=%s",
                  dto.id, dto.transaction_id, dto.effective_amount, dto.date, dto.currency_id, dto.company_id)
    
    stage = StageConfig(
        type=stage_type,
        max_group_size_bank=cfg.max_group_size_bank,
        max_group_size_book=cfg.max_group_size_book,
        amount_tol=cfg.amount_tolerance,
        date_tol=cfg.date_tolerance_days,
    )
    pipe_cfg = PipelineConfig(
        stages=[stage],
        auto_apply_score=float(getattr(cfg, "min_confidence", 1.0)),
        max_suggestions=getattr(cfg, "max_suggestions", 1000),
    )
    engine = ReconciliationPipelineEngine(company_id=company_id, config=pipe_cfg)
    engine.current_weights = {
        "embedding": float(getattr(cfg, "embedding_weight", 0.50)),
        "amount":    float(getattr(cfg, "amount_weight",    0.35)),
        "currency":  float(getattr(cfg, "currency_weight",  0.10)),
        "date":      float(getattr(cfg, "date_weight",      0.05)),
    }
    
    log.debug(
        "Single config weights: embedding=%.2f, amount=%.2f, currency=%.2f, date=%.2f; "
        "tolerances: amount_tol=%s, date_tol=%s; max_group_size_bank=%d, max_group_size_book=%d; "
        "min_confidence=%.2f, max_suggestions=%d",
        engine.current_weights["embedding"], engine.current_weights["amount"], 
        engine.current_weights["currency"], engine.current_weights["date"],
        cfg.amount_tolerance, cfg.date_tolerance_days, cfg.max_group_size_bank, cfg.max_group_size_book,
        float(getattr(cfg, "min_confidence", 0)), getattr(cfg, "max_suggestions", 1000)
    )
    
    # Run and filter by min_confidence
    suggestions = engine.run(banks, books)
    total = len(suggestions)
    min_conf = float(getattr(cfg, "min_confidence", 0))
    if min_conf:
        suggestions = [s for s in suggestions if s["confidence_score"] >= min_conf]
        log.debug("Applied min_confidence=%.2f filter: %d of %d suggestions retained", 
                  min_conf, len(suggestions), total)
    return suggestions

def run_pipeline(pipeline: object,
                 banks: List[BankTransactionDTO],
                 books: List[JournalEntryDTO]) -> List[dict]:
    """
    Execute a multi-stage pipeline.  The ``pipeline`` object must have:
      - company_id
      - auto_apply_score
      - max_suggestions
      - a ``stages`` iterable that yields stage objects with attributes:
          enabled, order, config (with relevant fields), and optional overrides.
    """
    
    log.debug("Running multi-stage pipeline (ID=%s) for company %s: auto_apply_score=%.2f, max_suggestions=%d", 
          getattr(pipeline, "id", None), pipeline.company_id, float(pipeline.auto_apply_score), pipeline.max_suggestions)
    
    stage_configs: List[StageConfig] = []
    weight_list: List[Dict[str, float]] = []
    for stage_obj in pipeline.stages.select_related("config").order_by("order"):
        cfg = stage_obj.config
        if not stage_obj.enabled:
            continue
        
        if cfg.max_group_size_bank > 1 or cfg.max_group_size_book > 1:
            stage_type = "many_to_many"
        elif cfg.amount_tolerance > 0 or cfg.date_tolerance_days > 0:
            stage_type = "fuzzy_1to1"
        else:
            stage_type = "exact_1to1"
            
        log.debug(
            "Configured pipeline stage %d (order %d): type=%s, max_group_size_bank=%d, max_group_size_book=%d, "
            "amount_tol=%s, date_tol=%s, weights=%s",
            len(stage_configs), stage_obj.order, stage_type, stage_configs[-1].max_group_size_bank, 
            stage_configs[-1].max_group_size_book, stage_configs[-1].amount_tol, stage_configs[-1].date_tol, weight_list[-1]
        )
        
        stage_configs.append(StageConfig(
            type=stage_type,
            enabled=True,
            max_group_size_bank=stage_obj.max_group_size_bank or cfg.max_group_size_bank,
            max_group_size_book=stage_obj.max_group_size_book or cfg.max_group_size_book,
            amount_tol=stage_obj.amount_tolerance if stage_obj.amount_tolerance is not None else cfg.amount_tolerance,
            date_tol=stage_obj.date_tolerance_days if stage_obj.date_tolerance_days is not None else cfg.date_tolerance_days,
            embedding_weight=stage_obj.embedding_weight if stage_obj.embedding_weight is not None else float(cfg.embedding_weight),
            amount_weight=stage_obj.amount_weight if stage_obj.amount_weight is not None else float(cfg.amount_weight),
            currency_weight=stage_obj.currency_weight if stage_obj.currency_weight is not None else float(cfg.currency_weight),
            date_weight=stage_obj.date_weight if stage_obj.date_weight is not None else float(cfg.date_weight),
        ))
        weight_list.append({
            "embedding": float(stage_obj.embedding_weight) if stage_obj.embedding_weight is not None else float(cfg.embedding_weight),
            "amount":    float(stage_obj.amount_weight)    if stage_obj.amount_weight    is not None else float(cfg.amount_weight),
            "currency":  float(stage_obj.currency_weight)  if stage_obj.currency_weight  is not None else float(cfg.currency_weight),
            "date":      float(stage_obj.date_weight)      if stage_obj.date_weight      is not None else float(cfg.date_weight),
        })
        
    
    pipe_cfg = PipelineConfig(
        stages=stage_configs,
        auto_apply_score=float(pipeline.auto_apply_score),
        max_suggestions=pipeline.max_suggestions,
    )
    
    log.debug("Pipeline engine initialized with %d enabled stages out of %d configured", 
      len(stage_configs), pipeline.stages.count() if hasattr(pipeline.stages, 'count') else len(stage_configs))
        
    
    engine = ReconciliationPipelineEngine(company_id=pipeline.company_id, config=pipe_cfg)
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
    ) -> Dict[str, object]:
        """
        Execute reconciliation based on a config_id or pipeline_id in `data`.
        It refuses to run if neither is provided.
        """
        config_id = data.get("config_id")
        pipeline_id = data.get("pipeline_id")
        if not (config_id or pipeline_id):
            raise ValueError("Either config_id or pipeline_id must be provided")

        company_id = resolve_tenant(tenant_id).id

        # Build candidate QuerySets
        bank_ids = data.get("bank_ids", [])
        book_ids = data.get("book_ids", [])
        bank_qs = BankTransaction.objects.exclude(
            reconciliations__status__in=["matched", "approved"]
        )
        bank_count_initial = bank_qs.count()
        log.debug("Initial unmatched bank transactions count: %d", bank_count_initial)
        
        if bank_ids:
            bank_qs = bank_qs.filter(id__in=bank_ids)
            filtered_count = bank_qs.count()
            log.debug("Filtered bank transactions by provided IDs (%d ids): %d records remain", 
                      len(bank_ids), filtered_count)
        else:
            log.debug("No bank_ids provided; using all unmatched bank transactions (%d records)", 
                      bank_count_initial)
        
        book_qs = JournalEntry.objects.exclude(
            reconciliations__status__in=["matched", "approved"]
        )
        book_count_initial = book_qs.count()
        log.debug("Initial unmatched journal entries count: %d", book_count_initial)
        if book_ids:
            book_qs = book_qs.filter(id__in=book_ids)
            filtered_book_count = book_qs.count()
            log.debug("Filtered journal entries by provided IDs (%d ids): %d records remain", 
                      len(book_ids), filtered_book_count)
        else:
            log.debug("No book_ids provided; using all unmatched journal entries (%d records)", 
                      book_count_initial)

        # Only consider journal entries that belong to a bank account
        pre_account_count = book_qs.count()
        book_qs = book_qs.filter(account__bank_account__isnull=False)
        post_account_count = book_qs.count()
        log.debug("Filtered journal entries to those linked to bank accounts: %d records remain (from %d)", 
                  post_account_count, pre_account_count)
        
        # Convert querysets to DTOs
        candidate_bank = [
            BankTransactionDTO(
                id=tx.id,
                company_id=tx.company_id,
                date=tx.date,
                amount=tx.amount,
                currency_id=tx.currency_id,
                description=tx.description,
                embedding=list(tx.description_embedding)
                if getattr(tx, "description_embedding", None)
                else None,
            )
            for tx in bank_qs
        ]
        
        log.debug("Created %d BankTransactionDTOs", len(candidate_bank))
        for dto in candidate_bank[:10]:  # limit to first 10 for brevity
            log.debug("BankDTO: id=%s, amount=%s, date=%s, currency_id=%s, company_id=%s",
                      dto.id, dto.amount, dto.date, dto.currency_id, dto.company_id)
        
        candidate_book = [
            JournalEntryDTO(
                id=je.id,
                company_id=je.company_id,
                transaction_id=je.transaction_id,
                date=je.date or (je.transaction.date if je.transaction else None),
                effective_amount=je.get_effective_amount(),
                currency_id=je.transaction.currency_id if je.transaction else None,
                description=je.transaction.description if je.transaction else "",
                embedding=list(je.transaction.description_embedding)
                if getattr(je.transaction, "description_embedding", None)
                else None,
            )
            for je in book_qs
        ]
        
        log.debug("Created %d JournalEntryDTOs", len(candidate_book))
        for dto in candidate_book[:10]:  # again, limit to avoid noise
            log.debug("BookDTO: id=%s, tx_id=%s, amount=%s, date=%s, currency_id=%s, company_id=%s",
                      dto.id, dto.transaction_id, dto.effective_amount, dto.date, dto.currency_id, dto.company_id)

        # Run the appropriate matching engine
        if pipeline_id:
            pipeline = ReconciliationPipeline.objects.get(id=pipeline_id)
            suggestions = run_pipeline(pipeline, candidate_bank, candidate_book)
        else:
            cfg = ReconciliationConfig.objects.get(id=config_id)
            suggestions = run_single_config(cfg, candidate_bank, candidate_book, company_id)

        # Optionally auto-apply matches with confidence 1.0
        auto_info = {"enabled": bool(auto_match_100), "applied": 0, "skipped": 0, "details": []}
        if auto_match_100:
            auto_info = ReconciliationService._apply_auto_matches_100(suggestions)
        
        log.info(
    "Recon task: company=%s config_id=%s pipeline_id=%s banks=%d books=%d suggestions=%d",
    company_id, config_id, pipeline_id, len(candidate_bank), len(candidate_book), len(suggestions)
)
        
        return {"suggestions": suggestions, "auto_match": auto_info}

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