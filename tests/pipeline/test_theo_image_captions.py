"""Tests for deterministic caption builder + markdown section inserter."""

from __future__ import annotations

from pipeline.lyra.image_fetcher import ImageCandidate
from pipeline.lyra.theo_image_captions import (
    build_caption,
    find_section_for_claim,
    insert_image_after_section,
)


def _cand(**kw):
    base = dict(
        url="https://u/a.jpg",
        source="wikimedia",
        title="Nebra Sky Disc",
        description="",
        artist="Frank Vincentz",
        license="Public Domain",
        license_url="https://creativecommons.org/publicdomain/",
        thumbnail_url="",
        metadata={},
    )
    base.update(kw)
    return ImageCandidate(**base)


def test_caption_includes_title_source_license_and_rationale():
    c = _cand()
    cap = build_caption(c, rationale="The disc is the direct evidence for the claim.")
    assert "Nebra Sky Disc" in cap
    assert "Frank Vincentz" in cap
    assert "Public Domain" in cap
    assert "Wikimedia" in cap
    assert "direct evidence" in cap


def test_caption_never_fabricates_missing_metadata():
    c = _cand(artist="")
    cap = build_caption(c, rationale="x")
    # Missing artist omitted, not guessed
    assert "Unknown" not in cap
    assert "by {" not in cap


def test_insert_image_after_section_places_before_next_heading():
    paper = (
        "# Title\n\n"
        "## Intro\n\nIntro text.\n\n"
        "## Findings\n\nThe Nebra Sky Disc dates to 1600 BCE [1].\n\n"
        "## Conclusion\n\nWrap up."
    )
    out = insert_image_after_section(
        paper,
        section_heading="Findings",
        image_markdown="![Nebra Sky Disc](/x.jpg)\n\n*caption*",
    )
    assert "![Nebra Sky Disc]" in out
    # Image must land inside Findings, before Conclusion
    findings_start = out.index("## Findings")
    conclusion_start = out.index("## Conclusion")
    img_pos = out.index("![Nebra Sky Disc]")
    assert findings_start < img_pos < conclusion_start


def test_insert_image_no_op_when_section_missing():
    paper = "# Title\n\n## Intro\n\nOnly section."
    out = insert_image_after_section(paper, "Findings", "![x](/x.jpg)")
    assert out == paper


def test_find_section_for_claim_matches_by_distinctive_phrase():
    paper = (
        "# Title\n\n"
        "## Sky Beings\n\nThe Pyramid Texts at Saqqara describe divine beings [1].\n\n"
        "## Stonework\n\nPuma Punku's H-blocks show precision [2]."
    )
    claim = "The Pyramid Texts at Saqqara describe divine beings"
    assert find_section_for_claim(paper, claim) == "Sky Beings"


def test_find_section_for_claim_returns_none_when_not_found():
    paper = "# T\n\n## Only\n\nPlaceholder."
    assert find_section_for_claim(paper, "unrelated claim text") is None
