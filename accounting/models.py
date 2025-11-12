# NORD/accounting/models.py

from re import U
from django.db import models
#from multitenancy.models import BaseModel, TenantAwareBaseModel#Company, CustomUser, Entity
from datetime import timedelta
from django.db.models import Q, Sum, CheckConstraint
from decimal import Decimal, ROUND_HALF_UP
from itertools import combinations
from django.apps import apps
from django.core.exceptions import ValidationError
from django.utils.timezone import now

from multitenancy.models import BaseModel, TenantAwareBaseModel
from mptt.models import MPTTModel, TreeForeignKey
from mptt.managers import TreeManager
from multitenancy.models import Company, CustomUser
from django.conf import settings
from pgvector.django import VectorField, HnswIndex


from django.utils.dateparse import parse_date  # only needed if you keep saves without full_clean()



class Currency(BaseModel):
    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=100)
    symbol = models.CharField(max_length=10)
    
    def __str__(self):
        return self.code
    
    def __repr__(self):
        return f"<Currency {self.code}>"

class CostCenter(TenantAwareBaseModel):
    TYPE_COST = 'cost'
    TYPE_PROFIT = 'profit'
    TYPE_CHOICES = [
        (TYPE_COST, 'Cost'),
        (TYPE_PROFIT, 'Profit')
    ]
    
    #company = models.ForeignKey('multitenancy.Company', related_name='costcenters', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    center_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    description = models.CharField(max_length=255, null=True, blank=True)
    balance = models.DecimalField(max_digits=12, decimal_places=2)
    balance_date = models.DateField()
    
    def __str__(self):
        return f'({self.id}) {self.company} - {self.name} ({self.center_type})'
    
    class Meta:
        unique_together = ('company', 'name')
    
    def get_current_balance(self):
        # Start with the last known balance and balance_date
        validated_balance = self.balance
        last_balance_date = self.balance_date

        # Fetch journal entries linked to this cost center after the balance_date
        transactions = JournalEntry.objects.filter(
            cost_center=self,
            transaction__date__gt=last_balance_date,
            state='posted',
            transaction__balance_validated=False  # <-- include only not yet validated transactions
        ).aggregate(
            total_debit=Sum('debit_amount'),
            total_credit=Sum('credit_amount')
        )

        total_debit = transactions['total_debit'] or Decimal('0.00')
        total_credit = transactions['total_credit'] or Decimal('0.00')
        
        effective_amount = (total_debit - total_credit)
        current_balance = validated_balance + effective_amount
        
        # Assume debit increases balance and credit decreases it; adjust according to your accounting rules.
        return current_balance
    
class Bank(BaseModel):
    name = models.CharField(max_length=100, unique = True)
    country = models.CharField(max_length=50)  # e.g., 'United States of America'
    bank_code = models.CharField(max_length=50, unique = True)  # e.g., 'BOFAUS3N'
    is_active = models.BooleanField(default=True)


    def __str__(self):
        return f'{self.bank_code} - {self.name} - {self.country}'

