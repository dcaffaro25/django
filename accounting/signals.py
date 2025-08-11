from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from accounting.models import JournalEntry, Account

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
