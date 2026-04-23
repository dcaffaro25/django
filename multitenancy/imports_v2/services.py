"""Business logic for the v2 analyze → commit flow (template mode).

Phase 2 scope — happy path + erp_id conflict detection. Phase 3 adds
the ETL parse front-half; Phase 4 adds the resolve step plus the
remaining issue types (unmatched references, JE balance mismatch,
bad dates, ambiguous FKs, ETL missing parameters).

Keep this module thin: it owns the session lifecycle and delegates
the heavy parse/write work to the legacy helpers in
``multitenancy.tasks``. That means a v2 analyze → commit of a clean
file writes exactly what the legacy bulk-import would have written —
the only difference is that v2 inserts an issue-detection gate
between parse and write.
"""
from __future__ import annotations

import datetime
import decimal
import hashlib
import io
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from django.db import transaction
from django.utils import timezone

from multitenancy.models import ImportSession
from multitenancy.tasks import (
    _group_transaction_rows_by_erp_id,
    execute_import_job,
)

from . import issues as issue_mod


# --- session TTL -----------------------------------------------------------

SESSION_TTL = timedelta(hours=24)


# --- Excel parsing ---------------------------------------------------------

# Sheets we skip even when present in the uploaded file — they're
# documentation, not data. Mirrors the legacy bulk-import behaviour at
# ``multitenancy.views.BulkImportAPIView``.
_RESERVED_SHEETS = frozenset({"References", "ImportHelp"})


