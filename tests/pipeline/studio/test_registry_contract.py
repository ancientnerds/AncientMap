"""The committed renderer registry (stream D's video/src/blocks/registry.json, contract C5),
glyph set (DRAWABLE of video/src/theme/glyphs.ts) and hook caption line budget
(video/src/captions.ts) against this plan's mirrors of them: the local cue table, the fixture
entries, the icons, the code points the brand font files map, HOOK_LINE_MAX_CHARS."""

from __future__ import annotations

import json
import re

import pytest

from pipeline.studio import blocks, casefile, config, glyphs, script
from tests.pipeline.studio import episode_fixtures as ef
from tests.pipeline.studio import script_fixtures as sf


def test_the_cue_table_covers_exactly_the_registry():
    assert set(script.LOCAL_CUES) == set(blocks.load_registry())


def test_the_fixture_entries_and_icons_are_the_committed_ones():
    registry = blocks.load_registry()
    assert {name: registry[name] for name in sf.REGISTRY} == sf.REGISTRY
    assert blocks.claim_icons(registry) == ef.ICONS


def test_the_fixture_script_passes_against_the_committed_registry():
    data = sf.script()
    report = script.validate_script(
        data,
        casefile.from_dict(ef.casefile()),
        blocks.load_registry(),
        slug="baalbek-c5",
        fmt="full",
        words=sf.words_for(data),
        captures=sf.manifests(),
    )
    assert report.errors == [] and report.deferred == []


@pytest.mark.parametrize("block", ["EvidenceCard", "QuoteCard"])
def test_a_dossier_source_title_the_card_cannot_draw_on_one_line_is_refused_by_episode_check(block):
    """Render-R1: casefile.py puts no limit on source.title, and the card's title line was clipped
    inside the LayoutBox, so the lint called a cut-off 111-character title clean. The registry now
    bounds the title and the locator per card, and the validator `episode check` runs refuses it."""
    title = "The Megalithic Quarry of Baalbek: A Reassessment of Roman Stone-Working Technology and Logistics - ResearchGate"
    assert len(title) == 111

    def props(source_title: str, locator: str) -> dict:
        return {
            "evidence": {
                "id": "e1",
                "claim_id": "c1",
                "kind": "quantity",
                "statement": "The block weighs about 1,000 tonnes.",
                "source": {
                    "url": "https://www.researchgate.net/publication/1",
                    "title": source_title,
                    "tier": 1,
                    "license": "",
                    "quote": "estimated to weigh 1,650 tonnes",
                    "locator": locator,
                },
                "paper_anchor": None,
            }
        }

    schema = blocks.load_registry()[block]["props"]
    errors = blocks.props_errors(schema, props(title, "section 2"))
    assert len(errors) == 1 and re.fullmatch(
        r"props\.evidence\.source\.title: longer than \d+", errors[0]
    )
    errors = blocks.props_errors(
        schema, props("Baalbek: the largest blocks", "p. 112, section 2, the long third footnote")
    )
    assert len(errors) == 1 and re.fullmatch(
        r"props\.evidence\.source\.locator: longer than \d+", errors[0]
    )
    assert blocks.props_errors(schema, props("Baalbek: the largest blocks", "section 2")) == []


#: (block, drawn pattern, characters): strings the render lint refused although `episode check`
#: accepted them (render-R2, measured 2026-10-01 on the RTX 3080): a place label on every clip
#: block's lower third (and a real 24-character site name in it), a photo caption, a card
#: statement, the end card's headline and link, the basis line of a UnitGrid, a fifth list item.
_REFUSED_BY_THE_LINT = [
    ("PhotoPlate", "label.title", len("Temple of Jupiter, Baalbek")),
    ("PhotoPlate", "label.title", len("Sacsayhuaman Walls Cusco")),
    ("ShareCard", "headline", 49),
    ("PlatformClip", "label.subtitle", 50),
    ("PhotoPlate", "caption", 63),
    ("EvidenceCard", "evidence.statement", 146),
    ("ShareCard", "url", 54),
    ("UnitGrid", "basis", 64),
    ("ListCard", "items[].text", 77),
]


def _drawn_leaf(schema: dict, pattern: str) -> dict:
    """The schema a registry `drawn` pattern ('items[].text') leads to."""
    for segment in pattern.split("."):
        schema = schema["properties"][segment.removesuffix("[]")]
        if segment.endswith("[]"):
            schema = schema["items"]
    return schema


