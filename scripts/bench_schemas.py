"""Empirical schema ladder test for OpenAI Structured Outputs.

Runs five progressively-slimmer schemas against the real chart +
prompt, reports latency / token counts / validation per rung, and
stops at the first rung that produces a valid document in
reasonable time.

Usage::

    # With OPENAI_API_KEY set in the env:
    python scripts/bench_schemas.py --company 4 --model gpt-4o-mini

Ranked most → least complete. Pick the highest rung that consistently
works; that tells us which fields are breaking Structured Outputs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Literal, Optional, Union

import django

# Make project root importable regardless of where we invoke from.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Bootstrap Django so we can import the services / models.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nord_backend.settings")
django.setup()

from pydantic import BaseModel, ConfigDict, Field  # noqa: E402
from openai import OpenAI  # noqa: E402

from accounting.reports.services.ai_assistant import (  # noqa: E402
    _SYSTEM_PROMPT,
    _build_chart_context,
    _build_user_prompt,
)
from accounting.reports.services.document_schema import (  # noqa: E402
    to_openai_strict_schema,
)


# -------------------------------------------------------------------- shared types

ReportType = Literal["balance_sheet", "income_statement", "cash_flow"]
BlockType = Literal["section", "line", "subtotal", "total", "header", "spacer"]
CalcMethod = Literal[
    "ending_balance", "opening_balance", "net_movement",
    "debit_total", "credit_total", "change_in_balance",
    "rollup_children", "formula", "manual_input",
]
SignPolicy = Literal["natural", "invert", "absolute"]
Scale = Literal["none", "K", "M", "B"]


# ==================================================================== Rung A: richest

# Flat (no tree), discriminated union on type, all decorative fields kept.

class _A_AccountsSelector(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_ids: Optional[List[int]] = None
    code_prefix: Optional[str] = None
    path_contains: Optional[str] = None
    include_descendants: Optional[bool] = None


class _A_BlockDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    calculation_method: Optional[CalcMethod] = None
    sign_policy: Optional[SignPolicy] = None
    scale: Optional[Scale] = None
    decimal_places: Optional[int] = Field(default=None, ge=0, le=8)


class _A_BlockBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    label: Optional[str] = None
    parent_id: Optional[str] = None
    bold: Optional[bool] = None
    indent: Optional[int] = Field(default=None, ge=0, le=8)
    ai_explanation: Optional[str] = Field(default=None, max_length=2000)


class A_Section(_A_BlockBase):
    type: Literal["section"]
    defaults: Optional[_A_BlockDefaults] = None


class A_Line(_A_BlockBase):
    type: Literal["line"]
    accounts: Optional[_A_AccountsSelector] = None
    calculation_method: Optional[CalcMethod] = None
    sign_policy: Optional[SignPolicy] = None
    scale: Optional[Scale] = None
    decimal_places: Optional[int] = Field(default=None, ge=0, le=8)


class A_Subtotal(_A_BlockBase):
    type: Literal["subtotal"]
    formula: Optional[str] = None
    accounts: Optional[_A_AccountsSelector] = None
    calculation_method: Optional[CalcMethod] = None
    sign_policy: Optional[SignPolicy] = None


class A_Total(_A_BlockBase):
    type: Literal["total"]
    formula: Optional[str] = None
    sign_policy: Optional[SignPolicy] = None


class A_Header(_A_BlockBase):
    type: Literal["header"]


class A_Spacer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    type: Literal["spacer"]


A_Block = Union[A_Section, A_Line, A_Subtotal, A_Total, A_Header, A_Spacer]


class A_Template(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1, max_length=200)
    report_type: ReportType
    defaults: Optional[_A_BlockDefaults] = None
    blocks: List[A_Block]


# ==================================================================== Rung B: -explanation, -decoration

# Drops ai_explanation + bold + indent from every block (server recomputes indent
# from depth; explanation + bold are Phase 2). Keeps everything else.

class _B_BlockBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    label: Optional[str] = None
    parent_id: Optional[str] = None


class B_Section(_B_BlockBase):
    type: Literal["section"]
    defaults: Optional[_A_BlockDefaults] = None


class B_Line(_B_BlockBase):
    type: Literal["line"]
    accounts: Optional[_A_AccountsSelector] = None
    calculation_method: Optional[CalcMethod] = None
    sign_policy: Optional[SignPolicy] = None
    scale: Optional[Scale] = None
    decimal_places: Optional[int] = Field(default=None, ge=0, le=8)


class B_Subtotal(_B_BlockBase):
    type: Literal["subtotal"]
    formula: Optional[str] = None
    accounts: Optional[_A_AccountsSelector] = None


class B_Total(_B_BlockBase):
    type: Literal["total"]
    formula: Optional[str] = None


class B_Header(_B_BlockBase):
    type: Literal["header"]


class B_Spacer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    type: Literal["spacer"]


B_Block = Union[B_Section, B_Line, B_Subtotal, B_Total, B_Header, B_Spacer]


class B_Template(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    report_type: ReportType
    defaults: Optional[_A_BlockDefaults] = None  # top-level defaults only
    blocks: List[B_Block]


# ==================================================================== B-family: add back one feature at a time


# B0 = B + top-level description ONLY (cheapest possible addition)
class B0_Template(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    report_type: ReportType
    description: Optional[str] = Field(default=None, max_length=1000)
    defaults: Optional[_A_BlockDefaults] = None
    blocks: List[B_Block]


# B1 = B + bold + indent (pure decorative, cheap types)
class _B1_BlockBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    label: Optional[str] = None
    parent_id: Optional[str] = None
    bold: Optional[bool] = None
    indent: Optional[int] = Field(default=None, ge=0, le=8)


class B1_Section(_B1_BlockBase):
    type: Literal["section"]
    defaults: Optional[_A_BlockDefaults] = None


class B1_Line(_B1_BlockBase):
    type: Literal["line"]
    accounts: Optional[_A_AccountsSelector] = None
    calculation_method: Optional[CalcMethod] = None
    sign_policy: Optional[SignPolicy] = None
    scale: Optional[Scale] = None
    decimal_places: Optional[int] = Field(default=None, ge=0, le=8)


class B1_Subtotal(_B1_BlockBase):
    type: Literal["subtotal"]
    formula: Optional[str] = None
    accounts: Optional[_A_AccountsSelector] = None


class B1_Total(_B1_BlockBase):
    type: Literal["total"]
    formula: Optional[str] = None


class B1_Header(_B1_BlockBase):
    type: Literal["header"]


class B1_Spacer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    type: Literal["spacer"]


B1_Block = Union[B1_Section, B1_Line, B1_Subtotal, B1_Total, B1_Header, B1_Spacer]


class B1_Template(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    report_type: ReportType
    description: Optional[str] = Field(default=None, max_length=1000)
    defaults: Optional[_A_BlockDefaults] = None
    blocks: List[B1_Block]


# B2 = B1 + short ai_explanation (max_length=300, one per block)
class _B2_BlockBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    label: Optional[str] = None
    parent_id: Optional[str] = None
    bold: Optional[bool] = None
    indent: Optional[int] = Field(default=None, ge=0, le=8)
    ai_explanation: Optional[str] = Field(default=None, max_length=300)


class B2_Section(_B2_BlockBase):
    type: Literal["section"]
    defaults: Optional[_A_BlockDefaults] = None


class B2_Line(_B2_BlockBase):
    type: Literal["line"]
    accounts: Optional[_A_AccountsSelector] = None
    calculation_method: Optional[CalcMethod] = None
    sign_policy: Optional[SignPolicy] = None
    scale: Optional[Scale] = None
    decimal_places: Optional[int] = Field(default=None, ge=0, le=8)


class B2_Subtotal(_B2_BlockBase):
    type: Literal["subtotal"]
    formula: Optional[str] = None
    accounts: Optional[_A_AccountsSelector] = None


class B2_Total(_B2_BlockBase):
    type: Literal["total"]
    formula: Optional[str] = None


class B2_Header(_B2_BlockBase):
    type: Literal["header"]


class B2_Spacer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    type: Literal["spacer"]


B2_Block = Union[B2_Section, B2_Line, B2_Subtotal, B2_Total, B2_Header, B2_Spacer]


class B2_Template(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    report_type: ReportType
    description: Optional[str] = Field(default=None, max_length=1000)
    defaults: Optional[_A_BlockDefaults] = None
    blocks: List[B2_Block]


# B3 = B2 but ai_explanation max_length=2000 (matches canonical). If B3 fails
# and B2 passes, the long string-length constraint is the SO-compile blocker.
class _B3_BlockBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    label: Optional[str] = None
    parent_id: Optional[str] = None
    bold: Optional[bool] = None
    indent: Optional[int] = Field(default=None, ge=0, le=8)
    ai_explanation: Optional[str] = Field(default=None, max_length=2000)


class B3_Section(_B3_BlockBase):
    type: Literal["section"]
    defaults: Optional[_A_BlockDefaults] = None


class B3_Line(_B3_BlockBase):
    type: Literal["line"]
    accounts: Optional[_A_AccountsSelector] = None
    calculation_method: Optional[CalcMethod] = None
    sign_policy: Optional[SignPolicy] = None
    scale: Optional[Scale] = None
    decimal_places: Optional[int] = Field(default=None, ge=0, le=8)


class B3_Subtotal(_B3_BlockBase):
    type: Literal["subtotal"]
    formula: Optional[str] = None
    accounts: Optional[_A_AccountsSelector] = None


class B3_Total(_B3_BlockBase):
    type: Literal["total"]
    formula: Optional[str] = None


class B3_Header(_B3_BlockBase):
    type: Literal["header"]


class B3_Spacer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    type: Literal["spacer"]


B3_Block = Union[B3_Section, B3_Line, B3_Subtotal, B3_Total, B3_Header, B3_Spacer]


class B3_Template(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    report_type: ReportType
    description: Optional[str] = Field(default=None, max_length=1000)
    defaults: Optional[_A_BlockDefaults] = None
    blocks: List[B3_Block]


# ==================================================================== Rung C: -selector variants, -decimal, -section defaults

# Accounts selector drops path_contains + include_descendants (just
# account_ids + code_prefix). Subtotal loses accounts (lean on formula).
# Section drops its own defaults (cascade flattens to top-level only).

class _C_AccountsSelector(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_ids: Optional[List[int]] = None
    code_prefix: Optional[str] = None


class _C_BlockDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    calculation_method: Optional[CalcMethod] = None
    sign_policy: Optional[SignPolicy] = None
    scale: Optional[Scale] = None


class _C_BlockBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    label: Optional[str] = None
    parent_id: Optional[str] = None


class C_Section(_C_BlockBase):
    type: Literal["section"]


class C_Line(_C_BlockBase):
    type: Literal["line"]
    accounts: Optional[_C_AccountsSelector] = None
    calculation_method: Optional[CalcMethod] = None
    sign_policy: Optional[SignPolicy] = None


class C_Subtotal(_C_BlockBase):
    type: Literal["subtotal"]
    formula: Optional[str] = None


class C_Total(_C_BlockBase):
    type: Literal["total"]
    formula: Optional[str] = None


class C_Header(_C_BlockBase):
    type: Literal["header"]


class C_Spacer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    type: Literal["spacer"]


C_Block = Union[C_Section, C_Line, C_Subtotal, C_Total, C_Header, C_Spacer]


class C_Template(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    report_type: ReportType
    defaults: Optional[_C_BlockDefaults] = None
    blocks: List[C_Block]


# ==================================================================== Rung D: single block type

# Collapse the 6-type discriminated union into ONE block type with the
# superset of fields. The model picks ``type`` and only fills in the
# fields relevant to that type. Much simpler for the SO compiler to
# sample but model has to self-police which fields are valid per type.

class D_Block(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    type: BlockType
    label: Optional[str] = None
    parent_id: Optional[str] = None
    # Line-only (rest leave None)
    code_prefix: Optional[str] = None
    account_ids: Optional[List[int]] = None
    # Subtotal/total-only
    formula: Optional[str] = None
    # Per-block overrides (null = inherit from defaults / per-report-type server rule)
    calculation_method: Optional[CalcMethod] = None
    sign_policy: Optional[SignPolicy] = None


class D_Template(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    report_type: ReportType
    blocks: List[D_Block]


# ==================================================================== Rung E: skeleton only

# Barest viable template: identity + flat blocks with id/type/label/parent.
# Everything else is server-computed from per-report-type defaults.

class E_Block(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    type: BlockType
    label: Optional[str] = None
    parent_id: Optional[str] = None
    code_prefix: Optional[str] = None  # tiny concession — we need SOMETHING for lines
    formula: Optional[str] = None      # and SOMETHING for subtotals/totals


class E_Template(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    report_type: ReportType
    blocks: List[E_Block]


# ==================================================================== runner

RUNGS = [
    ("A: flat + full fields", A_Template),
    ("B: -ai_explanation, -bold, -indent", B_Template),
    ("B0: B + top-level description only", B0_Template),
    ("B1: B + bold + indent + description", B1_Template),
    ("B2: B1 + ai_explanation (max 300)", B2_Template),
    ("B3: B1 + ai_explanation (max 2000)", B3_Template),
    ("C: -section defaults, slimmer selector", C_Template),
    ("D: single union-free block type", D_Template),
    ("E: minimal skeleton", E_Template),
]


def _strict(schema: dict) -> dict:
    return to_openai_strict_schema(schema)


def _count_blocks(doc: dict) -> int:
    blocks = doc.get("blocks") or []
    return len(blocks)


def run_one(model_class: type, *, report_type: str, preferences: str, chart: dict,
            openai_model: str, timeout_s: int, retries: int = 0) -> Dict[str, Any]:
    schema = _strict(model_class.model_json_schema())
    schema_chars = len(json.dumps(schema))
    user_prompt = _build_user_prompt(report_type, preferences, chart)

    c = OpenAI(timeout=timeout_s, max_retries=retries)
    t0 = time.time()
    try:
        r = c.chat.completions.create(
            model=openai_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=10000,
            temperature=0.1,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "TemplateDocument", "schema": schema, "strict": True},
            },
        )
        dt = time.time() - t0
        content = r.choices[0].message.content
        raw = json.loads(content)
        try:
            model_class.model_validate(raw)
            valid_status = "OK"
        except Exception as exc:
            valid_status = f"pydantic-FAIL: {type(exc).__name__}"
        return {
            "status": "ok",
            "dt": dt,
            "schema_chars": schema_chars,
            "tok_in": r.usage.prompt_tokens,
            "tok_out": r.usage.completion_tokens,
            "blocks": _count_blocks(raw),
            "valid": valid_status,
            "finish": r.choices[0].finish_reason,
        }
    except Exception as exc:
        dt = time.time() - t0
        return {
            "status": "fail",
            "dt": dt,
            "schema_chars": schema_chars,
            "err": f"{type(exc).__name__}: {str(exc)[:140]}",
        }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", type=int, required=True)
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--report-type", default="income_statement",
                    choices=["income_statement", "balance_sheet", "cash_flow"])
    ap.add_argument("--preferences", default="")
    ap.add_argument("--stop-on-success", action="store_true",
                    help="Halt after the first rung that passes.")
    ap.add_argument("--only", default=None,
                    help="Run only the rung whose label starts with this prefix (e.g. 'B').")
    ap.add_argument("--repeat", type=int, default=1,
                    help="How many times to run each rung (reliability check).")
    ap.add_argument("--retries", type=int, default=0,
                    help="OpenAI SDK max_retries (0 = single attempt).")
    args = ap.parse_args()

    chart = _build_chart_context(company_id=args.company)
    print(f"Chart: {chart['sampled']}/{chart['total_accounts']} accounts · model={args.model} · timeout={args.timeout}s")
    print(f"{'Rung':45s} {'schema':>8s} {'time':>7s} {'tok_in':>7s} {'tok_out':>8s} {'blocks':>6s}  valid")
    print("-" * 100)

    rungs = RUNGS
    if args.only:
        rungs = [(lbl, cls) for (lbl, cls) in RUNGS if lbl.startswith(args.only)]

    for label, cls in rungs:
        for i in range(args.repeat):
            suffix = f" #{i+1}" if args.repeat > 1 else ""
            result = run_one(
                cls,
                report_type=args.report_type,
                preferences=args.preferences,
                chart=chart,
                openai_model=args.model,
                timeout_s=args.timeout,
                retries=args.retries,
            )
            tag = f"{label}{suffix}"
            if result["status"] == "ok":
                print(f"{tag:48s} {result['schema_chars']:>7d}B {result['dt']:>6.1f}s "
                      f"{result['tok_in']:>7d} {result['tok_out']:>8d} {result['blocks']:>6d}  {result['valid']}")
                if args.stop_on_success and result["valid"] == "OK":
                    print(f"\nFirst rung to produce a valid document: {label}")
                    return 0
            else:
                print(f"{tag:48s} {result['schema_chars']:>7d}B {result['dt']:>6.1f}s  {result['err']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
