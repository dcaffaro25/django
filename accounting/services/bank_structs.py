# accounting/services/bank_structs.py
from decimal import Decimal
from django.apps import apps
from django.utils.timezone import now
from django.db import transaction, IntegrityError

PENDING_ENTITY_NAME = "PENDING"
PENDING_BANK_NAME = "PENDING"
PENDING_BANKACCOUNT_NAME = "Pending BankAccount"
PENDING_BANKACCOUNT_NUMBER = "PENDING"
PENDING_BRANCH_ID = "PENDING"
PENDING_GL_ACCOUNT_NAME = "Bank Clearing (Pending)"
PENDING_GL_ACCOUNT_CODE = "1.1.1.PENDING"  # adapt to your CoA conventions
BANK_GL_ACCOUNT_CODE_PREFIX = "1.1.1.BANK."  # prefix for auto-created bank GL accounts
DEFAULT_ACCOUNT_DIRECTION = 1  # assets typically +1

def _get_model(label):
    return apps.get_model("accounting", label)

def _get_multi(label):
    # for models outside 'accounting'
    return apps.get_model("multitenancy", label)

@transaction.atomic
def ensure_pending_bank_structs(company_id, *, currency_id=None):
    """
    Ensures, for a given company:
      - a 'PENDING' Bank (or reuses existing)
      - a 'Pending BankAccount'
      - a GL Account linked to that pending BankAccount (clearing account)
    Returns (pending_bank_account, pending_gl_account)
    """
    Bank = apps.get_model("accounting", "Bank")
    BankAccount = apps.get_model("accounting", "BankAccount")
    Account = apps.get_model("accounting", "Account")
    Currency = apps.get_model("accounting", "Currency")
    Entity = apps.get_model("multitenancy", "Entity")
    
    # pick a currency if not given (first one as a fallback)
    if currency_id is None:
        currency_id = Currency.objects.values_list("id", flat=True).order_by("id").first()
    
    entity, _ = Entity.objects.get_or_create(
        company_id=company_id,
        name=PENDING_ENTITY_NAME,
        defaults={}
    )
    
    bank, _ = Bank.objects.get_or_create(
        #company_id=company_id,
        name=PENDING_BANK_NAME,
        defaults={}
    )

    # Use a savepoint to isolate IntegrityError and prevent transaction breakage
    # This allows us to rollback just the failed get_or_create attempt without
    # breaking the entire transaction
    try:
        sid = transaction.savepoint()
    except Exception:
        # Transaction is already in a failed state, can't create savepoint
        # Try to get the existing record directly, or create it if it doesn't exist
        try:
            pending_ba = BankAccount.objects.get(
                company_id=company_id,
                name=PENDING_BANKACCOUNT_NAME,
                account_number=PENDING_BANKACCOUNT_NUMBER,
                branch_id=PENDING_BRANCH_ID,
                bank=bank,
            )
        except BankAccount.DoesNotExist:
            # Record doesn't exist and transaction is broken - can't create it here
            # This is a critical error - the function should fail gracefully
            # The caller should handle this or use the endpoint to create it manually
            raise RuntimeError(
                f"Pending BankAccount does not exist for company {company_id} and cannot be created "
                f"because the transaction is in a failed state. Please use the ensure_pending endpoint "
                f"to create it manually."
            )
    else:
        try:
            pending_ba, _ = BankAccount.objects.get_or_create(
                company_id=company_id,
                name=PENDING_BANKACCOUNT_NAME,
                account_number=PENDING_BANKACCOUNT_NUMBER,
                branch_id=PENDING_BRANCH_ID,
                bank=bank,
                defaults=dict(
                    currency_id=currency_id,
                    balance=Decimal("0.00"),
                    balance_date=now().date(),
                    account_type="pending",
                    entity = entity,
                    #entity_id=entity_id,  # set to None if you allow; else choose a default entity for the company
                ),
            )
            # Successfully created, release the savepoint
            transaction.savepoint_commit(sid)
        except IntegrityError:
            # Race condition: another process created it between check and create
            # Rollback the savepoint to restore transaction state
            transaction.savepoint_rollback(sid)
            
            # After rollback, we need to retry getting the record
            # Due to transaction isolation, we might not see it immediately, so retry with a small delay
            import time
            max_retries = 3
            retry_delay = 0.1  # 100ms
            
            for attempt in range(max_retries):
                # Try to get the existing record (use filter().first() to avoid DoesNotExist)
                pending_ba = BankAccount.objects.filter(
                    company_id=company_id,
                    name=PENDING_BANKACCOUNT_NAME,
                    account_number=PENDING_BANKACCOUNT_NUMBER,
                    branch_id=PENDING_BRANCH_ID,
                    bank=bank,
                ).first()
                
                if pending_ba:
                    break
                
                # If not found and this isn't the last attempt, wait a bit for transaction to commit
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
            
            if not pending_ba:
                # Record still doesn't exist after retries
                # This shouldn't happen, but if it does, the record might have been created
                # in another transaction that hasn't committed yet
                # Try one final get_or_create without savepoint (let it handle the IntegrityError)
                try:
                    pending_ba, _ = BankAccount.objects.get_or_create(
                        company_id=company_id,
                        name=PENDING_BANKACCOUNT_NAME,
                        account_number=PENDING_BANKACCOUNT_NUMBER,
                        branch_id=PENDING_BRANCH_ID,
                        bank=bank,
                        defaults=dict(
                            currency_id=currency_id,
                            balance=Decimal("0.00"),
                            balance_date=now().date(),
                            account_type="pending",
                            entity=entity,
                        ),
                    )
                except IntegrityError:
                    # Final attempt - the record definitely exists, use get() with select_for_update
                    # This will wait for any pending transaction to commit
                    from django.db import transaction as db_transaction
                    try:
                        with db_transaction.atomic():
                            pending_ba = BankAccount.objects.select_for_update(nowait=False).get(
                                company_id=company_id,
                                name=PENDING_BANKACCOUNT_NAME,
                                account_number=PENDING_BANKACCOUNT_NUMBER,
                                branch_id=PENDING_BRANCH_ID,
                                bank=bank,
                            )
                    except BankAccount.DoesNotExist:
                        # Even after all retries and select_for_update, record not found
                        # This is very unusual - the IntegrityError said it exists
                        # The record might be in a transaction that will rollback
                        # Raise a clear error message
                        raise RuntimeError(
                            f"Pending BankAccount for company {company_id} triggered IntegrityError "
                            f"(indicating it exists) but could not be retrieved after multiple attempts. "
                            f"This may be due to transaction isolation. Please try the ensure_pending "
                            f"endpoint again, or check the database directly."
                        )

    # Make sure currency is set even if record existed
    if not pending_ba.currency_id and currency_id:
        pending_ba.currency_id = currency_id
        pending_ba.save(update_fields=["currency"])

    pending_gl, _ = Account.objects.get_or_create(
        company_id=company_id,
        name=PENDING_GL_ACCOUNT_NAME,
        account_code=PENDING_GL_ACCOUNT_CODE,
        defaults=dict(
            description="Auto-created clearing account for pending bank movements",
            account_direction=DEFAULT_ACCOUNT_DIRECTION,
            balance_date=now().date(),
            balance=Decimal("0.00"),
            currency_id=currency_id,
            bank_account=pending_ba,
            is_active=True,
            parent=None,  # set a parent if you have a Cash & Equivalents node
        ),
    )

    # ensure link is correct
    if pending_gl.bank_account_id != pending_ba.id:
        pending_gl.bank_account = pending_ba
        pending_gl.save(update_fields=["bank_account"])

    return pending_ba, pending_gl


@transaction.atomic
def ensure_gl_account_for_bank(company_id, bank_account):
    """
    Ensures a leaf GL account tied to the provided bank_account.
    Returns the Account instance.
    """
    Account = _get_model("Account")

    acc = Account.objects.filter(
        company_id=company_id,
        bank_account_id=bank_account.id
    ).first()

    if acc:
        return acc

    # Create a new leaf account for this bank account
    name = f"Bank - {bank_account.bank.name} {bank_account.account_number}"
    code = f"{BANK_GL_ACCOUNT_CODE_PREFIX}{bank_account.id}"

    acc = Account.objects.create(
        company_id=company_id,
        name=name,
        account_code=code,
        description=f"Auto-created GL account for {bank_account}",
        account_direction=DEFAULT_ACCOUNT_DIRECTION,
        balance_date=now().date(),
        balance=Decimal("0.00"),
        currency_id=bank_account.currency_id,
        bank_account_id=bank_account.id,
        is_active=True,
        parent=None,  # optionally set a Cash parent
    )
    return acc
