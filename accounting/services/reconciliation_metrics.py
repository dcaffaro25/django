"""
reconciliation_metrics.py

Metrics and instrumentation utilities for reconciliation matching.
Provides dataclasses for collecting per-run, per-stage, and per-anchor metrics,
as well as structured logging and explanation payloads.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Callable

log = logging.getLogger("recon.metrics")


# ----------------------------------------------------------------------
# Metrics Dataclasses
# ----------------------------------------------------------------------

@dataclass
class AnchorMetrics:
    """
    Metrics collected for each anchor (bank in OTM, book in MTO).
    
    Attributes:
        anchor_id: The ID of the anchor (bank or book)
        anchor_type: "bank" or "book"
        candidate_count_initial: Number of candidates before filtering
        candidate_count_after_date_filter: After date window filter
        candidate_count_after_currency_filter: After currency filter
        candidate_count_after_sign_filter: After sign filter
        candidate_count_final: Final candidate count after all filters
        feasible_group_sizes: List of feasible group sizes
        infeasible_group_sizes: List of infeasible group sizes
        g_min: Minimum feasible group size
        sizes_skipped_by_bounds: Number of sizes skipped due to feasibility bounds
        combinations_explored: Total combinations examined
        branches_pruned_by_bounds: Branches pruned by bound checking
        all_in_shortcut_used: Whether the all-in shortcut was used
        top_k_returned: Number of alternatives returned
        best_confidence: Confidence of the best match found
        time_ms: Time spent processing this anchor in milliseconds
    """
    anchor_id: int
    anchor_type: str  # "bank" or "book"
    
    # Candidate filtering
    candidate_count_initial: int = 0
    candidate_count_after_date_filter: int = 0
    candidate_count_after_currency_filter: int = 0
    candidate_count_after_sign_filter: int = 0
    candidate_count_final: int = 0
    
    # Feasibility bounds
    feasible_group_sizes: List[int] = field(default_factory=list)
    infeasible_group_sizes: List[int] = field(default_factory=list)
    g_min: Optional[int] = None
    sizes_skipped_by_bounds: int = 0
    
    # Search metrics
    combinations_explored: int = 0
    branches_pruned_by_bounds: int = 0
    all_in_shortcut_used: bool = False
    
    # Results
    top_k_returned: int = 0
    best_confidence: float = 0.0
    
    # Performance
    time_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    def log(self, level: int = logging.DEBUG) -> None:
        """Log this anchor's metrics."""
        log.log(
            level,
            "ANCHOR_METRICS %s=%s g_min=%s skipped=%s combos=%s time_ms=%.2f conf=%.4f",
            self.anchor_type,
            self.anchor_id,
            self.g_min,
            self.sizes_skipped_by_bounds,
            self.combinations_explored,
            self.time_ms,
            self.best_confidence,
        )


@dataclass
class StageMetrics:
    """
    Metrics for a single matching stage.
    
    Attributes:
        stage_type: Type of stage (exact_1to1, fuzzy_1to1, one_to_many, etc.)
        stage_index: Position in the pipeline
        candidates_generated: Total candidate pairs/groups generated
        combinations_explored: Total combinations examined across all anchors
        suggestions_produced: Number of suggestions created
        duration_ms: Time spent on this stage in milliseconds
        avg_confidence: Average confidence of produced suggestions
        anchors_processed: Number of anchors (banks or books) processed
        anchors_with_g_min_skip: Anchors where g_min caused skipping
        total_sizes_skipped: Sum of sizes skipped across all anchors
        all_in_shortcuts_used: Count of all-in shortcuts taken
        anchor_metrics: Per-anchor detailed metrics (optional)
    """
    stage_type: str
    stage_index: int = 0
    
    # Counts
    candidates_generated: int = 0
    combinations_explored: int = 0
    suggestions_produced: int = 0
    
    # Performance
    duration_ms: float = 0.0
    
    # Quality
    avg_confidence: float = 0.0
    min_confidence: float = 1.0
    max_confidence: float = 0.0
    
    # Feasibility pruning aggregates
    anchors_processed: int = 0
    anchors_with_g_min_skip: int = 0
    total_sizes_skipped: int = 0
    all_in_shortcuts_used: int = 0
    
    # Detailed per-anchor metrics (optional, can be memory-intensive)
    anchor_metrics: List[AnchorMetrics] = field(default_factory=list)
    
    def to_dict(self, include_anchor_metrics: bool = False) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "stage_type": self.stage_type,
            "stage_index": self.stage_index,
            "candidates_generated": self.candidates_generated,
            "combinations_explored": self.combinations_explored,
            "suggestions_produced": self.suggestions_produced,
            "duration_ms": self.duration_ms,
            "avg_confidence": self.avg_confidence,
            "min_confidence": self.min_confidence,
            "max_confidence": self.max_confidence,
            "anchors_processed": self.anchors_processed,
            "anchors_with_g_min_skip": self.anchors_with_g_min_skip,
            "total_sizes_skipped": self.total_sizes_skipped,
            "all_in_shortcuts_used": self.all_in_shortcuts_used,
        }
        if include_anchor_metrics:
            result["anchor_metrics"] = [m.to_dict() for m in self.anchor_metrics]
        return result
    
    def log(self, level: int = logging.INFO) -> None:
        """Log this stage's metrics."""
        log.log(
            level,
            "STAGE_METRICS type=%s suggestions=%d combos=%d duration_ms=%.2f avg_conf=%.4f g_min_skips=%d",
            self.stage_type,
            self.suggestions_produced,
            self.combinations_explored,
            self.duration_ms,
            self.avg_confidence,
            self.anchors_with_g_min_skip,
        )


