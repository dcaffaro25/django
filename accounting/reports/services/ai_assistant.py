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
import re
import time
from typing import Any, Dict, List, Optional

from pydantic import ValidationError as PydanticValidationError

from accounting.models import Account
from accounting.services.external_ai_client import ExternalAIClient, ExternalAIError

from .ai_pricing import estimate_cost_usd
from .document_schema import (
    AccountsSelector,
    SlimTemplateDocument,
    TemplateDocument,
    slim_to_canonical,
    to_openai_strict_schema,
    validate_document,
)


log = logging.getLogger(__name__)


class AiAssistantError(Exception):
    """Raised when the AI service fails to produce a valid template."""


# --- Error humanization ---------------------------------------------------


def _humanize_ai_error(exc: BaseException) -> str:
    """Turn a raw provider error into a pt-BR message the UI can surface.

    We keep the original exception's message available via ``exc.__cause__``
    for logs; the returned string is what users see in the frontend's toast
    or modal banner.
    """
    msg = str(exc) or ""
    low = msg.lower()

    # Context length exceeded — separate from rate limit (400 error class).
    if (
        "context_length" in low
        or "context length" in low
        or "maximum context" in low
    ):
        return (
            "Prompt excedeu o tamanho máximo do modelo. "
            "Reduza o número de blocos ou divida o modelo."
        )

    # OpenAI / Anthropic 429: rate limits (per-minute tokens or requests).
    if "rate_limit" in low or "429" in msg or "too many requests" in low:
        if "tokens per min" in low or "tpm" in low:
            return (
                "Limite de tokens por minuto do provedor atingido. "
                "Aguarde ~1 minuto e tente novamente, ou peça ao admin "
                "para subir o tier da conta OpenAI (adicionar método de "
                "pagamento eleva de 10k para 30k TPM)."
            )
        return (
            "Provedor de IA pediu para aguardar (limite de requisições). "
            "Tente novamente em instantes."
        )

    # Provider auth
    if "invalid_api_key" in low or "incorrect api key" in low or "401" in msg:
        return (
            "Chave de IA inválida ou expirada. Peça ao admin para "
            "revalidar a chave em Ajustes → Uso da IA."
        )

    # Quota exhausted (distinct from rate limit — account has no credits)
    if "insufficient_quota" in low or "billing" in low and "quota" in low:
        return (
            "A conta do provedor de IA está sem saldo. "
            "Peça ao admin para recarregar créditos."
        )

    # Content policy refusals
    if "content_policy" in low or "content policy" in low:
        return (
            "O provedor recusou a geração por política de conteúdo. "
            "Reformule a solicitação."
        )

    # Fallback — return the original, trimmed. Useful during dev.
    return msg[:300] or "Falha ao contatar o provedor de IA."


# --- Usage-logging helper ---------------------------------------------------


def _run_ai_call(
    *,
    client: ExternalAIClient,
    prompt: str,
    system_prompt: Optional[str],
    context: Optional[Dict[str, Any]],
    endpoint: str,
    response_schema: Optional[Dict[str, Any]] = None,
    schema_name: str = "Response",
) -> Dict[str, Any]:
    """Invoke ``client.generate_json_with_meta`` and write an ``AIUsageLog``
    row whether the call succeeds or fails.

    ``context`` carries the request-scoped attribution (``user_id``,
    ``company_id``); when it's ``None`` (e.g. internal calls, tests) we still
    make the AI call but skip logging. Logging failures never propagate — a
    DB hiccup must never make an otherwise-successful AI call look broken.

    ``response_schema`` (optional): when supplied, OpenAI uses Structured
    Outputs and we skip the repair pass downstream. Anthropic ignores it
    and stays on prompt-based JSON for now.
    """
    t0 = time.time()
    try:
        resp = client.generate_json_with_meta(
            prompt, system_prompt=system_prompt,
            response_schema=response_schema, schema_name=schema_name,
        )
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


