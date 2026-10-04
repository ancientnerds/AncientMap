from __future__ import annotations

import pytest

from pipeline.lyra.theo_publishing import report_paragraphs
from pipeline.studio.paper import anchors

REPORT = """# Title

## The Stone in the Quarry

The Stone of the Pregnant Woman weighs about 1000 tons [1]. It lies in the quarry [1].

![Stone](/data/research-images/x/s1_stone.jpg)

*Stone. Photo: Jane Doe / Wikimedia Commons.*
[Source](https://commons.wikimedia.org/wiki/File:Stone.jpg)

## How Heavy Is Heavy

The podium blocks weigh about 800 tons [2]. The quarry blocks are heavier still [1] [2].

### A sub heading

The podium blocks weigh about 800 tons on some counts [2].

## References

[1] Report — https://example.org/a (accessed 2026-09-20) [Academic]
[2] Wiki — https://example.org/b (accessed 2026-09-20) [Reputable]
"""


def test_paragraphs_skip_headings_images_captions_and_references():
    paras = anchors.paragraphs(REPORT)
    assert [(p.index, p.section) for p in paras] == [
        (0, "The Stone in the Quarry"),
        (1, "How Heavy Is Heavy"),
        (2, "How Heavy Is Heavy"),
    ]
    assert paras[0].text.startswith("The Stone of the Pregnant Woman")


def test_paragraphs_are_the_publish_gates_paragraphs():
    assert [p.text for p in anchors.paragraphs(REPORT)] == report_paragraphs(REPORT)


def test_an_anchor_names_the_paragraph_it_opens():
    paras = anchors.paragraphs(REPORT)
    assert anchors.matching_paragraphs(paras, "The Stone of the Pregnant Woman weighs") == [0]
    assert anchors.matching_paragraphs(paras, "weighs about 1000 tons [1]. It lies in") == []
    assert anchors.matching_paragraphs(paras, "The podium blocks weigh about 800 tons") == [1, 2]


def test_normalize_is_the_shared_key():
    assert anchors.normalize("The  **Stone**\nof the") == anchors.normalize("the stone of the")


def test_anchor_problems():
    assert anchors.anchor_problem("The Stone of the Pregnant Woman weighs about") is None
    # the shared normaliser drops [N] and [S:<id>], so a marker is no problem of its own
    assert anchors.anchor_problem("It lies [S:aaaaaaaaaaa1] in the quarry, they say") is None
    assert anchors.anchor_problem("too short") == "anchor_text is shorter than 20 characters"
    assert anchors.anchor_problem("short [1] [2] [3] [4] [5]") == (
        "anchor_text is shorter than 20 characters"
    )


def test_anchor_copied_from_the_draft_resolves_in_the_numbered_paper():
    evidence = [
        {"id": "ev-01", "anchor_text": "The Stone of the Pregnant Woman weighs about 1000 tons"}
    ]
    assert anchors.resolve_evidence_anchors(REPORT, evidence) == {"ev-01": 0}


def test_ambiguous_missing_short_and_mid_paragraph_anchors_are_all_reported():
    evidence = [
        {"id": "ev-01", "anchor_text": "The podium blocks weigh about 800 tons"},
        {"id": "ev-02", "anchor_text": "This sentence appears nowhere in the paper"},
        {"id": "ev-03", "anchor_text": "too short"},
        {"id": "ev-04", "anchor_text": "weighs about 1000 tons [1]. It lies in the quarry"},
    ]
    with pytest.raises(anchors.AnchorError) as exc:
        anchors.resolve_evidence_anchors(REPORT, evidence)
    msg = str(exc.value)
    assert "ev-01: anchor_text matches 2 paragraphs" in msg
    assert "ev-02: anchor_text matches 0 paragraphs" in msg
    assert "ev-03: anchor_text shorter than 20 characters" in msg
    assert "ev-04: anchor_text matches 0 paragraphs" in msg  # opens no paragraph
