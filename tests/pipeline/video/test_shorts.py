"""Pure-function tests for the site-shorts pipeline (no network, no ffmpeg, no VLM)."""

from pathlib import Path

import pytest

from pipeline.video.media import ff_path
from pipeline.video.shorts_audit import evaluate, passed
from pipeline.video.shorts_captions import Word, align_words, display_text, spoken_at, srt_text
from pipeline.video.shorts_export import (
    RARITY_NAMES,
    assemble_site,
    country_code_for,
    orbit_zoom_for,
)
from pipeline.video.shorts_images import local_image_name
from pipeline.video.shorts_render import (
    NAME_AUDIO_DELAY_S,
    NARRATION_TAIL_S,
    Segment,
    StillPick,
    build_comment,
    build_description,
    captions_filter,
    chip_text,
    clip_filter,
    cut_stills,
    final_graph,
    flag_overlay_graph,
    flash_times,
    gain_db,
    hashtags,
    info_alpha,
    info_filter,
    mix_graph,
    name_alpha,
    name_audio_at,
    name_layout,
    plan_timeline,
    pushin_filter,
    stills_graph,
    stills_window,
    wrap_lines,
)
from pipeline.video.shorts_select import (
    Candidate,
    aspect_penalty,
    focus_of,
    is_panorama,
    normalize_subject,
    reject_reason,
    score,
    select_stills,
)
from pipeline.video.shorts_tts import specific_place, spoken_name

CUTS = [("a.jpg", 2.75), ("b.jpg", 2.75), ("c.jpg", 2.75), ("d.jpg", 2.75)]
OPENING = (Path("short-opening.mp4"), 6.0)
RETURN = (Path("short-return.mp4"), 3.0)


def _total(segments):
    return sum(s.duration for s in segments)


class TestPlanTimeline:
    def test_loop_cut_opening_stills_return(self):
        segs = plan_timeline(narration_s=16.4, cuts=CUTS, opening=OPENING, closing=RETURN)
        kinds = [s.kind for s in segs]
        # 17.0 s narration span: 6 s opening, 11 s of stills, then the return
        assert kinds == ["clip", "still", "still", "still", "still", "return"]
        assert segs[0].duration == 6.0 and segs[0].start == 0.0
        assert segs[1].duration == 2.75
        assert [s.source for s in segs[1:5]] == ["a.jpg", "b.jpg", "c.jpg", "d.jpg"]
        assert segs[-1].duration == 3.0  # never shortened: its last frame is the loop point
        assert _total(segs) == pytest.approx(17.0 + 3.0)

    def test_name_audio_starts_shortly_into_the_return_clip(self):
        segs = plan_timeline(narration_s=16.4, cuts=CUTS, opening=OPENING, closing=RETURN)
        assert name_audio_at(segs, name_s=1.5) == pytest.approx(17.0 + NAME_AUDIO_DELAY_S)

    def test_without_return_clip_name_audio_follows_the_stills(self):
        segs = plan_timeline(
            narration_s=6.0, cuts=[("a.jpg", 3.3), ("b.jpg", 3.3)], opening=None, closing=None
        )
        assert [s.kind for s in segs] == ["still", "still"]
        assert name_audio_at(segs, name_s=0.5) == pytest.approx(6.6 - 0.5 - 0.15)

    def test_stills_window_follows_the_opening(self):
        assert stills_window(16.4, 6.0) == (6.0, 17.0)
        assert stills_window(6.0, None) == (0.0, 6.6)
        assert stills_window(5.0, 9.0) == (5.6, 5.6)  # long opening capped at the span
        assert stills_window(5.0, 5.2) == (5.2, 5.2)  # deficit within the slack absorbed

    def test_long_opening_is_capped_at_the_narration_span(self):
        segs = plan_timeline(narration_s=5.0, cuts=[], opening=(Path("o.mp4"), 9.0), closing=None)
        assert [s.kind for s in segs] == ["clip"]
        assert segs[0].duration == pytest.approx(5.0 + NARRATION_TAIL_S)

    def test_requires_stills_that_fill_the_window(self):
        with pytest.raises(ValueError):
            plan_timeline(narration_s=5.0, cuts=[], opening=None, closing=None)
        with pytest.raises(ValueError):
            plan_timeline(narration_s=5.0, cuts=[("a.jpg", 2.0)], opening=None, closing=None)


