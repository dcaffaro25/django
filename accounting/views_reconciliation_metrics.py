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
        "transaction_ids": [100, 101]  // Optional (specific transactions, must be unposted)
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
        
        # Trigger Celery task for async recalculation
        try:
            task = recalculate_reconciliation_metrics_task.delay(
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat() if end_date else None,
                company_id=company_id,
                entity_id=entity_id,
                account_id=account_id,
                transaction_ids=transaction_ids,
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

