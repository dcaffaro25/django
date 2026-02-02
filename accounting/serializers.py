# NORD/accounting/serializers.py

from rest_framework import serializers
from .models import (Currency, Account, Transaction, JournalEntry, 
                     ReconciliationTask, Rule, Bank, BankAccount, BankTransaction, 
                     Reconciliation, CostCenter, ReconciliationConfig,
                     ReconciliationPipeline, ReconciliationPipelineStage,
                     ReconciliationRule)
from multitenancy.serializers import CompanySerializer, EntitySerializer, FlexibleRelatedField
from multitenancy.serializers import CompanyMiniSerializer, EntityMiniSerializer
from django.core.exceptions import ObjectDoesNotExist


class EmbeddingSearchSerializer(serializers.Serializer):
    query = serializers.CharField()
    k_each = serializers.IntegerField(default=10, min_value=1, max_value=100)
    company_id = serializers.IntegerField(required=False)
    min_similarity = serializers.FloatField(required=False, min_value=0.0, max_value=1.0)
    model = serializers.CharField(required=False)  # optional override (e.g., "nomic-embed-text")

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
        unique_field='account_code',
        required=False,
        allow_null=True
    )
    
    bank_designation_pending = serializers.BooleanField(required=False)
    has_designated_bank = serializers.SerializerMethodField()
    
    #entity = EntitySerializer()
    #account = AccountSerializer()
    
    def get_has_designated_bank(self, obj):
        return bool(obj.account and getattr(obj.account, 'bank_account_id', None))

    def validate(self, attrs):
        # Enforce: if not pending, account is required
        pending = attrs.get("bank_designation_pending", getattr(self.instance, "bank_designation_pending", False))
        if not pending and not (attrs.get("account") or getattr(self.instance, "account_id", None)):
            raise serializers.ValidationError("account is required when bank_designation_pending is False.")
        return attrs
    
    class Meta:
        model = JournalEntry
        fields = [
            "id", "company", "transaction", "description","account", "cost_center",
            "debit_amount", "credit_amount",
            "state", "date",
            "bank_designation_pending", "has_designated_bank",
            "notes",
        ]

