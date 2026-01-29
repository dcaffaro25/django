from django.apps import apps
import logging

from multitenancy.signals import CHANGES_TRACKER, clear_changes, get_changes
import unicodedata
from copy import deepcopy
from django.forms.models import model_to_dict
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
import random
import ast
import re
import operator
import threading
import time
import traceback  # <-- new import for tracebacks
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from faker import Faker
from rest_framework.exceptions import ValidationError
from accounting.models import Transaction, JournalEntry, Account
from accounting.serializers import TransactionSerializer, JournalEntrySerializer
from .models import IntegrationRule, SubstitutionRule

from django.db import transaction
from django.test.utils import setup_test_environment, teardown_test_environment
import time
from django.utils.text import slugify

from multitenancy.utils import get_app_for_model
import json
from typing import Any, Dict, List, Optional, Tuple, Union

faker = Faker()
logger = logging.getLogger(__name__)

# Custom timeout exception
class TimeoutException(Exception):
    pass

def timeout_handler(seconds):
    def decorator(func):
        def wrapper(*args, **kwargs):
            result = [None]
            exception = [None]

            def target():
                try:
                    result[0] = func(*args, **kwargs)
                except Exception as e:
                    exception[0] = e

            thread = threading.Thread(target=target)
            thread.start()
            thread.join(seconds)  # Wait for the specified timeout

            if thread.is_alive():
                raise TimeoutException("Execution timed out.")

            if exception[0]:
                raise exception[0]

            return result[0]

        return wrapper
    return decorator


# -----------------------------------------------
# Global or local storage for debug messages
# -----------------------------------------------
debug_logs = []  # A list of strings we'll accumulate

def add_debug_message(msg):
    """Append a debug message to our in-memory buffer."""
    debug_logs.append(msg)


# -------------------
# SAFE OPERATORS
# -------------------
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv
}

SAFE_COMPARISONS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}

SAFE_BOOL_OPS = {
    ast.And: all,
    ast.Or: any
}

SAFE_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Not: operator.not_
}

def sum_group(group, key):
    """Sum a specific key across all items in a group."""
    return sum(item.get(key, 0) for item in group)

def max_group(group, key):
    """Find the maximum value of a specific key in a group."""
    return max(item.get(key, 0) for item in group)

def min_group(group, key):
    """Find the minimum value of a specific key in a group."""
    return min(item.get(key, 0) for item in group)

def first(seq):
    """
    Return the first element of a list-like object or None if empty.
    """
    if seq:
        return seq[0]
    return None

def last(seq):
    """
    Return the last element of a list-like object or None if empty.
    """
    if seq:
        return seq[-1]
    return None

def debug_log(*args):
    message = " ".join(str(a) for a in args)
    add_debug_message(message)

def to_decimal(value, places=2):
    dec_val = Decimal(str(value))
    quant_str = "1." + ("0" * places)
    return dec_val.quantize(Decimal(quant_str), rounding=ROUND_HALF_UP)


# -----------------------------------------------
# ACCOUNT LOOKUP HELPERS (for IntegrationRules)
# -----------------------------------------------

def lookup_account_by_path(path: str, company_id: int, path_separator: str = ' > ') -> Optional[Account]:
    """
    Look up an Account by its hierarchical path.
    
    Args:
        path: Account path like "Assets > Banks > Bradesco"
        company_id: Company ID to search within
        path_separator: Separator used in the path (default: ' > ')
        
    Returns:
        Account instance or None if not found
    """
    if not path or not company_id:
        return None
    
    path_parts = [p.strip() for p in str(path).split(path_separator) if p.strip()]
    if not path_parts:
        return None
    
    # Traverse the account tree
    parent = None
    account = None
    
    for part_name in path_parts:
        account = Account.objects.filter(
            company_id=company_id,
            name__iexact=part_name,
            parent=parent
        ).first()
        
        if not account:
            return None
        
        parent = account
    
    return account


def lookup_account_by_code(code: str, company_id: int) -> Optional[Account]:
    """Look up an Account by its account_code."""
    if not code or not company_id:
        return None
    return Account.objects.filter(
        company_id=company_id,
        account_code__iexact=str(code).strip()
    ).first()


def lookup_account_by_name(name: str, company_id: int) -> Optional[Account]:
    """Look up an Account by its name (first match)."""
    if not name or not company_id:
        return None
    return Account.objects.filter(
        company_id=company_id,
        name__iexact=str(name).strip()
    ).first()


def calculate_debit_credit(amount: Decimal, account: Account) -> Dict[str, Optional[Decimal]]:
    """
    Calculate debit_amount and credit_amount based on amount sign and account direction.
    
    Args:
        amount: The amount (can be positive or negative)
        account: Account instance with account_direction
        
    Returns:
        Dict with 'debit_amount' and 'credit_amount' keys
    """
    if not account:
        return {'debit_amount': None, 'credit_amount': None}
    
    abs_amount = abs(Decimal(str(amount)))
    direction = account.account_direction
    
    # Logic:
    # - Positive amount + debit-normal (1) → debit
    # - Negative amount + debit-normal (1) → credit
    # - Positive amount + credit-normal (-1) → credit
    # - Negative amount + credit-normal (-1) → debit
    
    if (amount >= 0 and direction == 1) or (amount < 0 and direction == -1):
        return {'debit_amount': abs_amount, 'credit_amount': None}
    else:
        return {'debit_amount': None, 'credit_amount': abs_amount}


