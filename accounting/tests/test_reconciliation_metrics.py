"""
test_reconciliation_metrics.py

Unit tests for reconciliation metrics dataclasses.
"""

import pytest
import time
from datetime import datetime, timedelta

from accounting.services.reconciliation_metrics import (
    AnchorMetrics,
    StageMetrics,
    ReconciliationMetrics,
    MetricsCollector,
    MatchExplanation,
    build_match_explanation,
)


# ----------------------------------------------------------------------
# Tests: AnchorMetrics
# ----------------------------------------------------------------------

class TestAnchorMetrics:
    """Tests for AnchorMetrics dataclass."""
    
    def test_default_values(self):
        """Test default values are set correctly."""
        metrics = AnchorMetrics(anchor_id=1, anchor_type="bank")
        
        assert metrics.anchor_id == 1
        assert metrics.anchor_type == "bank"
        assert metrics.candidate_count_initial == 0
        assert metrics.candidate_count_final == 0
        assert metrics.g_min is None
        assert metrics.sizes_skipped_by_bounds == 0
        assert metrics.combinations_explored == 0
        assert metrics.branches_pruned_by_bounds == 0
        assert metrics.all_in_shortcut_used is False
        assert metrics.top_k_returned == 0
        assert metrics.best_confidence == 0.0
        assert metrics.time_ms == 0.0
    
    def test_feasibility_metrics(self):
        """Test feasibility-related metrics."""
        metrics = AnchorMetrics(
            anchor_id=123,
            anchor_type="bank",
            candidate_count_initial=40,
            candidate_count_final=40,
            feasible_group_sizes=[40],
            infeasible_group_sizes=list(range(1, 40)),
            g_min=40,
            sizes_skipped_by_bounds=39,
        )
        
        assert metrics.g_min == 40
        assert metrics.sizes_skipped_by_bounds == 39
        assert len(metrics.feasible_group_sizes) == 1
        assert len(metrics.infeasible_group_sizes) == 39
    
    def test_all_in_shortcut(self):
        """Test all-in shortcut tracking."""
        metrics = AnchorMetrics(
            anchor_id=1,
            anchor_type="bank",
            all_in_shortcut_used=True,
            combinations_explored=1,
        )
        
        assert metrics.all_in_shortcut_used is True
        assert metrics.combinations_explored == 1


# ----------------------------------------------------------------------
# Tests: StageMetrics
# ----------------------------------------------------------------------

class TestStageMetrics:
    """Tests for StageMetrics dataclass."""
    
    def test_default_values(self):
        """Test default values are set correctly."""
        metrics = StageMetrics(stage_type="one_to_many")
        
        assert metrics.stage_type == "one_to_many"
        assert metrics.candidates_generated == 0
        assert metrics.combinations_explored == 0
        assert metrics.suggestions_produced == 0
        assert metrics.duration_ms == 0.0
        assert metrics.avg_confidence == 0.0
        assert metrics.anchors_processed == 0
        assert metrics.anchors_with_g_min_skip == 0
        assert metrics.total_sizes_skipped == 0
        assert metrics.all_in_shortcuts_used == 0
        assert metrics.per_anchor_details == []
    
    def test_with_anchor_details(self):
        """Test with per-anchor detail metrics."""
        anchor1 = AnchorMetrics(anchor_id=1, anchor_type="bank", g_min=5)
        anchor2 = AnchorMetrics(anchor_id=2, anchor_type="bank", g_min=3)
        
        metrics = StageMetrics(
            stage_type="one_to_many",
            anchors_processed=2,
            anchor_metrics=[anchor1, anchor2]
        )
        
        assert len(metrics.anchor_metrics) == 2
        assert metrics.anchor_metrics[0].g_min == 5
        assert metrics.anchor_metrics[1].g_min == 3
    
    def test_feasibility_pruning_summary(self):
        """Test feasibility pruning summary metrics."""
        metrics = StageMetrics(
            stage_type="one_to_many",
            anchors_processed=10,
            anchors_with_g_min_skip=7,
            total_sizes_skipped=150,
            all_in_shortcuts_used=2,
        )
        
        assert metrics.anchors_with_g_min_skip == 7
        assert metrics.total_sizes_skipped == 150
        assert metrics.all_in_shortcuts_used == 2


