import ast
import operator
#from .models import IntegrationRule
from accounting.models import Transaction, JournalEntry, Account
from collections import defaultdict
import threading
import time
from accounting.serializers import TransactionSerializer, JournalEntrySerializer
from rest_framework.exceptions import ValidationError
from datetime import datetime, timezone

# Custom timeout exception
class TimeoutException(Exception):
    pass

# Timeout decorator with threading
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


# Aggregation Functions
def sum_group(group, key):
    """Sum a specific key across all items in a group."""
    return sum(item.get(key, 0) for item in group)


def max_group(group, key):
    """Find the maximum value of a specific key in a group."""
    return max(item.get(key, 0) for item in group)


def min_group(group, key):
    """Find the minimum value of a specific key in a group."""
    return min(item.get(key, 0) for item in group)


# Allowed built-in functions
SAFE_FUNCTIONS = {
    "sum": sum,
    "len": len,
    "str": str,
    "dict": dict,  # only if you want to allow dict()
    "today": lambda: datetime.now(timezone.utc).date(),
    "sum_group": sum_group,
    "max_group": max_group,
    "min_group": min_group,
    # Add more as needed, or from math, e.g.:
    # "abs": abs,
    # "round": round,
    # "floor": math.floor,
    # "ceil": math.ceil,
    # "sqrt": math.sqrt,
}


class FormulaEvaluationError(Exception):
    """Custom exception for formula evaluation errors."""
    pass