def create_transaction_with_entries(payload: Dict[str, Any], company_id: int) -> Dict[str, Any]:
    """
    Create a Transaction with two balanced JournalEntries from a generic payload.
    
    This function extracts relevant fields for Transaction and JournalEntry,
    ignoring any extra fields that don't match model fields.
    
    Payload can include:
    - Transaction fields: date, description, amount, entity_id, currency_id, state
    - Bank account: bank_account_id (looks up associated Account for bank entry)
    - Opposing account: account_path, account_id, or account_code
    - Optional: cost_center_id, cost_center_path
    - Any other fields are ignored
    
    Creates:
    1. Transaction record
    2. JournalEntry for bank account (from bank_account_id → Account with that bank_account)
    3. JournalEntry for opposing account (from account_path/account_id/account_code)
    
    The debit/credit is determined by:
    - Bank account entry: follows the amount sign (positive=debit for asset, negative=credit)
    - Opposing account entry: opposite of bank entry to balance
    
    Args:
        payload: Dict with all fields (extra fields are ignored)
        company_id: Company ID for all records
        
    Returns:
        Dict with 'transaction', 'bank_journal_entry', 'opposing_journal_entry', 'errors', 'warnings'
    """
    from accounting.models import Account, BankAccount
    from accounting.serializers import TransactionSerializer, JournalEntrySerializer
    
    result = {
        'transaction': None,
        'bank_journal_entry': None,
        'opposing_journal_entry': None,
        'errors': [],
        'warnings': [],
    }
    
    # -------------------------------------------------------------------------
    # 1. Extract and validate required fields
    # -------------------------------------------------------------------------
    
    amount_raw = payload.get('amount')
    if amount_raw is None:
        result['errors'].append("Missing required field: 'amount'")
        return result
    
    try:
        # Handle Brazilian format if needed
        if isinstance(amount_raw, str):
            amount_raw = amount_raw.replace('.', '').replace(',', '.')
        amount = Decimal(str(amount_raw))
    except Exception as e:
        result['errors'].append(f"Invalid amount value: {amount_raw}")
        return result
    
    abs_amount = abs(amount)
    
    # Date
    date = payload.get('date')
    if not date:
        result['errors'].append("Missing required field: 'date'")
        return result
    
    # Description
    description = payload.get('description', '')
    
    # Entity
    entity_id = payload.get('entity_id')
    if not entity_id:
        result['errors'].append("Missing required field: 'entity_id'")
        return result
    
    # Currency
    currency_id = payload.get('currency_id')
    if not currency_id:
        result['errors'].append("Missing required field: 'currency_id'")
        return result
    
    # -------------------------------------------------------------------------
    # 2. Look up Bank Account and its associated Account
    # -------------------------------------------------------------------------
    
    bank_account_id = payload.get('bank_account_id')
    bank_account = None
    bank_ledger_account = None
    
    if bank_account_id:
        try:
            bank_account = BankAccount.objects.filter(
                company_id=company_id,
                id=int(bank_account_id)
            ).first()
        except (ValueError, TypeError):
            pass
        
        if bank_account:
            # Find the Account linked to this BankAccount
            bank_ledger_account = Account.objects.filter(
                company_id=company_id,
                bank_account_id=bank_account.id
            ).first()
            
            if not bank_ledger_account:
                result['warnings'].append(f"No ledger Account found for BankAccount {bank_account_id}")
    else:
        result['warnings'].append("No bank_account_id provided - bank journal entry will not be created")
    
    # -------------------------------------------------------------------------
    # 3. Look up Opposing Account
    # -------------------------------------------------------------------------
    
    opposing_account = None
    
    # Try account_id first
    account_id = payload.get('account_id')
    if account_id:
        try:
            opposing_account = Account.objects.filter(
                company_id=company_id,
                id=int(account_id)
            ).first()
        except (ValueError, TypeError):
            pass
    
    # Try account_code
    if not opposing_account:
        account_code = payload.get('account_code')
        if account_code:
            opposing_account = lookup_account_by_code(str(account_code), company_id)
    
    # Try account_path
    if not opposing_account:
        account_path = payload.get('account_path')
        path_separator = payload.get('path_separator', ' > ')
        if account_path:
            opposing_account = lookup_account_by_path(str(account_path), company_id, path_separator)
    
    if not opposing_account:
        result['warnings'].append("No opposing account found (tried account_id, account_code, account_path)")
    
    # -------------------------------------------------------------------------
    # 4. Look up Cost Center (optional)
    # -------------------------------------------------------------------------
    
    cost_center_id = payload.get('cost_center_id')
    # Could also support cost_center_path lookup here if needed
    
    # -------------------------------------------------------------------------
    # 5. Create Transaction
    # -------------------------------------------------------------------------
    
    transaction_data = {
        'company': company_id,
        'date': date,
        'description': description,
        'amount': abs_amount,
        'entity_id': entity_id,
        'currency_id': currency_id,
        'state': payload.get('state', 'pending'),
    }
    
    try:
        tx_serializer = TransactionSerializer(data=transaction_data)
        if tx_serializer.is_valid(raise_exception=True):
            transaction_obj = tx_serializer.save()
            result['transaction'] = {
                'id': transaction_obj.id,
                'date': str(transaction_obj.date),
                'description': transaction_obj.description,
                'amount': str(transaction_obj.amount),
            }
    except Exception as e:
        result['errors'].append(f"Failed to create Transaction: {str(e)}")
        return result
    
    # -------------------------------------------------------------------------
    # 6. Calculate Debit/Credit for Journal Entries
    # -------------------------------------------------------------------------
    
    # For bank transactions:
    # - Positive amount (deposit/income): Bank account gets DEBIT (asset increases)
    # - Negative amount (payment/expense): Bank account gets CREDIT (asset decreases)
    
    # The opposing account gets the opposite entry to balance
    
    if bank_ledger_account:
        # Bank account is typically an asset (direction=1)
        # Positive amount → debit bank, credit opposing
        # Negative amount → credit bank, debit opposing
        if amount >= 0:
            bank_debit = abs_amount
            bank_credit = None
            opposing_debit = None
            opposing_credit = abs_amount
        else:
            bank_debit = None
            bank_credit = abs_amount
            opposing_debit = abs_amount
            opposing_credit = None
    else:
        # No bank account, skip bank entry
        bank_debit = None
        bank_credit = None
        # Still create opposing entry if account exists
        if amount >= 0:
            opposing_debit = None
            opposing_credit = abs_amount
        else:
            opposing_debit = abs_amount
            opposing_credit = None
    
    # -------------------------------------------------------------------------
    # 7. Create Bank Account Journal Entry
    # -------------------------------------------------------------------------
    
    if bank_ledger_account:
        bank_je_data = {
            'company': company_id,
            'transaction': transaction_obj.id,
            'account': bank_ledger_account.id,
            'date': date,
            'description': description,
            'debit_amount': bank_debit,
            'credit_amount': bank_credit,
            'cost_center': cost_center_id,
            'state': 'pending',
        }
        
        try:
            bank_je_serializer = JournalEntrySerializer(data=bank_je_data)
            if bank_je_serializer.is_valid(raise_exception=True):
                bank_je = bank_je_serializer.save()
                result['bank_journal_entry'] = {
                    'id': bank_je.id,
                    'account_id': bank_ledger_account.id,
                    'account_name': bank_ledger_account.name,
                    'debit_amount': str(bank_debit) if bank_debit else None,
                    'credit_amount': str(bank_credit) if bank_credit else None,
                }
        except Exception as e:
            result['errors'].append(f"Failed to create bank JournalEntry: {str(e)}")
    
    # -------------------------------------------------------------------------
    # 8. Create Opposing Account Journal Entry
    # -------------------------------------------------------------------------
    
    if opposing_account:
        opposing_je_data = {
            'company': company_id,
            'transaction': transaction_obj.id,
            'account': opposing_account.id,
            'date': date,
            'description': description,
            'debit_amount': opposing_debit,
            'credit_amount': opposing_credit,
            'cost_center': cost_center_id,
            'state': 'pending',
        }
        
        try:
            opposing_je_serializer = JournalEntrySerializer(data=opposing_je_data)
            if opposing_je_serializer.is_valid(raise_exception=True):
                opposing_je = opposing_je_serializer.save()
                result['opposing_journal_entry'] = {
                    'id': opposing_je.id,
                    'account_id': opposing_account.id,
                    'account_name': opposing_account.name,
                    'account_path': opposing_account.get_path() if hasattr(opposing_account, 'get_path') else None,
                    'debit_amount': str(opposing_debit) if opposing_debit else None,
                    'credit_amount': str(opposing_credit) if opposing_credit else None,
                }
        except Exception as e:
            result['errors'].append(f"Failed to create opposing JournalEntry: {str(e)}")
    
    # -------------------------------------------------------------------------
    # 9. Update Transaction flags
    # -------------------------------------------------------------------------
    
    try:
        from accounting.utils import update_journal_entries_and_transaction_flags
        journal_entries = []
        if result['bank_journal_entry']:
            journal_entries.append(JournalEntry.objects.get(id=result['bank_journal_entry']['id']))
        if result['opposing_journal_entry']:
            journal_entries.append(JournalEntry.objects.get(id=result['opposing_journal_entry']['id']))
        if journal_entries:
            update_journal_entries_and_transaction_flags(journal_entries)
    except Exception as e:
        result['warnings'].append(f"Could not update transaction flags: {str(e)}")
    
    return result


Row = Union[Dict[str, Any], List[Any]]

def _normalize(value: str) -> str:
    """Remove acentuação e converte para minúsculas."""
    if value is None:
        return ''
    nfkd = unicodedata.normalize('NFKD', str(value))
    stripped = ''.join(c for c in nfkd if not unicodedata.combining(c))
    return stripped.casefold()

def _passes_conditions(row: Dict[str, Any], conditions: Optional[Dict[str, Any]]) -> bool:
    """
    Avalia condicional (em JSON) para decidir se a regra deve ser aplicada.
    Formatos suportados:
      {"all": [cond1, cond2, ...]}
      {"any": [cond1, cond2, ...]}
      {"not": cond}
      {"field": "campo", "op": "eq|neq|in|nin|regex|iexact|lt|lte|gt|gte|contains|icontains", "value": X}
    """
    if not conditions:
        return True
    # operadores lógicos
    if isinstance(conditions, dict) and "all" in conditions:
        return all(_passes_conditions(row, c) for c in conditions["all"])
    if isinstance(conditions, dict) and "any" in conditions:
        return any(_passes_conditions(row, c) for c in conditions["any"])
    if isinstance(conditions, dict) and "not" in conditions:
        return not _passes_conditions(row, conditions["not"])
    # condição simples
    if not isinstance(conditions, dict):
        return True
    field = conditions.get("field")
    op = (conditions.get("op") or "eq").lower()
    target = conditions.get("value")
    value = row.get(field)
    def to_num(x):
        try:
            return float(x)
        except Exception:
            return None
    if op == "eq":   return value == target
    if op == "neq":  return value != target
    if op == "iexact": return _normalize(value) == _normalize(target)
    if op == "in":
        try: return value in target
        except Exception: return False
    if op == "nin":
        try: return value not in target
        except Exception: return False
    if op == "contains": return str(target) in str(value)
    if op == "icontains": return _normalize(target) in _normalize(value)
    if op == "regex":
        try: return re.search(str(target), str(value)) is not None
        except re.error: return False
    if op in {"lt", "lte", "gt", "gte"}:
        a, b = to_num(value), to_num(target)
        if a is None or b is None: return False
        if op == "lt":  return a < b
        if op == "lte": return a <= b
        if op == "gt":  return a > b
        if op == "gte": return a >= b
    return True

