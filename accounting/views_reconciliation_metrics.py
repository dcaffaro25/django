"""
views_reconciliation_metrics.py

API views for reconciliation financial metrics calculation and retrieval.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.utils.dateparse import parse_date
from datetime import date
from typing import Optional, List

from accounting.services.reconciliation_financial_metrics_service import (
    ReconciliationFinancialMetricsService,
)
from accounting.tasks import recalculate_reconciliation_metrics_task


class ReconciliationMetricsRecalculateView(APIView):
    """
    Endpoint to queue reconciliation financial metrics recalculation as a Celery task.
    
    POST /api/reconciliation-metrics/recalculate/
    
    Note: Only processes unposted (pending) transactions and journal entries.
    Posted transactions and journal entries are excluded from recalculation.
    
    Returns a task_id that can be used to check the status of the recalculation.
    
    Request body:
    {
        "start_date": "2025-01-01",  // Required
        "end_date": "2025-01-31",     // Optional, defaults to today
        "company_id": 1,               // Optional
        "entity_id": 2,                // Optional
        "account_id": 10,              // Optional (filters journal entries)
        "transaction_ids": [100, 101], // Optional (specific transactions, must be unposted)
        "only_uncalculated": false     // Optional (default: false). If true, only process items that haven't been calculated yet
    }
    
    Response:
    {
        "success": true,
        "task_id": "abc-123-def",
        "status": "PENDING",
        "message": "Recalculation task queued successfully"
    }
    """
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request, tenant_id=None):
        """Recalculate metrics for transactions and journal entries."""
        # Parse start_date (required)
        start_date_str = request.data.get('start_date')
        if not start_date_str:
            return Response(
                {"error": "start_date is required (YYYY-MM-DD format)"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        start_date = parse_date(start_date_str)
        if not start_date:
            return Response(
                {"error": "Invalid start_date format. Use YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Parse end_date (optional, defaults to today)
        end_date = None
        end_date_str = request.data.get('end_date')
        if end_date_str:
            end_date = parse_date(end_date_str)
            if not end_date:
                return Response(
                    {"error": "Invalid end_date format. Use YYYY-MM-DD"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Parse optional filters
        company_id = request.data.get('company_id')
        entity_id = request.data.get('entity_id')
        account_id = request.data.get('account_id')
        transaction_ids = request.data.get('transaction_ids')  # List of IDs
        only_uncalculated = request.data.get('only_uncalculated', False)  # Boolean flag
        
        # Validate transaction_ids if provided
        if transaction_ids is not None:
            if not isinstance(transaction_ids, list):
                return Response(
                    {"error": "transaction_ids must be a list"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            try:
                transaction_ids = [int(id) for id in transaction_ids]
            except (ValueError, TypeError):
                return Response(
                    {"error": "All transaction_ids must be integers"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Convert optional IDs to integers if provided
        try:
            if company_id is not None:
                company_id = int(company_id)
            if entity_id is not None:
                entity_id = int(entity_id)
            if account_id is not None:
                account_id = int(account_id)
        except (ValueError, TypeError):
            return Response(
                {"error": "company_id, entity_id, and account_id must be integers"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Convert only_uncalculated to boolean
        if isinstance(only_uncalculated, str):
            only_uncalculated = only_uncalculated.lower() in ('true', '1', 'yes')
        elif not isinstance(only_uncalculated, bool):
            only_uncalculated = bool(only_uncalculated)
        
        # Trigger Celery task for async recalculation
        try:
            task = recalculate_reconciliation_metrics_task.delay(
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat() if end_date else None,
                company_id=company_id,
                entity_id=entity_id,
                account_id=account_id,
                transaction_ids=transaction_ids,
                only_uncalculated=only_uncalculated,
            )
            
            return Response(
                {
                    "success": True,
                    "task_id": task.id,
                    "status": task.status,
                    "message": "Recalculation task queued successfully",
                    "filters": {
                        "start_date": str(start_date),
                        "end_date": str(end_date) if end_date else None,
                        "company_id": company_id,
                        "entity_id": entity_id,
                        "account_id": account_id,
                        "transaction_ids": transaction_ids,
                        "only_uncalculated": only_uncalculated,
                    }
                },
                status=status.HTTP_202_ACCEPTED
            )
        
        except Exception as e:
            return Response(
                {
                    "error": "Failed to queue recalculation task",
                    "message": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ReconciliationMetricsTransactionView(APIView):
    """
    Endpoint to get calculated metrics for a transaction.
    
    GET /api/reconciliation-metrics/transaction/{transaction_id}/
    
    Also recalculates transaction flags (is_balanced, is_reconciled, state, is_posted)
    and journal entry flags (is_cash, is_reconciled) before returning metrics.
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request, transaction_id: int, tenant_id=None):
        """Get metrics for a specific transaction."""
        from accounting.models import Transaction
        from accounting.utils import recalculate_transaction_and_journal_entry_status
        import logging
        
        log = logging.getLogger(__name__)
        
        try:
            transaction = Transaction.objects.get(id=transaction_id)
        except Transaction.DoesNotExist:
            return Response(
                {"error": "Transaction not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Recalculate transaction and journal entry flags first
        try:
            recalculate_transaction_and_journal_entry_status(
                transaction_ids=[transaction_id]
            )
        except Exception as e:
            log.warning(f"Error recalculating flags for transaction {transaction_id}: {e}")
            # Continue even if flag recalculation fails
        
        # Refresh transaction from DB to get updated flags
        transaction.refresh_from_db()
        
        # Calculate reconciliation financial metrics
        service = ReconciliationFinancialMetricsService()
        metrics = service.calculate_transaction_metrics(transaction)
        
        # Store metrics
        service.store_transaction_metrics(transaction, metrics)
        
        return Response({
            "transaction_id": transaction_id,
            "metrics": metrics,
            "flags": {
                "is_balanced": transaction.is_balanced,
                "is_reconciled": transaction.is_reconciled,
                "state": transaction.state,
                "is_posted": transaction.is_posted,
            }
        }, status=status.HTTP_200_OK)


class ReconciliationMetricsJournalEntryView(APIView):
    """
    Endpoint to get calculated metrics for a journal entry.
    
    GET /api/reconciliation-metrics/journal-entry/{journal_entry_id}/
    
    Also recalculates journal entry flags (is_cash, is_reconciled) and 
    parent transaction flags (is_balanced, is_reconciled) before returning metrics.
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request, journal_entry_id: int, tenant_id=None):
        """Get metrics for a specific journal entry."""
        from accounting.models import JournalEntry
        from accounting.utils import update_journal_entries_and_transaction_flags
        import logging
        
        log = logging.getLogger(__name__)
        
        try:
            journal_entry = JournalEntry.objects.select_related('transaction').get(id=journal_entry_id)
        except JournalEntry.DoesNotExist:
            return Response(
                {"error": "Journal entry not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Recalculate flags for this journal entry and its transaction
        try:
            update_journal_entries_and_transaction_flags([journal_entry])
        except Exception as e:
            log.warning(f"Error recalculating flags for journal entry {journal_entry_id}: {e}")
            # Continue even if flag recalculation fails
        
        # Refresh journal entry and transaction from DB to get updated flags
        journal_entry.refresh_from_db()
        if journal_entry.transaction_id:
            journal_entry.transaction.refresh_from_db()
        
        # Calculate reconciliation financial metrics
        service = ReconciliationFinancialMetricsService()
        metrics = service.calculate_journal_entry_metrics(journal_entry)
        account_verification = service.verify_account_assignment(journal_entry)
        
        # Store metrics
        service.store_journal_entry_metrics(journal_entry, metrics)
        
        return Response({
            "journal_entry_id": journal_entry_id,
            "metrics": metrics,
            "account_verification": account_verification,
            "flags": {
                "is_cash": journal_entry.is_cash,
                "is_reconciled": journal_entry.is_reconciled,
            },
            "transaction_flags": {
                "is_balanced": journal_entry.transaction.is_balanced if journal_entry.transaction_id else None,
                "is_reconciled": journal_entry.transaction.is_reconciled if journal_entry.transaction_id else None,
            } if journal_entry.transaction_id else None,
        }, status=status.HTTP_200_OK)


class ReconciliationKPIsView(APIView):
    """
    Tenant-scoped KPI snapshot for the Reconciliation dashboard.

    GET /{tenant}/api/reconciliation/kpis/
    Optional query params:
      - date_from, date_to: YYYY-MM-DD (restrict unreconciled computation; defaults: no lower bound, today)
      - lookback_days:      integer, default 30, window used for auto-match rate + task counts
      - trend_days:         integer, default 14, window for daily unreconciled-count sparkline

    Response:
    {
      "as_of": "2026-04-18",
      "unreconciled": {
        "count": 123,
        "amount_abs": "12345.67",
        "oldest_age_days": 42,
        "oldest_date": "2026-03-07"
      },
      "tasks_30d": {
        "completed": 17,
        "failed": 2,
        "running": 1,
        "suggestion_count": 900,
        "auto_match_applied": 750,
        "automatch_rate": 0.8333
      },
      "trend_14d": [
        {"date": "2026-04-05", "new_bank_tx": 12, "reconciled": 10}, ...
      ]
    }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, tenant_id=None):
        from decimal import Decimal
        from datetime import timedelta
        from django.db.models import Sum, Count, Q, F, Min, Value, DecimalField
        from django.db.models.functions import Abs, Coalesce, TruncDate
        from multitenancy.utils import resolve_tenant
        from accounting.models import (
            BankTransaction,
            JournalEntry,
            Reconciliation,
            ReconciliationTask,
        )

        try:
            company_id = resolve_tenant(tenant_id).id
        except Exception:
            return Response({"error": "invalid tenant"}, status=status.HTTP_400_BAD_REQUEST)

        today = date.today()
        # Optional explicit window. When omitted, the bank side is
        # unbounded so the KPI matches what the Workbench (Bancada)
        # shows -- previously we defaulted ``date_to`` to today, which
        # silently dropped future-dated bank tx and produced a number
        # the operator couldn't reconcile against the workbench list.
        date_to = parse_date(request.query_params.get("date_to") or "")
        date_from = parse_date(request.query_params.get("date_from") or "")
        try:
            lookback_days = int(request.query_params.get("lookback_days") or 30)
            trend_days = int(request.query_params.get("trend_days") or 14)
        except (TypeError, ValueError):
            return Response({"error": "lookback_days and trend_days must be integers"}, status=status.HTTP_400_BAD_REQUEST)

        lookback_start = today - timedelta(days=lookback_days)
        trend_start = today - timedelta(days=trend_days - 1)

        # The book side is anchored to D-1 (yesterday) when no explicit
        # ``date_to`` is supplied: the Painel sums book entries whose
        # expected settlement date has already passed. Future-dated JEs
        # (next-day boletos, scheduled payments) are excluded because
        # they're not late yet and including them would inflate the
        # "em aberto" alarm bar with normal future activity.
        book_settlement_cutoff = date_to or (today - timedelta(days=1))

        # --- Unreconciled bank transactions ---
        # A bank tx is unreconciled if it has NO reconciliation record with a "closed" status.
        closed_statuses = ["matched", "approved"]
        bt_qs = BankTransaction.objects.filter(
            company_id=company_id,
            is_deleted=False,
        ).exclude(
            reconciliations__status__in=closed_statuses,
            reconciliations__is_deleted=False,
        )
        if date_from:
            bt_qs = bt_qs.filter(date__gte=date_from)
        if date_to:
            bt_qs = bt_qs.filter(date__lte=date_to)

        agg = bt_qs.aggregate(
            count=Count("id", distinct=True),
            amount_abs=Sum(Abs(F("amount"))),
            oldest_date=Min("date"),
        )
        count = int(agg.get("count") or 0)
        amount_abs = agg.get("amount_abs") or Decimal("0")
        oldest_date = agg.get("oldest_date")
        oldest_age = (today - oldest_date).days if oldest_date else None

        # --- Unreconciled BOOK side (journal entries on cash/bank legs) ---
        # Filter rationale:
        #   * ``account__bank_account__isnull=False`` -- structural
        #     definition of a cash leg: the JE's GL account points to a
        #     BankAccount row. We tried switching to ``is_cash=True``
        #     (the maintained flag), but in tenants where the metrics
        #     recompute pipeline hasn't run on every JE the flag is
        #     under-set and the KPI collapses by orders of magnitude.
        #     The structural join is consistent across tenants.
        #   * ``is_reconciled=False`` -- not yet tied to a bank tx.
        #   * ``state != canceled``   -- ignore retracted lines.
        #   * ``date__lte = D-1``     -- only legs whose expected
        #     settlement date has passed. The card disclaimer surfaces
        #     this cutoff to the operator so they can reconcile it
        #     against what they see in other reports.
        je_qs = JournalEntry.objects.filter(
            company_id=company_id,
            is_reconciled=False,
            account__bank_account__isnull=False,
        ).exclude(state="canceled")
        if date_from:
            je_qs = je_qs.filter(date__gte=date_from)
        je_qs = je_qs.filter(date__lte=book_settlement_cutoff)

        # Coalesce both legs to 0 before subtracting -- ``debit_amount``
        # and ``credit_amount`` are nullable on JournalEntry, and SQL's
        # ``NULL - <number> = NULL`` would otherwise null-out the whole
        # row. ``Sum`` then drops NULLs, so the historical query was
        # silently summing only the (rare) JEs with both legs filled,
        # producing R$ 0.00 on tenants where the convention is one-leg-
        # per-row. ``DecimalField`` on the Value() keeps PostgreSQL
        # happy when none of the inputs constrain the type.
        _zero = Value(Decimal("0"), output_field=DecimalField(max_digits=12, decimal_places=2))
        je_agg = je_qs.aggregate(
            count=Count("id", distinct=True),
            amount_abs=Sum(
                Abs(Coalesce(F("debit_amount"), _zero) - Coalesce(F("credit_amount"), _zero))
            ),
            oldest_date=Min("date"),
        )
        book_count = int(je_agg.get("count") or 0)
        book_amount_abs = je_agg.get("amount_abs") or Decimal("0")
        book_oldest_date = je_agg.get("oldest_date")
        book_oldest_age = (today - book_oldest_date).days if book_oldest_date else None

        # --- Tasks in lookback window ---
        tasks = ReconciliationTask.objects.filter(
            tenant_id=str(company_id),
            updated_at__date__gte=lookback_start,
        )
        task_totals = tasks.aggregate(
            completed=Count("id", filter=Q(status="completed")),
            failed=Count("id", filter=Q(status="failed")),
            running=Count("id", filter=Q(status__in=["running", "queued"])),
            suggestion_count=Sum("suggestion_count", filter=Q(status="completed")),
            auto_match_applied=Sum("auto_match_applied", filter=Q(status="completed")),
        )
        sug = int(task_totals.get("suggestion_count") or 0)
        auto = int(task_totals.get("auto_match_applied") or 0)
        automatch_rate = float(auto / sug) if sug > 0 else None

        # --- Trend: daily new bank tx vs. daily reconciliations ---
        bt_trend = (
            BankTransaction.objects.filter(
                company_id=company_id,
                is_deleted=False,
                date__gte=trend_start,
                date__lte=today,
            )
            .values("date")
            .annotate(n=Count("id"))
            .order_by("date")
        )
        bt_by_day = {r["date"]: r["n"] for r in bt_trend}

        rec_trend = (
            Reconciliation.objects.filter(
                company_id=company_id,
                is_deleted=False,
                status__in=closed_statuses,
                updated_at__date__gte=trend_start,
                updated_at__date__lte=today,
            )
            .annotate(d=TruncDate("updated_at"))
            .values("d")
            .annotate(n=Count("id"))
            .order_by("d")
        )
        rec_by_day = {r["d"]: r["n"] for r in rec_trend}

        trend = []
        for i in range(trend_days):
            d = trend_start + timedelta(days=i)
            trend.append({
                "date": d.isoformat(),
                "new_bank_tx": int(bt_by_day.get(d) or 0),
                "reconciled": int(rec_by_day.get(d) or 0),
            })

        return Response(
            {
                "as_of": today.isoformat(),
                "unreconciled": {
                    # Top-level keys preserved for backward compat: the
                    # legacy dashboard widget reads these as the bank
                    # side. New callers should prefer ``unreconciled.bank``
                    # / ``unreconciled.book`` for clarity.
                    "count": count,
                    "amount_abs": str(amount_abs),
                    "oldest_age_days": oldest_age,
                    "oldest_date": oldest_date.isoformat() if oldest_date else None,
                    "bank": {
                        "count": count,
                        "amount_abs": str(amount_abs),
                        "oldest_age_days": oldest_age,
                        "oldest_date": oldest_date.isoformat() if oldest_date else None,
                        # Echo the filter so the frontend can render an
                        # accurate disclaimer ("any unreconciled, no date
                        # ceiling" vs. "up to {date_to}").
                        "date_to": date_to.isoformat() if date_to else None,
                        "date_from": date_from.isoformat() if date_from else None,
                    },
                    "book": {
                        "count": book_count,
                        "amount_abs": str(book_amount_abs),
                        "oldest_age_days": book_oldest_age,
                        "oldest_date": book_oldest_date.isoformat() if book_oldest_date else None,
                        # Settlement cutoff drives the card disclaimer.
                        # Defaults to D-1 (today - 1 day); operators can
                        # widen with explicit ``?date_to=`` if needed.
                        "settlement_cutoff": book_settlement_cutoff.isoformat(),
                    },
                },
                "tasks_30d": {
                    "completed": int(task_totals.get("completed") or 0),
                    "failed": int(task_totals.get("failed") or 0),
                    "running": int(task_totals.get("running") or 0),
                    "suggestion_count": sug,
                    "auto_match_applied": auto,
                    "automatch_rate": automatch_rate,
                },
                "trend_14d": trend,
            },
            status=status.HTTP_200_OK,
        )
