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


def bulk_post_balanced_transactions(
    company,
    *,
    dry_run: bool = False,
    limit: int = 0,
) -> dict:
    """Promote every ``state='pending'`` AND ``is_balanced=True`` Tx
    on ``company`` to ``state='posted'``.

    The posting workflow exists per-Tx (``post_transaction``) but
    there's no auto-trigger or UI button calling it; tenants
    accumulate balanced-but-unposted Txs indefinitely. This is the
    bulk fix, mirroring ``billing.services.invoice_payment_evidence
    .backfill_invoice_status_from_recon`` for the GL side.

    Idempotent: re-running is a no-op once everything balanced is
    posted. Safe to wire to a UI button + scheduled task.

    Args:
        company: tenant.
        dry_run: when True, count what would change but do not
            touch the DB. Used by the UI's confirm modal.
        limit: optional cap; ``0`` (default) means no cap.

    Returns counters + samples for the operator's confirmation
    step.
    """
    from accounting.models import Transaction

    qs = Transaction.objects.filter(
        company=company,
        state='pending',
        is_balanced=True,
    ).order_by('date', 'id')
    total = qs.count()
    iter_qs = qs[:limit] if limit > 0 else qs

    counters = {
        'scanned_pending_balanced': total,
        'would_post': 0,
        'posted': 0,
        'failed': 0,
        'samples': [],
        'failures': [],
    }
    sample_buf: list[dict] = []

    if dry_run:
        # Cheap dry-run: same query, no writes.
        counters['would_post'] = total
        # Pull a few samples without locking.
        for tx in iter_qs.only('id', 'date', 'amount', 'description')[:5]:
            sample_buf.append({
                'id': tx.id,
                'date': tx.date.isoformat() if tx.date else None,
                'amount': str(tx.amount) if tx.amount is not None else None,
                'description': (tx.description or '')[:80],
            })
        counters['samples'] = sample_buf
        return counters

    # Real run: per-Tx via the existing service so any guard there
    # (validate_balanced, JE state cascade) keeps applying.
    for tx in iter_qs:
        try:
            post_transaction(tx)
            counters['posted'] += 1
            if len(sample_buf) < 5:
                sample_buf.append({
                    'id': tx.id,
                    'date': tx.date.isoformat() if tx.date else None,
                    'amount': str(tx.amount) if tx.amount is not None else None,
                    'description': (tx.description or '')[:80],
                })
        except Exception as exc:
            counters['failed'] += 1
            if len(counters['failures']) < 5:
                counters['failures'].append({
                    'id': tx.id,
                    'error': f"{type(exc).__name__}: {exc}",
                })

    counters['samples'] = sample_buf
    counters['would_post'] = counters['posted'] + counters['failed']

    # Posting changes JE.state which IS report-cache-relevant
    # (state='posted' filter changes which JEs flow into delta_map).
    # Bump version so dashboards refresh.
    if counters['posted'] > 0:
        try:
            from accounting.services.report_cache import bump_version
            bump_version(company.id)
        except Exception:
            pass

    return counters