def apply_substitutions(
    payload: List[Union[Dict[str, Any], List[Any]]],
    company_id: int,
    model_name: Optional[str] = None,
    field_names: Optional[List[str]] = None,
    column_names: Optional[List[str]] = None,
    *,
    return_audit: bool = False,
    commit: bool = False,
    processed_row_ids: Optional[set] = None,
    sheet_name: Optional[str] = None,
    substitution_cache: Optional[Dict[str, Dict[str, Dict[Any, Any]]]] = None,
) -> Union[
    List[Union[Dict[str, Any], List[Any]]],
    Tuple[List[Union[Dict[str, Any], List[Any]]], List[Dict[str, Any]]]
]:
    """
    Aplica regras de substituição a cada linha do payload.
    Aceita campo JSON `filter_conditions` em SubstitutionRule para determinar se a regra se aplica.
    Quando `return_audit=True`, retorna também uma auditoria de mudanças por linha.
    Auditoria: lista de dicionários { "__row_id", "field", "old", "new", "rule_id", "rule_name" }.
    
    Quando `commit=True` e `processed_row_ids` é fornecido, rastreia quais linhas já foram processadas
    para evitar processamento duplicado. O set `processed_row_ids` é atualizado in-place com os IDs
    das linhas processadas. Tracking usa (model_name, sheet_name, row_id) para permitir que o mesmo
    row_id apareça em diferentes sheets do mesmo arquivo.
    
    Quando `substitution_cache` é fornecido, armazena mapeamentos de valores originais para valores
    substituídos por modelo e campo: {model_name: {field_name: {original_value: substituted_value}}}.
    Se um valor original já foi substituído anteriormente, reutiliza o resultado em cache em vez de
    reavaliar as regras de substituição.
    """
    if not company_id:
        raise ValueError("Company ID is required for substitutions.")
    from multitenancy.models import SubstitutionRule  # evitar import circular
    
    # Helper function to normalize row ID (matching tasks.py logic)
    def _norm_row_key(key: Any) -> Any:
        if isinstance(key, str):
            return key.replace("\u00A0", " ").strip().lower()
        return key
    
    # Initialize processed_row_ids set if not provided
    if processed_row_ids is None:
        processed_row_ids = set()
    
    # Initialize substitution_cache if not provided
    # Structure: {model_name: {field_name: {original_value: substituted_value}}}
    if substitution_cache is None:
        substitution_cache = {}
    rules_qs = SubstitutionRule.objects.filter(company_id=company_id)
    if model_name:
        rules_qs = rules_qs.filter(model_name=model_name)
    if field_names:
        rules_qs = rules_qs.filter(field_name__in=field_names)
    if column_names:
        rules_qs = rules_qs.filter(column_name__in=column_names)
    # Evaluate queryset once so we can profile and reuse
    rules_list = list(rules_qs)
    # agrupar regras
    grouped = {"model_field": {}, "column_name": {}, "column_index": {}}
    for rl in rules_list:
        if rl.model_name and rl.field_name:
            key = (rl.model_name, rl.field_name)
            grouped["model_field"].setdefault(key, []).append(rl)
        elif rl.column_name:
            grouped["column_name"].setdefault(rl.column_name, []).append(rl)
        elif rl.column_index is not None:
            grouped["column_index"].setdefault(rl.column_index, []).append(rl)
    # trabalhar com cópia
    rows = deepcopy(payload)
    audit: List[Dict[str, Any]] = []
    # Simple profiling accumulators
    prof_start = time.perf_counter()
    rule_time = defaultdict(float)
    rule_hits = defaultdict(int)
    
    # NEW: FK substitution logic (before normal substitutions)
    if model_name:
        from django.db import models as dj_models
        from multitenancy.tasks import MODEL_APP_MAP
        
        app_label = MODEL_APP_MAP.get(model_name)
        if app_label:
            try:
                model = apps.get_model(app_label, model_name)
                # Build FK field mapping: {field_name: related_model_name}
                fk_field_mapping = {}
                for field in model._meta.fields:
                    if isinstance(field, dj_models.ForeignKey):
                        related_model = getattr(field, 'related_model', None)
                        if related_model:
                            fk_field_mapping[field.name] = related_model.__name__
                
                if fk_field_mapping:
                    logger.debug(f"ETL SUBSTITUTION: Found {len(fk_field_mapping)} FK fields in {model_name}: {list(fk_field_mapping.keys())}")
                    
                    # Apply FK substitutions to each row
                    for rec in rows:
                        if isinstance(rec, dict):
                            for field_name, related_model_name in fk_field_mapping.items():
                                if field_name not in rec or rec[field_name] is None:
                                    continue
                                
                                original_value = rec[field_name]
                                
                                # Log before FK substitution
                                logger.debug(f"ETL SUBSTITUTION: Before FK substitution - {field_name}: '{original_value}' (type: {type(original_value).__name__})")
                                
                                # Look for substitution rules: model_name=related_model_name, field_name="id"
                                fk_rules = SubstitutionRule.objects.filter(
                                    company_id=company_id,
                                    model_name__iexact=related_model_name,
                                    field_name__iexact="id"
                                )
                                
                                if fk_rules.exists():
                                    logger.debug(f"ETL SUBSTITUTION: Found {fk_rules.count()} FK substitution rules for {field_name} -> {related_model_name}.id")
                                    
                                    for rule in fk_rules:
                                        # Check filter_conditions
                                        filter_conditions = getattr(rule, 'filter_conditions', None)
                                        if filter_conditions and not _passes_conditions(rec, filter_conditions):
                                            logger.debug(f"ETL SUBSTITUTION: FK rule {rule.id} ({rule.title or rule.id}) failed filter_conditions for {field_name}")
                                            continue
                                        
                                        # Apply substitution using _should_apply_rule logic
                                        mt = (rule.match_type or "exact").lower()
                                        mv = rule.match_value
                                        sv = rule.substitution_value
                                        str_value = str(original_value)
                                        
                                        matched = False
                                        new_value = original_value
                                        
                                        if mt == "exact":
                                            if str_value == mv:
                                                matched = True
                                                new_value = sv
                                        elif mt == "regex":
                                            try:
                                                if re.search(str(mv), str_value):
                                                    matched = True
                                                    new_value = re.sub(str(mv), str(sv), str_value)
                                            except re.error:
                                                logger.warning(f"ETL SUBSTITUTION: Invalid regex pattern in FK substitution rule {rule.id}: {rule.match_value}")
                                        elif mt == "caseless":
                                            if _normalize(str_value) == _normalize(mv):
                                                matched = True
                                                new_value = sv
                                        
                                        if matched and new_value != original_value:
                                            # Convert to int for _id fields
                                            if field_name.endswith('_id'):
                                                try:
                                                    new_value = int(new_value)
                                                    logger.debug(f"ETL SUBSTITUTION: Converted {field_name} substitution value to integer: {new_value}")
                                                except (ValueError, TypeError):
                                                    logger.debug(f"ETL SUBSTITUTION: Could not convert {field_name} value '{new_value}' to int, keeping as string")
                                            
                                            rec[field_name] = new_value
                                            logger.info(f"ETL SUBSTITUTION: FK substitution applied - {field_name}: '{original_value}' -> '{new_value}' (rule: {rule.title or rule.id}, target: {related_model_name}.id)")
                                            
                                            if return_audit:
                                                rid = rec.get("__row_id")
                                                audit.append({
                                                    "__row_id": rid,
                                                    "field": field_name,
                                                    "old": original_value,
                                                    "new": new_value,
                                                    "rule_id": rule.id,
                                                    "rule_name": rule.title or f"Rule#{rule.id}",
                                                })
                                            break  # First matching rule wins
                                else:
                                    logger.debug(f"ETL SUBSTITUTION: No FK substitution rules found for {field_name} -> {related_model_name}.id")
            except LookupError as e:
                logger.debug(f"ETL SUBSTITUTION: Could not load model {model_name} from app {app_label}: {e}")
            except Exception as e:
                logger.warning(f"ETL SUBSTITUTION: Error in FK substitution logic: {e}", exc_info=True)
    
    def _should_apply_rule(row_dict: Dict[str, Any], rl: SubstitutionRule, field: str, value: Any) -> Tuple[bool, Any]:
        """Avalia condições, tipo de correspondência e retorna (True, novo_valor) se aplicar."""
        # verifica condições
        if not _passes_conditions(row_dict, getattr(rl, "filter_conditions", None)):
            return (False, value)
        # verifica match
        mt = (rl.match_type or "exact").lower()
        mv = rl.match_value
        sv = rl.substitution_value
        if mt == "exact":
            if value == mv: return (True, sv)
        elif mt == "regex":
            try:
                if re.search(str(mv), str(value or "")):
                    return (True, re.sub(str(mv), str(sv), str(value or "")))
            except re.error:
                return (False, value)
        elif mt == "caseless":
            if _normalize(value) == _normalize(mv): return (True, sv)
        return (False, value)
    def _rule_name(rl: SubstitutionRule) -> str:
        """Retorna nome legível da regra, usando campos alternativos se não existir 'name'."""
        return (
            getattr(rl, "name", None)
            or getattr(rl, "title", None)
            or getattr(rl, "label", None)
            or getattr(rl, "description", None)
            or f"Rule#{rl.id}"
        )
    
    # Filter out already-processed rows and track new ones when commit=True
    # Track by (model_name, sheet_name, row_id) tuple to allow same row_id in different sheets
    # For rows without __row_id, we can't track them, so they'll be processed
    rows_to_process = []
    skipped_count = 0
    
    for rec in rows:
        # Skip already-processed rows when commit=True
        if commit and model_name:
            rid_raw = rec.get("__row_id") if isinstance(rec, dict) else None
            if rid_raw is not None:
                rid_normalized = _norm_row_key(rid_raw)
                # Use (model_name, sheet_name, row_id) as the key to allow same row_id in different sheets
                # sheet_name can be None, which is fine - it will still differentiate sheets
                tracking_key = (model_name, sheet_name, rid_normalized)
                if tracking_key in processed_row_ids:
                    skipped_count += 1
                    logger.info(f"ETL SUBSTITUTION: Skipping already-processed row {rid_normalized} for {model_name} in sheet '{sheet_name}' (tracking_key={tracking_key})")
                    continue
                # Mark this row as being processed BEFORE substitution
                # This ensures we don't process the same row_id twice within the same sheet
                processed_row_ids.add(tracking_key)
            # If row has no __row_id, we can't track it, so it will be processed
            # This is intentional - rows without IDs might be legitimate duplicates
        
        rows_to_process.append(rec)
    
    if skipped_count > 0:
        logger.info(f"ETL SUBSTITUTION: Skipped {skipped_count} already-processed rows for {model_name} in sheet '{sheet_name}' (tracking by (model_name, sheet_name, row_id))")
    
    # Process only the rows that haven't been processed yet
    rows = rows_to_process
    
    for rec in rows:
        # dicionários: usar __row_id e campos nomeados
        if isinstance(rec, dict):
            rid = rec.get("__row_id")
            # regras por model/field
            for (mdl, fld), rule_list in grouped["model_field"].items():
                if mdl == model_name and fld in rec:
                    original = rec[fld]
                    
                    # Check cache first - if we've already substituted this value, reuse it
                    if model_name and fld:
                        if model_name in substitution_cache and fld in substitution_cache[model_name]:
                            field_cache = substitution_cache[model_name][fld]
                            # Check if this original value has been cached (handles None correctly)
                            if original in field_cache:
                                cached_value = field_cache[original]
                                # Found in cache, use cached substitution
                                if cached_value != original:
                                    rec[fld] = cached_value
                                    if return_audit:
                                        audit.append({
                                            "__row_id": rid,
                                            "field": fld,
                                            "old": original,
                                            "new": cached_value,
                                            "rule_id": None,
                                            "rule_name": "Cached substitution",
                                        })
                                continue  # Skip rule evaluation, use cached value
                    
                    # Not in cache, apply rules
                    new_value = original
                    applied_rule = None
                    for rl in rule_list:
                        _t0 = time.perf_counter()
                        apply, new_value = _should_apply_rule(rec, rl, fld, rec[fld])
                        rule_time[rl.id] += time.perf_counter() - _t0
                        rule_hits[rl.id] += 1
                        if apply:
                            applied_rule = rl
                            break
                    
                    # Cache the substitution result if it changed
                    if new_value != original and model_name and fld:
                        if model_name not in substitution_cache:
                            substitution_cache[model_name] = {}
                        if fld not in substitution_cache[model_name]:
                            substitution_cache[model_name][fld] = {}
                        substitution_cache[model_name][fld][original] = new_value
                        logger.debug(f"ETL SUBSTITUTION: Cached substitution for {model_name}.{fld}: '{original}' -> '{new_value}'")
                    
                    if new_value != original:
                        rec[fld] = new_value
                        if return_audit:
                            audit.append({
                                "__row_id": rid,
                                "field": fld,
                                "old": original,
                                "new": new_value,
                                "rule_id": applied_rule.id if applied_rule else None,
                                "rule_name": _rule_name(applied_rule) if applied_rule else "Unknown",
                            })
            # regras por column_name
            for col, rule_list in grouped["column_name"].items():
                if col in rec:
                    original = rec[col]
                    
                    # Check cache first - if we've already substituted this value, reuse it
                    if model_name and col:
                        if model_name in substitution_cache and col in substitution_cache[model_name]:
                            field_cache = substitution_cache[model_name][col]
                            # Check if this original value has been cached (handles None correctly)
                            if original in field_cache:
                                cached_value = field_cache[original]
                                # Found in cache, use cached substitution
                                if cached_value != original:
                                    rec[col] = cached_value
                                    if return_audit:
                                        audit.append({
                                            "__row_id": rid,
                                            "field": col,
                                            "old": original,
                                            "new": cached_value,
                                            "rule_id": None,
                                            "rule_name": "Cached substitution",
                                        })
                                continue  # Skip rule evaluation, use cached value
                    
                    # Not in cache, apply rules
                    new_value = original
                    applied_rule = None
                    for rl in rule_list:
                        _t0 = time.perf_counter()
                        apply, new_value = _should_apply_rule(rec, rl, col, rec[col])
                        rule_time[rl.id] += time.perf_counter() - _t0
                        rule_hits[rl.id] += 1
                        if apply:
                            applied_rule = rl
                            break
                    
                    # Cache the substitution result if it changed
                    if new_value != original and model_name and col:
                        if model_name not in substitution_cache:
                            substitution_cache[model_name] = {}
                        if col not in substitution_cache[model_name]:
                            substitution_cache[model_name][col] = {}
                        substitution_cache[model_name][col][original] = new_value
                        logger.debug(f"ETL SUBSTITUTION: Cached substitution for {model_name}.{col}: '{original}' -> '{new_value}'")
                    
                    if new_value != original:
                        rec[col] = new_value
                        if return_audit:
                            audit.append({
                                "__row_id": rid,
                                "field": col,
                                "old": original,
                                "new": new_value,
                                "rule_id": applied_rule.id if applied_rule else None,
                                "rule_name": _rule_name(applied_rule) if applied_rule else "Unknown",
                            })
        # listas ou tuplas: usar índices
        elif isinstance(rec, (list, tuple)):
            # converter tupla para lista para permitir mutação
            if isinstance(rec, tuple):
                rec = list(rec)
                rows[rows.index(rec)] = rec  # atualiza referência
            for idx, rule_list in grouped["column_index"].items():
                if idx < len(rec):
                    original = rec[idx]
                    for rl in rule_list:
                        # constrói um dict simplificado para avaliar conditions (campo fictício col_x)
                        _t0 = time.perf_counter()
                        row_dict_for_cond = {f"col_{i}": rec[i] for i in range(len(rec))}
                        apply, new_value = _should_apply_rule(row_dict_for_cond, rl, f"col_{idx}", rec[idx])
                        rule_time[rl.id] += time.perf_counter() - _t0
                        rule_hits[rl.id] += 1
                        if apply:
                            if new_value != original:
                                rec[idx] = new_value
                                if return_audit:
                                    audit.append({
                                        "__row_id": None,
                                        "field": f"col_{idx}",
                                        "old": original,
                                        "new": new_value,
                                        "rule_id": rl.id,
                                        "rule_name": _rule_name(rl),
                                    })
                            break
    # Log profiling results if there are any rules
    prof_total = time.perf_counter() - prof_start
    if rule_time and prof_total > 0.01:
        logger.info(f"ETL SUBSTITUTION PROFILE: Total time {prof_total:.3f}s for {len(rows)} rows ({prof_total/len(rows)*1000:.2f}ms per row)")
        # Sort rules by total time
        sorted_rules = sorted(rule_time.items(), key=lambda x: x[1], reverse=True)
        for rule_id, total_time in sorted_rules[:10]:  # Top 10 slowest rules
            hits = rule_hits.get(rule_id, 0)
            avg_time = total_time / hits if hits > 0 else 0
            # Try to get rule name
            rule_name = f"Rule#{rule_id}"
            try:
                for rl in rules_list:
                    if rl.id == rule_id:
                        rule_name = _rule_name(rl)
                        break
            except:
                pass
            logger.info(f"ETL SUBSTITUTION PROFILE: Rule {rule_name} (id={rule_id}): {hits} hits, {total_time:.3f}s total, {avg_time*1000:.2f}ms avg")
    return (rows, audit) if return_audit else rows

