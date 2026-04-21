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
import time
from typing import Any, Dict, List, Optional

from pydantic import ValidationError as PydanticValidationError

from accounting.models import Account
from accounting.services.external_ai_client import ExternalAIClient, ExternalAIError

from .ai_pricing import estimate_cost_usd
from .document_schema import TemplateDocument, validate_document


log = logging.getLogger(__name__)


class AiAssistantError(Exception):
    """Raised when the AI service fails to produce a valid template."""


# --- Usage-logging helper ---------------------------------------------------


def _run_ai_call(
    *,
    client: ExternalAIClient,
    prompt: str,
    system_prompt: Optional[str],
    context: Optional[Dict[str, Any]],
    endpoint: str,
) -> Dict[str, Any]:
    """Invoke ``client.generate_json_with_meta`` and write an ``AIUsageLog``
    row whether the call succeeds or fails.

    ``context`` carries the request-scoped attribution (``user_id``,
    ``company_id``); when it's ``None`` (e.g. internal calls, tests) we still
    make the AI call but skip logging. Logging failures never propagate — a
    DB hiccup must never make an otherwise-successful AI call look broken.
    """
    t0 = time.time()
    try:
        resp = client.generate_json_with_meta(prompt, system_prompt=system_prompt)
        duration_ms = int((time.time() - t0) * 1000)
        _record_usage(
            context=context,
            endpoint=endpoint,
            provider=resp.get("provider", client.provider),
            model=resp.get("model", client.model),
            usage=resp.get("usage") or {},
            duration_ms=duration_ms,
            status="success",
        )
        return resp.get("content") or {}
    except Exception as exc:
        duration_ms = int((time.time() - t0) * 1000)
        _record_usage(
            context=context,
            endpoint=endpoint,
            provider=client.provider,
            model=client.model,
            usage={},
            duration_ms=duration_ms,
            status="error",
            error=exc,
        )
        raise


