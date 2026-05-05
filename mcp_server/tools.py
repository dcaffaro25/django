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
# Tools: API meta — let the agent discover + call the full Sysnord REST API
# ---------------------------------------------------------------------------
# The ``api_meta`` app exposes /api/meta/* endpoints with model + endpoint
# + enum + filter introspection. We let the agent (a) discover the surface
# via discover_api, then (b) call it via call_internal_api. This avoids
# hand-crafting an MCP tool per DRF endpoint (the codebase has 1k+).
#
# Tenant + user context are injected by ``agent_runtime`` (similar to how
# ``company_id`` is force-overridden) so the agent can't escape the
# conversation's scope by passing a different tenant in the path.

# Cap the response body size to keep agent context manageable. Tunable
# via ``settings.AGENT_API_RESPONSE_BYTE_CAP``.
_API_RESPONSE_DEFAULT_CAP = 30_000


def discover_api(
    category: str,
    name: str | None = None,
    search: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Browse the Sysnord API surface via ``api_meta`` introspection.

    Categories:
      * ``capabilities`` — auth, pagination, multi-tenancy, error format.
        No further args needed.
      * ``models`` — list every model. Optional ``search`` filters by name.
      * ``model_detail`` — full schema (fields, FKs, indexes, constraints).
        Pass ``name='Invoice'`` (case-insensitive).
      * ``model_relationships`` — direct + transitive relations for a model.
        Pass ``name='BankTransaction'``.
      * ``endpoints`` — every DRF route. ``search`` filters by path or name.
      * ``enums`` — every choices field. ``search`` filters by name/values.
      * ``filters`` — every FilterSet's accepted query params.

    Use this to figure out *what* you can ask before calling
    ``call_internal_api``. Pure read; no network."""
    from api_meta.registry import (
        get_all_endpoints,
        get_all_enums,
        get_all_filters,
        get_all_models,
        get_capabilities,
        get_model_detail,
        get_model_relationships,
    )

    cat = (category or "").lower()
    s = (search or "").lower()

    if cat == "capabilities":
        return {"category": "capabilities", "data": get_capabilities()}

    if cat == "models":
        rows = [
            {"name": m["name"], "app": m["app"], "table": m["table"],
             "field_count": len(m.get("fields") or []),
             "description": (m.get("description") or "")[:160]}
            for m in get_all_models()
        ]
        if s:
            rows = [r for r in rows if s in r["name"].lower() or s in r["app"].lower()]
        return {"category": "models", "count": len(rows), "models": rows[:limit]}

    if cat == "model_detail":
        if not name:
            return {"error": "name is required for model_detail."}
        d = get_model_detail(name)
        if not d:
            return {"error": f"Model {name!r} not found."}
        return {"category": "model_detail", "data": d}

    if cat == "model_relationships":
        if not name:
            return {"error": "name is required for model_relationships."}
        d = get_model_relationships(name)
        if not d:
            return {"error": f"Model {name!r} not found."}
        return {"category": "model_relationships", "data": d}

    if cat == "endpoints":
        rows = get_all_endpoints()
        if s:
            rows = [
                r for r in rows
                if s in (r.get("path") or "").lower()
                or s in (r.get("name") or "").lower()
                or any(s in (t or "").lower() for t in (r.get("tags") or []))
            ]
        # Trim — agent doesn't need every detail per row in a list view.
        compact = [
            {
                "method": r.get("method"),
                "path": r.get("path"),
                "name": r.get("name"),
                "summary": r.get("summary"),
                "auth_required": r.get("auth_required"),
                "filterset": r.get("filterset"),
                "search_fields": r.get("search_fields"),
                "ordering_fields": r.get("ordering_fields"),
            }
            for r in rows
        ]
        return {"category": "endpoints", "count": len(compact), "endpoints": compact[:limit]}

    if cat == "enums":
        all_enums = get_all_enums()
        if s:
            all_enums = {
                k: v for k, v in all_enums.items()
                if s in k.lower()
                or any(s in str(val).lower() for val in (v.get("values") or []))
            }
        items = list(all_enums.items())[:limit]
        return {"category": "enums", "count": len(items), "enums": dict(items)}

    if cat == "filters":
        return {"category": "filters", "data": get_all_filters()}

    return {
        "error": (
            f"Unknown category {category!r}. Valid: capabilities | models | "
            f"model_detail | model_relationships | endpoints | enums | filters."
        )
    }


def call_internal_api(
    method: str,
    path: str,
    query: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    _tenant_slug: str = "",
    _acting_user_id: int | None = None,
) -> dict[str, Any]:
    """Dispatch an in-process call to any Sysnord REST endpoint as the
    conversation's user, scoped to the conversation's tenant.

    Currently **read-only** — only ``GET`` and ``HEAD`` accepted. Writes
    (POST/PUT/PATCH/DELETE) are gated; track the dedicated write-tool
    roadmap (Phase 1) to enable them with audit + confirmation.

    The ``_tenant_slug`` and ``_acting_user_id`` parameters are injected
    by the agent runtime — agent-supplied values are ignored, so the
    tenant boundary cannot be crossed via a crafted path.

    Path conventions:
      * ``/api/meta/...`` — global meta endpoints; called as-is.
      * ``/api/...`` — the agent runtime auto-prefixes the tenant slug.
      * ``/{slug}/api/...`` — the leading slug is replaced with the
        conversation's tenant (defence in depth).

    Returns ``{status_code, data, truncated, content_type}``. Response
    body is capped at ``settings.AGENT_API_RESPONSE_BYTE_CAP`` bytes
    (default 30_000) — if truncated, ask for narrower filters."""
    import re

    from django.conf import settings as django_settings
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient

    method_u = (method or "").upper().strip()
    if method_u not in ("GET", "HEAD"):
        return {
            "error": (
                f"Method {method_u} is not yet allowed. Only GET/HEAD are "
                "enabled — write tools land in a separate phase with audit + "
                "confirmation gates."
            )
        }
    if not path or not isinstance(path, str):
        return {"error": "path is required."}

    # Normalise path: enforce leading slash, strip query (we pass via params).
    p = path if path.startswith("/") else "/" + path
    p = p.split("?", 1)[0]

    # Tenant injection.
    if p.startswith("/api/meta/") or p == "/api/meta":
        # Global meta endpoints — no tenant prefix.
        final_path = p
    else:
        # Strip any leading /{slug}/ that the agent supplied.
        m = re.match(r"^/([\w-]+)/(api/.*)$", p)
        if m:
            inner = "/" + m.group(2)
        elif p.startswith("/api/"):
            inner = p
        else:
            return {
                "error": (
                    f"path must be either /api/meta/... or /{{tenant}}/api/... "
                    f"or /api/... (got {p!r})."
                )
            }
        if not _tenant_slug:
            return {"error": "Internal: tenant_slug not injected by runtime."}
        final_path = f"/{_tenant_slug}{inner}"

    User = get_user_model()
    user = None
    if _acting_user_id:
        try:
            user = User.objects.get(pk=_acting_user_id)
        except User.DoesNotExist:
            return {"error": f"acting user id={_acting_user_id} not found."}

    client = APIClient()
    if user is not None:
        client.force_authenticate(user=user)

    try:
        if method_u == "GET":
            resp = client.get(final_path, data=query or {}, format="json")
        else:  # HEAD
            resp = client.head(final_path, data=query or {})
    except Exception as exc:
        return {
            "error": f"In-process dispatch failed: {type(exc).__name__}: {exc}",
            "path": final_path,
        }

    cap = int(getattr(django_settings, "AGENT_API_RESPONSE_BYTE_CAP", _API_RESPONSE_DEFAULT_CAP))
    raw = resp.content or b""
    truncated = False
    if len(raw) > cap:
        raw = raw[:cap]
        truncated = True

    # Try to parse JSON; fall back to a string preview for HTML/plain.
    content_type = resp.get("Content-Type", "")
    parsed: Any
    if "application/json" in content_type:
        try:
            import json as _json
            parsed = _json.loads(raw.decode("utf-8", errors="replace"))
        except (ValueError, UnicodeDecodeError):
            parsed = raw.decode("utf-8", errors="replace")
    else:
        parsed = raw.decode("utf-8", errors="replace")

    return {
        "status_code": resp.status_code,
        "path": final_path,
        "content_type": content_type,
        "truncated": truncated,
        "byte_cap": cap,
        "data": parsed,
    }


# ---------------------------------------------------------------------------
# Tools: ERP API definitions (Omie etc.) — list, describe, invoke
# ---------------------------------------------------------------------------
# Each tenant has zero-or-more ``ERPConnection`` rows (credentials per
# provider) and the provider exposes a registry of ``ERPAPIDefinition``
# rows (one per call: ``ListarContasPagar``, ``ConsultarNF``, …) with
# ``url`` + ``method`` + ``param_schema`` (defaults derived from schema).
#
# Only read-style calls are exposed to the agent: name prefixes
# ``Listar``, ``Consultar``, ``Pesquisar``, ``Obter``, ``Get``. Writes
# (``Incluir``, ``Alterar``, ``Excluir``, ``Cancelar``) are blocked here
# and tracked with the broader write-tool roadmap.

_ERP_READ_PREFIXES = ("Listar", "Consultar", "Pesquisar", "Obter", "Get")


def list_erp_apis(
    company_id: int,
    provider: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    """List the ERP API calls the tenant has access to (i.e. there's an
    active ``ERPConnection`` for the provider AND the call is registered
    in ``ERPAPIDefinition``).

    Filters: ``provider`` slug (e.g. 'omie') and a substring ``search``
    over the call name."""
    from erp_integrations.models import ERPAPIDefinition, ERPConnection

    conns = ERPConnection.objects.filter(company_id=company_id, is_active=True)
    if provider:
        conns = conns.filter(provider__slug=provider)
    provider_ids = list(conns.values_list("provider_id", flat=True).distinct())
    if not provider_ids:
        return {
            "count": 0, "apis": [],
            "note": (
                f"No active ERPConnection for tenant company_id={company_id}"
                + (f" provider={provider!r}" if provider else "")
                + ". Configure one in the admin first."
            ),
        }

    qs = ERPAPIDefinition.objects.filter(
        provider_id__in=provider_ids, is_active=True,
    ).select_related("provider")
    if search:
        qs = qs.filter(call__icontains=search)

    rows = []
    for a in qs.order_by("provider__slug", "call"):
        rows.append({
            "id": a.id,
            "provider": a.provider.slug,
            "call": a.call,
            "method": a.method,
            "url": a.url,
            "description": a.description or "",
            "param_count": len(a.param_schema or []),
            "is_read_only": a.call.startswith(_ERP_READ_PREFIXES),
        })
    return {"count": len(rows), "apis": rows}


def describe_erp_api(
    company_id: int,
    call: str,
    provider: str | None = None,
) -> dict[str, Any]:
    """Return the full param_schema for one ERP API call so the agent
    knows which fields to pass when calling ``call_erp_api``.

    Each param spec carries name, type, description, required, and a
    default. Compose call_erp_api ``params={...}`` overriding only what
    you need; the rest fall back to defaults from the schema."""
    from erp_integrations.models import ERPAPIDefinition, ERPConnection

    conns = ERPConnection.objects.filter(company_id=company_id, is_active=True)
    if provider:
        conns = conns.filter(provider__slug=provider)
    provider_ids = list(conns.values_list("provider_id", flat=True).distinct())
    if not provider_ids:
        return {"error": f"No active ERPConnection for company_id={company_id}."}

    api = (
        ERPAPIDefinition.objects
        .filter(provider_id__in=provider_ids, call__iexact=call, is_active=True)
        .select_related("provider")
        .first()
    )
    if not api:
        return {
            "error": (
                f"ERP API call {call!r} not found for company_id={company_id}. "
                "Use list_erp_apis to see what's available."
            )
        }

    return {
        "provider": api.provider.slug,
        "call": api.call,
        "method": api.method,
        "url": api.url,
        "description": api.description or "",
        "is_read_only": api.call.startswith(_ERP_READ_PREFIXES),
        "param_schema": api.param_schema or [],
    }


# In-process cache for ``call_erp_api`` results. Keyed on (company_id,
# provider, call, canonical_args). Bounded by max entries + TTL. Not
# shared across processes (Celery workers, dev shells); good enough for
# de-duplicating within one pipeline run or one agent turn, which is
# where the throttle pain shows up.
_ERP_CACHE: dict[tuple, tuple[float, dict[str, Any]]] = {}
_ERP_CACHE_MAX_ENTRIES = 256


def _erp_cache_key(company_id: int, call: str, params: dict[str, Any] | None,
                   provider: str | None) -> tuple:
    import json as _json
    canon = _json.dumps(params or {}, sort_keys=True, default=str)
    return (company_id, provider or "", call, canon)


def call_erp_api(
    company_id: int,
    call: str,
    params: dict[str, Any] | None = None,
    provider: str | None = None,
    cache_ttl_seconds: int = 0,
) -> dict[str, Any]:
    """Invoke a registered ERP API call for the conversation's tenant,
    using its stored ``app_key``/``app_secret`` credentials.

    Read-only: name prefixes ``Listar``/``Consultar``/``Pesquisar``/
    ``Obter``/``Get``. Writes are rejected here and tracked separately.

    ``params`` overrides keys in the schema-derived default param
    object — e.g. ``{"pagina": 2, "registros_por_pagina": 50}``.

    ``cache_ttl_seconds``: when >0, the result is memoised in-process
    keyed on ``(company_id, provider, call, canonical_args)``. Same
    inputs within the TTL window return the cached response without
    re-hitting Omie. Useful for avoiding rate-limit cascades when the
    agent or pipeline naturally re-fetches the same lookup data
    (e.g. ``ListarClientes`` consulted by multiple downstream steps).
    Default 0 means caching is off — backwards-compatible.

    Returns ``{status_code, ok, response, truncated, byte_cap}`` —
    response is the unwrapped JSON (top-level key auto-stripped if Omie
    wraps the payload). Capped at ~30KB. If your call paginates, ask
    for the next page explicitly."""
    import json as _json

    import requests
    from django.conf import settings as django_settings

    from erp_integrations.models import ERPAPIDefinition, ERPConnection
    from erp_integrations.services.payload_builder import build_payload

    import time as _time

    if not call or not call.startswith(_ERP_READ_PREFIXES):
        return {
            "error": (
                f"ERP call {call!r} is not allowed via the agent. Only "
                "read-style calls (Listar / Consultar / Pesquisar / Obter / "
                "Get prefixes) are enabled. Writes need the dedicated write "
                "tools (separate phase)."
            )
        }

    # Cache lookup. Misses fall through to the live HTTP call.
    cache_key: tuple | None = None
    if cache_ttl_seconds and cache_ttl_seconds > 0:
        cache_key = _erp_cache_key(company_id, call, params, provider)
        cached = _ERP_CACHE.get(cache_key)
        if cached is not None:
            stored_at, payload = cached
            if (_time.time() - stored_at) < cache_ttl_seconds:
                # Annotate so callers can tell cache hits apart from fresh.
                return {**payload, "from_cache": True}

    conn_qs = ERPConnection.objects.filter(company_id=company_id, is_active=True)
    if provider:
        conn_qs = conn_qs.filter(provider__slug=provider)
    conn = conn_qs.select_related("provider").first()
    if not conn:
        return {"error": f"No active ERPConnection for company_id={company_id}."}

    api = (
        ERPAPIDefinition.objects
        .filter(provider=conn.provider, call__iexact=call, is_active=True)
        .first()
    )
    if not api:
        return {"error": f"ERP API call {call!r} not registered for {conn.provider.slug}."}

    payload = build_payload(connection=conn, api_definition=api, param_overrides=params or {})

    try:
        resp = requests.post(
            api.url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30.0,
        )
    except requests.RequestException as exc:
        return {"error": f"ERP call failed: {exc}"}

    cap = int(getattr(django_settings, "AGENT_API_RESPONSE_BYTE_CAP", _API_RESPONSE_DEFAULT_CAP))
    raw = resp.content or b""
    truncated = False
    if len(raw) > cap:
        raw = raw[:cap]
        truncated = True

    parsed: Any
    try:
        parsed = _json.loads(raw.decode("utf-8", errors="replace"))
    except (ValueError, UnicodeDecodeError):
        parsed = raw.decode("utf-8", errors="replace")

    # Surface Omie-style error envelopes as ``ok=False`` for clarity.
    # Different Omie modules return errors in slightly different shapes:
    # * SOAP-ish: {"faultcode", "faultstring"}
    # * Newer JSON: {"status": "error", "message": "..."}
    # * Method-missing: HTTP 500 + {"status": "error", "message": "Method X not exists"}
    is_error_envelope = isinstance(parsed, dict) and (
        "faultcode" in parsed
        or "faultstring" in parsed
        or (parsed.get("status") == "error" and "message" in parsed)
    )

    out = {
        "ok": resp.status_code < 400 and not is_error_envelope,
        "status_code": resp.status_code,
        "provider": conn.provider.slug,
        "call": api.call,
        "params_sent": params or {},
        "truncated": truncated,
        "byte_cap": cap,
        "response": parsed,
    }

    # Store in the cache only on success — caching errors would mask
    # transient issues that should retry.
    if cache_key is not None and out["ok"]:
        # Bound the cache size; oldest entries get evicted if we
        # exceed the limit.
        if len(_ERP_CACHE) >= _ERP_CACHE_MAX_ENTRIES:
            try:
                oldest_key = min(_ERP_CACHE, key=lambda k: _ERP_CACHE[k][0])
                _ERP_CACHE.pop(oldest_key, None)
            except ValueError:
                pass
        _ERP_CACHE[cache_key] = (_time.time(), out)

    return out


# ---------------------------------------------------------------------------
# Tool: run_reconciliation_agent (Phase 1 — first write tool; dry-run gated)
# ---------------------------------------------------------------------------
def run_reconciliation_agent(
    company_id: int,
    bank_account_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int | None = None,
    auto_accept_threshold: float | None = None,
    ambiguity_gap: float | None = None,
    min_confidence: float | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Execute one pass of the bank-reconciliation auto-accept agent.

    Wraps the existing :class:`accounting.services.reconciliation_agent_service.ReconciliationAgent`
    so the LLM can drive the same code path the recon cron uses. Each
    candidate bank transaction gets scored; matches above
    ``auto_accept_threshold`` are queued for acceptance — and *only*
    persisted if ``dry_run=False`` AND ``settings.AGENT_ALLOW_WRITES``
    is True. Otherwise the run is read-only: candidates are scored and
    proposals returned without any DB mutation.

    Every invocation, real or dry-run, also writes an
    :class:`agent.models.AgentWriteAudit` row so the operator has a
    paper trail of *what would have been done* before the kill-switch
    flips.

    Returns aggregate counters + the per-bank-tx decisions array. Use
    this to answer "reconcile what you can with confidence ≥ X."
    """
    import uuid as _uuid
    from datetime import date as _date

    from django.conf import settings as _django_settings

    # Parse date strings.
    try:
        df = _date.fromisoformat(date_from) if date_from else None
        dt = _date.fromisoformat(date_to) if date_to else None
    except (TypeError, ValueError) as exc:
        return {"error": f"Invalid date — use ISO YYYY-MM-DD. ({exc})"}

    # Effective dry_run: honour the kill-switch even if the LLM passed
    # dry_run=False. This protects against runaway automation while we
    # bed in the audit pipeline.
    requested_dry_run = bool(dry_run)
    writes_enabled = bool(getattr(_django_settings, "AGENT_ALLOW_WRITES", False))
    effective_dry_run = requested_dry_run or not writes_enabled
    blocked_by_policy = (not requested_dry_run) and (not writes_enabled)

    from accounting.services.reconciliation_agent_service import ReconciliationAgent

    args_summary_input = {
        "bank_account_id": bank_account_id,
        "date_from": date_from, "date_to": date_to, "limit": limit,
        "auto_accept_threshold": auto_accept_threshold,
        "ambiguity_gap": ambiguity_gap,
        "min_confidence": min_confidence,
        "dry_run_requested": requested_dry_run,
    }

    agent_service = ReconciliationAgent(
        company_id=company_id,
        auto_accept_threshold=auto_accept_threshold,
        ambiguity_gap=ambiguity_gap,
        min_confidence=min_confidence,
        dry_run=effective_dry_run,
        triggered_by="agent_chat",
    )
    try:
        result = agent_service.run(
            bank_account_id=bank_account_id,
            date_from=df, date_to=dt, limit=limit,
        )
    except Exception as exc:
        return {
            "error": f"Reconciliation run failed: {type(exc).__name__}: {exc}",
            "dry_run_effective": effective_dry_run,
        }

    # Persist the audit row.
    audit_row_id: int | None = None
    audit_status: str
    undo_token = ""
    if effective_dry_run:
        audit_status = "dry_run"
    else:
        audit_status = "applied"
        undo_token = _uuid.uuid4().hex

    # Pull the auto-accepted decision IDs from the DB — the in-memory
    # decision dicts don't include them (the recon service only writes
    # rows, doesn't echo the PKs back to the result struct).
    accepted_decision_ids: list[int] = []
    try:
        from accounting.models import ReconciliationAgentDecision
        accepted_decision_ids = list(
            ReconciliationAgentDecision.objects
            .filter(run_id=result.run_id, outcome="auto_accepted")
            .values_list("id", flat=True)
        )
    except Exception as exc:
        log.warning("agent.recon.fetch_decision_ids_failed: %s", exc)

    try:
        from agent.models import AgentWriteAudit
        from multitenancy.models import Company
        company = Company.objects.get(id=company_id)
        audit = AgentWriteAudit.objects.create(
            company=company,
            tool_name="run_reconciliation_agent",
            target_model="accounting.ReconciliationAgentDecision",
            target_ids=accepted_decision_ids,
            args_summary=str(args_summary_input)[:380],
            before_state={
                "n_candidates": result.n_candidates,
                "writes_enabled": writes_enabled,
                "blocked_by_policy": blocked_by_policy,
            },
            after_state={
                "n_auto_accepted": result.n_auto_accepted,
                "n_ambiguous": result.n_ambiguous,
                "n_no_match": result.n_no_match,
                "n_not_applicable": result.n_not_applicable,
            },
            status=audit_status,
            undo_token=undo_token,
        )
        audit_row_id = audit.id
    except Exception as exc:  # pragma: no cover — audit must not break tools
        log.warning("agent.write_audit.failed: %s", exc)

    return {
        "ok": True,
        "dry_run_effective": effective_dry_run,
        "blocked_by_policy": blocked_by_policy,
        "policy_note": (
            "Live writes are disabled (AGENT_ALLOW_WRITES=false). The run "
            "scored candidates and proposed acceptances, but did not modify "
            "the database. To enable, set AGENT_ALLOW_WRITES=true on the "
            "deployment."
        ) if blocked_by_policy else None,
        "run_id": result.run_id,
        "audit_id": audit_row_id,
        "undo_token": undo_token or None,
        "counters": {
            "n_candidates": result.n_candidates,
            "n_auto_accepted": result.n_auto_accepted,
            "n_ambiguous": result.n_ambiguous,
            "n_no_match": result.n_no_match,
            "n_not_applicable": result.n_not_applicable,
            "n_errors": result.n_errors,
        },
        "decisions_preview": [
            {
                "bank_tx_id": d.get("bank_transaction_id"),
                "outcome": d.get("outcome"),
                "top_confidence": d.get("top_confidence"),
                "second_confidence": d.get("second_confidence"),
                "reason": d.get("reason") or d.get("error"),
            }
            for d in (result.decisions or [])[:20]
        ],
    }


# ---------------------------------------------------------------------------
# Tool: propose_mapping_from_document — Phase 2 wave 2
# ---------------------------------------------------------------------------
def propose_mapping_from_document(
    company_id: int,
    attachment_id: int,
) -> dict[str, Any]:
    """Look at an ingested document (NF-e XML) and propose how it
    should land in Sysnord — a draft Invoice that the user can review
    and confirm.

    Logic:
      1. Pull ``extracted_text`` summary from ``ingest_document``
         (re-runs ingest if not cached yet).
      2. Resolve the counterparty: BusinessPartner by exact CNPJ first,
         then by CNPJ root (matriz/filial), then by name fuzzy match.
      3. Suggest the posting account: BP's
         ``receivable_account``/``payable_account`` if set, otherwise
         most-frequently-used account from past Invoices for that BP.
      4. Surface the totals + itens for the LLM to summarise.

    Read-only — does not create the Invoice. Pair with
    ``apply_document_mapping`` for the actual write."""
    from billing.models import BusinessPartner, Invoice

    from agent.models import AgentMessageAttachment

    try:
        att = AgentMessageAttachment.objects.get(
            id=attachment_id, company_id=company_id,
        )
    except AgentMessageAttachment.DoesNotExist:
        return {"error": f"Attachment {attachment_id} not found in company {company_id}."}

    if att.kind not in (AgentMessageAttachment.KIND_NFE_XML,):
        return {
            "error": (
                f"Only NF-e XML attachments are supported by this tool today. "
                f"Got kind={att.kind!r}."
            )
        }

    # Trigger ingest if not yet run (idempotent, reuses cache).
    ingest_result = ingest_document(
        company_id=company_id, attachment_id=attachment_id,
    )
    if "error" in ingest_result:
        return ingest_result

    # Re-parse to get the structured summary (we need fields the cached
    # plain-text representation doesn't expose).
    try:
        _, nfe_summary = _ingest_nfe_xml(att)
    except Exception as exc:
        return {"error": f"Could not parse NF-e for mapping: {exc}"}

    # Determine direction from the perspective of this tenant.
    # Find which side (emit or dest) is the tenant by matching the
    # tenant's company CNPJ (if available) — fall back to "unknown".
    import re

    tenant_cnpjs: set[str] = set()
    try:
        from multitenancy.models import Company
        tenant = Company.objects.get(id=company_id)
        for fld in ("cnpj", "identifier", "tax_id"):
            v = getattr(tenant, fld, "") or ""
            if v:
                tenant_cnpjs.add(re.sub(r"\D", "", v))
    except Exception:
        pass

    emit = re.sub(r"\D", "", nfe_summary.get("emit_cnpj") or "")
    dest = re.sub(r"\D", "", nfe_summary.get("dest_cnpj") or "")
    if tenant_cnpjs and emit in tenant_cnpjs:
        direction = "sale"
        counterparty_cnpj = dest
        counterparty_name = nfe_summary.get("dest_nome") or ""
    elif tenant_cnpjs and dest in tenant_cnpjs:
        direction = "purchase"
        counterparty_cnpj = emit
        counterparty_name = nfe_summary.get("emit_nome") or ""
    else:
        # No tenant-cnpj match — fall back to assuming the dest is the
        # counterparty (typical sale).
        direction = "unknown"
        counterparty_cnpj = dest or emit
        counterparty_name = nfe_summary.get("dest_nome") or nfe_summary.get("emit_nome") or ""

    # Resolve the BusinessPartner.
    bp_match: dict[str, Any] | None = None
    bp = None
    if counterparty_cnpj and len(counterparty_cnpj) == 14:
        # 1) exact CNPJ
        bp = BusinessPartner.objects.filter(
            company_id=company_id, identifier=counterparty_cnpj, is_active=True,
        ).first()
        if bp:
            bp_match = {"strategy": "exact_cnpj", "match_strength": 1.0}
        else:
            # 2) CNPJ root (matriz/filial)
            bp = BusinessPartner.objects.filter(
                company_id=company_id, cnpj_root=counterparty_cnpj[:8], is_active=True,
            ).first()
            if bp:
                bp_match = {"strategy": "cnpj_root", "match_strength": 0.85}
    if bp is None and counterparty_name:
        # 3) fuzzy name (icontains)
        bp = BusinessPartner.objects.filter(
            company_id=company_id, name__icontains=counterparty_name[:40], is_active=True,
        ).first()
        if bp:
            bp_match = {"strategy": "name_icontains", "match_strength": 0.5}

    # Suggest the account.
    suggested_account = None
    suggested_account_source = None
    if bp:
        if direction == "sale" and bp.receivable_account_id:
            suggested_account = {
                "id": bp.receivable_account_id,
                "name": bp.receivable_account.name if bp.receivable_account else None,
            }
            suggested_account_source = "bp.receivable_account"
        elif direction == "purchase" and bp.payable_account_id:
            suggested_account = {
                "id": bp.payable_account_id,
                "name": bp.payable_account.name if bp.payable_account else None,
            }
            suggested_account_source = "bp.payable_account"
        else:
            # Look at past Invoices for this BP — most-used line account.
            from collections import Counter
            past_inv_qs = Invoice.objects.filter(
                company_id=company_id, partner=bp,
            ).prefetch_related("lines")[:25]
            account_counter: Counter = Counter()
            for inv in past_inv_qs:
                for line in inv.lines.all():
                    if getattr(line, "account_id", None):
                        account_counter[line.account_id] += 1
            if account_counter:
                top_acc_id, hits = account_counter.most_common(1)[0]
                from accounting.models import Account
                acc = Account.objects.filter(id=top_acc_id).first()
                if acc:
                    suggested_account = {"id": acc.id, "name": acc.name}
                    suggested_account_source = f"history_top:{hits}_invoices"

    return {
        "ok": True,
        "attachment_id": att.id,
        "direction": direction,
        "counterparty": {
            "cnpj": counterparty_cnpj,
            "name": counterparty_name,
            "matched_partner_id": bp.id if bp else None,
            "matched_partner_name": bp.name if bp else None,
            "match": bp_match,
        },
        "suggested_account": suggested_account,
        "suggested_account_source": suggested_account_source,
        "nfe_summary": {
            "chave": nfe_summary.get("chave"),
            "numero": nfe_summary.get("numero"),
            "serie": nfe_summary.get("serie"),
            "data_emissao": nfe_summary.get("data_emissao"),
            "valor_total": nfe_summary.get("valor_total"),
            "item_count": nfe_summary.get("item_count"),
            "natureza_operacao": nfe_summary.get("natureza_operacao"),
        },
        "note": (
            "This is a proposal — review the suggested partner + account "
            "before calling apply_document_mapping. apply is also gated by "
            "settings.AGENT_ALLOW_WRITES."
        ),
    }


# ---------------------------------------------------------------------------
# Tool: apply_document_mapping — Phase 2 wave 2 (write)
# ---------------------------------------------------------------------------
def apply_document_mapping(
    company_id: int,
    attachment_id: int,
    partner_id: int,
    invoice_type: str,
    invoice_date: str | None = None,
    due_date: str | None = None,
    product_service_id: int | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Create an :class:`Invoice` from an ingested NF-e attachment.

    Reads the cached NFe summary, resolves currency from the partner,
    creates an Invoice header with totals from the NFe, and (if
    ``product_service_id`` is provided) creates one
    :class:`InvoiceLine` per NFe item using that single ProductService
    as a catch-all. Without a product_service_id, the Invoice is
    header-only — the user can fill lines manually later.

    Wrapped in the standard write-tool pattern: ``dry_run=True`` by
    default (returns the proposed payload), real writes only when
    ``settings.AGENT_ALLOW_WRITES`` is on AND the caller passes
    ``dry_run=False``. Every attempt — dry-run or applied — captures
    an :class:`agent.models.AgentWriteAudit` row with an
    ``undo_token`` that ``undo_via_audit`` can use to reverse the
    Invoice + lines.
    """
    import uuid as _uuid
    from datetime import date as _date

    from django.conf import settings as _django_settings
    from django.db import transaction as _txn

    from agent.models import AgentMessageAttachment, AgentWriteAudit
    from billing.models import BusinessPartner, Invoice, InvoiceLine, ProductService
    from multitenancy.models import Company

    # 1. Validate inputs / resolve dependencies.
    if invoice_type not in ("sale", "purchase"):
        return {"error": "invoice_type must be 'sale' or 'purchase'."}

    try:
        att = AgentMessageAttachment.objects.get(
            id=attachment_id, company_id=company_id,
        )
    except AgentMessageAttachment.DoesNotExist:
        return {"error": f"Attachment {attachment_id} not found in company {company_id}."}

    if att.kind != AgentMessageAttachment.KIND_NFE_XML:
        return {
            "error": (
                f"apply_document_mapping currently supports NF-e XML only. "
                f"Got kind={att.kind!r}."
            )
        }

    try:
        partner = BusinessPartner.objects.get(id=partner_id, company_id=company_id)
    except BusinessPartner.DoesNotExist:
        return {"error": f"BusinessPartner {partner_id} not found in company {company_id}."}

    product_service = None
    if product_service_id is not None:
        try:
            product_service = ProductService.objects.get(
                id=product_service_id, company_id=company_id,
            )
        except ProductService.DoesNotExist:
            return {
                "error": (
                    f"ProductService {product_service_id} not found. Pass a valid "
                    "product_service_id to create lines, or omit it for a "
                    "header-only Invoice."
                )
            }

    # 2. Re-parse the NFe summary (cheap; the cached extracted_text is a
    # human-readable string, but we need the structured fields here).
    try:
        _, nfe_summary = _ingest_nfe_xml(att)
    except Exception as exc:
        return {"error": f"Could not parse NF-e for apply: {exc}"}

    # 3. Defaults.
    parsed_invoice_date: _date | None = None
    if invoice_date:
        try:
            parsed_invoice_date = _date.fromisoformat(invoice_date)
        except ValueError as exc:
            return {"error": f"Invalid invoice_date: {exc}"}
    elif nfe_summary.get("data_emissao"):
        try:
            parsed_invoice_date = _date.fromisoformat(
                nfe_summary["data_emissao"][:10]
            )
        except ValueError:
            parsed_invoice_date = None

    parsed_due_date: _date | None = None
    if due_date:
        try:
            parsed_due_date = _date.fromisoformat(due_date)
        except ValueError as exc:
            return {"error": f"Invalid due_date: {exc}"}
    else:
        parsed_due_date = parsed_invoice_date

    if not parsed_invoice_date:
        return {"error": "invoice_date is required (NFe data_emissao not parseable)."}

    # 4. Build the proposed payload (used for both dry-run preview and
    # the actual create).
    items = nfe_summary.get("itens_preview") or []
    invoice_payload = {
        "company_id": company_id,
        "partner_id": partner.id,
        "invoice_type": invoice_type,
        "invoice_number": str(nfe_summary.get("numero") or ""),
        "invoice_date": parsed_invoice_date.isoformat(),
        "due_date": parsed_due_date.isoformat() if parsed_due_date else None,
        "currency_id": getattr(partner, "currency_id", None),
        "total_amount": str(nfe_summary.get("valor_total") or "0"),
        "tax_amount": str(nfe_summary.get("valor_icms") or "0"),
        "discount_amount": "0",
        "description": (
            f"NF-e {nfe_summary.get('numero', '?')}/{nfe_summary.get('serie', '?')} — "
            f"chave {nfe_summary.get('chave', '?')[-8:] or '?'}"
        ),
    }
    line_payloads = []
    if product_service is not None:
        for it in items:
            try:
                qty = Decimal("1")
                unit = Decimal(str(it.get("valor") or "0"))
            except Exception:
                qty = Decimal("1")
                unit = Decimal("0")
            line_payloads.append({
                "product_service_id": product_service.id,
                "description": (it.get("descricao") or "")[:255],
                "quantity": str(qty),
                "unit_price": str(unit),
                "total_price": str(qty * unit),
            })

    # 5. Effective dry_run honours the kill-switch.
    requested_dry_run = bool(dry_run)
    writes_enabled = bool(getattr(_django_settings, "AGENT_ALLOW_WRITES", False))
    effective_dry_run = requested_dry_run or not writes_enabled
    blocked_by_policy = (not requested_dry_run) and (not writes_enabled)

    args_summary = {
        "attachment_id": attachment_id, "partner_id": partner_id,
        "invoice_type": invoice_type, "invoice_date": str(parsed_invoice_date),
        "product_service_id": product_service_id,
        "dry_run_requested": requested_dry_run,
    }

    invoice_id: int | None = None
    line_ids: list[int] = []
    error_msg = ""

    if not effective_dry_run:
        try:
            with _txn.atomic():
                inv = Invoice.objects.create(
                    company=Company.objects.get(id=company_id),
                    partner=partner,
                    invoice_type=invoice_type,
                    invoice_number=invoice_payload["invoice_number"],
                    invoice_date=parsed_invoice_date,
                    due_date=parsed_due_date or parsed_invoice_date,
                    currency_id=invoice_payload["currency_id"],
                    total_amount=invoice_payload["total_amount"],
                    tax_amount=invoice_payload["tax_amount"],
                    discount_amount=invoice_payload["discount_amount"],
                    description=invoice_payload["description"],
                    status="draft",
                )
                invoice_id = inv.id
                for lp in line_payloads:
                    line = InvoiceLine.objects.create(
                        company_id=company_id,
                        invoice=inv,
                        product_service_id=lp["product_service_id"],
                        description=lp["description"],
                        quantity=Decimal(lp["quantity"]),
                        unit_price=Decimal(lp["unit_price"]),
                    )
                    line_ids.append(line.id)
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"

    # 6. Persist the audit row regardless of dry-run / success / failure.
    audit_status = (
        AgentWriteAudit.STATUS_FAILED if error_msg
        else (AgentWriteAudit.STATUS_DRY_RUN if effective_dry_run
              else AgentWriteAudit.STATUS_APPLIED)
    )
    undo_token = "" if (effective_dry_run or error_msg) else _uuid.uuid4().hex
    audit_row_id: int | None = None
    try:
        audit = AgentWriteAudit.objects.create(
            company=Company.objects.get(id=company_id),
            tool_name="apply_document_mapping",
            target_model="billing.Invoice",
            target_ids=[invoice_id] if invoice_id else [],
            args_summary=str(args_summary)[:380],
            before_state={
                "writes_enabled": writes_enabled,
                "blocked_by_policy": blocked_by_policy,
            },
            after_state={
                "invoice_payload": invoice_payload,
                "line_payloads": line_payloads,
                "invoice_id": invoice_id,
                "line_ids": line_ids,
            },
            status=audit_status,
            error_type=error_msg.split(":")[0] if error_msg else "",
            error_message=error_msg[:480] if error_msg else "",
            undo_token=undo_token,
        )
        audit_row_id = audit.id
    except Exception as exc:  # pragma: no cover — audit must not break tools
        log.warning("agent.write_audit.failed: %s", exc)

    if error_msg:
        return {
            "ok": False,
            "error": error_msg,
            "audit_id": audit_row_id,
        }

    return {
        "ok": True,
        "dry_run_effective": effective_dry_run,
        "blocked_by_policy": blocked_by_policy,
        "policy_note": (
            "Live writes are disabled (AGENT_ALLOW_WRITES=false). The Invoice "
            "and lines were NOT created — the proposal is in the audit row "
            "for review."
        ) if blocked_by_policy else None,
        "audit_id": audit_row_id,
        "undo_token": undo_token or None,
        "invoice_id": invoice_id,
        "line_ids": line_ids,
        "preview": {
            "invoice": invoice_payload,
            "lines": line_payloads,
            "header_only": product_service is None,
        },
    }


def _undo_apply_document_mapping(audit, *, dry_run: bool) -> dict[str, Any]:
    """Reverse an ``apply_document_mapping`` audit row by soft-deleting
    the created Invoice (lines cascade via FK)."""
    from billing.models import Invoice, InvoiceLine

    invoice_ids = audit.target_ids or []
    after = audit.after_state or {}
    line_ids = after.get("line_ids") or []

    if dry_run:
        return {
            "would_soft_delete_invoice_ids": invoice_ids,
            "would_soft_delete_line_ids": line_ids,
        }

    InvoiceLine.objects.filter(
        id__in=line_ids, company=audit.company,
    ).update(is_deleted=True)
    Invoice.objects.filter(
        id__in=invoice_ids, company=audit.company,
    ).update(is_deleted=True)
    return {
        "soft_deleted_invoice_ids": invoice_ids,
        "soft_deleted_line_ids": line_ids,
    }


# ---------------------------------------------------------------------------
# Tools: agent playbooks — saved, reusable agent configurations
# ---------------------------------------------------------------------------
def list_agent_playbooks(
    company_id: int,
    kind: str | None = None,
    only_active: bool = True,
) -> dict[str, Any]:
    """List saved playbooks for the tenant — configurations the agent
    can replay by name. Filter by ``kind`` (currently only ``recon``)
    and ``only_active`` to hide soft-deactivated rows.

    Returns name, description, last-run summary, and the params blob
    so the agent can reason about whether to run-as-is or tweak first."""
    from agent.models import AgentPlaybook

    qs = AgentPlaybook.objects.filter(company_id=company_id)
    if only_active:
        qs = qs.filter(is_active=True)
    if kind:
        qs = qs.filter(kind=kind)

    rows = []
    for p in qs.order_by("kind", "name"):
        rows.append({
            "id": p.id,
            "name": p.name,
            "kind": p.kind,
            "description": p.description,
            "params": p.params or {},
            "is_active": p.is_active,
            "schedule_cron": p.schedule_cron,
            "last_run_at": p.last_run_at.isoformat() if p.last_run_at else None,
            "last_run_summary": p.last_run_summary or {},
        })
    return {"count": len(rows), "playbooks": rows}


def save_agent_playbook(
    company_id: int,
    name: str,
    kind: str = "recon",
    description: str = "",
    params: dict[str, Any] | None = None,
    schedule_cron: str = "",
    is_active: bool = True,
) -> dict[str, Any]:
    """Create or update a playbook by ``(company, name)`` — upsert.

    For ``kind='recon'``, ``params`` accepts:
      auto_accept_threshold, ambiguity_gap, min_confidence,
      bank_account_id, date_from (ISO), date_to (ISO), limit.

    No live action runs here; this only persists the config. Use
    ``run_agent_playbook`` to execute, or eventually let the
    scheduled-tasks layer do it cron-driven.
    """
    from agent.models import AgentPlaybook
    from multitenancy.models import Company

    if not name or not isinstance(name, str):
        return {"error": "name is required."}
    if kind not in ("recon",):
        return {"error": f"Unsupported kind {kind!r}. Supported: 'recon'."}

    try:
        company = Company.objects.get(id=company_id)
    except Company.DoesNotExist:
        return {"error": f"Company {company_id} not found."}

    obj, created = AgentPlaybook.objects.update_or_create(
        company=company, name=name,
        defaults={
            "kind": kind,
            "description": description[:255],
            "params": params or {},
            "schedule_cron": schedule_cron[:64],
            "is_active": is_active,
        },
    )
    return {
        "ok": True,
        "id": obj.id,
        "created": created,
        "name": obj.name,
        "kind": obj.kind,
    }


def run_agent_playbook(
    company_id: int,
    name_or_id: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Execute a saved playbook. Resolves params from the row and
    dispatches to the right action handler:

    * ``kind='recon'`` → calls :func:`run_reconciliation_agent` with
      the saved knobs.

    Honours the same ``AGENT_ALLOW_WRITES`` kill-switch as the
    underlying tool. Updates the playbook's ``last_run_at`` /
    ``last_run_summary`` cache after each invocation.
    """
    from django.utils import timezone as _tz

    from agent.models import AgentPlaybook

    qs = AgentPlaybook.objects.filter(company_id=company_id, is_active=True)
    obj: AgentPlaybook | None = None
    if isinstance(name_or_id, int) or (isinstance(name_or_id, str) and name_or_id.isdigit()):
        obj = qs.filter(id=int(name_or_id)).first()
    else:
        obj = qs.filter(name=name_or_id).first()
    if obj is None:
        return {"error": f"No active playbook with name_or_id={name_or_id!r}."}

    if obj.kind == "recon":
        params = dict(obj.params or {})
        # Only pass keys that run_reconciliation_agent accepts; ignore
        # extras to be forgiving with old playbooks.
        accepted = {
            "bank_account_id", "date_from", "date_to", "limit",
            "auto_accept_threshold", "ambiguity_gap", "min_confidence",
        }
        clean = {k: v for k, v in params.items() if k in accepted}
        result = run_reconciliation_agent(
            company_id=company_id, dry_run=dry_run, **clean,
        )
        # Cache a small summary on the playbook so list_agent_playbooks
        # can show it without re-running.
        try:
            obj.last_run_at = _tz.now()
            obj.last_run_summary = {
                "dry_run_effective": result.get("dry_run_effective"),
                "ok": result.get("ok"),
                "counters": result.get("counters") or {},
                "audit_id": result.get("audit_id"),
            }
            obj.save(update_fields=["last_run_at", "last_run_summary", "updated_at"])
        except Exception as exc:  # pragma: no cover
            log.warning("agent.playbook.last_run_save_failed: %s", exc)
        return {
            "ok": True,
            "playbook_id": obj.id,
            "playbook_name": obj.name,
            "result": result,
        }

    return {"error": f"Unknown playbook kind {obj.kind!r}."}


# ---------------------------------------------------------------------------
# Tools: accept / reject ambiguous recon decisions — Phase 1 wave 2
# ---------------------------------------------------------------------------
def accept_recon_decision(
    company_id: int,
    decision_id: int,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Promote an ambiguous :class:`ReconciliationAgentDecision` into a
    real :class:`Reconciliation` by accepting its top suggestion.

    Reuses :meth:`ReconciliationAgent._auto_accept` so the produced
    Reconciliation row is byte-identical to one created by the agent's
    own auto-accept tier — same JE flips, same ``balance_validated``,
    same cache invalidation. The decision row's ``reconciliation`` FK
    is updated to point at the new row.

    ``dry_run=True`` (default) returns the projected payload without
    writing. Live writes additionally require
    ``settings.AGENT_ALLOW_WRITES`` to be on. Every attempt — dry-run
    or applied — writes an :class:`agent.models.AgentWriteAudit` row
    with an ``undo_token`` (live) for ``undo_via_audit`` to reverse.
    """
    import uuid as _uuid

    from django.conf import settings as _django_settings

    from accounting.models import ReconciliationAgentDecision
    from accounting.services.reconciliation_agent_service import (
        ReconciliationAgent,
    )

    from agent.models import AgentWriteAudit
    from multitenancy.models import Company

    try:
        decision = ReconciliationAgentDecision.objects.select_related(
            "bank_transaction", "run",
        ).get(id=decision_id, company_id=company_id)
    except ReconciliationAgentDecision.DoesNotExist:
        return {
            "error": (
                f"ReconciliationAgentDecision {decision_id} not found in "
                f"company {company_id}."
            )
        }

    if decision.outcome != "ambiguous":
        return {
            "error": (
                f"Decision {decision_id} has outcome={decision.outcome!r}; "
                f"only ambiguous decisions can be manually accepted."
            )
        }
    if decision.reconciliation_id:
        return {
            "ok": True,
            "already_accepted": True,
            "decision_id": decision_id,
            "reconciliation_id": decision.reconciliation_id,
        }

    suggestion = dict(decision.suggestion_payload or {})
    je_data = suggestion.get("existing_journal_entry") or {}
    if not je_data.get("id"):
        return {
            "error": (
                "Decision's suggestion_payload has no existing_journal_entry. "
                "This usually means the suggestion proposed a new JE rather "
                "than matching an existing one — out of scope for the "
                "manual-accept path."
            )
        }

    requested_dry_run = bool(dry_run)
    writes_enabled = bool(getattr(_django_settings, "AGENT_ALLOW_WRITES", False))
    effective_dry_run = requested_dry_run or not writes_enabled
    blocked_by_policy = (not requested_dry_run) and (not writes_enabled)

    args_summary = {
        "decision_id": decision_id,
        "bank_tx_id": decision.bank_transaction_id,
        "je_id": je_data.get("id"),
        "confidence": str(decision.top_confidence) if decision.top_confidence is not None else None,
        "dry_run_requested": requested_dry_run,
    }

    reconciliation_id: int | None = None
    error_msg = ""

    if not effective_dry_run:
        try:
            agent = ReconciliationAgent(company_id=company_id, dry_run=False)
            reconciliation_id = agent._auto_accept(
                bank_tx=decision.bank_transaction,
                suggestion=suggestion,
            )
            decision.reconciliation_id = reconciliation_id
            decision.save(update_fields=["reconciliation_id", "updated_at"])
            agent._bump_cache_version()
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"

    audit_status = (
        AgentWriteAudit.STATUS_FAILED if error_msg
        else (AgentWriteAudit.STATUS_DRY_RUN if effective_dry_run
              else AgentWriteAudit.STATUS_APPLIED)
    )
    undo_token = "" if (effective_dry_run or error_msg) else _uuid.uuid4().hex

    audit_row_id: int | None = None
    try:
        audit = AgentWriteAudit.objects.create(
            company=Company.objects.get(id=company_id),
            tool_name="accept_recon_decision",
            target_model="accounting.Reconciliation",
            target_ids=[reconciliation_id] if reconciliation_id else [],
            args_summary=str(args_summary)[:380],
            before_state={
                "decision_id": decision_id,
                "decision_outcome": decision.outcome,
                "writes_enabled": writes_enabled,
                "blocked_by_policy": blocked_by_policy,
            },
            after_state={
                "reconciliation_id": reconciliation_id,
                "decision_id": decision_id,
                "je_id": je_data.get("id"),
                "bank_tx_id": decision.bank_transaction_id,
            },
            status=audit_status,
            error_type=error_msg.split(":")[0] if error_msg else "",
            error_message=error_msg[:480] if error_msg else "",
            undo_token=undo_token,
        )
        audit_row_id = audit.id
    except Exception as exc:  # pragma: no cover
        log.warning("agent.write_audit.failed: %s", exc)

    if error_msg:
        return {"ok": False, "error": error_msg, "audit_id": audit_row_id}

    return {
        "ok": True,
        "dry_run_effective": effective_dry_run,
        "blocked_by_policy": blocked_by_policy,
        "policy_note": (
            "Live writes are disabled. The Reconciliation was NOT created — "
            "the proposal is in the audit row for review."
        ) if blocked_by_policy else None,
        "decision_id": decision_id,
        "reconciliation_id": reconciliation_id,
        "audit_id": audit_row_id,
        "undo_token": undo_token or None,
        "preview": {
            "bank_tx_id": decision.bank_transaction_id,
            "bank_tx_amount": str(getattr(decision.bank_transaction, "amount", "")),
            "je_id": je_data.get("id"),
            "confidence": str(decision.top_confidence) if decision.top_confidence is not None else None,
        },
    }


def reject_recon_decision(
    company_id: int,
    decision_id: int,
    reason: str = "",
) -> dict[str, Any]:
    """Capture a human rejection of an ambiguous decision.

    Doesn't mutate the decision row — the agent might have been right
    to flag it. Just records the human's "no" via
    :class:`agent.models.AgentWriteAudit` (status=rejected) so future
    runs can avoid re-suggesting the same match and the operator has
    a paper trail of what was discarded.
    """
    from accounting.models import ReconciliationAgentDecision

    from agent.models import AgentWriteAudit
    from multitenancy.models import Company

    try:
        decision = ReconciliationAgentDecision.objects.get(
            id=decision_id, company_id=company_id,
        )
    except ReconciliationAgentDecision.DoesNotExist:
        return {
            "error": (
                f"ReconciliationAgentDecision {decision_id} not found in "
                f"company {company_id}."
            )
        }

    if decision.outcome != "ambiguous":
        return {
            "error": (
                f"Decision {decision_id} has outcome={decision.outcome!r}; "
                f"only ambiguous decisions are subject to manual rejection."
            )
        }

    audit_row_id: int | None = None
    try:
        audit = AgentWriteAudit.objects.create(
            company=Company.objects.get(id=company_id),
            tool_name="reject_recon_decision",
            target_model="accounting.ReconciliationAgentDecision",
            target_ids=[decision_id],
            args_summary=str({"decision_id": decision_id, "reason": reason})[:380],
            before_state={
                "decision_id": decision_id,
                "decision_outcome": decision.outcome,
            },
            after_state={"rejected": True, "reason": (reason or "")[:200]},
            status=AgentWriteAudit.STATUS_REJECTED,
        )
        audit_row_id = audit.id
    except Exception as exc:  # pragma: no cover
        log.warning("agent.write_audit.failed: %s", exc)

    return {
        "ok": True,
        "decision_id": decision_id,
        "audit_id": audit_row_id,
        "reason": reason or None,
    }


def _undo_accept_recon_decision(audit, *, dry_run: bool) -> dict[str, Any]:
    """Reverse a manual ``accept_recon_decision`` by soft-deleting the
    Reconciliation it created and clearing the decision's
    ``reconciliation`` FK so it returns to ``ambiguous`` for re-review.
    """
    from accounting.models import (
        Reconciliation, ReconciliationAgentDecision,
    )

    after = audit.after_state or {}
    recon_ids = audit.target_ids or []
    decision_id = after.get("decision_id")

    if dry_run:
        return {
            "would_soft_delete_reconciliation_ids": recon_ids,
            "would_clear_decision_id": decision_id,
        }

    if recon_ids:
        Reconciliation.objects.filter(
            id__in=recon_ids, company=audit.company,
        ).update(is_deleted=True)
    if decision_id:
        ReconciliationAgentDecision.objects.filter(
            id=decision_id, company=audit.company,
        ).update(reconciliation=None)
    return {
        "soft_deleted_reconciliation_ids": recon_ids,
        "cleared_decision_id": decision_id,
    }


# ---------------------------------------------------------------------------
# Tool: list_recon_decisions — Phase 1 expansion (read)
# ---------------------------------------------------------------------------
def list_recon_decisions(
    company_id: int,
    run_id: int | None = None,
    outcome: str | None = None,
    bank_account_id: int | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    """List per-bank-tx decisions from past reconciliation-agent runs.

    Use this to inspect what the agent decided after a
    ``run_reconciliation_agent`` call: ``auto_accepted`` matches that
    landed, ``ambiguous`` ones still awaiting human review,
    ``no_match`` / ``not_applicable`` / ``error`` for observability.

    Filters: ``run_id`` (one specific run), ``outcome`` (one of
    auto_accepted/ambiguous/no_match/not_applicable/error),
    ``bank_account_id``."""
    from accounting.models import ReconciliationAgentDecision

    qs = ReconciliationAgentDecision.objects.filter(
        company_id=company_id
    ).select_related("bank_transaction", "run")

    if run_id is not None:
        qs = qs.filter(run_id=run_id)
    if outcome:
        qs = qs.filter(outcome=outcome)
    if bank_account_id is not None:
        qs = qs.filter(bank_transaction__bank_account_id=bank_account_id)

    rows = []
    for d in qs.order_by("-created_at", "-id")[:limit]:
        suggestion = d.suggestion_payload or {}
        # Top suggestion summary so the agent can describe the choice
        # without having to look up the bank tx separately.
        rows.append({
            "decision_id": d.id,
            "run_id": d.run_id,
            "bank_transaction_id": d.bank_transaction_id,
            "bank_tx": {
                "date": str(getattr(d.bank_transaction, "date", "")),
                "amount": str(getattr(d.bank_transaction, "amount", "")),
                "description": (getattr(d.bank_transaction, "description", "") or "")[:120],
            },
            "outcome": d.outcome,
            "top_confidence": str(d.top_confidence) if d.top_confidence is not None else None,
            "second_confidence": str(d.second_confidence) if d.second_confidence is not None else None,
            "reconciliation_id": d.reconciliation_id,
            "error_message": d.error_message[:200] if d.error_message else "",
            "top_suggestion_summary": {
                "score": suggestion.get("score") or suggestion.get("top_confidence"),
                "kind": suggestion.get("kind") or suggestion.get("type"),
                "candidate_journal_entry_ids": suggestion.get("journal_entry_ids", [])[:5],
            },
            "created_at": d.created_at.isoformat() if d.created_at else None,
        })

    return {"count": len(rows), "decisions": rows}


# ---------------------------------------------------------------------------
# Tool: undo_via_audit — Phase 1 expansion (write reversal)
# ---------------------------------------------------------------------------
def undo_via_audit(
    company_id: int,
    undo_token: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Reverse a write the agent performed earlier, identified by the
    ``undo_token`` returned alongside the original tool's response.

    Looks up the ``AgentWriteAudit`` row, dispatches per ``tool_name``
    to the right reversal logic, and (on success) flips the audit row
    status to ``undone``. Idempotent: trying to undo an already-undone
    row returns a clean no-op message.

    Currently supports:
      * ``run_reconciliation_agent`` — soft-deletes the
        ``ReconciliationAgentDecision`` rows + linked ``Reconciliation``
        rows from that run.

    Other write tools surface a clear "no reverser registered" message
    so the operator knows manual cleanup is needed.

    Gated by ``settings.AGENT_ALLOW_WRITES`` — even with a valid
    undo_token, the reversal is dry-run-only when the kill-switch is
    off."""
    from django.conf import settings as _django_settings
    from django.db import transaction as _txn

    from agent.models import AgentWriteAudit

    if not undo_token or not isinstance(undo_token, str):
        return {"error": "undo_token is required."}

    try:
        audit = AgentWriteAudit.objects.get(
            company_id=company_id, undo_token=undo_token,
        )
    except AgentWriteAudit.DoesNotExist:
        return {"error": f"No audit row with undo_token={undo_token!r} for this tenant."}

    if audit.status == AgentWriteAudit.STATUS_UNDONE:
        return {
            "ok": True,
            "already_undone": True,
            "audit_id": audit.id,
            "tool_name": audit.tool_name,
        }
    if audit.status != AgentWriteAudit.STATUS_APPLIED:
        return {
            "error": (
                f"Audit row status is {audit.status!r}; only 'applied' rows "
                f"can be undone."
            ),
            "audit_id": audit.id,
        }

    writes_enabled = bool(getattr(_django_settings, "AGENT_ALLOW_WRITES", False))
    effective_dry_run = bool(dry_run) or not writes_enabled

    # Reversal dispatch by tool name.
    reverser = _UNDO_REVERSERS.get(audit.tool_name)
    if reverser is None:
        return {
            "error": (
                f"No reverser registered for tool {audit.tool_name!r}. "
                f"Manual cleanup is required. Audit row id={audit.id}."
            ),
            "audit_id": audit.id,
        }

    try:
        with _txn.atomic():
            preview = reverser(audit, dry_run=effective_dry_run)
            if not effective_dry_run:
                audit.status = AgentWriteAudit.STATUS_UNDONE
                audit.save(update_fields=["status", "updated_at"])
    except Exception as exc:
        return {
            "error": f"Reversal failed: {type(exc).__name__}: {exc}",
            "audit_id": audit.id,
        }

    return {
        "ok": True,
        "dry_run_effective": effective_dry_run,
        "blocked_by_policy": (not writes_enabled) and not bool(dry_run),
        "audit_id": audit.id,
        "tool_name": audit.tool_name,
        "preview": preview,
    }


def _undo_run_reconciliation_agent(audit, *, dry_run: bool) -> dict[str, Any]:
    """Reverse a ``run_reconciliation_agent`` audit row.

    Soft-deletes the run's decisions + linked reconciliations. We
    don't reverse the cache invalidation (it'll naturally rebuild on
    the next read). The operator gets back a count summary.
    """
    from accounting.models import ReconciliationAgentDecision, Reconciliation

    decision_ids = audit.target_ids or []
    decisions = ReconciliationAgentDecision.objects.filter(
        id__in=decision_ids, company=audit.company,
    ).select_related("reconciliation")

    n_decisions = decisions.count()
    recon_ids = [d.reconciliation_id for d in decisions if d.reconciliation_id]

    if dry_run:
        return {
            "would_soft_delete_decisions": n_decisions,
            "would_soft_delete_reconciliations": len(recon_ids),
            "decision_ids": decision_ids,
            "reconciliation_ids": recon_ids,
        }

    # Soft delete via the BaseModel ``is_deleted`` flag — preserves
    # the audit trail. A hard delete would orphan FKs from the agent
    # runtime's history reads.
    Reconciliation.objects.filter(id__in=recon_ids).update(is_deleted=True)
    decisions.update(is_deleted=True)
    return {
        "soft_deleted_decisions": n_decisions,
        "soft_deleted_reconciliations": len(recon_ids),
        "decision_ids": decision_ids,
        "reconciliation_ids": recon_ids,
    }


_UNDO_REVERSERS = {
    "run_reconciliation_agent": _undo_run_reconciliation_agent,
    "apply_document_mapping": _undo_apply_document_mapping,
    "accept_recon_decision": _undo_accept_recon_decision,
}


# ---------------------------------------------------------------------------
# Tool: ingest_document — Phase 2
# ---------------------------------------------------------------------------
def ingest_document(
    company_id: int,
    attachment_id: int,
) -> dict[str, Any]:
    """Parse one ``AgentMessageAttachment`` into structured fields.

    Routing by ``kind`` (set when the file was uploaded):

    * ``nfe_xml``: parsed via ``billing.services.nfe_import_service`` so
      the agent gets back the same structured representation the import
      pipeline produces (chave, partes, totais, itens summary).
    * ``ofx``: parsed via ``ofxtools`` so the agent sees account info +
      the first N transactions (full balance/history is a sync job, not
      an inline parse).
    * ``pdf`` / ``image``: returns a hint that the LLM should "look"
      at the attachment directly — ingest doesn't run OCR here, the
      Responses API handles that via ``input_image``.
    * ``other``: clean error.

    Caches the extracted text on the attachment so subsequent turns
    don't re-parse. Idempotent.
    """
    from agent.models import AgentMessageAttachment

    try:
        att = AgentMessageAttachment.objects.get(
            id=attachment_id, company_id=company_id,
        )
    except AgentMessageAttachment.DoesNotExist:
        return {
            "error": (
                f"Attachment {attachment_id} not found in company {company_id}."
            )
        }

    if att.extracted_text:
        return {
            "ok": True,
            "cached": True,
            "attachment_id": att.id,
            "kind": att.kind,
            "extracted_text_preview": att.extracted_text[:600],
            "size_bytes": len(att.extracted_text),
        }

    kind = att.kind
    extracted = ""
    extra: dict[str, Any] = {}
    error_msg = ""

    try:
        if kind == AgentMessageAttachment.KIND_NFE_XML:
            extracted, extra = _ingest_nfe_xml(att)
        elif kind == AgentMessageAttachment.KIND_OFX:
            extracted, extra = _ingest_ofx(att)
        elif kind == AgentMessageAttachment.KIND_PDF:
            return {
                "ok": True,
                "attachment_id": att.id,
                "kind": kind,
                "note": (
                    "PDFs go through the Responses-API multimodal path. "
                    "The model can already see the file directly — no "
                    "explicit ingest step required."
                ),
            }
        elif kind == AgentMessageAttachment.KIND_IMAGE:
            return {
                "ok": True,
                "attachment_id": att.id,
                "kind": kind,
                "note": (
                    "Images go through the Responses-API multimodal path. "
                    "The model can already see the file directly — no "
                    "explicit ingest step required."
                ),
            }
        else:
            return {
                "error": f"Attachment {attachment_id} has unsupported kind {kind!r}.",
            }
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        log.exception(
            "agent.ingest_document.failed att=%s kind=%s",
            att.id, kind,
        )

    if error_msg:
        att.extraction_error = error_msg[:400]
        att.save(update_fields=["extraction_error", "updated_at"])
        return {"error": error_msg, "attachment_id": att.id, "kind": kind}

    att.extracted_text = extracted
    att.extraction_error = ""
    att.save(update_fields=["extracted_text", "extraction_error", "updated_at"])

    return {
        "ok": True,
        "cached": False,
        "attachment_id": att.id,
        "kind": kind,
        "extracted_text_preview": extracted[:600],
        "size_bytes": len(extracted),
        **({"summary": extra} if extra else {}),
    }


def _ingest_nfe_xml(att) -> tuple[str, dict[str, Any]]:
    """Parse an NF-e XML attachment, returning (text, summary_dict).

    Uses the existing fiscal pipeline parser when available; falls back
    to a generic ElementTree pass for the most useful fields. The
    summary dict is a small structured view for the agent to reference;
    the text is a human-readable Portuguese summary suited for inline
    context."""
    import xml.etree.ElementTree as ET

    raw = att.file.open("rb").read()
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"XML inválido: {exc}") from exc

    # Strip default namespaces for easier xpath.
    ns = {"nfe": "http://www.portalfiscal.inf.br/nfe"}
    def _find(path: str) -> str:
        el = root.find(path, ns)
        return (el.text or "").strip() if el is not None and el.text else ""

    chave = ""
    info_id = root.find(".//nfe:infNFe", ns)
    if info_id is not None and info_id.get("Id"):
        chave = info_id.get("Id", "").replace("NFe", "")

    summary = {
        "chave": chave,
        "numero": _find(".//nfe:ide/nfe:nNF"),
        "serie": _find(".//nfe:ide/nfe:serie"),
        "data_emissao": _find(".//nfe:ide/nfe:dhEmi"),
        "natureza_operacao": _find(".//nfe:ide/nfe:natOp"),
        "emit_cnpj": _find(".//nfe:emit/nfe:CNPJ"),
        "emit_nome": _find(".//nfe:emit/nfe:xNome"),
        "dest_cnpj": _find(".//nfe:dest/nfe:CNPJ") or _find(".//nfe:dest/nfe:CPF"),
        "dest_nome": _find(".//nfe:dest/nfe:xNome"),
        "valor_total": _find(".//nfe:total/nfe:ICMSTot/nfe:vNF"),
        "valor_produtos": _find(".//nfe:total/nfe:ICMSTot/nfe:vProd"),
        "valor_icms": _find(".//nfe:total/nfe:ICMSTot/nfe:vICMS"),
    }

    items = root.findall(".//nfe:det", ns)
    summary["item_count"] = len(items)
    summary["itens_preview"] = [
        {
            "numero": it.get("nItem"),
            "descricao": (it.find(".//nfe:prod/nfe:xProd", ns).text or "")[:100]
                if it.find(".//nfe:prod/nfe:xProd", ns) is not None else "",
            "ncm": (it.find(".//nfe:prod/nfe:NCM", ns).text or "")
                if it.find(".//nfe:prod/nfe:NCM", ns) is not None else "",
            "cfop": (it.find(".//nfe:prod/nfe:CFOP", ns).text or "")
                if it.find(".//nfe:prod/nfe:CFOP", ns) is not None else "",
            "valor": (it.find(".//nfe:prod/nfe:vProd", ns).text or "")
                if it.find(".//nfe:prod/nfe:vProd", ns) is not None else "",
        }
        for it in items[:10]
    ]

    text = (
        f"NF-e {summary.get('numero', '?')}/{summary.get('serie', '?')}\n"
        f"Chave: {summary.get('chave', '?')}\n"
        f"Emissão: {summary.get('data_emissao', '?')}\n"
        f"Natureza: {summary.get('natureza_operacao', '?')}\n"
        f"Emitente: {summary.get('emit_nome', '?')} ({summary.get('emit_cnpj', '?')})\n"
        f"Destinatário: {summary.get('dest_nome', '?')} ({summary.get('dest_cnpj', '?')})\n"
        f"Valor total: R$ {summary.get('valor_total', '?')}\n"
        f"Itens ({summary['item_count']} no total, mostrando primeiros "
        f"{len(summary['itens_preview'])}):\n"
    )
    for it in summary["itens_preview"]:
        text += (
            f"  - #{it['numero']}: {it['descricao']} | NCM {it['ncm']} | "
            f"CFOP {it['cfop']} | R$ {it['valor']}\n"
        )
    return text, summary


def _ingest_ofx(att) -> tuple[str, dict[str, Any]]:
    """Parse an OFX bank statement into a textual summary.

    Tries the ``ofxtools`` library first; if unavailable, falls back to
    a forgiving regex pass over the SGML body so the agent still gets
    something useful."""
    raw_bytes = att.file.open("rb").read()
    raw = raw_bytes.decode("latin-1", errors="replace")

    try:
        from ofxtools import Parser
        parser = Parser.OFXTree()
        parser.parse(att.file.open("rb"))
        ofx_obj = parser.convert()
        statements = ofx_obj.statements or []
        summary = {
            "statement_count": len(statements),
            "accounts": [],
        }
        text_lines = [f"OFX com {len(statements)} extrato(s):"]
        for st in statements:
            acc = getattr(st, "account", None)
            acc_info = {
                "bank": getattr(acc, "bankid", None) if acc else None,
                "account": getattr(acc, "acctid", None) if acc else None,
                "currency": getattr(st, "curdef", None),
                "balance": str(getattr(st, "balamt", "")),
                "balance_date": str(getattr(st, "dtasof", "")),
                "transaction_count": len(getattr(st, "transactions", []) or []),
            }
            summary["accounts"].append(acc_info)
            text_lines.append(
                f"  Conta {acc_info['account']} (banco {acc_info['bank']}): "
                f"saldo R$ {acc_info['balance']} em {acc_info['balance_date']} "
                f"— {acc_info['transaction_count']} lançamentos."
            )
            for tx in (getattr(st, "transactions", []) or [])[:10]:
                text_lines.append(
                    f"    {tx.dtposted} {tx.trnamt:>12} {tx.memo or tx.name or ''}"
                )
        return "\n".join(text_lines), summary
    except ImportError:
        # Fallback regex parse — pull the basics.
        import re
        ban_match = re.search(r"<BANKID>(\d+)", raw)
        acc_match = re.search(r"<ACCTID>(\d+)", raw)
        bal_match = re.search(r"<BALAMT>([-\d.]+)", raw)
        tx_count = len(re.findall(r"<STMTTRN>", raw))
        summary = {
            "bank": ban_match.group(1) if ban_match else None,
            "account": acc_match.group(1) if acc_match else None,
            "balance": bal_match.group(1) if bal_match else None,
            "transaction_count": tx_count,
        }
        text = (
            f"OFX (parser básico, instale ofxtools para detalhamento):\n"
            f"  Banco: {summary['bank']}\n"
            f"  Conta: {summary['account']}\n"
            f"  Saldo: R$ {summary['balance']}\n"
            f"  Lançamentos: {summary['transaction_count']}"
        )
        return text, summary


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
    # Domain tag — used for audit aggregation, observability, and
    # eventually for catalog filtering. Free-form string; suggested
    # values: ``recon``, ``fiscal``, ``finance``, ``billing``,
    # ``external``, ``meta``, ``erp``, ``internal``, ``general``.
    domain: str = "general"


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
        name="discover_api",
        description="Browse the Sysnord REST API surface via api_meta introspection. "
                    "Use it to find which endpoint, model, enum, or filter to use "
                    "before calling call_internal_api. Categories: capabilities | "
                    "models | model_detail | model_relationships | endpoints | enums | "
                    "filters. Combine with 'search' to narrow.",
        handler=discover_api,
        input_schema={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["capabilities", "models", "model_detail",
                             "model_relationships", "endpoints", "enums", "filters"],
                },
                "name": {"type": "string", "description": "Required for *_detail / relationships."},
                "search": {"type": "string", "description": "Substring filter for list categories."},
                "limit": {"type": "integer", "default": 50},
            },
            "required": ["category"],
        },
    ),
    ToolDef(
        name="call_internal_api",
        description="Dispatch a GET/HEAD request to any Sysnord REST endpoint, "
                    "scoped to the conversation's tenant and user. Use it after "
                    "discover_api when no specialised tool fits. Auto-prefixes the "
                    "tenant in /api/... paths; /api/meta/ is global. Response body "
                    "capped at ~30KB — use filters to narrow if truncated. "
                    "Read-only for now (POST/PUT/PATCH/DELETE rejected).",
        handler=call_internal_api,
        input_schema={
            "type": "object",
            "properties": {
                "method": {"type": "string", "enum": ["GET", "HEAD"]},
                "path": {
                    "type": "string",
                    "description": "Endpoint path. Either /api/meta/... (global) or /api/... (auto-tenanted).",
                },
                "query": {"type": "object", "description": "Query string params."},
                "body": {"type": "object", "description": "Request body (ignored for GET/HEAD)."},
            },
            "required": ["method", "path"],
        },
    ),
    ToolDef(
        name="list_erp_apis",
        description="List ERP API calls (Omie etc.) the tenant has access to. "
                    "Filtered to providers with an active ERPConnection for the "
                    "tenant. Use it to discover what external ERP data the agent "
                    "can pull (e.g. ListarContasPagar, ConsultarNF, ListarPedidos).",
        handler=list_erp_apis,
        input_schema={
            "type": "object",
            "properties": {
                "company_id": {"type": "integer"},
                "provider": {"type": "string", "description": "e.g. 'omie' (optional)"},
                "search": {"type": "string"},
            },
            "required": ["company_id"],
        },
    ),
    ToolDef(
        name="describe_erp_api",
        description="Return the full param_schema for one ERP API call. Each entry "
                    "has name + type + description + required + default. Use this "
                    "right before call_erp_api to compose the params dict.",
        handler=describe_erp_api,
        input_schema={
            "type": "object",
            "properties": {
                "company_id": {"type": "integer"},
                "call": {"type": "string", "description": "API method name, e.g. 'ListarContasPagar'"},
                "provider": {"type": "string"},
            },
            "required": ["company_id", "call"],
        },
    ),
    ToolDef(
        name="call_erp_api",
        description="Invoke a registered read-style ERP API call (Omie etc.) for "
                    "the conversation's tenant, using its stored credentials. "
                    "params overrides schema defaults — e.g. {'pagina': 1, "
                    "'registros_por_pagina': 50}. Read-only: only Listar/Consultar/"
                    "Pesquisar/Obter/Get prefixes are allowed; writes are blocked. "
                    "Pass cache_ttl_seconds=N (e.g. 60) to memoise identical "
                    "(call, params) results in-process — useful when the agent "
                    "would otherwise re-fetch the same Listar* data multiple "
                    "times in one turn.",
        handler=call_erp_api,
        input_schema={
            "type": "object",
            "properties": {
                "company_id": {"type": "integer"},
                "call": {"type": "string"},
                "params": {
                    "type": "object",
                    "description": "ERP method parameters to send. Example for Omie ListarPedidos: {'pagina': 1, 'registros_por_pagina': 3}. Always set pagination params when the user asks for a small sample.",
                    "additionalProperties": True,
                },
                "provider": {"type": "string"},
                "cache_ttl_seconds": {
                    "type": "integer",
                    "description": "0 = no cache (default). >0 = reuse identical results within window.",
                    "default": 0,
                },
            },
            "required": ["company_id", "call"],
        },
    ),
    ToolDef(
        name="list_agent_playbooks",
        description="List saved playbooks (named, reusable agent configurations) "
                    "for the tenant. First kind: 'recon' — pre-configured params "
                    "for run_reconciliation_agent. Each row shows last_run_summary "
                    "so the agent can decide whether to re-run or tweak.",
        handler=list_agent_playbooks,
        input_schema={
            "type": "object",
            "properties": {
                "company_id": {"type": "integer"},
                "kind": {"type": "string", "enum": ["recon"]},
                "only_active": {"type": "boolean", "default": True},
            },
            "required": ["company_id"],
        },
    ),
    ToolDef(
        name="save_agent_playbook",
        description="Create or update a playbook (upsert by (company, name)). "
                    "Use it to remember a tuning the user liked — e.g. "
                    "'monthly_close' with auto_accept_threshold=0.9 — so future "
                    "turns can run it by name.",
        handler=save_agent_playbook,
        input_schema={
            "type": "object",
            "properties": {
                "company_id": {"type": "integer"},
                "name": {"type": "string"},
                "kind": {"type": "string", "enum": ["recon"]},
                "description": {"type": "string"},
                "params": {"type": "object"},
                "schedule_cron": {"type": "string"},
                "is_active": {"type": "boolean", "default": True},
            },
            "required": ["company_id", "name"],
        },
    ),
    ToolDef(
        name="run_agent_playbook",
        description="Execute a saved playbook by name (or numeric id). For 'recon' "
                    "kind, runs run_reconciliation_agent with the saved knobs and "
                    "honours AGENT_ALLOW_WRITES. Updates the playbook's "
                    "last_run_summary cache.",
        handler=run_agent_playbook,
        input_schema={
            "type": "object",
            "properties": {
                "company_id": {"type": "integer"},
                "name_or_id": {"type": "string"},
                "dry_run": {"type": "boolean", "default": True},
            },
            "required": ["company_id", "name_or_id"],
        },
    ),
    ToolDef(
        name="apply_document_mapping",
        description="Create an Invoice from an ingested NF-e XML attachment, "
                    "using the partner_id resolved by propose_mapping_from_document. "
                    "Pass product_service_id to also create one InvoiceLine per "
                    "NFe item (catch-all product); omit it for a header-only "
                    "Invoice. **Dry-run by default**: no DB writes happen unless "
                    "(a) dry_run=False AND (b) AGENT_ALLOW_WRITES is enabled. "
                    "Every attempt writes an AgentWriteAudit row with an undo_token "
                    "that undo_via_audit can use to soft-delete the Invoice + lines.",
        handler=apply_document_mapping,
        input_schema={
            "type": "object",
            "properties": {
                "company_id": {"type": "integer"},
                "attachment_id": {"type": "integer"},
                "partner_id": {"type": "integer"},
                "invoice_type": {"type": "string", "enum": ["sale", "purchase"]},
                "invoice_date": {"type": "string", "format": "date"},
                "due_date": {"type": "string", "format": "date"},
                "product_service_id": {
                    "type": "integer",
                    "description": "Optional catch-all ProductService used for all "
                                   "lines. Omit for a header-only Invoice.",
                },
                "dry_run": {"type": "boolean", "default": True},
            },
            "required": ["company_id", "attachment_id", "partner_id", "invoice_type"],
        },
    ),
    ToolDef(
        name="propose_mapping_from_document",
        description="Given an NF-e XML attachment that's been ingested, propose "
                    "how it should land in Sysnord: counterparty (BusinessPartner) "
                    "matched by CNPJ → CNPJ root → name fuzzy; suggested posting "
                    "account from BP's receivable/payable_account or from past "
                    "invoice history. Read-only — pair with apply_document_mapping "
                    "(when that lands) for the actual write.",
        handler=propose_mapping_from_document,
        input_schema={
            "type": "object",
            "properties": {
                "company_id": {"type": "integer"},
                "attachment_id": {"type": "integer"},
            },
            "required": ["company_id", "attachment_id"],
        },
    ),
    ToolDef(
        name="accept_recon_decision",
        description="Promote one ambiguous ReconciliationAgentDecision into a "
                    "live Reconciliation by accepting its top suggestion. Same "
                    "JE flips + cache invalidation as the agent's auto-accept. "
                    "Dry-run by default; live writes need AGENT_ALLOW_WRITES. "
                    "Audited; reversible via undo_via_audit.",
        handler=accept_recon_decision,
        input_schema={
            "type": "object",
            "properties": {
                "company_id": {"type": "integer"},
                "decision_id": {"type": "integer"},
                "dry_run": {"type": "boolean", "default": True},
            },
            "required": ["company_id", "decision_id"],
        },
    ),
    ToolDef(
        name="reject_recon_decision",
        description="Capture a human rejection of an ambiguous decision (with "
                    "an optional reason). Doesn't mutate the decision row — "
                    "writes an AgentWriteAudit row with status=rejected so "
                    "future runs and operators can see what was deliberately "
                    "discarded.",
        handler=reject_recon_decision,
        input_schema={
            "type": "object",
            "properties": {
                "company_id": {"type": "integer"},
                "decision_id": {"type": "integer"},
                "reason": {"type": "string"},
            },
            "required": ["company_id", "decision_id"],
        },
    ),
    ToolDef(
        name="list_recon_decisions",
        description="List per-bank-tx decisions from past reconciliation-agent "
                    "runs. Filter by run_id, outcome (auto_accepted/ambiguous/"
                    "no_match/not_applicable/error), or bank_account_id. Useful "
                    "for follow-up questions like 'show me the ambiguous matches "
                    "from the last run' before any human acceptance.",
        handler=list_recon_decisions,
        input_schema={
            "type": "object",
            "properties": {
                "company_id": {"type": "integer"},
                "run_id": {"type": "integer"},
                "outcome": {
                    "type": "string",
                    "enum": ["auto_accepted", "ambiguous", "no_match",
                             "not_applicable", "error"],
                },
                "bank_account_id": {"type": "integer"},
                "limit": {"type": "integer", "default": 25},
            },
            "required": ["company_id"],
        },
    ),
    ToolDef(
        name="undo_via_audit",
        description="Reverse an earlier write tool's run using the undo_token "
                    "returned with the original response. Looks up the "
                    "AgentWriteAudit row and dispatches per tool to the right "
                    "reverser. Currently supports run_reconciliation_agent "
                    "(soft-deletes decisions + reconciliations). dry_run=true "
                    "by default — flip with explicit consent.",
        handler=undo_via_audit,
        input_schema={
            "type": "object",
            "properties": {
                "company_id": {"type": "integer"},
                "undo_token": {"type": "string"},
                "dry_run": {"type": "boolean", "default": True},
            },
            "required": ["company_id", "undo_token"],
        },
    ),
    ToolDef(
        name="ingest_document",
        description="Parse one chat attachment into structured fields. Supports "
                    "NF-e XML (returns chave/partes/totais/itens), OFX bank "
                    "statements (returns account info + first transactions). "
                    "PDFs and images are handled directly by the multimodal LLM "
                    "— no explicit ingest needed for those. Cached per attachment, "
                    "so calling twice is free.",
        handler=ingest_document,
        input_schema={
            "type": "object",
            "properties": {
                "company_id": {"type": "integer"},
                "attachment_id": {"type": "integer"},
            },
            "required": ["company_id", "attachment_id"],
        },
    ),
    ToolDef(
        name="run_reconciliation_agent",
        description="Run the bank-reconciliation auto-accept agent over a tenant's "
                    "unreconciled transactions, scoring candidates and proposing "
                    "matches. **Dry-run by default**: no DB writes happen unless "
                    "(a) the user passes dry_run=False AND (b) AGENT_ALLOW_WRITES "
                    "is enabled on the deployment. Every run is captured in "
                    "AgentWriteAudit. Returns counters + a preview of decisions.",
        handler=run_reconciliation_agent,
        input_schema={
            "type": "object",
            "properties": {
                "company_id": {"type": "integer"},
                "bank_account_id": {"type": "integer"},
                "date_from": {"type": "string", "format": "date"},
                "date_to": {"type": "string", "format": "date"},
                "limit": {"type": "integer"},
                "auto_accept_threshold": {"type": "number", "description": "0-1 (e.g. 0.95)"},
                "ambiguity_gap": {"type": "number", "description": "Min gap between top-1 and top-2"},
                "min_confidence": {"type": "number"},
                "dry_run": {"type": "boolean", "default": True},
            },
            "required": ["company_id"],
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


# Domain tags for each tool — central, easy to audit. Keep in sync when
# adding new tools above.
_TOOL_DOMAINS: dict[str, str] = {
    # Internal Sysnord DB reads
    "list_companies": "internal",
    "list_accounts": "internal",
    "get_account": "internal",
    "get_transaction": "internal",
    "list_unreconciled_bank_transactions": "recon",
    "suggest_reconciliation": "recon",
    "run_reconciliation_agent": "recon",
    "ingest_document": "fiscal",
    "list_recon_decisions": "recon",
    "undo_via_audit": "recon",
    "propose_mapping_from_document": "billing",
    "apply_document_mapping": "billing",
    "list_agent_playbooks": "recon",
    "save_agent_playbook": "recon",
    "run_agent_playbook": "recon",
    "accept_recon_decision": "recon",
    "reject_recon_decision": "recon",
    "get_invoice": "billing",
    "list_invoice_critics": "billing",
    "get_nota_fiscal": "fiscal",
    "financial_statements": "finance",
    # External — counterparty / fiscal lookups
    "fetch_cnpj_from_receita": "external",
    # External — Brazilian central bank, FX, regional registries
    "fetch_bcb_indicator": "external",
    "fetch_ptax": "external",
    "fetch_cep": "external",
    "fetch_holidays_brazil": "external",
    "fetch_bank_by_code": "external",
    "fetch_ncm": "external",
    "fetch_cnae_info": "external",
    # Local lookups (no network)
    "validate_cfop": "fiscal",
    "simples_nacional_annex_for_cnae": "fiscal",
    # Sysnord meta + dynamic API access
    "discover_api": "meta",
    "call_internal_api": "meta",
    # Tenant-mapped ERP integrations
    "list_erp_apis": "erp",
    "describe_erp_api": "erp",
    "call_erp_api": "erp",
}

# Apply tags. ``replace`` since ToolDef is a frozen dataclass.
TOOLS = [
    type(t)(
        name=t.name,
        description=t.description,
        handler=t.handler,
        input_schema=t.input_schema,
        domain=_TOOL_DOMAINS.get(t.name, "general"),
    )
    for t in TOOLS
]
TOOLS_BY_NAME: dict[str, ToolDef] = {t.name: t for t in TOOLS}


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a tool call. Raises KeyError on unknown tool."""
    tool = TOOLS_BY_NAME[name]
    return tool.handler(**(arguments or {}))


def get_tool_domain(name: str) -> str:
    """Look up a tool's domain tag (or 'general' if unknown)."""
    tool = TOOLS_BY_NAME.get(name)
    return tool.domain if tool else "general"
