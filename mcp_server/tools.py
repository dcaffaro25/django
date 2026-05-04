"""Tool implementations for the Sysnord MCP server.

Each tool is a plain Python function that takes JSON-serialisable arguments
and returns a JSON-serialisable dict. Tools access the Django ORM directly
(in-process), so the MCP server runs as a Django management command.

All tools require ``company_id`` to enforce tenant scoping. The MCP transport
layer (``stdio.py``) wires them to the MCP protocol.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable

from django.db.models import Q

log = logging.getLogger(__name__)


def _to_jsonable(value: Any) -> Any:
    """Convert ORM/decimal/date values to JSON-friendly forms."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    return value


def _resolve_company(company_id: int):
    from multitenancy.models import Company
    try:
        return Company.objects.get(id=company_id)
    except Company.DoesNotExist as exc:
        raise ValueError(f"Company id={company_id} not found") from exc


# ---------------------------------------------------------------------------
# Tool: list_companies
# ---------------------------------------------------------------------------
def list_companies() -> dict[str, Any]:
    """Return all tenants the running process can see (no auth filtering;
    tenant scoping is via ``company_id`` on subsequent calls)."""
    from multitenancy.models import Company

    rows = list(
        Company.objects.order_by("id").values("id", "name", "subdomain")
    )
    return {"count": len(rows), "companies": rows}


# ---------------------------------------------------------------------------
# Tool: list_accounts
# ---------------------------------------------------------------------------
def list_accounts(
    company_id: int,
    search: str | None = None,
    report_category: str | None = None,
    only_active: bool = True,
    limit: int = 100,
) -> dict[str, Any]:
    """Return Chart-of-Accounts rows for a tenant. Filters: name/code search,
    report_category (e.g. ``ativo_circulante``, ``receita_operacional``),
    active-only.

    Note: this model has no ``account_type`` column — taxonomy lives in
    ``report_category`` (set via the demonstrativos pipeline) and ``tags``."""
    from accounting.models import Account

    qs = Account.objects.filter(company_id=company_id)
    if only_active:
        qs = qs.filter(is_active=True)
    if report_category:
        qs = qs.filter(report_category=report_category)
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(account_code__icontains=search))

    rows = list(
        qs.order_by("account_code").values(
            "id", "account_code", "name", "report_category", "account_direction",
            "is_active", "balance", "balance_date",
        )[:limit]
    )
    return {"count": len(rows), "accounts": _to_jsonable(rows)}


# ---------------------------------------------------------------------------
# Tool: get_account
# ---------------------------------------------------------------------------
def get_account(company_id: int, account_id: int) -> dict[str, Any]:
    from accounting.models import Account

    try:
        a = Account.objects.get(id=account_id, company_id=company_id)
    except Account.DoesNotExist:
        return {"error": f"Account {account_id} not found in company {company_id}"}

    return _to_jsonable({
        "id": a.id,
        "account_code": a.account_code,
        "name": a.name,
        "account_direction": a.account_direction,
        "parent_id": a.parent_id,
        "is_active": a.is_active,
        "balance": a.balance,
        "balance_date": a.balance_date,
        "report_category": getattr(a, "report_category", None),
        "cashflow_category": getattr(a, "cashflow_category", None),
        "tags": list(getattr(a, "tags", []) or []),
    })


# ---------------------------------------------------------------------------
# Tool: get_transaction
# ---------------------------------------------------------------------------
def get_transaction(company_id: int, transaction_id: int) -> dict[str, Any]:
    from accounting.models import Transaction

    try:
        tx = Transaction.objects.prefetch_related("journal_entries__account").get(
            id=transaction_id, company_id=company_id
        )
    except Transaction.DoesNotExist:
        return {"error": f"Transaction {transaction_id} not found in company {company_id}"}

    jes = [
        {
            "id": je.id,
            "account_id": je.account_id,
            "account_code": je.account.account_code if je.account else None,
            "account_name": je.account.name if je.account else None,
            "debit_amount": je.debit_amount,
            "credit_amount": je.credit_amount,
            "is_reconciled": je.is_reconciled,
            "state": je.state,
            "date": je.date,
        }
        for je in tx.journal_entries.all()
    ]

    return _to_jsonable({
        "id": tx.id,
        "date": tx.date,
        "description": tx.description,
        "amount": getattr(tx, "amount", None),
        "nf_number": getattr(tx, "nf_number", None),
        "cnpj": getattr(tx, "cnpj", None),
        "balance_validated": getattr(tx, "balance_validated", None),
        "journal_entries": jes,
    })


# ---------------------------------------------------------------------------
# Tool: list_unreconciled_bank_transactions
# ---------------------------------------------------------------------------
def list_unreconciled_bank_transactions(
    company_id: int,
    bank_account_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List bank transactions that have no accepted/matched reconciliation.

    Used by the agent caller to figure out what's outstanding."""
    from accounting.models import BankTransaction

    qs = BankTransaction.objects.filter(company_id=company_id)
    qs = qs.exclude(reconciliations__status__in=["matched", "approved"])
    if bank_account_id:
        qs = qs.filter(bank_account_id=bank_account_id)
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)

    rows = list(
        qs.order_by("-date").values(
            "id", "date", "amount", "description", "bank_account_id",
            "reference_number", "cnpj", "status",
        )[:limit]
    )
    return {"count": len(rows), "bank_transactions": _to_jsonable(rows)}


# ---------------------------------------------------------------------------
# Tool: suggest_reconciliation
# ---------------------------------------------------------------------------
def suggest_reconciliation(
    company_id: int,
    bank_transaction_ids: list[int],
    max_suggestions: int = 5,
    min_confidence: float = 0.3,
) -> dict[str, Any]:
    """Wrap ``BankTransactionSuggestionService.suggest_book_transactions`` so
    an external agent can probe for matches without running an HTTP call."""
    from accounting.services.bank_transaction_suggestion_service import (
        BankTransactionSuggestionService,
    )

    svc = BankTransactionSuggestionService(company_id=company_id)
    result = svc.suggest_book_transactions(
        bank_transaction_ids=list(bank_transaction_ids),
        max_suggestions_per_bank=max_suggestions,
        min_confidence=min_confidence,
    )
    return _to_jsonable(result)