class TestCutStills:
    def test_opens_with_the_best_due_still_and_cuts_on_the_spoken_word(self):
        # Machu Picchu: window 6.0–16.3; "built from polished…" spoken at 5.5,
        # "Its Intihuatana stone" at 9.6, the first sentence at 0.0, one still unplaced
        picks = [
            StillPick("windows.jpg", 17.3, anchor=5.5),
            StillPick("stone.jpg", 17.3, anchor=9.6),
            StillPick("triumph.jpg", 16.8, anchor=0.0),
            StillPick("old.jpg", 8.4, anchor=None),
        ]
        cuts = cut_stills(6.0, 16.3, picks)
        assert [p for p, _ in cuts] == ["windows.jpg", "stone.jpg", "triumph.jpg"]
        assert cuts[0][1] == pytest.approx(3.4)  # stone cuts in at 9.4 = 0.2 s before its word
        assert sum(d for _, d in cuts) == pytest.approx(10.3)
        assert min(d for _, d in cuts) >= 2.2

    def test_a_still_never_cuts_in_sooner_than_the_minimum(self):
        picks = [
            StillPick("a.jpg", 5, anchor=3.0),
            StillPick("b.jpg", 4, anchor=3.5),
            StillPick("c.jpg", 3, anchor=None),
        ]
        cuts = cut_stills(0.0, 10.0, picks)
        assert [p for p, _ in cuts] == ["c.jpg", "a.jpg", "b.jpg"]
        assert cuts[0][1] == pytest.approx(2.8)  # a at its word
        assert cuts[1][1] == pytest.approx(3.6)  # b too close to a: placed as a filler, mid-gap
        assert min(d for _, d in cuts) >= 2.2

    def test_a_little_late_is_accepted(self):
        picks = [
            StillPick("x.jpg", 9, anchor=None),
            StillPick("a.jpg", 5, anchor=3.0),
            StillPick("b.jpg", 4, anchor=4.5),
        ]
        cuts = cut_stills(0.0, 10.0, picks)
        # b wants 4.3 but a cut in at 2.8: pushed 0.7 s to 5.0, within the tolerance
        assert cuts == [
            ("x.jpg", pytest.approx(2.8)),
            ("a.jpg", pytest.approx(2.2)),
            ("b.jpg", pytest.approx(5.0)),
        ]

    def test_without_due_stills_the_earliest_word_opens(self):
        picks = [StillPick("a.jpg", 5, anchor=3.0), StillPick("b.jpg", 9, anchor=4.6)]
        cuts = cut_stills(0.0, 10.0, picks)
        assert cuts == [("a.jpg", pytest.approx(4.4)), ("b.jpg", pytest.approx(5.6))]

    def test_a_word_too_near_the_end_becomes_a_filler(self):
        picks = [StillPick("x.jpg", 9, anchor=None), StillPick("z.jpg", 5, anchor=9.5)]
        cuts = cut_stills(0.0, 10.0, picks)
        assert cuts == [("x.jpg", pytest.approx(5.0)), ("z.jpg", pytest.approx(5.0))]

    def test_fillers_stop_when_no_gap_holds_two_minimum_stills(self):
        picks = [StillPick(f"{i}.jpg", 10 - i, anchor=None) for i in range(8)]
        cuts = cut_stills(0.0, 10.3, picks)
        assert len(cuts) == 4  # 10.3 → 2 × 5.15 → 4 × 2.575; no gap ≥ 4.4 is left
        assert min(d for _, d in cuts) >= 2.2

    def test_single_and_empty(self):
        assert cut_stills(0.0, 4.0, [StillPick("a.jpg", 1)]) == [("a.jpg", 4.0)]
        assert cut_stills(5.0, 5.0, [StillPick("a.jpg", 1)]) == []
        with pytest.raises(ValueError):
            cut_stills(0.0, 4.0, [])


