"""AI assistant for the new report engine.

PR 6: ``generate_template`` — a one-shot generator that reads the tenant's
chart of accounts, calls the external AI, and returns a draft
:class:`~accounting.reports.services.document_schema.TemplateDocument` as a
dict. **Never persists.** The frontend drops the result straight into the
builder as an unsaved draft.

Later PRs add:
  * ``refine`` — inline one-shot actions (normalize labels, add missing
    accounts, translate, etc.) returning JSON Patch. [PR 7]
  * ``chat`` — streaming tool-calling assistant. [PR 8]
  * ``explain`` — natural-language explanation of a single cell. [PR 11]

We deliberately don't reuse :class:`TemplateSuggestionService` from the legacy
module — its prompt emits the flat ``line_templates`` shape, and adapting
that to our block tree is more work than writing a fresh, schema-aware
prompt. :class:`accounting.services.external_ai_client.ExternalAIClient` is
the shared HTTP layer, which we do reuse.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import ValidationError as PydanticValidationError

from accounting.models import Account
from accounting.services.external_ai_client import ExternalAIClient, ExternalAIError

from .document_schema import TemplateDocument, validate_document


log = logging.getLogger(__name__)


class AiAssistantError(Exception):
    """Raised when the AI service fails to produce a valid template."""


# --- Chart-of-accounts context ---------------------------------------------


def _build_chart_context(company_id: int, limit: int = 400) -> Dict[str, Any]:
    """Summarize a tenant's chart of accounts into a compact structure for
    the AI prompt. Returns a dict with top-level stats and a sample list.

    We cap at ``limit`` accounts to keep prompts small. For larger charts,
    the AI should use ``code_prefix`` selectors (which match by pattern, so
    unseen accounts still get picked up at calculate-time).
    """
    qs = (
        Account.objects.filter(company_id=company_id, is_active=True)
        .order_by("account_code", "path")
        .values("id", "name", "account_code", "path", "account_direction", "level")
    )
    total = qs.count()
    sample = list(qs[:limit])
    return {
        "total_accounts": total,
        "sampled": len(sample),
        "accounts": [
            {
                "code": a["account_code"] or "",
                "name": a["name"],
                "path": a["path"] or "",
                "direction": a["account_direction"],
                "level": a["level"],
            }
            for a in sample
        ],
    }


# --- Prompts ---------------------------------------------------------------


_SYSTEM_PROMPT = """\
You are a senior Brazilian accountant and financial reporting expert with \
deep knowledge of IFRS and BR GAAP. You design financial statement templates \
that are compliant, well-structured, and match the company's actual chart of \
accounts.

Respond with ONLY valid JSON — no markdown, no commentary, no preamble.

The JSON must match this schema (a tree of typed blocks):

{
  "version": 1,
  "name": "string (pt-BR)",
  "report_type": "income_statement" | "balance_sheet" | "cash_flow",
  "description": "string (optional)",
  "defaults": {
    "calculation_method": "net_movement" | "ending_balance" | ...,
    "sign_policy": "natural" | "invert" | "absolute",
    "decimal_places": 2
  },
  "blocks": [
    {
      "type": "section",
      "id": "snake_case_id",
      "label": "Pt-BR label",
      "defaults": { ... optional overrides ... },
      "children": [ ...nested blocks... ]
    },
    {
      "type": "line",
      "id": "snake_case_id",
      "label": "Pt-BR label",
      "accounts": { "code_prefix": "4.01", "include_descendants": true }
    },
    {
      "type": "subtotal",
      "id": "snake_case_id",
      "label": "Pt-BR label",
      "formula": "sum(children)"
    },
    {
      "type": "total",
      "id": "snake_case_id",
      "label": "Pt-BR label",
      "bold": true,
      "formula": "revenue_gross - deductions"
    },
    {
      "type": "header",
      "id": "snake_case_id",
      "label": "Pt-BR header label"
    },
    { "type": "spacer", "id": "sp_1" }
  ]
}

Rules (STRICT):
- Block ids MUST match ^[A-Za-z_][A-Za-z0-9_]*$ and be unique across the tree.
- Formulas reference other block ids (e.g. "revenue_gross - taxes") or use
  the helpers sum(children) / abs(x) / min(a,b) / max(a,b). The special
  identifier "children" is only valid inside sum/min/max/abs.
- For income_statement use defaults.calculation_method = "net_movement".
- For balance_sheet use defaults.calculation_method = "ending_balance".
- For cash_flow use a mix: opening_balance + net_movement + ending_balance.
- Prefer accounts.code_prefix (pattern match) over listing explicit ids.
- Use sections for logical grouping; put a subtotal at the end of each
  section. Top-level totals (net income, total assets, etc.) go at the root.
