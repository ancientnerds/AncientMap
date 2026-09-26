"""Pure-function tests for the site-shorts pipeline (no network, no ffmpeg, no VLM)."""

import hashlib
from pathlib import Path

import pytest
from PIL import ImageFont

from pipeline.video import shorts_audit
from pipeline.video.__main__ import music_start_default, sfx
from pipeline.video.media import ff_path
from pipeline.video.shorts_audit import (
    card_sha256,
    card_trace,
    evaluate,
    longest_frozen_run,
    passed,
    widest_word_px,
)
from pipeline.video.shorts_brand import FONT_HEADING, FONT_SOURCES, FONTS, missing_glyphs
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
    TEASER_NOTE,
    Segment,
    StillPick,
    build_comment,
    build_description,
    captions_filter,
    clip_filter,
    cut_stills,
    final_graph,
    flash_times,
    gain_db,
    hashtags,
    mix_graph,
    name_alpha,
    name_audio_at,
    name_layout,
    plan_timeline,
    pushin_filter,
    return_overlays_graph,
    segment_starts,
    stills_graph,
    stills_window,
    wrap_lines,
)
from pipeline.video.shorts_select import (
    Candidate,
    aspect_penalty,
    focus_of,
    image_title,
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
        assert f.endswith("s=1080x1920:fps=60,setsar=1,format=yuv420p")  # concat needs equal SARs

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
        assert len(lines) == 2 and size == 64
        lines, size, _ = name_layout("Archaeological Site of Olympia")
        assert lines == ["Archaeological Site", "of Olympia"] and size == 64  # not a lone "Olympia"
        lines, size, _ = name_layout("Senegambian Stone Circles")
        assert lines == ["Senegambian", "Stone Circles"] and size == 84

    def test_description_lists_every_image_with_license(self):
        site = {
            "name": "Machu Picchu",
            "country": "Peru",
            "card_text": "A citadel.",
            "card_ai": None,
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
        # A card without a teaser provenance claims no AI text (O10 marks the teaser cards).
        assert TEASER_NOTE not in text
        teaser = build_description({**site, "card_ai": "generated"}, imgs, "v")
        assert TEASER_NOTE in teaser
        assert teaser.index(TEASER_NOTE) < teaser.index("AI-generated voice")

    def test_hashtags_use_the_specific_place_and_skip_duplicates(self):
        tags = hashtags({"name": "Rano Raraku", "country": "Chile, Easter Island"})
        assert tags[-2:] == ["#EasterIsland", "#RanoRaraku"]
        assert specific_place("Chile, Easter Island") == "Easter Island"
        assert hashtags({"name": "Peru", "country": "Peru"}).count("#Peru") == 1

    def test_comment_asks_a_question_and_carries_the_site_link(self):
        c = build_comment({"name": "Machu Picchu", "page_path": "/sites/peru/machu-picchu-1"})
        assert c.startswith("Have you been to Machu Picchu?")
        assert "https://ancientnerds.com/sites/peru/machu-picchu-1" in c


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
            "[3:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,volume=-12.0dB,asplit=2[s0][s1]"
            in g
        )
        assert "[s0]adelay=6000:all=1[sd0]" in g and "[s1]adelay=8750:all=1[sd1]" in g
        assert (
            "[vm][md][sd0][sd1]amix=inputs=4:duration=longest:normalize=0,apad=whole_dur=19.500"
            in g
        )
        g = mix_graph(16.7, 19.5, flashes=[6.0])
        assert "[2:a]" in g and g.endswith(
            "[v][sd0]amix=inputs=2:duration=longest:normalize=0,apad=whole_dur=19.500,atrim=duration=19.500[a]"
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
        assert "borderw=3:bordercolor=black" in named and "box=1" not in named
        assert "text_align=center" in named  # every line centred, not the block only
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

    def test_a_photo_of_another_site_is_rejected(self):
        # the Puma Punku article carries Ollantaytambo and Delphi masonry as comparisons
        foreign = _cand("ollanta", 1600, 1200, _good("Ollantaytambo wall", 5), dh=0x7F << 5)
        foreign.verdict["other_site"] = True
        assert reject_reason(foreign, require_verdict=True) == "other site"
        assert image_title({"title": None, "filename": "Ollantaytambo_Monolithen.jpg"}) == (
            "Ollantaytambo Monolithen"
        )
        assert image_title({"title": "Puma Punku5", "filename": "x.jpg"}) == "Puma Punku5"

    def test_select_orders_by_score_and_drops_duplicates(self):
        cands = [
            _cand("map", 1600, 1362, _good(kind="map_or_document", subject="map"), dh=0x7F << 40),
            _cand("intihuatana_a", 1600, 1200, _good("Intihuatana stone", 4), dh=0x7F),
            _cand("intihuatana_b", 1600, 1200, _good("intihuatana stone", 5), dh=0x7F ^ 0b1),
            _cand("terraces", 1600, 1035, _good("Agricultural terraces", 4), dh=0x7F << 10),
            _cand("panorama", 1598, 472, _good("valley", 5), dh=0x7F << 20),
            _cand("windows", 1600, 1200, _good("Three Windows", 3), dh=0x7F << 30),
            _cand("tiny", 800, 533, _good("Dolmen", 5), dh=0x7F << 50),
        ]
        kept, rejected = select_stills(cands)
        assert [c.image["filename"] for c in kept] == ["intihuatana_b", "terraces", "windows"]
        reasons = {c.image["filename"]: why for c, why in rejected}
        assert reasons["map"] == "kind=map_or_document"
        assert reasons["tiny"] == "too small (800x533)"  # Commons originals can be thumbnails
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
            "card_text_sha256": None,
            "card_provenance": None,
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


#: A card and the hash its `_description_provenance` pins (S13), computed here with hashlib
#: rather than with the module's own helper, so a wrong helper cannot move the expectation.
CARD = "Machu Picchu is a 15th-century Inca citadel at 2,430 metres."
CARD_SHA = hashlib.sha256(CARD.encode("utf-8")).hexdigest()

#: One `_SITE_SQL` row, as the export reads it; a card without card provenance.
_EXPORT_ROW = {
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
    "card_text_sha256": None,
    "card_provenance": None,
}


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
        "widest_caption": "Intihuatana",
        "max_caption_w": 640,
        "flag": "pe",
        "flag_exists": True,
        "heading_font": "orbitron-700.ttf",
        "missing_glyphs": [],
        "return_needed_s": 2.55,
        "min_still_s": 3.44,
        "frozen_run": 6,
        "card_words": 27,
        "caption_words": 27,
        "captions_end": 15.1,
        "card_sha256": CARD_SHA,
        "card_provenance_sha256": CARD_SHA,
    }
    m.update(over)
    return m


class TestReturnOverlays:
    def test_flag_fades_with_the_name_and_sits_under_it(self):
        g = return_overlays_graph(3.0, name_lines=1, line_h=100)
        assert g.startswith("[1:v]format=rgba,scale=180:-1,fade=t=in:st=0:d=0.3:alpha=1,")
        assert "fade=t=out:st=2.350:d=0.5:alpha=1[flag]" in g
        assert g.endswith("[base][flag]overlay=x=(W-w)/2:y=942:shortest=1[out]")  # 770 + 100 + 72


class TestAudit:
    def test_new_elements_have_checks(self):
        names = {c.name for c in evaluate(_measurements())}
        assert {"captions_fit", "flag_present", "return_covers_name", "stills_pace"} <= names
        assert passed(evaluate(_measurements()))
        assert not passed(evaluate(_measurements(max_caption_w=1010)))
        assert not passed(evaluate(_measurements(flag_exists=False)))
        assert not passed(evaluate(_measurements(missing_glyphs=["\u015f"])))
        assert not passed(evaluate(_measurements(return_s=3.0, return_needed_s=3.4)))
        assert not passed(evaluate(_measurements(min_still_s=1.9)))
        assert not passed(evaluate(_measurements(frozen_run=24)))  # recorder stalled

    def test_longest_frozen_run(self):
        assert longest_frozen_run([1.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0]) == 3
        assert longest_frozen_run([0.0] * 5 + [2.0]) == 5
        assert longest_frozen_run([0.5, 0.6, 0.7]) == 0
        assert longest_frozen_run([]) == 0

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


# S13: the narrated card is the card its `_description_provenance` pins (Phase 5).


def test_s13_the_card_hash_is_the_provenance_form():
    assert card_sha256(CARD) == CARD_SHA
    assert card_sha256("Ávila") == hashlib.sha256("Ávila".encode()).hexdigest()


def test_s13_a_card_its_provenance_pins_passes():
    checks = {c.name: c.ok for c in evaluate(_measurements())}
    assert checks["card_traced"] is True


def test_s13_a_card_that_is_not_the_pinned_one_fails():
    other = card_sha256(CARD + " ")  # one byte off: the file was edited after the write
    checks = evaluate(_measurements(card_sha256=other))
    assert not passed(checks)
    assert {c.name for c in checks if not c.ok} == {"card_traced"}


def test_s13_a_card_without_card_provenance_is_not_shorts_eligible():
    """A held card, or one written before Phase 5, carries no pinned hash."""
    checks = evaluate(_measurements(card_provenance_sha256=None))
    failed = [c for c in checks if not c.ok]
    assert [c.name for c in failed] == ["card_traced"]
    assert "carries no card" in failed[0].value


def test_s13_the_card_is_measured_from_the_narrated_text_and_the_pin_from_the_provenance():
    """The two S13 inputs `measure_site` reads out of site.json: the hash of the card the short
    narrates, and the hash its provenance pins. Taking either from the other side would make S13
    pass every card that has any pin."""
    pinned = card_sha256(CARD + " ")  # the card was edited after the write
    trace = card_trace({"card_text": CARD, "card_text_sha256": pinned})
    assert trace == {"card_sha256": CARD_SHA, "card_provenance_sha256": pinned}
    checks = evaluate(_measurements(**trace))
    assert {c.name for c in checks if not c.ok} == {"card_traced"}
    held = card_trace({"card_text": CARD, "card_text_sha256": None})
    assert held == {"card_sha256": CARD_SHA, "card_provenance_sha256": None}


def test_s13_the_audit_measures_the_card_through_card_trace():
    """`measure_site` needs a rendered short (ffprobe, the mp4), so its wiring is read from its
    source: the S13 fields of the dict it returns are exactly `card_trace(site)`."""
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(shorts_audit.measure_site)))
    returned = [node.value for node in ast.walk(tree) if isinstance(node, ast.Return)]
    assert len(returned) == 1 and isinstance(returned[0], ast.Dict)
    spreads = [v for k, v in zip(returned[0].keys, returned[0].values, strict=True) if k is None]
    assert [ast.unparse(v) for v in spreads] == ["card_trace(site)"]
    keys = {k.value for k in returned[0].keys if isinstance(k, ast.Constant)}
    assert not keys & {"card_sha256", "card_provenance_sha256"}


