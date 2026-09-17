"""Pure-function tests for the site-shorts pipeline (no network, no ffmpeg, no VLM)."""

from pathlib import Path

import pytest

from pipeline.video.media import ff_path
from pipeline.video.shorts_audit import evaluate, passed
from pipeline.video.shorts_export import RARITY_NAMES, assemble_site, orbit_zoom_for
from pipeline.video.shorts_images import local_image_name
from pipeline.video.shorts_render import (
    DISSOLVE_S,
    NAME_AUDIO_DELAY_S,
    NARRATION_TAIL_S,
    build_description,
    clip_filter,
    final_graph,
    gain_db,
    mix_graph,
    name_alpha,
    name_audio_at,
    name_layout,
    plan_timeline,
    pushin_filter,
    stills_graph,
    wrap_lines,
)
from pipeline.video.shorts_select import (
    Candidate,
    aspect_penalty,
    is_panorama,
    normalize_subject,
    order_by_narration,
    reject_reason,
    score,
    select_stills,
)

IMGS = [Path("a.jpg"), Path("b.jpg"), Path("c.jpg"), Path("d.jpg")]
OPENING = (Path("short-opening.mp4"), 6.0)
RETURN = (Path("short-return.mp4"), 3.0)


def _total(segments):
    return sum(s.duration for s in segments)


class TestPlanTimeline:
    def test_loop_cut_opening_stills_return(self):
        segs = plan_timeline(narration_s=16.4, images=IMGS, opening=OPENING, closing=RETURN)
        kinds = [s.kind for s in segs]
        # 17.0 s narration span: 6 s opening, 11 s over 4 stills (3.5 s max each), then the return
        assert kinds == ["clip", "still", "still", "still", "still", "return"]
        assert segs[0].duration == 6.0 and segs[0].start == 0.0
        assert segs[1].duration == pytest.approx(11.0 / 4)
        assert [s.source for s in segs[1:5]] == ["a.jpg", "b.jpg", "c.jpg", "d.jpg"]
        assert segs[-1].duration == 3.0  # never shortened: its last frame is the loop point
        assert _total(segs) == pytest.approx(17.0 + 3.0)

    def test_name_audio_starts_shortly_into_the_return_clip(self):
        segs = plan_timeline(narration_s=16.4, images=IMGS, opening=OPENING, closing=RETURN)
        assert name_audio_at(segs, name_s=1.5) == pytest.approx(17.0 + NAME_AUDIO_DELAY_S)

    def test_without_return_clip_name_audio_follows_the_stills(self):
        segs = plan_timeline(narration_s=6.0, images=IMGS, opening=None, closing=None)
        assert [s.kind for s in segs] == ["still", "still"]
        assert name_audio_at(segs, name_s=0.5) == pytest.approx(6.6 - 0.5 - 0.15)

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

    def test_fewer_stills_than_slots_get_longer_slots(self):
        segs = plan_timeline(narration_s=10.0, images=IMGS[:2], opening=None, closing=None)
        assert [s.kind for s in segs] == ["still", "still"]
        assert segs[0].duration == pytest.approx(5.3)

    def test_requires_a_still(self):
        with pytest.raises(ValueError):
            plan_timeline(narration_s=5.0, images=[], opening=None, closing=None)


class TestStillsGraph:
    def test_dissolves_keep_the_total_length(self):
        lengths, graph = stills_graph([2.75, 2.75, 2.75])
        assert lengths == [2.75 + DISSOLVE_S, 2.75 + DISSOLVE_S, 2.75]
        assert graph.count("xfade=transition=fade") == 2
        assert "offset=2.750[x1]" in graph and "offset=5.500[out]" in graph
        assert "[x1][v2]xfade" in graph

    def test_single_still_has_no_dissolve(self):
        lengths, graph = stills_graph([4.0])
        assert lengths == [4.0]
        assert "xfade" not in graph and graph.endswith("[out]")

    def test_pushin_zooms_from_100_to_106_percent(self):
        f = pushin_filter(2.75)
        assert f.startswith("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,")
        assert "scale=eval=frame:w='iw*(1+0.06*t/2.750)':h='ih*(1+0.06*t/2.750)'" in f
        assert f.endswith("crop=1080:1920,fps=60,format=yuv420p")


