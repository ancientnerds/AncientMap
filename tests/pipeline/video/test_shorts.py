"""Pure-function tests for the site-shorts pipeline (no network, no ffmpeg)."""

from pathlib import Path

import pytest

from pipeline.video.media import ff_path
from pipeline.video.shorts_export import RARITY_NAMES, assemble_site
from pipeline.video.shorts_images import local_image_name
from pipeline.video.shorts_render import (
    BEAT_S,
    NARRATION_TAIL_S,
    REVEAL_S,
    build_description,
    credit_line,
    is_portrait,
    pan_filter,
    plan_timeline,
    reveal_filter,
    wrap_lines,
)

HERO = (Path("hero.jpg"), 4320, 3240)
IMGS = [HERO, (Path("a.jpg"), 1600, 1200), (Path("b.jpg"), 1600, 1200), (Path("c.jpg"), 1600, 1200)]


def _total(segments):
    return sum(s.duration for s in segments)


class TestPlanTimeline:
    def test_opening_covers_part_of_the_narration_then_pans(self):
        segs = plan_timeline(
            narration_s=16.4,
            images=IMGS,
            opening=(Path("opening.mp4"), 6.0),
            opening_start=0.0,
        )
        kinds = [s.kind for s in segs]
        # 17.0 s span: 6 s clip, 11 s over 4 stills (3.5 s max) → but only 3 in the pool
        assert kinds == ["clip", "pan", "pan", "pan", "black", "reveal"]
        assert segs[0].duration == 6.0 and segs[0].start == 0.0
        assert segs[1].duration == pytest.approx(11.0 / 3)
        assert [s.forward for s in segs[1:4]] == [True, False, True]
        assert segs[-1].source == str(HERO[0])
        assert _total(segs) == pytest.approx(17.0 + BEAT_S + REVEAL_S)

    def test_long_opening_is_capped_at_the_narration_span(self):
        segs = plan_timeline(narration_s=5.0, images=IMGS, opening=(Path("o.mp4"), 9.0))
        assert [s.kind for s in segs] == ["clip", "black", "reveal"]
        assert segs[0].duration == pytest.approx(5.0 + NARRATION_TAIL_S)

    def test_opening_deficit_within_slack_is_absorbed(self):
        segs = plan_timeline(narration_s=5.0, images=IMGS, opening=(Path("o.mp4"), 5.2))
        assert [s.kind for s in segs] == ["clip", "black", "reveal"]

    def test_no_opening_uses_stills_only(self):
        segs = plan_timeline(narration_s=6.0, images=IMGS, opening=None)
        assert [s.kind for s in segs] == ["pan", "pan", "black", "reveal"]
        assert _total(segs) == pytest.approx(6.6 + BEAT_S + REVEAL_S)

    def test_portrait_stills_pan_vertically(self):
        tall = [HERO, (Path("tall.jpg"), 1000, 3000)]
        segs = plan_timeline(narration_s=3.0, images=tall, opening=None)
        assert segs[0].kind == "pan" and segs[0].vertical is True

    def test_only_hero_available_reuses_it(self):
        segs = plan_timeline(narration_s=3.0, images=[HERO], opening=None)
        assert segs[0].kind == "pan" and segs[0].source == str(HERO[0])

    def test_requires_an_image(self):
        with pytest.raises(ValueError):
            plan_timeline(narration_s=5.0, images=[], opening=None)


class TestText:
    def test_wrap_lines_splits_long_names(self):
        lines = wrap_lines("Gochang, Hwasun and Ganghwa Dolmen Sites")
        assert len(lines) >= 3
        assert all(len(line) <= 16 for line in lines)

    def test_wrap_lines_short_name_single_line(self):
        assert wrap_lines("Machu Picchu") == ["Machu Picchu"]

    def test_credit_line(self):
        assert credit_line({"author": "Martin St-Amant", "license": "CC BY-SA 3.0"}) == (
            "Photo: Martin St-Amant · CC BY-SA 3.0 · Wikimedia Commons"
        )
        assert (
            credit_line({"author": None, "license": None}) == "Photo: Unknown · Wikimedia Commons"
        )

    def test_description_lists_every_image_with_license(self):
        site = {
            "name": "Machu Picchu",
            "country": "Peru",
            "card_text": "A citadel.",
            "rarity_name": "Legendary",
            "rarity_tier": 5,
            "total_power": 33,
            "page_path": "/sites/peru/machu-picchu-abcd1234",
        }
        imgs = [
            {
                "title": "Intiwatana",
                "filename": "x.jpg",
                "author": "bob",
                "license": "CC BY 2.0",
                "commons_page_url": "https://c/1",
                "original_url": "u1",
            },
            {
                "title": None,
                "filename": "y.jpg",
                "author": None,
                "license": None,
                "commons_page_url": None,
                "original_url": "u2",
            },
        ]
        text = build_description(site, imgs, "English_CaptivatingStoryteller", mapbox_used=True)
        assert "https://ancientnerds.com/sites/peru/machu-picchu-abcd1234" in text
        assert "© Mapbox © Maxar" in text
        assert "Mapbox" not in build_description(site, imgs, "v")
        assert "- Intiwatana — bob (CC BY 2.0) https://c/1" in text
        assert "- y.jpg — Unknown (license unknown) u2" in text
        assert "AI-generated voice" in text


