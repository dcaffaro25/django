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

from multitenancy.etl_service import ETLPipelineService
from multitenancy.models import ImportSession, ImportTransformationRule, SubstitutionRule
from multitenancy.tasks import (
    _group_transaction_rows_by_erp_id,
    execute_import_job,
)

from . import issues as issue_mod
from . import resolve_handlers as _resolve_handlers


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


# --- Phase 4B detectors: bad_date_format / negative_amount / unmatched_reference -----

# Field names the ``bad_date_format`` detector scans on every sheet. Keeping
# this list narrow avoids false positives on columns that look like dates
# but aren't meant to parse (e.g. free-text description columns).
_DATE_LIKE_FIELDS = ("date", "due_date", "payment_date", "start_date", "end_date")


def _tryparse_date(v: Any) -> Optional[datetime.date]:
    """Best-effort date parse. Returns ``date`` on success, ``None`` on
    anything it can't interpret (empty, non-date string, garbled input).

    Covers:
      * Python ``date`` / ``datetime`` / pandas ``Timestamp`` (already
        normalised to ISO via ``_json_scalar`` during parse, but we
        still accept the native types for safety).
      * ISO 8601 date prefixes (``YYYY-MM-DD``).
      * pt-BR ``DD/MM/YYYY``.
      * US ``MM/DD/YYYY`` — only when the BR interpretation would fail
        (heuristic, deliberately conservative).

    Deliberately *not* falling back to ``dateutil.parse`` — that accepts
    so much garbage that the detector would miss real bad values.
    """
    if v is None or v == "":
        return None
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    if isinstance(v, pd.Timestamp):
        return v.date()
    if not isinstance(v, str):
        return None
    s = v.strip()
    if not s:
        return None
    # ISO 8601 first (matches our own _json_scalar output)
    try:
        return datetime.date.fromisoformat(s[:10])
    except ValueError:
        pass
    # DD/MM/YYYY
    import re as _re
    m = _re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        d, mo, y = (int(x) for x in m.groups())
        try:
            return datetime.date(y, mo, d)
        except ValueError:
            # BR parse failed; try US ordering as a fallback.
            try:
                return datetime.date(y, d, mo)
            except ValueError:
                return None
    return None


def _detect_bad_date_format(
    rows: List[Dict[str, Any]],
    sheet_name: str,
) -> List[Dict[str, Any]]:
    """Emit one ``bad_date_format`` issue per row × date-column with an
    unparseable value. Skips empty / null values — those are a
    different problem (required-field validation) handled elsewhere.
    """
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_id = row.get("__row_id")
        for field in _DATE_LIKE_FIELDS:
            if field not in row:
                continue
            val = row[field]
            if val is None or val == "":
                continue
            if _tryparse_date(val) is None:
                out.append(issue_mod.make_issue(
                    type=issue_mod.ISSUE_BAD_DATE_FORMAT,
                    severity=issue_mod.SEVERITY_ERROR,
                    location={"sheet": sheet_name, "row_id": row_id, "field": field},
                    context={"value": val},
                    proposed_actions=[
                        issue_mod.ACTION_EDIT_VALUE,
                        issue_mod.ACTION_IGNORE_ROW,
                        issue_mod.ACTION_ABORT,
                    ],
                    message=(
                        f"{sheet_name} row {row_id!r}: value {val!r} in "
                        f"column {field!r} is not a parseable date (expected "
                        f"ISO YYYY-MM-DD or DD/MM/YYYY)"
                    ),
                ))
    return out


