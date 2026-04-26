"""Tests for the multi-strategy `insert_image_after_paragraph` matcher.

Run 9 leaked 8 images: candidates were selected and downloaded, but the
exact-substring anchor match failed because the audit/repair gates
mutated the prose between selection and embed time. The matcher now has
a strategy ladder with a guaranteed section-end fallback.
"""

import re

from pipeline.lyra.theo_image_captions import (
    _normalize_for_match,
    insert_image_after_paragraph,
)

IMG_MD = "![Test image](/data/test/img.jpg)"


def _paper(section_body: str, heading: str = "Investigation") -> str:
    return (
        f"# Title\n\nHook prose.\n\n## {heading}\n\n{section_body}\n\n"
        "## Other Section\n\nOther prose [1].\n"
    )


# ---------------------------------------------------------------------------
# _normalize_for_match
# ---------------------------------------------------------------------------


def test_normalize_strips_citation_markers():
    assert _normalize_for_match("The Anunnaki [3] descended.") == "the anunnaki descended"


def test_normalize_strips_emphasis():
    assert _normalize_for_match("*The* **Anunnaki** descended.") == "the anunnaki descended"


def test_normalize_collapses_punctuation():
    assert _normalize_for_match("Watchers, Enoch -- and Heaven!") == "watchers enoch and heaven"


def test_normalize_empty():
    assert _normalize_for_match("") == ""


# ---------------------------------------------------------------------------
# Strategy 1 — exact match
# ---------------------------------------------------------------------------


def test_strategy_exact_match():
    body = "The Anunnaki descended from the heavens to teach humans.\n\nMore prose."
    paper = _paper(body)
    out, strategy = insert_image_after_paragraph(
        paper, "Investigation", "The Anunnaki descended from the heavens", IMG_MD
    )
    assert strategy == "exact"
    assert IMG_MD in out
    # Image lands inside the Investigation section, before the next ## heading
    inv_idx = out.find("## Investigation")
    other_idx = out.find("## Other Section")
    assert inv_idx < out.find(IMG_MD) < other_idx


# ---------------------------------------------------------------------------
# Strategy 2 — normalized match
# ---------------------------------------------------------------------------


def test_strategy_normalized_match_when_citation_injected():
    """Smart-injection added [3] mid-paragraph after the opportunity was picked.

    Exact match fails because the original anchor "Anunnaki descended" doesn't
    contain "[3]". Normalized match strips [3] and re-locates the anchor.
    """
    body = "The Anunnaki [3] descended from the heavens to teach humans.\n\nMore prose."
    paper = _paper(body)
    out, strategy = insert_image_after_paragraph(
        paper, "Investigation", "The Anunnaki descended from the heavens", IMG_MD
    )
    assert strategy == "normalized"
    assert IMG_MD in out


def test_strategy_normalized_handles_emphasis_added():
    body = "The *Anunnaki* descended from the heavens to teach humans.\n\nMore prose."
    paper = _paper(body)
    out, strategy = insert_image_after_paragraph(
        paper, "Investigation", "The Anunnaki descended from the heavens", IMG_MD
    )
    assert strategy == "normalized"
    assert IMG_MD in out


# ---------------------------------------------------------------------------
# Strategy 3 — first-sentence match
# ---------------------------------------------------------------------------


def test_strategy_first_sentence_match():
    """Mid-paragraph rewrite changed the second half but the opener is intact."""
    body = (
        "The Anunnaki descended from the heavens. Modern scholarship now reads this "
        "differently than nineteenth-century commentators did.\n\nMore prose."
    )
    paper = _paper(body)
    # Original anchor recorded longer text that no longer matches verbatim
    out, strategy = insert_image_after_paragraph(
        paper,
        "Investigation",
        "The Anunnaki descended from the heavens. Eighteenth-century scholars saw this as",
        IMG_MD,
    )
    assert strategy in ("first_sentence", "normalized")  # either may match the opener
    assert IMG_MD in out


# ---------------------------------------------------------------------------
# Strategy 4 — section-end fallback
# ---------------------------------------------------------------------------


