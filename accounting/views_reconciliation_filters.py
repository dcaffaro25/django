"""
Endpoints supporting the reconciliation filter-stack UI.

* `GET  /api/reconciliation/filter-columns/?kind=bank_transaction`
     Lists the columns the FilterStackBuilder can offer, with their types and
     allowed operators.

* `POST /api/reconciliation/preview-counts/`
     Given optional bank/book filter stacks and optional existing bank_ids /
     book_ids, returns how many rows would be selected on each side. Used for
     live feedback in the "Run rule" drawer and on ConfigsPage row hovers.
"""

from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounting.models import BankTransaction, JournalEntry
from accounting.services.filter_compiler import (
    apply_stack,
    compile_stack_report,
    describe_columns,
    merge_ids,
)
from multitenancy.utils import resolve_tenant


def _scoped_qs(model, company_id):
    qs = model.objects.all()
    if company_id is not None:
        qs = qs.filter(company_id=company_id)
    return qs


class FilterColumnsView(APIView):
    """Describe available columns for the filter-stack builder."""

    permission_classes = [IsAuthenticated]

    def get(self, request, tenant_id=None):
        kind = request.query_params.get("kind")
        if kind:
            return Response({
                "kind": kind,
                "columns": describe_columns(kind),
            })
        return Response({
            "bank_transaction": describe_columns("bank_transaction"),
            "journal_entry": describe_columns("journal_entry"),
        })


class PreviewCountsView(APIView):
    """
    POST body:
      {
        "bank_filters":     <stack>?,       # applied to BankTransaction
        "book_filters":     <stack>?,       # applied to JournalEntry
        "bank_ids":         [int]?,         # explicit ids
        "book_ids":         [int]?,         # explicit ids
        "override_mode":    "append"|"replace"|"intersect" (default "append"),
        "merge_config_filters": bool,       # if true AND config_id set, AND cfg filters
        "config_id":        int?,           # optional: to preview "config + user filter" combo
      }

    Returns:
      {
        "bank": {"total": N, "sample_ids": [...] (≤ 5)},
        "book": {"total": N, "sample_ids": [...]},
        "warnings": [...]
      }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, tenant_id=None):
        data = request.data or {}
        company = resolve_tenant(tenant_id) if tenant_id else None
        company_id = getattr(company, "id", None)

        override_mode = (data.get("override_mode") or "append").lower()
        if override_mode not in ("append", "replace", "intersect"):
            override_mode = "append"

        merge_cfg_filters = bool(data.get("merge_config_filters", False))
        cfg = None
        if merge_cfg_filters and data.get("config_id"):
            try:
                from accounting.models import ReconciliationConfig
                cfg = ReconciliationConfig.objects.get(id=int(data["config_id"]))
            except Exception:
                cfg = None

        warnings: list[str] = []

        # ----- BANK side -----
        bank_qs = _scoped_qs(BankTransaction, company_id)
        if cfg and cfg.bank_filters:
            bank_qs = apply_stack(bank_qs, cfg.bank_filters, "bank_transaction")
        bank_stack = data.get("bank_filters")
        if bank_stack:
            bank_qs = apply_stack(bank_qs, bank_stack, "bank_transaction")
            _, w = compile_stack_report(bank_stack, "bank_transaction")
            warnings.extend([f"bank: {m}" for m in w])

        bank_filter_ids = list(bank_qs.values_list("id", flat=True)) if bank_stack or cfg else []
        bank_final = merge_ids(data.get("bank_ids"), bank_filter_ids, mode=override_mode) \
            if (bank_stack or cfg) else list(data.get("bank_ids") or [])
        # If neither filters nor explicit IDs provided, report "all unscoped"
        if not (bank_stack or cfg or data.get("bank_ids")):
            bank_final_qs = _scoped_qs(BankTransaction, company_id)
            bank_total = bank_final_qs.count()
            bank_sample = list(bank_final_qs.values_list("id", flat=True)[:5])
        else:
            bank_total = len(bank_final)
            bank_sample = bank_final[:5]

        # ----- BOOK side -----
        book_qs = _scoped_qs(JournalEntry, company_id)
        if cfg and cfg.book_filters:
            book_qs = apply_stack(book_qs, cfg.book_filters, "journal_entry")
        book_stack = data.get("book_filters")
        if book_stack:
            book_qs = apply_stack(book_qs, book_stack, "journal_entry")
            _, w = compile_stack_report(book_stack, "journal_entry")
            warnings.extend([f"book: {m}" for m in w])

        book_filter_ids = list(book_qs.values_list("id", flat=True)) if book_stack or cfg else []
        book_final = merge_ids(data.get("book_ids"), book_filter_ids, mode=override_mode) \
            if (book_stack or cfg) else list(data.get("book_ids") or [])
        if not (book_stack or cfg or data.get("book_ids")):
            book_final_qs = _scoped_qs(JournalEntry, company_id)
            book_total = book_final_qs.count()
            book_sample = list(book_final_qs.values_list("id", flat=True)[:5])
        else:
            book_total = len(book_final)
            book_sample = book_final[:5]

        return Response({
            "bank": {"total": bank_total, "sample_ids": list(bank_sample)},
            "book": {"total": book_total, "sample_ids": list(book_sample)},
            "warnings": warnings,
            "override_mode": override_mode,
        })
