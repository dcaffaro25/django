"""Unit tests for bulk import __row_id classification."""
from django.test import SimpleTestCase

from multitenancy.tasks import _parse_import_row_id


class ParseImportRowIdTests(SimpleTestCase):
    def test_create_alphanumeric(self):
        mode, detail, disp = _parse_import_row_id("bp1")
        self.assertEqual(mode, "create")
        self.assertEqual(detail, "bp1")
        self.assertEqual(disp, "bp1")

    def test_create_none(self):
        mode, detail, disp = _parse_import_row_id(None)
        self.assertEqual(mode, "create")
        self.assertIsNone(detail)
        self.assertIsNone(disp)

    def test_update_positive_int(self):
        mode, detail, disp = _parse_import_row_id(42)
        self.assertEqual(mode, "update")
        self.assertEqual(detail, 42)
        self.assertEqual(disp, 42)

    def test_update_positive_string(self):
        mode, detail, disp = _parse_import_row_id("99")
        self.assertEqual(mode, "update")
        self.assertEqual(detail, 99)

    def test_delete_negative_int(self):
        mode, detail, disp = _parse_import_row_id(-7)
        self.assertEqual(mode, "delete")
        self.assertEqual(detail, 7)
        self.assertEqual(disp, -7)

    def test_delete_negative_float(self):
        mode, detail, disp = _parse_import_row_id(-3.0)
        self.assertEqual(mode, "delete")
        self.assertEqual(detail, 3)

    def test_zero_error(self):
        mode, detail, _ = _parse_import_row_id(0)
        self.assertEqual(mode, "error")
        self.assertIsInstance(detail, str)

    def test_bool_error(self):
        mode, detail, _ = _parse_import_row_id(True)
        self.assertEqual(mode, "error")

    def test_non_integer_float_error(self):
        mode, detail, _ = _parse_import_row_id(1.5)
        self.assertEqual(mode, "error")
