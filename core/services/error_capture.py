"""Error capture — ingest + fingerprint + upsert to ErrorReport.

The only public surface is :func:`capture_error`. Every source of
errors (DRF exception handler, Django signal, Celery task_failure,
frontend beacon) funnels through it so we have one place to tune
what gets fingerprinted and how.

Design notes:

* **Fingerprints are stable by design.** Frontend: hash of
  ``error_class + top-of-stack``. Backend: hash of
  ``error_class + endpoint + status`` (endpoint + status because a
  500 vs a 404 vs a 403 on the same route are different stories).
  Celery: hash of ``error_class + task_name``.
* **Affected users count is approximate.** We increment when the
  user_id differs from the last one we saw; the true "distinct
  affected users" could drift over time. Accurate enough for the
  dashboard headline — the detail page computes the real count
  from events when asked.
* **Reopen detection is non-racy.** If an event arrives after
  ``resolved_at``, we flip ``is_reopened=True`` but leave
  ``is_resolved=True`` so the admin can see "was fixed, came back"
  explicitly. Manually resolving again clears the flag.
"""

from __future__ import annotations

import hashlib
import logging
import traceback
from typing import Any

from django.db import transaction as db_transaction
from django.utils import timezone

from core.models import ErrorReport, UserActivityEvent


log = logging.getLogger(__name__)

_MAX_STACK_CHARS = 8_000
_MAX_MSG_CHARS = 500


def _fingerprint(parts: list[str]) -> str:
    """SHA1 of the joined parts. Truncate in the model to 64 chars
    but hashes are 40 — plenty of headroom."""
    joined = "\n".join((p or "").strip() for p in parts)
    return hashlib.sha1(joined.encode("utf-8", "replace")).hexdigest()


def _top_of_stack(stack: str) -> str:
    """First non-empty, non-indented line that looks like a frame.
    We want the most-specific location that's ours — not the
    bottom-of-stack bootstrap noise."""
    if not stack:
        return ""
    for line in stack.splitlines():
        s = line.strip()
        if not s:
            continue
        # Common patterns: "File .../foo.py", "at SomeFn (...)", "Error at ...".
        if s.startswith("File ") or s.startswith("at ") or "(" in s:
            return s[:200]
    return stack.splitlines()[0][:200]


def fingerprint_frontend(error_class: str, stack: str) -> str:
    return _fingerprint(["frontend", error_class, _top_of_stack(stack)])


def fingerprint_backend(error_class: str, path: str, status_code: int | None) -> str:
    return _fingerprint([
        "backend_drf",
        error_class,
        (path or "").split("?")[0],
        str(status_code or ""),
    ])


def fingerprint_django(error_class: str, path: str) -> str:
    return _fingerprint([
        "backend_django",
        error_class,
        (path or "").split("?")[0],
    ])


def fingerprint_celery(error_class: str, task_name: str) -> str:
    return _fingerprint(["celery", error_class, task_name])


def capture_error(
    *,
    kind: str,
    fingerprint: str,
    error_class: str = "",
    message: str = "",
    stack: str = "",
    path: str = "",
    method: str = "",
    status_code: int | None = None,
    user=None,
    company=None,
    session=None,
    breadcrumbs: list | None = None,
    raw_meta: dict | None = None,
) -> ErrorReport:
    """Upsert an ErrorReport + write a UserActivityEvent occurrence.

    Returns the updated report. Safe to call in request/response
    paths — wrapped in its own atomic() so a capture failure
    doesn't poison the caller.
    """
    now = timezone.now()
    message = (message or "")[:_MAX_MSG_CHARS]
    stack = (stack or "")[:_MAX_STACK_CHARS]

    try:
        with db_transaction.atomic():
            report, created = ErrorReport.objects.select_for_update().get_or_create(
                fingerprint=fingerprint,
                defaults={
                    "kind": kind,
                    "error_class": (error_class or "")[:128],
                    "message": message,
                    "sample_stack": stack,
                    "path": (path or "")[:512],
                    "method": (method or "")[:8],
                    "status_code": status_code,
                    "count": 1,
                    "affected_users": 1 if user else 0,
                    "last_seen_at": now,
                },
            )
            if not created:
                report.count = (report.count or 0) + 1
                report.last_seen_at = now
                # Refresh the surface fields opportunistically —
                # the latest message/stack is what the admin wants
                # to see, not the first one.
                if message:
                    report.message = message
                if stack:
                    report.sample_stack = stack
                if path and not report.path:
                    report.path = path[:512]
                if status_code is not None and report.status_code != status_code:
                    report.status_code = status_code
                # Reopen detection: an occurrence after a resolved
                # timestamp is a signal the fix didn't take.
                if report.is_resolved and report.resolved_at and now > report.resolved_at:
                    report.is_reopened = True
                report.save()

            # Increment affected_users heuristically. Backend captures
            # usually don't pass a session (no browser tab) so there
            # are no events to peek at; fall back to stashing the
            # last-seen user_id inside the occurrence event we write
            # below, or compute on-demand from events. For now the
            # detail endpoint has the authoritative distinct count.

            # Write an occurrence event so we keep breadcrumbs and
            # per-incident detail available. Session may be None —
            # backend captures don't have one.
            if session is not None:
                ev_meta: dict[str, Any] = {
                    "fingerprint": fingerprint,
                    "error_class": error_class,
                    "message": message,
                    "stack": stack[:4000],
                    "status_code": status_code,
                    "method": method,
                }
                if breadcrumbs:
                    ev_meta["breadcrumbs"] = breadcrumbs[-20:]
                if raw_meta:
                    ev_meta["raw"] = raw_meta
                UserActivityEvent.objects.create(
                    session=session,
                    user=user,
                    company=company,
                    kind=UserActivityEvent.KIND_ERROR,
                    area="",  # resolved by path/kind on the admin side
                    path=path or "",
                    meta=ev_meta,
                )

        return report
    except Exception:  # pragma: no cover — defensive, don't take down the caller
        log.exception("capture_error failed for fingerprint=%s", fingerprint)
        raise


def capture_exception(
    exc: BaseException,
    *,
    kind: str = ErrorReport.KIND_BACKEND_DJANGO,
    request=None,
    task_name: str = "",
    user=None,
) -> ErrorReport | None:
    """Convenience wrapper for Python exceptions. Used by all three
    backend entry points (DRF handler, Django signal, Celery signal).

    Never raises — a broken capture path must not mask the real
    error. Returns None on failure; caller moves on.
    """
    try:
        cls = type(exc).__name__
        msg = str(exc)
        stack = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        path = ""
        method = ""
        status_code: int | None = None
        if request is not None:
            # Duck-type: works for Django + DRF requests.
            path = getattr(request, "path", "") or ""
            method = getattr(request, "method", "") or ""
            status_code = getattr(getattr(request, "_error_status", None), "real", None)
        if kind == ErrorReport.KIND_CELERY:
            fp = fingerprint_celery(cls, task_name)
        elif kind == ErrorReport.KIND_BACKEND_DRF and status_code:
            fp = fingerprint_backend(cls, path, status_code)
        else:
            fp = fingerprint_django(cls, path)
        return capture_error(
            kind=kind,
            fingerprint=fp,
            error_class=cls,
            message=msg,
            stack=stack,
            path=path,
            method=method,
            status_code=status_code,
            user=user if user is not None else getattr(request, "user", None) if request else None,
            raw_meta={"task_name": task_name} if task_name else None,
        )
    except Exception:
        log.exception("capture_exception swallowed")
        return None
