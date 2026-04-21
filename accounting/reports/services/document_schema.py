"""
Canonical template document schema for the new report engine.

The document is the single source of truth for a ``ReportTemplate``. It is a
tree of typed blocks (section / line / subtotal / total / spacer / header)
validated by pydantic on every write.

Key design points:

* **Named IDs** — every non-spacer block carries a stable ``id`` referenced by
  formulas. IDs survive reorders; formulas never break from row moves.
* **Defaults cascade** — root ``defaults`` apply to all blocks; a section's
  ``defaults`` override root for its subtree; individual blocks override above.
* **Pattern account selectors** — lines reference accounts by pattern
  (``code_prefix``, ``path_contains``, explicit ``account_ids``); resolution
  happens at calculate-time.
* **Native hierarchy** — sections contain ``children``; ``sum(children)``
  is a built-in formula.

This module only validates shape and cross-reference integrity. Semantic
validation (e.g. a BP template shouldn't use ``net_movement``) is enforced at
calculate-time in :mod:`accounting.reports.services.calculator`.
"""

from __future__ import annotations

from typing import Any, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# --- Enums ------------------------------------------------------------------

ReportType = Literal[
    "balance_sheet",
    "income_statement",
    "cash_flow",
    "trial_balance",
    "general_ledger",
    "custom",
]

CalculationMethod = Literal[
    "ending_balance",
    "opening_balance",
    "net_movement",
    "debit_total",
    "credit_total",
    "change_in_balance",
    "rollup_children",
    "formula",
    "manual_input",
]

SignPolicy = Literal["natural", "invert", "absolute"]
Scale = Literal["none", "K", "M", "B"]


# --- Sub-models -------------------------------------------------------------

class AccountsSelector(BaseModel):
    """How a ``line`` / ``subtotal`` / ``total`` block picks its accounts.

    At least one of ``account_ids``, ``code_prefix``, or ``path_contains``
    should be set (validated at calc-time; an empty selector resolves to zero
    but emits a warning).
    """
    model_config = ConfigDict(extra="forbid")

    account_ids: Optional[List[int]] = None
    code_prefix: Optional[str] = None
    path_contains: Optional[str] = None
    include_descendants: bool = True


class BlockDefaults(BaseModel):
    """Defaults that cascade down the tree. All fields optional; missing
    values fall through to the parent (or root) defaults.
    """
    model_config = ConfigDict(extra="forbid")

    calculation_method: Optional[CalculationMethod] = None
    sign_policy: Optional[SignPolicy] = None
    scale: Optional[Scale] = None
    decimal_places: Optional[int] = Field(default=None, ge=0, le=8)
    show_zero: Optional[bool] = None
    bold: Optional[bool] = None


# --- Blocks -----------------------------------------------------------------

class _BlockBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    label: Optional[str] = Field(default=None, max_length=200)
    bold: Optional[bool] = None
    indent: Optional[int] = Field(default=None, ge=0, le=8)
    # Optional AI-produced explanation — client-side only; stripped on save if you want.
    ai_explanation: Optional[str] = Field(default=None, max_length=2000)


class HeaderBlock(_BlockBase):
    type: Literal["header"]


class SpacerBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["spacer"]
    id: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")


class LineBlock(_BlockBase):
    type: Literal["line"]
    accounts: Optional[AccountsSelector] = None
    calculation_method: Optional[CalculationMethod] = None
    sign_policy: Optional[SignPolicy] = None
    scale: Optional[Scale] = None
    decimal_places: Optional[int] = Field(default=None, ge=0, le=8)
    manual_value: Optional[str] = None  # numeric string for Decimal precision
    show_zero: Optional[bool] = None


class SubtotalBlock(_BlockBase):
    type: Literal["subtotal"]
    formula: Optional[str] = Field(default=None, max_length=500)
    accounts: Optional[AccountsSelector] = None
    calculation_method: Optional[CalculationMethod] = None
    sign_policy: Optional[SignPolicy] = None
    scale: Optional[Scale] = None
    decimal_places: Optional[int] = Field(default=None, ge=0, le=8)


class TotalBlock(_BlockBase):
    type: Literal["total"]
    formula: Optional[str] = Field(default=None, max_length=500)
    sign_policy: Optional[SignPolicy] = None
    scale: Optional[Scale] = None
    decimal_places: Optional[int] = Field(default=None, ge=0, le=8)