@dataclass 
class ReconciliationMetrics:
    """
    Aggregate metrics for a complete reconciliation run.
    
    Attributes:
        run_id: Unique identifier for this run
        company_id: Company being reconciled
        bank_count: Number of bank transactions
        book_count: Number of journal entries
        stage_metrics: Per-stage detailed metrics
        total_suggestions: Total suggestions produced
        match_type_distribution: Count by match type
        confidence_histogram: Suggestions binned by confidence
        total_duration_ms: Total run time in milliseconds
        time_limit_reached: Whether the time limit was hit
        pipeline_id: ID of the pipeline used (if any)
        config_id: ID of the config used (if any)
    """
    run_id: str = ""
    company_id: int = 0
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    
    # Inputs
    bank_count: int = 0
    book_count: int = 0
    
    # Per-stage
    stage_metrics: List[StageMetrics] = field(default_factory=list)
    
    # Outputs
    total_suggestions: int = 0
    match_type_distribution: Dict[str, int] = field(default_factory=dict)
    
    # Confidence distribution: buckets [0.5, 0.7, 0.9, 0.95, 0.99, 1.0]
    confidence_histogram: Dict[str, int] = field(default_factory=dict)
    
    # Performance
    total_duration_ms: float = 0.0
    time_limit_reached: bool = False
    
    # Context
    pipeline_id: Optional[int] = None
    config_id: Optional[int] = None
    
    def to_dict(self, include_anchor_metrics: bool = False) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "run_id": self.run_id,
            "company_id": self.company_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "bank_count": self.bank_count,
            "book_count": self.book_count,
            "stage_metrics": [
                s.to_dict(include_anchor_metrics) for s in self.stage_metrics
            ],
            "total_suggestions": self.total_suggestions,
            "match_type_distribution": self.match_type_distribution,
            "confidence_histogram": self.confidence_histogram,
            "total_duration_ms": self.total_duration_ms,
            "time_limit_reached": self.time_limit_reached,
            "pipeline_id": self.pipeline_id,
            "config_id": self.config_id,
        }
    
    def to_json(self, include_anchor_metrics: bool = False) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(include_anchor_metrics), default=str)
    
    def log_summary(self, level: int = logging.INFO) -> None:
        """Log a summary of the run metrics."""
        log.log(
            level,
            "RECONCILIATION_RUN run_id=%s company=%d banks=%d books=%d "
            "suggestions=%d duration_ms=%.2f time_limit=%s",
            self.run_id,
            self.company_id,
            self.bank_count,
            self.book_count,
            self.total_suggestions,
            self.total_duration_ms,
            self.time_limit_reached,
        )
        
        # Log match type distribution
        if self.match_type_distribution:
            log.log(
                level,
                "MATCH_DISTRIBUTION %s",
                json.dumps(self.match_type_distribution),
            )
        
        # Log confidence histogram
        if self.confidence_histogram:
            log.log(
                level,
                "CONFIDENCE_HISTOGRAM %s",
                json.dumps(self.confidence_histogram),
            )
        
        # Log each stage
        for stage in self.stage_metrics:
            stage.log(level)


