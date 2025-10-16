# NORD/accounting/serializers.py

from rest_framework import serializers
from .models import (Currency, Account, Transaction, JournalEntry, ReconciliationTask, Rule, Bank, BankAccount, BankTransaction, Reconciliation, CostCenter, ReconciliationConfig)
from multitenancy.serializers import CompanySerializer, EntitySerializer, FlexibleRelatedField
from multitenancy.serializers import CompanyMiniSerializer, EntityMiniSerializer
from django.core.exceptions import ObjectDoesNotExist


class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = '__all__'

class CurrencyMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = ['id', 'code', 'name']

class BankSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bank
        fields = '__all__'

class BankMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bank
        fields = ['id', 'name', 'bank_code']

class BankAccountSerializer(serializers.ModelSerializer):
    company = FlexibleRelatedField(
        serializer_class=CompanyMiniSerializer,
        unique_field='name'
    )
    entity = FlexibleRelatedField(
        serializer_class=EntityMiniSerializer,
        unique_field=['name']
    )
    bank = FlexibleRelatedField(
        serializer_class=BankMiniSerializer,
        unique_field=['name', 'bank_code']
    )
    currency = FlexibleRelatedField(
        serializer_class=CurrencyMiniSerializer,
        unique_field=['name', 'code']
    )
    
    current_balance = serializers.SerializerMethodField()  # <-- NEW FIELD
    
    class Meta:
        model = BankAccount
        fields = '__all__'
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['current_balance'] = self.get_current_balance(instance)
        return data
    
    def get_current_balance(self, obj):
        return obj.get_current_balance()  


class AccountSerializer(serializers.ModelSerializer):
    parent_id = serializers.IntegerField(source='parent.id', read_only=True)
    level = serializers.SerializerMethodField()
    path = serializers.SerializerMethodField()
    path_ids = serializers.SerializerMethodField()
    
    parent = serializers.PrimaryKeyRelatedField(
    queryset=Account.objects.all(),
    required=False,
    allow_null=True
)
    
    company = FlexibleRelatedField(
        serializer_class=CompanyMiniSerializer,
        unique_field='name'
    )
    currency = FlexibleRelatedField(
        serializer_class=CurrencyMiniSerializer,
        unique_field='code'
    )
    bank_account = FlexibleRelatedField(
        serializer_class=BankAccountSerializer,
        unique_field='name',
        allow_null=True,
        required=False
    )
    current_balance = serializers.SerializerMethodField()  # <-- NEW FIELD
    
    class Meta:
        model = Account
        fields = ['id', 'name', 'company', 'parent','parent_id', 'level', 'path', 'path_ids',
                  'account_code','description', 'key_words', 'examples', 'bank_account',
                  'account_direction', 'balance_date',
            'balance', 'currency', 'is_active', 'current_balance'
        ]
        
        
        
    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['current_balance'] = self.get_current_balance(instance)
        return data

    def get_current_balance(self, obj):
        return obj.get_current_balance()    


    def get_level(self, obj):
        """Calculate the level of the entity in the tree."""
        level = 0
        while obj.parent is not None:
            level += 1
            obj = obj.parent
        return level

    def get_path(self, obj):
        """Use the get_path method from the Entity model."""
        return obj.get_path()
    
    def get_path_ids(self, obj):
        """Retrieve the path IDs using the Entity's get_path method."""
        return obj.get_path_ids()

    


class CostCenterSerializer(serializers.ModelSerializer):
    current_balance = serializers.SerializerMethodField()  # <-- NEW FIELD
    
    class Meta:
        model = CostCenter
        fields = '__all__'
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['current_balance'] = self.get_current_balance(instance)
        return data
    
    def get_current_balance(self, obj):
        return obj.get_current_balance()  

class JournalEntrySerializer(serializers.ModelSerializer):
    company = FlexibleRelatedField(
        serializer_class=CompanySerializer,
        unique_field='name'
    )
    
    account = FlexibleRelatedField(
        serializer_class=AccountSerializer,
        unique_field='account_code'
    )
    
    bank_designation_pending = serializers.BooleanField(required=False)
    has_designated_bank = serializers.SerializerMethodField()
    
    #entity = EntitySerializer()
    #account = AccountSerializer()
    
    def get_has_designated_bank(self, obj):
        return obj.has_designated_bank

    def validate(self, attrs):
        # Enforce: if not pending, account is required
        pending = attrs.get("bank_designation_pending", getattr(self.instance, "bank_designation_pending", False))
        if not pending and not (attrs.get("account") or getattr(self.instance, "account_id", None)):
            raise serializers.ValidationError("account is required when bank_designation_pending is False.")
        return attrs
    
    class Meta:
        model = JournalEntry
        fields = [
            "id", "transaction", "account", "cost_center",
            "debit_amount", "credit_amount",
            "state", "date",
            "bank_designation_pending", "has_designated_bank",
        ]

