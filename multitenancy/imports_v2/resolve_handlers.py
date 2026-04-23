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


def handle_edit_value(
    session: ImportSession,
    issue: Dict[str, Any],
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Inline-edit a single row's field. Used by ``bad_date_format`` and
    ``negative_amount``.

    params: ``{"row_id": <id>, "field": <target field>, "new_value": <any>}``.

    The operator provides the replacement value directly; handler only
    validates shape, then writes. Re-detection after the batch catches
    a bad correction (e.g. operator typed another invalid date).
    """
    allowed = {
        issue_mod.ISSUE_BAD_DATE_FORMAT,
        issue_mod.ISSUE_NEGATIVE_AMOUNT,
    }
    if issue.get("type") not in allowed:
        raise ResolutionError(
            f"edit_value applies to {sorted(allowed)!r}, not "
            f"{issue.get('type')!r}"
        )
    row_id = params.get("row_id") if isinstance(params, dict) else None
    field = params.get("field") if isinstance(params, dict) else None
    if row_id is None:
        raise ResolutionError("edit_value requires params.row_id")
    if not field:
        raise ResolutionError("edit_value requires params.field")
    if "new_value" not in (params or {}):
        raise ResolutionError("edit_value requires params.new_value")
    new_value = params["new_value"]

    location = issue.get("location") or {}
    sheet = location.get("sheet")
    if not sheet:
        raise ResolutionError("edit_value requires issue.location.sheet")

    rows = _get_rows(session, sheet)
    old_value = None
    updated = 0
    for row in rows:
        if _row_id(row) == row_id:
            old_value = row.get(field)
            row[field] = new_value
            updated += 1
    if updated == 0:
        raise ResolutionError(
            f"no row with row_id={row_id!r} in sheet {sheet!r}"
        )
    _set_rows(session, sheet, rows)
    return {
        "sheet": sheet,
        "row_id": row_id,
        "field": field,
        "old_value": old_value,
        "new_value": new_value,
        "rows_updated": updated,
    }


def handle_map_to_existing(
    session: ImportSession,
    issue: Dict[str, Any],
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """``unmatched_reference`` / ``fk_ambiguous``: rewrite every row in
    the issue's sheet whose ``location.field`` equals the unresolved
    value so it points at the DB row the operator picked.

    params:
      * ``target_id`` (required) — the id of the DB row to map to.
      * ``create_substitution_rule`` (optional bool, default False) —
        when true, append a staged ``SubstitutionRule`` spec to
        ``session.staged_substitution_rules`` so commit materialises
        it for future imports.
      * ``rule`` (optional dict) — overrides for the staged rule's
        ``match_type`` / ``match_value`` / ``filter_conditions`` /
        ``title``. Defaults: exact match on the original value.
    """
    allowed = {
        issue_mod.ISSUE_UNMATCHED_REFERENCE,
        issue_mod.ISSUE_FK_AMBIGUOUS,
    }
    if issue.get("type") not in allowed:
        raise ResolutionError(
            f"map_to_existing applies to {sorted(allowed)!r}, not "
            f"{issue.get('type')!r}"
        )
    target_id = params.get("target_id") if isinstance(params, dict) else None
    if target_id is None:
        raise ResolutionError("map_to_existing requires params.target_id")

    location = issue.get("location") or {}
    context = issue.get("context") or {}
    sheet = location.get("sheet")
    field = location.get("field")
    original_value = location.get("value")
    if original_value is None:
        original_value = context.get("value")
    if not sheet or not field:
        raise ResolutionError(
            "map_to_existing requires issue.location.sheet + .field"
        )

    rows = _get_rows(session, sheet)
    updated = 0
    for row in rows:
        if row.get(field) == original_value:
            row[field] = target_id
            updated += 1
    _set_rows(session, sheet, rows)

    staged = False
    if params.get("create_substitution_rule") is True:
        rule_spec = params.get("rule") or {}
        related_model = context.get("related_model")
        if not related_model:
            raise ResolutionError(
                "map_to_existing create_substitution_rule needs "
                "issue.context.related_model (detector must populate it)"
            )
        rule_entry = {
            "model_name": related_model,
            "field_name": rule_spec.get("field_name") or "id",
            "match_type": rule_spec.get("match_type") or "exact",
            "match_value": rule_spec.get("match_value",
                                         str(original_value) if original_value is not None else ""),
            "substitution_value": str(target_id),
            "filter_conditions": rule_spec.get("filter_conditions"),
            "title": rule_spec.get("title") or (
                f"via resolve session #{session.pk}"
            ),
        }
        session.staged_substitution_rules = list(
            session.staged_substitution_rules or []
        ) + [rule_entry]
        staged = True

    return {
        "sheet": sheet,
        "field": field,
        "original_value": original_value,
        "mapped_to": target_id,
        "rows_updated": updated,
        "staged_rule": staged,
    }


# --- dispatcher ------------------------------------------------------------


# Map action → handler. Registered here rather than in a massive if/elif
# so Phase 4B can drop in ``map_to_existing`` / ``edit_value`` without
# touching the orchestrator.
ACTION_HANDLERS = {
    issue_mod.ACTION_PICK_ROW: handle_pick_row,
    issue_mod.ACTION_SKIP_GROUP: handle_skip_group,
    issue_mod.ACTION_IGNORE_ROW: handle_ignore_row,
    issue_mod.ACTION_ABORT: handle_abort,
    issue_mod.ACTION_EDIT_VALUE: handle_edit_value,
    issue_mod.ACTION_MAP_TO_EXISTING: handle_map_to_existing,
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
