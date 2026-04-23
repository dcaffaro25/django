"""Unit tests for Transaction row grouping by erp_id (Option B / 2a).

Documents the contract of ``_group_transaction_rows_by_erp_id`` — the
single grouping helper used by both Mode 1 (manual Transaction +
JournalEntry sheets) and Mode 2 (ETL auto-create-JE) to collapse
multiple import rows sharing the same ``erp_id`` into one logical
Transaction group.

The grouping semantics are documented in ``docs/manual/11-etl-importacao.md``
section 11.10c:

  * N rows with the same erp_id → one Transaction group.
  * If the rows agree on every ``shared_fields`` column → dedup to one
    Transaction in DB; all rows remain available for downstream JE
    processing (Mode 2 uses them as individual opposing legs).
  * If the rows disagree on any shared field → the whole group is a
    conflict; the caller must reject it with a clear per-field error.

This helper is PURE — it does not touch the database or call any
service. Good candidate for ``SimpleTestCase``.
"""
from django.test import SimpleTestCase

from multitenancy.tasks import _group_transaction_rows_by_erp_id


class GroupTransactionRowsByErpIdTests(SimpleTestCase):

    # --- happy path ---------------------------------------------------------

    def test_single_row_produces_single_group_no_conflict(self):
        rows = [
            {"__row_id": "r1", "__erp_id": "OMIE-1", "date": "2026-01-01",
             "amount": "1000.00", "entity_id": 42, "currency_id": 1},
        ]
        groups, conflicts = _group_transaction_rows_by_erp_id(
            rows, shared_fields=("date", "entity_id", "currency_id"),
        )
        self.assertEqual(list(groups.keys()), ["OMIE-1"])
        self.assertEqual(len(groups["OMIE-1"]), 1)
        self.assertEqual(conflicts, [])

    def test_two_rows_different_erp_ids_produce_two_groups(self):
        rows = [
            {"__row_id": "r1", "__erp_id": "OMIE-1", "date": "2026-01-01"},
            {"__row_id": "r2", "__erp_id": "OMIE-2", "date": "2026-01-02"},
        ]
        groups, conflicts = _group_transaction_rows_by_erp_id(
            rows, shared_fields=("date",),
        )
        self.assertEqual(sorted(groups.keys()), ["OMIE-1", "OMIE-2"])
        self.assertEqual(len(groups["OMIE-1"]), 1)
        self.assertEqual(len(groups["OMIE-2"]), 1)
        self.assertEqual(conflicts, [])

    # --- agreement: two rows, identical shared fields -----------------------

    def test_two_rows_same_erp_id_agreeing_on_all_fields_no_conflict(self):
        """Both rows present — caller will decide to dedup or fan out (Mode 2)."""
        rows = [
            {"__row_id": "r1", "__erp_id": "OMIE-1", "date": "2026-01-01",
             "entity_id": 42, "amount": "500.00"},
            {"__row_id": "r2", "__erp_id": "OMIE-1", "date": "2026-01-01",
             "entity_id": 42, "amount": "300.00"},  # amount is not a shared field
        ]
        groups, conflicts = _group_transaction_rows_by_erp_id(
            rows, shared_fields=("date", "entity_id"),
        )
        self.assertEqual(list(groups.keys()), ["OMIE-1"])
        self.assertEqual(len(groups["OMIE-1"]), 2)
        self.assertEqual(conflicts, [])

    # --- conflict: two rows, same erp_id, diverging field -------------------

    def test_two_rows_same_erp_id_conflict_on_one_field(self):
        rows = [
            {"__row_id": "r1", "__erp_id": "OMIE-1", "date": "2026-01-01",
             "entity_id": 42},
            {"__row_id": "r2", "__erp_id": "OMIE-1", "date": "2026-01-02",
             "entity_id": 42},
        ]
        groups, conflicts = _group_transaction_rows_by_erp_id(
            rows, shared_fields=("date", "entity_id"),
        )
        self.assertEqual(len(conflicts), 1)
        c = conflicts[0]
        self.assertEqual(c["erp_id"], "OMIE-1")
        self.assertEqual(sorted(c["row_ids"]), ["r1", "r2"])
        # ``fields`` maps the diverging field to the set of distinct values.
        self.assertIn("date", c["fields"])
        self.assertEqual(
            sorted(str(v) for v in c["fields"]["date"]),
            ["2026-01-01", "2026-01-02"],
        )
        # entity_id is shared + agrees → not in conflicts["fields"]
        self.assertNotIn("entity_id", c["fields"])

    def test_two_rows_same_erp_id_conflict_on_multiple_fields(self):
        rows = [
            {"__row_id": "r1", "__erp_id": "OMIE-1", "date": "2026-01-01",
             "currency_id": 1, "entity_id": 42},
            {"__row_id": "r2", "__erp_id": "OMIE-1", "date": "2026-01-02",
             "currency_id": 2, "entity_id": 42},
        ]
        groups, conflicts = _group_transaction_rows_by_erp_id(
            rows, shared_fields=("date", "currency_id", "entity_id"),
        )
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(sorted(conflicts[0]["fields"].keys()),
                         ["currency_id", "date"])

    def test_three_rows_same_erp_id_one_outlier(self):
        """Rows 1+2 agree, row 3 diverges — one conflict listing all three row ids."""
        rows = [
            {"__row_id": "r1", "__erp_id": "OMIE-1", "date": "2026-01-01"},
            {"__row_id": "r2", "__erp_id": "OMIE-1", "date": "2026-01-01"},
            {"__row_id": "r3", "__erp_id": "OMIE-1", "date": "2026-01-99"},
        ]
        groups, conflicts = _group_transaction_rows_by_erp_id(
            rows, shared_fields=("date",),
        )
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(sorted(conflicts[0]["row_ids"]), ["r1", "r2", "r3"])

    # --- multiple independent groups with mixed status ----------------------

    def test_mixed_good_group_and_conflicted_group(self):
        rows = [
            {"__row_id": "r1", "__erp_id": "GOOD-1", "date": "2026-01-01"},
            {"__row_id": "r2", "__erp_id": "GOOD-1", "date": "2026-01-01"},
            {"__row_id": "r3", "__erp_id": "BAD-1", "date": "2026-02-01"},
            {"__row_id": "r4", "__erp_id": "BAD-1", "date": "2026-02-02"},
        ]
        groups, conflicts = _group_transaction_rows_by_erp_id(
            rows, shared_fields=("date",),
        )
        # Both groups exist in ``groups`` regardless — caller decides what to
        # do with conflicted ones. Keeps ``groups`` simple: one key per erp_id.
        self.assertEqual(sorted(groups.keys()), ["BAD-1", "GOOD-1"])
        # But only BAD-1 shows up in conflicts.
        self.assertEqual([c["erp_id"] for c in conflicts], ["BAD-1"])

    # --- edge cases ---------------------------------------------------------

    def test_rows_without_erp_id_ignored(self):
        """Rows lacking ``__erp_id`` are not grouped — caller handles them separately."""
        rows = [
            {"__row_id": "r1", "date": "2026-01-01"},  # no __erp_id at all
            {"__row_id": "r2", "__erp_id": "", "date": "2026-01-01"},  # empty
            {"__row_id": "r3", "__erp_id": None, "date": "2026-01-01"},  # None
            {"__row_id": "r4", "__erp_id": "OMIE-1", "date": "2026-01-01"},
        ]
        groups, conflicts = _group_transaction_rows_by_erp_id(
            rows, shared_fields=("date",),
        )
        self.assertEqual(list(groups.keys()), ["OMIE-1"])
        self.assertEqual(len(groups["OMIE-1"]), 1)
        self.assertEqual(conflicts, [])

    def test_delete_rows_prefixed_with_dash_ignored(self):
        """``__erp_id`` starting with ``-`` is a delete marker, not a group key."""
        rows = [
            {"__row_id": "r1", "__erp_id": "-OMIE-1"},
            {"__row_id": "r2", "__erp_id": "OMIE-2", "date": "2026-01-01"},
        ]
        groups, conflicts = _group_transaction_rows_by_erp_id(
            rows, shared_fields=("date",),
        )
        self.assertEqual(list(groups.keys()), ["OMIE-2"])
        self.assertEqual(conflicts, [])

    def test_erp_id_whitespace_trimmed_before_grouping(self):
        """Trailing/leading whitespace on erp_id shouldn't split a group."""
        rows = [
            {"__row_id": "r1", "__erp_id": "OMIE-1", "date": "2026-01-01"},
            {"__row_id": "r2", "__erp_id": " OMIE-1 ", "date": "2026-01-01"},
        ]
        groups, conflicts = _group_transaction_rows_by_erp_id(
            rows, shared_fields=("date",),
        )
        self.assertEqual(list(groups.keys()), ["OMIE-1"])
        self.assertEqual(len(groups["OMIE-1"]), 2)

    def test_empty_input_returns_empty_groups(self):
        groups, conflicts = _group_transaction_rows_by_erp_id(
            [], shared_fields=("date",),
        )
        self.assertEqual(groups, {})
        self.assertEqual(conflicts, [])

    def test_none_vs_missing_field_treated_as_same_absence(self):
        """``None`` and an absent key both mean "no value" — shouldn't conflict."""
        rows = [
            {"__row_id": "r1", "__erp_id": "OMIE-1", "description": None},
            {"__row_id": "r2", "__erp_id": "OMIE-1"},  # description missing
        ]
        groups, conflicts = _group_transaction_rows_by_erp_id(
            rows, shared_fields=("description",),
        )
        self.assertEqual(conflicts, [])

    def test_group_preserves_row_order(self):
        """Rows within a group stay in sheet order (Mode 2 needs stable ordering
        for "first-row-wins" Tx-level fields and for bank-leg description
        inheritance)."""
        rows = [
            {"__row_id": "r3", "__erp_id": "OMIE-1", "date": "2026-01-01"},
            {"__row_id": "r1", "__erp_id": "OMIE-1", "date": "2026-01-01"},
            {"__row_id": "r2", "__erp_id": "OMIE-1", "date": "2026-01-01"},
        ]
        groups, _ = _group_transaction_rows_by_erp_id(
            rows, shared_fields=("date",),
        )
        self.assertEqual([r["__row_id"] for r in groups["OMIE-1"]],
                         ["r3", "r1", "r2"])