class TestText:
    def test_wrap_lines_splits_long_names(self):
        lines = wrap_lines("Gochang, Hwasun and Ganghwa Dolmen Sites")
        assert len(lines) >= 3
        assert all(len(line) <= 14 for line in lines)

    def test_wrap_lines_short_name_single_line(self):
        assert wrap_lines("Machu Picchu") == ["Machu Picchu"]

    def test_long_spoken_name_starts_early_enough_to_end_before_the_loop_point(self):
        segs = plan_timeline(narration_s=16.4, images=IMGS, opening=OPENING, closing=RETURN)
        at = name_audio_at(segs, name_s=6.0)
        assert at == pytest.approx(20.0 - 6.0 - 0.15)
        assert at < 17.0  # starts over the last still

    def test_name_layout_shrinks_long_names_to_three_lines_or_fewer(self):
        lines, size, _ = name_layout("Machu Picchu")
        assert (lines, size) == (["Machu Picchu"], 84)
        lines, size, _ = name_layout("Gochang, Hwasun and Ganghwa Dolmen Sites")
        assert len(lines) <= 3 and size < 84

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

    def test_name_alpha_is_gone_before_the_loop_point(self):
        expr = name_alpha(3.0)
        assert expr.startswith("if(lt(t\\,0.3)\\,t/0.3\\,")
        assert "if(gt(t\\,2.850)\\,0\\," in expr  # fully transparent for the last 0.15 s
        assert "gt(t\\,2.350)" in expr and "(2.850-t)/0.5" in expr

    def test_mix_graph_processes_both_voices_dry_and_bounds_them(self):
        g = mix_graph(16.7, 19.5)
        assert g.count("acompressor=") == 2
        assert "adelay=16700:all=1[d1]" in g
        assert g.endswith("apad=whole_dur=19.500,atrim=duration=19.500[a]")
        assert "loudnorm" not in g and "afir" not in g and "aecho" not in g

    def test_final_graph_is_look_plus_fixed_gain(self):
        g = final_graph(gain_db(-20.5))
        assert g.startswith("[0:v]eq=saturation=0.78") and "[vout];" in g
        assert g.endswith("[1:a]volume=6.50dB,alimiter=limit=0.75:level=false[a]")

    def test_clip_filter_adds_name_only_for_the_return(self, tmp_path):
        credit = tmp_path / "credit.txt"
        name = tmp_path / "name.txt"
        plain = clip_filter(6.0, credit_file=credit)
        named = clip_filter(3.0, credit_file=credit, name_file=name, name_lines=2)
        assert "credit.txt" in plain and "name.txt" not in plain
        assert "name.txt" in named and "fontsize=84" in named
        assert named.endswith("format=yuv420p")


def _cand(name, w, h, verdict=None, dh=0):
    return Candidate(
        image={"filename": name, "local_path": name}, width=w, height=h, dhash=dh, verdict=verdict
    )


def _good(subject="terraces", quality=4, **over):
    v = {
        "kind": "site_photo",
        "subject": subject,
        "people_prominent": False,
        "text_or_overlay": False,
        "quality": quality,
        "relevance": 4,
        "illustrates": "",
        "vertical_crop_ok": True,
    }
    v.update(over)
    return v


class TestSelection:
    def test_aspect_penalty_is_zero_at_9_16_and_symmetric(self):
        assert aspect_penalty(1080, 1920) == pytest.approx(0.0)
        # mirror of 4:3 around 9:16 is (9/16)^2 / (4/3) ≈ 0.2373
        assert aspect_penalty(1600, 1200) == pytest.approx(aspect_penalty(2373, 10000), rel=1e-3)

    def test_panorama_threshold(self):
        assert is_panorama(1598, 472) is True
        assert is_panorama(1600, 960) is False

    @pytest.mark.parametrize(
        "verdict, reason",
        [
            (_good(kind="map_or_document"), "kind=map_or_document"),
            (_good(people_prominent=True), "people prominent"),
            (_good(text_or_overlay=True), "text or overlay"),
            (_good(quality=2), "quality=2"),
            (_good(relevance=1), "relevance=1"),
            (_good(vertical_crop_ok=False), "subject lost in 9:16 crop"),
            (_good(), None),
        ],
    )
    def test_reject_reasons(self, verdict, reason):
        assert reject_reason(_cand("x", 1600, 1200, verdict), require_verdict=True) == reason

    def test_verdict_required_unless_running_without_vlm(self):
        c = _cand("x", 1600, 1200)
        assert reject_reason(c, require_verdict=True) == "no VLM verdict"
        assert reject_reason(c, require_verdict=False) is None
        assert reject_reason(_cand("p", 1598, 472), require_verdict=False) == "panorama"

    def test_score_prefers_relevance_then_quality_then_portrait(self):
        tall = _cand("t", 1600, 2115, _good(quality=4))
        wide = _cand("w", 1600, 960, _good(quality=4))
        better_wide = _cand("b", 1600, 960, _good(quality=5))
        relevant_wide = _cand("r", 1600, 960, _good(quality=3, relevance=5))
        assert score(tall) > score(wide)  # same verdict: portrait wins
        assert score(better_wide) > score(wide)  # quality breaks ties
        assert score(relevant_wide) > score(better_wide)  # relevance beats two quality points

    def test_order_by_narration_follows_the_card_text(self):
        text = "Built from polished dry-stone walls. Its Intihuatana stone tracks the sun."
        # hashes ≥ 7 bits apart so nothing counts as a pixel duplicate
        walls = _cand(
            "walls", 1600, 1200, _good("walls", 3, illustrates="dry-stone walls"), dh=0x7F
        )
        stone = _cand(
            "stone", 1600, 1200, _good("stone", 5, illustrates="Intihuatana stone"), dh=0x7F << 10
        )
        vista = _cand("vista", 1600, 1200, _good("vista", 4, illustrates=""), dh=0x7F << 20)
        kept, _ = select_stills([walls, stone, vista])
        assert [c.image["filename"] for c in kept] == ["stone", "vista", "walls"]  # score order
        ordered = order_by_narration(kept, text, lambda c: c.verdict)
        assert [c.image["filename"] for c in ordered] == ["walls", "stone", "vista"]

    def test_select_orders_by_score_and_drops_duplicates(self):
        cands = [
            _cand("map", 1600, 1362, _good(kind="map_or_document", subject="map"), dh=0x7F << 40),
            _cand("intihuatana_a", 1600, 1200, _good("Intihuatana stone", 4), dh=0x7F),
            _cand("intihuatana_b", 1600, 1200, _good("intihuatana stone", 5), dh=0x7F ^ 0b1),
            _cand("terraces", 1600, 1035, _good("Agricultural terraces", 4), dh=0x7F << 10),
            _cand("panorama", 1598, 472, _good("valley", 5), dh=0x7F << 20),
            _cand("windows", 1600, 1200, _good("Three Windows", 3), dh=0x7F << 30),
        ]
        kept, rejected = select_stills(cands)
        assert [c.image["filename"] for c in kept] == ["intihuatana_b", "terraces", "windows"]
        reasons = {c.image["filename"]: why for c, why in rejected}
        assert reasons["map"] == "kind=map_or_document"
        assert reasons["panorama"] == "panorama"
        assert reasons["intihuatana_a"].startswith("duplicate")

    def test_normalize_subject(self):
        assert normalize_subject(" Intihuatana Stone! ") == "intihuatana stone"


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
        assert site["orbit_zoom"] == 15.0  # Fortress/citadel

    def test_orbit_zoom_by_site_type(self):
        assert orbit_zoom_for("Stone circle") == 16.6
        assert orbit_zoom_for("Geoglyphs") == 13.5
        assert orbit_zoom_for("Something new") == 14.2
        assert orbit_zoom_for(None) == 14.2


