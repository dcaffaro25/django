"""Per-action handlers for the v2 resolve endpoint.

One handler per ``ACTION_*`` constant in ``issues``. Each handler takes
the session (mutated in-place), the issue the operator is acting on,
and the resolution's ``params`` dict. Mutates ``session.parsed_payload``
as needed and returns a small result dict. The orchestrator in
``services.resolve_session`` is responsible for:

    * finding the issue by ``issue_id`` (and 400-ing when not found),
    * dispatching to the right handler per ``action``,
    * re-running issue detection on the updated payload, and
    * recording the resolution in ``session.resolutions``.

Handlers raise ``ResolutionError`` on bad params or when an action
doesn't apply to the issue type. The service turns that into a 400.

Phase 4 scope carries these action handlers:

  * ``pick_row``        — erp_id_conflict
  * ``skip_group``      — erp_id_conflict
  * ``ignore_row``      — any per-row issue (single-row drop)
  * ``abort``           — any issue (terminal kill switch)

Phase 4B (next commit) will add ``map_to_existing`` (staged rule
creation) and ``edit_value`` for ``bad_date_format`` / ``negative_amount``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from multitenancy.models import ImportSession

from . import issues as issue_mod


class ResolutionError(ValueError):
    """Raised on malformed/invalid resolve params.

    The orchestrator translates this into a 400 so the operator sees
    a specific message rather than a generic 500.
    """


# --- payload helpers -------------------------------------------------------
#
# Template mode stores rows under ``parsed_payload['sheets'][name]``;
# ETL mode under ``parsed_payload['transformed_data'][name]``. Handlers
# read through these helpers so action logic stays mode-agnostic.


def _rows_container(session: ImportSession) -> Dict[str, List[Dict[str, Any]]]:
    """Return the dict that holds sheet/model → [rows]. Mutable in-place.

    Adds the key if missing so handlers can assign through it without
    null-checks.
    """
    payload = session.parsed_payload or {}
    if session.mode == ImportSession.MODE_ETL:
        container = payload.setdefault("transformed_data", {})
    else:
        container = payload.setdefault("sheets", {})
    session.parsed_payload = payload
    return container


def _get_rows(session: ImportSession, sheet: str) -> List[Dict[str, Any]]:
    return list(_rows_container(session).get(sheet) or [])


def _set_rows(session: ImportSession, sheet: str, rows: List[Dict[str, Any]]) -> None:
    _rows_container(session)[sheet] = rows


def _row_id(row: Dict[str, Any]) -> Any:
    """Return the row's ``__row_id``. Handlers compare against the same
    raw value the detectors put in ``issue.location.row_ids`` — no
    normalisation here, else we'd drift from detector state."""
    return row.get("__row_id")


# --- action handlers -------------------------------------------------------


def handle_pick_row(
    session: ImportSession,
    issue: Dict[str, Any],
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """``erp_id_conflict``: keep exactly one row from the conflicting
    group, drop the rest.

    params: ``{"row_id": <one of the conflict's row_ids>}``.
    """
    if issue.get("type") != issue_mod.ISSUE_ERP_ID_CONFLICT:
        raise ResolutionError(
            f"pick_row only applies to erp_id_conflict, not {issue.get('type')!r}"
        )
    location = issue.get("location") or {}
    sheet = location.get("sheet")
    group_row_ids = location.get("row_ids") or []
    keep = params.get("row_id") if isinstance(params, dict) else None
    if keep is None:
        raise ResolutionError("pick_row requires params.row_id")
    if keep not in group_row_ids:
        raise ResolutionError(
            f"row_id {keep!r} is not in the conflicting group "
            f"(valid: {group_row_ids!r})"
        )

    drop_set = {r for r in group_row_ids if r != keep}
    before = _get_rows(session, sheet)
    kept = [r for r in before if _row_id(r) not in drop_set]
    _set_rows(session, sheet, kept)
    return {
        "sheet": sheet,
        "kept_row_id": keep,
        "dropped_row_ids": sorted(
            [r for r in drop_set if r is not None], key=lambda x: str(x)
        ),
        "rows_before": len(before),
        "rows_after": len(kept),
    }


def handle_skip_group(
    session: ImportSession,
    issue: Dict[str, Any],
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """``erp_id_conflict``: drop every row of the conflicting group."""
    if issue.get("type") != issue_mod.ISSUE_ERP_ID_CONFLICT:
        raise ResolutionError(
            f"skip_group only applies to erp_id_conflict, not {issue.get('type')!r}"
        )
    location = issue.get("location") or {}
    sheet = location.get("sheet")
    drop_set = set(location.get("row_ids") or [])
    before = _get_rows(session, sheet)
    kept = [r for r in before if _row_id(r) not in drop_set]
    _set_rows(session, sheet, kept)
    return {
        "sheet": sheet,
        "dropped_row_ids": sorted(
            [r for r in drop_set if r is not None], key=lambda x: str(x)
        ),
        "rows_before": len(before),
        "rows_after": len(kept),
    }


def handle_ignore_row(
    session: ImportSession,
    issue: Dict[str, Any],
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Drop a single row (by ``__row_id``) from the issue's sheet. Works
    for any issue type whose ``location`` names one sheet.

    params: ``{"row_id": <the row to drop>}``.
    """
    location = issue.get("location") or {}
    sheet = location.get("sheet")
    if not sheet:
        raise ResolutionError(
            "ignore_row requires issue.location.sheet (none present)"
        )
    row_id = params.get("row_id") if isinstance(params, dict) else None
    if row_id is None:
        raise ResolutionError("ignore_row requires params.row_id")
    before = _get_rows(session, sheet)
    kept = [r for r in before if _row_id(r) != row_id]
    _set_rows(session, sheet, kept)
    return {
        "sheet": sheet,
        "dropped_row_id": row_id,
        "rows_before": len(before),
        "rows_after": len(kept),
    }


def handle_abort(
    session: ImportSession,
    issue: Dict[str, Any],
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Flip the session to ``error``. Orchestrator short-circuits the
    rest of the resolution batch once abort lands so downstream handlers
    don't also try to mutate the payload."""
    reason = (
        params.get("reason") if isinstance(params, dict) else None
    ) or "operator_abort"
    return {"abort": True, "reason": reason, "via_issue_id": issue.get("issue_id")}


# --- dispatcher ------------------------------------------------------------


# Map action → handler. Registered here rather than in a massive if/elif
# so Phase 4B can drop in ``map_to_existing`` / ``edit_value`` without
# touching the orchestrator.
ACTION_HANDLERS = {
    issue_mod.ACTION_PICK_ROW: handle_pick_row,
    issue_mod.ACTION_SKIP_GROUP: handle_skip_group,
    issue_mod.ACTION_IGNORE_ROW: handle_ignore_row,
    issue_mod.ACTION_ABORT: handle_abort,
}


def apply_resolution(
    session: ImportSession,
    issue: Dict[str, Any],
    action: str,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Dispatch one ``{issue, action, params}`` tuple to its handler.

    Raises ``ResolutionError`` on unknown action or when the action
    isn't in the issue's ``proposed_actions`` whitelist (defence in
    depth — handler-level validation still runs).
    """
    handler = ACTION_HANDLERS.get(action)
    if handler is None:
        raise ResolutionError(f"unknown action: {action!r}")
    proposed = set(issue.get("proposed_actions") or [])
    if proposed and action not in proposed:
        raise ResolutionError(
            f"action {action!r} is not in the issue's proposed_actions "
            f"({sorted(proposed)!r})"
        )
    return handler(session, issue, params or {})