def apply_substitutions2(payload, company_id, model_name=None, field_names=None,
                        column_names=None):
    if not company_id:
        raise ValueError("Company ID is required for substitutions.")

    from multitenancy.models import SubstitutionRule
    rules = SubstitutionRule.objects.filter(company_id=company_id)
    
    if model_name:
        rules = rules.filter(model_name=model_name)
    if field_names:
        rules = rules.filter(field_name__in=field_names)
    
    grouped = {
        "model_field": {},
        "column_name": {},
        "column_index": {},
    }
    
    
    for rule in rules:
        if rule.model_name and rule.field_name:
            key = (rule.model_name, rule.field_name)
            grouped["model_field"].setdefault(key, []).append(rule)
        elif rule.column_name:
            grouped["column_name"].setdefault(rule.column_name, []).append(rule)
        elif rule.column_index is not None:
            grouped["column_index"].setdefault(rule.column_index, []).append(rule)

    for rec in payload:
        # Caso dicionário
        if isinstance(rec, dict):
            # aplica regras model/field
            for (mdl, fld), rule_list in grouped["model_field"].items():
                if model_name == mdl and fld in rec:
                    value = rec[fld]
                    for rl in rule_list:
                        if rl.match_type == 'exact' and value == rl.match_value:
                            rec[fld] = rl.substitution_value
                            break
                        if rl.match_type == 'regex' and re.match(rl.match_value, str(value)):
                            rec[fld] = re.sub(rl.match_value, rl.substitution_value, str(value))
                            break
                        if rl.match_type == 'caseless':
                            if _normalize(value) == _normalize(rl.match_value):
                                rec[fld] = rl.substitution_value
                                break
            # aplica regras por column_name
            for col_name, rule_list in grouped["column_name"].items():
                if col_name in rec:
                    value = rec[col_name]
                    for rl in rule_list:
                        if rl.match_type == 'exact' and value == rl.match_value:
                            rec[col_name] = rl.substitution_value
                            break
                        if rl.match_type == 'regex' and re.match(rl.match_value, str(value)):
                            rec[col_name] = re.sub(rl.match_value, rl.substitution_value, str(value))
                            break
                        if rl.match_type == 'caseless':
                            if _normalize(value) == _normalize(rl.match_value):
                                rec[col_name] = rl.substitution_value
                                break
        # Caso lista/tupla
        elif isinstance(rec, (list, tuple)):
            for idx, rule_list in grouped["column_index"].items():
                if idx < len(rec):
                    value = rec[idx]
                    for rl in rule_list:
                        if rl.match_type == 'exact' and value == rl.match_value:
                            rec[idx] = rl.substitution_value
                            break
                        if rl.match_type == 'regex' and re.match(rl.match_value, str(value)):
                            rec[idx] = re.sub(rl.match_value, rl.substitution_value, str(value))
                            break
                        if rl.match_type == 'caseless':
                            if _normalize(value) == _normalize(rl.match_value):
                                rec[idx] = rl.substitution_value
                                break

    return payload

