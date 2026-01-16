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


class ReconciliationMetricsRecalculateView(APIView):
    """
    Endpoint to recalculate reconciliation financial metrics.
    
    POST /api/reconciliation-metrics/recalculate/
    
    Request body:
    {
        "start_date": "2025-01-01",  // Required
        "end_date": "2025-01-31",     // Optional, defaults to today
        "company_id": 1,               // Optional
        "entity_id": 2,                // Optional
        "account_id": 10,              // Optional (filters journal entries)
        "transaction_ids": [100, 101]  // Optional (specific transactions)
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
        
        # Run recalculation
        service = ReconciliationFinancialMetricsService()
        try:
            result = service.recalculate_metrics(
                start_date=start_date,
                end_date=end_date,
                company_id=company_id,
                entity_id=entity_id,
                account_id=account_id,
                transaction_ids=transaction_ids,
            )
            
            return Response(result, status=status.HTTP_200_OK)
        
        except Exception as e:
            return Response(
                {
                    "error": "Recalculation failed",
                    "message": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ReconciliationMetricsTransactionView(APIView):
    """
    Endpoint to get calculated metrics for a transaction.
    
    GET /api/reconciliation-metrics/transaction/{transaction_id}/
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request, transaction_id: int, tenant_id=None):
        """Get metrics for a specific transaction."""
        from accounting.models import Transaction
        
        try:
            transaction = Transaction.objects.get(id=transaction_id)
        except Transaction.DoesNotExist:
            return Response(
                {"error": "Transaction not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        service = ReconciliationFinancialMetricsService()
        metrics = service.calculate_transaction_metrics(transaction)
        
        return Response({
            "transaction_id": transaction_id,
            "metrics": metrics
        }, status=status.HTTP_200_OK)


class ReconciliationMetricsJournalEntryView(APIView):
    """
    Endpoint to get calculated metrics for a journal entry.
    
    GET /api/reconciliation-metrics/journal-entry/{journal_entry_id}/
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request, journal_entry_id: int, tenant_id=None):
        """Get metrics for a specific journal entry."""
        from accounting.models import JournalEntry
        
        try:
            journal_entry = JournalEntry.objects.get(id=journal_entry_id)
        except JournalEntry.DoesNotExist:
            return Response(
                {"error": "Journal entry not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        service = ReconciliationFinancialMetricsService()
        metrics = service.calculate_journal_entry_metrics(journal_entry)
        account_verification = service.verify_account_assignment(journal_entry)
        
        return Response({
            "journal_entry_id": journal_entry_id,
            "metrics": metrics,
            "account_verification": account_verification
        }, status=status.HTTP_200_OK)

