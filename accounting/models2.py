from django.db import models
from multitenancy import Company, CustomUser, Entity
from datetime import timedelta
from django.db.models import Q
from itertools import combinations

class Currency(models.Model):
    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=100)
    symbol = models.CharField(max_length=10)
    
    def __str__(self):
        return self.code
    
    def __repr__(self):
        return f"<Currency {self.code}>"

class Account(models.Model):
    company = models.ForeignKey(Company, related_name='accounts', on_delete=models.CASCADE)
    account_code = models.CharField(max_length=100)
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=50)  # e.g., 'asset', 'liability', etc.
    account_direction = models.IntegerField()
    balance = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Transaction(models.Model):
    company = models.ForeignKey(Company, related_name='transactions', on_delete=models.CASCADE)
    date = models.DateField()
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    state = models.CharField(max_length=50, default='pending')  # e.g., 'pending', 'posted', etc. default = pending
    rules = models.ManyToManyField('Rule', blank=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    '''
    #include method to retrieve all journal entries for a transaction
    def journal_entries(self):
        return self.journal_entries.all()

    #include method to retrieve all rules for a transaction
    def rules(self):
        return self.rules.all()
    '''
    #include method to check if the total of all journal entries for a transaction is balanced
    def check_balance(self):
        sum([entry.debit_amount for entry in self.journal_entries.all()]) - sum(
            [entry.credit_amount for entry in self.journal_entries.all()])

    '''
    def post(self):
        if self.state == 'pending':
            if self.check_balance() == 0:
                for entry in self.journal_entries.all():
                    entry.state = 'posted'
                    entry.save()
                self.state = 'posted'
                self.save()
            else:
                raise Exception('Transaction is not balanced: {}'.format(self))
        else:
            raise Exception('Transaction is not pending: {}'.format(self))

    def unpost(self):
        if self.state == 'posted':
            for entry in self.journal_entries.all():
                entry.state = 'pending'
                entry.save()
            self.state = 'pending'
            self.save()
        else:
            raise Exception('Transaction is not posted: {}'.format(self))


    def cancel(self, user):
        if self.state != 'posted':
            for entry in self.journal_entries.all():
                entry.state = 'canceled'
                entry.save()
            self.state = 'canceled'
            self.save()
        elif user.is_superuser:
            for entry in self.journal_entries.all():
                entry.state = 'canceled'
                entry.save()
            self.state = 'canceled'
            self.save()
        else:
            raise Exception('Transaction is already posted, only superuser can cancel: {}'.format(self))
    '''

class JournalEntry(models.Model):
    transaction = models.ForeignKey(Transaction, related_name='journal_entries', on_delete=models.CASCADE)
    entity = models.ForeignKey(Entity, related_name='journal_entries', on_delete=models.CASCADE)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    debit_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    credit_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    state = models.CharField(max_length=10, choices=[('pending', 'Pending'), ('posted', 'Posted'), ('canceled', 'Canceled')], default='pending')
    #description = models.CharField(max_length=255, null=True, blank=True)
    #additional_info = models.JSONField(null=True, blank=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    updated_by = models.ForeignKey(CustomUser, related_name='+', on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f'{self.account.account_code} - {self.transaction.description}'

    def save(self, *args, **kwargs):
        if self.debit_amount and self.credit_amount:
            raise ValueError('Only one of debit_amount or credit_amount can be set')
        if self.debit_amount is None and self.credit_amount is None:
            raise ValueError('Either debit_amount or credit_amount must be set')
        if (self.debit_amount and self.debit_amount < 0) or (self.credit_amount and self.credit_amount < 0):
            raise ValueError('Amounts cannot be negative')
        super().save(*args, **kwargs)

    def get_amount(self):
        return self.debit_amount if self.debit_amount else self.credit_amount

    def get_balance(self):
        return self.debit_amount if self.debit_amount else -self.credit_amount




class Rule(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    model = models.CharField(max_length=100)  # e.g., 'Transaction', 'Account'
    action = models.CharField(max_length=100)  # e.g., 'create_journal_entry'
    condition = models.JSONField()  # JSON to define when the rule is applicable


class Bank(models.Model):
    name = models.CharField(max_length=100)
    country = models.CharField(max_length=50)  # e.g., 'United States of America'
    bank_code = models.CharField(max_length=50)  # e.g., 'BOFAUS3N'
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.bank_code} - {self.name} - {self.country}'

class BankAccount(models.Model):
    company = models.ForeignKey(Company, related_name='bank_accounts', on_delete=models.CASCADE)
    entity = models.ForeignKey(Entity, related_name='bank_accounts', on_delete=models.CASCADE)
    account_number = models.CharField(max_length=50)
    bank = models.ForeignKey(Bank, on_delete=models.CASCADE)
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=12, decimal_places=2)
    balance_date = models.DateField()
    #include fields usually present in OFX files
    account_type = models.CharField(max_length=50)
    branch_id = models.CharField(max_length=50)
    branch_name = models.CharField(max_length=50)
    branch_phone = models.CharField(max_length=50)
    account_name = models.CharField(max_length=50)
    #include fields usually present in CSV/Excel files
    account_holder = models.CharField(max_length=50)
    account_holder_address = models.CharField(max_length=255)
    account_holder_city = models.CharField(max_length=50)
    account_holder_state = models.CharField(max_length=50)
    account_holder_zip = models.CharField(max_length=50)
    account_holder_country = models.CharField(max_length=50)

    def __str__(self):
        return f'{self.bank_name} - {self.account_number}'