class SectionBlock(_BlockBase):
    type: Literal["section"]
    defaults: Optional[BlockDefaults] = None
    children: List["Block"] = Field(default_factory=list)


Block = Union[SectionBlock, HeaderBlock, LineBlock, SubtotalBlock, TotalBlock, SpacerBlock]

SectionBlock.model_rebuild()


# --- Document ---------------------------------------------------------------

class TemplateDocument(BaseModel):
    """Canonical template document."""
    model_config = ConfigDict(extra="forbid")

    version: int = Field(default=1, ge=1)
    name: str = Field(..., min_length=1, max_length=200)
    report_type: ReportType
    description: Optional[str] = Field(default=None, max_length=1000)
    defaults: BlockDefaults = Field(default_factory=BlockDefaults)
    blocks: List[Block] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_unique_ids(self) -> "TemplateDocument":
        seen: dict[str, list[str]] = {}
        for path, block in _walk(self.blocks):
            bid = _block_id(block)
            if bid is None:
                continue
            seen.setdefault(bid, []).append(path)
        dupes = {k: v for k, v in seen.items() if len(v) > 1}
        if dupes:
            summary = "; ".join(f"{k} at {', '.join(v)}" for k, v in dupes.items())
            raise ValueError(f"Duplicate block ids: {summary}")
        return self


# --- Helpers ----------------------------------------------------------------

def _block_id(block: Any) -> Optional[str]:
    return getattr(block, "id", None)


def _walk(blocks: List[Block], prefix: str = "") -> list[tuple[str, Block]]:
    """Depth-first traversal yielding ``(path, block)`` tuples.

    Path is a dotted id chain (``revenue.sales``) useful for error messages.
    """
    out: list[tuple[str, Block]] = []
    for idx, b in enumerate(blocks):
        bid = getattr(b, "id", f"[{idx}]")
        path = f"{prefix}.{bid}" if prefix else bid
        out.append((path, b))
        children = getattr(b, "children", None)
        if children:
            out.extend(_walk(children, path))
    return out


def validate_document(data: dict) -> TemplateDocument:
    """Validate a raw dict and return a ``TemplateDocument`` model instance.

    Raises ``pydantic.ValidationError`` on failure — callers should catch and
    translate to DRF ``ValidationError`` for clean 400 responses.
    """
    return TemplateDocument.model_validate(data)


def collect_block_ids(doc: TemplateDocument) -> list[str]:
    """Return every non-spacer block id, in document order."""
    return [getattr(b, "id") for _, b in _walk(doc.blocks) if _block_id(b) is not None]


# --- OpenAI Structured Outputs helper --------------------------------------


def to_openai_strict_schema(schema: dict | None = None) -> dict:
    """Convert our pydantic JSON Schema to OpenAI's ``strict: true`` dialect.

    What the transform does:

    1. Marks **every** property as required on every object. OpenAI's strict
       mode has no concept of "optional" fields — missing fields are invalid.
       Our schema already expresses nullability via ``anyOf: [{...}, {"type":
       "null"}]``, so "optional" translates to "required but nullable". This
       function just makes that explicit by rewriting ``required`` to the
       full property-key list on each object.
    2. Leaves ``additionalProperties: false`` alone (pydantic ``extra="forbid"``
       already set it everywhere).
    3. Recurses into ``$defs`` so the transform applies to every nested
       block type.

    What it deliberately does NOT do:
    - Strip ``default`` (OpenAI ignores defaults under strict mode; keeping
      them is harmless and they help readability).
    - Flatten ``anyOf`` block unions — OpenAI strict supports them as-is.
    - Rewrite recursive ``$ref`` — supported since late 2024.

    Pass ``None`` to start from :class:`TemplateDocument`'s own schema.
    """
    if schema is None:
        schema = TemplateDocument.model_json_schema()
    out = _walk_and_strict(schema)
    return out


def _walk_and_strict(node: Any) -> Any:
    """Recursively mark objects as strict: every property becomes required."""
    if isinstance(node, dict):
        # Root + every nested object with a "properties" key needs the
        # required-lists-everything treatment.
        if node.get("type") == "object" and "properties" in node:
            node = dict(node)
            node["required"] = list(node["properties"].keys())
            # additionalProperties: false is required by OpenAI strict — our
            # pydantic already sets it, but we belt-and-braces here for
            # schemas passed in from outside.
            node.setdefault("additionalProperties", False)
        # Recurse into every child.
        return {k: _walk_and_strict(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_walk_and_strict(v) for v in node]
    return node
