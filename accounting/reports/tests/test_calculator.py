"""Tests for the calculator orchestration.

These are unit tests — the legacy calculation kernels (``_calc_ending_balance``
etc.) and the account resolver are stubbed out. The goal is to prove that the
calculator:

* Fans out over multiple periods.
* Computes variance periods from base/compare.
* Resolves formulas (including forward refs via second-pass settling).
* Applies ``sign_policy`` and returns a well-shaped result.
* Rejects incompatible report/period combos up front.

Integration tests that touch real GL data belong in PR 3 once the endpoints
land and fixtures exist.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from accounting.reports.services.calculator import Period, ReportCalculator
from accounting.reports.services.intelligence import AccountResolver


# --- Helpers ---------------------------------------------------------------


def _mk_calculator(per_account_value=100):
    """Build a calculator with the legacy kernel + account resolver mocked.

    The kernel returns ``per_account_value`` per account for every method.
    The account resolver returns one fake account for any pattern.
    """
    calc = ReportCalculator(company_id=1)

    # Mock the account resolver to return a single fake account whenever the
    # selector has any field set.
    fake_account = MagicMock(id=42, account_direction=1, is_active=True)

    def fake_resolve(selector):
        if selector is None:
            return []
        if (
            (getattr(selector, "account_ids", None) or [])
            or getattr(selector, "code_prefix", None)
            or getattr(selector, "path_contains", None)
        ):
            return [fake_account]
        return []

    calc._resolver.resolve = fake_resolve  # type: ignore[assignment]

    # Mock the legacy kernel methods.
    calc._legacy._calc_ending_balance = MagicMock(return_value=Decimal(str(per_account_value)))
    calc._legacy._calc_net_movement = MagicMock(return_value=Decimal(str(per_account_value)))
    calc._legacy._calc_debit_total = MagicMock(return_value=Decimal(str(per_account_value)))
    calc._legacy._calc_credit_total = MagicMock(return_value=Decimal(str(per_account_value)))
    return calc


def _dre_doc():
    return {
        "name": "DRE",
        "report_type": "income_statement",
        "defaults": {"calculation_method": "net_movement"},
        "blocks": [
            {
                "type": "section",
                "id": "revenue",
                "label": "Receita",
                "children": [
                    {"type": "line", "id": "sales", "label": "Vendas",
                     "accounts": {"code_prefix": "4.01"}},
                    {"type": "line", "id": "services", "label": "Serviços",
                     "accounts": {"code_prefix": "4.02"}},
                    {"type": "subtotal", "id": "rev_total", "label": "Total",
                     "formula": "sum(children)"},
                ],
            },
            {"type": "total", "id": "net_income", "label": "Resultado Líquido",
             "formula": "rev_total"},
        ],
    }


def _dre_periods_yoy():
    return [
        {"id": "cur", "label": "2025", "type": "range",
         "start": "2025-01-01", "end": "2025-12-31"},
        {"id": "prev", "label": "2024", "type": "range",
         "start": "2024-01-01", "end": "2024-12-31"},
        {"id": "var_abs", "label": "Δ", "type": "variance_abs",
         "base": "prev", "compare": "cur"},
        {"id": "var_pct", "label": "%", "type": "variance_pct",
         "base": "prev", "compare": "cur"},
    ]


# --- Tests ----------------------------------------------------------------


def test_single_period_basic():
    calc = _mk_calculator(per_account_value=150)
    result = calc.calculate(
        document=_dre_doc(),
        periods=[{"id": "cur", "label": "2025", "type": "range",
                  "start": "2025-01-01", "end": "2025-12-31"}],
    )

    # Each line (sales/services) has 1 account @ 150
    line_by_id = {l["id"]: l for l in result["lines"]}
    assert line_by_id["sales"]["values"]["cur"] == 150.0
    assert line_by_id["services"]["values"]["cur"] == 150.0

    # Subtotal with sum(children) sums the three direct children:
    #   sales(150) + services(150) + rev_total(0 on first pass)
    # After second-pass settle, rev_total should stabilize to 300.
    assert line_by_id["rev_total"]["values"]["cur"] == 300.0

    # Total block with formula "rev_total" references the subtotal
    assert line_by_id["net_income"]["values"]["cur"] == 300.0


def test_multi_period_yoy_and_variance():
    calc = _mk_calculator(per_account_value=100)

    # Make the kernel period-aware: return 120 for 2025, 100 for 2024
    def period_aware(accounts, start, end, include_pending):
        return Decimal("120") if start.year == 2025 else Decimal("100")

    calc._legacy._calc_net_movement = MagicMock(side_effect=period_aware)

    result = calc.calculate(document=_dre_doc(), periods=_dre_periods_yoy())
    by_id = {l["id"]: l for l in result["lines"]}

    # Absolute variance on a line: 120 - 100 = 20
    assert by_id["sales"]["values"]["cur"] == 120.0
    assert by_id["sales"]["values"]["prev"] == 100.0
    assert by_id["sales"]["values"]["var_abs"] == 20.0

    # Percentage variance: (120 - 100) / 100 * 100 = 20.00
    assert by_id["sales"]["values"]["var_pct"] == 20.0


def test_variance_pct_divide_by_zero_returns_zero():
    calc = _mk_calculator()

    def only_current(accounts, start, end, include_pending):
        return Decimal("50") if start.year == 2025 else Decimal("0")

    calc._legacy._calc_net_movement = MagicMock(side_effect=only_current)
    result = calc.calculate(document=_dre_doc(), periods=_dre_periods_yoy())
    by_id = {l["id"]: l for l in result["lines"]}
    # base is 0 → variance_pct defined as 0 (sentinel for "undefined")
    assert by_id["sales"]["values"]["var_pct"] == 0.0


def test_sign_policy_invert_applied():
    calc = _mk_calculator(per_account_value=50)
    doc = _dre_doc()
    doc["blocks"][0]["children"][0]["sign_policy"] = "invert"
    result = calc.calculate(
        document=doc,
        periods=[{"id": "cur", "label": "2025", "type": "range",
                  "start": "2025-01-01", "end": "2025-12-31"}],
    )
    by_id = {l["id"]: l for l in result["lines"]}
    assert by_id["sales"]["values"]["cur"] == -50.0


def test_header_and_spacer_produce_zero_without_touching_kernel():
    calc = _mk_calculator()
    doc = {
        "name": "T", "report_type": "income_statement",
        "blocks": [
            {"type": "header", "id": "h", "label": "Header"},
            {"type": "spacer", "id": "sp"},
            {"type": "line", "id": "a", "label": "A",
             "accounts": {"code_prefix": "4.01"}},
        ],
    }
    result = calc.calculate(
        document=doc,
        periods=[{"id": "cur", "label": "2025", "type": "range",
                  "start": "2025-01-01", "end": "2025-12-31"}],
    )
    by_id = {l["id"]: l for l in result["lines"]}
    assert by_id["h"]["values"]["cur"] == 0.0
    assert by_id["sp"]["values"]["cur"] == 0.0
    assert by_id["a"]["values"]["cur"] == 100.0


def test_balance_sheet_with_as_of_period():
    calc = _mk_calculator(per_account_value=500)
    doc = {
        "name": "BP", "report_type": "balance_sheet",
        "defaults": {"calculation_method": "ending_balance"},
        "blocks": [
            {"type": "line", "id": "assets", "label": "Ativo",
             "accounts": {"code_prefix": "1"}},
        ],
    }
    result = calc.calculate(
        document=doc,
        periods=[{"id": "now", "label": "2025-12-31", "type": "as_of",
                  "date": "2025-12-31"}],
    )
    by_id = {l["id"]: l for l in result["lines"]}
    assert by_id["assets"]["values"]["now"] == 500.0


def test_incompatible_period_type_rejected():
    calc = _mk_calculator()
    with pytest.raises(ValueError):
        calc.calculate(
            document=_dre_doc(),  # income_statement
            periods=[{"id": "x", "label": "x", "type": "as_of",
                      "date": "2025-12-31"}],
        )


def test_variance_references_unknown_period_rejected():
    calc = _mk_calculator()
    with pytest.raises(ValueError):
        calc.calculate(
            document=_dre_doc(),
            periods=[
                {"id": "cur", "label": "2025", "type": "range",
                 "start": "2025-01-01", "end": "2025-12-31"},
                {"id": "v", "label": "Δ", "type": "variance_abs",
                 "base": "not_a_period", "compare": "cur"},
            ],
        )


def test_account_count_zero_emits_warning():
    calc = _mk_calculator()
    # Override resolver to return empty for this specific selector
    calc._resolver.resolve = lambda sel: []  # type: ignore[assignment]

    doc = {
        "name": "T", "report_type": "income_statement",
        "blocks": [
            {"type": "line", "id": "empty", "label": "X",
             "accounts": {"code_prefix": "9.99"}, "calculation_method": "net_movement"},
        ],
    }
    result = calc.calculate(
        document=doc,
        periods=[{"id": "cur", "label": "2025", "type": "range",
                  "start": "2025-01-01", "end": "2025-12-31"}],
    )
    warns = result["warnings"]
    assert any("no accounts" in w["message"] for w in warns)
    by_id = {l["id"]: l for l in result["lines"]}
    assert by_id["empty"]["values"]["cur"] == 0.0


def test_result_shape():
    calc = _mk_calculator()
    result = calc.calculate(
        document=_dre_doc(),
        periods=_dre_periods_yoy(),
    )
    assert set(result.keys()) == {"periods", "template", "lines", "warnings"}
    assert len(result["periods"]) == 4
    assert result["template"]["report_type"] == "income_statement"
    for line in result["lines"]:
        assert {"id", "type", "label", "depth", "indent", "bold", "parent_id",
                "values", "memory"}.issubset(line.keys())
