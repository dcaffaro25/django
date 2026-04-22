"""Tests for the slim AI schema + slim_to_canonical converter.

The slim schema is what the OpenAI Structured Outputs sampler actually
receives; the canonical :class:`TemplateDocument` is the server's
source of truth. These tests guard the round-trip:

  * The slim schema itself is valid under OpenAI's strict dialect.
  * A representative AI output (flat + parent_id) reassembles correctly
    into the canonical tree shape.
  * Edge cases — orphaned parent_id, unknown fields, root-only blocks,
    deeply nested sections — don't break the converter.
"""

import json

import pytest

from accounting.reports.services.document_schema import (
    SlimTemplateDocument,
    TemplateDocument,
    slim_to_canonical,
    to_openai_strict_schema,
    validate_document,
)


# --- Schema shape --------------------------------------------------------


def _walk(obj, path=""):
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            yield from _walk(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")


def test_slim_schema_is_strict_openai_compliant():
    schema = to_openai_strict_schema(SlimTemplateDocument.model_json_schema())
    for path, node in _walk(schema):
        if isinstance(node, dict) and node.get("type") == "object" and "properties" in node:
            assert node.get("additionalProperties") is False, (
                f"{path}: missing additionalProperties: false"
            )
            # Every property must appear in ``required`` (strict mode).
            assert set(node.get("required", [])) == set(node["properties"].keys()), (
                f"{path}: required does not cover all properties"
            )


def test_slim_schema_is_smaller_than_canonical():
    """Regression guard: if this flips, the slim schema's bulk has crept
    back up and we should re-benchmark against Structured Outputs.
    """
    slim = to_openai_strict_schema(SlimTemplateDocument.model_json_schema())
    canonical = to_openai_strict_schema()
    assert len(json.dumps(slim)) < len(json.dumps(canonical)), (
        "slim schema is no longer smaller than canonical"
    )


# --- Converter: happy path -----------------------------------------------


def _slim_sample() -> dict:
    """Representative AI output: a 3-section DRE with a subtotal per
    section and a top-level total formula."""
    return {
        "name": "DRE — Exemplo",
        "report_type": "income_statement",
        "defaults": {
            "calculation_method": "net_movement",
            "sign_policy": "natural",
            "scale": "none",
            "decimal_places": 2,
        },
        "blocks": [
            {"type": "section", "id": "revenue", "label": "Receita",
             "parent_id": None},
            {"type": "line", "id": "sales", "label": "Vendas",
             "parent_id": "revenue",
             "accounts": {"code_prefix": "4.01", "include_descendants": True}},
            {"type": "subtotal", "id": "revenue_total", "label": "Total Receita",
             "parent_id": "revenue", "formula": "sum(children)"},

            {"type": "section", "id": "expenses", "label": "Despesas",
             "parent_id": None},
            {"type": "line", "id": "opex", "label": "OPEX",
             "parent_id": "expenses",
             "accounts": {"code_prefix": "5.01"}},
            {"type": "subtotal", "id": "expenses_total", "label": "Total Despesas",
             "parent_id": "expenses", "formula": "sum(children)"},

            {"type": "total", "id": "net_income", "label": "Lucro Líquido",
             "parent_id": None,
             "formula": "revenue_total - expenses_total"},
        ],
    }


def test_slim_to_canonical_rebuilds_tree_from_parent_ids():
    doc = slim_to_canonical(_slim_sample(), report_type="income_statement")
    # Top-level blocks: 2 sections + 1 total = 3
    assert len(doc["blocks"]) == 3
    sections = [b for b in doc["blocks"] if b["type"] == "section"]
    assert len(sections) == 2
    assert sections[0]["id"] == "revenue"
    # Section has rebuilt children
    assert {c["id"] for c in sections[0]["children"]} == {"sales", "revenue_total"}
    # parent_id is NOT in the canonical output
    for c in sections[0]["children"]:
        assert "parent_id" not in c


def test_slim_to_canonical_fills_bold_on_totals_and_subtotals():
    doc = slim_to_canonical(_slim_sample(), report_type="income_statement")
    # Top-level total
    total = next(b for b in doc["blocks"] if b["type"] == "total")
    assert total.get("bold") is True
    # Subtotal inside a section
    revenue = next(b for b in doc["blocks"] if b.get("id") == "revenue")
    sub = next(c for c in revenue["children"] if c["type"] == "subtotal")
    assert sub.get("bold") is True


def test_slim_to_canonical_fills_indent_by_depth():
    doc = slim_to_canonical(_slim_sample(), report_type="income_statement")
    # Top-level: indent=0
    for b in doc["blocks"]:
        if b["type"] not in ("spacer",):
            assert b.get("indent") == 0, f"{b['id']} at root should be indent=0"
    # Children of a section: indent=1
    revenue = next(b for b in doc["blocks"] if b.get("id") == "revenue")
    for c in revenue["children"]:
        assert c.get("indent") == 1


def test_slim_to_canonical_output_passes_canonical_validation():
    doc = slim_to_canonical(_slim_sample(), report_type="income_statement")
    # If validate_document raises we've regressed the contract.
    model = validate_document(doc)
    assert isinstance(model, TemplateDocument)
    assert model.report_type == "income_statement"


# --- Converter: defensive behaviour --------------------------------------


def test_slim_to_canonical_promotes_orphaned_parent_id_to_root(caplog):
    """An AI hallucination that references a nonexistent parent should
    not lose the block — we promote it to root and log a warning."""
    slim = {
        "name": "Orphan Test",
        "report_type": "income_statement",
        "defaults": None,
        "blocks": [
            {"type": "line", "id": "stray", "label": "Stray",
             "parent_id": "does_not_exist"},
        ],
    }
    doc = slim_to_canonical(slim, report_type="income_statement")
    assert len(doc["blocks"]) == 1
    assert doc["blocks"][0]["id"] == "stray"


def test_slim_to_canonical_coerces_report_type_from_caller():
    slim = _slim_sample()
    slim["report_type"] = "balance_sheet"  # wrong on purpose
    doc = slim_to_canonical(slim, report_type="income_statement")
    assert doc["report_type"] == "income_statement"


def test_slim_to_canonical_strips_unknown_fields_per_block():
    """Even under strict SO the server should not trust the input. If
    someone wires a non-SO provider (Anthropic) through this path, the
    prompt-based JSON could carry stray keys."""
    slim = {
        "name": "Stray Fields",
        "report_type": "income_statement",
        "defaults": None,
        "blocks": [
            {"type": "line", "id": "x", "label": "X", "parent_id": None,
             "ai_explanation": "legacy field", "hide_if_zero": True},
        ],
    }
    doc = slim_to_canonical(slim, report_type="income_statement")
    block = doc["blocks"][0]
    assert "ai_explanation" not in block
    assert "hide_if_zero" not in block
    # Must still be canonical-valid
    validate_document(doc)


def test_slim_to_canonical_handles_nested_sections():
    """Three levels deep: group > subgroup > leaf."""
    slim = {
        "name": "Nested",
        "report_type": "income_statement",
        "defaults": None,
        "blocks": [
            {"type": "section", "id": "group", "label": "Group", "parent_id": None},
            {"type": "section", "id": "subgroup", "label": "Sub", "parent_id": "group"},
            {"type": "line", "id": "leaf", "label": "Leaf", "parent_id": "subgroup"},
        ],
    }
    doc = slim_to_canonical(slim, report_type="income_statement")
    group = doc["blocks"][0]
    subgroup = group["children"][0]
    leaf = subgroup["children"][0]
    assert group["indent"] == 0
    assert subgroup["indent"] == 1
    assert leaf["indent"] == 2
    validate_document(doc)


def test_slim_to_canonical_dedupes_duplicate_ids():
    """Observed AI failure: section + subtotal both named 'revenue'. We
    rename the duplicate rather than rejecting the whole document."""
    slim = {
        "name": "Dup Id",
        "report_type": "income_statement",
        "defaults": None,
        "blocks": [
            {"type": "section", "id": "revenue", "label": "Receita", "parent_id": None},
            {"type": "subtotal", "id": "revenue", "label": "Total Receita",
             "parent_id": "revenue", "formula": "sum(children)"},
        ],
    }
    doc = slim_to_canonical(slim, report_type="income_statement")
    # Validation succeeds (ids are unique now)
    validate_document(doc)
    ids = {doc["blocks"][0]["id"], doc["blocks"][0]["children"][0]["id"]}
    assert ids == {"revenue", "revenue_2"}


def test_slim_to_canonical_empty_blocks_list():
    slim = {
        "name": "Empty",
        "report_type": "income_statement",
        "defaults": None,
        "blocks": [],
    }
    doc = slim_to_canonical(slim, report_type="income_statement")
    assert doc["blocks"] == []
    validate_document(doc)


# --- Pydantic model validation ------------------------------------------


def test_slim_template_document_accepts_the_sample():
    SlimTemplateDocument.model_validate(_slim_sample())


def test_slim_template_document_rejects_children_field():
    """The AI MUST NOT emit ``children`` — that's a canonical-only field.
    Under strict SO this can't happen (extra='forbid'); this test guards
    the Anthropic fallback path."""
    bad = _slim_sample()
    bad["blocks"].append(
        {"type": "section", "id": "weird", "label": "W", "parent_id": None,
         "children": []}
    )
    with pytest.raises(Exception):
        SlimTemplateDocument.model_validate(bad)


def test_slim_template_document_rejects_ai_explanation():
    bad = _slim_sample()
    bad["blocks"][0]["ai_explanation"] = "should not be here"
    with pytest.raises(Exception):
        SlimTemplateDocument.model_validate(bad)
