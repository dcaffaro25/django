"""
test_reconciliation_service.py

Comprehensive test suite for the reconciliation service.
Includes unit tests, property-based tests, and integration tests.
"""

import random
from datetime import date, timedelta
from decimal import Decimal
from typing import List
from unittest.mock import MagicMock, patch

import pytest

# Import the reconciliation service components
from accounting.services.reconciliation_service import (
    BankTransactionDTO,
    JournalEntryDTO,
    StageConfig,
    PipelineConfig,
    ReconciliationPipelineEngine,
    compute_match_scores,
    compute_feasibility_bounds,
    q2,
    _sign,
    _avg_embedding,
    CENT,
)


# ----------------------------------------------------------------------
# Test Fixtures
# ----------------------------------------------------------------------

@pytest.fixture
def sample_weights():
    """Default weight configuration for scoring."""
    return {
        "embedding": 0.5,
        "amount": 0.35,
        "currency": 0.1,
        "date": 0.05,
    }


@pytest.fixture
def sample_stage_config():
    """Sample stage configuration for one-to-many matching."""
    return StageConfig(
        type="one_to_many",
        amount_tol=Decimal("0.01"),
        avg_date_delta_days=7,
        group_span_days=30,
        max_group_size_bank=1,
        max_group_size_book=5,
        allow_mixed_signs=False,
        max_alternatives_per_anchor=3,
    )


@pytest.fixture
def sample_pipeline_config(sample_stage_config):
    """Sample pipeline configuration."""
    return PipelineConfig(
        stages=[sample_stage_config],
        max_suggestions=1000,
        max_runtime_seconds=60,
        weights={
            "embedding": 0.5,
            "amount": 0.35,
            "currency": 0.1,
            "date": 0.05,
        },
    )


def create_bank_dto(
    id: int = 1,
    amount: Decimal = Decimal("1000.00"),
    date_val: date = None,
    company_id: int = 1,
    currency_id: int = 1,
    description: str = "Test bank transaction",
    embedding: List[float] = None,
) -> BankTransactionDTO:
    """Factory function to create BankTransactionDTO instances."""
    return BankTransactionDTO(
        id=id,
        company_id=company_id,
        amount_base=amount,
        currency_id=currency_id,
        date=date_val or date.today(),
        description=description,
        embedding=embedding or [0.1] * 384,
    )


def create_book_dto(
    id: int = 1,
    amount: Decimal = Decimal("1000.00"),
    date_val: date = None,
    company_id: int = 1,
    currency_id: int = 1,
    description: str = "Test journal entry",
    embedding: List[float] = None,
) -> JournalEntryDTO:
    """Factory function to create JournalEntryDTO instances."""
    return JournalEntryDTO(
        id=id,
        company_id=company_id,
        amount_base=amount,
        currency_id=currency_id,
        date=date_val or date.today(),
        description=description,
        embedding=embedding or [0.1] * 384,
    )


# ----------------------------------------------------------------------
# Unit Tests: Scoring Functions
# ----------------------------------------------------------------------