def _build_chart_context(company_id: int, limit: int = 150) -> Dict[str, Any]:
    """Summarize a tenant's chart of accounts into a compact structure for
    the AI prompt. Returns a dict with top-level stats and a sample list.

    Prompt-size tuning (post the 45k-token 429 incident):
    - Default cap is 150 accounts, not 400 — saves ~15k tokens on a
      large chart. The AI works with code_prefix patterns, so unseen
      accounts still match at calculate-time.
    - Accounts with a non-empty ``account_code`` are preferred; coded
      accounts are more useful for pattern selectors and waste fewer
      tokens than paths.

    Performance (post PR 9):
      - ``Account.get_path()`` walks ``parent.parent.parent…`` one FK
        hop at a time, which fires a DB round-trip per step. On Railway
        latency that's ~300ms × 5-6 levels × 150 accounts ≈ **45s** just
        to build this context. We now pre-load every active account for
        the company in ONE query and compute paths in Python from the
        resulting ``{id → (name, parent_id)}`` map. O(1) queries, not
        O(N×depth).
    """
    base = Account.objects.filter(company_id=company_id, is_active=True)
    total = base.count()

    # Pre-load the full company chart in one round-trip. For datbaby
    # (~250 accounts) this is <10KB payload; for the largest realistic
    # chart (~2k accounts) still well under a second. We use
    # ``values`` instead of model instances so the ``parent`` FK comes
    # back as ``parent_id`` — no attribute access triggers a second
    # query for lazy relations.
    all_rows = list(
        base.values("id", "name", "account_code", "account_direction", "level", "parent_id")
    )
    by_id = {r["id"]: r for r in all_rows}

    def _path_of(row: Dict[str, Any]) -> str:
        """Walk the pre-loaded parent map (all in memory)."""
        parts: List[str] = []
        current = row
        # Guard against pathological cycles — shouldn't happen in MPTT
        # but a bad import could break the invariant.
        visited: set[int] = set()
        while current is not None and current["id"] not in visited:
            parts.insert(0, current["name"])
            visited.add(current["id"])
            pid = current.get("parent_id")
            current = by_id.get(pid) if pid is not None else None
        return " > ".join(parts)

    # Prefer coded accounts; they're shorter + more useful for patterns.
    # Fall back to all active accounts when the chart isn't coded.
    #
    # Filter out auto-generated artifact codes from the "coded" pool.
    # Two patterns observed on Evolat's chart:
    #   * ``1.1.1.BANK.27`` — bank-account integration auto-fills
    #     these when a BankAccount is linked to a leaf GL row.
    #   * ``1.1.1.PENDING`` — the "Bank Clearing (Pending)" sentinel
    #     account uses a similar non-numeric tail.
    # General rule: real CoA codes are numeric segments separated by
    # dots (e.g. ``4.01``, ``1.1.1``); ANY segment containing a
    # non-digit means the code was auto-generated. Including such
    # codes in the sample tricked the AI into emitting
    # ``code_prefix: "1.1.1.BANK"`` style selectors that can't
    # disambiguate operator-meaningful categories.
    _REAL_CODE_RE = re.compile(r"^\d+(?:\.\d+)*$")

    def _is_meaningful_code(c: Optional[str]) -> bool:
        c = (c or "").strip()
        if not c or c == "0":
            return False
        return bool(_REAL_CODE_RE.match(c))

    coded = [r for r in all_rows if _is_meaningful_code(r["account_code"])]
    coded.sort(key=lambda r: (r["account_code"] or "", r["name"] or ""))
    sample_rows = coded[:limit]
    if len(sample_rows) < limit:
        # Top up with uncoded (incl. artifact-coded) accounts to fill
        # the budget. The path/name still carries the operator-facing
        # meaning even when no real code exists.
        uncoded = [r for r in all_rows if not _is_meaningful_code(r["account_code"])]
        uncoded.sort(key=lambda r: r["name"] or "")
        sample_rows.extend(uncoded[: limit - len(sample_rows)])

    accounts: List[Dict[str, Any]] = []
    for r in sample_rows:
        path = _path_of(r)
        # Hide artifact codes from the prompt entirely. Showing the
        # numeric id would also leak through ``account_ids``, but the
        # path stays meaningful, so we just blank the code column
        # instead. Keeps real codes (when present) intact.
        code = r["account_code"] or ""
        if not _is_meaningful_code(code):
            code = ""
        accounts.append({
            "id": r["id"],  # required for path_contains-failed fallbacks + account_ids selectors
            "code": code,
            "name": r["name"],
            # Truncate path — most value is at the top of the hierarchy;
            # we already give the AI the code and direction.
            "path": path[:120],
            "direction": r["account_direction"],
            "level": r["level"],
        })
    return {
        "total_accounts": total,
        "sampled": len(sample_rows),
        "accounts": accounts,
    }