# ----------------------------------------------------------------------
# Tests: ReconciliationMetrics
# ----------------------------------------------------------------------

class TestReconciliationMetrics:
    """Tests for ReconciliationMetrics dataclass."""
    
    def test_default_values(self):
        """Test default values are set correctly."""
        metrics = ReconciliationMetrics()
        
        assert metrics.bank_count == 0
        assert metrics.book_count == 0
        assert metrics.stage_metrics == []
        assert metrics.total_suggestions == 0
        assert metrics.match_type_distribution == {}
        assert metrics.confidence_histogram == []
        assert metrics.total_duration_ms == 0.0
        assert metrics.time_limit_reached is False
    
    def test_with_stage_metrics(self):
        """Test with multiple stage metrics."""
        stage1 = StageMetrics(stage_type="exact_1to1", suggestions_produced=10)
        stage2 = StageMetrics(stage_type="fuzzy_1to1", suggestions_produced=5)
        stage3 = StageMetrics(stage_type="one_to_many", suggestions_produced=3)
        
        metrics = ReconciliationMetrics(
            bank_count=100,
            book_count=200,
            stage_metrics=[stage1, stage2, stage3],
            total_suggestions=18,
        )
        
        assert metrics.bank_count == 100
        assert metrics.book_count == 200
        assert len(metrics.stage_metrics) == 3
        assert metrics.total_suggestions == 18
    
    def test_match_type_distribution(self):
        """Test match type distribution tracking."""
        metrics = ReconciliationMetrics(
            match_type_distribution={
                "exact_1to1": 50,
                "fuzzy_1to1": 30,
                "one_to_many": 15,
                "many_to_one": 5,
            }
        )
        
        assert metrics.match_type_distribution["exact_1to1"] == 50
        assert sum(metrics.match_type_distribution.values()) == 100
    
    def test_confidence_histogram(self):
        """Test confidence histogram."""
        metrics = ReconciliationMetrics(
            confidence_histogram=[0.5, 0.7, 0.9, 0.95, 0.99, 1.0]
        )
        
        assert len(metrics.confidence_histogram) == 6


# ----------------------------------------------------------------------
# Tests: MetricsCollector
# ----------------------------------------------------------------------