# ---------------------------------------------------------------------------
# Tool: get_invoice
# ---------------------------------------------------------------------------
def get_invoice(company_id: int, invoice_id: int) -> dict[str, Any]:
    from billing.models import Invoice

    try:
        inv = Invoice.objects.prefetch_related("lines").get(
            id=invoice_id, company_id=company_id
        )
    except Invoice.DoesNotExist:
        return {"error": f"Invoice {invoice_id} not found in company {company_id}"}

    lines = [
        {
            "id": line.id,
            "description": line.description,
            "quantity": line.quantity,
            "unit_price": line.unit_price,
            "total_price": line.total_price,
            "tax_amount": line.tax_amount,
            "product_service_id": line.product_service_id,
        }
        for line in inv.lines.all()
    ]
    return _to_jsonable({
        "id": inv.id,
        "invoice_number": inv.invoice_number,
        "invoice_type": inv.invoice_type,
        "invoice_date": inv.invoice_date,
        "due_date": inv.due_date,
        "partner_id": inv.partner_id,
        "status": inv.status,
        "fiscal_status": inv.fiscal_status,
        "total_amount": inv.total_amount,
        "tax_amount": inv.tax_amount,
        "discount_amount": inv.discount_amount,
        "critics_count": inv.critics_count,
        "lines": lines,
    })


# ---------------------------------------------------------------------------
# Tool: list_invoice_critics
# ---------------------------------------------------------------------------
def list_invoice_critics(company_id: int, invoice_id: int) -> dict[str, Any]:
    from billing.models import Invoice
    from billing.services.critics_service import (
        compute_critics_for_invoice,
        annotate_acknowledgements,
        critics_to_dict,
    )

    try:
        inv = Invoice.objects.get(id=invoice_id, company_id=company_id)
    except Invoice.DoesNotExist:
        return {"error": f"Invoice {invoice_id} not found in company {company_id}"}

    critics = compute_critics_for_invoice(inv)
    critics = annotate_acknowledgements(inv, critics)
    return _to_jsonable({
        "invoice_id": inv.id,
        "count": len(critics),
        "critics": critics_to_dict(critics),
    })


# ---------------------------------------------------------------------------
# Tool: get_nota_fiscal
# ---------------------------------------------------------------------------
def get_nota_fiscal(company_id: int, nf_id: int) -> dict[str, Any]:
    from billing.models_nfe import NotaFiscal

    try:
        nf = NotaFiscal.objects.prefetch_related("itens").get(
            id=nf_id, company_id=company_id
        )
    except NotaFiscal.DoesNotExist:
        return {"error": f"NotaFiscal {nf_id} not found in company {company_id}"}

    return _to_jsonable({
        "id": nf.id,
        "numero": nf.numero,
        "serie": nf.serie,
        "chave": nf.chave,
        "data_emissao": nf.data_emissao,
        "valor_nota": nf.valor_nota,
        "valor_produtos": nf.valor_produtos,
        "emit_cnpj": nf.emit_cnpj,
        "dest_cnpj": nf.dest_cnpj,
        "finalidade": nf.finalidade,
        "tipo_operacao": nf.tipo_operacao,
        "status_sefaz": nf.status_sefaz,
        "item_count": nf.itens.count(),
    })


# ---------------------------------------------------------------------------
# Tool: fetch_cnpj_from_receita
# ---------------------------------------------------------------------------
_CNPJ_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CNPJ_CACHE_TTL_SECONDS = 3600  # 1 hour — Receita data changes rarely


def fetch_cnpj_from_receita(cnpj: str) -> dict[str, Any]:
    """Look up a Brazilian CNPJ in the Receita Federal public registry.

    Backed by `BrasilAPI <https://brasilapi.com.br/docs#tag/CNPJ>`_'s
    public endpoint (no API key needed). Accepts CNPJ with or without
    punctuation; strips non-digits before the call. Cached for 1h to
    avoid hammering the upstream service.

    Returns a curated subset of the upstream payload — razão social,
    fantasia, situação cadastral, CNAE primário + secundárias, endereço,
    capital social, sócios. Tenant-agnostic (no ``company_id`` —
    pure external lookup)."""
    import re
    import time

    import requests

    digits = re.sub(r"\D", "", cnpj or "")
    if len(digits) != 14:
        return {
            "error": (
                f"CNPJ must be 14 digits — got {len(digits)} after stripping "
                "punctuation. Pass e.g. '12.345.678/0001-90' or '12345678000190'."
            )
        }

    cached = _CNPJ_CACHE.get(digits)
    if cached and (time.time() - cached[0]) < _CNPJ_CACHE_TTL_SECONDS:
        return cached[1]

    url = f"https://brasilapi.com.br/api/cnpj/v1/{digits}"
    try:
        resp = requests.get(url, timeout=8.0)
    except requests.RequestException as exc:
        return {"error": f"BrasilAPI unreachable: {exc}"}

    if resp.status_code == 404:
        return {"error": f"CNPJ {digits} not found in the Receita Federal registry."}
    if resp.status_code == 429:
        return {"error": "BrasilAPI rate-limited this request. Try again in a minute."}
    if resp.status_code >= 400:
        return {
            "error": f"BrasilAPI returned {resp.status_code}: {resp.text[:200]}"
        }

    try:
        raw = resp.json()
    except ValueError:
        return {"error": "BrasilAPI returned non-JSON response."}

    # Curate — full payload is ~50 fields; agent rarely needs all of them.
    cnaes_secundarias = [
        {"codigo": c.get("codigo"), "descricao": c.get("descricao")}
        for c in (raw.get("cnaes_secundarios") or [])[:10]
    ]
    socios = [
        {
            "nome": q.get("nome_socio"),
            "qualificacao": q.get("qualificacao_socio"),
            "data_entrada": q.get("data_entrada_sociedade"),
        }
        for q in (raw.get("qsa") or [])[:10]
    ]
    curated = {
        "cnpj": raw.get("cnpj"),
        "razao_social": raw.get("razao_social"),
        "nome_fantasia": raw.get("nome_fantasia"),
        "situacao_cadastral": raw.get("descricao_situacao_cadastral"),
        "data_situacao_cadastral": raw.get("data_situacao_cadastral"),
        "data_inicio_atividade": raw.get("data_inicio_atividade"),
        "natureza_juridica": raw.get("natureza_juridica"),
        "porte": raw.get("porte"),
        "capital_social": raw.get("capital_social"),
        "cnae_principal": {
            "codigo": raw.get("cnae_fiscal"),
            "descricao": raw.get("cnae_fiscal_descricao"),
        },
        "cnaes_secundarias": cnaes_secundarias,
        "endereco": {
            "logradouro": raw.get("logradouro"),
            "numero": raw.get("numero"),
            "complemento": raw.get("complemento"),
            "bairro": raw.get("bairro"),
            "municipio": raw.get("municipio"),
            "uf": raw.get("uf"),
            "cep": raw.get("cep"),
        },
        "telefone": raw.get("ddd_telefone_1"),
        "email": raw.get("email"),
        "socios": socios,
        "matriz_filial": "matriz" if raw.get("identificador_matriz_filial") == 1 else "filial",
    }
    _CNPJ_CACHE[digits] = (time.time(), curated)
    return _to_jsonable(curated)