def test_local_image_name_is_filesystem_safe_and_keeps_original_extension():
    assert local_image_name(3, "Machu Picchu (cropped) ü.jpg") == "03_Machu_Picchu_cropped.jpg"
    assert (
        local_image_name(3, "Machu_Picchu.webp", "https://upload.wikimedia.org/x/Machu_Picchu.JPG")
        == "03_Machu_Picchu.jpg"
    )


def _measurements(**over):
    m = {
        "width": 1080,
        "height": 1920,
        "fps": 60,
        "duration": 18.74,
        "narration_s": 15.12,
        "opening_frames": 358,
        "return_frames": 178,
        "return_s": 3.0,
        "luma_samples": [(0.0, 40.0), (0.25, 42.0), (6.0, 60.0)],
        "loop_seam": 1.1,
        "lufs": -14.3,
        "peak_dbfs": -1.4,
        "voice_start_db": -5.9,
        "name_at": 15.93,
        "name_window_db": -1.5,
        "tail_db": -91.0,
        "stills_kept": 8,
        "stills_rejected": 4,
        "stills_used": 3,
        "name_lines": 1,
    }
    m.update(over)
    return m


class TestAudit:
    def test_clean_short_passes_every_check(self):
        checks = evaluate(_measurements())
        assert passed(checks)
        assert {c.name for c in checks} >= {
            "duration",
            "no_black_frames",
            "loop_seam",
            "name_spoken",
        }

    def test_black_frames_and_missing_name_fail(self):
        checks = evaluate(
            _measurements(luma_samples=[(0.0, 40.0), (1.5, 8.0)], name_window_db=-30.0)
        )
        failed = {c.name for c in checks if not c.ok}
        assert failed == {"no_black_frames", "name_spoken"}

    def test_duration_expects_narration_tail_and_return(self):
        assert passed(evaluate(_measurements(duration=15.12 + 0.6 + 3.0)))
        assert not passed(evaluate(_measurements(duration=16.0)))
        # a longer return take (long spoken name) is expected in full
        assert passed(
            evaluate(_measurements(return_s=6.7, return_frames=400, duration=15.12 + 0.6 + 6.7))
        )
        # without a return clip the duration expectation drops the 3 s (the
        # missing clip itself still fails its own check)
        checks = evaluate(_measurements(return_frames=0, return_s=0.0, duration=15.72))
        assert next(c for c in checks if c.name == "duration").ok
        assert not next(c for c in checks if c.name == "return_clip").ok

    def test_loudness_peak_and_seam_thresholds(self):
        assert not passed(evaluate(_measurements(lufs=-17.0)))
        assert not passed(evaluate(_measurements(peak_dbfs=-0.3)))
        assert not passed(evaluate(_measurements(loop_seam=5.0)))