# ----------------------------------------------------------------------
# Match Explanation
# ----------------------------------------------------------------------

@dataclass
class MatchExplanation:
    """
    Structured explanation for why a match was made.
    
    Includes all scoring components and metadata for debugging and audit.
    """
    match_type: str
    bank_ids: List[int]
    journal_entry_ids: List[int]
    confidence_score: float
    
    # Amount
    bank_total: float = 0.0
    book_total: float = 0.0
    amount_delta: float = 0.0
    amount_score: float = 0.0
    
    # Date
    date_delta_days: int = 0
    date_score: float = 0.0
    
    # Description/Embedding
    embedding_similarity: float = 0.0
    description_score: float = 0.0
    
    # Currency
    currency_match: bool = True
    
    # Group info
    group_size_banks: int = 1
    group_size_books: int = 1
    bank_span_days: int = 0
    book_span_days: int = 0
    
    # Alternatives info
    rank_among_alternatives: int = 1
    total_alternatives: int = 1
    is_primary: bool = True
    alternatives_group_id: Optional[str] = None
    
    # Pruning info
    g_min: Optional[int] = None
    sizes_skipped: int = 0
    search_strategy: str = "exact"
    all_in_shortcut_used: bool = False
    
    # Weights used
    weights: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)


# ----------------------------------------------------------------------
# Metrics Collector
# ----------------------------------------------------------------------

