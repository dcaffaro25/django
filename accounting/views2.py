from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from .models import Currency, Account, Transaction, JournalEntry, Rule, Bank, BankAccount, BankTransaction, Reconciliation
from .serializers import (CurrencySerializer, AccountSerializer, TransactionSerializer,
                          JournalEntrySerializer, RuleSerializer, BankSerializer, 
                          BankAccountSerializer, BankTransactionSerializer, ReconciliationSerializer)

# Currency ViewSet
class CurrencyViewSet(viewsets.ModelViewSet):
    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer

# Account ViewSet
class AccountViewSet(viewsets.ModelViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer

# Transaction ViewSet
class TransactionViewSet(viewsets.ModelViewSet):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer

# JournalEntry ViewSet
class JournalEntryViewSet(viewsets.ModelViewSet):
    queryset = JournalEntry.objects.all()
    serializer_class = JournalEntrySerializer

# Rule ViewSet
class RuleViewSet(viewsets.ModelViewSet):
    queryset = Rule.objects.all()
    serializer_class = RuleSerializer

# Bank ViewSet
class BankViewSet(viewsets.ModelViewSet):
    queryset = Bank.objects.all()
    serializer_class = BankSerializer

# BankAccount ViewSet
class BankAccountViewSet(viewsets.ModelViewSet):
    queryset = BankAccount.objects.all()
    serializer_class = BankAccountSerializer

# BankTransaction ViewSet
class BankTransactionViewSet(viewsets.ModelViewSet):
    queryset = BankTransaction.objects.all()
    serializer_class = BankTransactionSerializer

    # Custom action for getting matching journal entries
    @action(detail=True, methods=['get'])
    def match_journal_entries(self, request, pk=None):
        bank_transaction = self.get_object()
        matches = self.get_matching_journal_entries(bank_transaction)  # Implement this method
        return Response(JournalEntrySerializer(matches, many=True).data)

    # Custom action for getting many-to-many matches
    @action(detail=True, methods=['get'])
    def match_many_journal_entries(self, request, pk=None):
        bank_transaction = self.get_object()
        matches = self.get_many_to_many_matches(bank_transaction)  # Implement this method
        return Response(JournalEntrySerializer(matches, many=True).data)

    # Implement the get_matching_journal_entries and get_many_to_many_matches methods
    # ...

# Reconciliation ViewSet
class ReconciliationViewSet(viewsets.ModelViewSet):
    queryset = Reconciliation.objects.all()
    serializer_class = ReconciliationSerializer

# ... Implement any additional custom methods or logic as needed ...
