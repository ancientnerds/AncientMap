"""Schema-aware sanitizer for structured_llm_call output.

Single-source regression for the entire "MiniMax emits string where
the schema says object" class of bugs. Every case here is a real
crash that took down a Theo handler in production:

* cross_pollination (commit c7a8948) — strings inside cp_array
* decomposition (commit 10f55ae) — strings inside angles array
* angle_audit (commit 10f55ae) — strings inside scored_sources / rejected_sources
* angle_specialist (commit 428cf67) — strings inside findings array
"""

from __future__ import annotations

from pipeline.lyra.minimax_shared import _SCHEMA_DROP, _coerce_to_schema


def test_drops_string_items_in_array_of_objects() -> None:
    schema = {
        "type": "array",
        "items": {"type": "object", "properties": {"id": {"type": "string"}}},
    }
    raw = [{"id": "a"}, "stray-string", {"id": "b"}]
    assert _coerce_to_schema(raw, schema) == [{"id": "a"}, {"id": "b"}]


def test_drops_string_items_in_top_level_object_array() -> None:
    # Mirrors CROSS_POLLINATION_SCHEMA shape.
    schema = {
        "type": "object",
        "properties": {
            "cross_pollination": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "angle_id": {"type": "string"},
                        "enriched_queries": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
        },
    }
    raw = {
        "cross_pollination": [
            {"angle_id": "abc", "enriched_queries": ["q1", "q2"]},
            "bare-string-that-should-be-dict",
            {"angle_id": "def", "enriched_queries": ["q3"]},
        ],
    }
    out = _coerce_to_schema(raw, schema)
    assert isinstance(out, dict)
    assert len(out["cross_pollination"]) == 2
    assert all(isinstance(cp, dict) for cp in out["cross_pollination"])


def test_drops_dict_items_in_array_of_strings() -> None:
    schema = {"type": "array", "items": {"type": "string"}}
    raw = ["query1", {"this": "should-not-be-here"}, "query2", 42]
    assert _coerce_to_schema(raw, schema) == ["query1", "query2"]


def test_object_at_root_when_array_expected_becomes_empty_array() -> None:
    schema = {"type": "array", "items": {"type": "object"}}
    raw = {"oops": "not an array"}
    assert _coerce_to_schema(raw, schema) == []


def test_keeps_unknown_object_keys_unchanged() -> None:
    # Schemas in this codebase don't set additionalProperties:false,
    # so unknown fields should pass through unchanged.
    schema = {
        "type": "object",
        "properties": {"known": {"type": "string"}},
    }
    raw = {"known": "value", "extra_metadata": {"foo": 42}}
    out = _coerce_to_schema(raw, schema)
    assert out == {"known": "value", "extra_metadata": {"foo": 42}}


def test_nested_array_of_strings_inside_object_inside_array() -> None:
    # Mirrors specialist findings shape: findings[].source_ids[] strings.
    schema = {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim": {"type": "string"},
                        "source_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
        },
    }
    raw = {
        "findings": [
            {"claim": "ok", "source_ids": ["a", "b"]},
            "non-dict finding",  # ← past bug 1
            {"claim": "also ok", "source_ids": ["c", {"bad": "dict"}, "d"]},  # ← past bug 2
        ],
    }
    out = _coerce_to_schema(raw, schema)
    assert isinstance(out, dict)
    findings = out["findings"]
    assert len(findings) == 2
    assert findings[0] == {"claim": "ok", "source_ids": ["a", "b"]}
    assert findings[1] == {"claim": "also ok", "source_ids": ["c", "d"]}


def test_primitive_type_mismatch_drops_value() -> None:
    schema = {"type": "string"}
    assert _coerce_to_schema(42, schema) is _SCHEMA_DROP
    assert _coerce_to_schema("hello", schema) == "hello"


def test_unknown_schema_types_passthrough() -> None:
    # Schemas may declare types we don't model here (e.g. enum-only). Don't
    # accidentally drop those — pass through.
    schema: dict = {"enum": ["a", "b", "c"]}
    assert _coerce_to_schema("a", schema) == "a"


def test_array_with_no_items_schema_passes_through() -> None:
    schema = {"type": "array"}  # no items declaration
    raw = ["any", {"shape": "is fine"}, 42]
    assert _coerce_to_schema(raw, schema) == ["any", {"shape": "is fine"}, 42]