class TestFilters:
    def test_ff_path_escapes_drive_colon_and_backslashes(self):
        assert ff_path(Path(r"C:\x\fonts\a.ttf")) == "C\\:/x/fonts/a.ttf"

    def test_pan_filter_sweeps_the_overflow_axis(self):
        fwd = pan_filter(3.4, forward=True, vertical=False)
        assert "scale=1080:1920:force_original_aspect_ratio=increase" in fwd
        assert "x='(iw-ow)/2+(t/3.400-0.5)*min(iw-ow\\,900)':y=0" in fwd
        back = pan_filter(3.4, forward=False, vertical=False)
        assert "x='(iw-ow)/2-(t/3.400-0.5)*min(iw-ow\\,900)':y=0" in back
        tall = pan_filter(2.0, forward=True, vertical=True)
        assert "x=0:y='(ih-oh)/2+(t/2.000-0.5)*min(ih-oh\\,900)'" in tall
        assert "fps=60" in fwd

    def test_is_portrait_threshold(self):
        assert is_portrait(1000, 3000) is True
        assert is_portrait(1600, 1200) is False
        assert is_portrait(1080, 1920) is False  # exactly 9:16 fills the frame, no overflow

    def test_reveal_filter_positions_follow_name_lines(self, tmp_path):
        one = reveal_filter(name_lines=1, ribbon_width=300, rarity_tier=5, text_dir=tmp_path)
        three = reveal_filter(name_lines=3, ribbon_width=300, rarity_tier=4, text_dir=tmp_path)
        assert "0xFFC107" in one and "0x9C27B0" in three
        assert "x=390:" in one  # (1080-300)/2 centred ribbon
        assert one != three
        assert "textfile='" in one and "name.txt" in one


class TestExportShape:
    def test_assemble_site_maps_rarity_and_path(self):
        row = {
            "id": "12345678-aaaa-bbbb-cccc-1234567890ab",
            "name": "Machu Picchu",
            "country": "Peru",
            "lat": -13.16,
            "lon": -72.54,
            "site_type": "Fortress/citadel",
            "period_name": "1000 - 1500 AD",
            "description": " desc ",
            "card_description": " card ",
            "rarity_tier": 5,
            "rarity_score": 61.0,
            "total_power": 33,
            "antiquity": 1,
            "fortification": 2,
            "cultural_influence": 3,
            "mystery": 4,
            "legacy": 5,
            "civilization": "Inca",
        }
        imgs = [
            {
                "id": 1,
                "filename": "a.jpg",
                "original_url": "u",
                "commons_page_url": "c",
                "author": "x",
                "author_url": None,
                "license": "CC0",
                "license_url": None,
                "title": "t",
                "is_hero": True,
                "is_lead": False,
                "sort_order": 0,
                "width": 1600,
                "height": 900,
            }
        ]
        site = assemble_site(row, imgs)
        assert site["rarity_name"] == RARITY_NAMES[5] == "Legendary"
        assert site["slug"] == "machu-picchu"
        assert site["page_path"].startswith("/sites/peru/machu-picchu-")
        assert site["card_text"] == "card" and site["lng"] == -72.54
        assert site["images"][0]["is_hero"] is True and site["stats"]["mystery"] == 4


def test_local_image_name_is_filesystem_safe_and_keeps_original_extension():
    assert local_image_name(3, "Machu Picchu (cropped) ü.jpg") == "03_Machu_Picchu_cropped.jpg"
    assert (
        local_image_name(3, "Machu_Picchu.webp", "https://upload.wikimedia.org/x/Machu_Picchu.JPG")
        == "03_Machu_Picchu.jpg"
    )
