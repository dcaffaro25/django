# NORD/accounting/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import viewsets, status, response
from rest_framework.decorators import action, api_view
from django.db.models import Q, Sum, Count, F, Value as V
from django.db.models.functions import TruncDate, Coalesce, Cast
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from itertools import product, combinations
from multitenancy.api_utils import generic_bulk_create, generic_bulk_update, generic_bulk_delete
from multitenancy.models import CustomUser, Company, Entity
from multitenancy.mixins import ScopedQuerysetMixin
from .models import (Currency, Account, Transaction, JournalEntry, Rule, CostCenter, Bank, BankAccount, BankTransaction, Reconciliation, CostCenter,ReconciliationTask, ReconciliationConfig)
from .serializers import (CurrencySerializer, AccountSerializer, TransactionSerializer, CostCenterSerializer, JournalEntrySerializer, RuleSerializer, BankSerializer, BankAccountSerializer, BankTransactionSerializer, ReconciliationSerializer, TransactionListSerializer,ReconciliationTaskSerializer,ReconciliationConfigSerializer)
from .services.transaction_service import *
from .utils import parse_ofx_text, decode_ofx_content, generate_ofx_transaction_hash, find_book_combos
from datetime import datetime
import pandas as pd
from decimal import Decimal
from django.db.models import DecimalField, DateField
from django.db.utils import OperationalError
from itertools import product
from networkx.algorithms import bipartite
import networkx as nx
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from django.http import HttpResponse
from bisect import bisect_left, bisect_right
from .tasks import match_many_to_many_task
#from celery.task.control import inspect
from nord_backend.celery import app
from multitenancy.api_utils import _to_bool
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters as drf_filters
from .filters import BankTransactionFilter, TransactionFilter

# Currency ViewSet
class CurrencyViewSet(viewsets.ModelViewSet):
    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer
    
    @action(methods=['post'], detail=False)
    def bulk_create(self, request, *args, **kwargs):
        return generic_bulk_create(self, request.data)

    @action(methods=['put'], detail=False)
    def bulk_update(self, request, *args, **kwargs):
        return generic_bulk_update(self, request.data)

    @action(methods=['delete'], detail=False)
    def bulk_delete(self, request, *args, **kwargs):
        ids = request.data  # Assuming request.data is a list of IDs
        return generic_bulk_delete(self, ids)

# Account ViewSet
class CostCenterViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = CostCenter.objects.all()
    serializer_class = CostCenterSerializer
    
    @action(methods=['post'], detail=False)
    def bulk_create(self, request, *args, **kwargs):
        return generic_bulk_create(self, request.data)

    @action(methods=['put'], detail=False)
    def bulk_update(self, request, *args, **kwargs):
        return generic_bulk_update(self, request.data)

    @action(methods=['delete'], detail=False)
    def bulk_delete(self, request, *args, **kwargs):
        ids = request.data  # Assuming request.data is a list of IDs
        return generic_bulk_delete(self, ids)

# Account ViewSet
class AccountViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    
    @action(methods=['post'], detail=False)
    def bulk_create(self, request, *args, **kwargs):
        return generic_bulk_create(self, request.data)

    @action(methods=['put'], detail=False)
    def bulk_update(self, request, *args, **kwargs):
        return generic_bulk_update(self, request.data)

    @action(methods=['delete'], detail=False)
    def bulk_delete(self, request, *args, **kwargs):
        ids = request.data  # Assuming request.data is a list of IDs
        return generic_bulk_delete(self, ids)

class AccountSummaryView(APIView):
    def get(self, request, *args, **kwargs):
        company_id = request.query_params.get('company_id')
        entity_id = request.query_params.get('entity_id')
        min_depth = int(request.query_params.get('min_depth', 1))
        include_pending = request.query_params.get('include_pending', 'false').lower() == 'true'
        beginning_date = request.query_params.get('beginning_date')
        end_date = request.query_params.get('end_date')

        if not company_id:
            return Response({"error": "Company ID is required"}, status=status.HTTP_400_BAD_REQUEST)

        accounts_with_balances = Account.get_accounts_summary(
            company_id, entity_id, min_depth, include_pending, beginning_date, end_date
        )
        data = [{'account_code': account.account_code, 'balance': balance} for account, balance in accounts_with_balances]
        return Response(data)

