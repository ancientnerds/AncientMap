from __future__ import annotations

import json

import pytest

from pipeline.studio import blocks
from pipeline.studio.config import REPO

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


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_are_not_numbers(value):
    """json.loads reads NaN and Infinity, but the timeline's JSON.parse in the renderer does
    not, and NaN is neither below a minimum nor above a maximum."""
    schema = {"type": "number", "minimum": 0, "maximum": 1}
    assert blocks.props_errors(schema, value) == ["props: expected number"]


#: A card under hook captions holds less than on the full stage (the stage is 140 px shorter).
HOOK_CARD = {
    "type": "object",
    "properties": {
        "statement": {"type": "string", "minLength": 1, "maxLength": 100, "hookMaxLength": 68},
        "note": {"type": "string", "minLength": 1, "maxLength": 110, "hookMaxLength": 0},
        "rows": {"type": "array", "items": {"type": "string"}, "maxItems": 6, "hookMaxItems": 5},
    },
}


def test_hook_limits_bind_a_hook_beat_only():
    value = {"statement": "x" * 80, "note": "a note", "rows": ["r"] * 6}
    assert blocks.props_errors(HOOK_CARD, value) == []
    assert blocks.props_errors(HOOK_CARD, value, hook=True) == [
        "props.statement: longer than 68 on a hook beat",
        "props.note: not allowed on a hook beat",
        "props.rows: more than 5 items on a hook beat",
    ]
    fits = {"statement": "x" * 68, "rows": ["r"] * 5}
    assert blocks.props_errors(HOOK_CARD, fits, hook=True) == []


def test_a_hook_limit_inside_an_array_item_and_the_stage_limit_first():
    schema = {"type": "array", "items": HOOK_CARD}
    problems = blocks.props_errors(
        schema, [{"statement": "x" * 69}, {"statement": "x" * 101}], hook=True
    )
    assert problems == [
        "props[0].statement: longer than 68 on a hook beat",
        "props[1].statement: longer than 100",
    ]


def test_hook_limits_must_be_well_formed_to_load():
    def problems(**leaf):
        node = {"type": "object", "properties": {"a": leaf}}
        return blocks.validate_registry({"blocks": {"Card": _entry(node)}})

    assert problems(type="string", maxLength=10, hookMaxLength=10) == []
    assert problems(type="array", maxItems=6, hookMaxItems=0) == []
    assert problems(type="string", maxLength=10, hookMaxLength=11) == [
        "Card.props.properties.a: hookMaxLength 11 must not exceed maxLength"
    ]
    assert problems(type="string", hookMaxLength=5) == [
        "Card.props.properties.a: hookMaxLength 5 must not exceed maxLength"
    ]
    assert problems(type="string", maxLength=10, hookMaxLength=-1) == [
        "Card.props.properties.a: hookMaxLength must be an integer of at least 0"
    ]
    assert problems(type="string", maxLength=10, hookMaxLength=True) == [
        "Card.props.properties.a: hookMaxLength must be an integer of at least 0"
    ]
    assert problems(type="array", maxItems=6, hookMaxLength=3) == [
        "Card.props.properties.a: hookMaxLength belongs to a schema of type 'string'"
    ]
    assert problems(type="string", maxLength=6, hookMaxItems=3) == [
        "Card.props.properties.a: hookMaxItems belongs to a schema of type 'array'"
    ]


# ---- text composed of several fields (video/src/blocks/composed.ts, test/gpu/capacity.gpu.ts)

COMPOSED_FIXTURE = REPO / "video" / "test" / "fixtures" / "composed-limits.json"


def _bars(unit, *values):
    return {
        "title": "Weights",
        "unit": unit,
        "basis": "two sources",
        "bars": [{"id": f"b{i}", "label": f"Bar {i}", "value": v} for i, v in enumerate(values)],
    }


def _evidence(host, locator, *, tier=1, anchor="ev-01"):
    return {
        "id": "ev-01",
        "claim_id": "c1",
        "kind": "fact",
        "statement": "A statement.",
        "source": {
            "url": f"https://{host}/paper",
            "title": "A paper",
            "tier": tier,
            "license": "",
            "quote": "A quote.",
            "locator": locator,
        },
        "paper_anchor": anchor,
    }


