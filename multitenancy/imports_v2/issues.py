"""Canonical schema for v2 import diagnostics.

An ``Issue`` is one unresolved item the operator must act on before the
session can commit. The structure is intentionally loose (a dict, not
a Pydantic model) so it survives JSONField roundtrips and so the
frontend can render unknown issue types without backend coordination.

Every issue carries:

  * ``issue_id``:  stable string for UI keys + resolution targeting.
  * ``type``:      one of ``ISSUE_TYPES`` (see below). Frontend matches
                   on this to pick a renderer.
  * ``severity``:  ``"error"`` (blocks commit) or ``"warning"`` (shown
                   but doesn't block).
  * ``location``:  dict telling the operator WHERE the issue is — which
                   sheet, row(s), field, erp_id, etc.
  * ``context``:   the data needed to explain/resolve the issue —
                   e.g. the conflicting values for an erp_id_conflict.
  * ``proposed_actions``: list of action names the resolve endpoint
                   will accept for this issue. The frontend uses this to
                   decide which buttons/form to render.

Adding a new issue type later = new constant + handler in
``services.py`` + frontend renderer. No schema migration.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional


# --- issue types -----------------------------------------------------------

# Phase 2 — detected at analyze:
ISSUE_ERP_ID_CONFLICT = "erp_id_conflict"
# Phase 4 — detected at analyze but needs resolve flow:
ISSUE_UNMATCHED_REFERENCE = "unmatched_reference"
ISSUE_JE_BALANCE_MISMATCH = "je_balance_mismatch"
ISSUE_BAD_DATE_FORMAT = "bad_date_format"
ISSUE_NEGATIVE_AMOUNT = "negative_amount"
ISSUE_FK_AMBIGUOUS = "fk_ambiguous"
# ETL-only (Phase 3):
ISSUE_MISSING_ETL_PARAMETER = "missing_etl_parameter"

ISSUE_TYPES = frozenset({
    ISSUE_ERP_ID_CONFLICT,
    ISSUE_UNMATCHED_REFERENCE,
    ISSUE_JE_BALANCE_MISMATCH,
    ISSUE_BAD_DATE_FORMAT,
    ISSUE_NEGATIVE_AMOUNT,
    ISSUE_FK_AMBIGUOUS,
    ISSUE_MISSING_ETL_PARAMETER,
})


# --- severity --------------------------------------------------------------

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITIES = frozenset({SEVERITY_ERROR, SEVERITY_WARNING})


# --- action names ----------------------------------------------------------
# The resolve endpoint accepts ``action`` strings; each issue type has a
# fixed set of actions it understands. See ``services.py:resolve_issue``.

ACTION_PICK_ROW = "pick_row"              # erp_id_conflict: keep one row, drop rest
ACTION_SKIP_GROUP = "skip_group"          # erp_id_conflict: drop every row of the group
ACTION_ABORT = "abort"                    # any: mark session error and stop
ACTION_MAP_TO_EXISTING = "map_to_existing"  # unmatched_reference: pick a DB row
ACTION_CREATE_SUBSTITUTION_RULE = "create_substitution_rule"
ACTION_EDIT_VALUE = "edit_value"          # bad_date_format, negative_amount: inline edit
ACTION_IGNORE_ROW = "ignore_row"          # any per-row issue: drop just this row


# --- constructors ----------------------------------------------------------


def make_issue(
    *,
    type: str,
    severity: str = SEVERITY_ERROR,
    location: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
    proposed_actions: Optional[List[str]] = None,
    message: Optional[str] = None,
) -> Dict[str, Any]:
    """Build one ``Issue`` dict with a fresh issue_id.

    Pure helper; no DB. Callers pass the result into
    ``ImportSession.open_issues`` via a services-layer mutator.
    """
    if type not in ISSUE_TYPES:
        raise ValueError(f"unknown issue type: {type!r}")
    if severity not in SEVERITIES:
        raise ValueError(f"unknown severity: {severity!r}")
    return {
        "issue_id": f"iss-{uuid.uuid4().hex[:12]}",
        "type": type,
        "severity": severity,
        "location": location or {},
        "context": context or {},
        "proposed_actions": proposed_actions or [],
        "message": message,
    }


def has_blocking_issues(issues: List[Dict[str, Any]]) -> bool:
    """True if any ``error``-severity issue is present. Warnings don't block."""
    return any(i.get("severity") == SEVERITY_ERROR for i in (issues or []))


def count_by_type(issues: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for i in issues or []:
        t = i.get("type")
        if t:
            out[t] = out.get(t, 0) + 1
    return out
