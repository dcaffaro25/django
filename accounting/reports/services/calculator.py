"""
Report calculator — pure function from ``(document, periods, options)`` to a
result object. No DB writes. Stateless across calls (per-call caches only).

Composition over inheritance: an internal ``FinancialStatementGenerator``
instance from the legacy module provides the account-level calculation
kernels (``_calc_ending_balance``, ``_calc_net_movement``, etc.). We never
touch the legacy ORM classes directly — we read accounts with our own
resolver and call the kernels as free functions bound to a temporary legacy
instance. The legacy module stays untouched.

Response shape matches the plan:

.. code-block:: json

    {
      "periods": [...],              # echoed after validation
      "template": { ... },           # the resolved (defaults cascaded) doc
      "lines": [
        {
          "id": "revenue_gross",
          "label": "...",
          "type": "subtotal",
          "depth": 1,
          "bold": true,
          "values": {"cur": 1200000, "prev": 950000, "var_abs": 250000, "var_pct": 26.32},
          "memory": {"cur": {"account_ids": [...], "raw_total": 1200000.00}}
        }
      ],
      "totals": {"revenue_net": {"cur": 1100000, ...}},
      "warnings": [{"level": "warn", "block_id": "taxes", "message": "..."}]
    }
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from accounting.services.financial_statement_service import FinancialStatementGenerator

from .document_schema import TemplateDocument, validate_document
from .intelligence import (
    AccountResolver,
    FormulaError,
    FormulaEvaluator,
    ResolvedBlock,
    flatten_blocks,
    validate_period_compat,
)


# --- Input dataclasses -----------------------------------------------------


@dataclass
class Period:
    """A single column of the output.

    Concrete types (``range``, ``as_of``) reach the calculation kernel;
    variance types (``variance_abs``, ``variance_pct``, ``variance_pp``) are
    computed post-hoc off two other periods.
    """
    id: str
    label: str
    type: str
    start: Optional[date] = None
    end: Optional[date] = None
    date: Optional[date] = None   # for as_of
    base: Optional[str] = None    # for variance*
    compare: Optional[str] = None # for variance*


@dataclass
class Options:
    include_pending: bool = False
    currency_id: Optional[int] = None
    cost_center_id: Optional[int] = None


@dataclass
class Warning:
    level: str  # "info" | "warn" | "error"
    block_id: Optional[str]
    message: str


# --- Parser for raw input dicts -------------------------------------------


def _parse_periods(raw: List[dict]) -> List[Period]:
    out: List[Period] = []
    for r in raw:
        pid = r["id"]
        ptype = r["type"]
        start = _parse_date(r.get("start")) if ptype == "range" else None
        end = _parse_date(r.get("end")) if ptype == "range" else None
        as_of = _parse_date(r.get("date")) if ptype == "as_of" else None
        out.append(Period(
            id=pid,
            label=r.get("label", pid),
            type=ptype,
            start=start,
            end=end,
            date=as_of,
            base=r.get("base"),
            compare=r.get("compare"),
        ))
    return out


def _parse_date(v: Any) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    return date.fromisoformat(v)


def _parse_options(raw: Optional[dict]) -> Options:
    raw = raw or {}
    return Options(
        include_pending=bool(raw.get("include_pending", False)),
        currency_id=raw.get("currency_id"),
        cost_center_id=raw.get("cost_center_id"),
    )


# --- Calculator -----------------------------------------------------------


class ReportCalculator:
    """Stateless-across-calls orchestrator for a single ``/calculate/`` call.

    Caches legacy-kernel reuse, account resolution, and per-period balance
    prefetches for the duration of this instance. Construct one per request.
    """

    def __init__(self, company_id: int):
        self.company_id = company_id
        self._legacy = FinancialStatementGenerator(company_id=company_id)
        self._resolver = AccountResolver(company_id=company_id)

    # -- Public entry point ------------------------------------------------

    def calculate(
        self,
        document: dict | TemplateDocument,
        periods: List[dict] | List[Period],
        options: Optional[dict | Options] = None,
    ) -> dict:
        doc = document if isinstance(document, TemplateDocument) else validate_document(document)
        period_list = periods if periods and isinstance(periods[0], Period) else _parse_periods(periods)
        opts = options if isinstance(options, Options) else _parse_options(options)

        warnings: List[Warning] = []

        # Period-type compatibility
        for p in period_list:
            try:
                validate_period_compat(doc.report_type, p.type)
            except ValueError as e:
                raise ValueError(f"period '{p.id}': {e}") from e

        # Cross-refs for variance periods
        by_id: Dict[str, Period] = {p.id: p for p in period_list}
        for p in period_list:
            if p.type.startswith("variance"):
                if not p.base or not p.compare:
                    raise ValueError(f"variance period '{p.id}' needs both 'base' and 'compare'")
                if p.base not in by_id or p.compare not in by_id:
                    raise ValueError(f"variance period '{p.id}': base/compare must reference other periods")

        resolved_blocks = flatten_blocks(doc)

        # Calculate values per concrete period
        values_by_period: Dict[str, Dict[str, Decimal]] = {}
        memory_by_period: Dict[str, Dict[str, dict]] = {}
        for p in period_list:
            if p.type.startswith("variance"):
                continue
            values, memory = self._calculate_period(
                resolved_blocks, p, opts, warnings,
            )
            values_by_period[p.id] = values
            memory_by_period[p.id] = memory

        # Derive variance periods
        for p in period_list:
            if not p.type.startswith("variance"):
                continue
            values_by_period[p.id] = self._compute_variance(
                kind=p.type,
                base_values=values_by_period[p.base],
                compare_values=values_by_period[p.compare],
            )

        # Build the response
        lines_out: List[dict] = []
        for blk in resolved_blocks:
            values = {pid: _decimal_to_float(values_by_period[pid].get(blk.id, Decimal("0"))) for pid in values_by_period}
            memory = {pid: memory_by_period[pid].get(blk.id) for pid in memory_by_period if memory_by_period[pid].get(blk.id)}
            lines_out.append({
                "id": blk.id,
                "type": blk.type,
                "label": blk.label,
                "depth": blk.depth,
                "indent": blk.indent,
                "bold": blk.bold,
                "parent_id": blk.parent_id,
                "values": values,
                "memory": memory,
            })

        return {
            "periods": [_period_to_dict(p) for p in period_list],
            "template": doc.model_dump(mode="json"),
            "lines": lines_out,
            "warnings": [w.__dict__ for w in warnings],
        }

    # -- Per-period engine -------------------------------------------------

    def _calculate_period(
        self,
        blocks: List[ResolvedBlock],
        period: Period,
        options: Options,
        warnings: List[Warning],
    ) -> tuple[Dict[str, Decimal], Dict[str, dict]]:
        """Run every block for a single concrete period.

        Order: document (pre-order) order for account/stock/flow measures;
        formula / rollup_children blocks pick up values computed earlier in
        the same iteration (so ``sum(children)`` works as long as children
        appear before their subtotal in doc order — which they do for a
        subtotal placed *at the end* of a section, the conventional layout).

        For ``rollup_children`` or ``sum(children)`` on a subtotal that
        appears *before* its children, we do a second pass.
        """
        values: Dict[str, Decimal] = {}
        memory: Dict[str, dict] = {}

        for blk in blocks:
            if blk.type in ("header", "spacer"):
                values[blk.id] = Decimal("0")
                continue

            try:
                v, mem = self._calculate_block(blk, period, options, values, warnings)
            except FormulaError as e:
                warnings.append(Warning("warn", blk.id, f"formula error: {e}"))
                v, mem = Decimal("0"), None
            except ValueError as e:
                warnings.append(Warning("warn", blk.id, str(e)))
                v, mem = Decimal("0"), None

            # Apply sign policy
            v = _apply_sign(v, blk.sign_policy)
            values[blk.id] = v
            if mem is not None:
                memory[blk.id] = mem

        # Second pass: any subtotals/totals whose formula referenced
        # forward-declared blocks will be wrong on pass 1. Re-run formula
        # blocks now that every id has a value. Iterate a few times to settle
        # chained formulas; bail on divergence.
        formula_blocks = [b for b in blocks if (b.formula or b.calculation_method in ("formula", "rollup_children"))]
        if formula_blocks:
            for _pass in range(4):
                changed = False
                for blk in formula_blocks:
                    try:
                        v_new, _ = self._evaluate_formula_or_rollup(blk, values)
                    except FormulaError as e:
                        warnings.append(Warning("warn", blk.id, f"formula re-eval: {e}"))
                        continue
                    v_new = _apply_sign(v_new, blk.sign_policy)
                    if v_new != values.get(blk.id):
                        values[blk.id] = v_new
                        changed = True
                if not changed:
                    break

        return values, memory

    def _calculate_block(
        self,
        blk: ResolvedBlock,
        period: Period,
        options: Options,
        values_so_far: Dict[str, Decimal],
        warnings: List[Warning],
    ) -> tuple[Decimal, Optional[dict]]:
        """Return ``(value, memory)`` for a single block in a single period."""
        # Formula / rollup_children: depends only on other block values.
        # An explicit ``formula`` always wins over an inherited calculation_method
        # (subtotals in a doc with default ``net_movement`` should still sum
        # children, not query the GL with an empty selector).
        if (
            blk.formula
            or blk.calculation_method in ("formula", "rollup_children")
            or (blk.type in ("subtotal", "total") and not blk.accounts)
        ):
            v, _ = self._evaluate_formula_or_rollup(blk, values_so_far)
            return v, None

        # Manual input
        if blk.calculation_method == "manual_input":
            if blk.manual_value is None:
                return Decimal("0"), None
            return Decimal(str(blk.manual_value)), {"source": "manual_input"}

        # Account-backed calculations
        accounts = self._resolver.resolve(blk.accounts)
        if blk.type == "line" and not accounts:
            warnings.append(Warning("warn", blk.id, "no accounts matched selector — contributed 0"))

        account_ids = [a.id for a in accounts]
        memory: dict = {
            "account_ids": account_ids,
            "account_count": len(accounts),
            "calc_method": blk.calculation_method,
            "period_type": period.type,
        }

        if not accounts:
            return Decimal("0"), memory

        method = blk.calculation_method or _default_method_for_period(period.type)
        value = self._run_kernel(method, accounts, period, options, warnings, blk)
        memory["raw_total"] = _decimal_to_float(value)
        return value, memory

    def _evaluate_formula_or_rollup(
        self, blk: ResolvedBlock, values: Dict[str, Decimal],
    ) -> tuple[Decimal, None]:
        if blk.calculation_method == "rollup_children":
            # Sum direct children (non-spacer, non-header)
            total = Decimal("0")
            for cid in blk.child_ids:
                if cid in values:
                    total += values[cid]
            return total, None

        # Formula: either explicit formula string, or default "sum(children)"
        # if the block is a subtotal/total with a running group of sibling
        # line blocks (or a section with direct children).
        expr = blk.formula
        if not expr:
            if blk.type == "section" and blk.child_ids:
                expr = "sum(children)"
            elif blk.type in ("subtotal", "total") and blk.sibling_line_ids:
                expr = "sum(children)"
        if not expr:
            return Decimal("0"), None

        # Pick the right "children" cohort per block type. For sections it's
        # direct tree children; for subtotals/totals it's the running group of
        # preceding line siblings (standard accountant semantics).
        if blk.type in ("subtotal", "total"):
            source_ids = blk.sibling_line_ids
        else:
            source_ids = blk.child_ids
        child_values = [values[cid] for cid in source_ids if cid in values]
        evaluator = FormulaEvaluator(block_values=values, child_values=child_values)
        return evaluator.evaluate(expr), None

    def _run_kernel(
        self,
        method: str,
        accounts: list,
        period: Period,
        options: Options,
        warnings: List[Warning],
        blk: ResolvedBlock,
    ) -> Decimal:
        """Dispatch to the legacy calc helper matching ``method``."""
        inc = options.include_pending
        if method == "ending_balance":
            if period.type == "range":
                as_of = period.end
            elif period.type == "as_of":
                as_of = period.date
            else:
                raise ValueError(f"method 'ending_balance' cannot run on period type {period.type}")
            return self._legacy._calc_ending_balance(accounts, as_of, inc)

        if method == "opening_balance":
            if period.type != "range" or period.start is None:
                raise ValueError("'opening_balance' requires a range period")
            opening_date = period.start - timedelta(days=1)
            return self._legacy._calc_ending_balance(accounts, opening_date, inc)

        if method == "net_movement":
            if period.type != "range":
                raise ValueError("'net_movement' requires a range period")
            return self._legacy._calc_net_movement(accounts, period.start, period.end, inc)

        if method == "debit_total":
            if period.type != "range":
                raise ValueError("'debit_total' requires a range period")
            return self._legacy._calc_debit_total(accounts, period.start, period.end, inc)

        if method == "credit_total":
            if period.type != "range":
                raise ValueError("'credit_total' requires a range period")
            return self._legacy._calc_credit_total(accounts, period.start, period.end, inc)

        if method == "change_in_balance":
            if period.type != "range" or period.start is None:
                raise ValueError("'change_in_balance' requires a range period")
            opening = self._legacy._calc_ending_balance(accounts, period.start - timedelta(days=1), inc)
            ending = self._legacy._calc_ending_balance(accounts, period.end, inc)
            return ending - opening

        warnings.append(Warning("warn", blk.id, f"unknown calculation method '{method}' → 0"))
        return Decimal("0")

    # -- Variance helpers --------------------------------------------------

    def _compute_variance(
        self, kind: str, base_values: Dict[str, Decimal], compare_values: Dict[str, Decimal],
    ) -> Dict[str, Decimal]:
        out: Dict[str, Decimal] = {}
        all_ids = set(base_values) | set(compare_values)
        for bid in all_ids:
            base = base_values.get(bid, Decimal("0"))
            cmp_ = compare_values.get(bid, Decimal("0"))
            if kind == "variance_abs":
                out[bid] = cmp_ - base
            elif kind in ("variance_pct", "variance_pp"):
                if base == 0:
                    # Represent undefined as 0 and rely on client to render — a
                    # sentinel None would force us to permit None in the values
                    # map, complicating downstream consumers.
                    out[bid] = Decimal("0")
                else:
                    out[bid] = (cmp_ - base) / abs(base) * Decimal("100")
            else:
                out[bid] = Decimal("0")
        return out


# --- Helpers --------------------------------------------------------------


def _apply_sign(value: Decimal, sign_policy: str) -> Decimal:
    if sign_policy == "invert":
        return -value
    if sign_policy == "absolute":
        return abs(value)
    return value


def _default_method_for_period(period_type: str) -> str:
    """Sensible calc-method default when a block doesn't specify one.

    Lets simple templates omit ``calculation_method`` on every block and rely
    on period semantics: a range implies a flow (``net_movement``), an as-of
    implies a stock (``ending_balance``).
    """
    if period_type == "as_of":
        return "ending_balance"
    return "net_movement"


def _decimal_to_float(v: Decimal) -> float:
    """Lossy but consistent: two-decimal rounding at the transport boundary."""
    try:
        return float(v.quantize(Decimal("0.01")))
    except Exception:
        return float(v)


def _period_to_dict(p: Period) -> dict:
    d = {"id": p.id, "label": p.label, "type": p.type}
    if p.start:
        d["start"] = p.start.isoformat()
    if p.end:
        d["end"] = p.end.isoformat()
    if p.date:
        d["date"] = p.date.isoformat()
    if p.base:
        d["base"] = p.base
    if p.compare:
        d["compare"] = p.compare
    return d
