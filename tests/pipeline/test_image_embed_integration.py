"""End-to-end test for the multi-strategy embed pipeline.

Builds a synthetic paper with multiple sections and a list of image
candidates, then exercises `insert_image_after_paragraph` directly to
verify that:

1. Mutated paragraphs (audit/repair injected `[N]`) still get an image
   via the normalized strategy.
2. Heavily rewritten paragraphs still get an image via the
   first-sentence strategy or section_fallback.
3. Completely unmatched anchors land via section_fallback (not lost
   silently like Run 9).
4. The chosen-strategy distribution is what we expect.

This is the layer that broke in Run 9: 8 candidates selected, 0
embedded. After the fix, all candidates should land somewhere visible.
"""

import re

from pipeline.lyra.theo_image_captions import insert_image_after_paragraph

PAPER = """# Test Paper

Hook intro paragraph.

## Sky Beings in Ancient Texts

The Anunnaki descended from the heavens to teach humans astronomy and metallurgy.

The Watchers in the Book of Enoch are described as fallen angels who came down.

Ezekiel's vision in the Hebrew Bible presents interpretive challenges that span generations.

## Megalithic Construction

Construction of the Giza pyramids required moving multi-ton blocks with surprising precision.

Puma Punku features andesite blocks cut with sub-millimeter tolerances.

## What We Actually Know

The evidence for ancient sky-visitors is mixed. Some traditions overlap suggestively.
"""


def _img(name: str) -> str:
    return f"![{name}](/data/{name}.jpg)"


def test_run_9_failure_pattern_recovers():
    """Five image candidates with various anchor states; all should land somewhere."""
    paper = PAPER

    # Candidate 1: anchor matches exactly
    paper, s1 = insert_image_after_paragraph(
        paper,
        "Sky Beings in Ancient Texts",
        "The Anunnaki descended from the heavens",
        _img("anunnaki"),
    )

    # Candidate 2: anchor was captured before audit injected [3] mid-text.
    # Simulate by FIRST modifying the paper to inject [3], then matching the
    # original (un-marked) anchor.
    paper = paper.replace(
        "The Watchers in the Book of Enoch are described",
        "The Watchers [3] in the Book of Enoch are described",
        1,
    )
    paper, s2 = insert_image_after_paragraph(
        paper,
        "Sky Beings in Ancient Texts",
        "The Watchers in the Book of Enoch are described",
        _img("watchers"),
    )

    # Candidate 3: opener intact but mid-paragraph rewritten.
    # Simulate: replace the rest of the Ezekiel sentence.
    paper = paper.replace(
        "Ezekiel's vision in the Hebrew Bible presents interpretive challenges that span generations.",
        "Ezekiel's vision in the Hebrew Bible has been studied across centuries by merkabah mystics, Christian theologians, and modern ancient-astronaut commentators alike.",
    )
    paper, s3 = insert_image_after_paragraph(
        paper,
        "Sky Beings in Ancient Texts",
        "Ezekiel's vision in the Hebrew Bible presents interpretive challenges that span generations.",
        _img("ezekiel"),
    )

    # Candidate 4: anchor completely doesn't match (audit fully rewrote para).
    # Should fall back to section_fallback.
    paper, s4 = insert_image_after_paragraph(
        paper,
        "Megalithic Construction",
        "Some completely unrelated anchor about Roman aqueducts in Segovia",
        _img("megalith_fallback"),
    )

    # Candidate 5: exact match in the assessment section
    paper, s5 = insert_image_after_paragraph(
        paper,
        "What We Actually Know",
        "The evidence for ancient sky-visitors is mixed",
        _img("assessment"),
    )

    strategies = [s1, s2, s3, s4, s5]
    print("strategies:", strategies)

    # Every image landed (no `failed`)
    assert "failed" not in strategies, f"Some images failed to embed: {strategies}"

    # All 5 image markdowns are present in the final paper
    embedded = re.findall(r"!\[[^\]]*\]\([^)]+\)", paper)
    assert len(embedded) == 5, f"Expected 5 images embedded, got {len(embedded)}"

    # Strategy distribution: 2 exact (anunnaki, assessment), 1 normalized
    # (watchers — [3] was injected), 1 first_sentence or normalized
    # (ezekiel), 1 section_fallback (megalith)
    assert "exact" in strategies
    assert "normalized" in strategies
    assert "section_fallback" in strategies


def test_section_fallback_fires_only_when_anchor_truly_missing():
    """Verify section_fallback isn't picked up over a real anchor match."""
    body_with_anchor = "The Anunnaki descended.\n\nMore prose.\n"
    paper = f"## Investigation\n\n{body_with_anchor}\n## Other\n\nx\n"
    out, strategy = insert_image_after_paragraph(
        paper, "Investigation", "The Anunnaki descended", _img("a")
    )
    assert strategy == "exact"
    # Should NOT also fire as section_fallback
    embedded = re.findall(r"!\[[^\]]*\]\([^)]+\)", out)
    assert len(embedded) == 1


def test_multiple_fallbacks_in_same_section_all_embed_at_section_end():
    """If multiple unmatched anchors target one section, the caller (probative_images)
    enforces a cap. The matcher itself doesn't cap — it just always embeds."""
    paper = "## Investigation\n\nReal prose here.\n\n## Other\n\nx\n"
    img1 = _img("img1")
    img2 = _img("img2")
    paper, s1 = insert_image_after_paragraph(paper, "Investigation", "no match here", img1)
    paper, s2 = insert_image_after_paragraph(paper, "Investigation", "also no match", img2)
    assert s1 == "section_fallback"
    assert s2 == "section_fallback"
    assert img1 in paper
    assert img2 in paper
