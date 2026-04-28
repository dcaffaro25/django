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
    """Account serializer with N+1 queries eliminated.

    Two perf knobs the viewset can flip:

    1. ``context['account_path_map']`` -- a precomputed
       ``{id: {"path": str, "path_ids": [int], "level": int}}`` dict
       built ONCE per request from a single bulk query in
       ``AccountViewSet.get_queryset``. Avoids the per-row
       ``parent.parent.parent...`` lazy walk that previously fired
       ~3 × depth queries PER ROW (3× because path / path_ids /
       level each walked independently). Falls back to per-row
       walking if the context isn't present (single-row reads,
       legacy callers).

    2. ``annotated_current_balance`` -- when the queryset annotates
       a ``current_balance`` column via Subquery, we read it directly
       instead of calling ``obj.get_current_balance()`` which fires
       a per-row aggregation. Falls back to the model method when
       absent.

    On Evolat (356 accounts, MPTT depth 5) this drops a single
    ``GET /api/accounts/`` from ~7000 queries to <5.
    """
    parent_id = serializers.IntegerField(source='parent.id', read_only=True)
    level = serializers.SerializerMethodField()
    path = serializers.SerializerMethodField()
    path_ids = serializers.SerializerMethodField()

    parent = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.all(),
        required=False,
        allow_null=True,
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
    current_balance = serializers.SerializerMethodField()
    # ``effective_category`` and ``effective_tags`` reflect the MPTT
    # inheritance walk -- nearest tagged ancestor for category, union
    # for tags. Computed in Python from the same path map; falls back
    # to a real walk for ad-hoc single-row reads. See
    # ``accounting/services/taxonomy_resolver.py`` for the rules.
    effective_category = serializers.SerializerMethodField()
    effective_tags = serializers.SerializerMethodField()
    # JE-based balance breakdown. Annotated by ``AccountViewSet.get_queryset``
    # via three Subqueries; the frontend rolls up subtree totals by
    # summing children's values. Each is a Decimal-as-string in JSON
    # (DRF's standard DecimalField behaviour).
    #
    # ``own_posted_delta`` is the post-anchor delta for POSTED JEs --
    # adding ``balance`` gives the validated + posted balance.
    # ``own_pending_delta`` is the cumulative effect of JEs whose
    # Transaction is in ``state='pending'``.
    # ``own_unreconciled_delta`` covers JEs not yet reconciled.
    own_posted_delta = serializers.SerializerMethodField()
    own_pending_delta = serializers.SerializerMethodField()
    own_unreconciled_delta = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = [
            'id', 'name', 'company', 'parent', 'parent_id', 'level', 'path', 'path_ids',
            'account_code', 'description', 'key_words', 'examples', 'bank_account',
            'account_direction', 'balance_date',
            'balance', 'currency', 'is_active', 'current_balance',
            # Phase 1 taxonomy fields. Always serialised; null/[] when unset.
            'report_category', 'tags',
            'effective_category', 'effective_tags',
            # JE-derived deltas (see field-level docstrings above).
            'own_posted_delta', 'own_pending_delta', 'own_unreconciled_delta',
        ]

    # ------------------------------------------------------------------
    # Bulk path/level/path_ids lookup
    # ------------------------------------------------------------------
    def _path_entry(self, obj):
        """Return ``{path, path_ids, level}`` for ``obj`` -- from the
        precomputed context dict if available, else compute by walking
        the parent chain (the legacy slow path)."""
        cache = self.context.get('account_path_map') if self.context else None
        if cache is not None:
            entry = cache.get(obj.id)
            if entry is not None:
                return entry
        # Legacy fallback: per-row walk. Single-row reads or unwired
        # callers still work, just slower.
        names: list[str] = []
        ids: list[int] = []
        node = obj
        while node is not None:
            names.append(node.name)
            ids.append(node.id)
            node = node.parent
        names.reverse()
        ids.reverse()
        return {
            "path": " > ".join(names),
            "path_ids": ids,
            "level": max(0, len(ids) - 1),
        }

    def get_level(self, obj):
        return self._path_entry(obj)["level"]

    def get_path(self, obj):
        return self._path_entry(obj)["path"]

    def get_path_ids(self, obj):
        return self._path_entry(obj)["path_ids"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Keep this override for backwards compat -- some callers relied
        # on ``current_balance`` being recomputed in to_representation
        # even when the SerializerMethodField path didn't fire.
        data['current_balance'] = self.get_current_balance(instance)
        return data

    # ------------------------------------------------------------------
    # MPTT-walked taxonomy
    # ------------------------------------------------------------------
    # ``account_taxonomy_map`` from context carries pre-computed
    # ``{effective_category, effective_tags}`` per account so we never
    # walk ``obj.parent.parent...`` via ORM lazy loads (each level
    # would trigger a DB roundtrip; ``select_related('parent')`` only
    # caches ONE level). Without the map we fall back to the live
    # walk -- only fires for ad-hoc single-row reads where the cost
    # is negligible.
    def get_effective_category(self, obj):
        m = (self.context or {}).get('account_taxonomy_map') or {}
        bucket = m.get(obj.id)
        if bucket is not None:
            return bucket.get('effective_category')
        from accounting.services.taxonomy_resolver import effective_category
        return effective_category(obj)

    def get_effective_tags(self, obj):
        m = (self.context or {}).get('account_taxonomy_map') or {}
        bucket = m.get(obj.id)
        if bucket is not None:
            return bucket.get('effective_tags', [])
        from accounting.services.taxonomy_resolver import effective_tags
        return effective_tags(obj)

    # ------------------------------------------------------------------
    # JE-derived deltas
    # ------------------------------------------------------------------
    # Read from the ``account_delta_map`` the viewset attaches via
    # ``get_serializer_context``. The single bulk-query approach is
    # massively faster than the per-row Subqueries we tried first,
    # but means single-row callers (no viewset context) get "0" for
    # all three deltas. Acceptable -- the data only matters in the
    # list view.
    def _delta(self, obj, key):
        m = (self.context or {}).get('account_delta_map') or {}
        bucket = m.get(obj.id)
        if not bucket:
            return "0"
        return bucket.get(key, "0")

    def get_own_posted_delta(self, obj):
        return self._delta(obj, 'own_posted_delta')

    def get_own_pending_delta(self, obj):
        return self._delta(obj, 'own_pending_delta')

    def get_own_unreconciled_delta(self, obj):
        return self._delta(obj, 'own_unreconciled_delta')

    # Compute ``current_balance`` from the bulk-loaded delta map +
    # the account's own anchor. Critical: we never fall back to
    # ``obj.get_current_balance()`` because that recurses through
    # ``get_children()`` and reintroduces the per-row N+1 we just
    # eliminated. Non-leaf rows naturally come out as
    # ``balance + 0 = 0`` here; the frontend rolls up subtree totals
    # via the tree (see ChartOfAccountsPage's ``computeRollups``).
    #
    # When ``include_pending`` is True in context, also adds
    # ``own_pending_delta`` -- caller opted in via
    # ``?include_pending=1`` on the list endpoint. Default stays
    # posted-only so legacy callers don't change behaviour.
    def get_current_balance(self, obj):
        from decimal import Decimal
        ctx = self.context or {}
        # ``exclude_anchor`` is set by the viewset when the request is
        # scoped to a single entity — anchor balance is per-account
        # (whole tenant), not per-entity, so including it would
        # contaminate the entity-filtered report. Drop to flow-only
        # (posted + pending).
        exclude_anchor = bool(ctx.get('exclude_anchor'))
        try:
            anchor = Decimal('0') if exclude_anchor else Decimal(str(obj.balance or '0'))
        except Exception:
            anchor = Decimal('0')
        m = ctx.get('account_delta_map') or {}
        bucket = m.get(obj.id)
        if not bucket:
            return str(anchor)
        try:
            posted = Decimal(bucket.get('own_posted_delta') or '0')
        except Exception:
            posted = Decimal('0')
        include_pending = bool(ctx.get('include_pending'))
        pending = Decimal('0')
        if include_pending:
            try:
                pending = Decimal(bucket.get('own_pending_delta') or '0')
            except Exception:
                pending = Decimal('0')
        return str(anchor + posted + pending)

    


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
            "id", "company", "transaction", "erp_id",
            "description", "account", "cost_center",
            "debit_amount", "credit_amount",
            "state", "date",
            "bank_designation_pending", "has_designated_bank",
            "notes", "tag",
        ]


