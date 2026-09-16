"""Pure-function tests for the site-shorts pipeline (no network, no ffmpeg)."""

from pathlib import Path

import pytest

from pipeline.video.media import ff_path
from pipeline.video.shorts_export import RARITY_NAMES, assemble_site
from pipeline.video.shorts_images import local_image_name
from pipeline.video.shorts_render import (
    NAME_AUDIO_DELAY_S,
    NARRATION_TAIL_S,
    build_description,
    clip_filter,
    is_portrait,
    name_alpha,
    name_audio_at,
    pan_filter,
    plan_timeline,
    wrap_lines,
)

IMGS = [
    (Path("a.jpg"), 4320, 3240),
    (Path("b.jpg"), 1600, 1200),
    (Path("c.jpg"), 1600, 1200),
    (Path("d.jpg"), 1600, 1200),
]
OPENING = (Path("short-opening.mp4"), 6.0)
RETURN = (Path("short-return.mp4"), 3.0)


def _total(segments):
    return sum(s.duration for s in segments)


class TestPlanTimeline:
    def test_loop_cut_opening_stills_return(self):
        segs = plan_timeline(narration_s=16.4, images=IMGS, opening=OPENING, closing=RETURN)
        kinds = [s.kind for s in segs]
        # 17.0 s narration span: 6 s opening, 11 s over 4 stills (3.5 s max each), then the return
        assert kinds == ["clip", "pan", "pan", "pan", "pan", "return"]
        assert segs[0].duration == 6.0 and segs[0].start == 0.0
        assert segs[1].duration == pytest.approx(11.0 / 4)
        assert [s.forward for s in segs[1:5]] == [True, False, True, False]
        assert segs[-1].duration == 3.0  # never shortened: its last frame is the loop point
        assert _total(segs) == pytest.approx(17.0 + 3.0)

    def test_name_audio_starts_shortly_into_the_return_clip(self):
        segs = plan_timeline(narration_s=16.4, images=IMGS, opening=OPENING, closing=RETURN)
        assert name_audio_at(segs) == pytest.approx(17.0 + NAME_AUDIO_DELAY_S)

    def test_without_return_clip_name_audio_follows_the_stills(self):
        segs = plan_timeline(narration_s=6.0, images=IMGS, opening=None, closing=None)
        assert [s.kind for s in segs] == ["pan", "pan"]
        assert name_audio_at(segs) == pytest.approx(6.0 + NARRATION_TAIL_S)

    def test_long_opening_is_capped_at_the_narration_span(self):
        segs = plan_timeline(
            narration_s=5.0, images=IMGS, opening=(Path("o.mp4"), 9.0), closing=None
        )
        assert [s.kind for s in segs] == ["clip"]
        assert segs[0].duration == pytest.approx(5.0 + NARRATION_TAIL_S)

    def test_opening_deficit_within_slack_is_absorbed(self):
        segs = plan_timeline(
            narration_s=5.0, images=IMGS, opening=(Path("o.mp4"), 5.2), closing=None
        )
        assert [s.kind for s in segs] == ["clip"]

    def test_portrait_stills_pan_vertically(self):
        tall = [(Path("tall.jpg"), 1000, 3000)]
        segs = plan_timeline(narration_s=3.0, images=tall, opening=None, closing=None)
        assert segs[0].kind == "pan" and segs[0].vertical is True

    def test_requires_an_image(self):
        with pytest.raises(ValueError):
            plan_timeline(narration_s=5.0, images=[], opening=None, closing=None)


class TestText:
    def test_wrap_lines_splits_long_names(self):
        lines = wrap_lines("Gochang, Hwasun and Ganghwa Dolmen Sites")
        assert len(lines) >= 3
        assert all(len(line) <= 14 for line in lines)

    def test_wrap_lines_short_name_single_line(self):
        assert wrap_lines("Machu Picchu") == ["Machu Picchu"]

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
        assert "- Intiwatana — bob (CC BY 2.0) https://c/1" in text
        assert "- y.jpg — Unknown (license unknown) u2" in text
        assert "© Mapbox © Maxar" in text
        assert "AI-generated voice" in text
        assert "Mapbox" not in build_description(site, imgs, "v")


class TestFilters:
    def test_ff_path_escapes_drive_colon_and_backslashes(self):
        assert ff_path(Path(r"C:\x\fonts\a.ttf")) == "C\\:/x/fonts/a.ttf"

    def test_pan_filter_moves_from_30_to_70_percent_eased(self):
        fwd = pan_filter(2.75, forward=True, vertical=False)
        assert "scale=1080:1920:force_original_aspect_ratio=increase" in fwd
        assert "x='(iw-ow)*(0.3+0.4*(t/2.750)*(t/2.750)*(3-2*(t/2.750)))':y=0" in fwd
        back = pan_filter(2.75, forward=False, vertical=False)
        assert "x='(iw-ow)*(0.7-0.4*(t/2.750)*(t/2.750)*(3-2*(t/2.750)))':y=0" in back
        tall = pan_filter(2.0, forward=True, vertical=True)
        assert "x=0:y='(ih-oh)*(0.3+0.4*(t/2.000)*(t/2.000)*(3-2*(t/2.000)))'" in tall
        assert "fps=60" in fwd

    def test_is_portrait_threshold(self):
        assert is_portrait(1000, 3000) is True
        assert is_portrait(1600, 1200) is False
        assert is_portrait(1080, 1920) is False  # exactly 9:16 fills the frame, no overflow

    def test_name_alpha_is_gone_before_the_loop_point(self):
        expr = name_alpha(3.0)
        assert expr.startswith("if(lt(t\\,0.3)\\,t/0.3\\,")
        assert "if(gt(t\\,2.850)\\,0\\," in expr  # fully transparent for the last 0.15 s
        assert "gt(t\\,2.350)" in expr and "(2.850-t)/0.5" in expr

    def test_clip_filter_adds_name_only_for_the_return(self, tmp_path):
        credit = tmp_path / "credit.txt"
        name = tmp_path / "name.txt"
        plain = clip_filter(6.0, credit_file=credit)
        named = clip_filter(3.0, credit_file=credit, name_file=name, name_lines=2)
        assert "credit.txt" in plain and "name.txt" not in plain
        assert "name.txt" in named and "fontsize=84" in named
        assert named.endswith("format=yuv420p")


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
