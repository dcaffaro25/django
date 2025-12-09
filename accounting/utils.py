import base64
import re
from datetime import datetime
import hashlib
import json
from decimal import Decimal
from django.db import transaction
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from typing import List, Dict, Any, Optional

from accounting.models import Transaction, JournalEntry


def _normalize_digits(value) -> Optional[str]:
    """
    Normalize a bank or account code:
    - accepts None / int / str
    - strips all non-digits
    - returns canonical string without leading zeros (via int),
      e.g. '0237' -> '237'.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    digits = re.sub(r"\D", "", s)
    if not digits:
        return None
    # canonical form: int -> str, removes leading zeros safely
    try:
        return str(int(digits))
    except ValueError:
        return None


def _normalize_raw_digits(value) -> Optional[str]:
    """
    Return only the digits from value as a string (no int() cast),
    e.g. '0237' -> '0237'. Useful for exact matching when DB stores
    codes with leading zeros.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    digits = re.sub(r"\D", "", s)
    return digits or None

def update_journal_entries_and_transaction_flags(journal_entries):
    """
    Given an iterable of JournalEntry instances, recompute per‑entry flags
    (is_cash, is_reconciled) and the parent Transaction flags (is_balanced,
    is_reconciled).  Call this inside an atomic block.
    """
    tx_ids = {je.transaction_id for je in journal_entries}

    with transaction.atomic():
        # Per-entry flags
        for je in journal_entries:
            is_cash = bool(
                je.bank_designation_pending or (
                    je.account and getattr(je.account, 'bank_account_id', None)
                )
            )
            je.is_cash = is_cash
            je.is_reconciled = je.reconciliations.filter(
                status__in=['matched', 'approved']
            ).exists()
            je.save(update_fields=['is_cash', 'is_reconciled'])

        # Transaction flags
        for tx in Transaction.objects.select_for_update().filter(id__in=tx_ids):
            sums = tx.journal_entries.aggregate(
                total_debits=Coalesce(Sum('debit_amount'), Decimal('0')),
                total_credits=Coalesce(Sum('credit_amount'), Decimal('0')),
            )
            tx.is_balanced = (sums['total_debits'] == sums['total_credits'])

            bank_entries = tx.journal_entries.filter(
                Q(account__bank_account__isnull=False) | Q(bank_designation_pending=True)
            )
            if not bank_entries.exists():
                tx.is_reconciled = False
            else:
                tx.is_reconciled = not bank_entries.exclude(
                    is_reconciled=True
                ).exists()

            tx.save(update_fields=['is_balanced', 'is_reconciled'])