class BankAccount(TenantAwareBaseModel):
    entity = models.ForeignKey('multitenancy.Entity', related_name='bank_accounts', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=50)
    bank = models.ForeignKey(Bank, on_delete=models.CASCADE)
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=12, decimal_places=2)
    balance_date = models.DateField()
    account_type = models.CharField(max_length=50)
    branch_id = models.CharField(max_length=50, default=1)

    def __str__(self):
        return f'({self.id}) {self.company} - {self.entity} - {self.bank.name} - {self.account_number}'
    
    class Meta:
        unique_together = ('name', 'bank', 'account_number', 'branch_id')
    
    def get_current_balance(self):
        last_balance_date = self.balance_date
        validated_balance = self.balance
        transactions = BankTransaction.objects.filter(
            bank_account=self,
            date__gt=last_balance_date,
            balance_validated=False  # <-- include only not yet validated transactions
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        current_balance = validated_balance + transactions

        return current_balance
    
class AllocationBase(TenantAwareBaseModel):
    """
    Allocation rules between cost and profit centers.
    """
    cost_center = models.ForeignKey(CostCenter, related_name='allocations', on_delete=models.CASCADE)
    profit_center = models.ForeignKey(CostCenter, related_name='allocations_as_profit', on_delete=models.CASCADE)
    percentage = models.DecimalField(max_digits=5, decimal_places=2)
    month = models.DateField()
    
    class Meta:
        unique_together = ('cost_center', 'profit_center', 'month')
    
    def clean(self):
        super().clean()
        if self.percentage <= 0 or self.percentage > 100:
            raise ValidationError("Percentage must be between 0 and 100.")

    def __str__(self):
        return f"{self.cost_center.name} -> {self.profit_center.name} ({self.percentage}%)"

#incluir tabela para gerenciar visibilidade e acesso de cada entidade aos modelos de centro de custo e plano de contas.

class Account(TenantAwareBaseModel, MPTTModel):
    account_code = models.CharField(max_length=100, null=True, blank=True)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, null=True, blank=True)
    key_words = models.CharField(max_length=100, null=True, blank=True)
    examples = models.CharField(max_length=255, null=True, blank=True)
    account_direction = models.IntegerField()
    balance_date = models.DateField()
    balance = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    parent = TreeForeignKey('self', null=True, blank=True, related_name='children', on_delete=models.CASCADE)
    
    objects = TreeManager()
    
    account_description_embedding = VectorField(
        dimensions=768, 
        help_text="Vector embeddings (embeddinggemma:300m) of the account content",
        null=True, blank=True)

    
    class MPTTMeta:
        order_insertion_by = ['account_code']    

    class Meta:
        unique_together = ('company', 'account_code', 'name')
        indexes = [
            HnswIndex(
                name="acct_emb_hnsw",
                fields=["account_description_embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            )
            ]
    def __str__(self):
        return f'({self.id}) {self.company} - {self.account_code} - {self.get_path()}'
    
    def is_leaf(self):
        return not self.get_children().exists()
    
    def get_current_balance(self):
        if self.is_leaf():
            last_balance_date = self.balance_date
            validated_balance = self.balance

            transactions = JournalEntry.objects.filter(
                account=self,
                transaction__date__gt=last_balance_date,
                transaction__state='posted',
                transaction__balance_validated=False
            ).aggregate(
                total_debit=Sum('debit_amount'),
                total_credit=Sum('credit_amount')
            )

            total_debit = transactions['total_debit'] or Decimal('0.00')
            total_credit = transactions['total_credit'] or Decimal('0.00')

            effective_amount = (total_debit - total_credit) * self.account_direction
            return validated_balance + effective_amount

        else:
            return sum(child.get_current_balance() for child in self.get_children())
    
    def calculate_balance(self, include_pending=False, beginning_date=None, end_date=None):
        if self.is_leaf():
            entries = self.journal_entries.filter(state='posted')
            if include_pending:
                entries = entries | self.journal_entries.filter(state='pending')

            date_filter = Q()
            if beginning_date:
                date_filter &= Q(date__gte=beginning_date)
            if end_date:
                date_filter &= Q(date__lte=end_date)

            entries = entries.filter(date_filter)
            return entries.aggregate(balance=Sum('amount'))['balance']
        else:
            return sum(child.calculate_balance(include_pending, beginning_date, end_date) for child in self.get_children())


    def get_path(self):
        """Return the full path of this entity as a string."""
        ancestors = [self.name]
        parent = self.parent
        while parent is not None:
            ancestors.insert(0, parent.name)
            parent = parent.parent
        return ' > '.join(ancestors)
    
    def get_path_ids(self):
        """Returns the list of IDs representing the full path to this entity."""
        path = []
        current = self
        while current:
            path.insert(0, current.id)  # Prepend the current entity ID
            current = current.parent
        return path
    
    
    @staticmethod
    def get_leaf_accounts(company_id, entity_id=None, min_depth=1):
        Account = apps.get_model('accounting', 'Account')
        accounts = Account.objects.filter(company_id=company_id)
        if entity_id:
            accounts = accounts.filter(entities__id=entity_id)
        return accounts.filter(is_leaf_node=True, account_code__regex=rf"([0-9-]{{{min_depth},}})")

    @staticmethod
    def get_accounts_summary(company_id, entity_id=None, min_depth=1, include_pending=False, beginning_date=None, end_date=None):
        Account = apps.get_model('accounting', 'Account')
        accounts_query = Account.objects.filter(company_id=company_id)

        if entity_id:
            accounts_query = accounts_query.filter(entities__id=entity_id)

        # Annotar profundidade real (via MPTT) se necessário
        accounts = accounts_query.filter(level__gte=min_depth)

        return [(account, account.calculate_balance(include_pending, beginning_date, end_date)) for account in accounts]
    
    def update_parent_balances(self):
        """Recalcula os saldos de todos os ancestrais até a raiz."""
        for ancestor in self.get_ancestors():
            ancestor_balance = sum(child.get_current_balance() for child in ancestor.get_children())
            ancestor.balance = ancestor_balance
            ancestor.save(update_fields=['balance'])

class Transaction(TenantAwareBaseModel):
    date = models.DateField()
    entity = models.ForeignKey('multitenancy.Entity', related_name='transactions', on_delete=models.CASCADE)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    state = models.CharField(max_length=50, default='pending')  # e.g., 'pending', 'posted'
    balance_validated = models.BooleanField(default=False)  # <-- NEW FIELD
    rules = models.ManyToManyField('Rule', blank=True)
    
    description_embedding = VectorField(
        dimensions=768, 
        help_text="Vector embeddings (embeddinggemma:300m) of the description content",
        null=True, blank=True)
    
    
    class Meta:
        indexes = [
            HnswIndex(
                name="tx_desc_emb_hnsw",
                fields=["description_embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
            models.Index(fields=['date']),
            models.Index(fields=['entity']),
            models.Index(fields=['state']),
            models.Index(fields=['amount']),
            # If you often filter by company (inherited from TenantAwareBaseModel), add:
            models.Index(fields=['company']),
        ]
    
    def clean_fields(self, exclude=None):
        exclude = set(exclude or [])
        if 'amount' not in exclude and self.amount is not None:
            # go through str() to kill binary float artifacts; then force 2dp
            self.amount = Decimal(str(self.amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        super().clean_fields(exclude=exclude)
    
    def save(self, *args, **kwargs):
        if self.amount is not None:
            self.amount = Decimal(str(self.amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return super().save(*args, **kwargs)
    
    def check_balance(self):
        sum([entry.debit_amount for entry in self.journal_entries.all()]) - sum(
            [entry.credit_amount for entry in self.journal_entries.all()])

    def __str__(self):
        return f'{self.date} - {self.amount} - {self.description}'
    
    #função de entuba de sugere as as journal entries que deveriam ser criadas com base no historico e numa tabela de regras de de-para cadastradas. e checar consistencia.
    #modelo de contratos com cliente, entidade, data inicio, data fim, valor, recorrencia, regra ajuste preço.
    



class JournalEntry(TenantAwareBaseModel):
    transaction = models.ForeignKey(Transaction, related_name='journal_entries', on_delete=models.CASCADE)
    account = models.ForeignKey(Account, on_delete=models.CASCADE, null=True, blank=True)
    cost_center = models.ForeignKey(CostCenter, on_delete=models.CASCADE, null=True, blank=True)
    debit_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    credit_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    state = models.CharField(
        max_length=10,
        choices=[('pending', 'Pending'), ('posted', 'Posted'), ('canceled', 'Canceled')],
        default='pending',
    )
    date = models.DateField(null=True, blank=True)

    bank_designation_pending = models.BooleanField(
        default=False,
        db_index=True,
        help_text="If True, this line is the cash/bank leg and still awaits assignment to a specific bank GL."
    )

    class Meta:
        indexes = [
            models.Index(fields=['transaction']),
            models.Index(fields=['account']),
            models.Index(fields=['cost_center']),
            models.Index(fields=['date']),
            models.Index(fields=['bank_designation_pending']),
        ]
        constraints = [
            CheckConstraint(
                name="je_pending_or_account_present",
                check=Q(bank_designation_pending=True) | Q(account__isnull=False),
            ),
            # (Optional but recommended) enforce only one side set at DB level:
            # CheckConstraint(
            #     name="je_one_side_only",
            #     check=(Q(debit_amount__isnull=False, credit_amount__isnull=True) |
            #            Q(debit_amount__isnull=True, credit_amount__isnull=False)),
            # ),
            # (Optional) non-negative amounts at DB level:
            # CheckConstraint(
            #     name="je_non_negative",
            #     check=(Q(debit_amount__gte=0) | Q(debit_amount__isnull=True)) &
            #           (Q(credit_amount__gte=0) | Q(credit_amount__isnull=True)),
            # ),
        ]

    def clean(self):
        super().clean()

        # Require account unless it's explicitly pending designation
        if not self.bank_designation_pending and self.account_id is None:
            raise ValidationError({"account": "Account is required unless bank_designation_pending is True."})

        # Normalize/ensure date relative to transaction here so it also runs in preview (full_clean)
        if not self.date:
            self.date = self.transaction.date
        # If someone bypasses full_clean and sets a string:
        if isinstance(self.date, str):
            parsed = parse_date(self.date)
            if parsed:
                self.date = parsed
        if self.date and self.transaction_id and self.date < self.transaction.date:
            raise ValidationError({"date": "Journal entry date cannot be earlier than the transaction date"})

        # Validate amounts (DB constraints optional; model guard still nice)
        if (self.debit_amount and self.debit_amount < 0) or (self.credit_amount and self.credit_amount < 0):
            raise ValidationError("Amounts cannot be negative")
        if self.debit_amount and self.credit_amount:
            raise ValidationError("Only one of debit_amount or credit_amount can be set")
        if self.debit_amount is None and self.credit_amount is None:
            raise ValidationError("Either debit_amount or credit_amount must be set")

    def clean_fields(self, exclude=None):
        exclude = set(exclude or [])
        if 'debit_amount' not in exclude and self.debit_amount is not None:
            self.debit_amount = Decimal(str(self.debit_amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if 'credit_amount' not in exclude and self.credit_amount is not None:
            self.credit_amount = Decimal(str(self.credit_amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        super().clean_fields(exclude=exclude)

    def save(self, *args, **kwargs):
        # Ensure model logic runs even if saved outside the importer/admin
        # (Your importer already calls full_clean(); this just adds safety.)
        self.full_clean()

        # Auto-behavior for the pending flag/designation:
        if self.account and getattr(self.account, "bank_account_id", None):
            self.bank_designation_pending = False

        if self.bank_designation_pending and self.account_id is None:
            # Lazy import to avoid circulars
            from accounting.services.bank_structs import ensure_pending_bank_structs
            pending_ba, pending_gl = ensure_pending_bank_structs(
                company_id=self.company_id,
                currency_id=self.transaction.currency_id
            )
            self.account_id = pending_gl.id  # stays pending until reconciliation promotes it

        # clean_fields already quantized; this is harmless but redundant—keep if you like:
        if self.debit_amount is not None:
            self.debit_amount = Decimal(str(self.debit_amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if self.credit_amount is not None:
            self.credit_amount = Decimal(str(self.credit_amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        return super().save(*args, **kwargs)

    def __str__(self):
        acct_code = self.account.account_code if self.account_id else "pending-bank"
        return f'{self.transaction.date} - {self.transaction.amount} - {acct_code} - {self.transaction.description}'

    def get_amount(self):
        return self.debit_amount if self.debit_amount is not None else self.credit_amount

    def get_effective_amount(self):
        direction = self.account.account_direction if (self.account and self.account.account_direction) else 1
        if self.debit_amount is not None and self.debit_amount != 0:
            base = self.debit_amount
        elif self.credit_amount is not None and self.credit_amount != 0:
            base = -self.credit_amount
        else:
            base = Decimal('0')
        return base * direction

    def get_balance(self):
        return self.debit_amount if self.debit_amount is not None else (-self.credit_amount)

class Rule(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    model = models.CharField(max_length=100)  # e.g., 'Transaction', 'Account'
    action = models.CharField(max_length=100)  # e.g., 'create_journal_entry'
    condition = models.JSONField()  # JSON to define when the rule is applicable








class BankTransaction(TenantAwareBaseModel):
    #entity = models.ForeignKey('multitenancy.Entity', related_name='bank_transactions', on_delete=models.CASCADE)
    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE)
    date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255)
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    #transaction_type = models.CharField(max_length=50)
    #check_number = models.CharField(max_length=50, blank=True, null=True)
    reference_number = models.CharField(max_length=50, blank=True, null=True)
    #payee = models.CharField(max_length=255, blank=True, null=True)
    #memo = models.CharField(max_length=255)
    #account_number = models.CharField(max_length=50, blank=True, null=True)
    #routing_number = models.CharField(max_length=50, blank=True, null=True)
    #transaction_id = models.CharField(max_length=50, blank=True, null=True)
    status = models.CharField(max_length=50, default="pending")
    balance_validated = models.BooleanField(default=False)  # <-- NEW FIELD
    tx_hash = models.CharField(max_length=64, blank=True, null=True, db_index=True)
    
    description_embedding = VectorField(
        dimensions=768, 
        help_text="Vector embeddings (embeddinggemma:300m) of the bank transaction content",
        null=True, blank=True)

      

    
    @property
    def entity(self):
        # returns Entity instance
        return self.bank_account.entity

    @property
    def entity_id(self):
        # returns Entity id (fast path for DRF)
        return self.bank_account.entity_id

    def clean_fields(self, exclude=None):
        exclude = set(exclude or [])
        if 'amount' not in exclude and self.amount is not None:
            self.amount = Decimal(str(self.amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        super().clean_fields(exclude=exclude)

    def save(self, *args, **kwargs):
        if self.amount is not None:
            self.amount = Decimal(str(self.amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            HnswIndex(
                name="bank_desc_emb_hnsw",
                fields=["description_embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
            models.Index(fields=['date']),
            models.Index(fields=['bank_account']),     # keep this; used in joins
            models.Index(fields=['amount']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'{self.date} - {self.amount} - {self.description} - {self.bank_account}'
    
    

class ReconciliationTask(models.Model):
    STATUS_CHOICES = [
        ("queued", "queued"),
        ("running", "running"),
        ("completed", "completed"),
        ("failed", "failed"),
    ]

    task_id = models.CharField(max_length=255, unique=True, db_index=True)
    tenant_id = models.CharField(max_length=255, null=True, blank=True)

    parameters = models.JSONField(default=dict)  # request payload
    result = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="queued")
    error_message = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(default=now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"ReconciliationTask {self.task_id} ({self.status})"



class Reconciliation(TenantAwareBaseModel):
    """
    Represents a reconciliation process linking journal entries and bank transactions.
    """
    journal_entries = models.ManyToManyField('JournalEntry', related_name='reconciliations')
    bank_transactions = models.ManyToManyField('BankTransaction', related_name='reconciliations')
    status = models.CharField(
        max_length=50,
        choices=[
            ('pending', 'Pending'),
            ('matched', 'Matched'),
            ('unmatched', 'Unmatched'),
            ('review', 'Pending Review'),
            ('approved', 'Approved')
        ],
        default='pending'
    )
    # Use a DateTimeField to capture exact time.
    #reconciled_at = models.DateTimeField(auto_now_add=True)
    #reconciled_by = models.ForeignKey('multitenancy.CustomUser', on_delete=models.SET_NULL, null=True)
    # Optional fields for added context:
    reference = models.CharField(max_length=50, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        journal_ids = ', '.join(str(j.id) for j in self.journal_entries.all())
        bank_ids = ', '.join(str(b.id) for b in self.bank_transactions.all())
        return f"Reconciliation {self.reference or ''}: Journals({journal_ids}) ↔ Banks({bank_ids})"

    @property
    def total_journal_amount(self):
        # Sum the amounts from the related journal entries (using a defined method or field)
        return sum(entry.get_amount() for entry in self.journal_entries.all() if entry.get_amount() is not None)

    @property
    def total_bank_amount(self):
        # Sum the amounts from the related bank transactions
        return sum(tx.amount for tx in self.bank_transactions.all() if tx.amount is not None)

    @property
    def discrepancy(self):
        # The difference between bank and journal totals.
        return self.total_bank_amount - self.total_journal_amount
    
    
class ReconciliationConfig(models.Model):
    """Stores reusable reconciliation settings.

    Users can control basic matching behaviour via this model:

    * `strategy` – high‑level strategy name (for legacy fallback).
    * `amount_tolerance` and `date_tolerance_days` – fuzzy match
      thresholds.
    * `max_group_size_bank` and `max_group_size_book` – maximum
      group sizes on each side for many‑to‑many matching.
    * `fee_accounts`, `duplicate_window_days`, `text_similarity` –
      tune fee folding, duplicate detection and text similarity.

    The removed fields `fx_policy` and `pipeline` simplify the model.
    """

    SCOPE_CHOICES = [
        ("global", "Global"),
        ("company", "Company"),
        ("user", "User"),
        ("company_user", "Company + User"),
    ]

    scope = models.CharField(
        max_length=20,
        choices=SCOPE_CHOICES,
        default="company",
        help_text="Who this config applies to: global, company, user, or company+user",
    )
    company = models.ForeignKey(
        Company,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="reconciliation_configs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="reconciliation_configs",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    bank_filters = models.JSONField(default=dict, blank=True, null=True)
    book_filters = models.JSONField(default=dict, blank=True, null=True)

    embedding_weight = models.DecimalField(
        max_digits=4, decimal_places=2, default=0.50,
        help_text="Weight of embedding similarity in confidence calculation"
    )
    amount_weight = models.DecimalField(
        max_digits=4, decimal_places=2, default=0.35,
        help_text="Weight of amount match in confidence calculation"
    )
    currency_weight = models.DecimalField(
        max_digits=4, decimal_places=2, default=0.10,
        help_text="Weight of currency match in confidence calculation"
    )
    date_weight = models.DecimalField(
        max_digits=4, decimal_places=2, default=0.05,
        help_text="Weight of date proximity in confidence calculation"
    )
    amount_tolerance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    date_tolerance_days = models.PositiveIntegerField(default=2)
    max_group_size_bank = models.PositiveIntegerField(default=1)
    max_group_size_book = models.PositiveIntegerField(default=1)
    min_confidence = models.DecimalField(max_digits=4, decimal_places=2, default=0.9)
    max_suggestions = models.PositiveIntegerField(default=1000)

    # Additional tuning fields
    fee_accounts = models.JSONField(
        default=list,
        blank=True,
        null=True,
        help_text="List of account codes representing fees to include in group sums.",
    )
    duplicate_window_days = models.PositiveIntegerField(
        default=3,
        help_text="Number of days within which identical transactions are considered duplicates.",
    )
    text_similarity = models.JSONField(
        default=dict,
        blank=True,
        null=True,
        help_text="Settings for text and embedding similarity (e.g. use_trgm, use_embedding, weights).",
    )

    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("company", "user", "name")
        ordering = ["-updated_at"]

    def clean(self):
        super().clean()
        total = float(self.embedding_weight + self.amount_weight +
                      self.currency_weight + self.date_weight)
        if abs(total - 1.0) > 0.001:
            raise ValidationError("Confidence weights must sum to 1.0")
        from django.core.exceptions import ValidationError
        if self.scope == "company" and not self.company:
            raise ValidationError("Company is required for company scope configs.")
        if self.scope == "user" and not self.user:
            raise ValidationError("User is required for user scope configs.")
        if self.scope == "company_user" and (not self.company or not self.user):
            raise ValidationError("Both company and user are required for company_user scope configs.")

    def __str__(self) -> str:
        return self.name
    

class ReconciliationPipeline(models.Model):
    """Defines an ordered sequence of reconciliation stages.

    A pipeline belongs to a scope (global, company, user or company_user)
    and optionally references a company and/or user.  The pipeline
    determines high‑level behaviour such as when to auto‑apply
    matches and how many suggestions to return.  Actual stage logic
    comes from referenced `ReconciliationConfig` objects via
    `ReconciliationPipelineStage`.
    """

    scope = models.CharField(
        max_length=20,
        choices=[
            ("global", "Global"),
            ("company", "Company"),
            ("user", "User"),
            ("company_user", "Company + User"),
        ],
        default="company",
    )
    company = models.ForeignKey(
        Company,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="reconciliation_pipelines",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="reconciliation_pipelines",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    auto_apply_score = models.DecimalField(
        max_digits=4, decimal_places=2, default=1.0,
        help_text="Confidence threshold above which matches are auto‑applied."
    )
    max_suggestions = models.PositiveIntegerField(
        default=1000,
        help_text="Maximum number of suggestions returned in one run."
    )
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("company", "user", "name")
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.name


class ReconciliationPipelineStage(models.Model):
    """Links a pipeline to a `ReconciliationConfig` and defines order.

    Each stage points to a saved configuration that acts as the recipe
    for that stage.  The stage may also specify optional overrides
    (e.g. group sizes, tolerances, text weight) which take precedence
    over values from the referenced config.
    """

    pipeline = models.ForeignKey(
        ReconciliationPipeline,
        on_delete=models.CASCADE,
        related_name="stages",
    )
    config = models.ForeignKey(
        ReconciliationConfig,
        on_delete=models.CASCADE,
        related_name="pipeline_stages",
    )
    order = models.PositiveIntegerField()
    enabled = models.BooleanField(default=True)
    # Optional per‑stage overrides
    max_group_size_bank = models.PositiveIntegerField(null=True, blank=True)
    max_group_size_book = models.PositiveIntegerField(null=True, blank=True)
    amount_tolerance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    date_tolerance_days = models.PositiveIntegerField(null=True, blank=True)
    text_weight = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)

    class Meta:
        unique_together = ("pipeline", "order")
        ordering = ["order"]

    def __str__(self) -> str:
        return f"{self.pipeline.name} • Stage {self.order} ({self.config.name})"