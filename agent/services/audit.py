"""Audit-log helpers for the agent runtime — Phase 0.

Exposes one context-manager :func:`log_tool_call` that the runtime wraps
around every tool dispatch. The context manager:

* Times the call.
* On success: writes an ``AgentToolCallLog`` row with status ``ok`` (or
  ``warn`` if the tool returned an ``{"error": ...}`` blob).
* On exception: re-raises after writing an ``error`` row with type +
  truncated message.

Failures inside the audit machinery itself are *swallowed* and
logged — a broken audit row should never break a user-facing tool call.
"""
from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator

log = logging.getLogger(__name__)

# Limits to keep PII / context size bounded.
_ARGS_SUMMARY_CAP = 380


def _summarize_args(args: dict[str, Any] | None) -> str:
    """Truncate args to a debug-sized summary. Never store full args (PII)."""
    if not args:
        return ""
    try:
        s = json.dumps(args, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        s = repr(args)
    if len(s) > _ARGS_SUMMARY_CAP:
        return s[:_ARGS_SUMMARY_CAP] + "…"
    return s


def _response_size(value: Any) -> int | None:
    """Estimate the JSON-serialised size of a tool response."""
    if value is None:
        return 0
    try:
        return len(json.dumps(value, default=str, ensure_ascii=False))
    except (TypeError, ValueError):
        return None


@contextmanager
def log_tool_call(
    *,
    company,
    tool_name: str,
    tool_domain: str = "",
    args: dict[str, Any] | None = None,
    conversation=None,
    user=None,
    iteration: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Context manager that emits one :class:`AgentToolCallLog` row.

    Yields a small mutable dict the caller can populate with
    ``result`` and (optionally) ``status_override`` before the context
    exits. The decorator-style usage::

        with log_tool_call(company=..., tool_name="x", args=...) as ctx:
            result = call_tool("x", args)
            ctx["result"] = result

    On exit the row is written with whatever's in ``ctx``. If an
    exception escapes the block, status=error is written and the
    exception re-raised.
    """
    from agent.models import AgentToolCallLog

    ctx: dict[str, Any] = {"result": None, "status_override": None}
    started = time.monotonic()
    raised_exc: BaseException | None = None
    try:
        yield ctx
    except BaseException as exc:  # noqa: BLE001 — we re-raise after logging
        raised_exc = exc
        raise
    finally:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        result = ctx.get("result")
        status_override = ctx.get("status_override")

        # Determine status.
        if raised_exc is not None:
            status = AgentToolCallLog.STATUS_ERROR
            error_type = type(raised_exc).__name__
            error_msg = str(raised_exc)[:480]
        elif status_override:
            status = status_override
            error_type = ""
            error_msg = ""
        elif isinstance(result, dict) and "error" in result:
            status = AgentToolCallLog.STATUS_WARN
            error_type = ""
            error_msg = str(result.get("error"))[:480]
        else:
            status = AgentToolCallLog.STATUS_OK
            error_type = ""
            error_msg = ""

        try:
            AgentToolCallLog.objects.create(
                company=company,
                conversation=conversation,
                user=user,
                tool_name=tool_name,
                tool_domain=tool_domain or "",
                args_summary=_summarize_args(args),
                status=status,
                error_type=error_type,
                error_message=error_msg,
                latency_ms=elapsed_ms,
                response_size_bytes=_response_size(result) if status == AgentToolCallLog.STATUS_OK else None,
                iteration=iteration,
            )
        except Exception as audit_exc:  # pragma: no cover — audit must not break tools
            log.warning(
                "agent.audit.write_failed tool=%s status=%s err=%s",
                tool_name, status, audit_exc,
            )