class MetricsCollector:
    """
    Context manager and utility for collecting reconciliation metrics.
    
    Usage:
        with MetricsCollector(run_id="abc123", company_id=1) as collector:
            # Start a stage
            with collector.stage("one_to_many") as stage:
                # Process anchors
                for bank in banks:
                    with stage.anchor(bank.id, "bank") as anchor:
                        anchor.candidate_count_initial = len(books)
                        # ... process ...
                        anchor.suggestions_produced = 3
            
            # Get final metrics
            metrics = collector.finalize()
    """
    
    def __init__(
        self,
        run_id: str = "",
        company_id: int = 0,
        bank_count: int = 0,
        book_count: int = 0,
        pipeline_id: Optional[int] = None,
        config_id: Optional[int] = None,
    ):
        self.metrics = ReconciliationMetrics(
            run_id=run_id,
            company_id=company_id,
            bank_count=bank_count,
            book_count=book_count,
            pipeline_id=pipeline_id,
            config_id=config_id,
        )
        self._start_time: Optional[float] = None
        self._current_stage: Optional[StageMetrics] = None
        self._current_anchor: Optional[AnchorMetrics] = None
        self._stage_start_time: Optional[float] = None
        self._anchor_start_time: Optional[float] = None
    
    def __enter__(self) -> "MetricsCollector":
        self._start_time = time.perf_counter()
        self.metrics.started_at = datetime.utcnow().isoformat()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.finalize()
    
    def start_stage(self, stage_type: str) -> StageMetrics:
        """Start collecting metrics for a new stage."""
        if self._current_stage:
            self._end_stage()
        
        self._current_stage = StageMetrics(
            stage_type=stage_type,
            stage_index=len(self.metrics.stage_metrics),
        )
        self._stage_start_time = time.perf_counter()
        return self._current_stage
    
    def _end_stage(self) -> None:
        """End the current stage and save metrics."""
        if self._current_stage and self._stage_start_time:
            self._current_stage.duration_ms = (
                time.perf_counter() - self._stage_start_time
            ) * 1000
            
            # Calculate average confidence
            if self._current_stage.anchor_metrics:
                confidences = [
                    m.best_confidence 
                    for m in self._current_stage.anchor_metrics 
                    if m.best_confidence > 0
                ]
                if confidences:
                    self._current_stage.avg_confidence = sum(confidences) / len(confidences)
                    self._current_stage.min_confidence = min(confidences)
                    self._current_stage.max_confidence = max(confidences)
            
            self.metrics.stage_metrics.append(self._current_stage)
            self._current_stage.log()
        
        self._current_stage = None
        self._stage_start_time = None
    
    def start_anchor(self, anchor_id: int, anchor_type: str) -> AnchorMetrics:
        """Start collecting metrics for an anchor within the current stage."""
        if self._current_anchor:
            self._end_anchor()
        
        self._current_anchor = AnchorMetrics(
            anchor_id=anchor_id,
            anchor_type=anchor_type,
        )
        self._anchor_start_time = time.perf_counter()
        return self._current_anchor
    
    def _end_anchor(self) -> None:
        """End the current anchor and save metrics to the stage."""
        if self._current_anchor and self._anchor_start_time:
            self._current_anchor.time_ms = (
                time.perf_counter() - self._anchor_start_time
            ) * 1000
            
            if self._current_stage:
                self._current_stage.anchor_metrics.append(self._current_anchor)
                self._current_stage.anchors_processed += 1
                self._current_stage.combinations_explored += self._current_anchor.combinations_explored
                
                if self._current_anchor.g_min and self._current_anchor.g_min > 1:
                    self._current_stage.anchors_with_g_min_skip += 1
                    self._current_stage.total_sizes_skipped += self._current_anchor.sizes_skipped_by_bounds
                
                if self._current_anchor.all_in_shortcut_used:
                    self._current_stage.all_in_shortcuts_used += 1
            
            # Log if significant skipping occurred
            if self._current_anchor.sizes_skipped_by_bounds >= 10:
                log.warning(
                    "LARGE_SKIP %s=%s g_min=%d skipped=%d candidates=%d",
                    self._current_anchor.anchor_type,
                    self._current_anchor.anchor_id,
                    self._current_anchor.g_min,
                    self._current_anchor.sizes_skipped_by_bounds,
                    self._current_anchor.candidate_count_final,
                )
        
        self._current_anchor = None
        self._anchor_start_time = None
    
    def record_suggestion(self, suggestion: Dict[str, Any]) -> None:
        """Record a produced suggestion for metrics."""
        self.metrics.total_suggestions += 1
        
        # Update match type distribution
        match_type = suggestion.get("match_type", "unknown")
        self.metrics.match_type_distribution[match_type] = (
            self.metrics.match_type_distribution.get(match_type, 0) + 1
        )
        
        # Update confidence histogram
        confidence = float(suggestion.get("confidence_score", 0))
        bucket = self._confidence_bucket(confidence)
        self.metrics.confidence_histogram[bucket] = (
            self.metrics.confidence_histogram.get(bucket, 0) + 1
        )
        
        # Update current stage
        if self._current_stage:
            self._current_stage.suggestions_produced += 1
    
    def _confidence_bucket(self, confidence: float) -> str:
        """Map a confidence score to a histogram bucket."""
        if confidence >= 1.0:
            return "1.0"
        elif confidence >= 0.99:
            return "0.99"
        elif confidence >= 0.95:
            return "0.95"
        elif confidence >= 0.9:
            return "0.9"
        elif confidence >= 0.7:
            return "0.7"
        elif confidence >= 0.5:
            return "0.5"
        else:
            return "<0.5"
    
    def set_time_limit_reached(self, reached: bool = True) -> None:
        """Mark that the time limit was reached."""
        self.metrics.time_limit_reached = reached
    
    def finalize(self) -> ReconciliationMetrics:
        """Finalize and return the collected metrics."""
        # End any open anchor/stage
        if self._current_anchor:
            self._end_anchor()
        if self._current_stage:
            self._end_stage()
        
        # Calculate total duration
        if self._start_time:
            self.metrics.total_duration_ms = (
                time.perf_counter() - self._start_time
            ) * 1000
        
        self.metrics.ended_at = datetime.utcnow().isoformat()
        
        # Log summary
        self.metrics.log_summary()
        
        return self.metrics
    
    def stage(self, stage_type: str) -> "StageContext":
        """Context manager for a stage."""
        return StageContext(self, stage_type)
    
    def anchor(self, anchor_id: int, anchor_type: str) -> "AnchorContext":
        """Context manager for an anchor."""
        return AnchorContext(self, anchor_id, anchor_type)


class StageContext:
    """Context manager for stage metrics collection."""
    
    def __init__(self, collector: MetricsCollector, stage_type: str):
        self.collector = collector
        self.stage_type = stage_type
        self.metrics: Optional[StageMetrics] = None
    
    def __enter__(self) -> StageMetrics:
        self.metrics = self.collector.start_stage(self.stage_type)
        return self.metrics
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.collector._end_stage()
    
    def anchor(self, anchor_id: int, anchor_type: str) -> "AnchorContext":
        """Context manager for an anchor within this stage."""
        return AnchorContext(self.collector, anchor_id, anchor_type)