def test_s13_the_export_carries_the_pinned_hash_into_site_json():
    row = dict(_EXPORT_ROW, card_text_sha256=CARD_SHA)
    assert assemble_site(row, [])["card_text_sha256"] == CARD_SHA
    assert assemble_site(dict(_EXPORT_ROW), [])["card_text_sha256"] is None


def test_s13_the_export_reads_the_hash_from_the_card_provenance():
    from pipeline.video.shorts_export import _SITE_SQL

    sql = " ".join(str(_SITE_SQL).split())
    assert (
        "s.raw_data -> '_description_provenance' -> 'card' ->> 'text_sha256' "
        "AS card_text_sha256" in sql
    )
    assert "s.raw_data -> '_card_provenance' AS card_provenance" in sql


def _teaser_row(**over):
    from pipeline.utils import card_provenance as CP

    description = "Machu Picchu is a 15th-century Inca citadel at 2,430 metres."
    row = dict(_EXPORT_ROW, description=description, card_description=CARD)
    row["card_provenance"] = CP.build(
        run="wb-test",
        ai_system="Claude Opus (Anthropic)",
        card=CARD,
        description=description,
        stage="check",
        checker="teaser-check-b001",
        checked_at="2026-09-26T12:00:00+00:00",
        claims=[{"claim": "a 15th-century Inca citadel", "support": ["S1"]}],
    )
    return {**row, **over}