class TestStillsGraph:
    def test_stills_are_hard_cut_in_order(self):
        graph = stills_graph([2.75, 2.75, 2.75])
        assert graph.count("zoompan=") == 3
        assert graph.endswith(";[v0][v1][v2]concat=n=3:v=1:a=0[out]")
        assert "xfade" not in graph

    def test_single_still_has_no_concat(self):
        graph = stills_graph([4.0])
        assert "concat" not in graph and graph.endswith("[out]")

    def test_stills_alternate_push_in_and_push_out(self):
        graph = stills_graph([2.75, 2.75, 2.75])
        v0, v1, v2 = graph.split(";")[:3]
        assert "z='1+0.06*on/165':d=165" in v0 and "z='1+0.06*on/165':d=165" in v2
        assert "z='1+0.06*(1-on/165)':d=165" in v1

    def test_pushin_zooms_from_100_to_106_percent_on_a_supersampled_still(self):
        f = pushin_filter(2.75)
        assert f.startswith("scale=4320:7680:force_original_aspect_ratio=increase,crop=4320:7680:")
        assert "x='min(max(iw*0.500-2160\\,0)\\,iw-4320)'" in f  # centred by default
        assert "zoompan=z='1+0.06*on/165':d=165:" in f
        assert f.endswith("s=1080x1920:fps=60,format=yuv420p")

    def test_pushin_crops_around_the_focal_point(self):
        f = pushin_filter(2.75, focus=(0.8, 0.3))
        assert "x='min(max(iw*0.800-2160\\,0)\\,iw-4320)'" in f
        assert "y='min(max(ih*0.300-3840\\,0)\\,ih-7680)'" in f

    def test_focus_of_defaults_and_clamps(self):
        assert focus_of(None) == (0.5, 0.5)
        assert focus_of({"focus": {"x": 1.4, "y": -0.2}}) == (1.0, 0.0)
        assert focus_of({"focus": "left"}) == (0.5, 0.5)
        assert focus_of({"focus": {"x": 0.25, "y": 0.75}}) == (0.25, 0.75)