- All labels and the template name MUST be in Brazilian Portuguese (pt-BR).
- On every non-spacer block, include a short "_ai_explanation" field \
(<= 160 chars) describing why the block exists / what it aggregates.
"""


def _build_user_prompt(report_type: str, preferences: str, chart: Dict[str, Any]) -> str:
    accounts_repr = "\n".join(
        f"  {a['code'] or '—':<12} | L{a['level']} | {a['path'] or a['name']}"
        for a in chart["accounts"]
    )
    pref_line = f"\nUser preferences: {preferences.strip()}" if preferences.strip() else ""
    note = ""
    if chart["sampled"] < chart["total_accounts"]:
        note = (
            f"\nNote: Only the first {chart['sampled']} of "
            f"{chart['total_accounts']} accounts are shown — prefer code_prefix "
            "selectors so unseen accounts still match."
        )
    return (
        f"Generate a {report_type} template for the following company.\n"
        f"{pref_line}\n"
        f"{note}\n\n"
        f"Chart of accounts (code | level | path):\n{accounts_repr}"
    )


# --- Public entry point ----------------------------------------------------


def generate_template(
    *,
    company_id: int,
    report_type: str,
    preferences: str = "",
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Call the AI and return a validated :class:`TemplateDocument` as a dict.

    Raises
    ------
    AiAssistantError
        When the AI client can't be initialised (missing API key),
        returns non-JSON, produces an unparseable payload, or the payload
        doesn't conform to the document schema after one repair attempt.
    """
    chart = _build_chart_context(company_id=company_id)
    user_prompt = _build_user_prompt(report_type, preferences, chart)

    try:
        client = ExternalAIClient(provider=provider, model=model)
    except Exception as exc:
        raise AiAssistantError(f"AI client init failed: {exc}") from exc

    # Nudge the AI toward our report_type by putting it at the top of the user
    # message even though it's also repeated in the system prompt.
    log.info(
        "ai_assistant.generate_template: report_type=%s, accounts=%s/%s, prefs_len=%s",
        report_type,
        chart["sampled"],
        chart["total_accounts"],
        len(preferences),
    )

    try:
        raw = client.generate_json(user_prompt, system_prompt=_SYSTEM_PROMPT)
    except ExternalAIError as exc:
        raise AiAssistantError(f"AI call failed: {exc}") from exc

    # Validate against pydantic; emit a single repair pass if validation fails.
    try:
        doc_model = validate_document(raw)
    except PydanticValidationError as exc:
        log.warning("AI document failed first-pass validation: %s", exc)
        repair_prompt = (
            "The previous JSON document failed schema validation with these "
            "errors:\n\n"
            + json.dumps(exc.errors(), indent=2)
            + "\n\nRegenerate the SAME template, corrected so it validates. "
            "Respond with ONLY JSON."
        )
        try:
            raw = client.generate_json(repair_prompt, system_prompt=_SYSTEM_PROMPT)
            doc_model = validate_document(raw)
        except PydanticValidationError as exc2:
            raise AiAssistantError(
                f"AI returned an invalid document even after repair: {exc2}"
            ) from exc2
        except ExternalAIError as exc2:
            raise AiAssistantError(f"AI repair call failed: {exc2}") from exc2

    # Force the user-requested report_type in case the model produced a
    # different one — the UI expects it to match.
    doc_dict = doc_model.model_dump(mode="json")
    doc_dict["report_type"] = report_type
    return doc_dict


# ---------------------------------------------------------------------------
# Refine actions (PR 7) — one-shot transformations on an existing document.
#
# Each action takes the current document + optional extras and returns a
# modified document. The backend returns the new doc; the frontend computes
# a visual diff and lets the user accept or reject per block (the diff view
# lives in the UI, not here).
# ---------------------------------------------------------------------------


REFINE_ACTION_PROMPTS: Dict[str, str] = {
    "normalize_labels": (
        "Rewrite every 'label' field in the template so labels are "
        "consistent, concise, and follow professional accounting style "
        "in Brazilian Portuguese. Do NOT change ids, structure, or any "
        "field other than 'label' (and their cascading defaults). "
        "Keep it terse — avoid articles where possible, title case "
        "only for proper nouns."
    ),
    "translate_en": (
        "Translate every 'label', 'name', and 'description' field from "
        "Portuguese to English. Preserve all ids and structure. Keep "
        "accounting terminology standard (e.g. 'Receita Bruta' → 'Gross "
        "Revenue')."
    ),
    "translate_pt": (
        "Translate every 'label', 'name', and 'description' field to "
        "Brazilian Portuguese. Preserve all ids and structure."
    ),
    "suggest_subtotals": (
        "Analyze the document and insert 'subtotal' blocks at natural "
        "semantic breaks within each section (e.g. after a group of "
        "related lines). Do not duplicate existing subtotals. Give each "
        "new subtotal a descriptive Portuguese label and a "
        "'sum(children)' formula. Preserve every existing block unchanged."
    ),
    "add_missing_accounts": (
        "Compare the template against the chart of accounts provided. "
        "For accounts that are NOT currently matched by any line's "
        "accounts selector, add new 'line' blocks in the most appropriate "
        "section. If no suitable section exists, create one. Preserve "
        "every existing block unchanged."
    ),
}


