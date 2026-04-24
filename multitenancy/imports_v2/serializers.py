"""Response serializers for the v2 import endpoints.

Thin — the session's JSON blobs already carry client-shaped data, so
serializers mostly decorate with computed fields (``issue_counts``,
``is_committable``) and pick which columns the client sees. We don't
serialize ``file_bytes`` (never — client only ever needed the hash).
"""
from __future__ import annotations

from rest_framework import serializers

from multitenancy.models import ImportSession

from . import issues as issue_mod


class ImportSessionSerializer(serializers.ModelSerializer):
    """Full session view — used by GET, analyze, resolve, commit responses.

    Deliberately omits ``file_bytes`` (large binary) and ``config``'s
    implementation-secret fields; operator sees only what they'd need
    to make a decision.
    """

    issue_counts = serializers.SerializerMethodField()
    is_committable = serializers.SerializerMethodField()
    is_terminal = serializers.SerializerMethodField()
    substitutions_applied = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()
    transaction_groups = serializers.SerializerMethodField()
    preview = serializers.SerializerMethodField()

    class Meta:
        model = ImportSession
        fields = (
            "id",
            "company",
            "mode",
            "status",
            "file_name",
            "file_hash",
            "created_at",
            "updated_at",
            "expires_at",
            "committed_at",
            "open_issues",
            "resolutions",
            "staged_substitution_rules",
            "result",
            "summary",
            "issue_counts",
            "is_committable",
            "is_terminal",
            "substitutions_applied",
            "transaction_groups",
            "preview",
        )
        read_only_fields = fields

    def get_issue_counts(self, obj):
        return issue_mod.count_by_type(obj.open_issues or [])

    def get_is_committable(self, obj):
        return obj.is_committable()

    def get_is_terminal(self, obj):
        return obj.is_terminal()

    def get_substitutions_applied(self, obj):
        """Pulled out of ``parsed_payload`` so the client has a single flat
        list to render in the "Substituições aplicadas" panel without
        reaching into internal shape. Empty list in Phase 2 (no
        substitutions run yet)."""
        return (obj.parsed_payload or {}).get("substitutions_applied", [])

    def get_summary(self, obj):
        """Per-sheet row counts — cheap summary for the diagnostics header."""
        sheets = (obj.parsed_payload or {}).get("sheets", {}) or {}
        # ETL mode stores under ``transformed_data`` instead of ``sheets``;
        # use that when present so the header count is non-zero in ETL v2.
        if not sheets:
            td = (obj.parsed_payload or {}).get("transformed_data", {}) or {}
            sheets = td if isinstance(td, dict) else {}
        return {
            "sheets": {
                name: len(rows or []) if isinstance(rows, list) else 0
                for name, rows in sheets.items()
            },
        }

    def get_transaction_groups(self, obj):
        """Compact per-``__erp_id`` grouping of the Transaction rows, used
        by the ETL v2 "Grupos de erp_id" panel. One entry per distinct
        erp_id plus a sentinel (``erp_id=None``) bucket for rows that
        lack one. Each entry carries the full rows so the UI can expand
        and show them — compact enough because Transaction payloads
        rarely exceed a few dozen columns.

        Empty for template sessions (grouping is derived at commit time
        via the backend's Phase-0 ``_group_transaction_rows_by_erp_id``
        helper). Empty for ETL sessions with no Transaction rows.

        The ``hasConflict`` flag is layered on via open_issues.erp_id_conflict
        entries — the frontend could derive this itself, but inlining it
        here avoids N⁺¹ matching work on the client.
        """
        payload = obj.parsed_payload or {}
        # ETL mode: transformed_data.Transaction
        tx_rows = None
        td = payload.get("transformed_data")
        if isinstance(td, dict):
            candidate = td.get("Transaction")
            if isinstance(candidate, list):
                tx_rows = candidate
        # Fallback: template mode stores under sheets.Transaction. Groups
        # are less informative there (template rows ARE Transactions 1:1
        # pre-grouping), but we still surface them for uniformity.
        if tx_rows is None:
            sheets = payload.get("sheets")
            if isinstance(sheets, dict):
                candidate = sheets.get("Transaction")
                if isinstance(candidate, list):
                    tx_rows = candidate
        if not tx_rows:
            return []

        conflict_erp_ids = set()
        for issue in obj.open_issues or []:
            if (
                isinstance(issue, dict)
                and issue.get("type") == "erp_id_conflict"
            ):
                loc = issue.get("location") or {}
                eid = loc.get("erp_id")
                if eid:
                    conflict_erp_ids.add(str(eid))

        groups: dict = {}
        for row in tx_rows:
            if not isinstance(row, dict):
                continue
            erp = row.get("__erp_id")
            # Canonicalise "missing" / empty string to None so the sentinel
            # bucket catches all erp_id-less rows in one place.
            key = erp if (isinstance(erp, str) and erp) else None
            g = groups.setdefault(key, {
                "erp_id": key,
                "row_count": 0,
                "has_conflict": (
                    isinstance(key, str) and key in conflict_erp_ids
                ),
                "rows": [],
            })
            g["row_count"] += 1
            g["rows"].append(row)
        return list(groups.values())

    def get_preview(self, obj):
        """Dry-run counts from the analyze phase.

        For ETL sessions: ``ETLPipelineService.execute(commit=False)``
        already computes ``would_create`` / ``would_fail`` /
        ``total_rows`` — we surface them here for the frontend's
        "Prévia da importação" panel.

        For template sessions: empty dict (we don't run a commit=False
        dry-run at analyze yet — that's a follow-up commit; running
        execute_import_job twice per session doubles analyze cost on
        large imports, so it needs its own design pass).

        Backward compatible: a session created before this field existed
        reads as an empty dict.
        """
        preview = (obj.parsed_payload or {}).get("preview")
        if isinstance(preview, dict):
            return preview
        return {}