def _detect_negative_amounts(
    rows: List[Dict[str, Any]],
    sheet_name: str,
    *,
    rule: Optional[ImportTransformationRule] = None,
) -> List[Dict[str, Any]]:
    """Emit ``negative_amount`` issues for rows whose value in a column
    flagged ``positive_only=True`` (via ``ImportTransformationRule.column_options``)
    is negative.

    Only runs when a rule is passed (ETL mode) — template mode has no
    column_options to consult. Non-numeric values are skipped silently
    (they surface as a different issue type, not this one).
    """
    if rule is None:
        return []
    column_options = getattr(rule, "column_options", None) or {}
    if not isinstance(column_options, dict):
        return []
    positive_only_fields = {
        name for name, opts in column_options.items()
        if isinstance(opts, dict) and opts.get("positive_only") is True
    }
    if not positive_only_fields:
        return []

    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_id = row.get("__row_id")
        for field in positive_only_fields:
            if field not in row:
                continue
            val = row[field]
            if val is None or val == "":
                continue
            # Accept BR-style decimals (``1.234,56``) and plain floats.
            try:
                num = float(str(val).replace(".", "").replace(",", "."))
            except (ValueError, TypeError):
                continue
            if num < 0:
                out.append(issue_mod.make_issue(
                    type=issue_mod.ISSUE_NEGATIVE_AMOUNT,
                    severity=issue_mod.SEVERITY_ERROR,
                    location={"sheet": sheet_name, "row_id": row_id, "field": field},
                    context={"value": val, "parsed": num},
                    proposed_actions=[
                        issue_mod.ACTION_EDIT_VALUE,
                        issue_mod.ACTION_IGNORE_ROW,
                        issue_mod.ACTION_ABORT,
                    ],
                    message=(
                        f"{sheet_name} row {row_id!r}: column {field!r} is "
                        f"flagged positive-only but got {val!r} ({num})"
                    ),
                ))
    return out


# Mapping of reference field (column name in the import payload) → info
# needed to look up DB candidates for ``unmatched_reference`` detection.
# Only the narrow subset we can resolve confidently today: (name-lookup,
# same company). Account.path lookups and cost-center paths get similar
# treatment when they cross the "only check-by-name" line.
_REFERENCE_FIELD_LOOKUPS = (
    # (sheet-hint, column, app_label, model_name, lookup_field)
    #
    # ``sheet-hint`` filters which sheets we scan this column on —
    # ``None`` means any sheet. Narrow this list if false positives
    # surface (e.g. a Description column named "entity" in some template).
    #
    # Only tenant-scoped models (those with ``company_id``) belong here —
    # global models like ``Currency`` would FieldError on the company
    # filter. Extending: add any TenantAwareBaseModel-derived FK target.
    (None, "entity", "multitenancy", "Entity", "name"),
)


