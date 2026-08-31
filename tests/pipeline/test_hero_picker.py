"""Hero selection: the banner image chosen from a paper's embedded images.

The published solar-superflares paper ran a 194x110 Europeana TV frame as its
banner. It won on aspect ratio alone — at 1.76 it took the top landscape
bonus, and nothing in the scoring looked at absolute size, so a thumbnail
outranked every full-resolution photograph in the paper.
"""

from __future__ import annotations

from PIL import Image

from pipeline.lyra.hero_picker import HERO_MIN_WIDTH, pick_hero_image


def _write(tmp_path, monkeypatch, name: str, size: tuple[int, int]) -> str:
    """Write a real image under a patched images root; return its web path."""
    import pipeline.lyra.hero_picker as hp

    root = tmp_path / "data" / "research-images" / "paper"
    root.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size).save(root / name)
    monkeypatch.setattr(hp, "_IMAGES_ROOT", tmp_path)
    return f"/data/research-images/paper/{name}"


def _entry(web_path: str, title: str) -> dict:
    return {
        "web_path": web_path,
        "title": title,
        "source_url": "https://example.org/x",
        "source_name": "wikimedia",
        "rationale": "",
        "section_heading": "Findings",
    }


def test_a_thumbnail_never_outranks_a_full_size_image(tmp_path, monkeypatch):
    """The exact solar-superflares failure: a tiny wide frame beat everything."""
    tiny = _write(tmp_path, monkeypatch, "tiny.jpg", (194, 110))  # ratio 1.76
    big = _write(tmp_path, monkeypatch, "big.jpg", (960, 891))  # ratio 1.08
    hero = pick_hero_image("Solar Superflares", [_entry(tiny, "Kepler probe"), _entry(big, "Sun")])
    assert hero is not None
    assert hero["src"] == big


def test_landscape_still_wins_among_eligible_images(tmp_path, monkeypatch):
    """The size floor is a gate, not a new ranking — above it, format decides."""
    wide = _write(tmp_path, monkeypatch, "wide.jpg", (1600, 900))
    tall = _write(tmp_path, monkeypatch, "tall.jpg", (800, 1200))
    hero = pick_hero_image("Solar Superflares", [_entry(tall, "Sun"), _entry(wide, "Sun")])
    assert hero["src"] == wide


def test_falls_back_to_a_small_image_when_nothing_qualifies(tmp_path, monkeypatch):
    """A paper whose images are all small still gets a banner — degrading to
    no hero at all would be a worse regression than a soft one."""
    a = _write(tmp_path, monkeypatch, "a.jpg", (194, 110))
    b = _write(tmp_path, monkeypatch, "b.jpg", (200, 150))
    hero = pick_hero_image("Solar Superflares", [_entry(a, "x"), _entry(b, "y")])
    assert hero is not None
    assert hero["src"] in (a, b)


def test_min_width_is_above_thumbnail_territory():
    assert HERO_MIN_WIDTH >= 600


def test_no_images_means_no_hero():
    assert pick_hero_image("Any", []) is None


def test_evidence_outranks_an_illustration_as_banner(tmp_path, monkeypatch):
    """A banner presents the paper. An image the judge would not call a
    depiction of any claim must not be the first thing a reader sees —
    the reworked paper picked an ice-core chart marked "Illustration:".
    """
    # Same title, same size, same position bonus — `verified` is the ONLY
    # difference, so the assertion cannot pass on relevance by accident.
    illustration = _write(tmp_path, monkeypatch, "chart.jpg", (1600, 900))
    evidence = _write(tmp_path, monkeypatch, "flare.jpg", (1600, 900))
    entries = [
        {**_entry(illustration, "Solar image"), "verified": False},
        {**_entry(evidence, "Solar image"), "verified": True},
    ]
    assert pick_hero_image("Solar Superflares", entries)["src"] == evidence


def test_leading_title_words_weigh_double(tmp_path, monkeypatch):
    """ "Solar Superflares, Cosmic Impacts, and Fire-and-Flood Mythology" is
    about superflares first; a flood tablet matching the tail must not tie
    with a solar image matching the head."""
    flood = _write(tmp_path, monkeypatch, "flood.jpg", (960, 700))
    solar = _write(tmp_path, monkeypatch, "solar.jpg", (960, 700))
    entries = [
        {**_entry(flood, "Babylonian flood tablet"), "verified": True},
        {**_entry(solar, "Solar flare eruption"), "verified": True},
    ]
    hero = pick_hero_image("Solar Superflares, Cosmic Impacts, and Flood Mythology", entries)
    assert hero["src"] == solar


def test_missing_verified_key_is_treated_as_evidence(tmp_path, monkeypatch):
    """Papers embedded before the two-tier split carry no `verified` key —
    they must not all be demoted to illustrations."""
    a = _write(tmp_path, monkeypatch, "a.jpg", (960, 700))
    hero = pick_hero_image("Any", [_entry(a, "Legacy image")])
    assert hero["src"] == a


def test_title_lead_splits_on_the_first_separator():
    from pipeline.lyra.hero_picker import _title_lead

    assert _title_lead("Solar Superflares, Cosmic Impacts, and Flood Myth") == "Solar Superflares"
    assert _title_lead("Yonaguni: Natural or Man-Made?") == "Yonaguni"


def test_title_lead_falls_back_to_the_first_words():
    from pipeline.lyra.hero_picker import _title_lead

    assert _title_lead("The engineering and origins of the Baalbek megaliths") == (
        "The engineering and origins"
    )
    assert _title_lead("") == ""