class TestText:
    def test_wrap_lines_splits_long_names(self):
        lines = wrap_lines("Gochang, Hwasun and Ganghwa Dolmen Sites")
        assert len(lines) >= 3
        assert all(len(line) <= 14 for line in lines)

    def test_wrap_lines_short_name_single_line(self):
        assert wrap_lines("Machu Picchu") == ["Machu Picchu"]

    def test_long_spoken_name_starts_early_enough_to_end_before_the_loop_point(self):
        segs = plan_timeline(narration_s=16.4, cuts=CUTS, opening=OPENING, closing=RETURN)
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
        assert text.rstrip().endswith("#Shorts #archaeology #ancienthistory #Peru #MachuPicchu")
        assert "Mapbox" not in build_description(site, imgs, "v")

    def test_hashtags_use_the_specific_place_and_skip_duplicates(self):
        tags = hashtags({"name": "Rano Raraku", "country": "Chile, Easter Island"})
        assert tags[-2:] == ["#EasterIsland", "#RanoRaraku"]
        assert specific_place("Chile, Easter Island") == "Easter Island"
        assert hashtags({"name": "Peru", "country": "Peru"}).count("#Peru") == 1

    def test_comment_asks_a_question_and_carries_the_site_link(self):
        c = build_comment({"name": "Machu Picchu", "page_path": "/sites/peru/machu-picchu-1"})
        assert c.startswith("Have you been to Machu Picchu?")
        assert "https://ancientnerds.com/sites/peru/machu-picchu-1" in c

    def test_chip_drops_the_country_and_empty_fields(self):
        site = {"civilization": "Peru", "country": "Peru", "period_name": "1000 - 1500 AD"}
        assert chip_text({**site, "site_type": "Fortress/citadel"}) == (
            "1000 - 1500 AD · Fortress/citadel"
        )
        assert chip_text({**site, "civilization": "Inca", "site_type": None}) == (
            "Inca · 1000 - 1500 AD"
        )
        assert chip_text({"country": "Peru"}) == ""


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
        assert "adelay=16700:all=1," in g and "[d1]" in g
        assert g.endswith("apad=whole_dur=19.500,atrim=duration=19.500[a]")
        assert "loudnorm" not in g and "afir" not in g and "aecho" not in g

    def test_music_is_ducked_under_the_voice(self):
        g = mix_graph(16.7, 19.5, music=True)
        assert "[v]apad=whole_dur=19.500,asplit[vm][vsc]" in g
        assert "[m][vsc]sidechaincompress=threshold=0.04:ratio=2" in g
        assert "volume=-8.0dB[m]" in g
        assert g.endswith(
            "[vm][md]amix=inputs=2:duration=longest:normalize=0,apad=whole_dur=19.500,atrim=duration=19.500[a]"
        )
        assert "sidechaincompress" not in mix_graph(16.7, 19.5)

    def test_flash_sound_is_copied_to_every_still_start(self):
        g = mix_graph(16.7, 19.5, music=True, flashes=[6.0, 8.75])
        assert (
            "[3:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,volume=-6.0dB,asplit=2[s0][s1]"
            in g
        )
        assert "[s0]adelay=6000:all=1[k0]" in g and "[s1]adelay=8750:all=1[k1]" in g
        assert (
            "[vm][md][k0][k1]amix=inputs=4:duration=longest:normalize=0,apad=whole_dur=19.500" in g
        )
        g = mix_graph(16.7, 19.5, flashes=[6.0])
        assert "[2:a]" in g and g.endswith(
            "[v][k0]amix=inputs=2:duration=longest:normalize=0,apad=whole_dur=19.500,atrim=duration=19.500[a]"
        )

    def test_flash_times_are_the_still_starts(self):
        segs = plan_timeline(narration_s=16.4, cuts=CUTS, opening=OPENING, closing=RETURN)
        assert flash_times(segs) == [6.0, 8.75, 11.5, 14.25]

    def test_flash_times_sit_on_the_rendered_frame(self):
        # the trimmed 5.983 s opening came out as 358 frames (not 359), a 3.44 s
        # still is exactly 206: the second still starts at frame 564, not at 9.423 s
        segs = [
            Segment("clip", 5.983, "o"),
            Segment("still", 3.44, "a"),
            Segment("still", 3.44, "b"),
            Segment("return", 3.0, "r"),
        ]
        assert flash_times(segs, clip_frames=[358]) == pytest.approx([358 / 60, 564 / 60])
        assert flash_times(segs) == pytest.approx([359 / 60, 565 / 60])  # planned counts

    def test_final_graph_flashes_white_at_every_still_start(self):
        g = final_graph(0.0, "drawtext=x", [5.98, 9.42])
        assert g.startswith("[0:v]eq=saturation=0.78")
        assert (
            "[g0];color=c=white@0.85:s=1080x1920:r=60:d=0.28,format=rgba,fade=t=out:st=0:d=0.28:alpha=1,setpts=PTS+5.980/TB[f0];"
            in g
        )
        assert "[g0][f0]overlay=eof_action=pass:enable='between(t\\,5.972\\,6.252)'[g1];" in g
        assert (
            "[g1][f1]overlay=eof_action=pass:enable='between(t\\,9.412\\,9.692)',drawtext=x[vout];"
            in g
        )

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
        "card_words": 27,
        "caption_words": 27,
        "captions_end": 15.1,
    }
    m.update(over)
    return m


class TestAudit:
    def test_captions_must_cover_every_card_word_and_end_before_the_name(self):
        assert passed(evaluate(_measurements()))
        short = {c.name: c.ok for c in evaluate(_measurements(caption_words=26))}
        assert short["captions_timed"] is False
        late = {c.name: c.ok for c in evaluate(_measurements(captions_end=16.2))}
        assert late["captions_timed"] is False

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


