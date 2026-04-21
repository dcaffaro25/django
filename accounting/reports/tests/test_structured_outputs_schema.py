"""Verify our pydantic → OpenAI-strict schema conversion."""

import json

from accounting.reports.services.document_schema import (
    TemplateDocument,
    to_openai_strict_schema,
    validate_document,
)


def _walk(obj, path=""):
    """Yield (path, value) tuples for every node in a JSON-schema dict."""
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            yield from _walk(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")


def test_every_object_has_additionalProperties_false():
    schema = to_openai_strict_schema()
    for path, node in _walk(schema):
        if isinstance(node, dict) and node.get("type") == "object" and "properties" in node:
            assert node.get("additionalProperties") is False, (
                f"object at {path!r} missing additionalProperties: false"
            )


def test_every_object_lists_every_property_as_required():
    """OpenAI Structured Outputs requires full required lists."""
    schema = to_openai_strict_schema()
    for path, node in _walk(schema):
        if isinstance(node, dict) and node.get("type") == "object" and "properties" in node:
            prop_keys = set(node["properties"].keys())
            required = set(node.get("required") or [])
            assert prop_keys == required, (
                f"required/properties mismatch at {path}: "
                f"missing {prop_keys - required}, extra {required - prop_keys}"
            )


def test_defs_are_preserved():
    """We shouldn't lose any block type definitions during the transform."""
    schema = to_openai_strict_schema()
    defs = schema.get("$defs") or {}
    # Our pydantic model emits one $def per block type + helpers.
    for expected in (
        "AccountsSelector", "BlockDefaults",
        "HeaderBlock", "LineBlock", "SectionBlock",
        "SpacerBlock", "SubtotalBlock", "TotalBlock",
    ):
        assert expected in defs, f"missing $def {expected}"


def test_nullable_anyof_pattern_preserved():
    """Optional[str] should survive as anyOf:[string,null] — that's OpenAI's
    canonical 'nullable required' pattern."""
    schema = to_openai_strict_schema()
    line = schema["$defs"]["LineBlock"]["properties"]
    # label is Optional[str]
    label = line["label"]
    types = set()
    for variant in label.get("anyOf", []):
        if "type" in variant:
            types.add(variant["type"])
    assert "null" in types, "Optional[str] must include a null variant"


def test_doesnt_mutate_input():
    """The transform must not modify the caller-supplied dict in-place."""
    original = TemplateDocument.model_json_schema()
    original_copy = json.loads(json.dumps(original))
    to_openai_strict_schema(original)
    assert original == original_copy, "converter mutated input dict"


def test_pydantic_still_accepts_a_minimal_doc():
    # Sanity: even after we mark every field required at the schema level,
    # pydantic itself still accepts documents where nullable fields are
    # simply omitted (our validate_document is the authoritative gate).
    doc = {
        "name": "T",
        "report_type": "income_statement",
        "blocks": [{"type": "line", "id": "a", "label": "A"}],
    }
    validate_document(doc)