class BankTransaction(models.Model):
    company = models.ForeignKey(Company, related_name='bank_transactions', on_delete=models.CASCADE)
    entity = models.ForeignKey(Entity, related_name='bank_transactions', on_delete=models.CASCADE)
    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE)
    date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255)
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    #include fields usually present in OFX files
    transaction_type = models.CharField(max_length=50)
    check_number = models.CharField(max_length=50)
    reference_number = models.CharField(max_length=50)
    payee = models.CharField(max_length=255)
    memo = models.CharField(max_length=255)
    #include fields usually present in CSV/Excel files
    account_number = models.CharField(max_length=50)
    routing_number = models.CharField(max_length=50)
    #include fields usually present in QIF files
    transaction_id = models.CharField(max_length=50)
    status = models.CharField(max_length=50)
    #include fields usually present in IIF files
    transaction_class = models.CharField(max_length=50)
    transaction_method = models.CharField(max_length=50)
    transaction_amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_date = models.DateField()
    transaction_reference = models.CharField(max_length=50)
    transaction_memo = models.CharField(max_length=255)
    transaction_name = models.CharField(max_length=255)

    #provide a method for getting all bank transactions not reconciled
    '''
    @classmethod
    def get_unreconciled(cls):
        return cls.objects.filter(reconciliations__isnull=True)
    def __str__(self):
        return f'{self.date} - {self.amount} - {self.description}'
    
    def get_matching_journal_entries(self):
        potential_matches = JournalEntry.objects.filter(
            transaction__company=self.company,  # Ensure the same company
            transaction__entity=self.entity,    # Ensure the same entity
            account__account_type='cash',
            date__range=[self.date - timedelta(days=2), self.date + timedelta(days=2)]
        )

        matching_entries = []
        for entry in potential_matches:
            score = 0
            # Assigning weights to different criteria
            weight_date = 0.3
            weight_amount = 0.4
            weight_additional_info = 0.3
            delta_days = 5
            # Calculate score based on matching criteria
            if entry.date in [self.date - timedelta(days=delta_days), self.date + timedelta(days=delta_days)]:
                score += weight_date * (1-abs((entry.date - self.date).days)/delta_days)
            if entry.get_amount() == self.amount:
                score += weight_amount

            # Matching based on additional_info JSON field
            additional_info = entry.additional_info or {}
            if additional_info.get('transaction_type') == self.transaction_type:
                score += weight_additional_info * 0.5
            if additional_info.get('reference_number') == self.reference_number:
                score += weight_additional_info * 0.5

            if score > 0:  # Consider only entries with some level of matching
                matching_entries.append((entry, score))

        # Sort by score in descending order
        return sorted(matching_entries, key=lambda x: x[1], reverse=True)

    def get_many_to_many_matches(self):
        potential_matches = JournalEntry.objects.filter(
            transaction__company=self.company, 
            transaction__entity=self.entity,
            account__account_type='cash',
            date__range=[self.date - timedelta(days=2), self.date + timedelta(days=2)]
        )

        # Find all combinations of potential matches up to a certain size
        # Here, we assume a maximum of 3 journal entries for simplicity; adjust as needed
        all_combinations = []
        for r in range(2, 4):  # Starting from 2 because we're looking for combinations
            for combo in combinations(potential_matches, r):
                all_combinations.append(combo)

        # Filter combinations where the sum of amounts matches the bank transaction amount
        matching_combinations = []
        for combo in all_combinations:
            total_amount = sum([entry.get_amount() for entry in combo])
            if total_amount == self.amount:
                # Calculate a confidence score for the combination
                # Here, the score is simplistic; it could be refined to consider other factors
                confidence_score = sum([self.calculate_date_score(entry.date) for entry in combo]) / len(combo)
                matching_combinations.append((combo, confidence_score))

        # Sort combinations by confidence score in descending order
        return sorted(matching_combinations, key=lambda x: x[1], reverse=True)

    def find_best_matches(self):
        CONFIDENCE_THRESHOLD = 0.8

        single_matches = self.get_single_matches()
        best_single_match = max(single_matches, key=lambda x: x[1], default=(None, 0))

        if best_single_match[1] < CONFIDENCE_THRESHOLD:
            return self.get_many_to_many_matches()
        else:
            return [best_single_match]
    '''

class Reconciliation(models.Model):
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE)
    bank_transaction = models.ForeignKey(BankTransaction, on_delete=models.CASCADE)
    status = models.CharField(max_length=50, choices=[('matched', 'Matched'), ('unmatched', 'Unmatched')], default='unmatched')
    reconciled_on = models.DateField(auto_now_add=True)

    