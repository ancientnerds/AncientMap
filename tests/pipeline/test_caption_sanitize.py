"""Tests for caption-field sanitization used by image_markdown.

Regression coverage for the Run #12 Moyen-Orient-Amarna caption that
spilled out of its figcaption: the Wikimedia Commons Artist field
contained literal ``*`` (markdown italic delimiters), embedded
newlines, and a duplicated ``derivative work:`` chain.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.lyra.theo_image_captions import _sanitize_caption_field, build_caption


@dataclass
class _Cand:
    title: str
    artist: str
    source: str
    description: str = ""
    license: str = ""
    license_url: str = ""
    url: str = ""


def test_strips_asterisks() -> None:
    out = _sanitize_caption_field("*foo* bar *baz*")
    assert "*" not in out
    assert out == "foo bar baz"


def test_collapses_newlines_and_runs_of_whitespace() -> None:
    out = _sanitize_caption_field("foo\nbar\n\nbaz   qux")
    assert "\n" not in out
    assert out == "foo bar baz qux"


def test_replaces_underscores_with_spaces() -> None:
    out = _sanitize_caption_field("Moyen_Orient_Amarna_1.svg")
    assert out == "Moyen Orient Amarna 1.svg"


def test_dedupes_repeated_phrases() -> None:
    out = _sanitize_caption_field("derivative work: Zunkir (talk) derivative work: Zunkir (talk)")
    assert out.count("derivative work: Zunkir (talk)") == 1


def test_wikimedia_messy_artist_real_case() -> None:
    # Verbatim Artist string from `File:Moyen_Orient_Amarna_1.png` on
    # Wikimedia Commons that caused the user-visible bug.
    artist = (
        "Moyen_Orient_Amarna_1.svg: *Middle_East_topographic_map-blank.svg: "
        "Sémhur (talk)\nderivative work: Zunkir (talk)\nderivative work: "
        "Zunkir (talk)"
    )
    out = _sanitize_caption_field(artist)
    assert "*" not in out
    assert "\n" not in out
    # The repeated derivative-work line collapses to one occurrence.
    assert out.count("derivative work: Zunkir (talk)") == 1


def test_build_caption_keeps_outer_asterisk_pair_only() -> None:
    cand = _Cand(
        title="Moyen Orient Amarna 1",
        artist=(
            "Moyen_Orient_Amarna_1.svg: *Middle_East_topographic_map-blank.svg: "
            "Sémhur (talk)\nderivative work: Zunkir (talk)\nderivative work: "
            "Zunkir (talk)"
        ),
        source="wikidata",
    )
    caption = build_caption(cand, "Shows the trade routes")
    # Exactly two asterisks — the outer italic wrapper.
    assert caption.count("*") == 2
    # No newlines — the whole caption must fit on one line so the
    # frontend's FIGURE_RE captures it.
    assert "\n" not in caption


def test_empty_artist_omits_attribution() -> None:
    cand = _Cand(title="Mycenaean kylix", artist="", source="met_museum")
    caption = build_caption(cand, "A drinking cup from Mycenae")
    # Source label still appears, but no leading slash from empty artist.
    assert "Photo: The Met" in caption


def test_title_with_parens_survives() -> None:
    cand = _Cand(title="Tablet (KTU 1.6)", artist="Yale", source="wikidata")
    caption = build_caption(cand, "Ugaritic text")
    assert "(KTU 1.6)" in caption