@pytest.mark.parametrize(("block", "pattern", "length"), _REFUSED_BY_THE_LINT)
def test_a_string_longer_than_its_box_is_refused_by_episode_check_not_first_by_the_lint(
    block, pattern, length
):
    registry = blocks.load_registry()
    leaf = _drawn_leaf(registry[block]["props"], pattern)
    assert blocks.props_errors(leaf, "x" * length) == [f"props: longer than {leaf['maxLength']}"]


_LOWER_THIRD_NAMES = json.loads(
    (config.REPO / "video" / "test" / "fixtures" / "lower-third-names.json").read_text(
        encoding="utf-8"
    )
)
_LOWER_THIRD_BLOCKS = ["PhotoPlate", "MapboxTopdown", "PlatformClip", "GlobeShot", "MapboxFlyover"]


def test_every_block_with_a_lower_third_is_checked_against_the_real_names():
    registry = blocks.load_registry()
    assert [b for b, entry in registry.items() if "label.title" in entry["drawn"]] == (
        _LOWER_THIRD_BLOCKS
    )


@pytest.mark.parametrize("block", _LOWER_THIRD_BLOCKS)
def test_real_site_names_the_lint_refused_are_refused_by_episode_check_and_the_widest_that_fit_pass(
    block,
):
    """Render-R2 on realistic text (measured 2026-10-01 on the RTX 3080): the lower third's title
    held 24 characters, proved with one lower-case filler, and 7 of 50 real site names of 19-24
    characters (717 to 781 px in the 716 px box) overflowed although `episode check` accepted them.
    Now `overflow` is the real names the lint reported as overflowing, `fit` the widest real
    names of 14-21 characters, which test/gpu/capacity.gpu.ts lints clean: the limit lies between."""
    leaf = _drawn_leaf(blocks.load_registry()[block]["props"], "label.title")
    assert leaf["maxLength"] == 21
    for name in _LOWER_THIRD_NAMES["fit"]:
        assert blocks.props_errors(leaf, name) == [], name
    for name in _LOWER_THIRD_NAMES["overflow"]:
        assert blocks.props_errors(leaf, name) == ["props: longer than 21"], name
    assert max(len(n) for n in _LOWER_THIRD_NAMES["fit"]) == leaf["maxLength"]
    assert min(len(n) for n in _LOWER_THIRD_NAMES["overflow"]) == leaf["maxLength"] + 1


#: Real prose inside the full stage's registry limits (statement 100, quote 220), 99 and 204
#: characters: the reviewer's measurement of 2026-10-01, a hook EvidenceCard the render lint
#: refused (render-R2 on the hook stage) although `episode check` accepted it.
_STATEMENT_99 = "The Stone of the Pregnant Woman, the largest block cut at Baalbek, weighs about 1000 tonnes in all."
_QUOTE_204 = (
    "The excavators of the German Archaeological Institute measured the Stone of the Pregnant Woman "
    "in the Roman quarry at Baalbek and estimated that the block weighs about 1,000 tonnes. "
    "It is the biggest one."
)


def _script_opening_with(block: str, props: dict, *, hook: bool) -> dict:
    """The fixture script whose first two beats are `block` (b01) and the ClaimBoard, both hook or
    both not (a slice may have no hook)."""

    def mutate(data: dict) -> None:
        data["beats"][0] = sf.beat(
            "b01", "The excavators measured it in the quarry.", block, props, hook=hook
        )
        data["beats"][1]["hook"] = hook

    return sf.mutated_script(mutate)


def _validate_with_long_evidence(data: dict, *, fmt: str) -> list[str]:
    case = ef.casefile()
    case["evidence"][0]["statement"] = _STATEMENT_99
    case["evidence"][0]["source"]["quote"] = _QUOTE_204
    return script.validate_script(
        data,
        casefile.from_dict(case),
        blocks.load_registry(),
        slug="baalbek-c5",
        fmt=fmt,
    ).errors