def evaluate_expression(expression, context=None):
    """
    Evaluate a Python expression AST safely, allowing comprehensions,
    conditionals, and a curated set of builtins/operators.
    """

    if context is None:
        context = {}

    def _eval(node, local_context):
        """Recursive AST evaluator."""

        if isinstance(node, ast.Expression):
            return _eval(node.body, local_context)

        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in SAFE_OPERATORS:
                raise FormulaEvaluationError(f"Binary operator '{op_type}' not allowed.")
            left_val = _eval(node.left, local_context)
            right_val = _eval(node.right, local_context)
            return SAFE_OPERATORS[op_type](left_val, right_val)

        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in SAFE_UNARY_OPS:
                raise FormulaEvaluationError(f"Unary operator '{op_type}' not allowed.")
            operand_val = _eval(node.operand, local_context)
            return SAFE_UNARY_OPS[op_type](operand_val)

        elif isinstance(node, ast.BoolOp):
            op_type = type(node.op)
            if op_type not in SAFE_BOOL_OPS:
                raise FormulaEvaluationError(f"Boolean operator '{op_type}' not allowed.")
            # Evaluate all values
            values = [_eval(v, local_context) for v in node.values]
            # For 'and', we apply `all`, for 'or', we apply `any`.
            return SAFE_BOOL_OPS[op_type](values)

        elif isinstance(node, ast.Compare):
            # Only allow single comparisons like `x < y`, not chained `x < y < z`
            if len(node.ops) != 1 or len(node.comparators) != 1:
                raise FormulaEvaluationError("Chained comparisons are not allowed.")
            op_type = type(node.ops[0])
            if op_type not in SAFE_COMPARISONS:
                raise FormulaEvaluationError(f"Comparison operator '{op_type}' not allowed.")
            left_val = _eval(node.left, local_context)
            right_val = _eval(node.comparators[0], local_context)
            return SAFE_COMPARISONS[op_type](left_val, right_val)

        elif isinstance(node, ast.IfExp):
            condition_val = _eval(node.test, local_context)
            return _eval(node.body if condition_val else node.orelse, local_context)

        elif isinstance(node, ast.Name):
            # Return from local_context if present
            if node.id in local_context:
                return local_context[node.id]
            raise FormulaEvaluationError(f"Variable '{node.id}' is not defined.")

        elif isinstance(node, ast.Constant):
            # Python 3.8+ uses ast.Constant for numbers, strings, etc.
            return node.value

        elif isinstance(node, ast.Dict):
            # Evaluate each key/value
            return {
                _eval(k, local_context): _eval(v, local_context)
                for k, v in zip(node.keys, node.values)
            }

        elif isinstance(node, ast.Subscript):
            # e.g. foo["bar"] or foo[0]
            value = _eval(node.value, local_context)
            sl = _eval(node.slice, local_context)
            try:
                return value[sl]
            except (TypeError, KeyError, IndexError) as e:
                raise FormulaEvaluationError(f"Invalid subscript access: {e}")

        elif isinstance(node, ast.Call):
            # function calls
            func = node.func
            if not isinstance(func, ast.Name):
                raise FormulaEvaluationError("Only direct function calls (by name) are allowed.")

            func_name = func.id
            if func_name not in SAFE_FUNCTIONS:
                raise FormulaEvaluationError(f"Call to function '{func_name}' is not allowed.")

            # Evaluate arguments
            args = [_eval(arg, local_context) for arg in node.args]
            # For now, disallow kwargs or star args
            if node.keywords:
                raise FormulaEvaluationError("Keyword arguments not supported.")
            return SAFE_FUNCTIONS[func_name](*args)

        elif isinstance(node, ast.ListComp):
            # e.g. [ expression for target in iter if condition ]
            return _eval_listcomp(node, local_context)

        elif isinstance(node, ast.GeneratorExp):
            # e.g. ( expression for target in iter if condition )
            # We'll return a *list* from a generator for consistency.
            return _eval_genexp(node, local_context)

        # Optionally handle set/dict comprehensions if desired:
        # elif isinstance(node, ast.SetComp):
        #     ...
        # elif isinstance(node, ast.DictComp):
        #     ...

        else:
            raise FormulaEvaluationError(f"Unsupported expression: {ast.dump(node)}")

    def _eval_listcomp(node: ast.ListComp, local_context):
        """
        Evaluate a list comprehension manually.
        Example: [ elt for target in iter if condition ]
        """
        comps = node.generators
        if len(comps) != 1:
            # If you want to allow multi-level comprehensions, handle that here
            raise FormulaEvaluationError("Nested/multiple list comprehensions are not allowed.")

        comp = comps[0]
        iterable_val = _eval(comp.iter, local_context)
        if not isinstance(iterable_val, (list, tuple)):
            raise FormulaEvaluationError("Comprehension can only iterate over list/tuple.")

        result = []
        for item in iterable_val:
            # Bind the 'target' variable in a new child context
            child_context = dict(local_context)
            if isinstance(comp.target, ast.Name):
                child_context[comp.target.id] = item
            else:
                raise FormulaEvaluationError("Only simple variable targets in comps are allowed.")

            # Evaluate ifs
            skip = False
            for if_node in comp.ifs:
                if_val = _eval(if_node, child_context)
                if not if_val:
                    skip = True
                    break
            if skip:
                continue

            # Evaluate the listcomp's elt
            elt_val = _eval(node.elt, child_context)
            result.append(elt_val)
        return result

    def _eval_genexp(node: ast.GeneratorExp, local_context):
        """
        Evaluate a generator expression, returning a list for convenience.
        Example: ( elt for target in iter if condition )
        """
        # This is effectively the same as listcomp but we'll just wrap it in a list
        comps = node.generators
        if len(comps) != 1:
            raise FormulaEvaluationError("Nested generator expressions are not allowed.")

        comp = comps[0]
        iterable_val = _eval(comp.iter, local_context)
        if not isinstance(iterable_val, (list, tuple)):
            raise FormulaEvaluationError("GeneratorExp can only iterate over list/tuple.")

        result = []
        for item in iterable_val:
            child_context = dict(local_context)
            if isinstance(comp.target, ast.Name):
                child_context[comp.target.id] = item
            else:
                raise FormulaEvaluationError("Only simple variable targets in generator expr.")

            # Evaluate ifs
            skip = False
            for if_node in comp.ifs:
                if_val = _eval(if_node, child_context)
                if not if_val:
                    skip = True
                    break
            if skip:
                continue

            elt_val = _eval(node.elt, child_context)
            result.append(elt_val)
        return result

    # ---------------------------
    # Parse & Evaluate the AST
    # ---------------------------
    try:
        parsed = ast.parse(expression, mode='eval')
    except SyntaxError as e:
        raise FormulaEvaluationError(f"Syntax error: {e}")

    return _eval(parsed.body, context)


