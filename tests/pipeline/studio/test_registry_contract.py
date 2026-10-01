"""The committed renderer registry (stream D's video/src/blocks/registry.json, contract C5),
glyph set (DRAWABLE of video/src/theme/glyphs.ts) and hook caption line budget
(video/src/captions.ts) against this plan's mirrors of them: the local cue table, the fixture
entries, the icons, the code points the brand font files map, HOOK_LINE_MAX_CHARS."""

from __future__ import annotations

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
#: block's lower third, a photo caption, a card statement, the end card's link, the basis line of
#: a UnitGrid, a fifth list item.
_REFUSED_BY_THE_LINT = [
    ("PhotoPlate", "label.title", len("Temple of Jupiter, Baalbek")),
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


def test_the_brand_glyph_set_is_the_renderers():
    source = (config.REPO / "video" / "src" / "theme" / "glyphs.ts").read_text(encoding="utf-8")
    found = re.findall(r"export const DRAWABLE =\s*'([^']*)'", source)
    assert found == [glyphs.DRAWABLE]


def test_the_hook_line_budget_is_the_renderers():
    source = (config.REPO / "video" / "src" / "captions.ts").read_text(encoding="utf-8")
    found = re.findall(r"^export const HOOK_LINE_MAX_CHARS = (\d+)\b", source, re.MULTILINE)
    assert found == [str(script.HOOK_LINE_MAX_CHARS)]