def _record_usage(
    *,
    context: Optional[Dict[str, Any]],
    endpoint: str,
    provider: str,
    model: str,
    usage: Dict[str, Any],
    duration_ms: int,
    status: str,
    error: Optional[BaseException] = None,
) -> None:
    if context is None:
        return
    try:
        from ..models import AIUsageLog  # local import to avoid circular at module-load
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        total_tokens = int(usage.get("total_tokens", 0) or (prompt_tokens + completion_tokens))
        cost = estimate_cost_usd(
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        AIUsageLog.objects.create(
            user_id=context.get("user_id"),
            company_id=context.get("company_id"),
            endpoint=endpoint,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=cost,
            duration_ms=duration_ms,
            status=status,
            error_type=type(error).__name__ if error is not None else None,
            error_message=str(error)[:1000] if error is not None else None,
        )
    except Exception as log_exc:  # pragma: no cover — logging must never blow up the caller
        log.warning("AIUsageLog write failed: %s", log_exc)


# --- Chart-of-accounts context ---------------------------------------------


def _build_chart_context(company_id: int, limit: int = 400) -> Dict[str, Any]:
    """Summarize a tenant's chart of accounts into a compact structure for
    the AI prompt. Returns a dict with top-level stats and a sample list.

    We cap at ``limit`` accounts to keep prompts small. For larger charts,
    the AI should use ``code_prefix`` selectors (which match by pattern, so
    unseen accounts still get picked up at calculate-time).

    ``Account`` is an MPTTModel — there's no ``path`` column; we call
    ``get_path()`` on each instance instead.
    """
    qs = (
        Account.objects.filter(company_id=company_id, is_active=True)
        .order_by("account_code", "name")
    )
    total = qs.count()
    sample_instances = list(qs[:limit])
    accounts: List[Dict[str, Any]] = []
    for a in sample_instances:
        try:
            path = a.get_path() if hasattr(a, "get_path") else ""
        except Exception:
            path = ""
        accounts.append({
            "code": a.account_code or "",
            "name": a.name,
            "path": path or "",
            "direction": a.account_direction,
            "level": a.level,
        })
    return {
        "total_accounts": total,
        "sampled": len(sample_instances),
        "accounts": accounts,
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
    context: Optional[Dict[str, Any]] = None,
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
        raw = _run_ai_call(
            client=client, prompt=user_prompt, system_prompt=_SYSTEM_PROMPT,
            context=context, endpoint="generate_template",
        )
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
            raw = _run_ai_call(
                client=client, prompt=repair_prompt, system_prompt=_SYSTEM_PROMPT,
                context=context, endpoint="generate_template.repair",
            )
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
    context: Optional[Dict[str, Any]] = None,
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
        raw = _run_ai_call(
            client=client, prompt=user_prompt, system_prompt=_SYSTEM_PROMPT,
            context=context, endpoint=f"refine.{action}",
        )
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


# ---------------------------------------------------------------------------
# Chat with tool-calling (PR 8)
#
# The assistant can only mutate the template through a whitelist of
# "operations" it emits as structured JSON — never by rewriting the
# document directly. The frontend renders each operation as a diff card
# the user accepts or rejects. Operations are pure data, applied
# client-side so the server doesn't have to track conversation state
# between turns.
# ---------------------------------------------------------------------------


CHAT_SYSTEM_PROMPT = """\
You are an expert assistant helping a user build a financial statement \
template in a visual editor. You have access to the CURRENT template (a \
block tree) and the CURRENT preview result (optional, may be missing). You \
converse in Brazilian Portuguese by default (follow the user's language \
otherwise).

Crucially: you do NOT rewrite the template directly. You propose changes \
as discrete OPERATIONS that the user will review and accept/reject one by \
one. Every response MUST be valid JSON with this shape:

{
  "assistant_message": "string (pt-BR, human reply)",
  "operations": [ ... list of operation objects, possibly empty ... ]
}

Allowed operation kinds (each an object with "op" and named fields):

1. { "op": "add_block",
     "parent_id": "existing_section_id | null",   // null = root
     "after_id": "existing_block_id | null",      // null = append at start/end
     "block": { type, id, label, ... }            // full block object
   }
   Inserts a new block. "after_id" anchors the position; if null the block
   appends to the end of the chosen parent.

2. { "op": "update_block",
     "id": "existing_block_id",
     "patch": { ...partial block fields... }
   }
   Patches specific fields on an existing block. Do not change "id" or
   "type" via update_block — use remove_block + add_block instead.

3. { "op": "remove_block", "id": "existing_block_id" }
   Removes a block (and its descendants for sections).

4. { "op": "set_period_preset",
     "preset": "single|yoy|ytd_vs_ytd|qoq_4|mom_12|balance_now_vs_prior"
   }
   Asks the UI to re-apply a period preset.

Rules:
- Use snake_case ids; ids must be unique across the current tree.
- Only reference ids that exist. When inserting, pick a parent_id that
  does exist and make up a fresh id for the new block.
- For subtotal/total blocks, set formula sensibly
  (e.g. "sum(children)" or "rev_total - taxes").
- Keep assistant_message concise (< 3 sentences). Mention what each
  operation will do in plain language — the UI renders the operations
  separately.
- If the user asks a question that doesn't need any template change,
  return { "assistant_message": "...", "operations": [] }.

Respond with ONLY the JSON object, no markdown, no preamble.
"""


ALLOWED_OPS = {"add_block", "update_block", "remove_block", "set_period_preset"}
ALLOWED_PRESETS = {
    "single", "yoy", "ytd_vs_ytd", "qoq_4", "mom_12", "balance_now_vs_prior",
}


def _validate_operations(ops: List[Any]) -> List[dict]:
    """Light structural validation of emitted operations.

    We drop operations that don't match the whitelist rather than raising —
    a single malformed op shouldn't torch the whole chat turn; the UI will
    render the assistant_message and the subset of good operations.
    """
    out: List[dict] = []
    for raw in ops or []:
        if not isinstance(raw, dict):
            continue
        op = raw.get("op")
        if op not in ALLOWED_OPS:
            log.warning("dropping unknown op: %r", op)
            continue
        if op == "add_block":
            block = raw.get("block")
            if not isinstance(block, dict) or not block.get("id") or not block.get("type"):
                continue
            out.append({
                "op": "add_block",
                "parent_id": raw.get("parent_id"),
                "after_id": raw.get("after_id"),
                "block": block,
            })
        elif op == "update_block":
            if not raw.get("id") or not isinstance(raw.get("patch"), dict):
                continue
            out.append({"op": "update_block", "id": raw["id"], "patch": raw["patch"]})
        elif op == "remove_block":
            if not raw.get("id"):
                continue
            out.append({"op": "remove_block", "id": raw["id"]})
        elif op == "set_period_preset":
            preset = raw.get("preset")
            if preset not in ALLOWED_PRESETS:
                continue
            out.append({"op": "set_period_preset", "preset": preset})
    return out


def explain(
    *,
    company_id: int,
    document: dict,
    result: dict,
    block_id: str,
    period_id: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Explain a single value in the preview.

    Looks up the block's calc memory (written by ``ReportCalculator`` at
    calculate-time), resolves the contributing account ids back to full
    names + codes, and asks the AI to compose a concise Portuguese
    explanation. If the cell has no memory (formula/rollup block, or a
    spacer), we still produce something useful — the block type, its
    formula, and the computed value itself.
    """
    if not isinstance(result, dict):
        raise AiAssistantError("missing result to explain")

    # Find the line
    lines = result.get("lines") or []
    line = next((l for l in lines if l.get("id") == block_id), None)
    if line is None:
        raise AiAssistantError(f"block id '{block_id}' not found in result")

    values = line.get("values") or {}
    value = values.get(period_id)
    if value is None and period_id not in values:
        raise AiAssistantError(
            f"period id '{period_id}' not present on block '{block_id}'"
        )

    periods = {p.get("id"): p for p in (result.get("periods") or [])}
    period = periods.get(period_id, {})

    memory = (line.get("memory") or {}).get(period_id) or {}
    account_ids = memory.get("account_ids") or []

    # Resolve account ids → names for the prompt (capped). ``Account`` is an
    # MPTTModel, so ``path`` is a method, not a column — compute per-row.
    accounts_detail: List[Dict[str, Any]] = []
    if account_ids:
        instances = list(
            Account.objects.filter(
                company_id=company_id, id__in=account_ids[:40]
            )
        )
        for a in instances:
            try:
                path = a.get_path() if hasattr(a, "get_path") else ""
            except Exception:
                path = ""
            accounts_detail.append({
                "id": a.id,
                "name": a.name,
                "account_code": a.account_code,
                "path": path,
            })

    # Locate the block in the document so we can include its type/formula
    block_info: Dict[str, Any] = {"id": block_id}

    def _find(blocks: List[dict]) -> Optional[dict]:
        for b in blocks or []:
            if b.get("id") == block_id:
                return b
            if b.get("type") == "section":
                hit = _find(b.get("children") or [])
                if hit:
                    return hit
        return None

    found = _find(document.get("blocks") or [])
    if found:
        for key in ("type", "label", "formula", "calculation_method",
                    "sign_policy", "accounts"):
            if found.get(key) is not None:
                block_info[key] = found[key]

    user_prompt = (
        "Explique em português, em 1–3 frases curtas, por que este valor "
        f"é {value} na coluna '{period.get('label', period_id)}' "
        f"(período tipo '{period.get('type')}'). "
        "Mencione as contas que contribuíram (com código + nome) e, se "
        "houver fórmula, refira-se a ela pelos nomes dos blocos. Não use "
        "markdown ou cabeçalhos — resposta em texto corrido.\n\n"
        f"Bloco: {json.dumps(block_info, ensure_ascii=False)}\n"
        f"Período: {json.dumps(period, ensure_ascii=False)}\n"
        f"Valor: {value}\n"
        f"Memória de cálculo: {json.dumps(memory, ensure_ascii=False)}\n"
        f"Contas envolvidas: {json.dumps(accounts_detail, ensure_ascii=False)}\n"
    )

    explanation_text: str
    try:
        client = ExternalAIClient(provider=provider, model=model)
        # Explain uses its own system prompt — simpler to ask for a raw JSON
        # wrapping a single "text" field than to reuse the chat schema.
        raw = _run_ai_call(
            client=client,
            prompt=user_prompt + '\n\nResponda com JSON: {"text": "<explicação>"}',
            system_prompt=(
                "Você é um contador sênior explicando valores a um "
                "usuário em um editor de demonstrativos. Seja direto, "
                "referencie códigos de contas quando existir, mas fale "
                "em português acessível."
            ),
            context=context,
            endpoint="explain",
        )
        explanation_text = str(raw.get("text") or "").strip()
        if not explanation_text:
            raise AiAssistantError("empty explanation text")
    except Exception as exc:
        # Any failure — missing API key, network, bad output, bad provider —
        # falls back to the deterministic coded explanation. This is the
        # core promise of the explain endpoint: users always get something.
        log.warning("explain: AI call failed, falling back to coded text: %s", exc)
        explanation_text = _coded_explanation(
            block_info=block_info,
            period=period,
            value=value,
            memory=memory,
            accounts=accounts_detail,
        )

    return {
        "text": explanation_text,
        "block_id": block_id,
        "period_id": period_id,
        "value": value,
        "accounts": accounts_detail,
    }


def _coded_explanation(
    *,
    block_info: Dict[str, Any],
    period: Dict[str, Any],
    value: Any,
    memory: Dict[str, Any],
    accounts: List[Dict[str, Any]],
) -> str:
    """Deterministic fallback explanation when the AI is unavailable."""
    parts: List[str] = []
    btype = block_info.get("type", "linha")
    label = block_info.get("label") or block_info.get("id")
    period_label = period.get("label") or period.get("id")
    parts.append(f"{btype.capitalize()} '{label}' = {value} em '{period_label}'.")

    method = block_info.get("calculation_method") or memory.get("calc_method")
    if method:
        parts.append(f"Método de cálculo: {method}.")

    formula = block_info.get("formula")
    if formula:
        parts.append(f"Fórmula: {formula}.")

    if accounts:
        samples = ", ".join(
            f"{a.get('account_code') or '—'} {a.get('name', '')}".strip()
            for a in accounts[:5]
        )
        extra = (
            f" (+{len(accounts) - 5} outras)" if len(accounts) > 5 else ""
        )
        parts.append(f"Contas envolvidas: {samples}{extra}.")

    sign = block_info.get("sign_policy")
    if sign and sign != "natural":
        parts.append(f"Sinal: {sign}.")

    return " ".join(parts)


def chat(
    *,
    messages: List[dict],
    document: dict,
    preview_result: Optional[dict] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """One chat turn.

    Parameters
    ----------
    messages : list of {"role": "user"|"assistant", "content": str}
        Conversation so far; the last message is the user's new turn.
    document : current template doc (source of truth for the AI's context)
    preview_result : optional — the most recent /calculate/ result, so the
        AI can reference actual numbers in its replies.
    """
    if not messages:
        raise AiAssistantError("chat requires at least one message")

    try:
        validate_document(document)
    except PydanticValidationError as exc:
        raise AiAssistantError(f"document failed validation: {exc}") from exc

    # Summarize the preview if present — the full result can be large.
    preview_summary = ""
    if preview_result and isinstance(preview_result, dict):
        periods = preview_result.get("periods") or []
        lines_count = len(preview_result.get("lines") or [])
        warnings_count = len(preview_result.get("warnings") or [])
        preview_summary = (
            f"\nPREVIEW RESULT (summary):\n"
            f"- periods: {[p.get('id') for p in periods]}\n"
            f"- lines: {lines_count}\n"
            f"- warnings: {warnings_count}\n"
        )

    # Compose the user prompt carrying the current document + conversation.
    conv = "\n".join(
        f"{m.get('role', 'user').upper()}: {m.get('content', '')}"
        for m in messages[-10:]  # last 10 turns — cheap memory cap
    )
    user_prompt = (
        f"Current template (JSON):\n{json.dumps(document, ensure_ascii=False)}\n"
        f"{preview_summary}\n"
        f"Conversation:\n{conv}\n\n"
        f"Respond with JSON: {{\"assistant_message\": \"...\", \"operations\": [...]}}"
    )

    try:
        client = ExternalAIClient(provider=provider, model=model)
    except Exception as exc:
        raise AiAssistantError(f"AI client init failed: {exc}") from exc

    try:
        raw = _run_ai_call(
            client=client, prompt=user_prompt, system_prompt=CHAT_SYSTEM_PROMPT,
            context=context, endpoint="chat",
        )
    except ExternalAIError as exc:
        raise AiAssistantError(f"AI call failed: {exc}") from exc

    assistant_message = str(raw.get("assistant_message") or "").strip()
    operations = _validate_operations(raw.get("operations") or [])
    return {"assistant_message": assistant_message, "operations": operations}