class TestMetricsCollector:
    """Tests for MetricsCollector class."""
    
    def test_initialization(self):
        """Test collector initialization."""
        with MetricsCollector(bank_count=50, book_count=100) as collector:
            assert collector.metrics.bank_count == 50
            assert collector.metrics.book_count == 100
            assert collector._start_time is not None
    
    def test_start_stage(self):
        """Test starting a stage."""
        collector = MetricsCollector(bank_count=10, book_count=20)
        collector._start_time = time.perf_counter()
        stage = collector.start_stage("one_to_many")
        
        assert collector._current_stage.stage_type == "one_to_many"
        assert collector._stage_start_time is not None
        assert stage.stage_type == "one_to_many"
    
    def test_anchor_context_manager(self):
        """Test recording anchor metrics via context manager."""
        collector = MetricsCollector(bank_count=10, book_count=20)
        collector._start_time = time.perf_counter()
        
        with collector.stage("one_to_many") as stage:
            with collector.anchor(1, "bank") as anchor_metrics:
                anchor_metrics.g_min = 5
                anchor_metrics.sizes_skipped_by_bounds = 4
                anchor_metrics.combinations_explored = 100
        
        assert len(collector.metrics.stage_metrics) == 1
        assert len(collector.metrics.stage_metrics[0].anchor_metrics) == 1
        assert collector.metrics.stage_metrics[0].anchor_metrics[0].g_min == 5
    
    def test_end_stage(self):
        """Test ending a stage."""
        collector = MetricsCollector(bank_count=10, book_count=20)
        collector._start_time = time.perf_counter()
        
        with collector.stage("one_to_many") as stage:
            with collector.anchor(1, "bank") as anchor_metrics:
                anchor_metrics.g_min = 5
                anchor_metrics.best_confidence = 0.85
            
            stage.candidates_generated = 100
            stage.combinations_explored = 500
        
        assert len(collector.metrics.stage_metrics) == 1
        final_stage = collector.metrics.stage_metrics[0]
        assert final_stage.stage_type == "one_to_many"
        assert final_stage.candidates_generated == 100
        assert len(final_stage.anchor_metrics) == 1
    
    def test_end_stage_computes_duration(self):
        """Test that end_stage computes duration."""
        collector = MetricsCollector(bank_count=10, book_count=20)
        collector._start_time = time.perf_counter()
        
        with collector.stage("exact_1to1") as stage:
            # Small delay
            time.sleep(0.01)
        
        assert collector.metrics.stage_metrics[0].duration_ms >= 10  # At least 10ms
    
    def test_finalize(self):
        """Test finalizing metrics."""
        with MetricsCollector(bank_count=10, book_count=20) as collector:
            with collector.stage("exact_1to1") as stage:
                pass
            
            # Small delay
            time.sleep(0.01)
            
            # Record some suggestions
            collector.record_suggestion({"match_type": "exact_1to1", "confidence_score": 0.95})
            collector.record_suggestion({"match_type": "exact_1to1", "confidence_score": 1.0})
        
        final_metrics = collector.metrics
        assert final_metrics.total_suggestions == 2
        assert final_metrics.total_duration_ms >= 10
        assert final_metrics.match_type_distribution.get("exact_1to1") == 2
    
    def test_feasibility_pruning_aggregation(self):
        """Test aggregation of feasibility pruning metrics."""
        collector = MetricsCollector(bank_count=10, book_count=50)
        collector._start_time = time.perf_counter()
        
        with collector.stage("one_to_many") as stage:
            # Add anchors with different g_min values
            for i in range(5):
                with collector.anchor(i, "bank") as anchor:
                    if i < 3:
                        anchor.g_min = i + 2  # 3 with g_min > 1
                        anchor.sizes_skipped_by_bounds = i + 1
                    else:
                        anchor.g_min = None  # 2 without g_min
            
            stage.candidates_generated = 200
        
        final_stage = collector.metrics.stage_metrics[0]
        assert final_stage.anchors_processed == 5
        assert final_stage.anchors_with_g_min_skip == 3  # 3 anchors had g_min > 1
        assert final_stage.total_sizes_skipped == 1 + 2 + 3  # Sum of sizes_skipped


# ----------------------------------------------------------------------
# Tests: Edge Cases
# ----------------------------------------------------------------------

class TestMetricsEdgeCases:
    """Tests for edge cases in metrics handling."""
    
    def test_empty_stage(self):
        """Test stage with no anchors processed."""
        collector = MetricsCollector(bank_count=0, book_count=10)
        collector._start_time = time.perf_counter()
        
        with collector.stage("one_to_many") as stage:
            pass
        
        final_stage = collector.metrics.stage_metrics[0]
        assert final_stage.anchors_processed == 0
        assert final_stage.anchor_metrics == []
    
    def test_multiple_stages(self):
        """Test multiple stages in sequence."""
        collector = MetricsCollector(bank_count=20, book_count=40)
        collector._start_time = time.perf_counter()
        
        # Stage 1
        with collector.stage("exact_1to1") as stage:
            stage.candidates_generated = 50
        
        # Stage 2
        with collector.stage("fuzzy_1to1") as stage:
            stage.candidates_generated = 100
        
        # Stage 3
        with collector.stage("one_to_many") as stage:
            stage.candidates_generated = 200
        
        assert len(collector.metrics.stage_metrics) == 3
        assert collector.metrics.stage_metrics[0].stage_type == "exact_1to1"
        assert collector.metrics.stage_metrics[1].stage_type == "fuzzy_1to1"
        assert collector.metrics.stage_metrics[2].stage_type == "one_to_many"
    
    def test_confidence_histogram_computation(self):
        """Test computing confidence histogram from scores."""
        scores = [0.45, 0.55, 0.65, 0.75, 0.85, 0.92, 0.97, 1.0, 1.0, 1.0]
        
        # Bucket boundaries: [0.5, 0.7, 0.9, 0.95, 0.99, 1.0]
        # Expected: <0.5: 1, 0.5-0.7: 2, 0.7-0.9: 2, 0.9-0.95: 1, 0.95-0.99: 1, 0.99-1.0: 0, 1.0: 3
        
        histogram = compute_confidence_histogram(scores)
        
        assert histogram["<0.5"] == 1
        assert histogram["0.5-0.7"] == 2
        assert histogram["0.7-0.9"] == 2
        assert histogram["0.9-0.95"] == 1
        assert histogram["0.95-0.99"] == 1
        assert histogram["1.0"] == 3