SAFE_FUNCTIONS = {
    "debug_log": debug_log,
    "sum": sum,
    "len": len,
    "str": str,
    "int": int,
    "float": float,
    "dict": dict,
    "today": lambda: datetime.now(timezone.utc).date(),
    "sum_group": sum_group,
    "max_group": max_group,
    "min_group": min_group,
    "first": first,
    "last": last,
    "to_decimal": to_decimal,
    "apply_substitutions": apply_substitutions,
}

class FormulaEvaluationError(Exception):
    pass

def evaluate_expression(expression, context=None):
    import traceback
    if context is None:
        context = {}

    add_debug_message(f"[DEBUG] evaluate_expression called with expression: {expression}")
    add_debug_message(f"[DEBUG] Initial context keys: {list(context.keys())}")

    def _eval(node, local_context):
        from ast import (
            Expression, BinOp, UnaryOp, BoolOp, Compare, IfExp, Name, Constant,
            Dict, Subscript, Call, ListComp, GeneratorExp
        )

        add_debug_message(f"\n  [DEBUG] _eval on node: {ast.dump(node)}")
        add_debug_message(f"  [DEBUG] node type: {type(node).__name__}")
        add_debug_message(f"  [DEBUG] local_context keys: {list(local_context.keys())}")

        if isinstance(node, Expression):
            add_debug_message("  [DEBUG] Evaluating ast.Expression node")
            return _eval(node.body, local_context)
        elif isinstance(node, BinOp):
            op_type = type(node.op)
            add_debug_message(f"  [DEBUG] BinOp with operator: {op_type.__name__}")
            if op_type not in SAFE_OPERATORS:
                raise FormulaEvaluationError(f"Binary operator '{op_type}' not allowed.")
            left_val = _eval(node.left, local_context)
            right_val = _eval(node.right, local_context)
            add_debug_message(f"  [DEBUG] BinOp: left_val={left_val}, right_val={right_val}")
            return SAFE_OPERATORS[op_type](left_val, right_val)

        elif isinstance(node, UnaryOp):
            op_type = type(node.op)
            add_debug_message(f"  [DEBUG] UnaryOp with operator: {op_type.__name__}")
            if op_type not in SAFE_UNARY_OPS:
                raise FormulaEvaluationError(f"Unary operator '{op_type}' not allowed.")
            operand_val = _eval(node.operand, local_context)
            add_debug_message(f"  [DEBUG] operand_val={operand_val}")
            return SAFE_UNARY_OPS[op_type](operand_val)

        elif isinstance(node, BoolOp):
            op_type = type(node.op)
            add_debug_message(f"  [DEBUG] BoolOp with operator: {op_type.__name__}")
            if op_type not in SAFE_BOOL_OPS:
                raise FormulaEvaluationError(f"Boolean operator '{op_type}' not allowed.")
            values = [_eval(v, local_context) for v in node.values]
            add_debug_message(f"  [DEBUG] BoolOp values={values}")
            return SAFE_BOOL_OPS[op_type](values)

        elif isinstance(node, Compare):
            add_debug_message(f"  [DEBUG] Compare node with operators: {[type(o).__name__ for o in node.ops]}")
            if len(node.ops) != 1 or len(node.comparators) != 1:
                raise FormulaEvaluationError("Chained comparisons not allowed.")
            op_type = type(node.ops[0])
            if op_type not in SAFE_COMPARISONS:
                raise FormulaEvaluationError(f"Comparison operator '{op_type}' not allowed.")
            left_val = _eval(node.left, local_context)
            right_val = _eval(node.comparators[0], local_context)
            add_debug_message(f"  [DEBUG] Compare: left_val={left_val}, right_val={right_val}")
            return SAFE_COMPARISONS[op_type](left_val, right_val)

        elif isinstance(node, IfExp):
            add_debug_message("  [DEBUG] IfExp (ternary) node")
            condition_val = _eval(node.test, local_context)
            add_debug_message(f"  [DEBUG] condition_val={condition_val}")
            return _eval(node.body if condition_val else node.orelse, local_context)

        elif isinstance(node, Name):
            add_debug_message(f"  [DEBUG] Name lookup: {node.id}")
            if node.id in local_context:
                val = local_context[node.id]
                add_debug_message(f"  [DEBUG] Found in local_context: {node.id} -> {val}")
                return val
            raise FormulaEvaluationError(f"Variable '{node.id}' is not defined.")

        elif isinstance(node, Constant):
            add_debug_message(f"  [DEBUG] Constant value: {node.value}")
            return node.value

        elif isinstance(node, Dict):
            add_debug_message(f"  [DEBUG] Dict node, {len(node.keys)} key-value pairs")
            return {
                _eval(k, local_context): _eval(v, local_context)
                for k, v in zip(node.keys, node.values)
            }

        elif isinstance(node, Subscript):
            add_debug_message("  [DEBUG] Subscript node")
            value = _eval(node.value, local_context)
            sl = _eval(node.slice, local_context)
            add_debug_message(f"  [DEBUG] Attempting subscript on value={value} with slice={sl}")
            try:
                return value[sl]
            except (TypeError, KeyError, IndexError) as ex:
                raise FormulaEvaluationError(f"Invalid subscript access: {ex}")

        elif isinstance(node, Call):
            add_debug_message("  [DEBUG] Call node")
            func = node.func
            if not isinstance(func, Name):
                raise FormulaEvaluationError("Only direct function calls (by name) are allowed.")
            func_name = func.id
            add_debug_message(f"  [DEBUG] Function call to: {func_name}")
            if func_name not in SAFE_FUNCTIONS:
                raise FormulaEvaluationError(f"Call to function '{func_name}' is not allowed.")
            args = [_eval(arg, local_context) for arg in node.args]
            add_debug_message(f"  [DEBUG] Function call args={args}")
            if node.keywords:
                raise FormulaEvaluationError("Keyword arguments not supported.")
            return SAFE_FUNCTIONS[func_name](*args)

        elif isinstance(node, ListComp):
            add_debug_message("  [DEBUG] ListComp node")
            return _eval_listcomp(node, local_context)

        elif isinstance(node, GeneratorExp):
            add_debug_message("  [DEBUG] GeneratorExp node")
            return _eval_genexp(node, local_context)

        else:
            raise FormulaEvaluationError(f"Unsupported expression: {ast.dump(node)}")

    def _eval_listcomp(node: ast.ListComp, local_context):
        add_debug_message("  [DEBUG] _eval_listcomp entered")
        if len(node.generators) != 1:
            raise FormulaEvaluationError("Nested/multiple list comprehensions not allowed.")
        comp = node.generators[0]
        iterable_val = _eval(comp.iter, local_context)
        add_debug_message(f"  [DEBUG] listcomp: iterable_val={iterable_val}")
        if not isinstance(iterable_val, (list, tuple)):
            raise FormulaEvaluationError("Comprehension can only iterate over list/tuple.")

        result = []
        for i, item in enumerate(iterable_val):
            add_debug_message(f"  [DEBUG] ListComp loop {i}: item={item}")
            child_context = dict(local_context)
            if isinstance(comp.target, ast.Name):
                child_context[comp.target.id] = item
            else:
                raise FormulaEvaluationError("Only simple variable targets in comps are allowed.")

            skip = False
            for if_node in comp.ifs:
                if_val = _eval(if_node, child_context)
                add_debug_message(f"    [DEBUG] if_val={if_val} -> {'SKIP' if not if_val else 'KEEP'}")
                if not if_val:
                    skip = True
                    break
            if skip:
                continue

            elt_val = _eval(node.elt, child_context)
            add_debug_message(f"    [DEBUG] elt_val={elt_val}")
            result.append(elt_val)
        return result

    def _eval_genexp(node: ast.GeneratorExp, local_context):
        add_debug_message("  [DEBUG] _eval_genexp entered")
        if len(node.generators) != 1:
            raise FormulaEvaluationError("Nested generator expressions not allowed.")
        comp = node.generators[0]
        iterable_val = _eval(comp.iter, local_context)
        add_debug_message(f"  [DEBUG] genexp: iterable_val={iterable_val}")
        if not isinstance(iterable_val, (list, tuple)):
            raise FormulaEvaluationError("GeneratorExp can only iterate over list/tuple.")

        result = []
        for i, item in enumerate(iterable_val):
            add_debug_message(f"  [DEBUG] GenExp loop {i}: item={item}")
            child_context = dict(local_context)
            if isinstance(comp.target, ast.Name):
                child_context[comp.target.id] = item
            else:
                raise FormulaEvaluationError("Only simple variable targets in generator expr.")

            skip = False
            for if_node in comp.ifs:
                if_val = _eval(if_node, child_context)
                add_debug_message(f"    [DEBUG] if_val={if_val} -> {'SKIP' if not if_val else 'KEEP'}")
                if not if_val:
                    skip = True
                    break
            if skip:
                continue

            elt_val = _eval(node.elt, child_context)
            add_debug_message(f"    [DEBUG] elt_val={elt_val}")
            result.append(elt_val)
        return result

    from ast import parse
    try:
        parsed = parse(expression, mode='eval')
        add_debug_message("[DEBUG] AST successfully parsed for expression.")
    except SyntaxError as e:
        raise FormulaEvaluationError(f"Syntax error: {e}")

    evaluated_result = _eval(parsed.body, context)
    add_debug_message(f"[DEBUG] Final evaluated_result: {evaluated_result}")
    return evaluated_result