class TransactionListSerializer(serializers.ModelSerializer):
    company = serializers.PrimaryKeyRelatedField(read_only=True)
    currency = serializers.PrimaryKeyRelatedField(read_only=True)
    journal_entries_count = serializers.SerializerMethodField()
    balance = serializers.SerializerMethodField()
    journal_entries_summary = serializers.SerializerMethodField()
    journal_entries_bank_accounts = serializers.SerializerMethodField()
    reconciliation_status = serializers.SerializerMethodField()
    entity = serializers.PrimaryKeyRelatedField(read_only=True)
    bank_date = serializers.SerializerMethodField()
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'company', 'entity', 'currency', 'date', 'bank_date', 'description', 'amount', 'state',
            'journal_entries_count', 'balance', 'journal_entries_summary',
            'journal_entries_bank_accounts', 'reconciliation_status'
        ]

    def get_journal_entries_count(self, obj):
        return obj.journal_entries.count()

    def get_balance(self, obj):
        """
        Returns the net balance of the transaction:
        sum of all debit_amounts - sum of all credit_amounts
        """
        debit_sum = sum((je.debit_amount or 0) for je in obj.journal_entries.all())
        credit_sum = sum((je.credit_amount or 0) for je in obj.journal_entries.all())
        return float(debit_sum - credit_sum)

    def get_journal_entries_summary(self, obj):
        """
        Returns a single-line summary for each journal entry.
        Example output for each entry: "Acct:1000, D=500.00, C=0.00"
        """
        lines = []
        for je in obj.journal_entries.all():
            # Adjust the format as needed for your use case
            account_code = je.account.account_code if je.account else 'N/A'
            account_name = je.account.name if je.account else 'N/A'
            direction = 'DEBIT ' if je.debit_amount else 'CREDIT'
            debit = je.debit_amount or 0
            credit = je.credit_amount or 0
            amount = debit+credit
            lines.append(f"{direction} {amount} - ({account_code}) {account_name}")
        # Join each entry's summary with a pipe or comma or newline
        return lines #"\n".join(lines)
    
    def get_bank_date(self, obj):
        """
        Returns a single-line summary for each journal entry.
        Example output for each entry: "Acct:1000, D=500.00, C=0.00"
        """
        bank_date = "1900-01-01"
        lines = []
        for je in obj.journal_entries.all():
            if je.account and je.account.bank_account:
                bank_date = je.date
            
        # Join each entry's summary with a pipe or comma or newline
        return bank_date #"\n".join(lines)
    
    def get_journal_entries_bank_accounts(self, obj):
        """
        Returns a distinct list of bank account IDs that are linked to
        the accounts of this transaction's journal entries.
        """
        bank_account_ids = []
        for je in obj.journal_entries.all():
            if je.account and je.account.bank_account:
                bank_account_ids.append(je.account.bank_account.id)
        # Return only distinct IDs
        return list(set(bank_account_ids))
    
    def get_reconciliation_status(self, obj):
        # Consider only journal entries that have an account with a linked bank account.
        relevant_entries = [je for je in obj.journal_entries.all() if je.account and je.account.bank_account]
        if not relevant_entries:
            return 'pending'
        # A journal entry is considered reconciled if any related Reconciliation has status 'matched' or 'approved'.
        def is_reconciled(je):
            return any(rec.status in ['matched', 'approved'] for rec in je.reconciliations.all())
        statuses = [is_reconciled(je) for je in relevant_entries]
        if all(statuses):
            return 'matched'
        elif not any(statuses):
            return 'pending'
        else:
            return 'mixed'
    
class TransactionSerializer(serializers.ModelSerializer):
    
    company = FlexibleRelatedField(
        serializer_class=CompanySerializer,
        unique_field='name'
    )
    currency = FlexibleRelatedField(
        serializer_class=CurrencySerializer,
        unique_field=['name', 'code']
    )
    journal_entries = JournalEntrySerializer(many=True, read_only=True)

    class Meta:
        model = Transaction
        fields = '__all__'  # Or list specific fields along with 'journal_entries'

class RuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rule
        fields = '__all__'


    