def recalculate_transaction_and_journal_entry_status(transaction_ids=None, company_id=None):
    """
    Recalculate and update the status of transactions and their journal entries.
    
    This function:
    1. Checks if transactions are balanced (debits = credits)
    2. Updates transaction.state based on journal entry states
    3. Updates transaction.is_posted flag
    4. Updates journal entry flags (is_cash, is_reconciled)
    5. Updates transaction flags (is_balanced, is_reconciled)
    
    Parameters
    ----------
    transaction_ids: Optional[List[int]]
        Specific transaction IDs to recalculate. If None, recalculates all.
    company_id: Optional[int]
        If provided, only recalculate transactions for this company.
    
    Returns
    -------
    dict
        Statistics about what was updated
    """
    from accounting.models import Transaction, JournalEntry
    
    stats = {
        'transactions_checked': 0,
        'transactions_updated': 0,
        'journal_entries_updated': 0,
        'state_changes': 0,
    }
    
    # Build query
    query = Transaction.objects.select_related('company', 'currency', 'entity')
    if transaction_ids:
        query = query.filter(id__in=transaction_ids)
    if company_id:
        query = query.filter(company_id=company_id)
    
    with transaction.atomic():
        for tx in query.prefetch_related('journal_entries__account__bank_account', 'journal_entries__reconciliations'):
            stats['transactions_checked'] += 1
            updated = False
            
            # Get all journal entries for this transaction
            journal_entries = list(tx.journal_entries.all())
            
            if not journal_entries:
                continue
            
            # 1. Check if transaction is balanced
            sums = tx.journal_entries.aggregate(
                total_debits=Coalesce(Sum('debit_amount'), Decimal('0')),
                total_credits=Coalesce(Sum('credit_amount'), Decimal('0')),
            )
            is_balanced = (sums['total_debits'] == sums['total_credits'])
            
            if tx.is_balanced != is_balanced:
                tx.is_balanced = is_balanced
                updated = True
            
            # 2. Check journal entry states to determine transaction state
            all_posted = all(je.state == 'posted' for je in journal_entries)
            all_pending = all(je.state == 'pending' for je in journal_entries)
            all_canceled = all(je.state == 'canceled' for je in journal_entries)
            has_posted = any(je.state == 'posted' for je in journal_entries)
            has_canceled = any(je.state == 'canceled' for je in journal_entries)
            
            # Determine transaction state
            new_state = tx.state
            if all_canceled:
                new_state = 'canceled'
            elif all_posted:
                new_state = 'posted'
            elif all_pending:
                new_state = 'pending'
            elif has_posted and has_canceled:
                new_state = 'mixed'  # Some posted, some canceled
            elif has_posted:
                new_state = 'partial'  # Some posted, some pending
            
            if tx.state != new_state:
                tx.state = new_state
                stats['state_changes'] += 1
                updated = True
            
            # 3. Update is_posted flag
            new_is_posted = (new_state == 'posted')
            if tx.is_posted != new_is_posted:
                tx.is_posted = new_is_posted
                updated = True
            
            # 4. Update journal entry flags
            for je in journal_entries:
                je_updated = False
                
                # Check is_cash
                is_cash = bool(
                    je.bank_designation_pending or (
                        je.account and getattr(je.account, 'bank_account_id', None)
                    )
                )
                if je.is_cash != is_cash:
                    je.is_cash = is_cash
                    je_updated = True
                
                # Check is_reconciled
                is_reconciled = je.reconciliations.filter(
                    status__in=['matched', 'approved']
                ).exists()
                if je.is_reconciled != is_reconciled:
                    je.is_reconciled = is_reconciled
                    je_updated = True
                
                if je_updated:
                    je.save(update_fields=['is_cash', 'is_reconciled'])
                    stats['journal_entries_updated'] += 1
            
            # 5. Update transaction reconciliation flag
            bank_entries = tx.journal_entries.filter(
                Q(account__bank_account__isnull=False) | Q(bank_designation_pending=True)
            )
            if not bank_entries.exists():
                new_is_reconciled = False
            else:
                new_is_reconciled = not bank_entries.exclude(is_reconciled=True).exists()
            
            if tx.is_reconciled != new_is_reconciled:
                tx.is_reconciled = new_is_reconciled
                updated = True
            
            # Save transaction if updated
            if updated:
                tx.save(update_fields=['is_balanced', 'is_reconciled', 'state', 'is_posted'])
                stats['transactions_updated'] += 1
    
    return stats

def decode_ofx_content(data_dict):
    """
    Based on the data_dict, we decide:
    - if `ofx_text` is present, we use it directly
    - else if `base64Data` is present, decode it
    - and return a plain string with the OFX content
    """
    # 1) If 'ofx_text' is present, trust that
    ofx_text = data_dict.get("ofx_text")
    if ofx_text:
        return ofx_text

    # 2) If we have base64Data, decode it
    base64_str = data_dict.get("base64Data")
    if base64_str:
        # decode from base64
        decoded_bytes = base64.b64decode(base64_str)
        return decoded_bytes.decode("utf-8", errors="replace")

    # If neither is provided, return empty or raise error
    return None