class JournalEntryListSerializer(serializers.ModelSerializer):
    company = serializers.PrimaryKeyRelatedField(read_only=True)
    currency = serializers.PrimaryKeyRelatedField(read_only=True)
    entity = serializers.PrimaryKeyRelatedField(read_only=True)
    # Use regular fields that will read from annotations when available
    balance = serializers.SerializerMethodField()
    transaction_date = serializers.SerializerMethodField()
    transaction_description = serializers.SerializerMethodField()
    transaction_value = serializers.SerializerMethodField()
    bank_account = serializers.SerializerMethodField()
    reconciliation_status = serializers.SerializerMethodField()
    bank_date = serializers.SerializerMethodField()

    class Meta:
        model = JournalEntry
        fields = [
            'id', 'company', 'entity', 'currency', 'description', 'bank_date', 'balance',
            'transaction_date', 'transaction_description', 'transaction_value',
            'bank_account', 'reconciliation_status', 'notes',
        ]

    def to_representation(self, instance):
        """Override to use annotated fields when available."""
        data = super().to_representation(instance)
        
        # Use annotated fields if they exist (from queryset annotations)
        if hasattr(instance, 'transaction_date'):
            data['transaction_date'] = instance.transaction_date
        
        if hasattr(instance, 'transaction_description'):
            data['transaction_description'] = instance.transaction_description
        
        if hasattr(instance, 'transaction_value'):
            # Convert Decimal to float if needed
            value = instance.transaction_value
            data['transaction_value'] = float(value) if value is not None else None
        
        if hasattr(instance, 'bank_account_id'):
            data['bank_account'] = instance.bank_account_id
        
        if hasattr(instance, 'bank_date'):
            data['bank_date'] = instance.bank_date
        
        if hasattr(instance, 'balance'):
            # Convert Decimal to float if needed
            balance = instance.balance
            data['balance'] = float(balance) if balance is not None else None
        
        if hasattr(instance, 'reconciliation_status'):
            data['reconciliation_status'] = instance.reconciliation_status
        
        return data

    def get_transaction_date(self, obj):
        """Returns date from related transaction or annotation."""
        if hasattr(obj, 'transaction_date'):
            return obj.transaction_date
        return obj.transaction.date if obj.transaction else None

    def get_transaction_description(self, obj):
        """Returns description from related transaction or annotation."""
        if hasattr(obj, 'transaction_description'):
            return obj.transaction_description
        return obj.transaction.description if obj.transaction else None

    def get_transaction_value(self, obj):
        """Returns amount from related transaction or annotation."""
        if hasattr(obj, 'transaction_value'):
            value = obj.transaction_value
            return float(value) if value is not None else None
        if obj.transaction and obj.transaction.amount is not None:
            return float(obj.transaction.amount)
        return None

    def get_bank_date(self, obj):
        """Returns the journal date only if linked to a bank account."""
        if hasattr(obj, 'bank_date'):
            return obj.bank_date
        if obj.account and obj.account.bank_account:
            return obj.date
        return None

    def get_bank_account(self, obj):
        """Returns the bank account ID if linked."""
        if hasattr(obj, 'bank_account_id'):
            return obj.bank_account_id
        if obj.account and obj.account.bank_account:
            return obj.account.bank_account.id
        return None

    def get_balance(self, obj):
        """Returns debit - credit as float."""
        if hasattr(obj, 'balance'):
            balance = obj.balance
            return float(balance) if balance is not None else None
        debit = obj.debit_amount or 0
        credit = obj.credit_amount or 0
        return float(debit - credit)

    def get_reconciliation_status(self, obj):
        """Returns reconciliation status based on linked reconciliations or annotation."""
        if hasattr(obj, 'reconciliation_status'):
            return obj.reconciliation_status
        if obj.account and obj.account.bank_account:
            # Use prefetched reconciliations if available
            if hasattr(obj, 'recon_list'):
                if any(rec.status in ["matched", "approved"] for rec in obj.recon_list):
                    return "matched"
            elif obj.reconciliations.filter(status__in=["matched", "approved"]).exists():
                return "matched"
        return "pending"

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
    # New fields for transaction reconciliation page
    bank_recon_status = serializers.SerializerMethodField()
    bank_linked_je_count = serializers.SerializerMethodField()
    bank_reconciled_je_count = serializers.SerializerMethodField()
    is_balanced = serializers.BooleanField(read_only=True)
    total_debit = serializers.SerializerMethodField()
    total_credit = serializers.SerializerMethodField()
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'company', 'entity', 'currency', 'date', 'bank_date', 'description', 'amount', 'state',
            'journal_entries_count', 'balance', 'journal_entries_summary',
            'journal_entries_bank_accounts', 'reconciliation_status', 'notes',
            'is_balanced', 'bank_recon_status', 'bank_linked_je_count', 'bank_reconciled_je_count',
            'total_debit', 'total_credit'
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
    
    def get_bank_recon_status(self, obj):
        """
        Returns the bank reconciliation status:
        - 'matched': All bank-linked JEs have reconciliations with status 'matched' or 'approved'
        - 'pending': Has bank-linked JEs with no reconciliation
        - 'mixed': Some matched, some pending
        - 'na': No bank-linked JEs
        """
        relevant_entries = [je for je in obj.journal_entries.all() if je.account and je.account.bank_account]
        if not relevant_entries:
            return 'na'
        
        def is_reconciled(je):
            return any(rec.status in ['matched', 'approved'] for rec in je.reconciliations.all())
        
        statuses = [is_reconciled(je) for je in relevant_entries]
        if all(statuses):
            return 'matched'
        elif not any(statuses):
            return 'pending'
        else:
            return 'mixed'
    
    def get_bank_linked_je_count(self, obj):
        """Returns the count of journal entries linked to bank accounts."""
        return sum(1 for je in obj.journal_entries.all() if je.account and je.account.bank_account)
    
    def get_bank_reconciled_je_count(self, obj):
        """Returns the count of journal entries that are reconciled (matched/approved)."""
        count = 0
        for je in obj.journal_entries.all():
            if je.account and je.account.bank_account:
                if any(rec.status in ['matched', 'approved'] for rec in je.reconciliations.all()):
                    count += 1
        return count
    
    def get_total_debit(self, obj):
        """Returns total debit amount across all journal entries."""
        return float(sum((je.debit_amount or 0) for je in obj.journal_entries.all()))
    
    def get_total_credit(self, obj):
        """Returns total credit amount across all journal entries."""
        return float(sum((je.credit_amount or 0) for je in obj.journal_entries.all()))
    
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
    # Use annotated field if available, otherwise fall back to method
    reconciliation_status = serializers.CharField(read_only=True, required=False)
    entity = serializers.IntegerField(source='bank_account.entity_id', read_only=True)
    entity_name = serializers.CharField(source='bank_account.entity.name', read_only=True)

    class Meta:
        model = BankTransaction
        fields = [
            'id', 'company', 'bank_account', 'entity', 'entity_name', 'currency', 'date', 
            'description', 'amount', 'status', #'transaction_type',
            'is_deleted', 'updated_at', 'updated_by', 'reconciliation_status', 'notes'
        ]
        extra_kwargs = {
            "bank_account": {"queryset": BankAccount.objects.all()},
        }
    
    def to_representation(self, instance):
        """Override to use annotated field if available, otherwise compute it."""
        data = super().to_representation(instance)
        
        # If reconciliation_status annotation exists, use it (from queryset annotation)
        # Otherwise, compute it the old way (for backward compatibility)
        if hasattr(instance, 'reconciliation_status'):
            # Annotated field is already in data, no need to override
            pass
        else:
            # Fallback: compute reconciliation_status the old way
            qs = instance.reconciliations.all()
            if not qs.exists():
                data['reconciliation_status'] = 'pending'
            else:
                statuses = [rec.status for rec in qs]
                if all(status in ['matched', 'approved'] for status in statuses):
                    data['reconciliation_status'] = 'matched'
                elif all(status not in ['matched', 'approved'] for status in statuses):
                    data['reconciliation_status'] = 'pending'
                else:
                    data['reconciliation_status'] = 'mixed'
        
        return data
    
    def create(self, validated_data):
        # In case clients still send 'entity', ignore it
        validated_data.pop("entity", None)
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        validated_data.pop("entity", None)
        return super().update(instance, validated_data)

class ReconciliationTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReconciliationTask
        fields = [
            "id",
            "task_id",
            "status",
            "tenant_id",

            "config",
            "config_name",
            "pipeline",
            "pipeline_name",

            "parameters",
            "result",
            "error_message",

            "bank_candidates",
            "journal_candidates",
            "suggestion_count",
            "matched_bank_transactions",
            "matched_journal_entries",
            "auto_match_enabled",
            "auto_match_applied",
            "auto_match_skipped",
            "duration_seconds",
            "stats",

            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "status",
            "result",
            "error_message",
            "bank_candidates",
            "journal_candidates",
            "suggestion_count",
            "matched_bank_transactions",
            "matched_journal_entries",
            "auto_match_enabled",
            "auto_match_applied",
            "auto_match_skipped",
            "duration_seconds",
            "stats",
            "created_at",
            "updated_at",
        ]

class ReconciliationSerializer(serializers.ModelSerializer):
    same_company = serializers.SerializerMethodField()
    same_entity = serializers.SerializerMethodField()
    
    class Meta:
        model = Reconciliation
        fields = '__all__'
    
    def get_same_company(self, obj):
        """
        Check if all bank transactions and journal entries belong to the same company.
        Returns True if there's exactly one unique company ID across all records, False otherwise.
        """
        company_ids = set()
        
        # Collect company IDs from bank transactions
        for bank_tx in obj.bank_transactions.all():
            if bank_tx.company_id is not None:
                company_ids.add(bank_tx.company_id)
        
        # Collect company IDs from journal entries (via transaction)
        for je in obj.journal_entries.all():
            if hasattr(je, 'transaction') and je.transaction and je.transaction.company_id is not None:
                company_ids.add(je.transaction.company_id)
        
        # Return True if there's exactly one unique company ID, False otherwise
        # If no records or all have None, return False (treat as mismatch)
        return len(company_ids) == 1
    
    def get_same_entity(self, obj):
        """
        Check if all bank transactions and journal entries belong to the same entity.
        Returns True if there's exactly one unique entity ID across all records, False otherwise.
        """
        entity_ids = set()
        
        # Collect entity IDs from bank transactions (via entity_id property)
        for bank_tx in obj.bank_transactions.all():
            try:
                entity_id = bank_tx.entity_id
                if entity_id is not None:
                    entity_ids.add(entity_id)
            except (AttributeError, TypeError):
                # Fallback: try accessing via bank_account if property fails
                if hasattr(bank_tx, 'bank_account') and bank_tx.bank_account:
                    entity_id = getattr(bank_tx.bank_account, 'entity_id', None)
                    if entity_id is not None:
                        entity_ids.add(entity_id)
        
        # Collect entity IDs from journal entries (via transaction.entity_id)
        for je in obj.journal_entries.all():
            if hasattr(je, 'transaction') and je.transaction:
                entity_id = getattr(je.transaction, 'entity_id', None)
                if entity_id is not None:
                    entity_ids.add(entity_id)
        
        # Return True if there's exactly one unique entity ID, False otherwise
        # If no records or all have None, return False (treat as mismatch)
        return len(entity_ids) == 1

class ReconciliationConfigSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)
    user_name = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = ReconciliationConfig
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        scope = attrs.get("scope") or getattr(self.instance, "scope", None)
        # enforce company/user presence based on scope
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
        fields = "__all__"

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

class ReconciliationPipelineStageSerializer(serializers.ModelSerializer):
    """
    Serializer for an individual pipeline stage.  Exposes the stage order,
    whether it is enabled, and any per‑stage overrides.
    """
    config_name = serializers.CharField(source="config.name", read_only=True)

    class Meta:
        model = ReconciliationPipelineStage
        fields = "__all__"




