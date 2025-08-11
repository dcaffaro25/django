from django.apps import apps
import random
import ast
import re
import operator
import threading
import time
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
#https://nordventures.retool.com/editor/b3e8e0c2-b631-11ef-8bb9-3381755dd0f7/Nord%20App/configuracoes

faker = Faker()

# Custom timeout exception
class TimeoutException(Exception):
    pass

# You can keep or remove the old timeout_handler here
def timeout_handler(seconds):
    def decorator(func):
        def wrapper(*args, **kwargs):
            result = [None]  # Use a mutable object to store the result
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

# If you want, you can clear them at the start of each rule execution.
# We'll do that in execute_rule.






# -------------------
# SAFE OPERATORS
# -------------------
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,          # If you want exponent
    ast.FloorDiv: operator.floordiv # If you want floor division
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


# Instead of printing directly, we'll store the debug messages:
def debug_log(*args):
    message = " ".join(str(a) for a in args)
    add_debug_message(message)

def to_decimal(value, places=2):
    """
    Convert 'value' to a decimal, then quantize to 'places' decimals.
    If it's invalid, we raise an error. Example usage:

       to_decimal('300.12345') -> Decimal('300.12')
       to_decimal(300) -> Decimal('300.00')

    """
    # Start with a Decimal
    dec_val = Decimal(str(value))  # ensures strings/floats are captured
    # Then quantize
    quant_str = "1." + ("0" * places)  # e.g. "1.00" if places=2
    return dec_val.quantize(Decimal(quant_str), rounding=ROUND_HALF_UP)

def apply_substitutions(payload, model_name, field_names=None, company_id=None):
    """
    Apply substitution rules to a dataset.
    
    field_names: list, optional
        Fields to consider for substitution. If None, all fields will be evaluated.
    """
    
    if not company_id:
        raise ValueError("Company ID is required for substitutions.")
    
    from multitenancy.models import SubstitutionRule
    
    rules = SubstitutionRule.objects.filter(company_id=company_id, model_name=model_name)
    
    if field_names:
        rules = rules.filter(field_name__in=field_names)
    
    substitutions = {}

    # Build substitution map
    for rule in rules:
        key = (rule.model_name, rule.field_name)
        if key not in substitutions:
            substitutions[key] = []
        substitutions[key].append(rule)

    # Apply substitutions
    for record in payload:
        for (model, field), rules in substitutions.items():
            if field in record:
                value = record[field]
                for rule in rules:
                    if rule.match_type == "exact" and value == rule.match_value:
                        record[field] = rule.substitution_value
                    elif rule.match_type == "regex" and re.match(rule.match_value, str(value)):
                        record[field] = re.sub(rule.match_value, rule.substitution_value, str(value))

    return payload

# Allowed built-in functions
SAFE_FUNCTIONS = {
    "debug_log": debug_log,
    "sum": sum,
    "len": len,
    "str": str,
    "int": int,
    "float": float,
    "dict": dict,  # only if you want to allow dict()
    "today": lambda: datetime.now(timezone.utc).date(),
    "sum_group": sum_group,
    "max_group": max_group,
    "min_group": min_group,
    "to_decimal": to_decimal,
    "apply_substitutions": apply_substitutions,  # Add apply_substitutions here
}

class FormulaEvaluationError(Exception):
    pass