# ----------------------------------------------------------------------
# Tests: MatchExplanation
# ----------------------------------------------------------------------

class TestMatchExplanation:
    """Tests for MatchExplanation dataclass."""
    
    def test_basic_explanation(self):
        """Test creating a basic match explanation."""
        explanation = MatchExplanation(
            match_type="one_to_many",
            bank_ids=[1],
            journal_entry_ids=[2, 3, 4],
            confidence_score=0.95,
            bank_total=1000.0,
            book_total=999.98,
            amount_delta=0.02,
        )
        
        assert explanation.match_type == "one_to_many"
        assert len(explanation.journal_entry_ids) == 3
        assert explanation.confidence_score == 0.95
    
    def test_explanation_to_dict(self):
        """Test converting explanation to dictionary."""
        explanation = MatchExplanation(
            match_type="exact_1to1",
            bank_ids=[1],
            journal_entry_ids=[2],
            confidence_score=1.0,
        )
        
        result = explanation.to_dict()
        assert result["match_type"] == "exact_1to1"
        assert result["confidence_score"] == 1.0
    
    def test_build_match_explanation_from_suggestion(self):
        """Test building explanation from suggestion dict."""
        suggestion = {
            "match_type": "one_to_many",
            "bank_ids": [123],
            "journal_entries_ids": [456, 789],
            "confidence_score": 0.92,
            "abs_amount_diff": 0.50,
            "extra": {
                "avg_date_delta_days_measured": 2,
                "embed_similarity": 0.85,
            },
            "component_scores": {
                "amount_score": 0.95,
                "date_score": 0.90,
                "description_score": 0.85,
                "currency_score": 1.0,
            },
            "bank_stats": {"count": 1, "sum_amount": 1000},
            "book_stats": {"count": 2, "sum_amount": 999.50},
            "rank_among_alternatives": 1,
            "total_alternatives": 3,
            "is_primary": True,
        }
        
        explanation = build_match_explanation(
            suggestion,
            g_min=2,
            sizes_skipped=1,
            search_strategy="exact_with_pruning",
        )
        
        assert explanation.match_type == "one_to_many"
        assert explanation.confidence_score == 0.92
        assert explanation.g_min == 2
        assert explanation.sizes_skipped == 1
        assert explanation.search_strategy == "exact_with_pruning"
        assert explanation.rank_among_alternatives == 1
        assert explanation.total_alternatives == 3


def compute_confidence_histogram(scores):
    """Helper to compute confidence histogram from scores."""
    buckets = {"<0.5": 0, "0.5-0.7": 0, "0.7-0.9": 0, "0.9-0.95": 0, "0.95-0.99": 0, "1.0": 0}
    
    for score in scores:
        if score < 0.5:
            buckets["<0.5"] += 1
        elif score < 0.7:
            buckets["0.5-0.7"] += 1
        elif score < 0.9:
            buckets["0.7-0.9"] += 1
        elif score < 0.95:
            buckets["0.9-0.95"] += 1
        elif score < 1.0:
            buckets["0.95-0.99"] += 1
        else:
            buckets["1.0"] += 1
    
    return buckets