def group_by(data, field):
    grouped = defaultdict(list)
    for item in data:
        grouped[item[field]].append(item)
    return [{"group": key, "items": items} for key, items in grouped.items()]


def create_transaction(transaction_template, context):
    add_debug_message("\n🔄 DEBUG: create_transaction called with:")
    print("transaction_template:", transaction_template)

    transaction_data = {}
    for key, value in transaction_template.items():
        # 1) If the value is a string, we treat it as an expression
        if isinstance(value, str):
            add_debug_message(f"  [DEBUG] Evaluating field '{key}' with expression: {value}")
            evaluated = evaluate_expression(value, context)

            transaction_data[key] = evaluated

        # 2) If it's not a string expression:
        else:
            # (Example) If 'amount' can be an int, float, or Decimal but never a dict
            if key == 'amount':
                if isinstance(value, (int, float, Decimal)):
                    value = to_decimal(value, 2)
                elif isinstance(value, dict):
                    raise ValueError(
                        f"[create_transaction] Field '{key}' cannot be a dictionary. "
                        f"Expected numeric value, got: {value}"
                    )
                transaction_data[key] = value

            else:
                # If your business logic only allows scalars (int/float/str/None), disallow dict
                if isinstance(value, dict):
                    raise ValueError(
                        f"[create_transaction] Field '{key}' cannot be a dictionary. "
                        f"Got: {value}"
                    )
                transaction_data[key] = value

    # By now, transaction_data has no unexpected dicts
    add_debug_message(f"  [DEBUG] transaction_data after evaluation: {transaction_data}")

    serializer = TransactionSerializer(data=transaction_data)
    if serializer.is_valid(raise_exception=True):
        transaction = serializer.save()
        add_debug_message(f"✅ DEBUG: Transaction created successfully: {transaction}")
        if not transaction:
            raise ValueError("Transaction creation returned None.")
        return transaction

    add_debug_message("❌ DEBUG: Transaction creation failed during validation.")
    raise ValueError("Transaction creation failed due to validation errors.")


def create_journal_entry(transaction, entry_template, context):
    add_debug_message("\n🔄 DEBUG: create_journal_entry called with:")
    add_debug_message(str(entry_template))

    entry_data = {}
    for key, value in entry_template.items():
        if isinstance(value, str):
            add_debug_message(f"  [DEBUG] Evaluating field '{key}' with expression: {value}")
            entry_data[key] = evaluate_expression(value, context)
        else:
            if key in ['credit_amount', 'debit_amount']:
                if isinstance(value, (int, float, Decimal)):
                    value = to_decimal(value, 2)
            entry_data[key] = value

    entry_data['transaction'] = transaction.id
    entry_data['company'] = transaction.company.id

    add_debug_message(f"  [DEBUG] entry_data after evaluation: {entry_data}")

    serializer = JournalEntrySerializer(data=entry_data)
    if serializer.is_valid(raise_exception=True):
        journal_entry = serializer.save()
        add_debug_message(f"✅ DEBUG: Journal Entry created successfully: {journal_entry}")
        if not journal_entry:
            raise ValueError("Journal entry creation returned None.")
        return journal_entry

    add_debug_message("❌ DEBUG: Journal Entry creation failed during validation.")
    raise ValueError("Journal entry creation failed due to validation errors.")


def execute_rule(company_id: int, rule: str, payload: list):
    """
    Safely execute a rule using a sandboxed environment.
    If an error occurs, print the entire debug log + traceback.
    """
    import traceback

    debug_logs.clear()
    add_debug_message("[DEBUG] About to parse rule for syntax checking.")

    try:
        ast.parse(rule)
    except SyntaxError as e:
        add_debug_message(f"Syntax Error in rule: {e}")
        debug_output = "\n".join(debug_logs)
        print(debug_output)
        raise ValueError(f"Syntax Error in rule: {e}")

    context = {
        "payload": payload,
        "result": None,
        "group_by": group_by,
        "create_transaction": create_transaction,
        "create_journal_entry": create_journal_entry,
        "apply_substitutions": lambda model, fields=None: apply_substitutions(
            payload, model, field_names=fields, company_id=company_id
        ),
        "sum": sum,
        "len": len,
        "str": str,
        "int": int,
        "float": float,
        "abs": abs,
        "Decimal": Decimal,
        "sum_group": sum_group,
        "max_group": max_group,
        "min_group": min_group,
        "debug_log": debug_log,
        "to_decimal": to_decimal,
        "company_id": company_id,
        # Account lookup helpers
        "lookup_account_by_path": lambda path, sep=' > ': lookup_account_by_path(path, company_id, sep),
        "lookup_account_by_code": lambda code: lookup_account_by_code(code, company_id),
        "lookup_account_by_name": lambda name: lookup_account_by_name(name, company_id),
        "calculate_debit_credit": calculate_debit_credit,
        # Transaction + JournalEntries creation helper
        "create_transaction_with_entries": lambda payload: create_transaction_with_entries(payload, company_id),
        # Models for direct access
        "Account": Account,
        "Transaction": Transaction,
        "JournalEntry": JournalEntry,
    }

    exec_env = {"__builtins__": None, "context": context}
    exec_env.update(context)

    try:
        add_debug_message("\n🔍 DEBUG: Context before execution:")
        add_debug_message(str(context))
        exec(rule, exec_env, exec_env)
    except Exception as e:
        debug_output = "\n".join(debug_logs)
        full_tb = traceback.format_exc()  # capture the full traceback
        print("[DEBUG] An exception occurred during rule execution!")
        print("[DEBUG] Current debug log:\n", debug_output)
        print("[DEBUG] Full traceback:\n", full_tb)
        raise ValueError(f"Unexpected error during rule execution: {e}\nFull traceback:\n{full_tb}")

    if "result" not in exec_env or exec_env["result"] is None:
        debug_output = "\n".join(debug_logs)
        print(debug_output)
        raise ValueError("Rule executed successfully, but 'result' was not set in the context.")

    return exec_env["result"]


