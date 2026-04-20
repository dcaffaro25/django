"""Tests for the intelligence helpers (tree walk, formula evaluator, compat)."""

from decimal import Decimal

import pytest

from accounting.reports.services.document_schema import validate_document
from accounting.reports.services.intelligence import (
    FormulaError,
    FormulaEvaluator,
    extract_refs,
    flatten_blocks,
    validate_period_compat,
)


# --- flatten_blocks --------------------------------------------------------


def _doc_with_nested_defaults():
    return validate_document({
        "name": "T",
        "report_type": "income_statement",
        "defaults": {"sign_policy": "natural", "decimal_places": 2},
        "blocks": [
            {
                "type": "section",
                "id": "rev",
                "label": "Receita",
                "defaults": {"calculation_method": "net_movement"},
                "children": [
                    {"type": "line", "id": "sales", "label": "Vendas"},
                    {"type": "line", "id": "services", "label": "Serviços",
                     "sign_policy": "invert"},
                    {"type": "subtotal", "id": "rev_total", "label": "Total"},
                ],
            },
            {"type": "spacer", "id": "sp1"},
            {"type": "total", "id": "net", "label": "Líquido", "formula": "rev_total"},
        ],
    })


def test_flatten_preorder_and_depth():
    doc = _doc_with_nested_defaults()
    blocks = flatten_blocks(doc)
    ids = [b.id for b in blocks]
    assert ids == ["rev", "sales", "services", "rev_total", "sp1", "net"]
    by_id = {b.id: b for b in blocks}
    assert by_id["rev"].depth == 0
    assert by_id["sales"].depth == 1
    assert by_id["net"].depth == 0


def test_flatten_cascades_defaults():
    doc = _doc_with_nested_defaults()
    by_id = {b.id: b for b in flatten_blocks(doc)}
    # Inherited from root
    assert by_id["sales"].decimal_places == 2
    # Inherited from section override
    assert by_id["sales"].calculation_method == "net_movement"
    # Per-block override wins
    assert by_id["services"].sign_policy == "invert"
    # Non-override falls through to default
    assert by_id["sales"].sign_policy == "natural"


def test_flatten_sets_parent_and_children():
    doc = _doc_with_nested_defaults()
    by_id = {b.id: b for b in flatten_blocks(doc)}
    assert by_id["sales"].parent_id == "rev"
    assert by_id["rev"].parent_id is None
    assert by_id["rev"].child_ids == ["sales", "services", "rev_total"]
    assert by_id["net"].child_ids == []


def test_flatten_tracks_sibling_line_ids_for_subtotals():
    """A subtotal's running group is the line-type siblings since the last
    subtotal/total in the same parent — the standard accountant semantic.
    """
    doc = validate_document({
        "name": "T", "report_type": "income_statement",
        "blocks": [
            {"type": "section", "id": "s", "label": "S", "children": [
                {"type": "line", "id": "a", "label": "A"},
                {"type": "line", "id": "b", "label": "B"},
                {"type": "subtotal", "id": "st1", "label": "ST1"},
                {"type": "line", "id": "c", "label": "C"},
                {"type": "line", "id": "d", "label": "D"},
                {"type": "subtotal", "id": "st2", "label": "ST2"},
            ]},
        ],
    })
    by_id = {b.id: b for b in flatten_blocks(doc)}
    assert by_id["st1"].sibling_line_ids == ["a", "b"]
    # ST2's group starts after ST1 — doesn't include a, b.
    assert by_id["st2"].sibling_line_ids == ["c", "d"]


# --- FormulaEvaluator ------------------------------------------------------


def _ev(values, children=None):
    return FormulaEvaluator(
        block_values={k: Decimal(str(v)) for k, v in values.items()},
        child_values=[Decimal(str(c)) for c in (children or [])],
    )


def test_arithmetic_basic():
    e = _ev({"a": 100, "b": 40})
    assert e.evaluate("a + b") == Decimal("140")
    assert e.evaluate("a - b") == Decimal("60")
    assert e.evaluate("a * 2") == Decimal("200")
    assert e.evaluate("a / 4") == Decimal("25")
    assert e.evaluate("-a + b * 2") == Decimal("-20")


def test_sum_children():
    e = _ev({}, children=[10, 20, 30])
    assert e.evaluate("sum(children)") == Decimal("60")


def test_min_max_abs():
    e = _ev({"a": -5, "b": 10})
    assert e.evaluate("abs(a)") == Decimal("5")
    assert e.evaluate("min(a, b)") == Decimal("-5")
    assert e.evaluate("max(a, b)") == Decimal("10")


def test_undefined_ref_raises():
    e = _ev({"a": 1})
    with pytest.raises(FormulaError):
        e.evaluate("a + missing")


def test_syntax_error_raises():
    e = _ev({"a": 1})
    with pytest.raises(FormulaError):
        e.evaluate("a + (")


def test_disallowed_syntax_rejected():
    e = _ev({"a": 1})
    with pytest.raises(FormulaError):
        e.evaluate("a ** 2")  # power op not allowed
    with pytest.raises(FormulaError):
        e.evaluate("__import__('os')")


def test_division_by_zero():
    e = _ev({"a": 10})
    with pytest.raises(FormulaError):
        e.evaluate("a / 0")


# --- extract_refs ----------------------------------------------------------


def test_extract_refs_ignores_functions_and_children():
    refs = extract_refs("sum(children) + abs(revenue) - taxes * 2")
    assert refs == {"revenue", "taxes"}


# --- Period / report-type compat ------------------------------------------


def test_income_statement_rejects_as_of():
    with pytest.raises(ValueError):
        validate_period_compat("income_statement", "as_of")


def test_balance_sheet_rejects_range():
    with pytest.raises(ValueError):
        validate_period_compat("balance_sheet", "range")


def test_variance_is_always_compatible():
    # Should not raise for any report type
    validate_period_compat("balance_sheet", "variance_pct")
    validate_period_compat("income_statement", "variance_abs")


def test_cash_flow_accepts_both():
    validate_period_compat("cash_flow", "range")
    validate_period_compat("cash_flow", "as_of")
