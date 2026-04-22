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


# ---------------------------------------------------------------------------
# Slim schema for OpenAI Structured Outputs
#
# Empirical finding (see ``scripts/bench_schemas.py``): OpenAI's Structured
# Outputs sampler struggles with our canonical :class:`TemplateDocument`:
# the 9KB schema with recursive :class:`SectionBlock.children` and 8 $defs
# times out ≥95% of the time at 60s, and even at the SDK's 360s ceiling
# (120s × 3 retries) we see the "361.8s APITimeoutError" pattern in prod.
#
# This slim schema produces an AI output that's:
#   * **Flat** — blocks reference a ``parent_id`` instead of nesting; the
#     server rebuilds the tree before validation. Flat schemas sample
#     ~5× faster because there's no recursive $ref to unroll during
#     grammar compilation.
#   * **Decoration-free** — no ``bold``, ``indent``, ``ai_explanation``,
#     ``description``. All three are *derivable* server-side
#     (bold = is-a-total, indent = depth, ai_explanation = separate
#     :func:`explain` endpoint on demand) so we don't waste sampling
#     budget on them.
#   * **Feature-complete for the calc engine** — keeps the defaults
#     cascade (``CalculationMethod`` / ``SignPolicy`` / ``Scale``),
#     per-line overrides, and all three account-selector fields
#     (``account_ids`` / ``code_prefix`` / ``path_contains`` /
#     ``include_descendants``) so selected blocks still resolve correctly
#     once converted back to canonical.
#
# Measured on datbaby (253 accounts, gpt-4o-mini):
#   * canonical schema A: timeouts ≥95% at 60s; ~100% at 120s.
#   * slim schema (below): median 17s, p99 ~120s, 100% success with the
#     SDK's default 2 retries.
# ---------------------------------------------------------------------------


class SlimAccountsSelector(BaseModel):
    """Same shape as :class:`AccountsSelector` — re-declared here because
    Pydantic v2 refuses to share a model across two schema roots that both
    use ``extra="forbid"``. Safe to keep identical.
    """
    model_config = ConfigDict(extra="forbid")

    account_ids: Optional[List[int]] = None
    code_prefix: Optional[str] = None
    path_contains: Optional[str] = None
    include_descendants: Optional[bool] = None


class SlimBlockDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calculation_method: Optional[CalculationMethod] = None
    sign_policy: Optional[SignPolicy] = None
    scale: Optional[Scale] = None
    decimal_places: Optional[int] = Field(default=None, ge=0, le=8)


class _SlimBlockBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=64,
                    pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    label: Optional[str] = None
    # ``parent_id`` replaces ``children``. The server stitches blocks
    # back into a tree by walking parent_id references; top-level blocks
    # have ``parent_id = None``.
    parent_id: Optional[str] = None


class SlimSectionBlock(_SlimBlockBase):
    type: Literal["section"]
    defaults: Optional[SlimBlockDefaults] = None


class SlimLineBlock(_SlimBlockBase):
    type: Literal["line"]
    accounts: Optional[SlimAccountsSelector] = None
    calculation_method: Optional[CalculationMethod] = None
    sign_policy: Optional[SignPolicy] = None
    scale: Optional[Scale] = None
    decimal_places: Optional[int] = Field(default=None, ge=0, le=8)


class SlimSubtotalBlock(_SlimBlockBase):
    type: Literal["subtotal"]
    formula: Optional[str] = None
    accounts: Optional[SlimAccountsSelector] = None


class SlimTotalBlock(_SlimBlockBase):
    type: Literal["total"]
    formula: Optional[str] = None


class SlimHeaderBlock(_SlimBlockBase):
    type: Literal["header"]


class SlimSpacerBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    type: Literal["spacer"]


SlimBlock = Union[
    SlimSectionBlock, SlimLineBlock, SlimSubtotalBlock,
    SlimTotalBlock, SlimHeaderBlock, SlimSpacerBlock,
]


class SlimTemplateDocument(BaseModel):
    """The shape the AI emits. Gets converted to canonical
    :class:`TemplateDocument` before persistence (see
    :func:`slim_to_canonical`).
    """
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=200)
    report_type: ReportType
    defaults: Optional[SlimBlockDefaults] = None
    blocks: List[SlimBlock]


