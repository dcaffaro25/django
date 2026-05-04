"""Tests for the MCP server tool registry.

These tests do NOT require the ``mcp`` Python package — they only exercise
the registry / dispatcher layer in :mod:`mcp_server.tools`. Tool *content*
(field names, ORM access) is validated by the host services' own tests;
here we just lock the registry surface so a renamed handler doesn't slip
through unnoticed.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from mcp_server.tools import TOOLS, TOOLS_BY_NAME, call_tool


class McpToolRegistryTests(SimpleTestCase):
    def test_registry_unique_names(self):
        names = [t.name for t in TOOLS]
        self.assertEqual(len(names), len(set(names)), "tool names must be unique")

    def test_registry_handlers_callable(self):
        for tool in TOOLS:
            self.assertTrue(callable(tool.handler), f"{tool.name} handler not callable")

    def test_registry_input_schemas_are_jsonschema_objects(self):
        for tool in TOOLS:
            schema = tool.input_schema
            self.assertEqual(schema.get("type"), "object", f"{tool.name} schema must be object")
            self.assertIn("properties", schema, f"{tool.name} schema missing properties")
            self.assertIsInstance(schema.get("required", []), list, f"{tool.name} required must be list")

    def test_required_tools_are_present(self):
        # The agent + the operator UI both depend on these. Lock them.
        for required in (
            "list_companies",
            "list_accounts",
            "get_transaction",
            "list_unreconciled_bank_transactions",
            "suggest_reconciliation",
            "get_invoice",
            "list_invoice_critics",
            "get_nota_fiscal",
            "financial_statements",
        ):
            self.assertIn(required, TOOLS_BY_NAME, f"missing tool: {required}")

    def test_call_tool_unknown_raises(self):
        with self.assertRaises(KeyError):
            call_tool("does_not_exist", {})

    def test_company_id_is_required_on_tenant_scoped_tools(self):
        # Every tool except list_companies must take ``company_id``.
        non_scoped = {"list_companies"}
        for tool in TOOLS:
            if tool.name in non_scoped:
                continue
            required = tool.input_schema.get("required", [])
            self.assertIn(
                "company_id", required,
                f"{tool.name} must require company_id (tenant scoping)",
            )