@pytest.mark.parametrize(
    "props",
    [{"evidence": {"$ref": "e1"}}, {"evidence": {"$ref": "e1"}, "image": {"$ref": "m1"}}],
    ids=["no image", "with image"],
)
def test_a_hook_evidence_card_the_hook_stage_cannot_hold_is_refused_by_episode_check(props):
    """Render-R2 on the hook stage: under the hook captions the stage is 140 px shorter, an
    EvidenceCard holds a statement of 68 characters and a quote of 120 beside an image (88 and 165
    beside none), and the registry's full-stage limits (100, 220) let `episode check` accept 99
    and 204 characters of real prose that only `episode render` then refused, after the voice."""
    assert (len(_STATEMENT_99), len(_QUOTE_204)) == (99, 204)
    hook = _validate_with_long_evidence(
        _script_opening_with("EvidenceCard", props, hook=True), fmt="full"
    )
    assert hook == [
        "b01: props.evidence.statement: longer than 68 on a hook beat",
        "b01: props.evidence.source.quote: longer than 120 on a hook beat",
    ]
    # the same beat after the hook has the whole stage
    after = _script_opening_with("EvidenceCard", props, hook=False)
    assert _validate_with_long_evidence(after, fmt="slice") == []


def _claims(n: int) -> dict:
    claim = {"id": "c", "label": "A claim", "by": "", "icon": "weight", "status": "pending"}
    return {"title": "Claims", "claims": [{**claim, "id": f"c{i}"} for i in range(n)]}


def _list(n: int) -> dict:
    return {"title": "List", "items": [{"id": f"i{i}", "text": "An item"} for i in range(n)]}


def _bars(n: int) -> dict:
    bars = [{"id": f"b{i}", "label": "Bar", "value": 10 + i} for i in range(n)]
    return {"title": "Bars", "unit": "t", "basis": "a basis line", "bars": bars}


def _groups(n: int) -> dict:
    groups = [{"id": f"g{i}", "count": 3, "label": "Group", "tone": "accent"} for i in range(n)]
    return {"title": "Grid", "basis": "a basis line", "unitLabel": "a bus", "groups": groups}


def _meter(note: bool) -> dict:
    props = {"hypotheses": ["Roman engineers", "A lost civilization"], "start": [50, 50]}
    return {**props, "note": "A note"} if note else props


def _quote_card(length: int) -> dict:
    evidence = ef.casefile()["evidence"][0]
    evidence["source"]["quote"] = "x" * length
    evidence = {k: v for k, v in evidence.items() if k != "verification"}
    evidence["source"] = {k: v for k, v in evidence["source"].items() if k != "source_id"}
    return {"evidence": evidence}


#: (block, props that fit, props over the hook limit, the error): the layouts the hook stage
#: cannot host whatever the text. The full stage holds every one of them (the schema limit).
_HOOK_HOLDS_LESS = [
    ("ClaimBoard", _claims(5), _claims(6), "props.claims: more than 5 items on a hook beat"),
    ("ListCard", _list(4), _list(5), "props.items: more than 4 items on a hook beat"),
    ("BarChart", _bars(6), _bars(7), "props.bars: more than 6 items on a hook beat"),
    ("UnitGrid", _groups(2), _groups(3), "props.groups: more than 2 items on a hook beat"),
    ("Meter", _meter(note=False), _meter(note=True), "props.note: not allowed on a hook beat"),
    (
        "QuoteCard",
        _quote_card(230),
        _quote_card(231),
        "props.evidence.source.quote: longer than 230 on a hook beat",
    ),
]


@pytest.mark.parametrize(
    ("block", "fits", "over", "error"), _HOOK_HOLDS_LESS, ids=[c[0] for c in _HOOK_HOLDS_LESS]
)
def test_a_layout_the_hook_stage_cannot_host_is_refused_only_on_a_hook_beat(
    block, fits, over, error
):
    schema = blocks.load_registry()[block]["props"]
    assert blocks.props_errors(schema, fits, hook=True) == []
    assert blocks.props_errors(schema, over) == [], "the full stage holds it"
    assert blocks.props_errors(schema, over, hook=True) == [error]


def test_the_brand_glyph_set_is_the_renderers():
    source = (config.REPO / "video" / "src" / "theme" / "glyphs.ts").read_text(encoding="utf-8")
    found = re.findall(r"export const DRAWABLE =\s*'([^']*)'", source)
    assert found == [glyphs.DRAWABLE]


def test_the_hook_line_budget_is_the_renderers():
    source = (config.REPO / "video" / "src" / "captions.ts").read_text(encoding="utf-8")
    found = re.findall(r"^export const HOOK_LINE_MAX_CHARS = (\d+)\b", source, re.MULTILINE)
    assert found == [str(script.HOOK_LINE_MAX_CHARS)]
