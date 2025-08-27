from accounting.models import Transaction, JournalEntry, Account
from django.db.models import Sum


def calculate_transaction_balance(transaction):
    """
    Calculate the balance of a transaction by summing its journal entries.
    Returns the difference between total debits and credits.
    """
    balance = transaction.journal_entries.aggregate(
        debit_total=Sum('debit_amount') or 0,
        credit_total=Sum('credit_amount') or 0,
    )
    return balance['debit_total'] - balance['credit_total']


def create_balancing_journal_entry(transaction, balancing_account):
    """
    Create a journal entry to balance the transaction.
    The balancing entry will ensure total debits equal total credits.
    """
    balance = calculate_transaction_balance(transaction)
    if balance == 0:
        return None  # Transaction is already balanced

    is_debit = balance < 0
    amount = abs(balance)

    journal_entry = JournalEntry.objects.create(
        transaction=transaction,
        account=balancing_account,
        debit_amount=amount if is_debit else None,
        credit_amount=None if is_debit else amount,
        state='pending',
    )
    return journal_entry


def validate_transaction_balanced(transaction):
    """
    Check if a transaction is balanced (total debits == total credits).
    """
    return calculate_transaction_balance(transaction) == 0


def post_transaction(transaction):
    """
    Post a transaction by marking all its journal entries as 'posted'.
    Ensures the transaction is balanced before posting.
    """
    if not validate_transaction_balanced(transaction):
        raise ValueError("Transaction is not balanced")
    transaction.journal_entries.update(state='posted')
    transaction.state = 'posted'
    transaction.save()


def unpost_transaction(transaction):
    """
    Unpost a transaction by reverting its journal entries to 'pending'.
    """
    if transaction.state != 'posted':
        raise ValueError("Only posted transactions can be unposted")
    transaction.journal_entries.update(state='pending')
    transaction.state = 'pending'
    transaction.save()


def cancel_transaction(transaction):
    """
    Cancel a transaction by marking all its journal entries as 'canceled'.
    """
    transaction.journal_entries.update(state='canceled')
    transaction.state = 'canceled'
    transaction.save()