# --- Prompts ---------------------------------------------------------------


_SYSTEM_PROMPT = """\
You are a senior Brazilian accountant and financial reporting expert with \
deep knowledge of IFRS and BR GAAP. You design financial statement templates \
that are compliant, well-structured, and match the company's actual chart of \
accounts.

Respond with ONLY valid JSON — no markdown, no commentary, no preamble.

The JSON is a FLAT list of blocks (not nested). Every block carries its \
own ``id``; children reference their parent via ``parent_id``. The server \
reassembles the tree before persisting. This flat shape is mandatory — \
do NOT emit ``children: [...]``; emit child blocks as siblings with \
``parent_id`` pointing to their section.

{
  "name": "string (pt-BR)",
  "report_type": "income_statement" | "balance_sheet" | "cash_flow",
  "defaults": {
    "calculation_method": "net_movement" | "ending_balance" | ...,
    "sign_policy": "natural" | "invert" | "absolute",
    "scale": "none" | "K" | "M" | "B",
    "decimal_places": 2
  },
  "blocks": [
    { "type": "section",
      "id": "revenue", "label": "Receita Bruta", "parent_id": null,
      "defaults": { "calculation_method": "net_movement" } },
    { "type": "line",
      "id": "sales", "label": "Vendas", "parent_id": "revenue",
      "accounts": { "code_prefix": "4.01", "include_descendants": true } },
    { "type": "subtotal",
      "id": "revenue_total", "label": "Receita Total", "parent_id": "revenue",
      "formula": "sum(children)" },
    { "type": "total",
      "id": "net_income", "label": "Lucro Líquido", "parent_id": null,
      "formula": "revenue_total - expenses_total" },
    { "type": "header",
      "id": "hdr_results", "label": "Resultado", "parent_id": null },
    { "type": "spacer", "id": "sp_1" }
  ]
}

Rules (STRICT):
- Block ids MUST match ^[A-Za-z_][A-Za-z0-9_]*$ and be unique.
- ``parent_id`` must either be null (root) or reference an existing section's id.
  Only ``section`` blocks may be parents.
- Formulas reference other block ids (e.g. "revenue_gross - taxes") or use
  the helpers sum(children) / abs(x) / min(a,b) / max(a,b). The special
  identifier "children" is only valid inside sum/min/max/abs.
- For income_statement use defaults.calculation_method = "net_movement".
- For balance_sheet use defaults.calculation_method = "ending_balance".
- For cash_flow use a mix: opening_balance + net_movement + ending_balance.

ACCOUNT WIRING (CRITICAL — operators rely on this for real numbers):
- Every ``line`` block MUST set ``accounts`` to a selector that matches
  at least one account in the chart provided below. Lines without
  account wiring produce zero — operators will reject the template.
- The ``accounts`` selector accepts THREE alternative fields. Pick ONE
  per line based on the chart's coding state:
  1. ``code_prefix: "<code>"`` — when the chart has real numeric codes
     (e.g. ``4.01``). Match a code prefix that EXISTS verbatim in the
     ``code`` column below; ``include_descendants`` defaults to true so
     deeper accounts are picked up automatically.
  2. ``path_contains: "<substring>"`` — when the chart has no real
     codes (column shows ``—``) or your line's scope crosses code
     groups. Match a stable substring of the ``path`` column (e.g.
     ``path_contains: "Despesas Comerciais"``). Substring is matched
     against the ``parent > child > grandchild`` chain.
  3. ``account_ids: [<id>, ...]`` — explicit list of ids from the
     ``#<id>`` column. Use this when neither prefix nor path can
     express the line's scope cleanly (e.g. "Outras Receitas" pulling
     from disjoint sub-trees).
- Choose the most stable selector available. NEVER invent codes that
  don't appear verbatim in the chart's code column. NEVER invent
  account ids that aren't shown.
- ``subtotal`` blocks usually use a formula (``sum(children)``) and
  can omit ``accounts``. ``total`` blocks always use a formula.
- The line's ``label`` should describe the BUSINESS CATEGORY (not
  necessarily the account name). The wiring carries the technical
  link; the label carries the operator-facing meaning.

STRUCTURE:
- Use sections for logical grouping; put a subtotal at the end of each
  section (its ``parent_id`` = the section's id). Top-level totals
  (net income, total assets, etc.) have ``parent_id: null``.
- Emit blocks in display order — parents first, then their children,
  then sibling blocks.
- All labels and the template name MUST be in Brazilian Portuguese (pt-BR).
"""