def test_strategy_section_fallback_when_anchor_unmatched():
    """Anchor is completely different from any prose; falls back to section end."""
    body = "Completely different prose about Roman aqueducts in Segovia.\n\nMore prose."
    paper = _paper(body)
    out, strategy = insert_image_after_paragraph(
        paper, "Investigation", "The Anunnaki descended from the heavens", IMG_MD
    )
    assert strategy == "section_fallback"
    assert IMG_MD in out
    # Image lands inside the Investigation section, before the next ## heading
    inv_idx = out.find("## Investigation")
    other_idx = out.find("## Other Section")
    assert inv_idx < out.find(IMG_MD) < other_idx


def test_strategy_failed_when_section_missing():
    paper = _paper("Some prose here.")
    out, strategy = insert_image_after_paragraph(
        paper, "Nonexistent Section", "Some anchor", IMG_MD
    )
    assert strategy == "failed"
    assert out == paper  # unchanged


# ---------------------------------------------------------------------------
# Strategy ladder ordering — exact wins over normalized
# ---------------------------------------------------------------------------


def test_strategy_exact_preferred_over_normalized():
    """When both strategies could match, exact wins (it's the first in the ladder)."""
    body = "The Anunnaki descended. The Anunnaki *descended*.\n\nMore prose."
    paper = _paper(body)
    out, strategy = insert_image_after_paragraph(
        paper, "Investigation", "The Anunnaki descended", IMG_MD
    )
    assert strategy == "exact"
    # Image inserted after the FIRST paragraph (the exact match), not the
    # normalized one
    assert IMG_MD in out


# ---------------------------------------------------------------------------
# Multi-paragraph section
# ---------------------------------------------------------------------------


def test_multi_paragraph_inserts_at_correct_paragraph_end():
    body = (
        "First paragraph about the Anunnaki and their descent.\n\n"
        "Second paragraph about the Watchers in the Book of Enoch.\n\n"
        "Third paragraph about the Nephilim tradition."
    )
    paper = _paper(body)
    out, strategy = insert_image_after_paragraph(
        paper, "Investigation", "Second paragraph about the Watchers", IMG_MD
    )
    assert strategy == "exact"
    # Image should land between "Watchers" paragraph and "Third paragraph"
    img_idx = out.find(IMG_MD)
    second_idx = out.find("Second paragraph")
    third_idx = out.find("Third paragraph")
    assert second_idx < img_idx < third_idx


# ---------------------------------------------------------------------------
# Empty / edge cases
# ---------------------------------------------------------------------------


def test_empty_anchor_returns_failed():
    paper = _paper("Some prose.")
    out, strategy = insert_image_after_paragraph(paper, "Investigation", "", IMG_MD)
    assert strategy == "failed"
    assert out == paper


def test_empty_section_returns_failed():
    paper = _paper("Some prose.")
    out, strategy = insert_image_after_paragraph(paper, "", "Some anchor", IMG_MD)
    assert strategy == "failed"
    assert out == paper


# ---------------------------------------------------------------------------
# Final-section (no ## heading after) — section_fallback inserts at end
# ---------------------------------------------------------------------------


def test_section_fallback_in_final_section():
    paper = "# Title\n\n## Final Section\n\nCompletely unrelated prose about Roman aqueducts.\n"
    out, strategy = insert_image_after_paragraph(
        paper, "Final Section", "The Anunnaki descended from the heavens", IMG_MD
    )
    assert strategy == "section_fallback"
    assert IMG_MD in out
    # Image lands AFTER all the final-section prose
    final_idx = out.find("## Final Section")
    aq_idx = out.find("Roman aqueducts")
    assert final_idx < aq_idx < out.find(IMG_MD)


# ---------------------------------------------------------------------------
# Idempotency / repeated insert
# ---------------------------------------------------------------------------


def test_inserting_twice_inserts_two_images():
    body = "The Anunnaki descended.\n\nMore prose."
    paper = _paper(body)
    out1, _ = insert_image_after_paragraph(paper, "Investigation", "The Anunnaki descended", IMG_MD)
    out2, _ = insert_image_after_paragraph(out1, "Investigation", "The Anunnaki descended", IMG_MD)
    # Two images now in output
    assert len(re.findall(re.escape(IMG_MD), out2)) == 2