def test_s13_a_teaser_card_is_pinned_by_its_own_provenance_and_marked_generated():
    """Lane WB: the teaser provenance is the card's only statement - its hash (not the Phase-5
    key, which the lane nulls) goes to S13, and the AI note is claimed for the card."""
    site = assemble_site(_teaser_row(card_text_sha256="f" * 64), [])
    assert site["card_text_sha256"] == CARD_SHA
    assert site["card_ai"] == "generated"
    checks = {c.name: c.ok for c in evaluate(_measurements(**card_trace(site)))}
    assert checks["card_traced"] is True


def test_s13_a_stale_teaser_card_is_not_narrated_but_stays_marked():
    """The description changed since the card was checked against it: still AI text, no pin."""
    site = assemble_site(_teaser_row(description="An edited description."), [])
    assert site["card_text_sha256"] is None
    assert site["card_ai"] == "generated"
    failed = [c for c in evaluate(_measurements(**card_trace(site))) if not c.ok]
    assert [c.name for c in failed] == ["card_traced"]


def test_s13_a_card_the_teaser_provenance_does_not_hash_fails_and_is_not_marked():
    site = assemble_site(_teaser_row(card_description="Another card."), [])
    assert site["card_ai"] is None
    failed = [c for c in evaluate(_measurements(**card_trace(site))) if not c.ok]
    assert [c.name for c in failed] == ["card_traced"]