def refine_template(
    *,
    company_id: int,
    document: dict,
    action: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Run a one-shot refine action and return the modified document.

    The client is expected to diff the result against the pre-refine doc
    and show a preview before applying.
    """
    instruction = REFINE_ACTION_PROMPTS.get(action)
    if not instruction:
        raise AiAssistantError(f"unknown refine action: {action!r}")

    # Validate the incoming document first — we want to refuse garbage before
    # spending tokens on it.
    try:
        validate_document(document)
    except PydanticValidationError as exc:
        raise AiAssistantError(f"input document failed validation: {exc}") from exc

    # add_missing_accounts needs the chart as context; other actions don't.
    extras = ""
    if action == "add_missing_accounts":
        chart = _build_chart_context(company_id=company_id)
        extras = "\n\nChart of accounts (code | level | path):\n" + "\n".join(
            f"  {a['code'] or '—':<12} | L{a['level']} | {a['path'] or a['name']}"
            for a in chart["accounts"]
        )
        if chart["sampled"] < chart["total_accounts"]:
            extras += (
                f"\n\n(Only {chart['sampled']}/{chart['total_accounts']} "
                "accounts shown — prefer code_prefix selectors.)"
            )

    user_prompt = (
        f"Apply the following refine action to the template below.\n\n"
        f"Action: {action}\n"
        f"Instruction: {instruction}\n\n"
        f"Return the COMPLETE modified template as JSON matching the schema "
        f"described in the system prompt. Do not elide parts you didn't "
        f"change — the output is the full document.\n\n"
        f"Current template:\n{json.dumps(document, ensure_ascii=False)}"
        f"{extras}"
    )

    try:
        client = ExternalAIClient(provider=provider, model=model)
    except Exception as exc:
        raise AiAssistantError(f"AI client init failed: {exc}") from exc

    log.info("ai_assistant.refine_template: action=%s", action)

    try:
        raw = client.generate_json(user_prompt, system_prompt=_SYSTEM_PROMPT)
    except ExternalAIError as exc:
        raise AiAssistantError(f"AI call failed: {exc}") from exc

    try:
        new_doc = validate_document(raw)
    except PydanticValidationError as exc:
        raise AiAssistantError(
            f"AI-refined document failed validation: {exc}"
        ) from exc

    out = new_doc.model_dump(mode="json")
    # Preserve the original report_type — refine should never change it.
    out["report_type"] = document.get("report_type", out.get("report_type"))
    return out


def summarize_changes(old: dict, new: dict) -> Dict[str, Any]:
    """Cheap structural summary used by the UI to show a refine diff overview.

    Returns counts of added / removed / renamed blocks. Deep per-field diffs
    stay client-side where the renderer already knows the layout.
    """
    old_blocks = _collect_blocks_flat(old.get("blocks") or [])
    new_blocks = _collect_blocks_flat(new.get("blocks") or [])

    old_ids = {b["id"]: b for b in old_blocks if b.get("id")}
    new_ids = {b["id"]: b for b in new_blocks if b.get("id")}

    added = sorted(new_ids.keys() - old_ids.keys())
    removed = sorted(old_ids.keys() - new_ids.keys())

    renamed: List[Dict[str, str]] = []
    for bid in sorted(set(old_ids) & set(new_ids)):
        ol = old_ids[bid].get("label")
        nl = new_ids[bid].get("label")
        if ol != nl and ol is not None and nl is not None:
            renamed.append({"id": bid, "from": ol, "to": nl})

    return {
        "added_ids": added,
        "removed_ids": removed,
        "renamed": renamed,
        "old_count": len(old_blocks),
        "new_count": len(new_blocks),
    }


def _collect_blocks_flat(blocks: List[dict]) -> List[dict]:
    out: List[dict] = []
    for b in blocks or []:
        out.append(b)
        if b.get("type") == "section":
            out.extend(_collect_blocks_flat(b.get("children") or []))
    return out