def _json_scalar(v: Any) -> Any:
    """Coerce a single cell value into a JSON-safe scalar.

    pandas auto-parses date-looking columns to ``Timestamp`` and numeric
    columns to ``numpy.int64`` / ``numpy.float64``; none of those
    serialize through Django's JSONField without help. Normalise to:
      * ``None`` for NaN / None
      * ISO string for date/datetime/Timestamp
      * ``str`` for Decimal (preserving precision)
      * ``int`` for numpy ints; ``float`` for numpy floats (with NaN →
        None)
      * str for everything else that isn't already a JSON primitive.
    """
    if v is None:
        return None
    # pandas NaN / NaT (both are float('nan') equivalents — the `!=` trick
    # catches both without importing math.isnan).
    if isinstance(v, float) and v != v:
        return None
    if isinstance(v, (datetime.date, datetime.datetime, pd.Timestamp)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return str(v)
    # numpy scalars carry an ``.item()`` method returning a Python
    # primitive. Safer than relying on implicit conversions.
    if hasattr(v, "item") and callable(v.item):
        try:
            py = v.item()
        except (ValueError, TypeError):
            return str(v)
        if isinstance(py, float) and py != py:
            return None
        return py
    if isinstance(v, (bool, int, float, str)):
        return v
    return str(v)


def _parse_template_file(file_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
    """Parse an uploaded Excel template into ``{sheet_name: [row_dict, ...]}``.

    Reproduces the legacy parser's quirks (NaN/inf → None, skip
    reserved sheets) so a v2 session run against the same file would
    produce the same parsed payload as the legacy endpoint.

    Raises ``ValueError`` on unreadable files — caller converts to a
    session error.
    """
    try:
        dfs = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None)
    except Exception as exc:  # pragma: no cover - pandas wrap
        raise ValueError(f"could not read workbook: {exc}") from exc

    out: Dict[str, List[Dict[str, Any]]] = {}
    for sheet_name, df in dfs.items():
        if sheet_name in _RESERVED_SHEETS:
            continue
        # Replace pandas sentinels with None so downstream code sees
        # plain Python types. ``where(pd.notna(df), None)`` replaces
        # NaN/NaT; inf values are independent and need a separate pass.
        df = df.where(pd.notna(df), None)
        rows = df.to_dict(orient="records")
        cleaned: List[Dict[str, Any]] = []
        for r in rows:
            fixed = {}
            for k, v in r.items():
                # ``_json_scalar`` handles Timestamp/Decimal/numpy
                # primitives + ±inf floats. Keeps the payload
                # round-trippable through JSONField.
                if isinstance(v, float) and (
                    v == float("inf") or v == float("-inf")
                ):
                    fixed[k] = None
                else:
                    fixed[k] = _json_scalar(v)
            cleaned.append(fixed)
        out[sheet_name] = cleaned
    return out


# --- issue detection -------------------------------------------------------

# Shared fields that must agree across rows of the same erp_id group on
# the Transaction sheet. Mirrors manual §11.10c.1 (Mode 1).
_TRANSACTION_SHARED_FIELDS = (
    "date",
    "entity",
    "entity_id",
    "entity_erp_id",
    "currency",
    "currency_id",
    "currency_erp_id",
    "description",
    "amount",
)


def _detect_transaction_erp_id_conflicts(
    rows: List[Dict[str, Any]],
    sheet_name: str,
) -> List[Dict[str, Any]]:
    """Run the Phase 0 grouping helper against one Transaction sheet and
    convert every conflict into an ``Issue`` dict.
    """
    _groups, conflicts = _group_transaction_rows_by_erp_id(
        rows, shared_fields=_TRANSACTION_SHARED_FIELDS,
    )
    out: List[Dict[str, Any]] = []
    for c in conflicts:
        # Convert the ``fields`` map into human-readable summaries for the
        # ``message`` field. Frontend also gets the raw shape in ``context``.
        field_summaries = []
        for fname, values in c["fields"].items():
            rendered = " vs ".join(
                "null" if v is None else str(v) for v in values
            )
            field_summaries.append(f"{fname} ({rendered})")
        msg = (
            f"{sheet_name}: erp_id={c['erp_id']!r} shared by "
            f"{len(c['row_ids'])} rows but disagrees on: "
            + ", ".join(field_summaries)
        )
        out.append(issue_mod.make_issue(
            type=issue_mod.ISSUE_ERP_ID_CONFLICT,
            severity=issue_mod.SEVERITY_ERROR,
            location={"sheet": sheet_name, "erp_id": c["erp_id"], "row_ids": c["row_ids"]},
            context={"fields": c["fields"]},
            proposed_actions=[
                issue_mod.ACTION_PICK_ROW,
                issue_mod.ACTION_SKIP_GROUP,
                issue_mod.ACTION_ABORT,
            ],
            message=msg,
        ))
    return out


# --- public: analyze -------------------------------------------------------


def analyze_template(
    *,
    company_id: int,
    user,
    file_bytes: bytes,
    file_name: str,
    config: Optional[Dict[str, Any]] = None,
) -> ImportSession:
    """Create a new ``ImportSession`` for template mode and populate it.

    Always persists the uploaded bytes so Phase 4's resolve can re-parse
    without re-upload. The session transitions to ``ready`` if no
    blocking issues were detected; otherwise ``awaiting_resolve``.

    Errors during parse itself become a terminal ``error`` session —
    the operator can inspect the reason via GET and discard.
    """
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    now = timezone.now()

    session = ImportSession.objects.create(
        company_id=company_id,
        created_by=user if (user and getattr(user, "is_authenticated", False)) else None,
        mode=ImportSession.MODE_TEMPLATE,
        status=ImportSession.STATUS_ANALYZING,
        file_name=file_name or "upload.xlsx",
        file_hash=file_hash,
        file_bytes=file_bytes,
        config=dict(config or {}),
        expires_at=now + SESSION_TTL,
    )

    try:
        sheets = _parse_template_file(file_bytes)
    except ValueError as exc:
        session.status = ImportSession.STATUS_ERROR
        session.result = {"error": str(exc), "stage": "parse"}
        session.save(update_fields=["status", "result", "updated_at"])
        return session

    detected_issues: List[Dict[str, Any]] = []
    for sheet_name, rows in sheets.items():
        # Only Transaction sheets carry the grouping semantics in Phase 2.
        # Other sheets (JournalEntry, BankTransaction, etc.) are passed
        # through to the commit step unchanged.
        if sheet_name == "Transaction":
            detected_issues.extend(
                _detect_transaction_erp_id_conflicts(rows, sheet_name)
            )

    # Freeze the parsed payload on the session so commit/resolve can read
    # it without re-parsing. The raw bytes stay on ``file_bytes`` too
    # (redundant but intentional — resolve may re-parse with different
    # config and we want both versions available).
    session.parsed_payload = {"sheets": sheets}
    session.open_issues = detected_issues
    if issue_mod.has_blocking_issues(detected_issues):
        session.status = ImportSession.STATUS_AWAITING_RESOLVE
    else:
        session.status = ImportSession.STATUS_READY
    session.save(update_fields=[
        "parsed_payload", "open_issues", "status", "updated_at",
    ])
    return session


# --- public: commit --------------------------------------------------------


class CommitNotReady(Exception):
    """Raised when ``commit_session`` is called on a non-ready session."""


def commit_session(session: ImportSession) -> ImportSession:
    """Run the legacy ``execute_import_job`` against the session's parsed
    rows and flip status to ``committed`` (or ``error`` if the write
    fails).

    Requires ``session.status == READY``. Raises ``CommitNotReady``
    otherwise — the view layer translates that into a 409.

    Wraps the whole write in a DB transaction; a half-written session
    rolls back cleanly and the session is marked ``error`` for audit
    with no rows written.
    """
    if not session.is_committable():
        raise CommitNotReady(
            f"session #{session.pk} is {session.status}, not ready to commit"
        )
    if session.is_terminal():
        raise CommitNotReady(
            f"session #{session.pk} is already terminal ({session.status})"
        )

    session.status = ImportSession.STATUS_COMMITTING
    session.save(update_fields=["status", "updated_at"])

    sheets_dict = (session.parsed_payload or {}).get("sheets", {}) or {}
    # ``execute_import_job`` expects sheet dicts shaped like
    # ``{"model": "...", "rows": [...]}``. The parse step above just
    # stored {sheet_name: [row_dict]}; model name was implicit from the
    # sheet name (convention used by the legacy endpoint). We reshape
    # here rather than at parse time so the stored payload stays close
    # to the raw workbook.
    sheets_for_job = [
        {"model": sheet_name, "rows": rows}
        for sheet_name, rows in sheets_dict.items()
    ]

    try:
        with transaction.atomic():
            result = execute_import_job(
                company_id=session.company_id,
                sheets=sheets_for_job,
                commit=True,
                import_metadata={
                    "source": "v2_template",
                    "function": "imports_v2.services.commit_session",
                    "session_id": session.pk,
                    "filename": session.file_name,
                },
            )
    except Exception as exc:  # pragma: no cover - logged via session.result
        session.status = ImportSession.STATUS_ERROR
        session.result = {
            "error": str(exc),
            "stage": "commit",
            "type": type(exc).__name__,
        }
        session.save(update_fields=["status", "result", "updated_at"])
        raise

    session.status = ImportSession.STATUS_COMMITTED
    session.committed_at = timezone.now()
    session.result = result
    # Clear file_bytes now that we're committed — audit stays in
    # file_hash + file_name + result, but we don't hoard the payload.
    session.file_bytes = None
    session.save(update_fields=[
        "status", "committed_at", "result", "file_bytes", "updated_at",
    ])
    return session


# --- public: discard -------------------------------------------------------


def discard_session(session: ImportSession) -> ImportSession:
    """Mark a session as discarded and clear its file bytes.

    Idempotent: discarding an already-discarded session is a no-op.
    Terminal sessions (committed / error) cannot be discarded — they
    stay in their terminal state for audit.
    """
    if session.is_terminal():
        return session
    session.status = ImportSession.STATUS_DISCARDED
    session.file_bytes = None
    session.save(update_fields=["status", "file_bytes", "updated_at"])
    return session
