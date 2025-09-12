# NORD/accounting/models.py

from re import U
from django.db import models
#from multitenancy.models import BaseModel, TenantAwareBaseModel#Company, CustomUser, Entity
from datetime import timedelta
from django.db.models import Q, Sum
from decimal import Decimal
from itertools import combinations
from django.apps import apps
from django.core.exceptions import ValidationError
from django.utils.timezone import now

from multitenancy.models import BaseModel, TenantAwareBaseModel
from mptt.models import MPTTModel, TreeForeignKey
from mptt.managers import TreeManager
from multitenancy.models import Company, CustomUser
from django.conf import settings
from decimal import Decimal, ROUND_HALF_UP

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
    
    class MPTTMeta:
        order_insertion_by = ['account_code']    

    class Meta:
        unique_together = ('company', 'account_code', 'name')
        
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

    class Meta:
        indexes = [
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
    
    def check_balance(self):
        sum([entry.debit_amount for entry in self.journal_entries.all()]) - sum(
            [entry.credit_amount for entry in self.journal_entries.all()])

    def __str__(self):
        return f'{self.date} - {self.amount} - {self.description}'
    
    #função de entuba de sugere as as journal entries que deveriam ser criadas com base no historico e numa tabela de regras de de-para cadastradas. e checar consistencia.
    #modelo de contratos com cliente, entidade, data inicio, data fim, valor, recorrencia, regra ajuste preço.
    
class JournalEntry(TenantAwareBaseModel):
    transaction = models.ForeignKey(Transaction, related_name='journal_entries', on_delete=models.CASCADE)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    cost_center = models.ForeignKey(CostCenter, on_delete=models.CASCADE, null=True, blank=True)
    debit_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    credit_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    state = models.CharField(max_length=10, choices=[('pending', 'Pending'), ('posted', 'Posted'), ('canceled', 'Canceled')], default='pending')
    date = models.DateField(null=True, blank=True)
    
    def clean_fields(self, exclude=None):
        exclude = set(exclude or [])
        if 'debit_amount' not in exclude and self.debit_amount is not None:
            # go through str() to kill binary float artifacts; then force 2dp
            self.debit_amount = Decimal(str(self.debit_amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        if 'credit_amount' not in exclude and self.credit_amount is not None:
            # go through str() to kill binary float artifacts; then force 2dp
            self.credit_amount = Decimal(str(self.credit_amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        super().clean_fields(exclude=exclude)
    
    def save(self, *args, **kwargs):
        if self.debit_amount is not None:
            self.debit_amount = Decimal(str(self.debit_amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        if self.credit_amount is not None:
            self.credit_amount = Decimal(str(self.credit_amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        super().save(*args, **kwargs)
    
    class Meta:
        indexes = [
            models.Index(fields=['transaction']),
            models.Index(fields=['account']),
            models.Index(fields=['cost_center']),
            models.Index(fields=['date']),  # optionally index the new field
        ]
    
    def __str__(self):
        return f'{self.transaction.date} - {self.transaction.amount} - {self.account.account_code} - {self.transaction.description}'
    
    def save(self, *args, **kwargs):
        if (self.debit_amount and self.debit_amount < 0) or (self.credit_amount and self.credit_amount < 0):
            raise ValueError('Amounts cannot be negative')
        if self.debit_amount and self.credit_amount:
            raise ValueError('Only one of debit_amount or credit_amount can be set')
        if self.debit_amount is None and self.credit_amount is None:
            raise ValueError('Either debit_amount or credit_amount must be set')
        
        if not self.date:
            self.date = self.transaction.date  # default to transaction date

        if self.date < self.transaction.date:
            raise ValueError('Journal entry date cannot be earlier than the transaction date')

        
        super().save(*args, **kwargs)

    def get_amount(self):
        return self.debit_amount if self.debit_amount else self.credit_amount
    
    def get_effective_amount(self):
        # If the account has an account_direction field, use it; otherwise, default to 1.
        direction = self.account.account_direction if self.account and self.account.account_direction else 1
        #considers a debit in a positive direction account is positive.
        #print(self)
        #print(self.debit_amount, self.credit_amount)
        amount = 0
        if self.debit_amount:
            amount= self.debit_amount
        elif self.credit_amount:
            amount= -self.credit_amount
        #amount = self.debit_amount if self.debit_amount else -self.credit_amount
        return amount * direction
    
    def get_balance(self):
        return self.debit_amount if self.debit_amount else -self.credit_amount


class Rule(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    model = models.CharField(max_length=100)  # e.g., 'Transaction', 'Account'
    action = models.CharField(max_length=100)  # e.g., 'create_journal_entry'
    condition = models.JSONField()  # JSON to define when the rule is applicable








class BankTransaction(TenantAwareBaseModel):
    entity = models.ForeignKey('multitenancy.Entity', related_name='bank_transactions', on_delete=models.CASCADE)
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
    
    def clean_fields(self, exclude=None):
        exclude = set(exclude or [])
        if 'amount' not in exclude and self.amount is not None:
            # go through str() to kill binary float artifacts; then force 2dp
            self.amount = Decimal(str(self.amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        super().clean_fields(exclude=exclude)
    
    def save(self, *args, **kwargs):
        if self.amount is not None:
            # if floats can reach here, protect with str() to avoid artifacts
            self.amount = Decimal(str(self.amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        super().save(*args, **kwargs)
        

    
    class Meta:
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['bank_account']),
            models.Index(fields=['entity']),
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
    """
    Stores reusable reconciliation settings (shortcuts / presets).
    Can be global (system-wide), per company, or per user.
    """

    SCOPE_CHOICES = [
        ("global", "Global"),
        ("company", "Company"),
        ("user", "User"),
        ("company_user", "Company + User"),
    ]

    scope = models.CharField(
        max_length=20, choices=SCOPE_CHOICES, default="company",
        help_text="Who this config applies to: global, company, user, or company+user"
    )
    # Only required if scope == "company"
    company = models.ForeignKey(
        Company,
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="reconciliation_configs"
    )
    
    # Only required if scope == "user"
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="reconciliation_configs"
    )
    
    name = models.CharField(max_length=255, help_text="Name of this config, e.g. 'High Precision Match' or 'Loose Match'")
    description = models.TextField(blank=True, null=True)

    # Bank & Book filters (saved queries)
    bank_filters = models.JSONField(default=dict, blank=True)
    book_filters = models.JSONField(default=dict, blank=True)

    # Reconciliation parameters
    strategy = models.CharField(
        max_length=50,
        choices=[
            ("exact 1-to-1", "Exact 1-to-1"),
            ("fuzzy", "Fuzzy"),
            ("many-to-many", "Many-to-Many"),
            ("optimized", "Optimized"),
        ],
        default="optimized"
    )
    max_group_size = models.PositiveIntegerField(default=2)
    amount_tolerance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    date_tolerance_days = models.PositiveIntegerField(default=2)
    min_confidence = models.DecimalField(max_digits=4, decimal_places=2, default=0.9)
    max_suggestions = models.PositiveIntegerField(default=5)

    # Metadata
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("company", "user", "name")  # each company can’t have duplicate config names
        ordering = ["-updated_at"]

    def __str__(self):
        if self.scope == "global":
            return f"[Global] {self.name}"
        elif self.scope == "company" and self.company:
            return f"[Company: {self.company.name}] {self.name}"
        elif self.scope == "user" and self.user:
            return f"[User: {self.user.username}] {self.name}"
        elif self.scope == "company_user" and self.company and self.user:
            return f"[Company: {self.company.name} | User: {self.user.username}] {self.name}"
        return f"{self.name} (Unscoped)"

    def clean(self):
        """Ensure required fields are set depending on scope."""
        from django.core.exceptions import ValidationError

        if self.scope == "company" and not self.company:
            raise ValidationError("Company is required for company scope configs.")
        if self.scope == "user" and not self.user:
            raise ValidationError("User is required for user scope configs.")
        if self.scope == "company_user" and (not self.company or not self.user):
            raise ValidationError("Both company and user are required for company_user scope configs.")