def trigger_rule_event(company: int, event_name: str, payload) -> None:
    if isinstance(payload, dict):
        payload = [payload]
    
    rules = IntegrationRule.objects.filter(
        company_id=company,
        trigger_event=event_name,
        is_active=True
    ).order_by("execution_order")

    for rule in rules:
        try:
            rule.run_rule(payload)
        except Exception as e:
            print(f"Rule {rule.name} failed: {e}")







# Mock data dictionary
MOCK_DATA = {
    "Company": [
        {"id": 100001, "name": "Company A", "subdomain": "compa"},
    ],
    "Position": [
        {"id": 100001, "company_id": 100001, "title": "Manager", "department": "HR", "min_salary": 5000, "max_salary": 10000},
        {"id": 100002, "company_id": 100001, "title": "Developer", "department": "IT", "min_salary": 3000, "max_salary": 7000},
        {"id": 100003, "company_id": 100001, "title": "Analyst", "department": "Finance", "min_salary": 4000, "max_salary": 8000},
        {"id": 100004, "company_id": 100001, "title": "Designer", "department": "Marketing", "min_salary": 3500, "max_salary": 7500},
        {"id": 100005, "company_id": 100001, "title": "Tester", "department": "QA", "min_salary": 3000, "max_salary": 6000},
        {"id": 100006, "company_id": 100001, "title": "Administrator", "department": "IT", "min_salary": 4000, "max_salary": 9000},
        {"id": 100007, "company_id": 100001, "title": "Consultant", "department": "Consulting", "min_salary": 6000, "max_salary": 12000},
        {"id": 100008, "company_id": 100001, "title": "Engineer", "department": "Engineering", "min_salary": 5000, "max_salary": 10000},
        {"id": 100009, "company_id": 100001, "title": "Coordinator", "department": "Operations", "min_salary": 4500, "max_salary": 8500},
        {"id": 1000010, "company_id": 100001, "title": "Specialist", "department": "R&D", "min_salary": 5500, "max_salary": 9500}
    ],
    "Employee": [
        {"id": 100001, "name": "Alice", "CPF": "123.456.789-00", "position_id": 100001, "hire_date": "2023-01-15", "salary": 5500, "company_id": 100001, "is_active": True},
        {"id": 100002, "name": "Bob", "CPF": "234.567.890-11", "position_id": 100002, "hire_date": "2022-06-01", "salary": 4500, "company_id": 100001, "is_active": True},
        {"id": 100003, "name": "Charlie", "CPF": "345.678.901-22", "position_id": 100003, "hire_date": "2023-03-01", "salary": 6000, "company_id": 100001, "is_active": True},
        {"id": 100004, "name": "Diana", "CPF": "456.789.012-33", "position_id": 100004, "hire_date": "2022-07-01", "salary": 4800, "company_id": 100001, "is_active": True},
        {"id": 100005, "name": "Eve", "CPF": "567.890.123-44", "position_id": 100005, "hire_date": "2023-05-15", "salary": 3200, "company_id": 100001, "is_active": True},
        {"id": 100006, "name": "Frank", "CPF": "678.901.234-55", "position_id": 100006, "hire_date": "2021-12-01", "salary": 7000, "company_id": 100001, "is_active": True},
        {"id": 100007, "name": "Grace", "CPF": "789.012.345-66", "position_id": 100007, "hire_date": "2023-02-15", "salary": 8000, "company_id": 100001, "is_active": True},
        {"id": 100008, "name": "Henry", "CPF": "890.123.456-77", "position_id": 100008, "hire_date": "2023-06-01", "salary": 6000, "company_id": 100001, "is_active": True},
        {"id": 100009, "name": "Ivy", "CPF": "901.234.567-88", "position_id": 100009, "hire_date": "2022-11-01", "salary": 5000, "company_id": 100001, "is_active": True},
        {"id": 1000010, "name": "Jack", "CPF": "012.345.678-99", "position_id": 1000010, "hire_date": "2023-08-01", "salary": 7000, "company_id": 100001, "is_active": True}
    ],
    "TimeTracking": [
        {"id": 100001, "employee_id": 100001, "month_date": "2023-09-01", "total_hours_worked": 160, "days_present": 20, "days_absent": 0, "company_id": 100001},
        {"id": 100002, "employee_id": 100002, "month_date": "2023-09-01", "total_hours_worked": 150, "days_present": 18, "days_absent": 2, "company_id": 100001},
        {"id": 100003, "employee_id": 100003, "month_date": "2023-09-01", "total_hours_worked": 170, "days_present": 22, "days_absent": 0, "company_id": 100001},
        {"id": 100004, "employee_id": 100004, "month_date": "2023-09-01", "total_hours_worked": 140, "days_present": 16, "days_absent": 4, "company_id": 100001},
        {"id": 100005, "employee_id": 100005, "month_date": "2023-09-01", "total_hours_worked": 160, "days_present": 20, "days_absent": 0, "company_id": 100001},
        {"id": 100006, "employee_id": 100006, "month_date": "2023-09-01", "total_hours_worked": 150, "days_present": 18, "days_absent": 2, "company_id": 100001},
        {"id": 100007, "employee_id": 100007, "month_date": "2023-09-01", "total_hours_worked": 180, "days_present": 22, "days_absent": 0, "company_id": 100001},
        {"id": 100008, "employee_id": 100008, "month_date": "2023-09-01", "total_hours_worked": 155, "days_present": 19, "days_absent": 1, "company_id": 100001},
        {"id": 100009, "employee_id": 100009, "month_date": "2023-09-01", "total_hours_worked": 160, "days_present": 20, "days_absent": 0, "company_id": 100001},
        {"id": 1000010, "employee_id": 1000010, "month_date": "2023-09-01", "total_hours_worked": 160, "days_present": 20, "days_absent": 0, "company_id": 100001}
    ],
    "Payroll": [
        {"id": 100001, "employee_id": 100001, "company_id": 100001, "pay_date": "2023-09-30", "gross_salary": 5500.00, "inss_deduction": 440.00, "irrf_deduction": 385.00, "fgts": 440.00, "net_salary": 4625.00, "bonus": 9.50, "bank_hours": 0.00, "absence_deduction": 0.00, "adjustment_details": {}, "status": "approved"},
        {"id": 100002, "employee_id": 100002, "company_id": 100001, "pay_date": "2023-09-30", "gross_salary": 4500.00, "inss_deduction": 360.00, "irrf_deduction": 275.00, "fgts": 360.00, "net_salary": 3865.00, "bonus": 9.00, "bank_hours": 0.00, "absence_deduction": 50.00, "adjustment_details": {}, "status": "approved"},
        {"id": 100003, "employee_id": 100001, "company_id": 100001, "pay_date": "2023-08-31", "gross_salary": 5500.00, "inss_deduction": 440.00, "irrf_deduction": 385.00, "fgts": 440.00, "net_salary": 4625.00, "bonus": 9.50, "bank_hours": 0.00, "absence_deduction": 0.00, "adjustment_details": {}, "status": "approved"},
        {"id": 100004, "employee_id": 100002, "company_id": 100001, "pay_date": "2023-08-31", "gross_salary": 4500.00, "inss_deduction": 360.00, "irrf_deduction": 275.00, "fgts": 360.00, "net_salary": 3865.00, "bonus": 9.00, "bank_hours": 0.00, "absence_deduction": 50.00, "adjustment_details": {}, "status": "approved"},
        {"id": 100005, "employee_id": 100001, "company_id": 100001, "pay_date": "2023-07-31", "gross_salary": 5500.00, "inss_deduction": 440.00, "irrf_deduction": 385.00, "fgts": 440.00, "net_salary": 4625.00, "bonus": 9.50, "bank_hours": 0.00, "absence_deduction": 0.00, "adjustment_details": {}, "status": "approved"},
        {"id": 100006, "employee_id": 100002, "company_id": 100001, "pay_date": "2023-07-31", "gross_salary": 4500.00, "inss_deduction": 360.00, "irrf_deduction": 275.00, "fgts": 360.00, "net_salary": 3865.00, "bonus": 9.00, "bank_hours": 0.00, "absence_deduction": 50.00, "adjustment_details": {}, "status": "approved"},
        {"id": 100007, "employee_id": 100001, "company_id": 100001, "pay_date": "2023-06-30", "gross_salary": 5500.00, "inss_deduction": 440.00, "irrf_deduction": 385.00, "fgts": 440.00, "net_salary": 4625.00, "bonus": 9.50, "bank_hours": 0.00, "absence_deduction": 0.00, "adjustment_details": {}, "status": "approved"},
        {"id": 100008, "employee_id": 100002, "company_id": 100001, "pay_date": "2023-06-30", "gross_salary": 4500.00, "inss_deduction": 360.00, "irrf_deduction": 275.00, "fgts": 360.00, "net_salary": 3865.00, "bonus": 9.00, "bank_hours": 0.00, "absence_deduction": 50.00, "adjustment_details": {}, "status": "approved"},
        {"id": 100009, "employee_id": 100001, "company_id": 100001, "pay_date": "2023-05-31", "gross_salary": 5500.00, "inss_deduction": 440.00, "irrf_deduction": 385.00, "fgts": 440.00, "net_salary": 4625.00, "bonus": 9.50, "bank_hours": 0.00, "absence_deduction": 0.00, "adjustment_details": {}, "status": "approved"},
        {"id": 1000010, "employee_id": 100002, "company_id": 100001, "pay_date": "2023-05-31", "gross_salary": 4500.00, "inss_deduction": 360.00, "irrf_deduction": 275.00, "fgts": 360.00, "net_salary": 3865.00, "bonus": 9.00, "bank_hours": 0.00, "absence_deduction": 50.00, "adjustment_details": {}, "status": "approved"}
    ],
}