def slim_to_canonical(slim_doc: dict, *, report_type: Optional[str] = None) -> dict:
    """Convert a slim AI output into a canonical :class:`TemplateDocument` dict.

    Responsibilities:
      1. Re-build the ``children`` tree from flat ``parent_id`` links.
      2. Fill in decorative fields that the slim schema dropped:
         ``bold`` (subtotal / total are bold by convention) and
         ``indent`` (depth in the rebuilt tree).
      3. Coerce the top-level ``report_type`` to the caller-requested
         value — the AI sometimes echoes the literal from the prompt
         instead of the exact enum value, and the UI cross-references
         this field.
      4. Strip unknown keys so pydantic ``extra="forbid"`` accepts the
         output.

    The result is a dict (not a model) so callers can still run it
    through :func:`validate_document` for the cross-ref + unique-id
    invariants. If any parent_id is dangling the orphaned block is
    promoted to root; we emit a warning but never raise, because a
    lossy import is better than failing the whole generation.
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)

    raw_blocks: list[dict] = list(slim_doc.get("blocks") or [])

    # Strip unknown keys on each block (e.g. ai_explanation if the model
    # snuck one past the schema — shouldn't happen under strict SO, but
    # belt-and-braces before we pass to canonical validation).
    _ALLOWED_PER_TYPE: dict[str, set[str]] = {
        "section":  {"id", "type", "label", "parent_id", "defaults"},
        "line":     {"id", "type", "label", "parent_id", "accounts",
                     "calculation_method", "sign_policy", "scale", "decimal_places"},
        "subtotal": {"id", "type", "label", "parent_id", "formula", "accounts"},
        "total":    {"id", "type", "label", "parent_id", "formula"},
        "header":   {"id", "type", "label", "parent_id"},
        "spacer":   {"id", "type"},
    }
    cleaned: list[dict] = []
    for b in raw_blocks:
        if not isinstance(b, dict):
            continue
        btype = b.get("type")
        allowed = _ALLOWED_PER_TYPE.get(btype, {"id", "type", "label", "parent_id"})
        cleaned.append({k: v for k, v in b.items() if k in allowed or k == "parent_id"})

    # Dedupe ids. Observed AI failure mode (~1/3 of calls): the model
    # reuses the same id for both a section and its subtotal (e.g. both
    # are called ``revenue``). The cross-ref validator would reject
    # this. Auto-rename the second+ occurrence to ``{id}_N`` and
    # rewrite any ``parent_id`` that pointed at a block whose id we
    # just renamed. This is recovery-oriented: we log a warning but
    # keep the generation usable.
    seen: dict[str, int] = {}
    id_remap: dict[int, str] = {}  # index in cleaned -> new id
    original_ids: list[Optional[str]] = [b.get("id") for b in cleaned]
    for idx, b in enumerate(cleaned):
        bid = b.get("id")
        if not bid:
            continue
        if bid not in seen:
            seen[bid] = 1
            continue
        seen[bid] += 1
        new_id = f"{bid}_{seen[bid]}"
        # Walk forward in case ``new_id`` itself collides.
        while new_id in seen:
            seen[bid] += 1
            new_id = f"{bid}_{seen[bid]}"
        seen[new_id] = 1
        _log.warning(
            "slim_to_canonical: duplicate id %r at index %d — renaming to %r",
            bid, idx, new_id,
        )
        b["id"] = new_id
        id_remap[idx] = new_id
    # Rewrite parent_id references. A child that pointed at the ORIGINAL
    # (pre-rename) id should follow the first occurrence, not the
    # renamed duplicate — so no remap needed for children of the first
    # block. However children that explicitly parent under a later
    # duplicate are indistinguishable from children of the first; we
    # leave them pointing to the (now first-only) original id. This is
    # the least-surprising recovery and matches what the AI likely
    # meant.

    # Bucket by parent_id so the tree walk below is O(N) not O(N²).
    by_parent: dict[Optional[str], list[dict]] = {}
    for b in cleaned:
        pid = b.get("parent_id")
        by_parent.setdefault(pid, []).append(b)

    # Validate parent references. Orphans with unknown parent_id get
    # promoted to root to avoid losing them.
    known_ids = {b["id"] for b in cleaned if b.get("id")}
    for b in cleaned:
        pid = b.get("parent_id")
        if pid is not None and pid not in known_ids:
            _log.warning(
                "slim_to_canonical: block %r points to missing parent %r — promoting to root",
                b.get("id"), pid,
            )
            b["parent_id"] = None

    # Re-bucket after orphan promotion
    by_parent = {}
    for b in cleaned:
        by_parent.setdefault(b.get("parent_id"), []).append(b)

    def _build_subtree(parent_id: Optional[str], depth: int) -> list[dict]:
        out: list[dict] = []
        for b in by_parent.get(parent_id, []):
            btype = b.get("type")
            # Drop the flat-schema-only ``parent_id`` field on the way out
            new_b: dict = {k: v for k, v in b.items() if k != "parent_id"}

            # Decorate: bold for subtotal/total (convention), indent = depth
            # for everything except spacers / headers (they render their own
            # way in the grid).
            if btype in ("subtotal", "total"):
                new_b.setdefault("bold", True)
            if btype not in ("spacer",):
                new_b.setdefault("indent", depth)

            if btype == "section":
                new_b["children"] = _build_subtree(b["id"], depth + 1)
            out.append(new_b)
        return out

    canonical: dict = {
        "version": 1,
        "name": slim_doc.get("name") or "Template",
        "report_type": report_type or slim_doc.get("report_type") or "income_statement",
        "defaults": slim_doc.get("defaults") or {},
        "blocks": _build_subtree(None, 0),
    }
    return canonical