class TestComputeMatchScores:
    """Unit tests for compute_match_scores function."""
    
    def test_exact_match_returns_1(self, sample_weights):
        """Test that a perfect match returns score of 1.0."""
        scores = compute_match_scores(
            embed_sim=1.0,
            amount_diff=Decimal("0"),
            amount_tol=Decimal("1"),
            date_diff=0,
            date_tol=1,
            currency_match=1.0,
            weights=sample_weights,
        )
        assert scores["global_score"] == 1.0
        assert scores["amount_score"] == 1.0
        assert scores["date_score"] == 1.0
        assert scores["description_score"] == 1.0
        assert scores["currency_score"] == 1.0
    
    def test_zero_amount_diff_gives_full_amount_score(self, sample_weights):
        """Test amount_score is 1.0 when amount_diff is 0."""
        scores = compute_match_scores(
            embed_sim=0.0,
            amount_diff=Decimal("0"),
            amount_tol=Decimal("100"),
            date_diff=0,
            date_tol=1,
            currency_match=1.0,
            weights=sample_weights,
        )
        assert scores["amount_score"] == 1.0
    
    def test_max_amount_diff_gives_zero_amount_score(self, sample_weights):
        """Test amount_score is 0.0 when diff equals tolerance."""
        scores = compute_match_scores(
            embed_sim=0.0,
            amount_diff=Decimal("100"),
            amount_tol=Decimal("100"),
            date_diff=0,
            date_tol=1,
            currency_match=1.0,
            weights=sample_weights,
        )
        assert scores["amount_score"] == 0.0
    
    def test_partial_amount_diff(self, sample_weights):
        """Test amount_score calculation with partial diff."""
        scores = compute_match_scores(
            embed_sim=0.0,
            amount_diff=Decimal("50"),
            amount_tol=Decimal("100"),
            date_diff=0,
            date_tol=1,
            currency_match=1.0,
            weights=sample_weights,
        )
        assert scores["amount_score"] == 0.5
    
    def test_currency_mismatch_gives_zero_currency_score(self, sample_weights):
        """Test currency_score is 0.0 when currencies don't match."""
        scores = compute_match_scores(
            embed_sim=1.0,
            amount_diff=Decimal("0"),
            amount_tol=Decimal("1"),
            date_diff=0,
            date_tol=1,
            currency_match=0.0,
            weights=sample_weights,
        )
        assert scores["currency_score"] == 0.0
        assert scores["global_score"] < 1.0
    
    def test_weights_affect_global_score(self):
        """Test that different weights produce different global scores."""
        weights1 = {"embedding": 0.9, "amount": 0.05, "currency": 0.025, "date": 0.025}
        weights2 = {"embedding": 0.1, "amount": 0.8, "currency": 0.05, "date": 0.05}
        
        # High embedding similarity, low amount match
        scores1 = compute_match_scores(
            embed_sim=0.9,
            amount_diff=Decimal("80"),
            amount_tol=Decimal("100"),
            date_diff=0,
            date_tol=1,
            currency_match=1.0,
            weights=weights1,
        )
        scores2 = compute_match_scores(
            embed_sim=0.9,
            amount_diff=Decimal("80"),
            amount_tol=Decimal("100"),
            date_diff=0,
            date_tol=1,
            currency_match=1.0,
            weights=weights2,
        )
        
        # With weight on embedding, score should be higher
        assert scores1["global_score"] > scores2["global_score"]


class TestQuantizeFunctions:
    """Unit tests for quantization and sign functions."""
    
    def test_q2_rounds_to_two_decimals(self):
        """Test q2 rounds to two decimal places."""
        assert q2(Decimal("1.234")) == Decimal("1.23")
        assert q2(Decimal("1.235")) == Decimal("1.24")  # Round half up
        assert q2(Decimal("1.999")) == Decimal("2.00")
    
    def test_sign_positive(self):
        """Test _sign returns 1 for positive numbers."""
        assert _sign(Decimal("100")) == 1
        assert _sign(Decimal("0.01")) == 1
    
    def test_sign_negative(self):
        """Test _sign returns -1 for negative numbers."""
        assert _sign(Decimal("-100")) == -1
        assert _sign(Decimal("-0.01")) == -1
    
    def test_sign_zero(self):
        """Test _sign returns 0 for zero."""
        assert _sign(Decimal("0")) == 0
        assert _sign(Decimal("0.00")) == 0


# ----------------------------------------------------------------------
# Unit Tests: Feasibility Pruning
# ----------------------------------------------------------------------

