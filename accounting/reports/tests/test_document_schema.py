"""Tests for the pydantic document schema."""

import pytest
from pydantic import ValidationError

from accounting.reports.services.document_schema import (
    TemplateDocument,
    collect_block_ids,
    validate_document,
)


def _minimal_doc():
    return {
        "name": "Min",
        "report_type": "income_statement",
        "blocks": [
            {"type": "line", "id": "a", "label": "A"},
        ],
    }


def test_valid_minimal_document():
    doc = validate_document(_minimal_doc())
    assert isinstance(doc, TemplateDocument)
    assert doc.name == "Min"
    assert len(doc.blocks) == 1


def test_nested_sections_are_supported():
    data = {
        "name": "DRE",
        "report_type": "income_statement",
        "blocks": [
            {
                "type": "section",
                "id": "rev",
                "label": "Receita",
                "children": [
                    {"type": "line", "id": "a", "label": "A"},
                    {"type": "line", "id": "b", "label": "B"},
                    {"type": "subtotal", "id": "rev_total", "label": "Total"},
                ],
            }
        ],
    }
    doc = validate_document(data)
    assert collect_block_ids(doc) == ["rev", "a", "b", "rev_total"]


def test_duplicate_ids_rejected():
    data = _minimal_doc()
    data["blocks"].append({"type": "line", "id": "a", "label": "A (dup)"})
    with pytest.raises(ValidationError) as exc:
        validate_document(data)
    assert "Duplicate" in str(exc.value)


def test_invalid_id_rejected():
    data = _minimal_doc()
    data["blocks"][0]["id"] = "123bad"  # must start with letter/underscore
    with pytest.raises(ValidationError):
        validate_document(data)


def test_extra_fields_rejected():
    data = _minimal_doc()
    data["blocks"][0]["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        validate_document(data)


def test_unknown_block_type_rejected():
    data = _minimal_doc()
    data["blocks"].append({"type": "chart", "id": "x", "label": "?"})
    with pytest.raises(ValidationError):
        validate_document(data)
