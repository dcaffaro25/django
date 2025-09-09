# core/utils/exception_utils.py
import os
import math
import traceback
from decimal import Decimal
from pathlib import Path
from django.conf import settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # adjust if needed

def _json_safe(v):
    # keep it simple: make sure floats are finite and everything is string/primitive
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, Decimal):
        return float(v) if v.is_finite() else None
    return v

def exception_to_dict(exc, *, include_stack=None, max_stack_lines=200, include_locals=False):
    """
    Return a structured, JSON-safe error payload with file/function/line and (optionally) the stack.
    """
    include_stack = getattr(settings, "DEBUG", False) if include_stack is None else include_stack

    tb_exc = traceback.TracebackException.from_exception(exc, capture_locals=include_locals)
    frames = list(tb_exc.stack)

    # last frame where the exception was raised
    last = frames[-1] if frames else None
    if last:
        try:
            rel_file = os.path.relpath(last.filename, PROJECT_ROOT)
        except Exception:
            rel_file = last.filename
        location = {
            "file": rel_file,
            "function": last.name,
            "line": last.lineno,
        }
    else:
        location = None

    # Build a compact single-line summary
    summary = f"{exc.__class__.__name__}: {exc}"
    if location:
        summary += f" @ {location['file']}:{location['line']} in {location['function']}"

    # Optional pretty stack (string)
    stack_str = None
    if include_stack:
        stack_lines = list(tb_exc.format())[:max_stack_lines]
        stack_str = "".join(stack_lines)

    payload = {
        "type": exc.__class__.__name__,
        "message": str(exc),
        "summary": summary,
        "location": location,
        "cause": str(exc.__cause__) if exc.__cause__ else None,
        "context": str(exc.__context__) if exc.__context__ else None,
    }
    if include_stack:
        payload["stack"] = stack_str

    # Make values JSON-safe
    return {k: _json_safe(v) if not isinstance(v, dict) else v for k, v in payload.items()}
