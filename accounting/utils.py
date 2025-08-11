import base64
import re
from datetime import datetime
import hashlib
import json
from decimal import Decimal

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
          { "transaction_type": "CREDIT", "date": <date>, "amount": 20.0, "memo": "..."},
          ...
        ]
      }
    """
    if not ofx_text:
        raise ValueError("Empty OFX text provided.")

    # 1) Extract bank_code
    bank_match = re.search(r"<BANKID>(\w+)", ofx_text)
    if not bank_match:
        raise ValueError("No <BANKID> found in OFX.")
    bank_code = bank_match.group(1).strip()

    # 2) Extract account_id
    acct_match = re.search(r"<ACCTID>([\w/\-]+)", ofx_text)
    account_id = acct_match.group(1).strip() if acct_match else None

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
        memo_match = re.search(r"<MEMO>(.*)", block)
        
        trn_type = trn_type_match.group(1).strip() if trn_type_match else None
        dtposted_str = posted_match.group(1).strip() if posted_match else None
        amount_str = amount_match.group(1).strip() if amount_match else None
        memo_val = memo_match.group(1).strip() if memo_match else ""
        
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
            "memo": memo_val,
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