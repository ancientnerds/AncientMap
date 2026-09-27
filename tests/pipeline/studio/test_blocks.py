from __future__ import annotations

import json

import pytest

from pipeline.studio import blocks

PHOTO = {
    "type": "object",
    "required": ["image"],
    "additionalProperties": False,
    "properties": {
        "image": {
            "type": "object",
            "required": ["src", "markers"],
            "properties": {
                "src": {"type": "string", "minLength": 1},
                "markers": {"type": "array", "items": {"type": "object"}},
            },
        },
        "kenBurns": {"type": "string", "enum": ["in", "out", "none"]},
        "zoom": {"type": "number", "minimum": 1, "maximum": 3},
    },
}
CARD = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "n": {"type": "integer"},
        "lines": {"type": "array", "items": {"type": "string"}},
        "items": {
            "type": "array",
            "items": {"type": "object", "properties": {"text": {"type": "string"}}},
        },
    },
}


def _entry(props, drawn=(), **flags):
    return {"props": props, "map": False, "platform": False, "drawn": list(drawn), **flags}


def test_valid_registry_loads(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"blocks": {"PhotoPlate": _entry(PHOTO)}}), encoding="utf-8")
    assert set(blocks.load_registry(path)) == {"PhotoPlate"}


def test_registry_contract_problems():
    data = {
        "blocks": {
            "TitleCard": _entry({"type": "object"}),
            "Meter": _entry({"type": "object", "oneOf": []}),
            "Ticker": _entry({"type": "object"}, map="no"),
            "Stamp": _entry({"type": "string"}),
            "Old": {"props": {"type": "object"}, "map": False, "platform": False},
            "Blank": _entry({"type": "object"}, drawn=[""]),
        }
    }
    problems = blocks.validate_registry(data)
    assert "TitleCard: title-card and on-screen agent blocks are not allowed" in problems
    assert "Meter.props: unsupported keyword 'oneOf'" in problems
    assert "Ticker: map and platform must be booleans" in problems
    assert "Stamp: props must be a schema of type 'object'" in problems
    assert "Old: entry must be exactly {props, map, platform, drawn}" in problems
    assert "Blank: drawn must be a list of prop paths (non-empty strings)" in problems


def test_drawn_paths_lead_to_strings_of_the_props_schema():
    assert blocks.drawn_path_problem(CARD, "title") is None
    assert blocks.drawn_path_problem(CARD, "lines[]") is None
    assert blocks.drawn_path_problem(CARD, "items[].text") is None
    assert blocks.drawn_path_problem(CARD, "n") == "'n' does not lead to a string"
    assert blocks.drawn_path_problem(CARD, "nope") == "'nope': no property 'nope'"
    assert blocks.drawn_path_problem(CARD, "title[]") == "'title[]': title is not an array"
    problems = blocks.validate_registry({"blocks": {"Card": _entry(CARD, drawn=["title", "n"])}})
    assert problems == ["Card.drawn: 'n' does not lead to a string"]


def test_missing_registry_is_an_error(tmp_path):
    with pytest.raises(blocks.RegistryError, match="block registry is missing"):
        blocks.load_registry(tmp_path / "nope.json")


def test_props_errors_walk_the_whole_value():
    good = {"image": {"src": "media/a.jpg", "markers": []}, "kenBurns": "in", "zoom": 1.2}
    assert blocks.props_errors(PHOTO, good) == []
    bad = {"image": {"src": "", "markers": [1]}, "kenBurns": "spin", "zoom": 5, "extra": True}
    assert blocks.props_errors(PHOTO, bad) == [
        "props.image.src: shorter than 1",
        "props.image.markers[0]: expected object",
        "props.kenBurns: 'spin' is not one of ['in', 'out', 'none']",
        "props.zoom: above 3",
        "props.extra: not allowed",
    ]
    assert blocks.props_errors(PHOTO, {}) == ["props.image: missing"]


def test_booleans_are_not_numbers():
    assert blocks.props_errors({"type": "integer"}, True) == ["props: expected integer"]
    assert blocks.props_errors({"type": ["string", "null"]}, None) == []