# ---------------------------------------------------------------------------
# Tools: BCB Olinda / SGS — official Brazilian Central Bank time series
# ---------------------------------------------------------------------------
# Curated alias map. The agent shouldn't have to memorise SGS series IDs;
# it picks a friendly name and we resolve. Add as-needed.
_BCB_SERIES = {
    "selic":         {"id": 11,    "label": "Selic over (% a.d.)",      "unit": "% diário"},
    "selic_meta":    {"id": 432,   "label": "Selic meta (% a.a.)",      "unit": "% anual"},
    "cdi":           {"id": 12,    "label": "CDI (% a.d.)",             "unit": "% diário"},
    "ipca":          {"id": 433,   "label": "IPCA (% mês)",             "unit": "% mensal"},
    "igpm":          {"id": 189,   "label": "IGP-M (% mês)",            "unit": "% mensal"},
    "incc":          {"id": 192,   "label": "INCC-DI (% mês)",          "unit": "% mensal"},
    "ipca_15":       {"id": 7478,  "label": "IPCA-15 (% mês)",          "unit": "% mensal"},
    "tr":            {"id": 226,   "label": "TR (% mês)",               "unit": "% mensal"},
    "tjlp":          {"id": 256,   "label": "TJLP (% a.a.)",            "unit": "% anual"},
    "ptax_usd":      {"id": 1,     "label": "USD/BRL PTAX (compra)",    "unit": "R$"},
    "ptax_usd_venda":{"id": 10813, "label": "USD/BRL PTAX (venda)",     "unit": "R$"},
    "ptax_eur":      {"id": 21619, "label": "EUR/BRL PTAX (venda)",     "unit": "R$"},
}


def fetch_bcb_indicator(
    indicator: str,
    date_from: str | None = None,
    date_to: str | None = None,
    last_n: int | None = None,
) -> dict[str, Any]:
    """Fetch a Brazilian Central Bank time series (SGS/Olinda).

    Friendly indicator names: ``selic``, ``selic_meta``, ``cdi``,
    ``ipca``, ``igpm``, ``incc``, ``ipca_15``, ``tr``, ``tjlp``,
    ``ptax_usd``, ``ptax_usd_venda``, ``ptax_eur``. Pass either a date
    range (ISO YYYY-MM-DD) OR ``last_n`` to retrieve the most-recent
    N observations. If neither is supplied, defaults to ``last_n=1``
    (current value).

    No auth, no rate limit (BCB is generous), free."""
    import requests

    spec = _BCB_SERIES.get((indicator or "").lower())
    if not spec:
        return {
            "error": (
                f"Unknown indicator '{indicator}'. Valid: "
                + ", ".join(sorted(_BCB_SERIES.keys()))
            )
        }

    series_id = spec["id"]
    base = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series_id}/dados"

    if date_from or date_to:
        params: dict[str, str] = {"formato": "json"}
        if date_from:
            try:
                params["dataInicial"] = date.fromisoformat(date_from).strftime("%d/%m/%Y")
            except ValueError as exc:
                return {"error": f"Invalid date_from: {exc}"}
        if date_to:
            try:
                params["dataFinal"] = date.fromisoformat(date_to).strftime("%d/%m/%Y")
            except ValueError as exc:
                return {"error": f"Invalid date_to: {exc}"}
        url = base
    else:
        n = last_n if last_n and last_n > 0 else 1
        url = f"{base}/ultimos/{n}"
        params = {"formato": "json"}

    try:
        resp = requests.get(url, params=params, timeout=8.0)
    except requests.RequestException as exc:
        return {"error": f"BCB Olinda unreachable: {exc}"}
    if resp.status_code >= 400:
        return {"error": f"BCB Olinda returned {resp.status_code}: {resp.text[:200]}"}

    try:
        rows = resp.json()
    except ValueError:
        return {"error": "BCB Olinda returned non-JSON."}

    return {
        "indicator": indicator,
        "series_id": series_id,
        "label": spec["label"],
        "unit": spec["unit"],
        "count": len(rows),
        "observations": [
            {"date": r.get("data"), "value": r.get("valor")} for r in rows
        ],
    }