# Account ViewSet
class ReconciliationViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Reconciliation.objects.all()
    serializer_class = ReconciliationSerializer
    
    # Bulk operations
    @action(methods=['post'], detail=False)
    def bulk_create(self, request, *args, **kwargs):
        return generic_bulk_create(self, request.data)

    @action(methods=['put'], detail=False)
    def bulk_update(self, request, *args, **kwargs):
        return generic_bulk_update(self, request.data)

    @action(methods=['delete'], detail=False)
    def bulk_delete(self, request, *args, **kwargs):
        #data = request.data
        #bank_filters = data.get("bank_filters", {})
        print(request.data)
        ids = request.data if isinstance(request.data, list) else []
    
        if not ids:
            return Response(
                {'detail': 'Provide a non-empty list of IDs to delete.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return generic_bulk_delete(self, ids)

# Transaction ViewSet
class TransactionViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    #queryset = Transaction.objects.select_related('company').prefetch_related('journal_entries')
    queryset = (
        Transaction.objects
        .select_related('company', 'currency', 'entity')
        .prefetch_related(
            'journal_entries',
            # add more if needed
        )
    )
    
    filter_backends = [DjangoFilterBackend, drf_filters.SearchFilter, drf_filters.OrderingFilter]
    filterset_class = TransactionFilter
    search_fields = ["description", "entity__name", "journal_entries__account__name"]
    ordering_fields = ["date", "amount", "id", "created_at"]
    ordering = ["-date", "-id"]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return TransactionListSerializer
        return TransactionSerializer

    # Bulk operations
    @action(methods=['post'], detail=False)
    def bulk_create(self, request, *args, **kwargs):
        return generic_bulk_create(self, request.data)

    @action(methods=['put'], detail=False)
    def bulk_update(self, request, *args, **kwargs):
        return generic_bulk_update(self, request.data)

    @action(methods=['delete'], detail=False)
    def bulk_delete(self, request, *args, **kwargs):
        ids = request.data
        return generic_bulk_delete(self, ids)

    # Post a transaction
    @action(detail=True, methods=['post'])
    def post(self, request, pk=None):
        transaction = self.get_object()
        try:
            post_transaction(transaction)
            return Response({'status': 'Transaction posted successfully'})
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    # Unpost a transaction
    @action(detail=True, methods=['post'])
    def unpost(self, request, pk=None):
        transaction = self.get_object()
        try:
            unpost_transaction(transaction)
            return Response({'status': 'Transaction unposted successfully'})
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    # Cancel a transaction
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        transaction = self.get_object()
        if transaction.state == 'posted' and not request.user.is_superuser:
            return Response({'error': 'Only superusers can cancel posted transactions'}, status=status.HTTP_403_FORBIDDEN)

        cancel_transaction(transaction)
        return Response({'status': 'Transaction canceled successfully'})

    # Automatically create a balancing journal entry
    @action(detail=True, methods=['post'])
    def create_balancing_entry(self, request, pk=None):
        transaction = self.get_object()
        account_id = request.data.get('account_id')
        if not account_id:
            return Response({'error': 'Account ID is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            balancing_account = Account.objects.get(pk=account_id, company=transaction.company)
        except Account.DoesNotExist:
            return Response({'error': 'Invalid account ID'}, status=status.HTTP_400_BAD_REQUEST)

        journal_entry = create_balancing_journal_entry(transaction, balancing_account)
        if not journal_entry:
            return Response({'message': 'Transaction is already balanced'})

        return Response({'status': 'Balancing journal entry created', 'entry': JournalEntrySerializer(journal_entry).data})

    # Filter transactions by company, status, and balance
    @action(detail=False, methods=['get'])
    def filtered(self, request, tenant_id=None):
        """
        Filters transactions based on query parameters and tenant_id.
        """
        # Extract query parameters
        #company_id = request.query_params.get('company_id')
        status_filter = request.query_params.get('status')
        min_balance = request.query_params.get('min_balance')
        max_balance = request.query_params.get('max_balance')

        # Base queryset
        queryset = self.get_queryset().filter(company__subdomain=tenant_id)  # Use tenant_id here

        # Apply additional filters
        #if company_id:
        #    queryset = queryset.filter(company_id=company_id)
        if status_filter:
            if status_filter != "Todos" and status_filter != "*" and status_filter != "":
                queryset = queryset.filter(state=status_filter)
        if min_balance is not None:
            queryset = queryset.annotate(balance=Sum('journal_entries__debit_amount') - Sum('journal_entries__credit_amount'))
            queryset = queryset.filter(balance__gte=min_balance)
        if max_balance is not None:
            queryset = queryset.annotate(balance=Sum('journal_entries__debit_amount') - Sum('journal_entries__credit_amount'))
            queryset = queryset.filter(balance__lte=max_balance)

        # Serialize and return results
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    

class JournalEntryViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    #queryset = JournalEntry.objects.all()
    queryset = (
        JournalEntry.objects
        .select_related('company', 'account', 'transaction')
        # If you also need cost_center or any other FK, include it too
    )
    serializer_class = JournalEntrySerializer

    # Bulk operations
    @action(methods=['post'], detail=False)
    def bulk_create(self, request, *args, **kwargs):
        return generic_bulk_create(self, request.data)

    @action(methods=['put'], detail=False)
    def bulk_update(self, request, *args, **kwargs):
        return generic_bulk_update(self, request.data)

    @action(methods=['delete'], detail=False)
    def bulk_delete(self, request, *args, **kwargs):
        ids = request.data  # Assuming request.data is a list of IDs
        return generic_bulk_delete(self, ids)

    # Get journal entries by transaction
    @action(detail=False, methods=['get'])
    def by_transaction(self, request):
        transaction_id = request.query_params.get('transaction_id')
        if not transaction_id:
            return Response({'error': 'Transaction ID is required'}, status=status.HTTP_400_BAD_REQUEST)

        journal_entries = self.queryset.filter(transaction_id=transaction_id)
        serializer = self.get_serializer(journal_entries, many=True)
        return Response(serializer.data)

    # Filter journal entries by status or company
    @action(detail=False, methods=['get'])
    def filtered(self, request):
        status_filter = request.query_params.get('status', None)
        company_id = request.query_params.get('tenant_id', None)

        filters = Q()
        if status_filter:
            filters &= Q(state=status_filter)
        if company_id:
            filters &= Q(transaction__company_id=company_id)

        journal_entries = self.queryset.filter(filters)
        serializer = self.get_serializer(journal_entries, many=True)
        return Response(serializer.data)

    
# Rule ViewSet
class RuleViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Rule.objects.all()
    serializer_class = RuleSerializer
    
    @action(methods=['post'], detail=False)
    def bulk_create(self, request, *args, **kwargs):
        return generic_bulk_create(self, request.data)

    @action(methods=['put'], detail=False)
    def bulk_update(self, request, *args, **kwargs):
        return generic_bulk_update(self, request.data)

    @action(methods=['delete'], detail=False)
    def bulk_delete(self, request, *args, **kwargs):
        ids = request.data  # Assuming request.data is a list of IDs
        return generic_bulk_delete(self, ids)
    
# Bank ViewSet
class BankViewSet(viewsets.ModelViewSet):
    queryset = Bank.objects.all()
    serializer_class = BankSerializer
    
    @action(methods=['post'], detail=False)
    def bulk_create(self, request, *args, **kwargs):
        return generic_bulk_create(self, request.data)

    @action(methods=['put'], detail=False)
    def bulk_update(self, request, *args, **kwargs):
        return generic_bulk_update(self, request.data)

    @action(methods=['delete'], detail=False)
    def bulk_delete(self, request, *args, **kwargs):
        ids = request.data  # Assuming request.data is a list of IDs
        return generic_bulk_delete(self, ids)



# BankAccount ViewSet
class BankAccountViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = BankAccount.objects.all()
    serializer_class = BankAccountSerializer
    
    @action(methods=['post'], detail=False)
    def bulk_create(self, request, *args, **kwargs):
        return generic_bulk_create(self, request.data)

    @action(methods=['put'], detail=False)
    def bulk_update(self, request, *args, **kwargs):
        return generic_bulk_update(self, request.data)

    @action(methods=['delete'], detail=False)
    def bulk_delete(self, request, *args, **kwargs):
        ids = request.data  # Assuming request.data is a list of IDs
        return generic_bulk_delete(self, ids)
    
# BankTransaction ViewSet
class BankTransactionViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = BankTransaction.objects.all()
    serializer_class = BankTransactionSerializer
    
    filter_backends = [DjangoFilterBackend, drf_filters.SearchFilter, drf_filters.OrderingFilter]
    filterset_class = BankTransactionFilter
    search_fields = ["description", "reference_number", "bank_account__name", "entity__name"]
    ordering_fields = ["date", "amount", "id", "created_at"]  # ?ordering=-date,amount
    ordering = ["-date", "-id"]
    
    @action(methods=['post'], detail=False)
    def bulk_create(self, request, *args, **kwargs):
        return generic_bulk_create(self, request.data)

    @action(methods=['put'], detail=False)
    def bulk_update(self, request, *args, **kwargs):
        return generic_bulk_update(self, request.data)

    @action(methods=['delete'], detail=False)
    def bulk_delete(self, request, *args, **kwargs):
        ids = request.data  # Assuming request.data is a list of IDs
        return generic_bulk_delete(self, ids)
    
    @action(detail=False, methods=['post'])
    def import_ofx(self, request, *args, **kwargs):
        """
        Accepts a JSON body like:
        {
          "files": [
            { "name": "foo.OFX", "base64Data": "..." },
            { "ofx_text": "OFXHEADER:100\nDATA:OFXSGML\n..." }
          ]
        }

        For each file:
         - Decode
         - Parse
         - Check references
        Returns a combined structure describing each file's parse and missing references
        """
        files_data = request.data.get("files")
        if not files_data or not isinstance(files_data, list):
            return Response({"error": "Please provide 'files' as a list."},
                            status=status.HTTP_400_BAD_REQUEST)

        import_results = []

        # We'll keep track of overall missing references
        # But different files can have different bank_code or account_id
        for idx, file_item in enumerate(files_data):
            # 1) decode
            ofx_content = decode_ofx_content(file_item)
            if not ofx_content:
                import_results.append({
                    "index": idx,
                    "error": "No valid ofx_text or base64Data found.",
                })
                continue

            # 2) parse
            try:
                parsed = parse_ofx_text(ofx_content)
            except Exception as e:
                import_results.append({
                    "index": idx,
                    "error": f"Failed to parse OFX: {str(e)}",
                })
                continue

            bank_code = int(parsed.get("bank_code"))
            account_id = parsed.get("account_id")
            transactions = parsed.get("transactions", [])
            
            
            
            # 3) check references
            missing_bank = None
            missing_bank_account = None

            bank_obj = Bank.objects.filter(bank_code=bank_code).first()
            if bank_obj:
                bank_data = {
                    "result": "Success",
                    "message": "Bank found.",
                    "value": BankSerializer(bank_obj).data
                }
                bank_num = bank_obj.bank_code
            else:
                bank_data = {
                    "result": "Error",
                    "message": f"Bank code '{bank_code}' not found.",
                    "value": bank_code
                }
                bank_num = bank_code

            bank_acct_obj = BankAccount.objects.filter(bank__bank_code=bank_code, account_number=account_id).first()
            if bank_acct_obj:
                account_data = {
                    "result": "Success",
                    "message": "BankAccount found.",
                    "value": BankAccountSerializer(bank_acct_obj).data
                }
                acct_num = bank_acct_obj.account_number
            else:
                account_data = {
                    "result": "Error",
                    "message": f"BankAccount '{account_id}' not found.",
                    "value": account_id
                }
                acct_num = account_id
            
            for tx in transactions:
                raw_date = tx.get("date")
                parsed_date = None
                if raw_date:
                    try:
                        parsed_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
                    except:
                        pass
                # build the fields
                date_str = parsed_date.isoformat() if parsed_date else ""
                amount_val = tx.get("amount", 0.0)
                transaction_type = tx.get("transaction_type", "")
                memo = tx.get("description", "")
                  # from the DB or your code
                
                # 1) Generate the hash
                tx_hash = generate_ofx_transaction_hash(
                    date_str=date_str,
                    amount=amount_val,
                    transaction_type=transaction_type,
                    memo=memo,
                    bank_number=bank_num,
                    account_number=acct_num
                )
                tx['tx_hash'] = tx_hash
                
                existing = BankTransaction.objects.filter(tx_hash=tx_hash).first()
                if existing:
                    tx['status'] = 'duplicate'
                else:
                    tx['status'] = 'pending'
                    
            # Summarize result for this file
            import_results.append({
                "index": idx,
                "filename": file_item.get("name"),
                "bank": bank_data,
                "account": account_data,
                "transactions": transactions
            })

        return Response({"import_results": import_results}, status=status.HTTP_200_OK)
    
   
    
    @action(detail=False, methods=['get'])
    def unreconciled(self, request, tenant_id):
        unreconciled_transactions = BankTransaction.objects.filter(reconciliations__isnull=True)
        serializer = BankTransactionSerializer(unreconciled_transactions, many=True)
        return response.Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def finalize_reconciliation_matches(self, request, tenant_id):
        """
        Endpoint to finalize reconciliations from a list of matches.
    
        Expected JSON payload:
        {
            "matches": [
                {
                    "bank_transaction_ids": [1321, 1322],
                    "journal_entry_ids": [101, 102]
                },
                {
                    "bank_transaction_ids": [1331],
                    "journal_entry_ids": [103]
                }
            ],
            "adjustment_side": "bank",  // "bank", "journal", or "none"
            "reference": "Reconciliation batch 1",
            "notes": "Matched using high confidence scores"
        }
        
        For each match:
          - The system loads the provided bank transactions and journal entries.
          - It computes the difference between the bank total and the journal total.
          - If an adjustment is requested (adjustment_side != "none") and the difference is nonzero,
            an adjustment record is automatically created on the chosen side (bank or journal) so that
            the totals are balanced.
          - The final difference is then evaluated: if zero, status is set to "matched"; otherwise, "pending".
          - The provided reference and notes are stored (with additional matching details appended).
          
        The endpoint returns a list of created reconciliation record IDs.
        """
        data = request.data
        matches = data.get("matches", [])
        adjustment_side = data.get("adjustment_side", "none")  # expected: "bank", "journal", or "none"
        reference = data.get("reference", "")
        notes = data.get("notes", "")
        print(data, matches)
        created_ids = []
        
        with transaction.atomic():
            for match in matches:
                bank_ids = match.get("bank_transaction_ids", [])
                print("bank_ids: ",bank_ids)
                journal_ids = match.get("journal_entry_ids", [])
                print("journal_ids: ", journal_ids)
                if not bank_ids or not journal_ids:
                    continue  # skip if incomplete
                print("passou")
                # Load candidate records
                bank_txs = list(BankTransaction.objects.filter(id__in=bank_ids))
                journal_entries = list(JournalEntry.objects.filter(id__in=journal_ids))
                
                # Compute sums.
                sum_bank = sum(tx.amount for tx in bank_txs)
                print("sum_bank", sum_bank)
                sum_journal = sum(entry.get_effective_amount() for entry in journal_entries)
                print("sum_journal", sum_journal)
                diff = sum_bank - sum_journal
                print("diff", diff)

                adjustment_record = None
                # If adjustment is requested and there's a difference, create an adjustment record.
                if adjustment_side != "none" and diff != 0:
                    if adjustment_side == "bank":
                        # Create an adjustment record on the bank side so that:
                        # new sum_bank = sum_bank + adjustment_amount equals sum_journal.
                        adjustment_amount = sum_journal - sum_bank  # positive if bank needs an increase
                        adjustment_record = BankTransaction.objects.create(
                            company=bank_txs[0].company,
                            entity=bank_txs[0].entity,
                            bank_account=bank_txs[0].bank_account,
                            date=bank_txs[0].date,  # you might also use today's date
                            currency=bank_txs[0].currency,
                            amount=adjustment_amount,
                            description="Adjustment record for reconciliation",
                            #transaction_type="ADJUSTMENT",
                            status="pending",
                            tx_hash=f"adjustment_{bank_txs[0].id}"
                        )
                        bank_txs.append(adjustment_record)
                        sum_bank += adjustment_amount
                    elif adjustment_side == "journal":
                        # Create an adjustment record on the journal side so that:
                        # new sum_journal = sum_journal + adjustment_amount equals sum_bank.
                        adjustment_amount = sum_bank - sum_journal  # positive if journal needs an increase
                        # Determine which field to set based on the sign.
                        debit_amount = adjustment_amount if adjustment_amount > 0 else None
                        credit_amount = -adjustment_amount if adjustment_amount < 0 else None
                        # Use the transaction and other details from the first journal entry.
                        adjustment_record = JournalEntry.objects.create(
                            company=journal_entries[0].company,
                            transaction=journal_entries[0].transaction,
                            entity=journal_entries[0].transaction.entity,
                            account=journal_entries[0].account,
                            cost_center=journal_entries[0].cost_center,
                            debit_amount=debit_amount,
                            credit_amount=credit_amount,
                            state="matched",
                            memo="Adjustment record for reconciliation"
                        )
                        journal_entries.append(adjustment_record)
                        sum_journal += adjustment_amount
                
                # Recompute final difference.
                final_diff = sum_bank - sum_journal
                rec_status = "matched" if final_diff == 0 else "pending"
                
                # Build notes including match details.
                bank_ids_str = ", ".join(str(tx.id) for tx in bank_txs)
                journal_ids_str = ", ".join(str(je.id) for je in journal_entries)
                combined_notes = f"{notes}\nBank IDs: {bank_ids_str}\nJournal IDs: {journal_ids_str}\nDifference: {final_diff}"
                
                # Create the Reconciliation record.
                rec = Reconciliation.objects.create(
                    company=bank_txs[0].company,
                    status=rec_status,
                    reference=reference,
                    notes=combined_notes
                )
                rec.bank_transactions.set(bank_txs)
                rec.journal_entries.set(journal_entries)
                created_ids.append(rec.id)
                print(rec)
        return Response({"reconciliation_ids": created_ids})
    
    
    
    @action(detail=False, methods=['get'])
    def reconciliation_status(self, request, tenant_id=None):
        """
        Poll reconciliation task status/result
        """
        task_id = request.query_params.get("task_id")
        if not task_id:
            return Response({"error": "task_id is required"}, status=400)

        res = AsyncResult(task_id)
        return Response({
            "task_id": task_id,
            "status": res.status,
            "result": res.result if res.ready() else None
        })
    
    
    
class UnreconciledDashboardView(APIView):
    """
    Dashboard endpoint providing aggregated metrics on unreconciled records.
    
    A record is considered unreconciled if it does not have a related Reconciliation
    with status 'matched' or 'approved'.
    
    Returns overall and daily aggregates.
    """
    def get(self, request, tenant_id=None):
        try:
            # --- BANK TRANSACTIONS ---
            # Exclude reconciled records and those with missing dates.
            bank_qs = BankTransaction.objects.exclude(
                reconciliations__status__in=['matched', 'approved']
            ).filter(date__isnull=False).exclude(date='')
            
            if tenant_id:
                bank_qs = bank_qs.filter(company__subdomain=tenant_id)
            
            bank_overall = bank_qs.aggregate(
                count=Count('id'),
                total=Coalesce(Sum('amount'), V(0, output_field=DecimalField()))
            )
            
            bank_daily = bank_qs.annotate(day=TruncDate('date')).values('day').annotate(
                count=Count('id'),
                total=Coalesce(Sum('amount'), V(0, output_field=DecimalField()))
            ).order_by('day')
            
            # --- JOURNAL ENTRIES ---
            journal_qs = JournalEntry.objects.exclude(
                reconciliations__status__in=['matched', 'approved']
            ).filter(transaction__date__isnull=False).exclude(transaction__date='')
            
            if tenant_id:
                journal_qs = journal_qs.filter(transaction__company__subdomain=tenant_id)
            
            journal_overall = journal_qs.aggregate(
                count=Count('id'),
                total=Coalesce(Sum(F('debit_amount') - F('credit_amount')), V(0, output_field=DecimalField()))
            )
            
            journal_daily = journal_qs.annotate(day=TruncDate('transaction__date')).values('day').annotate(
                count=Count('id'),
                total=Coalesce(Sum(F('debit_amount') - F('credit_amount')), V(0, output_field=DecimalField()))
            ).order_by('day')
            
            response_data = {
                "bank_transactions": {
                    "overall": bank_overall,
                    "daily": list(bank_daily)
                },
                "journal_entries": {
                    "overall": journal_overall,
                    "daily": list(journal_daily)
                }
            }
            
            return Response(response_data)
        
        except OperationalError as e:
            return Response({"error": "Database error: " + str(e)}, status=500)
        except Exception as e:
            return Response({"error": str(e)}, status=500)
    
    
class ReconciliationTaskViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = ReconciliationTask.objects.all().order_by("-created_at")
    serializer_class = ReconciliationTaskSerializer

    @action(detail=False, methods=["post"])
    def start(self, request, tenant_id=None):
        """
        Start reconciliation as a background task
        """
        data = request.data
        auto_match_100 = _to_bool(data.get("auto_match_100", False))
        
        # 1. Pre-create DB record with placeholder task_id
        task_obj = ReconciliationTask.objects.create(
            task_id="queued",   # will be updated after Celery fires
            tenant_id=tenant_id,
            parameters=data,
            status="queued"
        )
    
        # 2. Trigger Celery, pass the db_id
        async_result = match_many_to_many_task.delay(task_obj.id, data, tenant_id, auto_match_100)
    
        # 3. Update the DB record with Celery task_id
        task_obj.task_id = async_result.id
        task_obj.save(update_fields=["task_id"])
    
        return Response({
            "message": "Task enqueued",
            "task_id": async_result.id,   # Celery UUID
            "db_id": task_obj.id,         # persistent DB PK
        })

    @action(detail=True, methods=["get"])
    def status(self, request, pk=None, tenant_id=None):
        """
        Get status/result of a task by DB ID
        """
        task = self.get_object()
        serializer = self.get_serializer(task)
        return Response(serializer.data)
    
    @action(detail=False, methods=["get"])
    def queued(self, request, tenant_id=None):
        """
        Returns both:
        1. DB-persisted tasks (filterable by tenant_id, status)
        2. Live Celery queue info (active/reserved/scheduled)
        Filters:
          - ?tenant_id=foo
          - ?last_n=100   (last 100 tasks)
          - ?hours_ago=6  (tasks from the last 6 hours)
        """
        
        tenant_filter = request.query_params.get("tenant_id")
        status_filter = request.query_params.get("status")
        last_n = request.query_params.get("last_n")
        hours_ago = request.query_params.get("hours_ago")
        
        # ---- DB tasks ----
        qs = ReconciliationTask.objects.all().order_by("-created_at")
        if tenant_filter:
            qs = qs.filter(tenant_id=tenant_filter)
        if status_filter:
            qs = qs.filter(status=status_filter)
        
        if hours_ago:
            try:
                raw = str(hours_ago).lower()
                if raw.endswith("d"):
                    hours = int(raw[:-1]) * 24
                elif raw.endswith("h"):
                    hours = int(raw[:-1])
                else:
                    hours = int(raw)  # fallback if pure number
        
                cutoff = timezone.now() - timedelta(hours=hours)
                qs = qs.filter(created_at__gte=cutoff)
            except ValueError:
                pass
    
        if last_n:
            try:
                last_n = int(last_n)
                qs = qs.order_by("-created_at")[:last_n]
            except ValueError:
                pass
    
        
        db_tasks = self.get_serializer(qs, many=True).data

        # ---- Celery live tasks ----
        try:
            i = app.control.inspect()
            live_info = {
                "active": i.active() or {},
                "reserved": i.reserved() or {},
                "scheduled": i.scheduled() or {}
            }
        except Exception as e:
            live_info = {"error": str(e)}

        return Response({
            "db_tasks": db_tasks,
            "celery_live": live_info
        })
    
    @action(detail=False, methods=["get"])
    def task_counts(self, request, tenant_id=None):
        """
        Lightweight endpoint to return counts of tasks by status.
        Filters:
          - ?tenant_id=foo
          - ?last_n=100   (last 100 tasks)
          - ?hours_ago=6  (tasks from the last 6 hours)
        """
        tenant_filter = tenant_id
        last_n = request.query_params.get("last_n")
        hours_ago = request.query_params.get("hours_ago")
    
        qs = ReconciliationTask.objects.all()
    
        if tenant_filter:
            qs = qs.filter(tenant_id=tenant_filter)
    
        if hours_ago:
            try:
                raw = str(hours_ago).lower()
                if raw.endswith("d"):
                    hours = int(raw[:-1]) * 24
                elif raw.endswith("h"):
                    hours = int(raw[:-1])
                else:
                    hours = int(raw)  # fallback if pure number
        
                cutoff = timezone.now() - timedelta(hours=hours)
                qs = qs.filter(created_at__gte=cutoff)
            except ValueError:
                pass
    
        if last_n:
            try:
                last_n = int(last_n)
                qs = qs.order_by("-created_at")[:last_n]
            except ValueError:
                pass
    
        counts = qs.values("status").annotate(total=Count("id"))
        status_map = {row["status"]: row["total"] for row in counts}
    
        return Response({
            "running": status_map.get("running", 0),
            "completed": status_map.get("completed", 0),
            "queued": status_map.get("queued", 0),
            "failed": status_map.get("failed", 0),
        })

class ReconciliationConfigViewSet2(viewsets.ModelViewSet):
    queryset = ReconciliationConfig.objects.all()
    serializer_class = ReconciliationConfigSerializer

    def get_queryset(self):
        user = self.request.user
        company_id = self.request.query_params.get("company_id")

        qs = super().get_queryset()

        return qs.filter(
            models.Q(scope="global") |
            models.Q(scope="company", company_id=company_id) |
            models.Q(scope="user", user=user)
        )

class ReconciliationConfigViewSet(viewsets.ModelViewSet):
    queryset = ReconciliationConfig.objects.all()
    serializer_class = ReconciliationConfigSerializer

    @action(detail=False, methods=["get"])
    def resolved(self, request, *args, **kwargs):
        """
        Return all configs available to the current user:
        - Global
        - Company
        - User
        - Company+User
        """
        user = request.user
        company_id = request.query_params.get("company_id")

        qs = ReconciliationConfig.objects.filter(
            Q(scope="global")
            | Q(scope="company", company_id=company_id)
            | Q(scope="user", user=user)
            | Q(scope="company_user", company_id=company_id, user=user)
        )

        serializer = ResolvedReconciliationConfigSerializer(qs, many=True)
        return Response(serializer.data)


# Transaction Schema Endpoint
@api_view(['GET'])
def transaction_schema(request, tenant_id=None):
    #tenant_id = request.query_params.get('company_id')  # Get the current tenant's company ID
    #if not company_id:
    #    return Response({"error": "company_id is required"}, status=400)

    companies = Company.objects.filter(subdomain=tenant_id).values_list('id', 'name')
    currencies = Currency.objects.all().values_list('code', 'name')

    schema = {
        "type": "object",
        "properties": {
            "company": {
                "type": "string",
                "title": "Company",
                "enum": [company[0] for company in companies],
                "enumNames": [company[1] for company in companies]
            },
            "date": {
                "type": "string",
                "format": "date",
                "title": "Date"
            },
            "description": {
                "type": "string",
                "title": "Description"
            },
            "amount": {
                "type": "number",
                "title": "Amount"
            },
            "currency": {
                "type": "string",
                "title": "Currency",
                "enum": [currency[0] for currency in currencies],
                "enumNames": [currency[1] for currency in currencies]
            },
            "state": {
                "type": "string",
                "title": "State",
                "enum": ["pending", "posted", "canceled"]
            }
        },
        "required": ["company", "date", "amount", "currency", "state"]
    }

    ui_schema = {
        "company": {"ui:widget": "select"},
        "currency": {"ui:widget": "select"},
        "state": {"ui:widget": "radio"}
    }

    return Response({"schema": schema, "uiSchema": ui_schema})

# Journal Entry Schema Endpoint
@api_view(['GET'])
def journal_entry_schema(request, tenant_id=None):
    transactions = Transaction.objects.all().values_list('id', 'description')
    accounts = Account.objects.all().values_list('id', 'name')
    
    schema = {
        "type": "object",
        "properties": {
            "transaction": {
                "type": "string",
                "title": "Transaction",
                "enum": [transaction[0] for transaction in transactions],
                "enumNames": [transaction[1] for transaction in transactions]
            },
            "account": {
                "type": "string",
                "title": "Account",
                "enum": [account[0] for account in accounts],
                "enumNames": [account[1] for account in accounts]
            },
            "debit_amount": {
                "type": "number",
                "title": "Debit Amount"
            },
            "credit_amount": {
                "type": "number",
                "title": "Credit Amount"
            },
            "state": {
                "type": "string",
                "title": "State",
                "enum": ["pending", "posted", "canceled"]
            }
        },
        "required": ["transaction", "account"]
    }
    
    ui_schema = {
        "transaction": {
            "ui:widget": "select"
        },
        "account": {
            "ui:widget": "select"
        },
        "state": {
            "ui:widget": "select"
        }
    }
    
    return Response({"schema": schema, "uiSchema": ui_schema})
