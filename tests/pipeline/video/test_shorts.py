"""Pure-function tests for the site-shorts pipeline (no network, no ffmpeg)."""

from pathlib import Path

import pytest

from pipeline.video.media import ff_path
from pipeline.video.shorts_export import RARITY_NAMES, assemble_site
from pipeline.video.shorts_images import local_image_name
from pipeline.video.shorts_render import (
    APPROACH_MAX_S,
    BEAT_S,
    NARRATION_TAIL_S,
    REVEAL_S,
    build_description,
    credit_line,
    kenburns_filter,
    plan_timeline,
    reveal_filter,
    wrap_lines,
)

HERO = Path("hero.jpg")
IMGS = [HERO, Path("a.jpg"), Path("b.jpg"), Path("c.jpg")]


def _total(segments):
    return sum(s.duration for s in segments)


class TestPlanTimeline:
    def test_full_chain_terrain_covers_narration(self):
        segs = plan_timeline(
            narration_s=15.0,
            images=IMGS,
            approach=(Path("approach.mp4"), 6.0),
            terrain=(Path("terrain.mp4"), 16.0),
            terrain_start=0.3,
        )
        kinds = [s.kind for s in segs]
        assert kinds == ["clip", "clip", "black", "reveal"]
        assert segs[0].start == 0.0 and segs[1].start == 0.3
        assert segs[0].duration == APPROACH_MAX_S  # capped
        assert segs[1].duration == pytest.approx(15.0 + NARRATION_TAIL_S)
        assert segs[-1].source == str(HERO)
        assert _total(segs) == pytest.approx(APPROACH_MAX_S + 15.6 + BEAT_S + REVEAL_S)

    def test_short_terrain_falls_back_to_kenburns_for_the_rest(self):
        segs = plan_timeline(
            narration_s=15.0,
            images=IMGS,
            approach=None,
            terrain=(Path("terrain.mp4"), 8.0),
        )
        assert [s.kind for s in segs] == ["clip", "kenburns", "kenburns", "black", "reveal"]
        assert segs[0].duration == 8.0
        # 7.6 s remain → 2 images of 3.8 s, hero kept out of the narration pool
        assert segs[1].duration == pytest.approx(3.8)
        assert {segs[1].source, segs[2].source} == {"a.jpg", "b.jpg"}
        assert segs[1].zoom_in and not segs[2].zoom_in

    def test_terrain_deficit_within_slack_is_absorbed(self):
        segs = plan_timeline(
            narration_s=15.0, images=IMGS, approach=None, terrain=(Path("t.mp4"), 15.2)
        )
        assert [s.kind for s in segs] == ["clip", "black", "reveal"]
        assert segs[0].duration == pytest.approx(15.2)

    def test_no_clips_at_all_uses_images_only(self):
        segs = plan_timeline(narration_s=12.0, images=IMGS, approach=None, terrain=None)
        assert [s.kind for s in segs] == ["kenburns", "kenburns", "kenburns", "black", "reveal"]
        assert _total(segs) == pytest.approx(12.6 + BEAT_S + REVEAL_S)

    def test_only_hero_available_reuses_it(self):
        segs = plan_timeline(narration_s=5.0, images=[HERO], approach=None, terrain=None)
        assert segs[0].kind == "kenburns" and segs[0].source == str(HERO)

    def test_requires_an_image(self):
        with pytest.raises(ValueError):
            plan_timeline(narration_s=5.0, images=[], approach=None, terrain=None)


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
        text = build_description(site, imgs, "English_CaptivatingStoryteller")
        assert "https://ancientnerds.com/sites/peru/machu-picchu-abcd1234" in text
        assert "- Intiwatana — bob (CC BY 2.0) https://c/1" in text
        assert "- y.jpg — Unknown (license unknown) u2" in text
        assert "AI-generated voice" in text


class TestFilters:
    def test_ff_path_escapes_drive_colon_and_backslashes(self):
        assert ff_path(Path(r"C:\x\fonts\a.ttf")) == "C\\:/x/fonts/a.ttf"

    def test_kenburns_zoom_direction(self):
        assert "z='1+0.12*on/(30*4.000)'" in kenburns_filter(True, 4.0)
        assert "z='1.12-0.12*on/(30*4.000)'" in kenburns_filter(False, 4.0)
        assert "s=1080x1920" in kenburns_filter(True, 4.0)

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