def fetch_ptax(currency: str, on_date: str | None = None) -> dict[str, Any]:
    """Fetch the BCB PTAX exchange rate for ``currency`` (e.g. ``USD``,
    ``EUR``, ``GBP``) on a given ISO date. If ``on_date`` omitted,
    returns the most-recent business-day quote.

    Returns bid + ask. Used by the BCB itself for accounting closes,
    so this is the canonical reference rate for revaluations.

    Source: BrasilAPI cambio (proxies BCB Olinda)."""
    import requests

    moeda = (currency or "").upper().strip()
    if not moeda or len(moeda) > 4:
        return {"error": f"currency must be a 3-letter code (e.g. 'USD', 'EUR'); got {currency!r}"}

    if on_date:
        try:
            d = date.fromisoformat(on_date)
        except ValueError as exc:
            return {"error": f"Invalid on_date: {exc}"}
        url = f"https://brasilapi.com.br/api/cambio/v1/cotacao/{moeda}/{d.isoformat()}"
    else:
        # Walk back up to 7 days to find the latest business-day quote.
        for back in range(0, 7):
            d = datetime.now().date() - timedelta(days=back)
            try_url = f"https://brasilapi.com.br/api/cambio/v1/cotacao/{moeda}/{d.isoformat()}"
            try:
                r = requests.get(try_url, timeout=6.0)
            except requests.RequestException:
                continue
            if r.status_code == 200:
                url = try_url
                break
        else:
            return {"error": f"No PTAX quote for {moeda} found in the last 7 days."}

    try:
        resp = requests.get(url, timeout=6.0)
    except requests.RequestException as exc:
        return {"error": f"BrasilAPI cambio unreachable: {exc}"}
    if resp.status_code == 404:
        return {"error": f"No PTAX quote for {moeda} on {d.isoformat()}."}
    if resp.status_code >= 400:
        return {"error": f"BrasilAPI cambio returned {resp.status_code}: {resp.text[:200]}"}

    raw = resp.json()
    # Response shape: {"cotacoes": [{"cotacao_compra", "cotacao_venda",
    # "data_hora_cotacao", "tipo_boletim"}, ...]} — multiple intraday
    # quotes. Prefer FECHAMENTO (closing PTAX); else fall back to the
    # last quote in the array (latest INTERMEDIÁRIO of the day).
    cotacoes = raw.get("cotacoes") or []
    if not cotacoes:
        return {"error": f"No PTAX quotes returned for {moeda} on {d.isoformat()}."}
    fechamento = next(
        (c for c in cotacoes if (c.get("tipo_boletim") or "").upper() == "FECHAMENTO"),
        None,
    )
    pick = fechamento or cotacoes[-1]
    return {
        "currency": moeda,
        "date": d.isoformat(),
        "bid": pick.get("cotacao_compra"),
        "ask": pick.get("cotacao_venda"),
        "official_date": pick.get("data_hora_cotacao"),
        "boletim": pick.get("tipo_boletim"),
        "intraday_quote_count": len(cotacoes),
    }


# ---------------------------------------------------------------------------
# Tool: fetch_cep
# ---------------------------------------------------------------------------
def fetch_cep(cep: str) -> dict[str, Any]:
    """Resolve a Brazilian CEP (postal code) to its address.

    Source: BrasilAPI (which fans out to multiple providers — Correios,
    ViaCEP, etc. — for resilience). Free, no auth."""
    import re

    import requests

    digits = re.sub(r"\D", "", cep or "")
    if len(digits) != 8:
        return {"error": f"CEP must be 8 digits — got {len(digits)} after stripping."}

    url = f"https://brasilapi.com.br/api/cep/v2/{digits}"
    try:
        resp = requests.get(url, timeout=6.0)
    except requests.RequestException as exc:
        return {"error": f"BrasilAPI CEP unreachable: {exc}"}
    if resp.status_code == 404:
        return {"error": f"CEP {digits} not found."}
    if resp.status_code >= 400:
        return {"error": f"BrasilAPI CEP returned {resp.status_code}: {resp.text[:200]}"}

    raw = resp.json()
    return {
        "cep": raw.get("cep"),
        "uf": raw.get("state"),
        "city": raw.get("city"),
        "neighborhood": raw.get("neighborhood"),
        "street": raw.get("street"),
        "service": raw.get("service"),
    }