class TestSpokenName:
    def test_site_and_country(self):
        assert spoken_name("Machu Picchu", "Peru") == "Machu Picchu, Peru."
        assert spoken_name("Stonehenge", "England") == "Stonehenge, England."

    def test_specific_part_of_a_compound_country(self):
        assert spoken_name("Rano Raraku", "Chile, Easter Island") == "Rano Raraku, Easter Island."

    def test_no_repetition_and_no_country(self):
        assert spoken_name("Temple of Egypt", "Egypt") == "Temple of Egypt."
        assert spoken_name("Atlantis", None) == "Atlantis."


class TestFlagAndMusic:
    def test_country_code_mirrors_the_frontend_mapping(self):
        assert country_code_for("Peru") == "PE"
        assert country_code_for("england") == "GB"
        assert (
            country_code_for("Chile, Easter Island") == "CL"
        )  # first part; the frontend gives None
        assert country_code_for("Atlantis") is None
        assert country_code_for(None) is None

    def test_site_json_carries_the_country_code(self):
        row = {
            "id": "12345678-aaaa-bbbb-cccc-1234567890ab",
            "name": "X",
            "country": "Peru",
            "lat": 0.0,
            "lon": 0.0,
            "site_type": "Tomb",
            "period_name": None,
            "description": "",
            "card_description": "c",
            "rarity_tier": 3,
            "rarity_score": 1,
            "total_power": 1,
            "antiquity": 0,
            "fortification": 0,
            "cultural_influence": 0,
            "mystery": 0,
            "legacy": 0,
            "civilization": None,
        }
        assert assemble_site(row, [])["country_code"] == "PE"

    def test_flag_fades_with_the_name_and_sits_under_it(self):
        g = flag_overlay_graph(3.0, name_lines=1, line_h=100)
        assert g.startswith("[1:v]format=rgba,scale=180:-1,fade=t=in:st=0:d=0.3:alpha=1")
        assert "fade=t=out:st=2.350:d=0.5:alpha=1[flag]" in g
        assert g.endswith("overlay=x=(W-w)/2:y=904:shortest=1[out]")  # (1920-100)//2-140 + 100 + 34

    def test_mix_graph_with_music_loops_fades_and_stays_silent_at_the_loop_point(self):
        g = mix_graph(16.7, 19.5, music=True)
        assert g.count("amix=inputs=2") == 2  # voices, then voices + ducked music
        assert "atrim=duration=19.200" in g  # music stops 0.3 s before the end
        assert "afade=t=in:st=0:d=1.0" in g and "afade=t=out:st=18.000:d=1.2" in g
        assert mix_graph(16.7, 19.5).count("amix=inputs=2") == 1