def parse_ofx_text(ofx_text):
    """
    Basic parser that extracts:
      - bank_code from <BANKID>
      - account_id from <ACCTID>
      - transactions from <STMTTRN> blocks
    Returns a dict:
      {
        "bank_code": "0237",
        "account_id": "1084/1448",
        "transactions": [
          { 
            "transaction_type": "CREDIT", 
            "date": <date>, 
            "amount": 20.0, 
            "memo": "...",  # Combined NAME | MEMO for backward compatibility
            "description": "NAME | MEMO"  # Combined NAME and MEMO fields
          },
          ...
        ]
      }
    
    The description field combines <NAME> (payee/description) and <MEMO> fields:
    - If both exist: "NAME | MEMO"
    - If only NAME exists: "NAME"
    - If only MEMO exists: "MEMO"
    - If neither exists: ""
    """
    if not ofx_text:
        raise ValueError("Empty OFX text provided.")

    # 1) Extract bank_code
    bank_match = re.search(r"<BANKID>(\w+)", ofx_text)
    if not bank_match:
        raise ValueError("No <BANKID> found in OFX.")
    bank_code = bank_match.group(1).strip()
    bank_code = _normalize_digits(bank_code)        # '0237' -> '237'
    bank_code = _normalize_raw_digits(bank_code)     # '0237' -> '0237'
    
    # 2) Extract account_id
    acct_match = re.search(r"<ACCTID>([\w/\-]+)", ofx_text)
    account_id = acct_match.group(1).strip() if acct_match else None
    account_id = _normalize_raw_digits(account_id)
    # 3) Find <STMTTRN> blocks
    stmttrn_pattern = re.compile(r"<STMTTRN>(.*?)</STMTTRN>", re.DOTALL)
    blocks = stmttrn_pattern.findall(ofx_text)

    transactions = []
    for block in blocks:
        # Grab fields with small regexes
        trn_type_match = re.search(r"<TRNTYPE>(\w+)", block)
        posted_match = re.search(r"<DTPOSTED>(\d+)", block)
        # Allow both dot and comma as decimal separators:
        amount_match = re.search(r"<TRNAMT>([-\d\.,]+)", block)
        # Extract both NAME (description/payee) and MEMO fields
        # OFX tags can be self-closing or have closing tags, handle both cases
        # Pattern: <NAME>content</NAME> or <NAME>content<next_tag or end
        name_match = re.search(r"<NAME>(.*?)(?:</NAME>|(?=<[A-Z/])|$)", block, re.DOTALL)
        memo_match = re.search(r"<MEMO>(.*?)(?:</MEMO>|(?=<[A-Z/])|$)", block, re.DOTALL)
        
        trn_type = trn_type_match.group(1).strip() if trn_type_match else None
        dtposted_str = posted_match.group(1).strip() if posted_match else None
        amount_str = amount_match.group(1).strip() if amount_match else None
        
        # Extract NAME and MEMO, handling multiline content
        name_val = name_match.group(1).strip() if name_match else ""
        memo_val = memo_match.group(1).strip() if memo_match else ""
        
        # Combine NAME and MEMO into description field
        # If both exist, combine them with a separator
        # If only one exists, use that
        description_parts = []
        if name_val:
            description_parts.append(name_val)
        if memo_val:
            description_parts.append(memo_val)
        
        # Join with " | " if both exist, otherwise use the single value
        description = " | ".join(description_parts) if len(description_parts) > 1 else (description_parts[0] if description_parts else "")
        
        # Keep memo field for backward compatibility
        memo_val = description  # Use combined description as memo for backward compatibility
        
        # Debug prints (remove or comment out in production)
        print('block:', block)
        print('amount_match:', amount_match)
        print('amount_str:', amount_str)
        
        # Convert date from e.g. "20230202000000" -> "2023-02-02"
        date_val = None
        if dtposted_str and len(dtposted_str) >= 8:
            date_str = dtposted_str[:8]
            date_val = datetime.strptime(date_str, "%Y%m%d").date()

        # Normalize the amount string:
        # Replace comma with dot to handle European-style decimals.
        if amount_str:
            normalized_amount_str = amount_str.replace(',', '.')
            # You can use float() or Decimal() here. For consistency with your model,
            # you might later convert it to Decimal. For now, we convert to float.
            amt_val = float(normalized_amount_str)
        else:
            amt_val = 0.0

        transactions.append({
            "transaction_type": trn_type,
            "date": date_val.isoformat() if date_val else None,  # "YYYY-MM-DD"
            "amount": amt_val,
            "memo": memo_val,  # This will be the combined description
            "description": description,  # Explicit description field with combined NAME | MEMO
        })

    return {
        "bank_code": bank_code,
        "account_id": account_id,
        "transactions": transactions
    }