IMAGE = {"src": "media/x.jpg", "width": 960, "height": 540, "alt": "x", "markers": []}


def _errors(block, props):
    return blocks.composed_errors(block, props)


def test_the_composed_limits_are_the_renderers():
    """The numbers pinned in the renderer's fixture (video/test/composed.test.ts pins the other side)."""
    pinned = json.loads(COMPOSED_FIXTURE.read_text(encoding="utf-8"))
    assert blocks.COMPOSED == pinned


def test_a_bar_value_text_the_value_box_cannot_hold_is_refused():
    """'tonnes' with [1000, 1650] is '1,000–1,650 tonnes', 18 characters in a box of 16: the lint
    refused what episode check accepted (render-R2)."""
    assert _errors("BarChart", _bars("tonnes", [1000, 1650])) == [
        'bar b0: "1,000–1,650 tonnes" is 18 characters; the value box holds 16 for a range'
    ]
    assert _errors("BarChart", _bars("tonnes", 1250000)) == [
        'bar b0: "1,250,000 tonnes" is 16 characters; the value box holds 14 for a single value'
    ]
    assert _errors("BarChart", _bars("metres", [119.65, 120.55])) == [
        'bar b0: "119.65–120.55 metres" is 20 characters; the value box holds 16 for a range'
    ]


@pytest.mark.parametrize(
    ("unit", "values"),
    [
        ("t", [[1000, 1650]]),
        ("tons", [[1000, 1650]]),
        ("tonnes", [[100, 165], 1250, 125000.0]),
        ("metres", [[19.6, 20.5], 1.75]),
    ],
)
def test_a_bar_value_text_that_fits_is_accepted(unit, values):
    assert _errors("BarChart", _bars(unit, *values)) == []


def test_a_float_that_is_whole_prints_without_decimals_as_the_renderer_does():
    # JSON 1000.0 and 1000 are the same number to the renderer: "1,000 tonnes", 12 characters
    assert _errors("BarChart", _bars("tonnes", 1000.0, [100.0, 165.0])) == []


def test_an_evidence_source_line_is_bounded_in_total():
    line = "onlinelibrary.wiley.com  //  tier 1  //  Results, paragraph 2  //  paper #ev-01"
    assert len(line) == 79
    props = {
        "evidence": _evidence("onlinelibrary.wiley.com", "Results, paragraph 2"),
        "image": IMAGE,
    }
    assert _errors("EvidenceCard", props) == [
        f'evidence ev-01: the source line "{line}" is 79 characters; the card holds 72 beside an image'
    ]
    assert _errors("EvidenceCard", {"evidence": props["evidence"]}) == []
    assert _errors("EvidenceCard", {**props, "evidence": _evidence("jstor.org", "x" * 24)}) == []
    # www. is not drawn; an unbounded paper anchor counts
    assert (
        _errors("EvidenceCard", {**props, "evidence": _evidence("www.jstor.org", "x" * 24)}) == []
    )
    long_anchor = {**props, "evidence": _evidence("jstor.org", "", anchor="ev-" + "z" * 60)}
    assert len(_errors("EvidenceCard", long_anchor)) == 1


def test_a_quote_card_meta_line_is_bounded_in_total_and_its_work_line_by_its_fields():
    props = {"evidence": _evidence("a" * 60 + ".org", "x" * 24)}
    assert [e.split(" is ")[0] for e in _errors("QuoteCard", props)] == [
        f'evidence ev-01: the meta line "{"x" * 24}  //  {"a" * 60}.org  //  tier 1"'
    ]
    assert _errors("QuoteCard", {"evidence": _evidence("onlinelibrary.wiley.com", "x" * 24)}) == []
    props = blocks.load_registry()["QuoteCard"]["props"]["properties"]
    work = (
        props["attribution"]["maxLength"]
        + 2
        + props["evidence"]["properties"]["source"]["properties"]["title"]["maxLength"]
    )
    assert work == blocks.COMPOSED["QuoteCard.workLine"]


def test_other_blocks_have_no_composed_limit():
    assert _errors("PhotoPlate", {"image": {}}) == []