class AnchorContext:
    """Context manager for anchor metrics collection."""
    
    def __init__(self, collector: MetricsCollector, anchor_id: int, anchor_type: str):
        self.collector = collector
        self.anchor_id = anchor_id
        self.anchor_type = anchor_type
        self.metrics: Optional[AnchorMetrics] = None
    
    def __enter__(self) -> AnchorMetrics:
        self.metrics = self.collector.start_anchor(self.anchor_id, self.anchor_type)
        return self.metrics
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.collector._end_anchor()


# ----------------------------------------------------------------------
# Utility Functions
# ----------------------------------------------------------------------

def build_match_explanation(
    suggestion: Dict[str, Any],
    g_min: Optional[int] = None,
    sizes_skipped: int = 0,
    search_strategy: str = "exact",
    all_in_shortcut_used: bool = False,
) -> MatchExplanation:
    """
    Build a MatchExplanation from a suggestion dict.
    
    Args:
        suggestion: The suggestion dictionary
        g_min: Minimum feasible group size used
        sizes_skipped: Number of group sizes skipped
        search_strategy: Strategy used (exact, beam, branch_and_bound)
        all_in_shortcut_used: Whether the all-in shortcut was taken
    
    Returns:
        MatchExplanation instance
    """
    extra = suggestion.get("extra", {})
    component_scores = suggestion.get("component_scores", {})
    bank_stats = suggestion.get("bank_stats", {})
    book_stats = suggestion.get("book_stats", {})
    weights = suggestion.get("confidence_weights", {})
    
    return MatchExplanation(
        match_type=suggestion.get("match_type", "unknown"),
        bank_ids=suggestion.get("bank_ids", []),
        journal_entry_ids=suggestion.get("journal_entries_ids", []),
        confidence_score=float(suggestion.get("confidence_score", 0)),
        
        # Amount
        bank_total=float(bank_stats.get("sum_amount", 0)),
        book_total=float(book_stats.get("sum_amount", 0)),
        amount_delta=float(suggestion.get("abs_amount_diff", 0)),
        amount_score=float(component_scores.get("amount_score", 0)),
        
        # Date
        date_delta_days=int(extra.get("avg_date_delta_days_measured", 0)),
        date_score=float(component_scores.get("date_score", 0)),
        
        # Description/Embedding
        embedding_similarity=float(extra.get("embed_similarity", 0)),
        description_score=float(component_scores.get("description_score", 0)),
        
        # Currency
        currency_match=bool(component_scores.get("currency_score", 1) > 0),
        
        # Group info
        group_size_banks=int(bank_stats.get("count", 1)),
        group_size_books=int(book_stats.get("count", 1)),
        bank_span_days=int(extra.get("bank_span_days_measured", 0)),
        book_span_days=int(extra.get("book_span_days_measured", 0)),
        
        # Alternatives info
        rank_among_alternatives=suggestion.get("rank_among_alternatives", 1),
        total_alternatives=suggestion.get("total_alternatives", 1),
        is_primary=suggestion.get("is_primary", True),
        alternatives_group_id=suggestion.get("alternatives_group_id"),
        
        # Pruning info
        g_min=g_min,
        sizes_skipped=sizes_skipped,
        search_strategy=search_strategy,
        all_in_shortcut_used=all_in_shortcut_used,
        
        # Weights
        weights=weights,
    )


def log_feasibility_skip(
    anchor_id: int,
    anchor_type: str,
    g_min: int,
    skipped_sizes: int,
    candidate_count: int,
) -> None:
    """
    Log when g_min causes significant size skipping.
    
    Args:
        anchor_id: ID of the anchor
        anchor_type: "bank" or "book"
        g_min: Minimum feasible group size
        skipped_sizes: Number of sizes skipped (g_min - 1)
        candidate_count: Number of candidates after filtering
    """
    log.info(
        "FEASIBILITY_SKIP %s=%s g_min=%d skipped_sizes=%d candidate_count=%d",
        anchor_type,
        anchor_id,
        g_min,
        skipped_sizes,
        candidate_count,
    )
    
    if skipped_sizes >= 10:
        log.warning(
            "LARGE_SKIP %s=%s g_min=%d skipped=%d - consider reducing max_group_size",
            anchor_type,
            anchor_id,
            g_min,
            skipped_sizes,
        )

