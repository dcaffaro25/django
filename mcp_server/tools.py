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
from datetime import date, datetime
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
