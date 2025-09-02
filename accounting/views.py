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

    
    @action(detail=False, methods=['post'])
    def bulk_import(self, request, *args, **kwargs):
        """
        Expects a multipart/form-data request with an Excel file.
        The Excel file must contain two sheets:

        1. "transactions" with the following columns:
           - external_id
           - transaction_date (YYYY-MM-DD)
           - description
           - amount
           - currency_code

        2. "journal_entries" with the following columns:
           - transaction_external_id (must match external_id in the transactions sheet)
           - journal_entity_id
           - journal_account_id
           - journal_cost_center_id (optional)
           - debit_amount (optional)
           - credit_amount (optional)

        All new records will be created with state 'pending'. No constraint on having at least 2 journal entries is enforced.
        """
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({"error": "No file uploaded."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Read all sheets from the Excel file
            sheets = pd.read_excel(file_obj, sheet_name=None)
            if 'transactions' not in sheets or 'journal_entries' not in sheets:
                return Response({"error": "Excel file must contain sheets 'transactions' and 'journal_entries'."}, status=status.HTTP_400_BAD_REQUEST)
            df_transactions = sheets['transactions']
            df_journal_entries = sheets['journal_entries']
        except Exception as e:
            return Response({"error": "Error reading Excel file: " + str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        created_transaction_ids = []
        created_journal_entries = []
        errors = []
        transaction_map = {}  # Maps external_id (as integer) to created Transaction instance
        old_raw_company_id='0'
        
        with transaction.atomic():
            # Process transactions sheet
            for index, row in df_transactions.iterrows():
                try:
                    raw_external_id = row.get('external_id')
                    if pd.isna(raw_external_id):
                        errors.append(f"Transactions sheet, row {index}: Missing external_id.")
                        continue
                    # Convert external_id to integer to normalize the key
                    external_id = int(raw_external_id)
                    
                    
                    raw_company_id = row.get('company_id')
                    if pd.isna(raw_company_id):
                        errors.append(f"Transactions sheet, row {index}: Missing external_id.")
                        continue
                    # Convert external_id to integer to normalize the key
                    if raw_company_id != old_raw_company_id:
                        company_id = int(raw_company_id)
                        company_obj = Company.objects.filter(id=company_id).first()
                        old_raw_company_id = raw_company_id
                    
                    
                    transaction_date = row.get('transaction_date')
                    description = row.get('description')
                    amount = row.get('amount')
                    currency_code = row.get('currency_code')
                    
                    # Validate required fields
                    if pd.isna(transaction_date) or pd.isna(description) or pd.isna(amount) or pd.isna(currency_code):
                        errors.append(f"Transactions sheet, row {index}: Missing required field.")
                        continue
                    
                    currency = Currency.objects.filter(code=currency_code).first()
                    if not currency:
                        errors.append(f"Transactions sheet, row {index}: Currency with code '{currency_code}' not found.")
                        continue
                    
                    # Create the Transaction with state 'pending'
                    trans = Transaction.objects.create(
                        company=company_obj,
                        date=transaction_date,
                        description=description,
                        amount=amount,
                        currency=currency,
                        state='pending'
                    )
                    transaction_map[external_id] = trans
                    created_transaction_ids.append(trans.id)
                except Exception as e:
                    errors.append(f"Transactions sheet, row {index}: {str(e)}")
            
            # Process journal_entries sheet
            for index, row in df_journal_entries.iterrows():
                try:
                    raw_trans_external_id = row.get('transaction_external_id')
                    if pd.isna(raw_trans_external_id):
                        errors.append(f"Journal entries sheet, row {index}: Missing transaction_external_id.")
                        continue
                    # Convert transaction_external_id to integer
                    trans_external_id = int(raw_trans_external_id)
                    
                    #journal_entity_id = row.get('journal_entity_id')
                    journal_account_id = row.get('journal_account_id')
                    journal_cost_center_id = row.get('journal_cost_center_id')
                    debit_amount = row.get('debit_amount')
                    credit_amount = row.get('credit_amount')
                    
                    
                    
                    #if pd.isna(journal_entity_id) or pd.isna(journal_account_id):
                    #    errors.append(f"Journal entries sheet, row {index}: Missing required field (journal_entity_id or journal_account_id).")
                    #    continue
                    
                    # Lookup the matching transaction using integer keys
                    trans = transaction_map.get(trans_external_id)
                    if not trans:
                        errors.append(f"Journal entries sheet, row {index}: No matching transaction found for external_id '{trans_external_id}'.")
                        continue
                    
                    #try:
                    #    entity = Entity.objects.get(pk=int(journal_entity_id))
                    #except Entity.DoesNotExist:
                    #    errors.append(f"Journal entries sheet, row {index}: Entity with ID {journal_entity_id} not found.")
                    #    continue
                    
                    try:
                        account = Account.objects.get(pk=int(journal_account_id))
                    except Account.DoesNotExist:
                        errors.append(f"Journal entries sheet, row {index}: Account with ID {journal_account_id} not found.")
                        continue
                    
                    cost_center = None
                    if pd.notna(journal_cost_center_id):
                        try:
                            cost_center = CostCenter.objects.get(pk=int(journal_cost_center_id))
                        except CostCenter.DoesNotExist:
                            errors.append(f"Journal entries sheet, row {index}: Cost center with ID {journal_cost_center_id} not found.")
                    
                    # Create the JournalEntry with state 'pending'
                    je = JournalEntry.objects.create(
                        company=company_obj,
                        transaction=trans,
                        account=account,
                        cost_center=cost_center,
                        debit_amount=debit_amount if pd.notna(debit_amount) else None,
                        credit_amount=credit_amount if pd.notna(credit_amount) else None,
                        state='pending'
                    )
                    created_journal_entries.append(je.id)
                except Exception as e:
                    errors.append(f"Journal entries sheet, row {index}: {str(e)}")
        
        response_status = status.HTTP_201_CREATED if not errors else status.HTTP_400_BAD_REQUEST
        return Response({
            "created_transactions": created_transaction_ids,
            "created_journal_entries": created_journal_entries,
            "errors": errors
        }, status=response_status)

    @action(detail=False, methods=['get'])
    def download_import_template(self, request, tenant_id=None):
        wb = Workbook()
        
        # --- Sheet 1: transactions ---
        ws1 = wb.active
        ws1.title = "transactions"
        ws1.append(["external_id", "company_id", "transaction_date", "description", "amount", "currency_code"])
    
        # --- Sheet 2: journal_entries ---
        ws2 = wb.create_sheet("journal_entries")
        ws2.append([
            "transaction_external_id", "journal_account_id",
            "journal_cost_center_id", "debit_amount", "credit_amount"
        ])
    
        # --- Sheet 3: auxiliar ---
        ws3 = wb.create_sheet("auxiliar")
    
        # Load data for FK tables
        from accounting.models import Account, CostCenter, Currency
        from multitenancy.models import Company, Entity
    
        company_data = list(Company.objects.values("id", "name"))    
        entity_data = list(Entity.objects.values("id", "company__id", "name"))
        account_data = list(Account.objects.values("id", "company__id", "name", "account_code"))
        cost_center_data = list(CostCenter.objects.values("id", "company__id", "name"))
        currency_data = list(Currency.objects.values("id", "code"))
    
        # Write side-by-side in "auxiliar"
        max_len = max(len(company_data), len(entity_data), len(account_data), len(cost_center_data), len(currency_data))
        ws3.append(["Companies", "", "", "Entities", "", "", "", "Accounts", "", "","", "", "Cost Centers", "", "", "", "Currencies"])
        ws3.append(["ID", "Name",    "", "ID", "Company_id", "Name", "", "ID", "Company_id", "Name", "Code", "", "ID", "Company_id", "Name", "", "ID", "Code"])
    
        for i in range(max_len):
            row = []
            row += [company_data[i]["id"], company_data[i]["name"]] if i < len(company_data) else ["", ""]
            row += [""]  # spacing
            row += [entity_data[i]["id"], entity_data[i]["company__id"], entity_data[i]["name"]] if i < len(entity_data) else ["", "", ""]
            row += [""]  # spacing
            row += [account_data[i]["id"], account_data[i]["company__id"], account_data[i]["name"], account_data[i]["account_code"]] if i < len(account_data) else ["", "", "", ""]
            row += [""]  # spacing
            row += [cost_center_data[i]["id"], cost_center_data[i]["company__id"], cost_center_data[i]["name"]] if i < len(cost_center_data) else ["", "", ""]
            row += [""]  # spacing
            row += [currency_data[i]["id"], currency_data[i]["code"]] if i < len(currency_data) else ["", ""]
            ws3.append(row)
    
        # Serve the Excel file as response
        from io import BytesIO
        output = BytesIO()
        wb.save(output)
        output.seek(0)
    
        response = HttpResponse(output, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename=bulk_import_template.xlsx'
        return response

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
    
    @action(detail=False, methods=['post'])
    def finalize_ofx_import2(self, request, *args, **kwargs):
        """
        Expects JSON like:
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
        # Check if request.data is a dict with a "files" key or a list directly.
        if isinstance(request.data, list):
            files_data = request.data
        elif isinstance(request.data, dict):
            files_data = request.data.get("files")
        else:
            files_data = None
    
        if not files_data or not isinstance(files_data, list):
            return Response({"error": "Please provide 'files' as a list."},
                            status=status.HTTP_400_BAD_REQUEST)
    
        import_results = []
    
        # Process each file
        for idx, file_item in enumerate(files_data):
            # 1) Decode
            ofx_content = decode_ofx_content(file_item)
            #print(ofx_content)
            if not ofx_content:
                import_results.append({
                    "index": idx,
                    "error": "No valid ofx_text or base64Data found.",
                })
                continue
    
            # 2) Parse
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
    
            # 3) Check references for bank and account
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
    
            created_overall = []
            errors = []
            
            try:
                with transaction.atomic():
                    for tx in transactions:
                        raw_date = tx.get("date")
                        parsed_date = None
                        if raw_date:
                            try:
                                parsed_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
                            except Exception as e:
                                pass
                        date_str = parsed_date.isoformat() if parsed_date else ""
                        
                        # Retrieve raw amount as a string, expecting it to preserve decimals.
                        raw_amount = tx.get("amount", "0.0")
                        #print(tx)
                        #print("Finalizing, raw amount:", raw_amount, type(raw_amount))
                        amount_val = raw_amount#Decimal(raw_amount)
                        #print("Converted Decimal:", amount_val, type(amount_val))
                        
                        transaction_type = tx.get("transaction_type", "")
                        memo = tx.get("memo", "")
                        bank_num = bank_obj.bank_code  # using bank_obj for consistency
                        acct_num = bank_acct_obj.account_number
    
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
    
                        # 2) Check for duplicate
                        existing = BankTransaction.objects.filter(tx_hash=tx_hash).first()
                        if existing:
                            continue
    
                        print('Finalizing, amount:', amount_val)
                        
                        # 3) Create new transaction
                        new_tx = BankTransaction.objects.create(
                            company=bank_acct_obj.company,
                            entity=bank_acct_obj.entity,
                            bank_account=bank_acct_obj,
                            date=parsed_date,
                            amount=amount_val,
                            description=memo[:255],
                            currency=bank_acct_obj.currency,
                            transaction_type=transaction_type,
                            memo=memo,
                            status='pending',
                            tx_hash=tx_hash
                        )
                        created_overall.append(new_tx.id)
                        
            except Exception as e:
                return Response({
                    "created": created_overall,
                    "errors": errors,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST)
    
            import_results.append({
                "index": idx,
                "count": len(created_overall),
                "transaction_ids": created_overall
            })
    
        return Response({
            "import_results": import_results
        }, status=status.HTTP_201_CREATED)

    
    @action(detail=False, methods=['post'])
    def finalize_ofx_import(self, request, *args, **kwargs):
        """
        Expects JSON like:
        {
          "import_results": [
            {
              "index": 0,
              "bank_code": "0237",
              "account_id": "1084/1448",
              "transactions": [ ... ]
            },
            ...
          ]
        }
        """
        data = request.data
        if isinstance(data, list):
            results = data  # If the data is already a list, use it directly.
        elif isinstance(data, dict):
            results = data.get("import_results")
        else:
            results = None
    
        if not results or not isinstance(results, list):
            return Response({"error": "Please provide 'import_results' as a list."},
                            status=status.HTTP_400_BAD_REQUEST)
        
        #results = request.data.get("import_results")

    
        created_overall = []
        errors = []
        
        # Wrap everything in an atomic block so that if one item fails, all are rolled back.
        try:
            with transaction.atomic():
                for item in results:
                    index = item.get("index")
                    bank = item.get("bank")
                    
                    account = item.get("account")
                    
                    tx_list = item.get("transactions", [])
    
                    if not bank or not account:
                        errors.append({
                            "index": index,
                            "error": "Missing bank_code or account_id"
                        })
                        # Raise an exception to abort the entire transaction.
                        raise Exception(f"Validation error on item index {index}")
                    print('bank:', bank)
                    print('account:', account)
                    bank_code = bank['bank_code']
                    
                    account_id = account['id']
                    
                    # Check references
                    bank = Bank.objects.filter(bank_code=bank_code).first()
                    if not bank:
                        errors.append({
                            "index": index,
                            "error": f"Bank with code={bank_code} not found."
                        })
                        raise Exception(f"Bank not found on item index {index}")
    
                    bank_acct = BankAccount.objects.filter(id=account_id).first()
                    if not bank_acct:
                        errors.append({
                            "index": index,
                            "error": f"BankAccount with account_number={account_id} not found."
                        })
                        raise Exception(f"BankAccount not found on item index {index}")
    
                    file_created_ids = []
                    for tx in tx_list:
                        raw_date = tx.get("date")
                        parsed_date = None
                        if raw_date:
                            try:
                                parsed_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
                            except Exception as e:
                                # You may want to record an error here too.
                                pass
    
                        date_str = parsed_date.isoformat() if parsed_date else ""
                        amount_val = tx.get("amount", 0.0)
                        print(amount_val)
                        transaction_type = tx.get("transaction_type", "")
                        memo = tx.get("memo", "")
                        bank_num = bank.bank_code
                        acct_num = bank_acct.account_number
    
                        # 1) Generate the hash
                        tx_hash = generate_ofx_transaction_hash(
                            date_str=date_str,
                            amount=amount_val,
                            transaction_type=transaction_type,
                            memo=memo,
                            bank_number=bank_num,
                            account_number=acct_num
                        )
    
                        # 2) Check if a record with this hash already exists
                        existing = BankTransaction.objects.filter(tx_hash=tx_hash).first()
                        if existing:
                            # Duplicate found, skip it.
                            continue
                        
                        print('amount', amount_val)
                        
                        # 3) Create new transaction
                        new_tx = BankTransaction.objects.create(
                            company = bank_acct.company,
                            entity=bank_acct.entity,
                            bank_account=bank_acct,
                            date=parsed_date,
                            amount=amount_val,
                            description=memo[:255],
                            currency=bank_acct.currency,
                            transaction_type=transaction_type,
                            memo=memo,
                            status='pending',
                            tx_hash=tx_hash
                        )
                        file_created_ids.append(new_tx.id)
    
                    created_overall.append({
                        "index": index,
                        "count": len(file_created_ids),
                        "transaction_ids": file_created_ids
                    })
    
                # If there are any errors collected, we explicitly fail.
                if errors:
                    raise Exception("Errors occurred during import.")
    
        except Exception as e:
            return Response({
                "created": created_overall,
                "errors": errors,
                "message": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
    
        return Response({
            "created": created_overall,
            "errors": errors
        }, status=status.HTTP_201_CREATED)
    
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
                            transaction_type="ADJUSTMENT",
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
    
    @action(detail=False, methods=['post'])
    def match_many_to_many_with_set2(self, request, tenant_id):
        """
        Instead of running inline, enqueue a Celery job.
        """
        data = request.data
        task = match_many_to_many_task.delay(data, tenant_id)
        
        return Response({
            "message": "Task queued",
            "task_id": task.id,
            "status": task.status
        })
    
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
    
    '''
        bank_filters = data.get("bank_filters", {})
        book_filters = data.get("book_filters", {})
        
        amount_tolerance = Decimal(str(data.get("amount_tolerance", "0")))
        date_tolerance_days = int(data.get("date_tolerance_days", 2))
        max_suggestions = int(data.get("max_suggestions", 5))
        max_group_size = int(data.get("max_group_size", 5))
        
        strategy = data.get("strategy", "Exact 1-to-1")
        
        bank_ids = data.get("bank_ids", [])
        book_ids = data.get("book_ids", [])
        #print("bank_ids.len", len(bank_ids))
        #print("book_ids.len", len(book_ids))
        print("bank_ids.len", bank_ids)
        print("book_ids.len", book_ids)
        candidate_bank = self.queryset.exclude(reconciliations__status__in=['matched', 'approved'])
        if bank_ids:
            candidate_bank = candidate_bank.filter(id__in=bank_ids)
        
        
        candidate_book = JournalEntry.objects.exclude(reconciliations__status__in=['matched', 'approved'])
        
        
        candidate_book = candidate_book.filter(transaction_id__in=book_ids)
        
        
        candidate_book = candidate_book.filter(account__bank_account__isnull=False)
        
        #if bank_filters.get("start_date"):
        #    candidate_bank = candidate_bank.filter(date__gte=bank_filters["start_date"])
        #if bank_filters.get("end_date"):
        #    candidate_bank = candidate_bank.filter(date__lte=bank_filters["end_date"])
    
        #if book_filters.get("start_date"):
        #    candidate_book = candidate_book.filter(transaction__date__gte=book_filters["start_date"])
        #if book_filters.get("end_date"):
        #    candidate_book = candidate_book.filter(transaction__date__lte=book_filters["end_date"])
    
        candidate_bank = list(candidate_bank)
        candidate_book = list(candidate_book)
        print('candidate_book',candidate_book)
        exact_matches = []
        fuzzy_matches = []
        group_matches = []
        
        
        #if strategy == "exact 1-to-1" or strategy == "optimized":
        #    exact_matches, candidate_bank, candidate_book = self.get_exact_matches(candidate_bank, candidate_book)
        
        #if strategy == "fuzzy" or strategy == "optimized":
        #    fuzzy_matches = self.get_fuzzy_matches(candidate_bank, candidate_book, amount_tolerance, date_tolerance_days)
        
        if strategy == "many-to-many" or strategy == "optimized":
            group_matches = self.get_group_matches(candidate_bank, candidate_book, amount_tolerance, date_tolerance_days, max_group_size=max_group_size)
        
            #get_group_matches(banks, books, amount_tolerance, date_tolerance, max_group_size=2, matcher=None, description_threshold=0.5, min_confidence_improvement=0.01):    
        
        combined_suggestions = (exact_matches + fuzzy_matches + group_matches)#[:max_suggestions]
    
        return Response({"suggestions": combined_suggestions})
    
    '''
    
    def get_exact_matches(self, banks, books):
        from collections import defaultdict
        from decimal import Decimal
        
        exact_matches = []
        matched_bank_ids = set()
        matched_book_transaction_ids = set()
        print(banks)
        print(books)
        bank_account_linked_accounts = set(
            Account.objects.filter(bank_account__isnull=False).values_list('id', flat=True)
        )
    
        book_transactions = defaultdict(list)
        for entry in books:
            if entry.account_id in bank_account_linked_accounts:
                book_transactions[entry.transaction.id].append(entry)
    
        for bank_tx in banks:
            for transaction_id, entries in book_transactions.items():
                if transaction_id in matched_book_transaction_ids:
                    continue
    
                transaction_amount = sum(
                    (e.debit_amount or Decimal('0')) - (e.credit_amount or Decimal('0'))
                    for e in entries
                )
    
                if abs(transaction_amount) == abs(bank_tx.amount) and entries[0].transaction.date == bank_tx.date:
                    if (transaction_amount > 0 and bank_tx.amount > 0) or (transaction_amount < 0 and bank_tx.amount < 0):
                        matched_bank_ids.add(bank_tx.id)
                        matched_book_transaction_ids.add(transaction_id)
                        
                        bank_summary = f"ID: {bank_tx.id}, Date: {bank_tx.date}, Amount: {bank_tx.amount}, Desc: {bank_tx.description}"
                        
                        journal_lines = []
                        for entry in [entries[0]]:
                            account_code = entry.account.account_code if entry.account else 'N/A'
                            account_name = entry.account.name if entry.account else 'N/A'
                            direction = 'DEBIT' if entry.debit_amount else 'CREDIT'
                            journal_lines.append(f"ID: {entry.transaction.id}, Date: {entry.date}, JE: {direction} {entry.get_effective_amount()} - ({account_code}) {account_name}, Desc: {entry.transaction.description}")
                        journal_summary = "\n".join(journal_lines)
                        
                        exact_matches.append({
                            "match_type": "1-to-1 Exact",
                            "bank_transaction_details": [{
                                "id": bank_tx.id,
                                "date": bank_tx.date,
                                "amount": bank_tx.amount,
                                "description": bank_tx.description,
                            }],
                            "journal_entry_details": [{
                                "transaction_id": transaction_id,
                                "date": entries[0].date,
                                "amount": transaction_amount,
                                "description": entries[0].transaction.description,
                                "journal_entries": [
                                    {
                                        "id": e.id,
                                        "account": e.account.name,
                                        "debit": e.debit_amount or Decimal('0'),
                                        "credit": e.credit_amount or Decimal('0')
                                    } for e in entries
                                ]
                            }],
                            "bank_ids": [tx.id for tx in [bank_tx]],
                            "journal_entries_ids": [entry.id for entry in [entries[0]]],
                            "sum_bank": bank_tx.amount,
                            "sum_book": transaction_amount,
                            "difference": 0,
                            "avg_date_diff": 0,
                            "confidence_score": 1.0,
                            "bank_transaction_summary": bank_summary,
                            "journal_entries_summary": journal_summary,
                        })

                        
                        break
    
        remaining_bank = [tx for tx in banks if tx.id not in matched_bank_ids]
        remaining_book = [entry for entry in books if entry.transaction.id not in matched_book_transaction_ids]
    
        return exact_matches, remaining_bank, remaining_book
    
    def get_fuzzy_matches(self, banks, books, amount_tolerance, date_tolerance):
        fuzzy_matches = []
    
        for bank_tx, book_tx in product(banks, books):
            amount_diff = abs(bank_tx.amount - book_tx.get_effective_amount())
            date_diff = abs((bank_tx.date - book_tx.transaction.date).days)
    
            if amount_diff <= amount_tolerance and date_diff <= date_tolerance:
                confidence = self.calculate_confidence(amount_diff, date_diff, amount_tolerance, date_tolerance)
                fuzzy_matches.append(self.format_suggestion_output("1-to-1 fuzzy",[bank_tx], [book_tx], confidence))
    
        fuzzy_matches.sort(key=lambda x: x['confidence_score'], reverse=True)
        return fuzzy_matches
    
    def get_group_matches(self, banks, books, amount_tolerance, date_tolerance, max_group_size=2, matcher=None, description_threshold=0.5, min_confidence_improvement=0.01):
        
        print('max_group_size', max_group_size)
        group_matches = []
        seen_matches = set()
        atomic_matches = {}  # (bank_id, book_id): confidence
    
        # Step 1: Preprocess and sort
        banks = sorted(banks, key=lambda x: x.date)
        books = sorted(books, key=lambda x: x.date)
    
        bank_dates = [tx.date for tx in banks]
        book_dates = [tx.date for tx in books]
        #print('dates', bank_dates, book_dates)
        # Step 2: Efficient windowing using bisect
        for i, bank_tx in enumerate(banks):
            start_date = bank_tx.date - timedelta(days=date_tolerance)
            end_date = bank_tx.date + timedelta(days=date_tolerance)
    
            # Get bank group around bank_tx.date
            bank_start = bisect_left(bank_dates, start_date)
            bank_end = bisect_right(bank_dates, end_date)
            bank_group = banks[bank_start:bank_end]
    
            # Get book group in date range
            book_start = bisect_left(book_dates, start_date)
            book_end = bisect_right(book_dates, end_date)
            book_group = books[book_start:book_end]
    
            #if len(bank_group) > 20 or len(book_group) > 20:
            #    continue
    
            for i in range(1, min(len(bank_group), max_group_size) + 1):
                for bank_combo in combinations(bank_group, i):
                    sum_bank = sum(tx.amount for tx in bank_combo)
    
                    for j in range(1, min(len(book_group), max_group_size) + 1):
                        for book_combo in combinations(book_group, j):
                            book_amounts = [
                                e.get_effective_amount()
                                for e in book_combo
                                if e.get_effective_amount() is not None
                            ]
                            #print('book_amounts', book_amounts)
                            if not book_amounts:
                                continue
                            sum_book = sum(book_amounts)
                            amount_diff = abs(sum_bank - sum_book)
                            #print(round(amount_diff, 6), amount_tolerance)
                            if round(amount_diff, 6) > amount_tolerance:
                                continue
                            #if abs(sum_book - sum_bank) > amount_tolerance:
                            #    continue
    
                            dates = [tx.date for tx in bank_combo] + [
                                e.date for e in book_combo
                            ]
                            #print((max(dates) - min(dates)).days, date_tolerance)
                            if (max(dates) - min(dates)).days > date_tolerance:
                                continue
    
                            # Optional: description similarity filtering
                            if matcher:
                                bank_descs = [tx.description for tx in bank_combo]
                                book_descs = [e.transaction.description for e in book_combo]
                                description_score = matcher.score(bank_descs, book_descs)
    
                                if description_score < description_threshold:
                                    continue
    
                            avg_date_diff = sum(
                                abs((tx.date - e.date).days)
                                for tx in bank_combo
                                for e in book_combo
                            ) / (len(bank_combo) * len(book_combo))
    
                            confidence = self.calculate_confidence(
                                amount_diff,
                                avg_date_diff,
                                amount_tolerance,
                                date_tolerance
                            )
    
                            # Check for redundant match using atomic_matches
                            if len(bank_combo) == 1 and len(book_combo) == 1:
                                # Store 1-to-1 match confidence
                                bank_id = bank_combo[0].id
                                book_id = book_combo[0].id
                                atomic_matches[(bank_id, book_id)] = confidence
                            else:
                                # For larger combos, check if all atomic pairs already matched
                                atomic_keys = [
                                    (b.id, e.id)
                                    for b in bank_combo
                                    for e in book_combo
                                ]
                                if all(k in atomic_matches for k in atomic_keys):
                                    avg_atomic_conf = sum(
                                        atomic_matches[k] for k in atomic_keys
                                    ) / len(atomic_keys)
                                    if confidence <= avg_atomic_conf + min_confidence_improvement:
                                        continue  # Skip redundant or inferior m-to-n match
    
                            # Avoid exact duplicates
                            bank_ids = tuple(sorted(tx.id for tx in bank_combo))
                            book_ids = tuple(sorted(e.id for e in book_combo))
                            match_key = (bank_ids, book_ids)
    
                            if match_key in seen_matches:
                                continue
                            seen_matches.add(match_key)
    
                            group_matches.append(
                                self.format_suggestion_output(
                                    "many-to-many",
                                    bank_combo,
                                    book_combo,
                                    confidence
                                )
                            )
        
        # === Add '# dup values' column to all group_matches ===
        value_counts = {}
        for match in group_matches:
            key = (round(match["sum_bank"], 6), round(match["sum_book"], 6))
            value_counts[key] = value_counts.get(key, 0) + 1
        
        for match in group_matches:
            key = (round(match["sum_bank"], 6), round(match["sum_book"], 6))
            match["# dup values"] = value_counts[key] - 1  # exclude self
        group_matches.sort(key=lambda x: x['confidence_score'], reverse=True)
        return group_matches
    
    def get_group_matches2(self, banks, books, amount_tolerance, date_tolerance, max_group_size=2):
        from itertools import combinations
        from collections import defaultdict

        group_matches = []

        bank_buckets = defaultdict(list)
        book_buckets = defaultdict(list)

        for tx in banks:
            bank_buckets[tx.date].append(tx)
        for entry in books:
            book_buckets[entry.transaction.date].append(entry)

        all_bank_dates = list(bank_buckets.keys())
        all_book_dates = list(book_buckets.keys())

        for bank_date in all_bank_dates:
            for book_date in all_book_dates:
                if abs((bank_date - book_date).days) <= date_tolerance:
                    bank_group = bank_buckets[bank_date]
                    book_group = book_buckets[book_date]

                    for i in range(1, min(len(bank_group), max_group_size) + 1):
                        for bank_combo in combinations(bank_group, i):
                            sum_bank = sum(tx.amount for tx in bank_combo)
                            for j in range(1, min(len(book_group), max_group_size) + 1):
                                for book_combo in combinations(book_group, j):
                                    amounts = [e.get_effective_amount() for e in book_combo if e.get_effective_amount() is not None]
                                    if not amounts:
                                        continue
                                    sum_book = sum(amounts)
                                    amount_diff = abs(sum_bank - sum_book)
                                    if amount_diff <= amount_tolerance:
                                        date_diffs = [abs((tx.date - e.transaction.date).days) for tx in bank_combo for e in book_combo]
                                        avg_date_diff = sum(date_diffs) / len(date_diffs) if date_diffs else 0
                                        if avg_date_diff <= date_tolerance:
                                            confidence = self.calculate_confidence(amount_diff, avg_date_diff, amount_tolerance, date_tolerance)
                                            group_matches.append(self.format_suggestion_output("many-to-many",bank_combo, book_combo, confidence))

        group_matches.sort(key=lambda x: x['confidence_score'], reverse=True)
        return group_matches

    
    def calculate_confidence(self, amount_diff, date_diff, amount_tol, date_tol):
        if amount_tol == 0:
            amount_tol = 0.01  # ou algum valor padrão mínimo seguro
        if date_tol == 0:
            date_tol = 1 
        
        amount_score = max(0, 1 - float(amount_diff) / float(amount_tol))
        date_score = max(0, 1 - float(date_diff) / float(date_tol))
        return round(0.7 * amount_score + 0.3 * date_score, 2)
    
    def format_suggestion(self, bank_tx, book_tx, confidence):
        return {
            "bank_transaction": {
                "id": bank_tx.id,
                "date": bank_tx.date,
                "amount": bank_tx.amount,
                "description": bank_tx.description,
            },
            "journal_entry": {
                "id": book_tx.id,
                "date": book_tx.date,
                "amount": book_tx.get_effective_amount(),
                "description": book_tx.transaction.description,
            },
            "difference": abs(bank_tx.amount - book_tx.get_effective_amount()),
            "confidence_score": confidence
        }
    
    def format_suggestion_output(self, match_type, bank_combo, book_combo, confidence_score):
        sum_bank = sum(tx.amount for tx in bank_combo)
        sum_book = sum(entry.get_effective_amount() for entry in book_combo)
        diff = abs(sum_bank - sum_book)
    
        # Média das diferenças de datas entre os pares
        date_diffs = [
            abs((tx.date - entry.date).days)
            for tx in bank_combo
            for entry in book_combo
        ]
        avg_date_diff = sum(date_diffs) / len(date_diffs) if date_diffs else 0
    
        bank_lines = []    
        for tx in bank_combo:
            bank_lines.append(f"ID: {tx.id}, Date: {tx.date}, Amount: {tx.amount}, Desc: {tx.description}")
        bank_summary = "\n".join(bank_lines)
        #bank_summary = f"{[ID: tx.id, Date: tx.date, Amount: tx.amount, Desc: tx.description for tx in bank_combo]}"
        #journal_summary = f"IDs: {[entry.id for entry in book_combo]}, Total: {sum_book:.2f}"
        
        #bank_summary = f"ID: {tx.id}, Date: {tx.date}, Amount: {tx.amount}, Desc: {tx.description}"
        
        journal_lines = []
        for entry in book_combo:
            account_code = entry.account.account_code if entry.account else 'N/A'
            account_name = entry.account.name if entry.account else 'N/A'
            direction = 'DEBIT' if entry.debit_amount else 'CREDIT'
            journal_lines.append(f"ID: {entry.transaction.id}, Date: {entry.date}, JE: {direction} {entry.get_effective_amount()} - ({account_code}) {account_name}, Desc: {entry.transaction.description}")
        journal_summary = "\n".join(journal_lines)
        
        
        return {
            "match_type": match_type,
            "N bank": len(bank_combo),
            "N book": len(book_combo),
            "bank_transaction_details": [{
                "id": tx.id,
                "date": tx.date,
                "amount": tx.amount,
                "description": tx.description,
                "tx_hash": tx.tx_hash,
                "bank_account": {
                    "id": tx.bank_account.id,
                    "name": tx.bank_account.name
                } if tx.bank_account else None,
                "entity": tx.entity.id if tx.entity else None,
                "currency": tx.currency.id
            } for tx in bank_combo],
            "journal_entry_details":[{
                "id": entry.id,
                "date": entry.date,
                "amount": entry.get_effective_amount(),
                "description": entry.transaction.description,
                "account": {
                    "id": entry.account.id,
                    "account_code": entry.account.account_code,
                    "name": entry.account.name
                } if entry.account else None,
                
                "transaction": {
                    "id": entry.transaction.id,
                    "entity": {
                        "id": entry.transaction.entity.id,
                        "name": entry.transaction.entity.name
                    } if entry.transaction.entity else None,
                    "description": entry.transaction.description,
                    "date": entry.transaction.date
                } if entry.transaction else None
            } for entry in book_combo],
            "bank_transaction_summary": bank_summary,
            "journal_entries_summary": journal_summary,
            "bank_ids": [tx.id for tx in bank_combo],
            "journal_entries_ids": [entry.id for entry in book_combo],
            "sum_bank": float(sum_bank),
            "sum_book": float(sum_book),
            "difference": float(diff),
            "avg_date_diff": avg_date_diff,
            "confidence_score": float(confidence_score)
        }
    
    
    
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
    
        # 1. Pre-create DB record with placeholder task_id
        task_obj = ReconciliationTask.objects.create(
            task_id="queued",   # will be updated after Celery fires
            tenant_id=tenant_id,
            parameters=data,
            status="queued"
        )
    
        # 2. Trigger Celery, pass the db_id
        async_result = match_many_to_many_task.delay(task_obj.id, data, tenant_id)
    
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
        """
        tenant_filter = request.query_params.get("tenant_id")
        status_filter = request.query_params.get("status")

        # ---- DB tasks ----
        qs = ReconciliationTask.objects.all().order_by("-created_at")
        if tenant_filter:
            qs = qs.filter(tenant_id=tenant_filter)
        if status_filter:
            qs = qs.filter(status=status_filter)

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
