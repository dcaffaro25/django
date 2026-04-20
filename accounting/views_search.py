"""Global search endpoint for the ⌘K command palette.

GET /{tenant}/api/search/?q=<query>&limit=<n>
Returns grouped, tenant-scoped hits across the most common record types.

Response:
{
  "q": "...",
  "groups": [
    {"type": "transaction", "label": "Transações", "items": [
        {"id": 123, "title": "...", "subtitle": "2026-03-15 · SJM · R$ 150,00", "url": "/accounting/transactions?id=123"},
        ...
    ]},
    {"type": "bank_transaction", "label": "Extratos", "items": [...]},
    ...
  ],
  "total": 47
}
"""

from decimal import Decimal
from typing import Any, Dict, List

from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from multitenancy.utils import resolve_tenant


def _fmt_amount(v: Any) -> str:
    try:
        d = Decimal(str(v))
        return f"R$ {d:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(v)


class GlobalSearchView(APIView):
    """Cross-entity, tenant-scoped search for ⌘K."""

    permission_classes = [IsAuthenticated]

    def get(self, request, tenant_id=None):
        q = (request.query_params.get("q") or "").strip()
        try:
            limit = max(1, min(50, int(request.query_params.get("limit") or 8)))
        except (TypeError, ValueError):
            limit = 8

        if len(q) < 2:
            return Response({"q": q, "groups": [], "total": 0})

        try:
            company_id = resolve_tenant(tenant_id).id
        except Exception:
            return Response({"q": q, "groups": [], "total": 0})

        from accounting.models import (
            Account, BankAccount, BankTransaction, JournalEntry, Transaction,
            ReconciliationConfig, ReconciliationPipeline,
        )
        from multitenancy.models import Entity

        groups: List[Dict[str, Any]] = []
        total = 0

        # Transactions
        tx_qs = (
            Transaction.objects.filter(company_id=company_id, is_deleted=False)
            .filter(Q(description__icontains=q) | Q(erp_id__iexact=q))
            .select_related("entity", "currency")
            .order_by("-date")[:limit]
        )
        tx_items = [
            {
                "id": t.id,
                "title": t.description or f"Transação #{t.id}",
                "subtitle": f"{t.date} · {getattr(t.entity, 'name', '—')} · {_fmt_amount(t.amount)}",
                "url": f"/accounting/transactions?id={t.id}",
                "state": t.state,
            }
            for t in tx_qs
        ]
        if tx_items:
            groups.append({"type": "transaction", "label": "Transações", "items": tx_items})
            total += len(tx_items)

        # Bank transactions
        bt_qs = (
            BankTransaction.objects.filter(company_id=company_id, is_deleted=False)
            .filter(Q(description__icontains=q) | Q(reference_number__iexact=q) | Q(cnpj__iexact=q))
            .select_related("bank_account", "currency")
            .order_by("-date")[:limit]
        )
        bt_items = [
            {
                "id": b.id,
                "title": b.description or f"Extrato #{b.id}",
                "subtitle": f"{b.date} · {getattr(b.bank_account, 'name', '—')} · {_fmt_amount(b.amount)}",
                "url": f"/recon/workbench?search={b.description[:40] if b.description else ''}",
            }
            for b in bt_qs
        ]
        if bt_items:
            groups.append({"type": "bank_transaction", "label": "Extratos bancários", "items": bt_items})
            total += len(bt_items)

        # Journal entries
        je_qs = (
            JournalEntry.objects.filter(company_id=company_id, is_deleted=False)
            .filter(Q(description__icontains=q))
            .select_related("account")
            .order_by("-transaction__date")[:limit]
        )
        je_items = [
            {
                "id": j.id,
                "title": j.description or f"Lançamento #{j.id}",
                "subtitle": f"{getattr(j.transaction, 'date', '—')} · {getattr(j.account, 'name', '—')}",
                "url": f"/accounting/journal-entries?id={j.id}",
            }
            for j in je_qs
        ]
        if je_items:
            groups.append({"type": "journal_entry", "label": "Lançamentos", "items": je_items})
            total += len(je_items)

        # Entities
        ent_qs = (
            Entity.objects.filter(company_id=company_id, is_deleted=False)
            .filter(Q(name__icontains=q) | Q(path__icontains=q))
            .order_by("path")[:limit]
        )
        ent_items = [
            {
                "id": e.id,
                "title": e.name,
                "subtitle": e.path or "",
                "url": f"/settings/entities?id={e.id}",
            }
            for e in ent_qs
        ]
        if ent_items:
            groups.append({"type": "entity", "label": "Entidades", "items": ent_items})
            total += len(ent_items)

        # Accounts
        acc_qs = (
            Account.objects.filter(company_id=company_id, is_deleted=False)
            .filter(Q(name__icontains=q) | Q(account_code__iexact=q) | Q(path__icontains=q))
            .order_by("path")[:limit]
        )
        acc_items = [
            {
                "id": a.id,
                "title": f"{a.account_code + ' · ' if a.account_code else ''}{a.name}",
                "subtitle": a.path or "",
                "url": f"/accounting/accounts?id={a.id}",
            }
            for a in acc_qs
        ]
        if acc_items:
            groups.append({"type": "account", "label": "Plano de contas", "items": acc_items})
            total += len(acc_items)

        # Bank accounts
        ba_qs = (
            BankAccount.objects.filter(company_id=company_id, is_deleted=False)
            .filter(Q(name__icontains=q) | Q(account_number__iexact=q))
            .select_related("bank", "entity")
            .order_by("name")[:limit]
        )
        ba_items = [
            {
                "id": b.id,
                "title": b.name,
                "subtitle": f"{getattr(b.bank, 'name', '—')} · {b.account_number or '—'}",
                "url": f"/accounting/bank-accounts?id={b.id}",
            }
            for b in ba_qs
        ]
        if ba_items:
            groups.append({"type": "bank_account", "label": "Contas bancárias", "items": ba_items})
            total += len(ba_items)

        # Configs + pipelines (admin-ish)
        cfg_qs = (
            ReconciliationConfig.objects.filter(
                Q(scope="global") | Q(company_id=company_id)
            )
            .filter(Q(name__icontains=q) | Q(description__icontains=q))
            .order_by("name")[:limit]
        )
        cfg_items = [
            {"id": c.id, "title": c.name, "subtitle": c.description or c.scope, "url": "/recon/configs"}
            for c in cfg_qs
        ]
        if cfg_items:
            groups.append({"type": "reconciliation_config", "label": "Configurações", "items": cfg_items})
            total += len(cfg_items)

        pipe_qs = (
            ReconciliationPipeline.objects.filter(
                Q(scope="global") | Q(company_id=company_id)
            )
            .filter(Q(name__icontains=q) | Q(description__icontains=q))
            .order_by("name")[:limit]
        )
        pipe_items = [
            {"id": p.id, "title": p.name, "subtitle": p.description or p.scope, "url": "/recon/pipelines"}
            for p in pipe_qs
        ]
        if pipe_items:
            groups.append({"type": "reconciliation_pipeline", "label": "Pipelines", "items": pipe_items})
            total += len(pipe_items)

        return Response({"q": q, "groups": groups, "total": total})
