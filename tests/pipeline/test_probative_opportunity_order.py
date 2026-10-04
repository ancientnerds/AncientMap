"""The image budget must reach every section before it deepens one.

Measured on the 31 live papers on 2026-10-04: 109 of 189 sections carried no
image, the three fixed tail sections were empty 76 times out of 93, 54 % of a
paper's images sat in its single most illustrated section and 11 of the 31
longest sections had none. The cause was the dispatch order, not the budget:
`order_opportunities_by_section` is the fix, and these tests pin it.
"""

from __future__ import annotations

from pipeline.lyra.handlers.probative_images import order_opportunities_by_section
from pipeline.lyra.theo_image_captions import images_per_section


def _opp(section: str, index: int) -> dict:
    return {
        "section": section,
        "paragraph_index": index,
        "search_query": f"query {index}",
        "search_queries": [f"query {index}"],
    }


def test_empty_input_stays_empty():
    assert order_opportunities_by_section([]) == []


def test_round_robin_hands_every_section_its_first_opportunity():
    opportunities = [
        _opp("a", 0),
        _opp("a", 1),
        _opp("a", 2),
        _opp("b", 3),
        _opp("b", 4),
        _opp("c", 5),
    ]
    ordered = order_opportunities_by_section(opportunities)
    assert [o["section"] for o in ordered] == ["a", "b", "c", "a", "b", "a"]


def test_a_budget_of_one_per_section_covers_every_section():
    """The owner's hard floor: with a budget of one image per section, the first
    pass of the budget reaches every section of the paper."""
    opportunities = [
        _opp("a", 0),
        _opp("a", 1),
        _opp("a", 2),
        _opp("a", 3),
        _opp("b", 4),
        _opp("b", 5),
        _opp("c", 6),
    ]
    ordered = order_opportunities_by_section(opportunities)
    budget = 3  # three sections
    covered = {o["section"] for o in ordered[:budget]}
    assert covered == {"a", "b", "c"}


def test_the_floor_comes_before_the_top_up():
    """A section with many opportunities must not crowd out a section with one:
    the reading order gave the first section all three of its images first."""
    opportunities = [
        _opp("long", 0),
        _opp("long", 1),
        _opp("long", 2),
        _opp("short", 3),
    ]
    ordered = order_opportunities_by_section(opportunities)
    # two sections, budget two: one image each, before "long" gets a second
    assert [o["paragraph_index"] for o in ordered[:2]] == [0, 3]


def test_paragraph_order_is_kept_inside_a_section():
    opportunities = [_opp("a", 5), _opp("b", 9), _opp("a", 1), _opp("b", 2), _opp("a", 3)]
    ordered = order_opportunities_by_section(opportunities)
    for section in ("a", "b"):
        indexes = [o["paragraph_index"] for o in ordered if o["section"] == section]
        assert indexes == sorted(indexes)


def test_sections_keep_the_order_of_their_first_appearance():
    opportunities = [_opp("second", 0), _opp("first", 1), _opp("second", 2), _opp("first", 3)]
    ordered = order_opportunities_by_section(opportunities)
    assert [o["section"] for o in ordered] == ["second", "first", "second", "first"]


def test_a_single_section_is_unchanged():
    opportunities = [_opp("only", 0), _opp("only", 1), _opp("only", 2)]
    assert order_opportunities_by_section(opportunities) == opportunities


def test_an_opportunity_without_a_section_keeps_its_own_group():
    """The VLM may omit the section; the opportunity must not be dropped."""
    nameless = {"paragraph_index": 7, "search_query": "q7"}
    opportunities = [_opp("a", 0), nameless, _opp("a", 1)]
    ordered = order_opportunities_by_section(opportunities)
    assert len(ordered) == 3
    assert nameless in ordered


_PAPER = """# Title

Lead paragraph.

![one](/data/research-images/x/p0_one.jpg)
*Illustration: one. Photo: A / Wikimedia Commons.*
[Source](https://example.org/one)

## The Quarry

A paragraph about the quarry.

![two](/data/research-images/x/p1_two.jpg)
*Illustration: two. Photo: B / Wikimedia Commons.*
[Source](https://example.org/two)

![three](/data/research-images/x/p2_three.jpg)
*Illustration: three. Photo: C / Wikimedia Commons.*
[Source](https://example.org/three)

## The Other Side

A paragraph about the counter case.

## What We Actually Know

A paragraph about what is known.

## References

[1] Someone. A title. Venue. DOI: 10.1/x. [Academic]
"""


def test_images_per_section_counts_the_empty_sections_too():
    """An empty section is the finding, not a missing key: the campaign has to
    be able to name the sections that never got an image."""
    assert images_per_section(_PAPER) == {
        "": 1,
        "The Quarry": 2,
        "The Other Side": 0,
        "What We Actually Know": 0,
    }


def test_images_per_section_leaves_out_the_references_section():
    counts = images_per_section(_PAPER + "\n![ref](/data/research-images/x/p9_ref.jpg)\n")
    assert "References" not in counts
    assert sum(counts.values()) == 3


def test_images_per_section_of_a_paper_without_images_is_all_zeros():
    report = "# Title\n\nLead.\n\n## One\n\nText.\n\n## Two\n\nText.\n"
    assert images_per_section(report) == {"One": 0, "Two": 0}