class TestFeasibilityBounds:
    """Unit tests for compute_feasibility_bounds function."""
    
    def test_g_min_computation_basic(self):
        """Test g_min is computed correctly for simple case."""
        amounts = [Decimal("100")] * 10  # 10 items of 100 each
        target = Decimal("500")
        tol = Decimal("0")
        feasible, g_min = compute_feasibility_bounds(amounts, target, tol, max_group_size=10)
        
        assert g_min == 5  # Need exactly 5 items
        assert feasible[5] == True
        assert feasible[4] == False
        assert feasible[6] == False
    
    def test_g_min_with_tolerance(self):
        """Test g_min computation with tolerance."""
        amounts = [Decimal("100")] * 10
        target = Decimal("450")
        tol = Decimal("50")  # 400-500 is feasible
        feasible, g_min = compute_feasibility_bounds(amounts, target, tol, max_group_size=10)
        
        assert g_min == 4  # 4 items = 400, which is in [400, 500]
        assert feasible[4] == True
        assert feasible[5] == True
        assert feasible[3] == False
    
    def test_g_min_no_feasible_size(self):
        """Test g_min is None when no size is feasible."""
        amounts = [Decimal("10")] * 5  # Max sum = 50
        target = Decimal("100")
        tol = Decimal("0")
        feasible, g_min = compute_feasibility_bounds(amounts, target, tol, max_group_size=5)
        
        assert g_min is None
        assert all(not f for f in feasible[1:])
    
    def test_g_min_only_full_group_feasible(self):
        """Test when only the full group is feasible (40+ books case)."""
        amounts = [Decimal("25")] * 40  # 40 items of 25 = 1000
        target = Decimal("1000")
        tol = Decimal("0")
        feasible, g_min = compute_feasibility_bounds(amounts, target, tol, max_group_size=40)
        
        assert g_min == 40  # Only full group is feasible
        assert feasible[40] == True
        assert feasible[39] == False
    
    def test_g_min_mixed_amounts(self):
        """Test g_min with varying amounts."""
        amounts = [Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40"), Decimal("50")]
        target = Decimal("60")
        tol = Decimal("5")  # 55-65 is feasible
        feasible, g_min = compute_feasibility_bounds(amounts, target, tol, max_group_size=5)
        
        # g_min should be 2 (max_sum for g=2 is 50+40=90, min_sum for g=2 is 10+20=30)
        # With tolerance, need to check if [min_sum, max_sum] intersects [55, 65]
        assert g_min == 2  # 50+20=70 or 40+30=70, intersects [55,65]
    
    def test_empty_amounts(self):
        """Test with empty amounts list."""
        amounts = []
        target = Decimal("100")
        tol = Decimal("0")
        feasible, g_min = compute_feasibility_bounds(amounts, target, tol, max_group_size=5)
        
        assert feasible == []
        assert g_min is None


# ----------------------------------------------------------------------
# Unit Tests: Embedding Average
# ----------------------------------------------------------------------

class TestAvgEmbedding:
    """Unit tests for _avg_embedding function."""
    
    def test_single_item(self):
        """Test averaging a single embedding."""
        item = create_book_dto(embedding=[1.0, 2.0, 3.0])
        result = _avg_embedding([item])
        assert result == [1.0, 2.0, 3.0]
    
    def test_multiple_items(self):
        """Test averaging multiple embeddings."""
        item1 = create_book_dto(id=1, embedding=[1.0, 0.0, 0.0])
        item2 = create_book_dto(id=2, embedding=[0.0, 1.0, 0.0])
        result = _avg_embedding([item1, item2])
        assert result == [0.5, 0.5, 0.0]
    
    def test_empty_list(self):
        """Test with empty list."""
        result = _avg_embedding([])
        assert result == []
    
    def test_none_embeddings(self):
        """Test with items that have no embeddings."""
        item = create_book_dto(embedding=None)
        item.embedding = None
        result = _avg_embedding([item])
        assert result == []


# ----------------------------------------------------------------------
# Integration Tests: Engine
# ----------------------------------------------------------------------

class TestReconciliationPipelineEngine:
    """Integration tests for ReconciliationPipelineEngine."""
    
    def test_exact_1to1_match(self, sample_pipeline_config):
        """Test exact 1-to-1 matching."""
        # Modify config for exact matching
        sample_pipeline_config.stages[0].type = "exact_1to1"
        sample_pipeline_config.stages[0].amount_tol = Decimal("0")
        
        bank = create_bank_dto(id=1, amount=Decimal("500.00"), date_val=date.today())
        book = create_book_dto(id=101, amount=Decimal("500.00"), date_val=date.today())
        
        engine = ReconciliationPipelineEngine(
            company_id=1,
            config=sample_pipeline_config,
        )
        results = engine.run([bank], [book])
        
        assert len(results) == 1
        assert results[0]["match_type"] == "exact_1to1"
        assert results[0]["bank_ids"] == [1]
        assert results[0]["journal_entries_ids"] == [101]
        assert results[0]["confidence_score"] == 1.0
    
    def test_fuzzy_1to1_match(self, sample_pipeline_config):
        """Test fuzzy 1-to-1 matching with tolerance."""
        sample_pipeline_config.stages[0].type = "fuzzy_1to1"
        sample_pipeline_config.stages[0].amount_tol = Decimal("1.00")
        
        bank = create_bank_dto(id=1, amount=Decimal("500.00"), date_val=date.today())
        book = create_book_dto(id=101, amount=Decimal("500.50"), date_val=date.today())
        
        engine = ReconciliationPipelineEngine(
            company_id=1,
            config=sample_pipeline_config,
        )
        results = engine.run([bank], [book])
        
        assert len(results) >= 1
        assert results[0]["match_type"] == "fuzzy_1to1"
        assert results[0]["confidence_score"] > 0.8
    
    def test_one_to_many_match(self, sample_pipeline_config):
        """Test one bank to many books matching."""
        sample_pipeline_config.stages[0].type = "one_to_many"
        sample_pipeline_config.stages[0].amount_tol = Decimal("0.01")
        
        bank = create_bank_dto(id=1, amount=Decimal("1000.00"), date_val=date.today())
        books = [
            create_book_dto(id=101, amount=Decimal("400.00"), date_val=date.today()),
            create_book_dto(id=102, amount=Decimal("600.00"), date_val=date.today()),
        ]
        
        engine = ReconciliationPipelineEngine(
            company_id=1,
            config=sample_pipeline_config,
        )
        results = engine.run([bank], books)
        
        # Should find the match
        assert len(results) >= 1
        matching_result = [r for r in results if r["match_type"] == "one_to_many"]
        assert len(matching_result) >= 1
        assert set(matching_result[0]["journal_entries_ids"]) == {101, 102}
    
    def test_many_to_one_match(self, sample_pipeline_config):
        """Test many banks to one book matching."""
        sample_pipeline_config.stages[0].type = "many_to_one"
        sample_pipeline_config.stages[0].amount_tol = Decimal("0.01")
        sample_pipeline_config.stages[0].max_group_size_bank = 5
        sample_pipeline_config.stages[0].max_group_size_book = 1
        
        banks = [
            create_bank_dto(id=1, amount=Decimal("300.00"), date_val=date.today()),
            create_bank_dto(id=2, amount=Decimal("700.00"), date_val=date.today()),
        ]
        book = create_book_dto(id=101, amount=Decimal("1000.00"), date_val=date.today())
        
        engine = ReconciliationPipelineEngine(
            company_id=1,
            config=sample_pipeline_config,
        )
        results = engine.run(banks, [book])
        
        assert len(results) >= 1
        matching_result = [r for r in results if r["match_type"] == "many_to_one"]
        assert len(matching_result) >= 1
    
    def test_no_double_matching(self, sample_pipeline_config):
        """Test that the same bank/book is not used twice."""
        sample_pipeline_config.stages[0].type = "fuzzy_1to1"
        sample_pipeline_config.stages[0].amount_tol = Decimal("10.00")
        
        bank = create_bank_dto(id=1, amount=Decimal("500.00"), date_val=date.today())
        books = [
            create_book_dto(id=101, amount=Decimal("500.00"), date_val=date.today()),
            create_book_dto(id=102, amount=Decimal("502.00"), date_val=date.today()),
        ]
        
        engine = ReconciliationPipelineEngine(
            company_id=1,
            config=sample_pipeline_config,
        )
        results = engine.run([bank], books)
        
        # Get primary matches only
        primary_matches = [r for r in results if r.get("is_primary", True)]
        
        # Bank 1 should only be matched once
        bank_1_matches = [r for r in primary_matches if 1 in r["bank_ids"]]
        assert len(bank_1_matches) <= 1
    
    def test_company_isolation(self, sample_pipeline_config):
        """Test that matching respects company boundaries."""
        sample_pipeline_config.stages[0].type = "exact_1to1"
        sample_pipeline_config.stages[0].amount_tol = Decimal("0")
        
        bank = create_bank_dto(id=1, amount=Decimal("500.00"), company_id=1)
        book_same = create_book_dto(id=101, amount=Decimal("500.00"), company_id=1)
        book_diff = create_book_dto(id=102, amount=Decimal("500.00"), company_id=2)
        
        engine = ReconciliationPipelineEngine(
            company_id=1,
            config=sample_pipeline_config,
        )
        results = engine.run([bank], [book_same, book_diff])
        
        # Should only match with the same company
        assert len(results) == 1
        assert 101 in results[0]["journal_entries_ids"]
        assert 102 not in results[0]["journal_entries_ids"]


# ----------------------------------------------------------------------
# Determinism Tests
# ----------------------------------------------------------------------

class TestDeterminism:
    """Tests for deterministic behavior."""
    
    def test_shuffled_input_same_results(self, sample_pipeline_config):
        """Test that shuffled input order yields identical results."""
        sample_pipeline_config.stages[0].type = "one_to_many"
        sample_pipeline_config.stages[0].amount_tol = Decimal("50.00")
        sample_pipeline_config.stages[0].max_alternatives_per_anchor = 5
        
        books_original = [
            create_book_dto(id=100+i, amount=Decimal(str(i * 100)), date_val=date.today())
            for i in range(1, 11)
        ]
        bank = create_bank_dto(id=1, amount=Decimal("500.00"), date_val=date.today())
        
        # Run with original order
        engine1 = ReconciliationPipelineEngine(company_id=1, config=sample_pipeline_config)
        result1 = engine1.run([bank], books_original)
        
        # Run with shuffled order
        books_shuffled = books_original.copy()
        random.seed(42)
        random.shuffle(books_shuffled)
        engine2 = ReconciliationPipelineEngine(company_id=1, config=sample_pipeline_config)
        result2 = engine2.run([bank], books_shuffled)
        
        # Should have same number of results
        assert len(result1) == len(result2)
        
        # Primary matches should be identical
        primary1 = sorted(
            [r for r in result1 if r.get("is_primary", True)],
            key=lambda r: (tuple(sorted(r["bank_ids"])), tuple(sorted(r["journal_entries_ids"])))
        )
        primary2 = sorted(
            [r for r in result2 if r.get("is_primary", True)],
            key=lambda r: (tuple(sorted(r["bank_ids"])), tuple(sorted(r["journal_entries_ids"])))
        )
        
        for r1, r2 in zip(primary1, primary2):
            assert sorted(r1["bank_ids"]) == sorted(r2["bank_ids"])
            assert sorted(r1["journal_entries_ids"]) == sorted(r2["journal_entries_ids"])
    
    def test_repeated_runs_same_results(self, sample_pipeline_config):
        """Test that repeated runs produce identical results."""
        sample_pipeline_config.stages[0].type = "fuzzy_1to1"
        
        banks = [create_bank_dto(id=i, amount=Decimal(str(100 * i))) for i in range(1, 6)]
        books = [create_book_dto(id=100+i, amount=Decimal(str(100 * i))) for i in range(1, 6)]
        
        results = []
        for _ in range(5):
            engine = ReconciliationPipelineEngine(company_id=1, config=sample_pipeline_config)
            results.append(engine.run(banks, books))
        
        # All runs should produce identical results
        first_result = results[0]
        for result in results[1:]:
            assert len(result) == len(first_result)
            for r1, r2 in zip(first_result, result):
                assert r1["bank_ids"] == r2["bank_ids"]
                assert r1["journal_entries_ids"] == r2["journal_entries_ids"]
                assert r1["confidence_score"] == r2["confidence_score"]


# ----------------------------------------------------------------------
# Feasibility Pruning Tests
# ----------------------------------------------------------------------

class TestFeasibilityPruning:
    """Tests for feasibility pruning behavior."""
    
    def test_40_books_edge_case(self, sample_pipeline_config):
        """
        Regression test: 40 books where only full group reaches target.
        Verify that the match is found quickly.
        """
        sample_pipeline_config.stages[0].type = "one_to_many"
        sample_pipeline_config.stages[0].amount_tol = Decimal("0")
        sample_pipeline_config.stages[0].max_group_size_book = 40
        
        # Create 40 books each worth 25, target = 1000
        books = [
            create_book_dto(id=100+i, amount=Decimal("25.00"), date_val=date.today())
            for i in range(40)
        ]
        bank = create_bank_dto(id=1, amount=Decimal("1000.00"), date_val=date.today())
        
        import time
        start = time.perf_counter()
        
        engine = ReconciliationPipelineEngine(company_id=1, config=sample_pipeline_config)
        results = engine.run([bank], books)
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        # Should find the match
        assert len(results) >= 1
        otm_results = [r for r in results if r["match_type"] == "one_to_many"]
        assert len(otm_results) >= 1
        assert len(otm_results[0]["journal_entries_ids"]) == 40
        
        # Should be fast due to feasibility pruning
        # (Without pruning, this would take exponential time)
        assert elapsed_ms < 5000, f"40-book case took {elapsed_ms}ms, should be much faster with pruning"
    
    def test_all_in_shortcut(self, sample_pipeline_config):
        """Test all-in shortcut when full group is exact match."""
        sample_pipeline_config.stages[0].type = "one_to_many"
        sample_pipeline_config.stages[0].amount_tol = Decimal("0")
        sample_pipeline_config.stages[0].max_group_size_book = 10
        
        books = [
            create_book_dto(id=100+i, amount=Decimal("250.00"), date_val=date.today())
            for i in range(4)
        ]
        bank = create_bank_dto(id=1, amount=Decimal("1000.00"), date_val=date.today())
        
        engine = ReconciliationPipelineEngine(company_id=1, config=sample_pipeline_config)
        results = engine.run([bank], books)
        
        # Should find the all-in match
        assert len(results) >= 1
        otm_results = [r for r in results if r["match_type"] == "one_to_many"]
        assert len(otm_results) >= 1
        assert len(otm_results[0]["journal_entries_ids"]) == 4


# ----------------------------------------------------------------------
# Alternatives Tests
# ----------------------------------------------------------------------

class TestAlternatives:
    """Tests for alternatives ranking and handling."""
    
    def test_alternatives_have_rank_fields(self, sample_pipeline_config):
        """Test that alternatives include rank metadata."""
        sample_pipeline_config.stages[0].type = "one_to_many"
        sample_pipeline_config.stages[0].amount_tol = Decimal("100.00")
        sample_pipeline_config.stages[0].max_alternatives_per_anchor = 5
        
        # Create multiple possible matches
        books = [
            create_book_dto(id=101, amount=Decimal("500.00"), date_val=date.today()),
            create_book_dto(id=102, amount=Decimal("520.00"), date_val=date.today()),
            create_book_dto(id=103, amount=Decimal("480.00"), date_val=date.today()),
        ]
        bank = create_bank_dto(id=1, amount=Decimal("500.00"), date_val=date.today())
        
        engine = ReconciliationPipelineEngine(company_id=1, config=sample_pipeline_config)
        results = engine.run([bank], books)
        
        # Should have multiple results
        assert len(results) >= 1
        
        # Primary result should have is_primary=True
        primary_results = [r for r in results if r.get("is_primary", False)]
        if primary_results:
            assert primary_results[0]["rank_among_alternatives"] == 1
    
    def test_alternatives_ranked_deterministically(self, sample_pipeline_config):
        """Test that alternatives are ranked in consistent order."""
        sample_pipeline_config.stages[0].type = "fuzzy_1to1"
        sample_pipeline_config.stages[0].amount_tol = Decimal("100.00")
        sample_pipeline_config.stages[0].max_alternatives_per_anchor = 10
        
        books = [
            create_book_dto(id=100+i, amount=Decimal(str(500 + i * 10)), date_val=date.today())
            for i in range(10)
        ]
        bank = create_bank_dto(id=1, amount=Decimal("500.00"), date_val=date.today())
        
        # Run multiple times
        all_runs = []
        for _ in range(3):
            engine = ReconciliationPipelineEngine(company_id=1, config=sample_pipeline_config)
            all_runs.append(engine.run([bank], books))
        
        # All runs should have same ordering
        for run in all_runs[1:]:
            assert len(run) == len(all_runs[0])
            for r1, r2 in zip(all_runs[0], run):
                assert r1.get("rank_among_alternatives") == r2.get("rank_among_alternatives")


# ----------------------------------------------------------------------
# Edge Cases
# ----------------------------------------------------------------------

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    def test_empty_banks(self, sample_pipeline_config):
        """Test handling of empty bank list."""
        books = [create_book_dto(id=101, amount=Decimal("100.00"))]
        
        engine = ReconciliationPipelineEngine(company_id=1, config=sample_pipeline_config)
        results = engine.run([], books)
        
        assert results == []
    
    def test_empty_books(self, sample_pipeline_config):
        """Test handling of empty book list."""
        banks = [create_bank_dto(id=1, amount=Decimal("100.00"))]
        
        engine = ReconciliationPipelineEngine(company_id=1, config=sample_pipeline_config)
        results = engine.run(banks, [])
        
        assert results == []
    
    def test_zero_amount_bank(self, sample_pipeline_config):
        """Test handling of zero amount bank transaction."""
        sample_pipeline_config.stages[0].type = "exact_1to1"
        
        bank = create_bank_dto(id=1, amount=Decimal("0.00"))
        book = create_book_dto(id=101, amount=Decimal("0.00"))
        
        engine = ReconciliationPipelineEngine(company_id=1, config=sample_pipeline_config)
        results = engine.run([bank], [book])
        
        # Should still match
        assert len(results) == 1
    
    def test_negative_amounts(self, sample_pipeline_config):
        """Test handling of negative amounts (credits)."""
        sample_pipeline_config.stages[0].type = "exact_1to1"
        sample_pipeline_config.stages[0].amount_tol = Decimal("0")
        
        bank = create_bank_dto(id=1, amount=Decimal("-500.00"))
        book = create_book_dto(id=101, amount=Decimal("-500.00"))
        
        engine = ReconciliationPipelineEngine(company_id=1, config=sample_pipeline_config)
        results = engine.run([bank], [book])
        
        assert len(results) == 1
    
    def test_large_date_gap_no_match(self, sample_pipeline_config):
        """Test that large date gaps prevent matching."""
        sample_pipeline_config.stages[0].type = "fuzzy_1to1"
        sample_pipeline_config.stages[0].avg_date_delta_days = 7
        
        bank = create_bank_dto(id=1, amount=Decimal("500.00"), date_val=date.today())
        book = create_book_dto(
            id=101,
            amount=Decimal("500.00"),
            date_val=date.today() - timedelta(days=30)
        )
        
        engine = ReconciliationPipelineEngine(company_id=1, config=sample_pipeline_config)
        results = engine.run([bank], [book])
        
        # Should not match due to date gap
        assert len(results) == 0
    
    def test_currency_mismatch_no_match(self, sample_pipeline_config):
        """Test that currency mismatches prevent matching."""
        sample_pipeline_config.stages[0].type = "exact_1to1"
        
        bank = create_bank_dto(id=1, amount=Decimal("500.00"), currency_id=1)
        book = create_book_dto(id=101, amount=Decimal("500.00"), currency_id=2)
        
        engine = ReconciliationPipelineEngine(company_id=1, config=sample_pipeline_config)
        results = engine.run([bank], [book])
        
        assert len(results) == 0


# ----------------------------------------------------------------------
# Performance Tests
# ----------------------------------------------------------------------

class TestPerformance:
    """Performance benchmarks (marked for optional slow runs)."""
    
    @pytest.mark.slow
    def test_large_dataset_performance(self, sample_pipeline_config):
        """Test performance with larger dataset."""
        sample_pipeline_config.stages[0].type = "fuzzy_1to1"
        sample_pipeline_config.max_runtime_seconds = 30
        
        # Create 1000 banks and 5000 books
        banks = [
            create_bank_dto(id=i, amount=Decimal(str(100 + (i % 100))))
            for i in range(1000)
        ]
        books = [
            create_book_dto(id=1000+i, amount=Decimal(str(100 + (i % 100))))
            for i in range(5000)
        ]
        
        import time
        start = time.perf_counter()
        
        engine = ReconciliationPipelineEngine(company_id=1, config=sample_pipeline_config)
        results = engine.run(banks, books)
        
        elapsed = time.perf_counter() - start
        
        # Should complete within reasonable time
        assert elapsed < 60, f"Large dataset took {elapsed}s, should be under 60s"
        
        # Should produce some results
        assert len(results) > 0

