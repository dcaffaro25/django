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
        return {
            "sheets": {name: len(rows or []) for name, rows in sheets.items()},
        }
