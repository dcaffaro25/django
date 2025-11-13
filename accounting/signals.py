from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from accounting.models import JournalEntry, Account

from django.db.models.signals import m2m_changed, post_delete
from django.dispatch import receiver

from .models import Reconciliation, JournalEntry
from accounting.utils import update_journal_entries_and_transaction_flags

@receiver(m2m_changed, sender=Reconciliation.journal_entries.through)
def on_reconciliation_entries_changed(sender, instance, action, pk_set, **kwargs):
    """
    Update flags whenever journal_entries are added to or removed from a Reconciliation.
    """
    if action in ('post_add', 'post_remove', 'post_clear'):
        # Gather affected journal entries
        entries = JournalEntry.objects.filter(pk__in=pk_set) if pk_set else instance.journal_entries.all()
        update_journal_entries_and_transaction_flags(entries)

@receiver(post_delete, sender=Reconciliation)
def on_reconciliation_deleted(sender, instance, **kwargs):
    """
    Recompute flags on all journal entries of a deleted Reconciliation.
    """
    update_journal_entries_and_transaction_flags(instance.journal_entries.all())

@receiver([post_save, post_delete], sender=JournalEntry)
def update_account_balance(sender, instance, **kwargs):
    account = instance.account

    # Recalcula o próprio saldo da conta, se for folha
    if account.is_leaf():
        new_balance = account.get_current_balance()
        account.balance = new_balance
        account.save(update_fields=['balance'])

    # Recalcula os saldos dos pais
    account.update_parent_balances()