def generate_ofx_transaction_hash(
    date_str: str,
    amount: float,
    transaction_type: str,
    memo: str,
    bank_number: str,
    account_number: str
) -> str:
    """
    Concatenate the relevant fields into a single string
    and compute a hash. 
    This string should be stable and consistent so 
    duplicates yield the same hash.
    """
    # 1) Normalize or trim fields as needed
    # For instance, lowercasing the memo or removing trailing spaces
    normalized_memo = memo.strip().lower() if memo else ""
    
    
    canonical_data = [
            date_str,
            amount,
            transaction_type,
            normalized_memo,
            bank_number,
            account_number
        ]
    raw = json.dumps(canonical_data, ensure_ascii=False, separators=(',', ':'))
    md5_hash = hashlib.md5(raw.encode('utf-8')).hexdigest()

    
    # 2) Build a raw string
    # *Make sure to include exactly the fields you consider relevant
    #raw_str = f"{date_str}|{abs(amount)}|{transaction_type.upper()}|{normalized_memo}|{bank_number}|{account_number}"

    # 3) Hash with e.g. MD5 (or SHA256 if you prefer)
    #md5_hash = hashlib.md5(raw_str.encode('utf-8')).hexdigest()
    return md5_hash

def find_book_combos(candidates, target, max_items, tolerance, current_combo=None, current_sum=Decimal("0"), start_index=0):
    """
    Recursively finds combinations of journal entries from `candidates` (a list of JournalEntry objects)
    such that the sum of entry.get_amount() is within `tolerance` of the target amount.
    Only combinations up to length `max_items` are considered.
    
    Returns a list of combinations (each combination is a list of JournalEntry objects) 
    that satisfy |current_sum - target| <= tolerance.
    """
    if current_combo is None:
        current_combo = []
    results = []
    
    # If we have at least one element, check if the sum is within tolerance.
    if current_combo and abs(current_sum - target) <= Decimal(tolerance):
        results.append(list(current_combo))
    
    # If we reached maximum allowed items, return.
    if len(current_combo) >= max_items:
        return results

    # Iterate over the candidates starting at start_index
    for i in range(start_index, len(candidates)):
        candidate = candidates[i]
        candidate_amount = candidate.get_amount()
        if candidate_amount is None:
            continue  # Skip candidate if amount is missing
            
        new_sum = current_sum + candidate_amount
        # Optionally, we can prune branches that are already too far off.
        # For example, if new_sum already exceeds target + tolerance, and since candidates are sorted ascending,
        # further additions will only increase the sum. (Assumes all amounts are non-negative.)
        if new_sum - target > Decimal(tolerance):
            break  # Prune since further candidates (being higher) will not help.
        current_combo.append(candidate)
        results.extend(find_book_combos(candidates, target, max_items, tolerance, current_combo, new_sum, i + 1))
        current_combo.pop()
    return results

def convert_decimals(obj):
    if isinstance(obj, list):
        return [convert_decimals(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        return float(obj)
    else:
        return obj