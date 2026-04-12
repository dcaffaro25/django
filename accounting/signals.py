from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver

from accounting.utils import update_journal_entries_and_transaction_flags

from .models import BankTransaction, JournalEntry, Reconciliation, Transaction


def _transitioning_to_soft_delete(instance) -> bool:
    """True when an existing row is being saved with is_deleted flipped from False to True."""
    if not instance.pk:
        return False
    model = instance.__class__
    try:
        previous = model.objects.get(pk=instance.pk)
    except model.DoesNotExist:
        return False
    return not previous.is_deleted and instance.is_deleted


def _hard_delete_reconciliations_queryset(rec_qs):
    """
    Permanently delete reconciliations in the given queryset, then refresh journal/transaction flags
    for all journal entries that were linked to those reconciliations.
    """
    rec_ids = list(rec_qs.values_list("pk", flat=True).distinct())
    if not rec_ids:
        return
    qs = Reconciliation.objects.filter(pk__in=rec_ids).prefetch_related("journal_entries")
    all_je_ids = set()
    for rec in qs:
        all_je_ids.update(rec.journal_entries.values_list("id", flat=True))
    qs.delete()
    if all_je_ids:
        update_journal_entries_and_transaction_flags(
            JournalEntry.objects.filter(pk__in=all_je_ids)
        )


@receiver(pre_save, sender=JournalEntry)
def hard_delete_reconciliations_on_journal_entry_soft_delete(sender, instance, **kwargs):
    # Note: QuerySet.update(is_deleted=True) does not emit pre_save; use per-row save() or call the helper explicitly.
    if not _transitioning_to_soft_delete(instance):
        return
    _hard_delete_reconciliations_queryset(
        Reconciliation.objects.filter(journal_entries=instance)
    )


@receiver(pre_save, sender=BankTransaction)
def hard_delete_reconciliations_on_bank_transaction_soft_delete(sender, instance, **kwargs):
    if not _transitioning_to_soft_delete(instance):
        return
    _hard_delete_reconciliations_queryset(
        Reconciliation.objects.filter(bank_transactions=instance)
    )


@receiver(pre_save, sender=Transaction)
def hard_delete_reconciliations_on_transaction_soft_delete(sender, instance, **kwargs):
    if not _transitioning_to_soft_delete(instance):
        return
    _hard_delete_reconciliations_queryset(
        Reconciliation.objects.filter(journal_entries__transaction=instance)
    )

@receiver(post_save, sender=Reconciliation)
def on_reconciliation_saved(sender, instance, **kwargs):
    """
    When status (or other fields) change without M2M updates, refresh journal/transaction flags.
    """
    if instance.journal_entries.exists():
        update_journal_entries_and_transaction_flags(instance.journal_entries.all())


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
    if account is None:
        return

    # Recalcula o próprio saldo da conta, se for folha
    if account.is_leaf():
        new_balance = account.get_current_balance()
        account.balance = new_balance
        account.save(update_fields=['balance'])

    # Recalcula os saldos dos pais
    account.update_parent_balances()