#: A real FreeType face (Pillow's own) at the caption size, for the width tests.
CAPTION_FACE = ImageFont.load_default(size=shorts_audit.CAPTION_SIZE)


# S3 and the Phase-4 card check (V10) measure a caption word with one function.


def test_the_widest_word_is_measured_as_shown_with_its_outline():
    word, px = widest_word_px(["An", "Intihuatana,", "stone"], CAPTION_FACE)
    assert word == "Intihuatana"  # the trailing comma is not drawn
    expected = int(CAPTION_FACE.getlength("Intihuatana")) + 2 * shorts_audit.CAPTION_BORDER
    assert px == expected


def test_a_punctuation_only_token_has_no_width():
    assert widest_word_px(["-", "—"], CAPTION_FACE) == ("", 0)


def test_the_caption_audit_measures_through_the_public_helper(monkeypatch):
    seen = []

    def spy(words, font):
        seen.append((list(words), font))
        return "x", 7

    monkeypatch.setattr(shorts_audit, "widest_word_px", spy)
    monkeypatch.setattr(shorts_audit, "caption_font", lambda path: CAPTION_FACE)
    got = shorts_audit._widest_caption([{"text": "Inca"}, {"text": "citadel."}], Path("f"))
    assert got == ("x", 7)
    assert seen == [(["Inca", "citadel."], CAPTION_FACE)]


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
        assert assemble_site(dict(_EXPORT_ROW), [])["country_code"] == "PE"

    def test_mix_graph_with_music_loops_fades_and_stays_silent_at_the_loop_point(self):
        g = mix_graph(16.7, 19.5, music=True)
        assert g.count("amix=inputs=2") == 2  # voices, then voices + ducked music
        assert "atrim=duration=19.200" in g  # music stops 0.3 s before the end
        assert "afade=t=in:st=0:d=1.0" in g and "afade=t=out:st=16.200:d=3.0" in g
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

    def test_words_never_overlap_in_time(self):
        heard = [("a", 0.0, 0.05), ("b", 0.05, 0.1), ("c", 0.4, 0.9)]
        words = align_words(["a", "b", "c"], heard)
        assert words[0].end <= words[1].start and words[1].end <= words[2].start
        assert (
            words[2].end - words[2].start >= 0.12
        )  # the minimum still applies where there is room
        assert words[1].end == 0.17  # min duration, but never past the next start
        same = align_words(["century", "BC."], [("century", 5.92, 6.04), ("BC.", 5.92, 6.18)])
        assert same[0].start < same[0].end <= same[1].start  # identical whisper starts pulled apart

    def test_needs_recognised_words(self):
        with pytest.raises(ValueError):
            align_words(["a"], [])

    @pytest.mark.skipif(
        not FONT_HEADING.exists(),
        reason="video-assets/fonts is gitignored; ensure_fonts() fills it on the render "
        "machine only. captions_filter measures the glyphs, so without the file these "
        "two blocked every deploy (CI 2026-09-17)",
    )
    def test_captions_filter_one_drawtext_per_word(self, tmp_path):
        f = captions_filter([Word("Inca", 1.22, 1.72), Word("citadel", 1.72, 2.16)], tmp_path)
        assert f.count("drawtext=") == 2
        assert "enable='gte(t\\,1.220)*lt(t\\,1.720)'" in f  # half-open: never two words at once
        assert "y_align=baseline:y=" in f and "x=(w-text_w)/2" in f
        assert (tmp_path / "w001.txt").read_text(encoding="utf-8") == "citadel"
        assert f.count("fontcolor=white") == 2
        assert f.count("borderw=5:bordercolor=black") == 2 and "box=" not in f

    @pytest.mark.skipif(
        not FONT_HEADING.exists(),
        reason="video-assets/fonts is gitignored; ensure_fonts() fills it on the render "
        "machine only. captions_filter measures the glyphs, so without the file these "
        "two blocked every deploy (CI 2026-09-17)",
    )
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