def _build_user_prompt(report_type: str, preferences: str, chart: Dict[str, Any]) -> str:
    # ``id`` is included so the AI can emit ``account_ids`` selectors
    # when ``code_prefix`` and ``path_contains`` aren't a good fit. Old
    # format dropped the id, forcing the AI to invent codes that don't
    # exist on codeless tenants.
    accounts_repr = "\n".join(
        f"  #{a.get('id', '?'):>5}  {a['code'] or '—':<12} | L{a['level']} | {a['path'] or a['name']}"
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

    # Detect "useless code" tenants (Evolat-style charts where the
    # operator never coded the CoA but a few auto-generated artifact
    # codes leak in -- e.g. "1.1.1.BANK.27" rows that the bank-account
    # linker creates). Old ``distinct_codes <= {"", "0"}`` check failed
    # for those tenants because the BANK-pseudo codes broke the subset
    # match, so the AI got no hint and emitted ``code_prefix`` against
    # codes that don't exist as real prefixes -- every line resolved
    # to zero accounts.
    #
    # New rule: count rows that have a *real* code (non-empty,
    # non-placeholder, not a BANK link artifact) and call the chart
    # codeless if that's < 20% of the sample. The 20% threshold is
    # generous on purpose -- a chart with one or two real codes among
    # hundreds of uncoded rows is operationally codeless.
    # Real CoA codes are numeric segments separated by dots
    # (e.g. ``4.01`` or ``1.1.1``). Any non-numeric segment marks the
    # code as auto-generated (BANK link, PENDING sentinel, etc.) — see
    # ``_build_chart_context`` for the same filter applied to sampling.
    _REAL_CODE_PROMPT_RE = re.compile(r"^\d+(?:\.\d+)*$")

    def _is_real_code(c: str) -> bool:
        c = (c or "").strip()
        if not c or c == "0":
            return False
        return bool(_REAL_CODE_PROMPT_RE.match(c))

    real_coded = sum(1 for a in chart["accounts"] if _is_real_code(a.get("code") or ""))
    sample_size = max(1, len(chart["accounts"]))
    useless_codes = (real_coded / sample_size) < 0.20
    coding_hint = ""
    if useless_codes:
        coding_hint = (
            "\nIMPORTANT — this company's chart has no usable account "
            "codes (most accounts are uncoded or only carry "
            "auto-generated artifact codes like ``1.1.1.BANK.27``). DO "
            "NOT emit ``code_prefix`` selectors. Use either:\n"
            "  * ``path_contains: \"<substring>\"`` — substring match "
            "against the parent-chain path shown in the chart below "
            "(e.g. ``path_contains: \"Despesas Comerciais\"``), OR\n"
            "  * ``account_ids: [<id>, ...]`` — explicit list of "
            "account ids from the chart.\n"
            "Never emit a code that doesn't appear verbatim in the "
            "chart's code column."
        )

    return (
        f"Generate a {report_type} template for the following company.\n"
        f"{pref_line}\n"
        f"{note}{coding_hint}\n\n"
        f"Chart of accounts (id | code | level | path):\n{accounts_repr}"
    )


# --- Account-id hydration --------------------------------------------------


def _hydrate_account_ids(
    doc_dict: Dict[str, Any], *, company_id: int,
) -> tuple[Dict[str, Any], List[str]]:
    """Walk every line / subtotal block and pin ``accounts.account_ids`` to
    the concrete list of accounts the selector currently matches against
    the company's chart of accounts.

    Why
    ===
    Without this pass, an AI-generated line carries only a coarse
    selector — e.g. ``code_prefix: "4.01"`` — and the operator has no
    visibility into WHICH accounts will feed it until they actually
    run the report. Worse: a hallucinated prefix the AI invented
    (``"5.99"``) doesn't match any real account, and the line silently
    produces zeros instead of failing loudly.

    Hydrating ``account_ids`` at generate-time:
      * **Auditability** — operators can see exactly which CoA accounts
        will be summed under each line of the draft, *before* saving.
      * **Surfaces empty matches** — the returned ``unmapped`` list
        names every line whose selector resolved to zero accounts so
        callers can warn / log / retry.
      * **Forward-compatible** — :class:`AccountResolver` ORs
        ``account_ids`` with ``code_prefix`` / ``path_contains``, so a
        new account added later that matches the prefix still flows
        into the line on the next calc. The hydrated list is a
        snapshot, not a hard cap.

    The dict is mutated in place AND returned (alongside the unmapped
    list) so callers can chain. We never overwrite an explicit
    ``account_ids`` the AI itself emitted — if the model already
    listed concrete accounts, that's its preferred wiring and the
    code_prefix is just a complementary hint.

    Notes
    -----
    Sections recursively contain children, so the walk is depth-first.
    Resolution failures (malformed selector, transient DB error) log
    and continue — a partial hydration is more useful than aborting
    the whole generation.
    """
    # Local import to avoid pulling the resolver — and its Q-builder
    # plus MPTT walks — at module load time. ``generate_template`` is
    # the only caller; the cost is paid only when the AI flow runs.
    from .intelligence import AccountResolver

    resolver = AccountResolver(company_id=company_id)
    unmapped: List[str] = []
    hydrated_count = 0

    def _walk(blocks: Any) -> None:
        nonlocal hydrated_count
        if not isinstance(blocks, list):
            return
        for b in blocks:
            if not isinstance(b, dict):
                continue
            sel = b.get("accounts")
            if (
                isinstance(sel, dict)
                and (sel.get("code_prefix") or sel.get("path_contains") or sel.get("account_ids"))
            ):
                # Only re-resolve when account_ids is empty — preserves
                # any explicit list the AI (or a downstream refine)
                # already produced. ``[]`` and ``None`` both count as
                # "needs hydration".
                if not sel.get("account_ids"):
                    try:
                        selector_obj = AccountsSelector(**sel)
                        accounts = resolver.resolve(selector_obj)
                        ids = sorted({a.id for a in accounts})
                        if ids:
                            sel["account_ids"] = ids
                            hydrated_count += 1
                        else:
                            unmapped.append(b.get("id") or "<unknown>")
                    except Exception as exc:  # noqa: BLE001 — log+skip
                        log.warning(
                            "ai_assistant._hydrate_account_ids: failed for block %r: %s",
                            b.get("id"), exc,
                        )
            # Sections own a ``children`` list — recurse so nested
            # lines also get hydrated.
            children = b.get("children")
            if children:
                _walk(children)

    _walk(doc_dict.get("blocks"))

    log.info(
        "ai_assistant: hydrated account_ids on %d line(s); %d unmapped",
        hydrated_count, len(unmapped),
    )
    if unmapped:
        log.warning(
            "ai_assistant: %d line(s) have no matching CoA accounts: %s",
            len(unmapped), ", ".join(unmapped[:10]),
        )
    return doc_dict, unmapped


# --- Public entry point ----------------------------------------------------


QUALITY_FAST = "fast"
QUALITY_STANDARD = "standard"
_VALID_QUALITIES = (QUALITY_FAST, QUALITY_STANDARD)


def _resolve_openai_model(
    quality: Optional[str],
    explicit_model: Optional[str],
) -> Optional[str]:
    """Pick an OpenAI model for ``generate_template`` from the quality
    knob. Callers can still override with an explicit ``model`` string
    (used by debugging / experimentation paths), which wins.

    ``fast`` (new default) routes to ``gpt-4o-mini`` — schema-constrained
    output via Structured Outputs keeps quality ≈ parity with ``gpt-4o``
    for template generation at ~3× streaming speed. ``standard`` routes
    to ``gpt-4o`` for the cases where the operator explicitly wants the
    larger model (unusually complex preferences or new account types
    the schema-only prompt can't disambiguate).

    Returns ``None`` to mean "let the client pick its default" — the
    client then falls back to ``TEMPLATE_AI_MODEL`` env var then
    ``gpt-4o``, preserving the escape hatch.
    """
    if explicit_model:
        return explicit_model
    q = (quality or QUALITY_FAST).strip().lower()
    if q == QUALITY_STANDARD:
        return "gpt-4o"
    # Anything else (including invalid strings) collapses to fast.
    return "gpt-4o-mini"


def generate_template(
    *,
    company_id: int,
    report_type: str,
    preferences: str = "",
    provider: Optional[str] = None,
    model: Optional[str] = None,
    quality: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Call the AI and return a validated :class:`TemplateDocument` as a dict.

    ``quality`` (new): ``"fast"`` (default) → ``gpt-4o-mini``;
    ``"standard"`` → ``gpt-4o``. Ignored when ``model`` is set
    explicitly or when ``provider`` isn't OpenAI (Anthropic's model
    choice is still controlled by env var).

    Raises
    ------
    AiAssistantError
        When the AI client can't be initialised (missing API key),
        returns non-JSON, produces an unparseable payload, or the payload
        doesn't conform to the document schema after one repair attempt.
    """
    chart = _build_chart_context(company_id=company_id)
    user_prompt = _build_user_prompt(report_type, preferences, chart)

    using_structured_outputs = (provider or "").lower() in ("", "openai")
    effective_model = model
    if using_structured_outputs and not effective_model:
        effective_model = _resolve_openai_model(quality, explicit_model=None)

    try:
        # ``generate_template`` is the heaviest of our AI calls -- the
        # input prompt is ~4-5k tokens (the chart of accounts) and
        # the output runs to several thousand tokens for a typical
        # template. The default 120s ``ExternalAIClient`` timeout was
        # tripping ``APITimeoutError`` on Evolat-sized charts
        # (observed 131s on 2026-04-28). Bumping to 200s gives
        # headroom while staying inside the 300s gunicorn budget.
        #
        # ``max_tokens`` stays at the SDK ceiling (16k) -- a 8k cap
        # truncated mid-output on Evolat once the new prompt let the
        # AI emit ``account_ids`` arrays alongside ``path_contains``,
        # producing "Invalid JSON in AI response" because the slim
        # schema's strict JSON wasn't closed properly. The actual
        # observed completion size is ~3-5k tokens; 16k is just a
        # ceiling so a particularly chatty run doesn't get clipped.
        client = ExternalAIClient(
            provider=provider, model=effective_model,
            timeout=200.0,
        )
    except Exception as exc:
        raise AiAssistantError(f"AI client init failed: {exc}") from exc

    # On OpenAI we use Structured Outputs — the model is token-sampled
    # against the SLIM schema (flat blocks + parent_id + defaults
    # cascade; no decoration fields). Empirically the canonical
    # ``TemplateDocument`` schema times out ~100% of the time because
    # the recursive tree + decorative fields push the SO grammar
    # compile past the API's per-request budget. The slim variant
    # finishes with median ~17s and 100% reliability under the SDK's
    # default 2 retries.
    #
    # The slim output is converted back to the canonical shape in
    # :func:`slim_to_canonical` below, which fills in derivable fields
    # (``bold`` from block type, ``indent`` from depth) and rebuilds
    # the ``children`` tree from ``parent_id`` links.
    #
    # See ``scripts/bench_schemas.py`` for the empirical data behind
    # this choice.
    response_schema = (
        to_openai_strict_schema(SlimTemplateDocument.model_json_schema())
        if using_structured_outputs else None
    )

    log.info(
        "ai_assistant.generate_template: report_type=%s, accounts=%s/%s, "
        "prefs_len=%s, quality=%s, model=%s, structured_outputs=%s",
        report_type,
        chart["sampled"],
        chart["total_accounts"],
        len(preferences),
        quality or QUALITY_FAST,
        effective_model or "(client default)",
        using_structured_outputs,
    )

    try:
        raw = _run_ai_call(
            client=client, prompt=user_prompt, system_prompt=_SYSTEM_PROMPT,
            context=context, endpoint="generate_template",
            response_schema=response_schema, schema_name="TemplateDocument",
        )
    except ExternalAIError as exc:
        raise AiAssistantError(_humanize_ai_error(exc)) from exc

    # Under Structured Outputs the AI emits the SLIM shape. Convert it
    # to canonical before validation — the UI and save pipeline both
    # expect the full TemplateDocument tree. Under plain JSON mode
    # (Anthropic) the model was told to emit the slim shape too; if it
    # hallucinates and emits a ``children`` tree instead we still catch
    # that via the canonical validation below.
    if using_structured_outputs:
        raw = slim_to_canonical(raw, report_type=report_type)

    # Pydantic pass. Under Structured Outputs the slim→canonical converter
    # produced a well-formed tree; this is a belt-and-braces check for
    # cross-reference integrity (unique ids, formula block refs). Under
    # plain JSON mode (Anthropic) we still allow a single repair retry.
    try:
        doc_model = validate_document(raw)
    except PydanticValidationError as exc:
        if using_structured_outputs:
            # Reachable only if slim_to_canonical produced a doc that
            # fails the cross-ref check (e.g. duplicate ids). Log and
            # surface — repair wouldn't help since the AI is no longer
            # in the loop.
            log.error(
                "Slim-to-canonical conversion failed cross-ref validation: %s", exc,
            )
            raise AiAssistantError(
                f"Generated template failed validation: {exc}"
            ) from exc

        log.warning("AI document failed first-pass validation: %s", exc)
        # Repair prompt: only the failed doc + the validation errors, no
        # chart of accounts. Prevents the retry from blowing past the TPM
        # limit (our original 429 was on repair calls with chart resent).
        repair_prompt = (
            "The JSON below failed schema validation. Regenerate it "
            "corrected. Respond with ONLY the full corrected JSON.\n\n"
            f"Errors:\n{json.dumps(exc.errors(), indent=2)}\n\n"
            f"Previous (invalid) doc:\n{json.dumps(raw, ensure_ascii=False)}"
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
            raise AiAssistantError(_humanize_ai_error(exc2)) from exc2

    # Force the user-requested report_type in case the model produced a
    # different one — the UI expects it to match.
    doc_dict = doc_model.model_dump(mode="json")
    doc_dict["report_type"] = report_type

    # Hydrate ``accounts.account_ids`` against the live CoA so each
    # generated line carries the explicit list of accounts it covers
    # (instead of just an opaque code_prefix or path_contains). See
    # ``_hydrate_account_ids`` for the full rationale.
    #
    # ``unmapped`` lists block ids whose selector resolved to ZERO
    # accounts — the operator should review those before saving. We
    # attach it as a top-level dict alongside the document below so
    # the canonical TemplateDocument stays clean (``extra="forbid"``
    # would reject any embedded annotation, which would then trip
    # the save endpoint's pydantic validation).
    doc_dict, unmapped = _hydrate_account_ids(doc_dict, company_id=company_id)
    return {
        "document": doc_dict,
        "warnings": {"unmapped_lines": unmapped} if unmapped else {},
    }


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

    # Refine actions are label/structure tweaks — GPT-4o-mini does them
    # well at ~15% of the cost AND with ~20x higher TPM limit on Tier 1.
    # Heavier structural work (generate_template) stays on gpt-4o.
    effective_model = model
    if not effective_model and (provider or "").lower() in ("", "openai"):
        effective_model = "gpt-4o-mini"

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
        client = ExternalAIClient(provider=provider, model=effective_model)
    except Exception as exc:
        raise AiAssistantError(f"AI client init failed: {exc}") from exc

    log.info("ai_assistant.refine_template: action=%s model=%s", action, client.model)

    try:
        raw = _run_ai_call(
            client=client, prompt=user_prompt, system_prompt=_SYSTEM_PROMPT,
            context=context, endpoint=f"refine.{action}",
        )
    except ExternalAIError as exc:
        raise AiAssistantError(_humanize_ai_error(exc)) from exc

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
        raise AiAssistantError(_humanize_ai_error(exc)) from exc

    assistant_message = str(raw.get("assistant_message") or "").strip()
    operations = _validate_operations(raw.get("operations") or [])
    return {"assistant_message": assistant_message, "operations": operations}
