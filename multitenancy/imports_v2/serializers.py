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
    progress = serializers.SerializerMethodField()

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
            # Phase 6.z-e — live progress snapshot. Empty dict for
            # non-running sessions.
            "progress",
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

    def get_progress(self, obj):
        """Merge DB progress snapshot with live Redis data (Phase 6.z-g).

        For non-terminal sessions, Redis holds the freshest intra-atomic
        row-level state (rows_processed, current_sheet, etc.); the DB
        snapshot only updates at stage boundaries outside the commit
        atomic block. Merge policy: start with the DB snapshot, let
        Redis fields override where they exist. That way stage-level
        fields published pre-atomic still show up, and row-level
        fields published during the write overwrite the generic
        ``stage=writing`` placeholder.

        Terminal sessions read only the DB value — Redis should be
        cleared by the worker on terminal, but we don't trust that
        to be instantaneous.
        """
        db_progress = obj.progress or {}
        if obj.is_terminal():
            return db_progress
        # Lazy import — keeps this module import-safe in environments
        # without the redis package (it's optional at runtime, not
        # build time).
        from . import progress_channel
        live = progress_channel.read(obj.pk)
        if not live:
            return db_progress
        if not isinstance(db_progress, dict):
            return live
        return {**db_progress, **live}

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


class ImportSessionListSerializer(serializers.ModelSerializer):
    """Lightweight session view for the queue list endpoint (Phase 6.z-b).

    Intentionally excludes ``parsed_payload``, ``open_issues`` (full
    entries), ``result``, ``staged_substitution_rules`` — those are
    multi-MB on a large import. The queue UI only needs filename,
    mode, status, timestamps, operator, and an issue-count badge.

    ``operator_name`` resolves the ``created_by`` FK inline so the
    queue doesn't need a second request to render rows. A missing
    user (deleted, never set) renders as ``None`` — the frontend
    shows "—".
    """

    is_terminal = serializers.SerializerMethodField()
    operator_name = serializers.SerializerMethodField()
    open_issue_count = serializers.SerializerMethodField()
    transformation_rule_name = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()

    class Meta:
        model = ImportSession
        fields = (
            "id",
            "mode",
            "status",
            "file_name",
            "file_hash",
            "created_at",
            "updated_at",
            "committed_at",
            "operator_name",
            "open_issue_count",
            "is_terminal",
            "transformation_rule_name",
            # Phase 6.z-e — small enough to inline per queue row so
            # running sessions show their stage + sheets_done/_total
            # without a second request.
            "progress",
        )
        read_only_fields = fields

    def get_is_terminal(self, obj):
        return obj.is_terminal()

    def get_operator_name(self, obj):
        """Prefer full name, fall back to username. Returns ``None`` when
        the FK is missing so the frontend can render a dash."""
        if not obj.created_by_id:
            return None
        user = getattr(obj, "created_by", None)
        if user is None:
            return None
        full = (user.get_full_name() or "").strip()
        return full or user.username or None

    def get_open_issue_count(self, obj):
        issues = obj.open_issues or []
        return len(issues) if isinstance(issues, list) else 0

    def get_transformation_rule_name(self, obj):
        """ETL-mode rows show the rule name in the queue so operators
        can tell two imports of the same file apart. Template rows
        return ``None``."""
        rule = getattr(obj, "transformation_rule", None)
        return getattr(rule, "name", None) if rule else None

    def get_progress(self, obj):
        """Merge DB snapshot with Redis live data — same policy as the
        full-session serializer. The queue refreshes every 3s while
        any row is running, so per-row Redis updates show up as
        inline progress badges (``75%`` etc.) within seconds of the
        worker publishing them."""
        db_progress = obj.progress or {}
        if obj.is_terminal():
            return db_progress
        from . import progress_channel
        live = progress_channel.read(obj.pk)
        if not live:
            return db_progress
        if not isinstance(db_progress, dict):
            return live
        return {**db_progress, **live}