class BankTransactionSerializer(serializers.ModelSerializer):
    reconciliation_status = serializers.SerializerMethodField()
    entity = serializers.IntegerField(source='bank_account.entity_id', read_only=True)
    entity_name = serializers.CharField(source='bank_account.entity.name', read_only=True)

    class Meta:
        model = BankTransaction
        fields = [
            'id', 'company', 'bank_account', 'entity', 'entity_name', 'currency', 'date', 
            'description', 'amount', 'status', #'transaction_type',
            'is_deleted', 'updated_at', 'updated_by', 'reconciliation_status'
        ]
        extra_kwargs = {
            "bank_account": {"queryset": BankAccount.objects.all()},
        }
        
    
    def create(self, validated_data):
        # In case clients still send 'entity', ignore it
        validated_data.pop("entity", None)
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        validated_data.pop("entity", None)
        return super().update(instance, validated_data)
    
    def get_reconciliation_status(self, obj):
        # Get all reconciliations for this bank transaction.
        qs = obj.reconciliations.all()
        if not qs.exists():
            return 'pending'
        statuses = [rec.status for rec in qs]
        if all(status in ['matched', 'approved'] for status in statuses):
            return 'matched'
        elif all(status not in ['matched', 'approved'] for status in statuses):
            return 'pending'
        else:
            return 'mixed'

class ReconciliationTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReconciliationTask
        fields = "__all__"

class ReconciliationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reconciliation
        fields = '__all__'

class ReconciliationConfigSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(
        source="company.name", read_only=True
    )
    user_name = serializers.CharField(
        source="user.username", read_only=True
    )

    class Meta:
        model = ReconciliationConfig
        fields = [
            "id",
            "scope",
            "company",
            "company_name",
            "user",
            "user_name",
            "name",
            "description",
            "bank_filters",
            "book_filters",
            "strategy",
            "max_group_size",
            "amount_tolerance",
            "date_tolerance_days",
            "min_confidence",
            "max_suggestions",
            "is_default",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        scope = attrs.get("scope") or getattr(self.instance, "scope", None)

        if scope == "company" and not attrs.get("company") and not getattr(self.instance, "company", None):
            raise serializers.ValidationError("Company is required when scope is 'company'.")
        if scope == "user" and not attrs.get("user") and not getattr(self.instance, "user", None):
            raise serializers.ValidationError("User is required when scope is 'user'.")

        return attrs

class ResolvedReconciliationConfigSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)
    user_name = serializers.CharField(source="user.username", read_only=True)
    scope_label = serializers.SerializerMethodField()

    class Meta:
        model = ReconciliationConfig
        fields = [
            "id",
            "scope",
            "scope_label",
            "company",
            "company_name",
            "user",
            "user_name",
            "name",
            "description",
            "bank_filters",
            "book_filters",
            "strategy",
            "max_group_size",
            "amount_tolerance",
            "date_tolerance_days",
            "min_confidence",
            "max_suggestions",
            "is_default",
            "created_at",
            "updated_at",
        ]

    def get_scope_label(self, obj):
        if obj.scope == "global":
            return "Global Shortcut"
        if obj.scope == "company" and obj.company:
            return f"Company Shortcut ({obj.company.name})"
        if obj.scope == "user" and obj.user:
            return f"User Shortcut ({obj.user.username})"
        if obj.scope == "company_user" and obj.company and obj.user:
            return f"Company+User Shortcut ({obj.company.name} | {obj.user.username})"
        return obj.scope
    
class StartEmbeddingBackfillSerializer(serializers.Serializer):
    per_model_limit = serializers.IntegerField(required=False, min_value=1)
    sync = serializers.BooleanField(required=False, default=False)


class TaskIdSerializer(serializers.Serializer):
    task_id = serializers.CharField()


class TaskStatusSerializer(serializers.Serializer):
    task_id = serializers.CharField()
    state = serializers.CharField()
    ready = serializers.BooleanField()
    successful = serializers.BooleanField()
    result = serializers.JSONField(required=False, allow_null=True)
    error = serializers.CharField(required=False, allow_blank=True)
    
class EmbedTestSerializer(serializers.Serializer):
    texts = serializers.ListField(
        child=serializers.CharField(allow_blank=True, allow_null=True),
        required=True
    )
    base_url = serializers.URLField(required=False)
    path = serializers.CharField(required=False, default="/api/embeddings")
    model = serializers.CharField(required=False, default="embeddinggemma:300m")
    timeout_s = serializers.FloatField(required=False, default=20.0)
    dim = serializers.IntegerField(required=False, default=768)
    api_key = serializers.CharField(required=False, allow_blank=True, allow_null=True)

class BackfillSerializer(serializers.Serializer):
    per_model_limit = serializers.IntegerField(required=False, min_value=1)
    base_url = serializers.URLField(required=False)
    path = serializers.CharField(required=False, default="/api/embeddings")
    model = serializers.CharField(required=False, default="embeddinggemma:300m")
    timeout_s = serializers.FloatField(required=False, default=20.0)
    dim = serializers.IntegerField(required=False, default=768)
    api_key = serializers.CharField(required=False, allow_blank=True, allow_null=True)