def _detect_unmatched_references(
    rows: List[Dict[str, Any]],
    sheet_name: str,
    *,
    company_id: int,
) -> List[Dict[str, Any]]:
    """For each reference column on the sheet, check that every distinct
    string value resolves to a DB row in the current company. Unresolved
    values → ``unmatched_reference`` issue. Ambiguous (>1 match) values
    → ``fk_ambiguous``. Matching values are ignored.

    Pragmatic scope: two well-known string references (``entity`` →
    ``Entity.name``, ``currency`` → ``Currency.code``). Extending the
    lookup table is cheap — add a row to ``_REFERENCE_FIELD_LOOKUPS``
    and the detector picks it up.
    """
    from django.apps import apps as _apps

    issues: List[Dict[str, Any]] = []
    # Collect distinct (field, value) pairs that actually appear.
    seen: Dict[str, set] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        for _hint, field, _app, _model, _lookup in _REFERENCE_FIELD_LOOKUPS:
            if _hint is not None and _hint != sheet_name:
                continue
            if field not in row:
                continue
            val = row[field]
            if val is None or val == "":
                continue
            if not isinstance(val, str):
                continue
            seen.setdefault(field, set()).add(val)

    if not seen:
        return issues

    for hint, field, app, model_name, lookup_field in _REFERENCE_FIELD_LOOKUPS:
        if hint is not None and hint != sheet_name:
            continue
        values = seen.get(field)
        if not values:
            continue
        try:
            model_cls = _apps.get_model(app, model_name)
        except LookupError:
            continue

        for val in values:
            qs = model_cls.objects.filter(
                company_id=company_id, **{lookup_field: val},
            )
            count = qs.count()
            if count == 0:
                issues.append(issue_mod.make_issue(
                    type=issue_mod.ISSUE_UNMATCHED_REFERENCE,
                    severity=issue_mod.SEVERITY_ERROR,
                    location={
                        "sheet": sheet_name,
                        "field": field,
                        "value": val,
                    },
                    context={
                        "value": val,
                        "related_model": model_name,
                        "related_app": app,
                        "lookup_field": lookup_field,
                    },
                    proposed_actions=[
                        issue_mod.ACTION_MAP_TO_EXISTING,
                        issue_mod.ACTION_IGNORE_ROW,
                        issue_mod.ACTION_ABORT,
                    ],
                    message=(
                        f"{sheet_name}: {field}={val!r} does not resolve to "
                        f"any {model_name} row in this company "
                        f"(lookup by {lookup_field})"
                    ),
                ))
            elif count > 1:
                issues.append(issue_mod.make_issue(
                    type=issue_mod.ISSUE_FK_AMBIGUOUS,
                    severity=issue_mod.SEVERITY_ERROR,
                    location={
                        "sheet": sheet_name,
                        "field": field,
                        "value": val,
                    },
                    context={
                        "value": val,
                        "related_model": model_name,
                        "related_app": app,
                        "lookup_field": lookup_field,
                        "candidate_ids": list(qs.values_list("pk", flat=True)[:10]),
                        "match_count": count,
                    },
                    proposed_actions=[
                        issue_mod.ACTION_MAP_TO_EXISTING,
                        issue_mod.ACTION_IGNORE_ROW,
                        issue_mod.ACTION_ABORT,
                    ],
                    message=(
                        f"{sheet_name}: {field}={val!r} matches {count} "
                        f"{model_name} rows by {lookup_field}; operator must "
                        f"pick one"
                    ),
                ))
    return issues


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
        # Phase 4B detectors — run on every sheet.
        detected_issues.extend(_detect_bad_date_format(rows, sheet_name))
        detected_issues.extend(_detect_unmatched_references(
            rows, sheet_name, company_id=company_id,
        ))

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
    """Mode-aware commit: dispatches to the right write backend.

    Template-mode sessions delegate to the legacy ``execute_import_job``;
    ETL-mode sessions re-run ``ETLPipelineService`` with ``commit=True``
    on the original file bytes so the commit reproduces exactly what
    was shown in the analyze step (transformations, substitutions,
    auto-JE creation).

    Requires ``session.status == READY``. Raises ``CommitNotReady``
    otherwise — the view layer translates that into a 409.

    Write errors flip the session to ``error`` with a diagnostic in
    ``result`` and re-raise; the view layer returns 500.
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

    try:
        # Wrap BOTH the staged-rule materialisation AND the write backend
        # in one outer atomic block so any error (rule clashes, write
        # failures) rolls both back together. The write backends have
        # their own inner atomic blocks — Django nests them as savepoints.
        with transaction.atomic():
            created_rule_pks = _materialise_staged_rules(session)
            if session.mode == ImportSession.MODE_ETL:
                result = _commit_etl_session(session)
            else:
                result = _commit_template_session(session)
    except Exception as exc:  # pragma: no cover - logged via session.result
        session.status = ImportSession.STATUS_ERROR
        session.result = {
            "error": str(exc),
            "stage": "commit",
            "type": type(exc).__name__,
        }
        session.save(update_fields=["status", "result", "updated_at"])
        raise

    # Surface the created rule pks in the commit response so the
    # frontend can link to them in the "Regras criadas" panel. Shallow-
    # copy first so we don't mutate the write-backend's return value.
    if isinstance(result, dict):
        result = {**result, "substitution_rules_created": created_rule_pks}
    else:
        result = {"write_result": result,
                  "substitution_rules_created": created_rule_pks}

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


def _materialise_staged_rules(session: ImportSession) -> List[int]:
    """Create one ``SubstitutionRule`` per entry in
    ``session.staged_substitution_rules``.

    Each entry is a dict staged by a resolve action (Phase 4B's
    ``map_to_existing`` populates these — in Phase 4A the list is
    expected to be empty; this helper is the plumbing both phases need).

    Runs inside the commit's atomic block: if rule creation fails (e.g.
    ``unique_together`` collision) the entire commit rolls back and the
    session flips to ``error``.

    Returns the list of created rule pks so the commit response can
    surface them to the client under ``substitution_rules_created``.
    """
    staged = session.staged_substitution_rules or []
    if not staged:
        return []
    created: List[int] = []
    for entry in staged:
        if not isinstance(entry, dict):
            raise ValueError(
                f"malformed entry in staged_substitution_rules: {entry!r}"
            )
        rule = SubstitutionRule.objects.create(
            company_id=session.company_id,
            model_name=entry["model_name"],
            field_name=entry["field_name"],
            match_type=entry.get("match_type", "exact"),
            match_value=entry["match_value"],
            substitution_value=entry["substitution_value"],
            filter_conditions=entry.get("filter_conditions"),
            title=entry.get("title"),
            source=SubstitutionRule.SOURCE_IMPORT_SESSION,
            source_session=session,
        )
        created.append(rule.pk)
    return created


def _commit_template_session(session: ImportSession) -> Dict[str, Any]:
    """Template-mode commit: replay parsed rows through
    ``execute_import_job`` (the legacy entry point). Atomic; rollback
    on any write failure."""
    sheets_dict = (session.parsed_payload or {}).get("sheets", {}) or {}
    # ``execute_import_job`` expects sheet dicts shaped like
    # ``{"model": "...", "rows": [...]}``. The parse step stored
    # ``{sheet_name: [row_dict]}`` — model name was implicit from the
    # sheet name (convention used by the legacy endpoint). Reshape here
    # rather than at parse time so the stored payload stays close to
    # the raw workbook.
    sheets_for_job = [
        {"model": sheet_name, "rows": rows}
        for sheet_name, rows in sheets_dict.items()
    ]
    with transaction.atomic():
        return execute_import_job(
            company_id=session.company_id,
            sheets=sheets_for_job,
            commit=True,
            import_metadata={
                "source": "v2_template",
                "function": "imports_v2.services._commit_template_session",
                "session_id": session.pk,
                "filename": session.file_name,
            },
        )


def _commit_etl_session(session: ImportSession) -> Dict[str, Any]:
    """ETL-mode commit: re-run ``ETLPipelineService`` on the original
    file bytes with ``commit=True``.

    Why re-run instead of replaying session.parsed_payload through
    execute_import_job? The ETL pipeline has side-effects (FK
    resolution via lookup_cache, post-processing for JournalEntry
    debit/credit, auto_create_journal_entries hook, integration-rule
    triggers) that aren't reproducible from just the transformed rows.
    Re-running against the same file bytes + same transformation rule
    within the 24h session TTL reproduces what we showed in analyze.
    """
    file_bytes = session.file_bytes
    if not file_bytes:
        raise CommitNotReady(
            f"session #{session.pk} has no file_bytes (expired?) — re-upload"
        )

    # Reconstruct an UploadedFile-like object for ETLPipelineService.
    # The service only reads ``.name`` and pandas-reads the file itself.
    from django.core.files.uploadedfile import SimpleUploadedFile
    file_like = SimpleUploadedFile(
        session.file_name or "import.xlsx",
        bytes(file_bytes),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    config = dict(session.config or {})
    auto_je = config.get("auto_create_journal_entries") or {}
    row_limit = config.get("row_limit")

    service = ETLPipelineService(
        company_id=session.company_id,
        file=file_like,
        commit=True,
        auto_create_journal_entries=auto_je,
        row_limit=row_limit if row_limit is not None else 0,  # 0 = all rows
    )
    # ``execute()`` handles its own transaction. On any failure it
    # raises, which our caller catches to flip session to ``error``.
    return service.execute()


# --- public: ETL analyze ---------------------------------------------------


def _detect_missing_etl_parameters(
    auto_je: Optional[Dict[str, Any]],
    transformed_data: Dict[str, List[Dict[str, Any]]],
    *,
    rule: Optional[ImportTransformationRule] = None,
) -> List[Dict[str, Any]]:
    """Check that every column the auto-JE config references is actually
    present in the transformed data.

    Example: config has ``auto_create_journal_entries.bank_account_field
    = 'bank_account_id'`` but no Transaction row exposes that key
    (operator forgot to map it in ``column_mappings``). Without this
    check the ETL pipeline would silently fail to create bank legs.

    ``auto_je`` is the dict the operator passes per-request (same
    semantics as the legacy ``/api/core/etl/execute/`` endpoint, which
    accepts the config in the POST body rather than on the rule). The
    optional ``rule`` is only used to populate the issue's context for
    the diagnostics panel.

    Returns zero or more blocking issues. Shown to the operator in the
    diagnostics panel per manual §11.10e "Parâmetros ausentes".
    """
    if not auto_je or not isinstance(auto_je, dict) or not auto_je.get("enabled"):
        return []

    # Fields that the auto-JE flow reads from each Transaction row.
    # ``opposing_account_field`` has a default of ``account_path`` in
    # the service; we treat explicit config as the source of truth.
    checked_fields = {
        "bank_account_field": auto_je.get("bank_account_field") or "bank_account_id",
        "opposing_account_field": auto_je.get("opposing_account_field") or "account_path",
    }
    cost_center_field = auto_je.get("cost_center_field")
    if cost_center_field:
        checked_fields["cost_center_field"] = cost_center_field

    # Look at the first row of each transformed model's data to inspect
    # which keys exist. If transformed_data is empty the analyze stage
    # has other, more fundamental errors — no point emitting missing-
    # param issues on top.
    tx_rows = transformed_data.get("Transaction") or []
    if not tx_rows:
        return []
    present_keys = set()
    for row in tx_rows[:5]:  # sample first few; uniform shape in practice
        if isinstance(row, dict):
            present_keys.update(row.keys())

    issues: List[Dict[str, Any]] = []
    for role, field_name in checked_fields.items():
        if not field_name:
            continue
        if field_name not in present_keys:
            issues.append(issue_mod.make_issue(
                type=issue_mod.ISSUE_MISSING_ETL_PARAMETER,
                severity=issue_mod.SEVERITY_ERROR,
                location={
                    "sheet": "Transaction",
                    "expected_column": field_name,
                    "role": role,
                },
                context={
                    "rule_id": rule.pk if rule is not None else None,
                    "rule_name": getattr(rule, "name", None) if rule is not None else None,
                    "auto_create_journal_entries": auto_je,
                    "present_columns": sorted(present_keys),
                },
                proposed_actions=[issue_mod.ACTION_ABORT],
                message=(
                    f"A configuração ``auto_create_journal_entries`` da "
                    f"regra espera a coluna {field_name!r} ({role}) na aba "
                    f"Transaction, mas ela não existe nas linhas "
                    f"transformadas. Ajuste o ``column_mappings`` da regra "
                    f"para produzir essa coluna, ou desabilite "
                    f"auto_create_journal_entries."
                ),
            ))
    return issues


def analyze_etl(
    *,
    company_id: int,
    user,
    file_bytes: bytes,
    file_name: str,
    transformation_rule_id: Optional[int] = None,
    config: Optional[Dict[str, Any]] = None,
) -> ImportSession:
    """Create an ETL-mode ``ImportSession`` and populate it by running
    ``ETLPipelineService.execute(commit=False)`` under the hood.

    Captures the service's outputs — transformed data, substitutions
    applied, substitution errors, python/database errors — into the
    session's ``parsed_payload`` + ``open_issues`` so the operator
    can review diagnostics without re-uploading.

    Phase 3 issue detection:
      * ``erp_id_conflict``  — same as template mode, scoped to
        ``transformed_data['Transaction']``.
      * ``missing_etl_parameter`` — rule declares auto-JE columns that
        aren't present in transformed rows.
      * ETL service errors (python_errors / database_errors /
        substitution_errors) pass through as ``parsed_payload['etl_errors']``
        so the frontend's existing error-bucket renderers keep working.
    """
    from django.core.files.uploadedfile import SimpleUploadedFile

    file_hash = hashlib.sha256(file_bytes).hexdigest()
    now = timezone.now()
    cfg = dict(config or {})

    rule = None
    if transformation_rule_id is not None:
        try:
            rule = ImportTransformationRule.objects.get(
                pk=transformation_rule_id, company_id=company_id,
            )
        except ImportTransformationRule.DoesNotExist:
            rule = None  # surface as a parse-stage error below

    # Freeze the auto-JE config — passed in ``config`` by the caller
    # (matches legacy ETL semantics where the config lives in the POST
    # body, not on the rule). Defaulting to {} means "no auto-JE" which
    # is the safe default.
    cfg.setdefault("auto_create_journal_entries", {})

    session = ImportSession.objects.create(
        company_id=company_id,
        created_by=user if (user and getattr(user, "is_authenticated", False)) else None,
        mode=ImportSession.MODE_ETL,
        status=ImportSession.STATUS_ANALYZING,
        transformation_rule=rule,
        file_name=file_name or "upload.xlsx",
        file_hash=file_hash,
        file_bytes=file_bytes,
        config=cfg,
        expires_at=now + SESSION_TTL,
    )

    if rule is None and transformation_rule_id is not None:
        session.status = ImportSession.STATUS_ERROR
        session.result = {
            "error": f"transformation rule #{transformation_rule_id} not found for this company",
            "stage": "lookup",
        }
        session.save(update_fields=["status", "result", "updated_at"])
        return session

    # Build a fresh UploadedFile for ETLPipelineService — it reads the
    # stream + ``.name``. We don't give it the raw bytes directly.
    file_like = SimpleUploadedFile(
        file_name or "upload.xlsx",
        file_bytes,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    service = ETLPipelineService(
        company_id=company_id,
        file=file_like,
        commit=False,
        auto_create_journal_entries=cfg.get("auto_create_journal_entries") or {},
        # row_limit=0 means "process all rows"; cfg can override for
        # sampled previews.
        row_limit=cfg.get("row_limit", 0),
    )

    try:
        etl_result = service.execute()
    except Exception as exc:
        session.status = ImportSession.STATUS_ERROR
        session.result = {
            "error": str(exc),
            "stage": "etl_execute",
            "type": type(exc).__name__,
        }
        session.save(update_fields=["status", "result", "updated_at"])
        return session

    # ETLPipelineService surfaces a ``transformed_data`` dict shaped as
    # ``{model_name: {"row_count": N, "rows": [...], "sample_columns": [...]}}``.
    # Flatten to ``{model_name: [rows]}`` for our own consumption. Keep
    # the full service result under ``etl_result`` for debugging/audit.
    transformed_flat: Dict[str, List[Dict[str, Any]]] = {}
    raw_td = (etl_result or {}).get("transformed_data") or {}
    for model_name, payload in raw_td.items():
        if isinstance(payload, dict) and "rows" in payload:
            transformed_flat[model_name] = list(payload.get("rows") or [])
        elif isinstance(payload, list):
            transformed_flat[model_name] = payload
        else:
            transformed_flat[model_name] = []

    detected_issues: List[Dict[str, Any]] = []
    # erp_id_conflict — same detector as template mode, applied to the
    # transformed Transaction rows (so substitutions have already had a
    # chance to fix mis-keyed rows).
    if "Transaction" in transformed_flat:
        detected_issues.extend(
            _detect_transaction_erp_id_conflicts(
                transformed_flat["Transaction"], "Transaction",
            )
        )
    # missing_etl_parameter — config-driven column check. Rule is
    # passed for diagnostic-panel context only; the actual check runs
    # against the auto-JE config the caller provided.
    detected_issues.extend(_detect_missing_etl_parameters(
        cfg.get("auto_create_journal_entries"),
        transformed_flat,
        rule=rule,
    ))
    # Phase 4B detectors — run on every transformed sheet.
    for model_name, rows in transformed_flat.items():
        detected_issues.extend(_detect_bad_date_format(rows, model_name))
        detected_issues.extend(_detect_negative_amounts(
            rows, model_name, rule=rule,
        ))
        detected_issues.extend(_detect_unmatched_references(
            rows, model_name, company_id=company_id,
        ))

    # Surface the ETL service's own error buckets as ``parsed_payload['etl_errors']``
    # (the frontend already renders them; we don't translate each one
    # into an Issue in Phase 3 — that's Phase 4 when unmatched-reference
    # resolution ships).
    #
    # ``would_create`` / ``would_fail`` / ``total_rows`` come from
    # ``ETLPipelineService.execute(commit=False)`` — they're the dry-run
    # counts legacy ETL preview already exposes. We pass them through
    # as ``parsed_payload["preview"]`` so the serializer's ``preview``
    # field can surface them to the frontend's "Prévia da importação"
    # panel on a clean analyze.
    session.parsed_payload = {
        "transformed_data": transformed_flat,
        "substitutions_applied": etl_result.get("substitutions_applied") or [],
        "etl_errors": {
            "python_errors": etl_result.get("python_errors") or [],
            "database_errors": etl_result.get("database_errors") or [],
            "substitution_errors": etl_result.get("substitution_errors") or [],
            "warnings": etl_result.get("warnings") or [],
        },
        "sheets_processed": etl_result.get("sheets_processed") or [],
        "preview": {
            "would_create": etl_result.get("would_create") or {},
            "would_fail": etl_result.get("would_fail") or {},
            "total_rows": etl_result.get("total_rows") or 0,
        },
    }
    session.open_issues = detected_issues
    if issue_mod.has_blocking_issues(detected_issues):
        session.status = ImportSession.STATUS_AWAITING_RESOLVE
    else:
        session.status = ImportSession.STATUS_READY
    session.save(update_fields=[
        "parsed_payload", "open_issues", "status", "updated_at",
    ])
    return session


# --- public: resolve -------------------------------------------------------


class ResolveNotApplicable(Exception):
    """Raised when ``resolve_session`` is called on a session whose status
    doesn't accept resolutions. View layer maps to 409.
    """


def _redetect_issues(session: ImportSession) -> List[Dict[str, Any]]:
    """Re-run the detectors relevant to ``session.mode`` over the current
    ``parsed_payload``. Called after every resolve-batch so an operator
    who partially resolves a group still sees the remaining issues.

    Mirrors the detector calls in ``analyze_template`` / ``analyze_etl``.
    When a new detector is added, add it here too or the resolve cycle
    will happily close out a session that an analyze would have blocked.
    """
    detected: List[Dict[str, Any]] = []
    company_id = session.company_id
    if session.mode == ImportSession.MODE_ETL:
        transformed = (session.parsed_payload or {}).get("transformed_data") or {}
        if "Transaction" in transformed:
            detected.extend(_detect_transaction_erp_id_conflicts(
                transformed["Transaction"], "Transaction",
            ))
        auto_je = (session.config or {}).get("auto_create_journal_entries")
        detected.extend(_detect_missing_etl_parameters(
            auto_je, transformed, rule=session.transformation_rule,
        ))
        for model_name, rows in transformed.items():
            detected.extend(_detect_bad_date_format(rows, model_name))
            detected.extend(_detect_negative_amounts(
                rows, model_name, rule=session.transformation_rule,
            ))
            detected.extend(_detect_unmatched_references(
                rows, model_name, company_id=company_id,
            ))
    else:
        sheets = (session.parsed_payload or {}).get("sheets") or {}
        for sheet_name, rows in sheets.items():
            if sheet_name == "Transaction":
                detected.extend(_detect_transaction_erp_id_conflicts(
                    rows, sheet_name,
                ))
            detected.extend(_detect_bad_date_format(rows, sheet_name))
            detected.extend(_detect_unmatched_references(
                rows, sheet_name, company_id=company_id,
            ))
    return detected


def resolve_session(
    session: ImportSession,
    resolutions: List[Dict[str, Any]],
) -> ImportSession:
    """Apply a batch of operator-provided resolutions to the session.

    Each resolution is ``{issue_id, action, params}``. For each one we:
      * find the matching issue in ``session.open_issues``,
      * dispatch to the per-action handler in ``resolve_handlers``,
      * record the result on ``session.resolutions``,
      * re-run detection on the (now-mutated) parsed_payload.

    Once all applicable resolutions have run we recompute the session
    status: ``ready`` if no blocking issues remain, otherwise the
    session stays in ``awaiting_resolve``. An ``abort`` resolution
    short-circuits the batch and flips the session to ``error``.

    Raises:
      * ``ResolveNotApplicable`` — session is terminal/committing.
      * ``resolve_handlers.ResolutionError`` — malformed params /
        unknown action / unknown issue_id (view translates to 400).
    """
    if session.is_terminal():
        raise ResolveNotApplicable(
            f"session #{session.pk} is terminal ({session.status}); "
            f"cannot resolve"
        )
    if session.status == ImportSession.STATUS_COMMITTING:
        raise ResolveNotApplicable(
            f"session #{session.pk} is committing; resolve not allowed"
        )

    if not isinstance(resolutions, list):
        raise _resolve_handlers.ResolutionError(
            "`resolutions` must be a list"
        )

    now_iso = timezone.now().isoformat()
    open_issues_by_id = {
        i.get("issue_id"): i for i in (session.open_issues or [])
    }
    new_resolutions: List[Dict[str, Any]] = []
    aborted = False
    abort_info: Optional[Dict[str, Any]] = None

    for res in resolutions:
        if not isinstance(res, dict):
            raise _resolve_handlers.ResolutionError(
                "each resolution must be an object"
            )
        issue_id = res.get("issue_id")
        action = res.get("action")
        params = res.get("params") or {}
        if not issue_id:
            raise _resolve_handlers.ResolutionError(
                "resolution is missing issue_id"
            )
        if not action:
            raise _resolve_handlers.ResolutionError(
                "resolution is missing action"
            )
        issue = open_issues_by_id.get(issue_id)
        if issue is None:
            raise _resolve_handlers.ResolutionError(
                f"no open issue with issue_id={issue_id!r}"
            )
        result = _resolve_handlers.apply_resolution(
            session, issue, action, params,
        )
        record = {
            "issue_id": issue_id,
            "action": action,
            "params": params,
            "result": result,
            "resolved_at": now_iso,
        }
        new_resolutions.append(record)
        if result.get("abort"):
            aborted = True
            abort_info = result
            break

    # Persist the resolution records BEFORE any status transition so the
    # audit trail is complete even if redetection or save fails.
    session.resolutions = list(session.resolutions or []) + new_resolutions

    if aborted:
        session.status = ImportSession.STATUS_ERROR
        session.result = {
            "error": "operator aborted",
            "stage": "resolve",
            "abort": abort_info,
        }
        session.save(update_fields=[
            "resolutions", "status", "result", "updated_at",
        ])
        return session

    # Re-detect issues against the now-mutated parsed_payload. Replaces
    # the open_issues list wholesale — any issue that's still valid will
    # be re-emitted; any issue the operator resolved won't re-appear.
    redetected = _redetect_issues(session)
    session.open_issues = redetected

    if issue_mod.has_blocking_issues(redetected):
        session.status = ImportSession.STATUS_AWAITING_RESOLVE
    else:
        session.status = ImportSession.STATUS_READY

    session.save(update_fields=[
        "parsed_payload", "open_issues", "resolutions",
        "staged_substitution_rules", "status", "updated_at",
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