def group_by(data, field):
    """
    Group data dynamically by a specified field.
    """

    grouped = defaultdict(list)
    for item in data:
        grouped[item[field]].append(item)
    return [{"group": key, "items": items} for key, items in grouped.items()]


def create_transaction(transaction_template, context):
    """
    Create a transaction with evaluated fields using the TransactionSerializer.
    """
    print("\n🔄 DEBUG: create_transaction called with:")
    print(transaction_template)

    transaction_data = {
        key: evaluate_expression(value, context) if isinstance(value, str) else value
        for key, value in transaction_template.items()
    }

    serializer = TransactionSerializer(data=transaction_data)
    if serializer.is_valid(raise_exception=True):
        transaction = serializer.save()
        print(f"✅ DEBUG: Transaction created successfully: {transaction}")
        if not transaction:
            raise ValueError("Transaction creation returned None.")
        return transaction
    
    print("❌ DEBUG: Transaction creation failed during validation.")
    raise ValueError("Transaction creation failed due to validation errors.")


def create_journal_entry(transaction, entry_template, context):
    """
    Create a journal entry with evaluated fields using the JournalEntrySerializer.
    """
    print("\n🔄 DEBUG: create_journal_entry called with:")
    print(entry_template)

    entry_data = {
        key: evaluate_expression(value, context) if isinstance(value, str) else value
        for key, value in entry_template.items()
    }
    entry_data['transaction'] = transaction

    serializer = JournalEntrySerializer(data=entry_data)
    if serializer.is_valid(raise_exception=True):
        journal_entry = serializer.save()
        print(f"✅ DEBUG: Journal Entry created successfully: {journal_entry}")
        if not journal_entry:
            raise ValueError("Journal entry creation returned None.")
        return journal_entry
    
    print("❌ DEBUG: Journal Entry creation failed during validation.")
    raise ValueError("Journal entry creation failed due to validation errors.")





@timeout_handler(seconds=5)
def execute_rule(rule: str, payload: list):
    """
    Safely execute a rule using a sandboxed environment.
    """
    # Validate syntax using AST
    try:
        ast.parse(rule)
    except SyntaxError as e:
        raise ValueError(f"Syntax Error in rule: {e}")

    # Create an isolated context
    context = {
        "payload": payload,
        "group_by": group_by,
        "create_transaction": create_transaction,
        "create_journal_entry": create_journal_entry,
        "sum": sum,
        "len": len,
        "sum_group": sum_group,
        "max_group": max_group,
        "min_group": min_group,
    
    }

    try:
        print("\n🔍 DEBUG: Context before execution:")
        print(context)
        exec(rule, {"__builtins__": None}, context)
        print("\n✅ DEBUG: Context after execution:")
        print(context)
        
    except TimeoutException as e:
        raise TimeoutException("Rule execution timed out.")
    except FormulaEvaluationError as e:
        raise ValueError(f"Formula error: {e}")
    except Exception as e:
        print("\n🚨 DEBUG: Context during exception:")
        print(context)
        raise ValueError(f"Unexpected error during rule execution: {e}")
    
    
    # Ensure result is explicitly checked
    if "result" not in context or context["result"] is None:
        raise ValueError(
            "Rule executed successfully, but 'result' was not set in the context. "
            "Ensure your rule explicitly sets the variable 'result'."
        )
    
    return context["result"]