class TestCaptions:
    def test_matching_words_take_the_heard_times(self):
        heard = [
            ("A", 0.0, 0.26),
            ("15th", 0.26, 0.84),
            ("century", 0.84, 1.22),
            ("Inca", 1.22, 1.72),
        ]
        words = align_words("A 15th-century Inca".split(), heard)
        # "15th-century" is one display token but two heard words → interpolated over both
        assert [w.text for w in words] == ["A", "15th-century", "Inca"]
        assert words[0].start == 0.0 and words[0].end == 0.26
        assert words[2].start == 1.22 and words[2].end == 1.72
        assert words[1].start == 0.26 and words[1].end == 1.22

    def test_numbers_and_punctuation_match_by_key(self):
        heard = [
            ("at", 2.16, 2.64),
            ("2", 2.64, 2.96),
            (",430", 2.96, 4.22),
            ("metres,", 4.22, 5.06),
        ]
        words = align_words("at 2,430 metres,".split(), heard)
        assert words[0].start == 2.16
        assert words[1].start == 2.64 and words[1].end == 4.22  # "2" + ",430" span
        assert words[2].start == 4.22 and words[2].end == 5.06

    def test_misheard_word_with_same_count_is_paired(self):
        heard = [("built", 5.5, 5.8), ("frum", 5.8, 6.1), ("polished", 6.1, 6.6)]
        words = align_words("built from polished".split(), heard)
        assert words[1].start == 5.8 and words[1].end == 6.1

    def test_every_word_has_a_minimum_duration_and_order(self):
        heard = [("a", 0.0, 0.05), ("b", 0.05, 0.1)]
        words = align_words(["a", "b"], heard)
        assert all(w.end - w.start >= 0.12 for w in words)
        assert words[0].start <= words[1].start

    def test_needs_recognised_words(self):
        with pytest.raises(ValueError):
            align_words(["a"], [])

    def test_captions_filter_one_drawtext_per_word(self, tmp_path):
        f = captions_filter([Word("Inca", 1.22, 1.72), Word("citadel", 1.72, 2.16)], tmp_path)
        assert f.count("drawtext=") == 2
        assert "enable='between(t\\,1.220\\,1.720)'" in f
        assert (tmp_path / "w001.txt").read_text(encoding="utf-8") == "citadel"
        assert f.count("fontcolor=white") == 2

    def test_captions_drop_edge_punctuation_but_keep_inner_marks(self, tmp_path):
        assert display_text("mortar.") == "mortar"
        assert display_text("metres,") == "metres"
        assert display_text("2,430") == "2,430"
        assert display_text("15th-century") == "15th-century"
        assert display_text("\u201cInca\u201d") == "Inca"
        words = [Word("walls", 0.0, 0.3), Word("\u2014", 0.3, 0.5), Word("mortar.", 0.5, 1.0)]
        f = captions_filter(words, tmp_path)
        assert f.count("drawtext=") == 2  # the lone dash gets no caption
        assert (tmp_path / "w002.txt").read_text(encoding="utf-8") == "mortar"

    def test_info_overlay_fades_in_and_out_inside_its_window(self, tmp_path):
        a = info_alpha(6.0, 16.4)
        assert a.startswith("if(lt(t\\,6.000)\\,0\\,")
        assert "(t-6.000)/0.4" in a and "(16.400-t)/0.4" in a
        f = info_filter(tmp_path / "chip.txt", tmp_path / "f.ttf", 6.0, 16.4)
        assert "enable='between(t\\,6.000\\,16.400)'" in f and "y=170" in f


class TestSpokenAndSrt:
    WORDS = [
        Word("A", 0.0, 0.2),
        Word("big", 0.2, 0.5),
        Word("Inca", 0.5, 0.9),
        Word("citadel.", 0.9, 1.4),
        Word("Its", 1.6, 1.8),
        Word("stone", 1.8, 2.3),
        Word("tracks", 2.3, 2.7),
        Word("the", 2.7, 2.8),
        Word("sun.", 2.8, 3.2),
    ]
    TEXT = "A big Inca citadel. Its stone tracks the sun."

    def test_spoken_at_finds_the_phrase_start(self):
        assert spoken_at(self.TEXT, "Inca citadel", self.WORDS) == 0.5
        assert spoken_at(self.TEXT, "its stone tracks the sun.", self.WORDS) == 1.6
        assert spoken_at(self.TEXT, "", self.WORDS) is None
        assert spoken_at(self.TEXT, "temple", self.WORDS) is None
        assert spoken_at(self.TEXT, "ig Inca", self.WORDS) == 0.2  # inside a token

    def test_srt_cues_break_at_sentence_ends_and_six_words(self):
        srt = srt_text(self.WORDS)
        blocks = srt.strip().split("\n\n")
        assert len(blocks) == 2
        assert blocks[0] == "1\n00:00:00,000 --> 00:00:01,400\nA big Inca citadel."
        assert blocks[1].endswith("Its stone tracks the sun.")
        assert srt_text([Word(str(i), i, i + 1) for i in range(7)]).count("-->") == 2