class TestBrandFonts:
    def test_every_video_font_has_a_source(self):
        for source, weight in FONTS.values():
            assert source in FONT_SOURCES and 100 <= weight <= 900

    def test_missing_glyphs_lists_what_the_font_cannot_draw(self):
        cmap = {ord(c) for c in "Karatepe-Aslnt "}
        assert missing_glyphs("Karatepe-Aslanta\u015f", cmap) == ["\u015f"]
        assert missing_glyphs("Karatepe", cmap) == []


class TestMusicStart:
    def test_sidecar_sets_the_offset(self, tmp_path):
        assert music_start_default(tmp_path) == 0.0
        (tmp_path / "music.json").write_text('{"start_s": 25}', encoding="utf-8")
        assert music_start_default(tmp_path) == 25.0


class TestWhoosh:
    def test_whoosh_follows_the_flash_input(self):
        g = mix_graph(16.7, 19.5, music=True, flashes=[6.0], whooshes=[1.0, 17.0])
        assert "[3:a]aformat" in g
        assert (
            "[4:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,volume=-14.0dB,asplit=2[w0][w1]"
            in g
        )
        assert "[w1]adelay=17000:all=1[wd1]" in g
        assert "[vm][md][sd0][wd0][wd1]amix=inputs=5" in g
        g = mix_graph(16.7, 19.5, whooshes=[1.0])  # no music, no flash: the whoosh is input 2
        assert "[2:a]aformat" in g and "[v][wd0]amix=inputs=2" in g


class TestSfxLookup:
    def test_named_effects_in_the_sfx_folder(self, tmp_path):
        assert sfx("flash", tmp_path) is None
        (tmp_path / "flash.wav").write_bytes(b"")
        (tmp_path / "whoosh.mp3").write_bytes(b"")
        (tmp_path / "notes.txt").write_text("x")
        assert sfx("flash", tmp_path) == tmp_path / "flash.wav"
        assert sfx("whoosh", tmp_path) == tmp_path / "whoosh.mp3"
