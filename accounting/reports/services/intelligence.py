"""
Coded-intelligence helpers — deterministic, fast, free.

Three building blocks the calculator leans on:

1. :func:`flatten_blocks` — walk the document tree, resolve inherited defaults
   (root → section → block), emit a depth-ordered list of ``ResolvedBlock``
   records plus parent/children maps. This is the ordering the calculator
   iterates over.

2. :class:`AccountResolver` — translate an ``AccountsSelector`` (code_prefix /
   path_contains / account_ids / include_descendants) into a concrete list of
   ``Account`` objects, mirroring the legacy
   ``FinancialStatementGenerator._get_accounts_for_line`` but reading from the
   new JSON-tree selector shape. Results are cached per-resolver instance so a
   template that matches 20 blocks against the same pattern only hits the DB
   once.

3. :class:`FormulaEvaluator` — parse and evaluate a name-based formula
   (``revenue - taxes``, ``sum(children)``, ``abs(L1)``). Uses Python's
   ``ast`` module for safe parsing (no ``eval``), supports +/-/*/// and
   unary minus, and a small whitelist of functions (``sum``, ``abs``,
   ``min``, ``max``). ``sum(children)`` resolves against the block's direct
   children (the calculator supplies them via ``bind_children``).

The legacy formula evaluator in ``accounting.services.formula_evaluator`` uses
``L{line_number}`` tokens — incompatible with our name-based references, so we
implement our own (simpler) safe evaluator here.

Also exposed: :func:`validate_period_compat` — raises :class:`ValueError`
when a period's ``type`` is incompatible with the document's ``report_type``
(e.g. an income statement with only ``as_of`` periods).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from django.db.models import Q

from accounting.models import Account

from .document_schema import (
    AccountsSelector,
    BlockDefaults,
    SectionBlock,
    SpacerBlock,
    TemplateDocument,
)


# --- Resolved block structure ----------------------------------------------


@dataclass
class ResolvedBlock:
    """A block with defaults already cascaded in.

    ``raw`` keeps the original pydantic model for any field the calculator
    might not consume via the resolved attributes (e.g. ``manual_value``).
    ``child_ids`` is the list of direct-child block ids in document order,
    used by ``sum(children)`` formula resolution and by the calculator's
    post-order subtotal pass.
    """
    id: str
    type: str
    label: Optional[str]
    depth: int
    parent_id: Optional[str]
    child_ids: List[str] = field(default_factory=list)
    # For subtotals/totals: the line-type siblings that belong to this
    # subtotal's "running group" — preceding line siblings (same parent, in
    # doc order, from the start-of-parent or the previous subtotal/total up
    # to this block). Empty for other block types. Used so
    # ``sum(children)`` works on subtotals the way accountants expect.
    sibling_line_ids: List[str] = field(default_factory=list)
    # Resolved (defaults cascaded) settings
    calculation_method: Optional[str] = None
    sign_policy: str = "natural"
    scale: str = "none"
    decimal_places: int = 2
    show_zero: bool = False
    bold: bool = False
    indent: int = 0
    # Pass-throughs from raw
    formula: Optional[str] = None
    manual_value: Optional[str] = None
    accounts: Optional[AccountsSelector] = None
    raw: Any = None


def flatten_blocks(doc: TemplateDocument) -> List[ResolvedBlock]:
    """Depth-first traversal with defaults cascaded and depth/parent tracked."""
    out: List[ResolvedBlock] = []

    def _defaults_merge(base: BlockDefaults, override: Optional[BlockDefaults]) -> BlockDefaults:
        if override is None:
            return base
        merged = base.model_dump()
        for k, v in override.model_dump().items():
            if v is not None:
                merged[k] = v
        return BlockDefaults(**merged)

    def _walk(
        blocks: Iterable[Any],
        current_defaults: BlockDefaults,
        depth: int,
        parent_id: Optional[str],
    ) -> List[str]:
        child_ids: List[str] = []
        # Track "line" siblings accumulating since the last subtotal/total in
        # this scope so we can assign them to the next subtotal/total block.
        running_line_siblings: List[str] = []

        for b in blocks:
            if isinstance(b, SectionBlock):
                bdefs = _defaults_merge(current_defaults, b.defaults)
                resolved = _make_resolved(b, bdefs, depth, parent_id)
                out.append(resolved)
                child_ids_for_section = _walk(b.children, bdefs, depth + 1, b.id)
                resolved.child_ids = child_ids_for_section
                child_ids.append(b.id)
                # A section is itself treated as a "group" — not a running line.
                running_line_siblings = []
            elif isinstance(b, SpacerBlock):
                out.append(ResolvedBlock(
                    id=b.id, type="spacer", label=None, depth=depth,
                    parent_id=parent_id, raw=b,
                ))
                child_ids.append(b.id)
            else:
                resolved = _make_resolved(b, current_defaults, depth, parent_id)
                if resolved.type in ("subtotal", "total"):
                    # This block owns the lines accumulated since the last
                    # subtotal/total break. sum(children) will sum them.
                    resolved.sibling_line_ids = list(running_line_siblings)
                    running_line_siblings = []
                elif resolved.type == "line":
                    running_line_siblings.append(resolved.id)
                out.append(resolved)
                child_ids.append(b.id)
        return child_ids

    def _make_resolved(b: Any, defaults: BlockDefaults, depth: int, parent_id: Optional[str]) -> ResolvedBlock:
        # Per-block overrides on the block itself (line/subtotal/total blocks
        # carry calculation_method, sign_policy, scale, decimal_places, bold,
        # show_zero). Spacers/headers do not.
        def pick(attr: str, fallback: Any) -> Any:
            v = getattr(b, attr, None)
            return v if v is not None else fallback

        return ResolvedBlock(
            id=getattr(b, "id"),
            type=getattr(b, "type"),
            label=getattr(b, "label", None),
            depth=depth,
            parent_id=parent_id,
            calculation_method=pick("calculation_method", defaults.calculation_method),
            sign_policy=pick("sign_policy", defaults.sign_policy or "natural"),
            scale=pick("scale", defaults.scale or "none"),
            decimal_places=pick("decimal_places", defaults.decimal_places if defaults.decimal_places is not None else 2),
            show_zero=pick("show_zero", defaults.show_zero if defaults.show_zero is not None else False),
            bold=pick("bold", defaults.bold if defaults.bold is not None else False),
            indent=getattr(b, "indent", None) or depth,
            formula=getattr(b, "formula", None),
            manual_value=getattr(b, "manual_value", None),
            accounts=getattr(b, "accounts", None),
            raw=b,
        )

    _walk(doc.blocks, doc.defaults, depth=0, parent_id=None)
    return out


# --- Period / report-type compatibility ------------------------------------


_INCOMPATIBLE: Dict[str, Set[str]] = {
    # Income statement is pure flow — no as_of snapshots.
    "income_statement": {"as_of"},
    # Balance sheet is pure stock — no ranges.
    "balance_sheet": {"range"},
    # Cash flow accepts both (opening = as_of, movements = range).
    # Custom + others: accept anything.
}


def validate_period_compat(report_type: str, period_type: str) -> None:
    """Raise ``ValueError`` if ``period_type`` doesn't suit ``report_type``.

    Variance period types are compatible with everything — they compute off
    two existing concrete periods.
    """
    if period_type.startswith("variance"):
        return
    incompatible = _INCOMPATIBLE.get(report_type, set())
    if period_type in incompatible:
        raise ValueError(
            f"period type '{period_type}' is not valid for report_type "
            f"'{report_type}' (only stock/flow semantics apply here)"
        )


# --- Account resolver ------------------------------------------------------


class AccountResolver:
    """Resolve :class:`AccountsSelector` → concrete ``Account`` list.

    Caches both pattern lookups and the expansion to leaves so repeated
    patterns across a template only hit the DB once.
    """

    def __init__(self, company_id: int):
        self.company_id = company_id
        self._pattern_cache: Dict[Tuple[Any, ...], List[Account]] = {}
        self._leaves_cache: Dict[int, List[Account]] = {}

    def resolve(self, selector: Optional[AccountsSelector]) -> List[Account]:
        """Return the concrete account list a selector matches.

        Empty selector (or no selector) → empty list. Callers that treat that
        as zero and emit a warning stay consistent with the legacy behavior.
        """
        if selector is None:
            return []

        key = (
            tuple(selector.account_ids or []),
            selector.code_prefix or "",
            selector.path_contains or "",
            selector.include_descendants,
        )
        cached = self._pattern_cache.get(key)
        if cached is not None:
            return cached

        qs = Account.objects.filter(company_id=self.company_id, is_active=True)
        filters = Q()
        any_filter = False

        if selector.account_ids:
            filters |= Q(id__in=selector.account_ids)
            any_filter = True
        if selector.code_prefix:
            filters |= Q(account_code__startswith=selector.code_prefix)
            any_filter = True
        if selector.path_contains:
            filters |= Q(path__icontains=selector.path_contains)
            any_filter = True

        if not any_filter:
            self._pattern_cache[key] = []
            return []

        accounts: List[Account] = list(qs.filter(filters))

        if selector.include_descendants:
            accounts = self._expand_to_leaves_with_self(accounts)

        self._pattern_cache[key] = accounts
        return accounts

    def _expand_to_leaves_with_self(self, roots: List[Account]) -> List[Account]:
        """Include leaf descendants plus any root that itself has entries.

        Mirrors the legacy ``_get_accounts_for_line`` behavior where a parent
        account that has direct journal entries posted to it is included in
        the calculation alongside its expanded leaves (common when bookkeepers
        post to a mid-level account instead of a leaf).
        """
        from accounting.models import JournalEntry  # local to avoid import cycles

        if not roots:
            return []
        seen: Dict[int, Account] = {}

        for root in roots:
            # Try the MPTT ``get_descendants`` if present; fall back to a
            # recursive walk via ``children``.
            if hasattr(root, "get_descendants"):
                try:
                    descendants = list(root.get_descendants(include_self=False))
                except Exception:
                    descendants = []
            else:
                descendants = []

            leaves: List[Account] = []
            for a in descendants:
                if not a.is_active:
                    continue
                has_children = (
                    a.get_descendant_count() > 0
                    if hasattr(a, "get_descendant_count")
                    else False
                )
                if not has_children:
                    leaves.append(a)

            # If a root has direct JE activity, include it even when it has
            # children — same rule the legacy engine applies.
            if leaves or not descendants:
                root_has_entries = JournalEntry.objects.filter(
                    account=root,
                    transaction__company_id=self.company_id,
                ).exists()
                if root_has_entries:
                    seen.setdefault(root.id, root)

            for leaf in leaves:
                seen.setdefault(leaf.id, leaf)

            if not leaves and not descendants:
                # Treat as a leaf itself
                seen.setdefault(root.id, root)

        return list(seen.values())


# --- Formula evaluator -----------------------------------------------------


class FormulaError(ValueError):
    """Raised when a formula cannot be parsed or evaluated."""


_ALLOWED_BIN_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd)
_ALLOWED_FUNCS = ("sum", "abs", "min", "max")


class FormulaEvaluator:
    """Safe evaluator for name-based formulas.

    Supported syntax:

    * references to other blocks by id — ``revenue - taxes``
    * literal integers / floats — ``0.15``
    * unary ``+``/``-``
    * binary ``+``, ``-``, ``*``, ``/``
    * parentheses
    * whitelisted function calls — ``sum(...)``, ``abs(...)``, ``min(...)``, ``max(...)``
    * the special identifier ``children`` — resolves to the list of direct child
      block values; only valid inside ``sum(children)`` (or ``min``/``max``).

    Unsupported: attribute access, subscripting, comprehensions, lambdas,
    booleans, string literals, anything not in the list above.
    """

    def __init__(self, block_values: Dict[str, Decimal], child_values: Optional[List[Decimal]] = None):
        self.block_values = block_values
        self.child_values = child_values or []

    def evaluate(self, expr: str) -> Decimal:
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError as e:
            raise FormulaError(f"syntax error in formula: {e}") from e
        return self._walk(tree.body)

    # --- AST walker -------------------------------------------------------

    def _walk(self, node: ast.AST) -> Decimal:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return Decimal(str(node.value))
            raise FormulaError(f"unsupported literal: {node.value!r}")

        if isinstance(node, ast.Name):
            name = node.id
            if name == "children":
                raise FormulaError("'children' may only appear inside sum/min/max/abs()")
            if name not in self.block_values:
                raise FormulaError(f"undefined reference: {name!r}")
            return self.block_values[name]

        if isinstance(node, ast.UnaryOp):
            if not isinstance(node.op, (ast.UAdd, ast.USub)):
                raise FormulaError("unsupported unary operator")
            v = self._walk(node.operand)
            return -v if isinstance(node.op, ast.USub) else v

        if isinstance(node, ast.BinOp):
            if not isinstance(node.op, _ALLOWED_BIN_OPS):
                raise FormulaError("unsupported binary operator")
            left = self._walk(node.left)
            right = self._walk(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                if right == 0:
                    raise FormulaError("division by zero")
                return left / right

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
                raise FormulaError("only sum/abs/min/max allowed as function calls")
            fname = node.func.id
            args = self._resolve_call_args(node.args, fname)
            if fname == "sum":
                return sum(args, Decimal("0"))
            if fname == "abs":
                if len(args) != 1:
                    raise FormulaError("abs() takes exactly one argument")
                return abs(args[0])
            if fname == "min":
                return min(args) if args else Decimal("0")
            if fname == "max":
                return max(args) if args else Decimal("0")

        raise FormulaError(f"unsupported expression node: {type(node).__name__}")

    def _resolve_call_args(self, nodes: List[ast.AST], fname: str) -> List[Decimal]:
        """Expand the special ``children`` identifier in-place for variadic funcs."""
        out: List[Decimal] = []
        for n in nodes:
            if isinstance(n, ast.Name) and n.id == "children":
                out.extend(self.child_values)
            else:
                out.append(self._walk(n))
        return out


# --- Convenience: references used by a formula (for static checks) ---------


def extract_refs(expr: str) -> Set[str]:
    """Return the set of block-id references used by ``expr``.

    ``children`` and whitelisted function names are excluded. Raises
    :class:`FormulaError` on a syntactically invalid expression.
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise FormulaError(f"syntax error: {e}") from e

    refs: Set[str] = set()
    func_names = set(_ALLOWED_FUNCS) | {"children"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            # The function name itself is not a ref
            continue
        if isinstance(node, ast.Name) and node.id not in func_names:
            refs.add(node.id)
    return refs