# ---------------------------------------------------------------------------
# Tool: fetch_holidays_brazil
# ---------------------------------------------------------------------------
def fetch_holidays_brazil(year: int) -> dict[str, Any]:
    """Return federal holidays for the given year. Useful for working-day
    arithmetic (NF-e prazos, payment due dates, fiscal calendar).

    Source: BrasilAPI (national holidays only — state/municipal not
    included). Free, no auth."""
    import requests

    if not isinstance(year, int) or year < 1900 or year > 2100:
        return {"error": "year must be an integer between 1900 and 2100."}

    url = f"https://brasilapi.com.br/api/feriados/v1/{year}"
    try:
        resp = requests.get(url, timeout=6.0)
    except requests.RequestException as exc:
        return {"error": f"BrasilAPI feriados unreachable: {exc}"}
    if resp.status_code >= 400:
        return {"error": f"BrasilAPI feriados returned {resp.status_code}: {resp.text[:200]}"}

    rows = resp.json()
    return {
        "year": year,
        "count": len(rows),
        "holidays": [
            {"date": r.get("date"), "name": r.get("name"), "type": r.get("type")}
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# Tool: fetch_bank_by_code
# ---------------------------------------------------------------------------
def fetch_bank_by_code(code: str) -> dict[str, Any]:
    """Look up a Brazilian bank by COMPE code (3-digit, e.g. ``341``
    for Itaú) or ISPB (8-digit). Returns the official name, ISPB,
    COMPE, and full corporate name.

    Source: BrasilAPI banks (mirrors the BCB STR participants registry).
    Free, no auth."""
    import requests

    raw_code = (code or "").strip()
    if not raw_code:
        return {"error": "code is required (COMPE 3-digit or ISPB 8-digit)."}

    url = f"https://brasilapi.com.br/api/banks/v1/{raw_code}"
    try:
        resp = requests.get(url, timeout=6.0)
    except requests.RequestException as exc:
        return {"error": f"BrasilAPI banks unreachable: {exc}"}
    if resp.status_code == 404:
        return {"error": f"Bank {raw_code} not found."}
    if resp.status_code >= 400:
        return {"error": f"BrasilAPI banks returned {resp.status_code}: {resp.text[:200]}"}

    raw = resp.json()
    return {
        "ispb": raw.get("ispb"),
        "compe": raw.get("code"),
        "name": raw.get("name"),
        "full_name": raw.get("fullName"),
    }


# ---------------------------------------------------------------------------
# Tool: fetch_ncm
# ---------------------------------------------------------------------------
def fetch_ncm(code: str) -> dict[str, Any]:
    """Look up an NCM (Nomenclatura Comum do Mercosul) code. Used to
    classify products on NFes and determine tax incidence (IPI, ICMS-ST).

    Source: BrasilAPI NCM (mirrors Receita Federal). Free, no auth."""
    import re

    import requests

    digits = re.sub(r"\D", "", code or "")
    if len(digits) < 2 or len(digits) > 8:
        return {"error": f"NCM code should be 2-8 digits — got {len(digits)}."}

    url = f"https://brasilapi.com.br/api/ncm/v1/{digits}"
    try:
        resp = requests.get(url, timeout=6.0)
    except requests.RequestException as exc:
        return {"error": f"BrasilAPI NCM unreachable: {exc}"}
    if resp.status_code == 404:
        return {"error": f"NCM {digits} not found."}
    if resp.status_code >= 400:
        return {"error": f"BrasilAPI NCM returned {resp.status_code}: {resp.text[:200]}"}

    raw = resp.json()
    return {
        "codigo": raw.get("codigo"),
        "descricao": raw.get("descricao"),
        "data_inicio": raw.get("data_inicio"),
        "data_fim": raw.get("data_fim"),
        "tipo_ato": raw.get("tipo_ato"),
        "numero_ato": raw.get("numero_ato"),
    }


# ---------------------------------------------------------------------------
# Tool: fetch_cnae_info
# ---------------------------------------------------------------------------
def fetch_cnae_info(code: str) -> dict[str, Any]:
    """Look up a CNAE (Classificação Nacional de Atividades Econômicas)
    subclasse by 7-digit code (e.g. ``4711301`` for hipermercados).

    Returns the description, the divisão/grupo/classe hierarchy, and
    flags whether it's eligible for Simples Nacional (best-effort
    based on the IBGE classification only — final eligibility is in
    LC 123/2006 and Resolução CGSN 140/2018).

    Source: IBGE Servicos de Dados (concla)."""
    import re

    import requests

    digits = re.sub(r"\D", "", code or "")
    if len(digits) != 7:
        return {"error": f"CNAE subclasse must be 7 digits — got {len(digits)}."}

    url = f"https://servicodados.ibge.gov.br/api/v2/cnae/subclasses/{digits}"
    try:
        resp = requests.get(url, timeout=8.0)
    except requests.RequestException as exc:
        return {"error": f"IBGE CNAE unreachable: {exc}"}
    if resp.status_code == 404:
        return {"error": f"CNAE {digits} not found."}
    if resp.status_code >= 400:
        return {"error": f"IBGE CNAE returned {resp.status_code}: {resp.text[:200]}"}

    raw = resp.json()
    if isinstance(raw, list):
        if not raw:
            return {"error": f"CNAE {digits} not found (empty response)."}
        raw = raw[0]

    classe = raw.get("classe") or {}
    grupo = classe.get("grupo") or {}
    divisao = grupo.get("divisao") or {}
    secao = divisao.get("secao") or {}
    return {
        "codigo": raw.get("id"),
        "descricao": raw.get("descricao"),
        "classe": {"id": classe.get("id"), "descricao": classe.get("descricao")},
        "grupo": {"id": grupo.get("id"), "descricao": grupo.get("descricao")},
        "divisao": {"id": divisao.get("id"), "descricao": divisao.get("descricao")},
        "secao": {"id": secao.get("id"), "descricao": secao.get("descricao")},
        "observacoes": raw.get("observacoes") or [],
    }


# ---------------------------------------------------------------------------
# Tool: validate_cfop
# ---------------------------------------------------------------------------
# CFOP first digit semantics — fixed structure defined by Convênio S/Nº/70.
_CFOP_FIRST_DIGIT = {
    "1": ("entrada", "operações dentro do estado"),
    "2": ("entrada", "operações de outros estados"),
    "3": ("entrada", "operações do exterior"),
    "5": ("saída",   "operações dentro do estado"),
    "6": ("saída",   "operações para outros estados"),
    "7": ("saída",   "operações para o exterior"),
}
# Common-use slice — the full CFOP table has ~700 codes; this covers
# the ones the agent will see on >95% of NFes for trade/services in
# Brazil. Extend as the corpus grows.
_CFOP_COMMON = {
    "1101": "Compra para industrialização ou produção rural",
    "1102": "Compra para comercialização",
    "1124": "Industrialização efetuada por outra empresa",
    "1202": "Devolução de venda de mercadoria adquirida ou recebida de terceiros",
    "1411": "Devolução de venda de produção do estabelecimento em operação com produto sujeito a ST",
    "1551": "Compra de bem para o ativo imobilizado",
    "1556": "Compra de material para uso ou consumo",
    "1908": "Entrada de bem por conta de contrato de comodato",
    "1949": "Outra entrada de mercadoria ou prestação de serviço não especificada",
    "2101": "Compra para industrialização (interestadual)",
    "2102": "Compra para comercialização (interestadual)",
    "2202": "Devolução de venda (interestadual)",
    "2551": "Compra de bem para o ativo imobilizado (interestadual)",
    "3101": "Compra para industrialização (importação)",
    "3102": "Compra para comercialização (importação)",
    "5101": "Venda de produção do estabelecimento",
    "5102": "Venda de mercadoria adquirida ou recebida de terceiros",
    "5202": "Devolução de compra para industrialização",
    "5401": "Venda de produção do estabelecimento em operação com produto sujeito a ST",
    "5403": "Venda de mercadoria adquirida ou recebida de terceiros em operação com ST",
    "5405": "Venda sujeita a ST cuja retenção foi feita anteriormente",
    "5551": "Venda de bem do ativo imobilizado",
    "5556": "Venda de material de uso ou consumo",
    "5910": "Remessa em bonificação, doação ou brinde",
    "5949": "Outra saída de mercadoria ou prestação de serviço não especificada",
    "6101": "Venda de produção (interestadual)",
    "6102": "Venda de mercadoria de terceiros (interestadual)",
    "6202": "Devolução de compra (interestadual)",
    "6401": "Venda em operação com ST (interestadual)",
    "6551": "Venda de bem do ativo imobilizado (interestadual)",
    "7101": "Venda de produção (exportação)",
    "7102": "Venda de mercadoria de terceiros (exportação)",
}


def validate_cfop(code: str) -> dict[str, Any]:
    """Validate a Brazilian CFOP code and decode its semantics.

    Returns: ``valid`` flag, ``operation`` (entrada/saída), ``scope``
    (in-state / interstate / external), and a description if it's in
    the curated common set. Codes not in the common set return
    ``valid=True`` (assuming the format is right) but
    ``description=None`` — the agent should treat unknown codes as
    plausible-but-unverified.

    Pure local function; no network."""
    import re

    digits = re.sub(r"\D", "", code or "")
    if len(digits) != 4:
        return {
            "valid": False,
            "error": f"CFOP must be 4 digits — got {len(digits)}.",
        }

    first = digits[0]
    spec = _CFOP_FIRST_DIGIT.get(first)
    if not spec:
        return {
            "valid": False,
            "error": f"CFOP first digit must be 1/2/3 (entrada) or 5/6/7 (saída); got {first}.",
        }

    operation, scope = spec
    description = _CFOP_COMMON.get(digits)
    return {
        "valid": True,
        "code": digits,
        "operation": operation,
        "scope": scope,
        "description": description,
        "is_common": description is not None,
    }


# ---------------------------------------------------------------------------
# Tool: simples_nacional_annex_for_cnae
# ---------------------------------------------------------------------------
# Mapping of CNAE prefix → Anexo Simples Nacional (LC 123/2006 + LC 155/2016).
# This is a curated partial list; the canonical source is the Receita Federal
# tabela "Tabela CNAE x Simples Nacional". Anexos:
#   I   — Comércio
#   II  — Indústria
#   III — Serviços (regra geral, fator R não aplica)
#   IV  — Serviços (escritórios contábeis, advocatícios, etc.)
#   V   — Serviços (intelectuais, sujeitos a fator R)
_CNAE_ANEXO_RULES = (
    # Industria — divisões CNAE 05–33
    (("05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "15", "16",
      "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27", "28",
      "29", "30", "31", "32", "33"), "II", "Indústria"),
    # Comércio — divisões 45–47
    (("45", "46", "47"), "I", "Comércio"),
    # Construção civil — anexo IV
    (("41", "42", "43"), "IV", "Construção civil"),
    # Serviços contábeis / advocatícios / vigilância / limpeza — anexo IV
    (("69", "692", "801", "802", "812", "813"), "IV", "Serviços profissionais (anexo IV)"),
    # Serviços de tecnologia, saúde, ensino, engenharia — anexo III ou V
    # (depende de fator R; pre-LC 155 tinha distinção rígida)
    (("62", "63", "71", "72", "73", "74", "85", "86"), "III/V", "Serviços (sujeito a fator R)"),
    # Demais serviços → III
    (("49", "50", "51", "52", "53", "55", "56",
      "58", "59", "60", "61", "64", "65", "66", "68",
      "75", "77", "78", "79", "80", "81", "82",
      "84", "87", "88", "90", "91", "92", "93", "94", "95", "96", "97"), "III", "Serviços"),
)


def simples_nacional_annex_for_cnae(cnae: str) -> dict[str, Any]:
    """Best-effort: map a CNAE to the Simples Nacional anexo (I-V).

    Heuristic — based on CNAE divisão (first 2 digits). Some CNAEs have
    company-specific exceptions (escritórios de software started anexo
    III after LC 155, scientific consultancies anexo V…) that this map
    can't capture. Treat the result as a starting hint, not a final
    enquadramento. Pure local function, no network.

    Returns ``annex`` (one of 'I', 'II', 'III', 'IV', 'V', 'III/V', or
    null) and a ``rationale`` string."""
    import re

    digits = re.sub(r"\D", "", cnae or "")
    if len(digits) < 2:
        return {"error": f"CNAE must have at least 2 digits — got {len(digits)}."}

    div = digits[:2]
    for prefixes, annex, label in _CNAE_ANEXO_RULES:
        if div in prefixes or any(digits.startswith(p) for p in prefixes if len(p) > 2):
            return {
                "cnae": digits,
                "divisao": div,
                "annex": annex,
                "label": label,
                "note": (
                    "Heurística baseada na divisão CNAE. Verifique fator R, "
                    "atividade-fim e atividades vedadas (LC 123/2006, art. 17) "
                    "antes do enquadramento final."
                ),
            }

    return {
        "cnae": digits,
        "divisao": div,
        "annex": None,
        "label": "Não mapeado",
        "note": (
            f"Divisão {div} não está na tabela curada. Pode estar entre as "
            "atividades vedadas, ou requer enquadramento manual. Consulte a "
            "Receita Federal."
        ),
    }


# ---------------------------------------------------------------------------
# Tool: financial_statements
# ---------------------------------------------------------------------------
def financial_statements(
    company_id: int,
    date_from: str,
    date_to: str,
    basis: str = "accrual",
    include_pending: bool = False,
    entity_id: int | None = None,
) -> dict[str, Any]:
    """Wrap the cached financial-statements pipeline. Returns DRE + Balanço +
    DFC categories with totals (no per-account breakdown — use list_accounts
    for that)."""
    from accounting.services.financial_statements import (
        compute_financial_statements_cached,
    )

    try:
        df = date.fromisoformat(date_from) if isinstance(date_from, str) else date_from
        dt = date.fromisoformat(date_to) if isinstance(date_to, str) else date_to
    except (TypeError, ValueError) as exc:
        return {"error": f"Invalid date — use ISO YYYY-MM-DD. ({exc})"}

    if df > dt:
        return {"error": f"date_from ({df.isoformat()}) is after date_to ({dt.isoformat()})."}

    result = compute_financial_statements_cached(
        company_id=company_id,
        date_from=df,
        date_to=dt,
        entity_id=entity_id,
        basis=basis,
        include_pending=include_pending,
    )
    # Strip per-account drilldown to keep response small for the agent.
    # The pipeline returns each category as
    # ``{"key", "label", "amount", "accounts", "account_count"}``.
    trimmed = {
        "period": result.get("period"),
        "basis": result.get("basis"),
        "categories": [
            {
                "key": c.get("key"),
                "label": c.get("label"),
                "amount": c.get("amount"),
                "account_count": c.get("account_count"),
            }
            for c in (result.get("categories") or [])
        ],
        "cashflow": result.get("cashflow"),
        "cash_total": result.get("cash_total"),
    }
    return _to_jsonable(trimmed)


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    handler: Callable[..., dict[str, Any]]
    input_schema: dict[str, Any]


TOOLS: list[ToolDef] = [
    ToolDef(
        name="list_companies",
        description="List all tenants visible to the MCP server.",
        handler=list_companies,
        input_schema={"type": "object", "properties": {}, "required": []},
    ),
    ToolDef(
        name="list_accounts",
        description="List Chart-of-Accounts rows for a tenant. Supports search by name/code, "
                    "filter by report_category (e.g. 'ativo_circulante', 'receita_operacional'), "
                    "and active-only.",
        handler=list_accounts,
        input_schema={
            "type": "object",
            "properties": {
                "company_id": {"type": "integer"},
                "search": {"type": "string"},
                "report_category": {"type": "string"},
                "only_active": {"type": "boolean", "default": True},
                "limit": {"type": "integer", "default": 100},
            },
            "required": ["company_id"],
        },
    ),
    ToolDef(
        name="get_account",
        description="Get full detail of one account, including taxonomy tags.",
        handler=get_account,
        input_schema={
            "type": "object",
            "properties": {
                "company_id": {"type": "integer"},
                "account_id": {"type": "integer"},
            },
            "required": ["company_id", "account_id"],
        },
    ),
    ToolDef(
        name="get_transaction",
        description="Get a Transaction with all its JournalEntries (account + amounts).",
        handler=get_transaction,
        input_schema={
            "type": "object",
            "properties": {
                "company_id": {"type": "integer"},
                "transaction_id": {"type": "integer"},
            },
            "required": ["company_id", "transaction_id"],
        },
    ),
    ToolDef(
        name="list_unreconciled_bank_transactions",
        description="List bank transactions without an accepted/matched reconciliation. "
                    "Filterable by bank_account and date range.",
        handler=list_unreconciled_bank_transactions,
        input_schema={
            "type": "object",
            "properties": {
                "company_id": {"type": "integer"},
                "bank_account_id": {"type": "integer"},
                "date_from": {"type": "string", "format": "date"},
                "date_to": {"type": "string", "format": "date"},
                "limit": {"type": "integer", "default": 50},
            },
            "required": ["company_id"],
        },
    ),
    ToolDef(
        name="suggest_reconciliation",
        description="Run the embedding+score suggestion engine for one or more bank transactions. "
                    "Returns ranked suggestions of existing journal entries or create-new patterns.",
        handler=suggest_reconciliation,
        input_schema={
            "type": "object",
            "properties": {
                "company_id": {"type": "integer"},
                "bank_transaction_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                },
                "max_suggestions": {"type": "integer", "default": 5},
                "min_confidence": {"type": "number", "default": 0.3},
            },
            "required": ["company_id", "bank_transaction_ids"],
        },
    ),
    ToolDef(
        name="get_invoice",
        description="Get an Invoice with its lines and fiscal_status.",
        handler=get_invoice,
        input_schema={
            "type": "object",
            "properties": {
                "company_id": {"type": "integer"},
                "invoice_id": {"type": "integer"},
            },
            "required": ["company_id", "invoice_id"],
        },
    ),
    ToolDef(
        name="list_invoice_critics",
        description="List active critics (data-quality findings) for an Invoice. Severities: "
                    "info/warning/error.",
        handler=list_invoice_critics,
        input_schema={
            "type": "object",
            "properties": {
                "company_id": {"type": "integer"},
                "invoice_id": {"type": "integer"},
            },
            "required": ["company_id", "invoice_id"],
        },
    ),
    ToolDef(
        name="get_nota_fiscal",
        description="Get a NotaFiscal with key fiscal fields (chave, partes, status SEFAZ).",
        handler=get_nota_fiscal,
        input_schema={
            "type": "object",
            "properties": {
                "company_id": {"type": "integer"},
                "nf_id": {"type": "integer"},
            },
            "required": ["company_id", "nf_id"],
        },
    ),
    ToolDef(
        name="fetch_cnpj_from_receita",
        description="Look up a Brazilian CNPJ in the Receita Federal public registry "
                    "(via BrasilAPI). Returns razão social, situação, CNAE, endereço, "
                    "capital, sócios. Use it to verify a counterparty, classify a partner "
                    "by economic activity (CNAE), or check whether a CNPJ is active. "
                    "Tenant-agnostic — no company_id needed.",
        handler=fetch_cnpj_from_receita,
        input_schema={
            "type": "object",
            "properties": {
                "cnpj": {
                    "type": "string",
                    "description": "Brazilian CNPJ. Punctuation optional "
                                   "('12.345.678/0001-90' or '12345678000190').",
                },
            },
            "required": ["cnpj"],
        },
    ),
    ToolDef(
        name="fetch_bcb_indicator",
        description="Fetch a Brazilian Central Bank time-series indicator (Selic, CDI, "
                    "IPCA, IGP-M, INCC, TR, TJLP, USD/BRL PTAX, EUR/BRL PTAX). "
                    "Pass a friendly name and either a date range or last_n=N. "
                    "Use it to update receivables by CDI, validate a Selic-based "
                    "fine, compute FX revaluations, etc. No tenant scoping.",
        handler=fetch_bcb_indicator,
        input_schema={
            "type": "object",
            "properties": {
                "indicator": {
                    "type": "string",
                    "description": "selic | selic_meta | cdi | ipca | igpm | incc | "
                                   "ipca_15 | tr | tjlp | ptax_usd | ptax_usd_venda | ptax_eur",
                },
                "date_from": {"type": "string", "format": "date"},
                "date_to": {"type": "string", "format": "date"},
                "last_n": {"type": "integer", "description": "Last N observations (alternative to date range)"},
            },
            "required": ["indicator"],
        },
    ),
    ToolDef(
        name="fetch_ptax",
        description="Fetch the BCB PTAX exchange rate (bid + ask) for a currency on a "
                    "specific date — or the most recent business-day quote if date is "
                    "omitted. Canonical reference for revaluation/exposure reporting.",
        handler=fetch_ptax,
        input_schema={
            "type": "object",
            "properties": {
                "currency": {"type": "string", "description": "3-letter code (USD, EUR, GBP, JPY, …)"},
                "on_date": {"type": "string", "format": "date"},
            },
            "required": ["currency"],
        },
    ),
    ToolDef(
        name="fetch_cep",
        description="Resolve a Brazilian CEP (postal code) to its address (UF, city, "
                    "neighborhood, street). Useful when filling a partner endereço or "
                    "validating delivery info.",
        handler=fetch_cep,
        input_schema={
            "type": "object",
            "properties": {"cep": {"type": "string"}},
            "required": ["cep"],
        },
    ),
    ToolDef(
        name="fetch_holidays_brazil",
        description="Federal holidays for a given year. Used by the agent for "
                    "working-day arithmetic (NF-e prazos, payment due dates, fiscal "
                    "calendar). National only — state/municipal holidays not included.",
        handler=fetch_holidays_brazil,
        input_schema={
            "type": "object",
            "properties": {"year": {"type": "integer", "minimum": 1900, "maximum": 2100}},
            "required": ["year"],
        },
    ),
    ToolDef(
        name="fetch_bank_by_code",
        description="Look up a Brazilian bank by COMPE 3-digit code (e.g. '341' = Itaú) "
                    "or 8-digit ISPB. Returns name, ISPB, full corporate name. Sourced "
                    "from BrasilAPI which mirrors the BCB STR participants registry.",
        handler=fetch_bank_by_code,
        input_schema={
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    ),
    ToolDef(
        name="fetch_ncm",
        description="Look up an NCM (Mercosul tariff) code → description. Used to "
                    "classify products on NF-e and check IPI/ICMS-ST incidence. "
                    "Accepts 2-8 digit codes (broader codes return the parent class).",
        handler=fetch_ncm,
        input_schema={
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    ),
    ToolDef(
        name="fetch_cnae_info",
        description="Look up a CNAE 7-digit subclasse on the IBGE registry. Returns the "
                    "description plus the classe/grupo/divisão/seção hierarchy. Used "
                    "alongside fetch_cnpj_from_receita to understand a counterparty's "
                    "economic activity.",
        handler=fetch_cnae_info,
        input_schema={
            "type": "object",
            "properties": {"code": {"type": "string", "description": "7-digit CNAE subclasse"}},
            "required": ["code"],
        },
    ),
    ToolDef(
        name="validate_cfop",
        description="Validate a 4-digit CFOP code and decode its operation type "
                    "(entrada/saída) and scope (in-state, interstate, foreign). "
                    "Common CFOPs return a description; unknown-but-formally-valid "
                    "codes return valid=true with description=null. Pure local lookup; "
                    "no network.",
        handler=validate_cfop,
        input_schema={
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    ),
    ToolDef(
        name="simples_nacional_annex_for_cnae",
        description="Heuristic mapping CNAE → Simples Nacional anexo (I/II/III/IV/V). "
                    "Use as a starting hint for enquadramento; final classification "
                    "depends on fator R, atividade-fim, and LC 123/2006 vedações. "
                    "Pure local function, no network.",
        handler=simples_nacional_annex_for_cnae,
        input_schema={
            "type": "object",
            "properties": {"cnae": {"type": "string"}},
            "required": ["cnae"],
        },
    ),
    ToolDef(
        name="financial_statements",
        description="Compute DRE/Balanço/DFC totals for a period. Basis = accrual (default) or cash.",
        handler=financial_statements,
        input_schema={
            "type": "object",
            "properties": {
                "company_id": {"type": "integer"},
                "date_from": {"type": "string", "format": "date"},
                "date_to": {"type": "string", "format": "date"},
                "basis": {"type": "string", "enum": ["accrual", "cash"], "default": "accrual"},
                "include_pending": {"type": "boolean", "default": False},
            },
            "required": ["company_id", "date_from", "date_to"],
        },
    ),
]


TOOLS_BY_NAME: dict[str, ToolDef] = {t.name: t for t in TOOLS}


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a tool call. Raises KeyError on unknown tool."""
    tool = TOOLS_BY_NAME[name]
    return tool.handler(**(arguments or {}))