class ReconciliationPipelineSerializer(serializers.ModelSerializer):
    """
    Serializer for a reconciliation pipeline with its nested stages.
    """
    company_name = serializers.CharField(source="company.name", read_only=True)
    user_name = serializers.CharField(source="user.username", read_only=True)
    stages = ReconciliationPipelineStageSerializer(many=True, read_only=True)

    class Meta:
        model = ReconciliationPipeline
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]


class ResolvedReconciliationPipelineSerializer(serializers.ModelSerializer):
    """
    Simple serializer for listing pipelines available to a given user.
    """
    company_name = serializers.CharField(source="company.name", read_only=True)
    user_name = serializers.CharField(source="user.username", read_only=True)
    scope_label = serializers.SerializerMethodField()

    class Meta:
        model = ReconciliationPipeline
        fields = "__all__"

    def get_scope_label(self, obj):
        if obj.scope == "global":
            return "Global Pipeline"
        if obj.scope == "company" and obj.company:
            return f"Company Pipeline ({obj.company.name})"
        if obj.scope == "user" and obj.user:
            return f"User Pipeline ({obj.user.username})"
        if obj.scope == "company_user" and obj.company and obj.user:
            return f"Company+User Pipeline ({obj.company.name} | {obj.user.username})"
        return obj.scope


class ProposedRuleSerializer(serializers.Serializer):
    """Serializer for a proposed rule returned by the propose endpoint."""
    temp_id = serializers.CharField(required=False)
    rule_type = serializers.CharField()
    name = serializers.CharField()
    bank_pattern = serializers.CharField()
    book_pattern = serializers.CharField()
    extraction_groups = serializers.DictField(required=False, default=dict)
    sample_count = serializers.IntegerField()
    accuracy_score = serializers.DecimalField(max_digits=5, decimal_places=4)
    samples = serializers.ListField(child=serializers.DictField(), required=False, default=list)


class ReconciliationRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReconciliationRule
        fields = "__all__"
        read_only_fields = ["validated_at"]


class ValidateRulesSerializer(serializers.Serializer):
    """Payload for POST validate: list of rule decisions."""
    rules = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False,
    )


class StartEmbeddingBackfillSerializer(serializers.Serializer):
    per_model_limit = serializers.IntegerField(required=False, min_value=1)
    sync = serializers.BooleanField(required=False, default=False)

class EmbedTestSerializer(serializers.Serializer):
    texts = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    # Optional overrides
    base_url  = serializers.CharField(required=False)
    path      = serializers.CharField(required=False)
    model     = serializers.CharField(required=False)
    timeout_s = serializers.FloatField(required=False)
    dim       = serializers.IntegerField(required=False)
    api_key   = serializers.CharField(required=False, allow_blank=True)
    num_thread = serializers.IntegerField(required=False)
    keep_alive = serializers.CharField(required=False)

class TaskIdSerializer(serializers.Serializer):
    task_id = serializers.CharField()

class TaskStatusSerializer(serializers.Serializer):
    task_id = serializers.CharField()
    state = serializers.CharField()
    ready = serializers.BooleanField()
    successful = serializers.BooleanField()
    result = serializers.JSONField(required=False)
    error = serializers.CharField(required=False)
    mode = serializers.CharField(required=False)

class BackfillSerializer(serializers.Serializer):
    per_model_limit = serializers.IntegerField(required=False, min_value=1)
    base_url = serializers.URLField(required=False)
    path = serializers.CharField(required=False, default="/api/embeddings")
    model = serializers.CharField(required=False, default="embeddinggemma:300m")
    timeout_s = serializers.FloatField(required=False, default=20.0)
    dim = serializers.IntegerField(required=False, default=768)
    api_key = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    
class EmbeddingJobSerializer(serializers.Serializer):
    task_id = serializers.CharField()
    task_name = serializers.CharField()
    status = serializers.CharField()            # Celery state string (SUCCESS/FAILURE/STARTED/...)
    status_friendly = serializers.CharField()   # human form (complete/error/running/...)
    created_at = serializers.DateTimeField(allow_null=True)
    started_at = serializers.DateTimeField(allow_null=True)
    done_at = serializers.DateTimeField(allow_null=True)
    runtime_s = serializers.FloatField(allow_null=True)
    worker = serializers.CharField(allow_null=True)
    queue = serializers.CharField(allow_null=True)
    result = serializers.JSONField(allow_null=True)    # your task's return dict (on success)
    error = serializers.CharField(allow_null=True)     # traceback or error string (on failure)
    progress = serializers.JSONField(allow_null=True)  # live meta if available