def evaluate_expression(expression, context=None):
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
            except (TypeError, KeyError, IndexError) as e:
                raise FormulaEvaluationError(f"Invalid subscript access: {e}")

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

    # Parse & Evaluate
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
    add_debug_message(str(transaction_template))

    transaction_data = {}
    for key, value in transaction_template.items():
        if isinstance(value, str):
            add_debug_message(f"  [DEBUG] Evaluating field '{key}' with expression: {value}")
            transaction_data[key] = evaluate_expression(value, context)
        else:
            if key == 'amount' :
                # If numeric, convert to decimal
                if isinstance(value, (int, float, Decimal)):
                    value = to_decimal(value, 2)
            transaction_data[key] = value

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
            if key == 'credit_amount' or key == 'debit_amount':
                if isinstance(value, (int, float, Decimal)):
                    value = to_decimal(value, 2)
            entry_data[key] = value

    # Pass the PK, not the transaction object
    entry_data['transaction'] = transaction.id

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
    If an error occurs, print the entire debug log.
    """

    # Clear out old logs at the start
    debug_logs.clear()

    # We'll store logs from the parse checks, etc.
    add_debug_message(f"[DEBUG] About to parse rule for syntax checking.")

    try:
        ast.parse(rule)
    except SyntaxError as e:
        add_debug_message(f"Syntax Error in rule: {e}")
        # Print everything we have and then raise
        debug_output = "\n".join(debug_logs)
        print(debug_output)
        raise ValueError(f"Syntax Error in rule: {e}")

    # Create an isolated context
    context = {
        "payload": payload,
        "result": None,
        "group_by": group_by,
        "create_transaction": create_transaction,
        "create_journal_entry": create_journal_entry,
        "apply_substitutions": lambda model, fields=None: apply_substitutions(
            payload, model, field_names=fields, company_id=company_id
        ),  # Add the function here
        "sum": sum,
        "len": len,
        "str": str,
        "int": int,
        "float": float,
        "sum_group": sum_group,
        "max_group": max_group,
        "min_group": min_group,
        "debug_log": debug_log,
        "to_decimal": to_decimal,
        "company_id": company_id,
    }

    # Provide an exec environment
    exec_env = {"__builtins__": None, "context": context}
    exec_env.update(context)

    try:
        add_debug_message("\n🔍 DEBUG: Context before execution:")
        add_debug_message(str(context))

        exec(rule, exec_env, exec_env)

    except Exception as e:
        # If anything goes wrong, dump the logs and raise
        debug_output = "\n".join(debug_logs)
        print(debug_output)  # Display all accumulated logs
        raise ValueError(f"Unexpected error during rule execution: {e}")

    # Check `result`
    if "result" not in exec_env or exec_env["result"] is None:
        debug_output = "\n".join(debug_logs)
        print(debug_output)
        raise ValueError(
            "Rule executed successfully, but 'result' was not set in the context."
        )

    # If all is good, we can either discard or print logs.
    # Let's say we discard them (or you could print them).
    # debug_logs.clear()

    return exec_env["result"]


def trigger_rule_event(company: int, event_name: str, payload) -> None:
    """
    Central dispatcher for any event that might trigger IntegrationRules.

    1) Query all active IntegrationRules for the given event_name.
    2) For each, call rule.run_rule(payload).
    3) Handle or log any errors as desired.
    """
    if isinstance(payload, dict):
        payload = [payload]
    
    # 1) Get relevant rules
    rules = IntegrationRule.objects.filter(
        company_id=company,
        trigger_event=event_name,
        is_active=True
    ).order_by("execution_order")

    # 2) Run each rule
    for rule in rules:
        try:
            rule.run_rule(payload)
            # If you want to do something with the success result,
            # you can capture it: result = rule.run_rule(payload)
        except Exception as e:
            # Optionally log or handle the error here
            # so other rules still get a chance to run
            print(f"Rule {rule.name} failed: {e}")
            
            
            
            
from threading import local

# Thread-safe dictionary to store changes
_thread_local = local()
_thread_local.modified_records = {"created": [], "updated": [], "deleted": []}

from django.forms.models import model_to_dict
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

def log_change(instance, operation):
    model_name = instance._meta.label
    record = {
        "model": model_name,
        "id": instance.pk,
        "operation": operation,
        "data": model_to_dict(instance),
    }
    if not hasattr(_thread_local, "modified_records"):
        _thread_local.modified_records = {"created": [], "updated": [], "deleted": []}
    _thread_local.modified_records[operation].append(record)

@receiver(post_save)
def track_save(sender, instance, created, **kwargs):
    if hasattr(_thread_local, "modified_records"):
        if created:
            log_change(instance, "created")
        else:
            log_change(instance, "updated")

@receiver(post_delete)
def track_delete(sender, instance, **kwargs):
    if hasattr(_thread_local, "modified_records"):
        log_change(instance, "deleted")


def clear_modified_records():
    """Clear the stored modified records."""
    if hasattr(_thread_local, "modified_records"):
        _thread_local.modified_records = {"created": [], "updated": [], "deleted": []}

def fetch_modified_records():
    """Fetch and clear the modified records."""
    if hasattr(_thread_local, "modified_records"):
        modified_records = _thread_local.modified_records
        clear_modified_records()
        return modified_records
    return {"created": [], "updated": [], "deleted": []}

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
    """
    Create records in the test environment based on setupData.

    Args:
        setup_data (dict): Predefined setup data for testing.
    """
    
    if isinstance(setup_data, str):
        # Convert class-like syntax into a dictionary
        setup_data_dict = {}
        for line in setup_data.splitlines():
            line = line.strip()
            if line.startswith("cls.") and "=" in line:
                # Extract the model name and record dictionary
                try:
                    model_key = line.split("=")[0].strip().replace("cls.", "")
                except:
                    print('ERROOOOOOOOOOOOO:', line)
                    print(model_key)
                model_key = model_key.split("_")[0].strip()
                record = eval(line.split("=", 1)[1].strip())  # Safely evaluate the record dictionary
                setup_data_dict.setdefault(model_key, []).append(record)
        setup_data = setup_data_dict
    
    # Apply the setup data to create records in the database
    for model_key, records in setup_data.items():
        # Extract app_label and model_name from the key
        try:
            #app_label, model_name = model_key.split(".")
            model = apps.get_model(get_app_for_model(model_key), model_key)
        except ValueError:
            raise ValueError(f"Invalid model key format: {model_key}. Expected 'app_label.ModelName'.")

        # Create records in the model
        for record in records:
            #try:

            #print(record)
            obj = model.objects.create(**record)
            #print(obj)
            #except Exception as e:
            #    raise ValueError(f"Error creating record in model '{model_name}': {e}")


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
    """
    Run the rule in a sandbox (test) environment.

    Args:
        company_id (int): The ID of the company.
        rule (str): The rule to be executed.
        setup_data (dict): Predefined setup data for the rule.
        payload (list): Mock payload to be used during execution.

    Returns:
        dict: Results of the sandbox execution.
    """
    print('1111111111111111111111111111')
    #teardown_test_environment()
    setup_test_environment()
    start_time = time.time()
    execution_logs = []
    modified_records = []

    try:
        with transaction.atomic():
            # Apply setup data
            print('22222222222222222222222222222')
            apply_setup_data(setup_data)
            print('33333333333333333333333333333333')
            # Clear debug logs and modified records
            debug_logs.clear()
            clear_modified_records()
            print('XXXXXXXXXXXXXXXXXXXXXXXXXXXX')
            # Execute the rule
            execute_rule(company_id=company_id, rule=rule, payload=payload)
            print('wwwwwwwwwwwwwwwwwwwwwwwwwww')
            # Capture debug logs
            execution_logs = debug_logs
    
            # Fetch modified records
            modified_records = fetch_modified_records()
            
            # Simulate rollback
            raise ValueError("Rollback test execution (sandbox mode)")


    except ValueError as e:
        if str(e) == "Rollback test execution (sandbox mode)":
            execution_time = time.time() - start_time
            return {
                "executionLogs": execution_logs,
                "modifiedRecords": modified_records,
                "executionTime": execution_time,
                "errors": None,
            }
        else:
            return {"errors": str(e), "executionLogs": debug_logs}

    except Exception as e:
        return {"errors": str(e), "executionLogs": debug_logs}

    finally:
        teardown_test_environment()