# Mock generation function
def generate_mock_data(trigger, special_functions, num_records=10):
    """
    Generate setupData and payload for testing based on trigger and special functions.
    :param trigger: The event trigger (e.g., "payroll_created").
    :param special_functions: List of special functions used in the rule.
    :param num_records: Number of records to return for the payload.
    :return: Dict containing setupData and payload.
    """
    # Define model dependencies per trigger
    trigger_dependencies = {
        "payroll_created": ["Company", "Employee", "TimeTracking", "KPI"],
        "payroll_approved": ["Company", "Employee", "TimeTracking"],
    }
    
    trigger_payload = {
        "payroll_created": "Payroll",
        "payroll_approved": "Payroll",
    }
    
    # Define special function dependencies
    function_dependencies = {
        "create_transaction": ["Company", "Employee", "Position"],
        "apply_substitutions": ["Company", "Employee"],
        "group_by": ["Employee", "TimeTracking"],
    }

    # Combine dependencies from trigger and special functions
    required_models = set(trigger_dependencies.get(trigger, []))
    for func in special_functions:
        required_models.update(function_dependencies.get(func, []))

    # Generate setupData
    setup_data = {}
    for model in required_models:
        if model in MOCK_DATA:
            setup_data[model] = MOCK_DATA[model]

    # Generate payload based on the trigger
    print('MOCK_DATA:', trigger_payload.get(trigger, []))
    payload = MOCK_DATA.get(trigger_payload.get(trigger, []))[:num_records]

    return {"setupData": setup_data, "payload": payload}


def apply_setup_data(setup_data):
    if isinstance(setup_data, str):
        setup_data_dict = {}
        for line in setup_data.splitlines():
            line = line.strip()
            
            if line.startswith("cls.") and "=" in line:
                try:
                    model_key = line.split("=")[0].strip().replace("cls.", "")
                except:
                    print('ERROR on line:', line)
                model_key = model_key.split("_")[0].strip()
                record = eval(line.split("=", 1)[1].strip())
                setup_data_dict.setdefault(model_key, []).append(record)
        setup_data = setup_data_dict
    
    for model_key, records in setup_data.items():
        try:
            model = apps.get_model(get_app_for_model(model_key), model_key)
        except ValueError:
            raise ValueError(f"Invalid model key format: {model_key}. Expected 'app_label.ModelName'.")

        for record in records:
            print('DEBUG: Trying to create record for:', model, record)
            obj = model.objects.create(**record)
        

def generate_mock_payload(trigger_event, num_records=10):
    """
    Generate mock payload for a given trigger event.

    Args:
        trigger_event (str): The trigger event.
        num_records (int): Number of records to include in the payload.

    Returns:
        list: Mock payload data.
    """
    # Predefined trigger-based payloads
    payloads = {
        "payroll_approved": MOCK_DATA["Employee"][:num_records],
        "payroll_created": MOCK_DATA["Employee"][:num_records],
        # Add more triggers as needed
    }
    return payloads.get(trigger_event, [])


def apply_payload(payload):

    payload_str = payload.split("=")[1].strip()
    parsed_payload = ast.literal_eval(payload_str)
    
    return parsed_payload

def validate_rule(trigger_event, rule, filter_conditions=None, num_records=10):
    """
    Validate the rule, apply filters, and propose mock data for setupData and payload.

    Args:
        trigger_event (str): The trigger event for the rule.
        rule (str): The rule to be validated.
        filter_conditions (str): Python expression for filtering payload records.
        num_records (int): Number of records to include in the payload.

    Returns:
        dict: Validation result with special functions, setupData, mockPayload, and filteredPayload.
    """
    try:
        # Check for syntax validity of the rule
        ast.parse(rule)
        syntax_valid = True
        print("syntax_valid:", syntax_valid)
    except SyntaxError as e:
        return {"error": f"Syntax error in rule: {e}"}

    # Validate the filter_conditions syntax if provided
    print('filter_conditions:', filter_conditions)
    if filter_conditions:
        try:
            print('erro')
            ast.parse(filter_conditions)
        except SyntaxError as e:
            return {"error": f"Syntax error in filter_conditions: {e}"}

    # Identify special functions used in the rule
    print("num_records:", num_records)
    special_functions = [func for func in SAFE_FUNCTIONS if func in rule]
    print("special_functions:", special_functions)

    # Generate setupData and payload
    mock_data_result = generate_mock_data(trigger_event, special_functions, num_records)
    setup_data = mock_data_result["setupData"]
    mock_payload = mock_data_result["payload"]

    # Apply filter_conditions to the payload
    filtered_payload = []
    if filter_conditions:
        context = {"record": None}
        for record in mock_payload:
            context["record"] = record
            print("record", record)
            try:
                if evaluate_expression(filter_conditions, context):
                    filtered_payload.append(record)
            except Exception as e:
                return {"error": f"Error evaluating filter_conditions: {e}"}
    else:
        filtered_payload = mock_payload
        
    return {
        "validation": {
            "syntax_valid": syntax_valid,
            "special_functions": special_functions,
        },
        "setupData": setup_data,
        "mockPayload": mock_payload,
        "filteredPayload": filtered_payload,
    }



def run_rule_in_sandbox(company_id, rule, setup_data, payload):
    import traceback

    setup_test_environment()
    start_time = time.time()
    execution_logs = []
    modified_records = []
    print('# Executando Run Rule in Sandbox')
    try:
        with transaction.atomic():
            print('########### Apply Setup Data')
            apply_setup_data(setup_data)
            print('########### Apply Setup Data - Executado')
            print('########### Apply Payload')
            payload = apply_payload(payload)
            print('########### Apply Payload - Executado')
            debug_logs.clear()
            clear_changes()

            # Execute the rule
            print('########### Execute Rule')
            result = execute_rule(company_id=company_id, rule=rule, payload=payload)
            print('########### Execute Rule - Executado')
            execution_logs = debug_logs
            modified_records = get_changes()

            # Force rollback
            raise ValueError("Rollback test execution (sandbox mode)")

    except ValueError as e:
        if str(e) == "Rollback test execution (sandbox mode)":
            execution_time = time.time() - start_time
            return {
                "executionLogs": execution_logs,
                "result": result,
                "modifiedRecords": modified_records,
                "executionTime": execution_time,
                "errors": None,
            }
        else:
            return {"errors": str(e), "executionLogs": debug_logs}

    except Exception as e:
        full_tb = traceback.format_exc()
        debug_output = "\n".join(debug_logs)
        print("[DEBUG] Exception in run_rule_in_sandbox!")
        print("[DEBUG] Current debug log:\n", debug_output)
        print("[DEBUG] Full traceback:\n", full_tb)
        return {
            "errors": f"{e}\nTraceback:\n{full_tb}",
            "executionLogs": debug_logs
        }

    finally:
        teardown_test_environment()