class JournalEntryDerivedLineSerializer(serializers.Serializer):
    """One new journal line to create on the same transaction as the template entry."""

    date = serializers.DateField(required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    debit_amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    credit_amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    account_id = serializers.IntegerField()
    cost_center_id = serializers.IntegerField(required=False, allow_null=True)
    state = serializers.ChoiceField(
        choices=[("pending", "Pending"), ("posted", "Posted"), ("canceled", "Canceled")],
        default="pending",
        required=False,
    )
    bank_designation_pending = serializers.BooleanField(required=False, default=False)
    is_cash = serializers.BooleanField(required=False, default=False)
    erp_id = serializers.CharField(required=False, allow_blank=True, max_length=128)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        from decimal import Decimal

        d = attrs.get("debit_amount")
        c = attrs.get("credit_amount")
        if d is None and c is None:
            raise serializers.ValidationError("Each line must set debit_amount or credit_amount.")
        d = d if d is not None else Decimal("0")
        c = c if c is not None else Decimal("0")
        if d == 0 and c == 0:
            raise serializers.ValidationError("debit_amount and credit_amount cannot both be zero.")
        if d > 0 and c > 0:
            raise serializers.ValidationError("Use only one of debit_amount or credit_amount as the primary amount.")
        return attrs


class JournalEntryDeriveFromSerializer(serializers.Serializer):
    """
    Create one or more journal entries on the same transaction as template_journal_entry_id.
    """

    template_journal_entry_id = serializers.IntegerField()
    entries = JournalEntryDerivedLineSerializer(many=True)

    def validate_entries(self, value):
        if not value:
            raise serializers.ValidationError("Provide at least one entry in entries.")
        return value


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
    numero_boleto = serializers.SerializerMethodField()
    cnpj = serializers.SerializerMethodField()
    due_date = serializers.SerializerMethodField()
    nf_number = serializers.SerializerMethodField()

    transaction_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = JournalEntry
        fields = [
            'id', 'transaction_id', 'company', 'entity', 'currency',
            'erp_id', 'description', 'bank_date', 'balance',
            'transaction_date', 'transaction_description', 'transaction_value',
            'bank_account', 'reconciliation_status', 'notes', 'tag',
            'numero_boleto', 'cnpj', 'due_date', 'nf_number',
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
        
        if hasattr(instance, 'bank_date'):
            data['bank_date'] = instance.bank_date
        
        if hasattr(instance, 'balance'):
            # Convert Decimal to float if needed
            balance = instance.balance
            data['balance'] = float(balance) if balance is not None else None
        
        if hasattr(instance, 'reconciliation_status'):
            data['reconciliation_status'] = instance.reconciliation_status

        if hasattr(instance, 'numero_boleto'):
            data['numero_boleto'] = instance.numero_boleto
        if hasattr(instance, 'cnpj'):
            data['cnpj'] = instance.cnpj
        if hasattr(instance, 'due_date'):
            data['due_date'] = instance.due_date
        if hasattr(instance, 'nf_number'):
            data['nf_number'] = instance.nf_number
        
        return data

    def get_numero_boleto(self, obj):
        if hasattr(obj, 'numero_boleto'):
            return obj.numero_boleto
        tx = getattr(obj, 'transaction', None)
        return getattr(tx, 'numero_boleto', None) if tx else None

    def get_cnpj(self, obj):
        if hasattr(obj, 'cnpj'):
            return obj.cnpj
        tx = getattr(obj, 'transaction', None)
        return getattr(tx, 'cnpj', None) if tx else None

    def get_due_date(self, obj):
        if hasattr(obj, 'due_date'):
            return obj.due_date
        tx = getattr(obj, 'transaction', None)
        return getattr(tx, 'due_date', None) if tx else None

    def get_nf_number(self, obj):
        if hasattr(obj, 'nf_number'):
            return obj.nf_number
        tx = getattr(obj, 'transaction', None)
        return getattr(tx, 'nf_number', None) if tx else None

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
        """Returns ``{"id", "name"}`` for the GL-linked bank account, or ``None``."""
        if hasattr(obj, 'bank_account_id') and obj.bank_account_id is not None:
            name = getattr(obj, 'bank_account_name', None)
            account = getattr(obj, 'account', None)
            if name is None and account and getattr(account, 'bank_account', None):
                name = account.bank_account.name
            return {'id': obj.bank_account_id, 'name': name}
        account = getattr(obj, 'account', None)
        if account and getattr(account, 'bank_account', None):
            ba = account.bank_account
            return {'id': ba.id, 'name': ba.name}
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
            recs = (
                obj.recon_list
                if hasattr(obj, 'recon_list')
                else list(obj.reconciliations.all())
            )
            if any(rec.status in ["matched", "approved"] for rec in recs):
                return "matched"
            if recs:
                return "open"
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
            'id', 'company', 'entity', 'currency', 'date', 'due_date', 'bank_date',
            'description', 'amount', 'state', 'erp_id', 'nf_number',
            'journal_entries_count', 'balance', 'journal_entries_summary',
            'journal_entries_bank_accounts', 'reconciliation_status', 'notes',
            'is_balanced', 'bank_recon_status', 'bank_linked_je_count', 'bank_reconciled_je_count',
            'total_debit', 'total_credit', 'numero_boleto', 'cnpj',
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

        def je_state(je):
            recs = list(je.reconciliations.all())
            if any(rec.status in ['matched', 'approved'] for rec in recs):
                return 'closed'
            if recs:
                return 'open'
            return 'none'

        states = [je_state(je) for je in relevant_entries]
        if all(s == 'closed' for s in states):
            return 'matched'
        if any(s == 'closed' for s in states):
            return 'mixed'
        if all(s == 'none' for s in states):
            return 'pending'
        if any(s == 'open' for s in states):
            return 'open'
        return 'pending'
    
    def get_bank_recon_status(self, obj):
        """
        Returns the bank reconciliation status:
        - 'matched': All bank-linked JEs have reconciliations with status 'matched' or 'approved'
        - 'open': All bank-linked JEs are linked to non-closed reconciliations (partial / in progress)
        - 'pending': At least one bank-linked JE has no reconciliation at all
        - 'mixed': Some closed, some not
        - 'na': No bank-linked JEs
        """
        relevant_entries = [je for je in obj.journal_entries.all() if je.account and je.account.bank_account]
        if not relevant_entries:
            return 'na'

        def je_state(je):
            recs = list(je.reconciliations.all())
            if any(rec.status in ['matched', 'approved'] for rec in recs):
                return 'closed'
            if recs:
                return 'open'
            return 'none'

        states = [je_state(je) for je in relevant_entries]
        if all(s == 'closed' for s in states):
            return 'matched'
        if any(s == 'closed' for s in states):
            return 'mixed'
        if all(s == 'none' for s in states):
            return 'pending'
        if any(s == 'open' for s in states):
            return 'open'
        return 'pending'
    
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


    


def _bank_tx_match_metrics(instance):
    """Compute (amount_reconciled, amount_remaining, match_progress_pct)
    for a single ``BankTransaction``.

    The reconciliation surface is M:M (one Reconciliation can link
    multiple bank txs to multiple journal entries). We apportion the
    matched journal-entry value to each bank tx by its share of the
    rec's total bank amount: ::

        share        = |bank_tx.amount| / |rec.total_bank_amount|
        bank_matched = share * |rec.total_journal_amount|

    Summed across every active reconciliation (statuses
    ``matched`` / ``approved`` / ``open``) gives the total matched
    magnitude for this bank tx. Remaining is clamped at 0 so rows
    where the operator linked extra JEs (rare but legal) don't
    surface as negative.

    Costs O(R * (J + B)) where R is the rec count for this bank tx
    and J/B are the JE/bank-tx counts inside each rec. The
    ``BankTransactionViewSet`` prefetches the M:M tables to keep this
    in-memory; without prefetch, this is N+1 by design (only callers
    that need the metrics pay).

    Returns a 3-tuple ``(Decimal, Decimal, int)``. ``int`` is rounded
    0..100. Values returned as Decimal so the serializer can quantize
    + render as strings consistently with ``amount`` itself.
    """
    from decimal import Decimal, ROUND_HALF_UP

    bank_amt_abs = abs(instance.amount or Decimal('0'))
    if bank_amt_abs == 0:
        return Decimal('0'), Decimal('0'), 0

    matched = Decimal('0')
    active_statuses = {'matched', 'approved', 'open'}

    # Prefer the prefetched ``recon_list`` (set by
    # ``BankTransactionViewSet.get_queryset``); fall back to the M:M
    # manager otherwise so callers without the prefetch still get
    # correct (slow) numbers rather than zeros.
    recs = getattr(instance, 'recon_list', None)
    if recs is None:
        recs = list(instance.reconciliations.all())

    for rec in recs:
        if rec.status not in active_statuses:
            continue
        rec_bank_total = abs(rec.total_bank_amount or Decimal('0'))
        rec_je_total = abs(rec.total_journal_amount or Decimal('0'))
        if rec_bank_total == 0:
            continue
        share = bank_amt_abs / rec_bank_total
        matched += share * rec_je_total

    if matched > bank_amt_abs:
        matched = bank_amt_abs
    remaining = bank_amt_abs - matched

    # Quantize for display consistency with ``amount`` (2 decimal
    # places). The percent stays an int for cheaper frontend
    # comparisons / chip rendering.
    q = Decimal('0.01')
    matched_q = matched.quantize(q, rounding=ROUND_HALF_UP)
    remaining_q = remaining.quantize(q, rounding=ROUND_HALF_UP)
    pct = int((matched / bank_amt_abs * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    pct = max(0, min(100, pct))
    return matched_q, remaining_q, pct


class BankTransactionSerializer(serializers.ModelSerializer):
    # Use annotated field if available, otherwise fall back to method
    reconciliation_status = serializers.CharField(read_only=True, required=False)
    entity = serializers.IntegerField(source='bank_account.entity_id', read_only=True)
    entity_name = serializers.CharField(source='bank_account.entity.name', read_only=True)
    # Per-bank-tx reconciliation progress. Surfaces partial-match
    # state to the Workbench / list pages so operators see "this row
    # is 60% reconciled, R$ 400 remaining" without drilling into the
    # reconciliation group. Computed lazily; see
    # ``_bank_tx_match_metrics`` for the apportionment rule.
    amount_reconciled = serializers.SerializerMethodField()
    amount_remaining = serializers.SerializerMethodField()
    match_progress_pct = serializers.SerializerMethodField()

    class Meta:
        model = BankTransaction
        fields = [
            'id', 'company', 'bank_account', 'entity', 'entity_name', 'currency', 'date',
            'description', 'amount', 'status', 'erp_id',
            'is_deleted', 'updated_at', 'updated_by', 'reconciliation_status', 'notes',
            'numeros_boleto', 'cnpj', 'tag',
            'amount_reconciled', 'amount_remaining', 'match_progress_pct',
        ]
        extra_kwargs = {
            "bank_account": {"queryset": BankAccount.objects.all()},
        }

    def _ensure_match_metrics(self, obj):
        """Compute the match metrics once per instance per
        serialization. Caches on the instance so the three field
        getters share a single pass over ``obj.recon_list``."""
        cache = getattr(obj, '_bank_tx_match_metrics_cache', None)
        if cache is None:
            cache = _bank_tx_match_metrics(obj)
            obj._bank_tx_match_metrics_cache = cache
        return cache

    def get_amount_reconciled(self, obj):
        matched, _remaining, _pct = self._ensure_match_metrics(obj)
        return str(matched)

    def get_amount_remaining(self, obj):
        _matched, remaining, _pct = self._ensure_match_metrics(obj)
        return str(remaining)

    def get_match_progress_pct(self, obj):
        _matched, _remaining, pct = self._ensure_match_metrics(obj)
        return pct

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
            qs = list(instance.reconciliations.all())
            if not qs:
                data['reconciliation_status'] = 'pending'
            else:
                statuses = [rec.status for rec in qs]
                if any(s in ['matched', 'approved'] for s in statuses):
                    if all(s in ['matched', 'approved'] for s in statuses):
                        data['reconciliation_status'] = 'matched'
                    else:
                        data['reconciliation_status'] = 'mixed'
                else:
                    data['reconciliation_status'] = 'open'

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


class ReconciliationRecordTagBulkSerializer(serializers.Serializer):
    """Bulk set the same free-text tag on journal lines and/or bank lines."""

    tag = serializers.CharField(allow_blank=True, max_length=255, required=True)
    journal_entry_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        default=list,
    )
    bank_transaction_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        default=list,
    )
    company_id = serializers.IntegerField(required=False, min_value=1)

    def validate(self, attrs):
        if not attrs.get("journal_entry_ids") and not attrs.get("bank_transaction_ids"):
            raise serializers.ValidationError(
                "Provide at least one of journal_entry_ids or bank_transaction_ids."
            )
        return attrs


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