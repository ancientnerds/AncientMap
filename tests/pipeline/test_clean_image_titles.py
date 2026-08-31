"""Caption backfill: filename cleanup + non-Latin tail removal.

The non-Latin cases mirror the two August 2026 papers (Yonaguni, Sumerian
ziggurat) that the artifact gate held because Wikimedia's multilingual
`description` field had been embedded verbatim in their captions.
"""

from __future__ import annotations

from pipeline.lyra.clean_image_titles import _drop_non_latin_tail, _rewrite_report


def test_caption_drops_japanese_description_tail():
    caption = (
        "Yonaguni Ryukyu no Kaze. Photo: Paipateroma / Wikimedia Commons. "
        "与那国島にある大河ドラマ「琉球の風」での結婚の地に建てられた記念碑。"
    )
    out = _drop_non_latin_tail(caption)
    assert out == "Yonaguni Ryukyu no Kaze. Photo: Paipateroma / Wikimedia Commons."


def test_caption_drops_arabic_description_tail():
    caption = (
        "SumerianZiggurat. Photo: Michael V Fox / Wikimedia Commons. "
        "English: Sumerian ziggurat; Arabic: الزقورة السومرية."
    )
    out = _drop_non_latin_tail(caption)
    assert "الزقورة" not in out
    assert "Photo: Michael V Fox / Wikimedia Commons." in out


def test_caption_keeps_latin_description_tail():
    caption = "Nebra Sky Disc. Photo: Frank Vincentz / Wikimedia Commons. A Bronze Age disc."
    assert _drop_non_latin_tail(caption) == caption


def test_caption_keeps_attribution_even_when_artist_is_non_latin():
    """Attribution is a licensing obligation — never silently stripped.

    The paper holds for a human instead; that is the honest outcome.
    """
    caption = "Some Relic. Photo: Иванов / Wikimedia Commons."
    assert "Иванов" in _drop_non_latin_tail(caption)


def test_rewrite_report_reaches_gallery_captions_without_own_image():
    """Galleries stack captions under ONE image; the later ones have no
    `![alt](path)` of their own. The block-anchored pass cannot see them —
    this is why the Yonaguni paper's Japanese caption survived the first
    version of this backfill.
    """
    report = (
        "![Terrace](/data/research-images/x/p2_terrace.jpg)\n\n"
        "*Main Terrace. Photo: Melkov / Wikimedia Commons. A part of the monument.*\n"
        "[Source](https://commons.wikimedia.org/wiki/File:Terrace.jpg)\n\n"
        "*Ryukyu no Kaze. Photo: Paipateroma / Wikimedia Commons. "
        "与那国島にある大河ドラマ「琉球の風」での結婚の地に建てられた記念碑。.*\n"
        "[Source](https://commons.wikimedia.org/wiki/File:Kaze.jpg)\n"
    )
    new_report, count = _rewrite_report(report)
    assert count == 1
    assert "与那国島" not in new_report
    assert "*Ryukyu no Kaze. Photo: Paipateroma / Wikimedia Commons.*" in new_report
    assert "A part of the monument." in new_report, "Latin captions untouched"
