from __future__ import annotations

from pipeline.studio import casefile, glyphs, render_audit, script
from pipeline.studio.blocks import load_registry
from tests.pipeline.studio import episode_fixtures as ef
from tests.pipeline.studio import script_fixtures as sf

GLYPH_ERROR = "has no glyph in the brand fonts (latin and latin-ext only)"
CREDIT_ERROR = "a map scene carries the in-frame credit ['© Mapbox', '© OpenStreetMap']"


def _validate(data, *, fmt="full", words=None, captures=None, cf=None):
    cf = cf or casefile.from_dict(ef.casefile())
    return script.validate_script(
        data, cf, sf.REGISTRY, slug="baalbek-c5", fmt=fmt, words=words, captures=captures
    )


def test_fixture_script_passes_before_voice_with_deferred_checks():
    report = _validate(sf.script())
    assert report.errors == []
    assert "chapter lengths are checked after the voice step" in report.deferred
    assert "clip lengths and holds are checked after the voice step" in report.deferred
    assert any("props not checked yet" in d for d in report.deferred)


def test_fixture_script_passes_fully_after_voice_and_capture():
    data = sf.script()
    report = _validate(data, words=sf.words_for(data), captures=sf.manifests())
    assert report.errors == [] and report.deferred == []


def test_a_partial_capture_defers_only_the_missing_ones():
    data = sf.script()
    partial = {"platform-01": sf.manifests()["platform-01"]}
    report = _validate(data, words=sf.words_for(data), captures=partial)
    assert report.errors == []
    assert [d.split(":")[0] for d in report.deferred] == ["b04", "b05"]


def _errors(mutate, **kw):
    return _validate(sf.mutated_script(mutate), **kw).errors


def test_unverified_evidence_and_missing_evidence():
    errors = _errors(lambda d: d["beats"][2].update(evidence=["e2"]))
    assert "b03: evidence e2 is unverified, not verified" in errors
    errors = _errors(lambda d: d["beats"][2].update(evidence=[]))
    assert "b03: a factual beat lists its evidence ids" in errors


def test_display_may_only_respell_numbers():
    errors = _errors(
        lambda d: d["beats"][0].update(
            display="This rock weighs about 1,000 tonnes. One person gives the scale."
        )
    )
    assert errors == [
        "b01: display differs from spoken beyond number spelling (token 1: spoken 'stone' vs display 'rock')"
    ]


def test_hook_limit_counts_screen_time_and_position():
    long = " ".join(["word"] * 70)  # 26.9 s of speech + lead and tail
    errors = _errors(lambda d: d["beats"][1].update(spoken=long, display=long, cues=[]))
    assert any(
        e.startswith("hook is ") and "s of screen time (estimated); max 32 s" in e for e in errors
    )
    errors = _errors(lambda d: d["beats"][3].update(hook=True))
    assert "b04: hook beats must all come first" in errors


def test_a_hook_word_must_fit_a_caption_line():
    """The renderer breaks hook caption lines between words at HOOK_LINE_MAX_CHARS characters
    (stream D's captionLines); one longer word (uppercased as drawn, punctuation included)
    cannot be broken, so it is refused before the voice."""

    def at(i, word):
        def mutate(d):
            d["beats"][i]["spoken"] += f" At {word}"
            d["beats"][i]["display"] += f" At {word}"

        return mutate

    assert script.HOOK_LINE_MAX_CHARS == 24
    assert _errors(at(0, "Pre-Pottery-Neolithic-A.")) == []  # 24 characters
    assert _errors(at(0, "Pre-Pottery-Neolithic-AB.")) == [
        "b01: hook word 'Pre-Pottery-Neolithic-AB.' is longer than 24 characters and cannot "
        "fit a caption line"
    ]
    assert _errors(at(5, "Pre-Pottery-Neolithic-AB.")) == []  # no hook, no caption


def test_share_card_is_the_end_card():
    """The link appears only on the end card and in the description (platform moments are
    never an advert): no beat but the last may use ShareCard, in a slice either."""
    end_card = sf.script()["beats"][8]["visual"]

    def early(d):
        d["beats"][2]["visual"] = end_card

    message = "b03: ShareCard is the end card; only the last beat may use it"
    assert message in _errors(early)
    assert _validate(sf.mutated_script(early), fmt="slice").errors == [message]


def test_beat_fields_and_chapter_titles_are_typed():
    def mutate(d):
        d["beats"][0].update(lead_s=-0.1, hook="yes")
        d["beats"][2].update(min_s=0, role="cliffhanger")
        d["chapters"][1]["title"] = " "

    errors = _errors(mutate)
    assert "b01: lead_s must be a number >= 0" in errors
    assert "b01: hook must be true or false" in errors
    assert "b03: min_s must be a number > 0" in errors
    assert "b03: role must be one of ['twist', 'verdict', 'change_mind']" in errors
    assert any(e.endswith("title must be a non-empty string") for e in errors)


def test_forbidden_and_unknown_blocks():
    errors = _errors(lambda d: d["beats"][6]["visual"].update(block="TitleCard"))
    assert "b07: block TitleCard (title card / on-screen agent) is not allowed" in errors
    errors = _errors(lambda d: d["beats"][6]["visual"].update(block="Hologram"))
    assert "b07: block Hologram is not in the renderer's registry" in errors


def test_platform_moment_count_and_length():
    errors = _errors(lambda d: d["beats"].pop(3))
    assert "2 platform moments; a full episode has 3-5" in errors
    assert _validate(sf.mutated_script(lambda d: d["beats"].pop(3)), fmt="slice").errors == [
        e for e in errors if "platform moments" not in e
    ]
    errors = _errors(lambda d: d["beats"][2].update(min_s=20.0))
    assert "b03: platform moment of 20.0 s (max 15 s)" in errors
    errors = _errors(lambda d: d["beats"][2].update(min_s=3.0))
    assert "b03: platform moment of 3.6 s (min 5 s)" in errors


def test_map_scenes_need_the_credit_in_frame_or_from_their_capture():
    data = sf.mutated_script(lambda d: d["beats"][2]["visual"].pop("credit"))
    words = sf.words_for(data)
    assert "b03: map credit checked after capture" in _validate(data).deferred
    assert _validate(data, words=words, captures=sf.manifests()).errors == []
    silent = sf.manifests()
    silent["platform-01"]["credits"] = []
    assert f"b03: {CREDIT_ERROR}" in _validate(data, words=words, captures=silent).errors

    def flyover(d):
        d["captures"].append({"id": "g1", "kind": "globe", "scene": "mapbox_flyin"})
        d["beats"][3]["visual"] = {"block": "MapboxFlyover", "props": {"clip": {"$capture": "g1"}}}

    data = sf.mutated_script(flyover)
    take = {**sf.manifests()["platform-02"], "id": "g1", "kind": "globe", "credits": []}
    errors = _validate(data, words=sf.words_for(data), captures={**sf.manifests(), "g1": take})
    assert f"b04: {CREDIT_ERROR}" in errors.errors


def test_local_cues_follow_the_renderers_cue_table():
    errors = _errors(lambda d: d["beats"][0]["cues"][0].update(target="mk9"))
    assert "b01 cue 1: show mk9: not a target of this block (mk1)" in errors
    errors = _errors(
        lambda d: d["beats"][1]["cues"].append(
            {"at_word": "machines", "do": "stamp", "target": "c1"}
        )
    )
    assert "b02 cue 2: the block does not take stamp cues" in errors

    def bars(target):
        def mutate(d):
            d["beats"][7]["visual"] = {
                "block": "BarChart",
                "props": {
                    "title": "Block weights",
                    "unit": "t",
                    "basis": "published estimates",
                    "bars": [
                        {"id": "q1", "label": "2014 block", "value": [1500, 1650]},
                        {"id": "b-podium", "label": "Podium block", "value": 800},
                    ],
                },
            }
            d["beats"][7]["cues"] = [{"at_word": "tool", "do": "show", "target": target}]

        return mutate

    assert [e for e in _errors(bars("b-podium")) if e.startswith("b08")] == []
    assert _errors(bars("b-none")) == [
        "b08 cue 1: show b-none: not a target of this block (q1, b-podium)"
    ]


def test_a_quantity_shown_in_a_chart_keeps_its_range():
    def chart(value):
        def mutate(d):
            d["beats"][7]["visual"] = {
                "block": "BarChart",
                "props": {
                    "title": "Block weights",
                    "unit": "t",
                    "basis": "published estimates",
                    "bars": [
                        {"id": "q1", "label": "2014 block", "value": value},
                        {"id": "b-podium", "label": "Podium block", "value": 800},
                    ],
                },
            }
            d["beats"][7]["cues"] = [{"at_word": "tool", "do": "show", "target": "q1"}]

        return mutate

    assert [e for e in _errors(chart([1500, 1650])) if e.startswith("b08")] == []
    assert "b08: element q1 must show quantity q1 as [1500, 1650]" in _errors(chart(1500))

    def in_kg(d):
        chart([1500, 1650])(d)
        d["beats"][7]["visual"]["props"]["unit"] = "kg"

    assert "b08: element q1 shows quantity q1 in kg; the case file says t" in _errors(in_kg)
    errors = _errors(lambda d: d["beats"][7]["visual"]["props"]["items"][0].update(id="q1"))
    assert (
        "b08: element q1 uses a quantity id; only a BarChart bar or a ScaleZoom end shows a "
        "quantity" in errors
    )


def test_a_shown_quantity_rests_only_on_verified_evidence():
    """Spec 4.2: every evidence item the script uses is verified, and a shown quantity uses its
    own evidence, whichever ids the beat lists."""
    data = ef.casefile()
    data["quantities"][0]["evidence"] = ["e1", "e2"]
    cf = casefile.from_dict(data)

    def chart(d):
        d["beats"][7]["visual"] = {
            "block": "BarChart",
            "props": {
                "title": "Block weights",
                "unit": "t",
                "basis": "published estimates",
                "bars": [
                    {"id": "q1", "label": "2014 block", "value": [1500, 1650]},
                    {"id": "b-podium", "label": "Podium block", "value": 800},
                ],
            },
        }
        d["beats"][7].update(evidence=["e1"], factual=True)
        d["beats"][7]["cues"] = [{"at_word": "tool", "do": "show", "target": "q1"}]

    report = _validate(sf.mutated_script(chart), cf=cf)
    assert [e for e in report.errors if e.startswith("b08")] == [
        "b08: element q1 shows quantity q1, whose evidence e2 is unverified, not verified"
    ]
    assert not [d for d in report.deferred if d.startswith("b08")]


def test_charts_are_linear_and_a_scale_zoom_shows_quantities():
    """Owner decision 31: no log axis anywhere; a ratio beyond 1:400 is a linear ScaleZoom."""

    def log_chart(d):
        d["beats"][7]["visual"] = {
            "block": "BarChart",
            "props": {
                "title": "Block weights",
                "unit": "t",
                "basis": "published estimates",
                "scale": "log10",
                "bars": [
                    {"id": "b-a", "label": "Podium block", "value": 800},
                    {"id": "b-b", "label": "A car", "value": 1.5},
                ],
            },
        }
        d["beats"][7]["cues"] = []

    assert (
        "b08: props.scale: not allowed"
        in _validate(sf.mutated_script(log_chart), words=sf.words_for(sf.script())).errors
    )
    data = ef.casefile()
    data["quantities"].append(
        {
            "id": "q2",
            "label": "Podium block",
            "value": 800,
            "unit": "t",
            "basis": "DAI 2014",
            "evidence": ["e1"],
        }
    )
    cf = casefile.from_dict(data)

    def zoom(large=800, unit="t", small_id="brick", target="q2"):
        def mutate(d):
            d["beats"][7]["visual"] = {
                "block": "ScaleZoom",
                "props": {
                    "title": "A brick and the podium block",
                    "unit": unit,
                    "basis": "published estimates",
                    "small": {"id": small_id, "label": "A brick", "value": 0.004},
                    "large": {"id": "q2", "label": "Podium block", "value": large},
                },
            }
            d["beats"][7]["cues"] = [{"at_word": "tool", "do": "show", "target": target}]

        return mutate

    def b08(mutate):
        return [e for e in _validate(sf.mutated_script(mutate), cf=cf).errors if "b08" in e]

    assert b08(zoom()) == []
    assert b08(zoom(target="nope")) == [
        "b08 cue 1: show nope: not a target of this block (brick, q2)"
    ]
    assert b08(zoom(large=900)) == ["b08: element q2 must show quantity q2 as 800"]
    assert b08(zoom(unit="kg")) == ["b08: element q2 shows quantity q2 in kg; the case file says t"]
    assert b08(zoom(small_id="q1")) == [
        "b08: element q1: a range quantity is shown as a range in a BarChart, not in a ScaleZoom"
    ]


def test_cue_shape_and_values():
    errors = _errors(lambda d: d["beats"][0]["cues"][0].update(at_word="giraffe"))
    assert "b01 cue 1: at_word 'giraffe' is not in display" in errors
    # a cue names whole display words: "on" is only a piece of "One" and "stone"
    errors = _errors(lambda d: d["beats"][0]["cues"][0].update(at_word="on"))
    assert "b01 cue 1: at_word 'on' is not in display" in errors
    assert _errors(lambda d: d["beats"][0]["cues"][0].update(at_word="one person")) == []
    assert script.cue_word_index("This stone weighs about 1,000 tonnes. One person", "one") == 6
    assert script.cue_word_index("It weighs 1,000 tonnes.", "TONNES") == 3
    errors = _errors(lambda d: d["beats"][0]["cues"][0].update(value=1))
    assert "b01 cue 1: a show cue takes no value" in errors
    errors = _errors(lambda d: d["beats"][0]["cues"][0].update(extra=True))
    assert "b01 cue 1: unknown cue keys ['extra']" in errors
    errors = _errors(lambda d: d["beats"][6]["cues"][0].update(value=[120, -20]))
    assert (
        "b07 cue 1: meter cue targets 'meter' with value [a, b], integers 0-100 summing to 100"
        in errors
    )
    errors = _errors(lambda d: d["beats"][0]["visual"]["props"].update(kenBurns="spin"))
    assert "b01: props.kenBurns: 'spin' is not one of ['in', 'out', 'none']" in errors


def test_claims_on_the_board_are_introduced_evidenced_and_statused():
    errors = _errors(lambda d: d["beats"][5].update(cues=[]))
    assert "claim c1: no status beat after its evidence" in errors
    errors = _errors(lambda d: d["beats"][1].update(cues=[]))
    assert "claim c1: on the board but never introduced" in errors
    data = ef.casefile()
    data["claims"].append({**data["claims"][0], "id": "c2", "label": "Another claim"})
    cf = casefile.from_dict(data)
    two = sf.mutated_script(
        lambda d: d["beats"][5]["cues"].append(
            {"at_word": "quarry", "do": "introduce", "target": "c2"}
        )
    )
    assert "b06 cue 2: introduce c2: no ClaimBoard of the episode lists this claim" in (
        _validate(two, cf=cf).errors
    )
    decided = casefile.from_dict(ef.mutated(claims__0__status="supported"))
    assert any(
        e.startswith("claim c1: a claim on the board starts 'pending'")
        for e in _validate(sf.script(), cf=decided).errors
    )


def test_meter_cues_need_a_meter_that_matches_the_case_file():
    errors = _errors(lambda d: d["beats"][6]["visual"]["props"].update(start=[60, 40]))
    assert "b07: Meter hypotheses/start must equal the case file's meter" in errors

    def no_meter(d):
        d["beats"][6]["visual"] = {
            "block": "ListCard",
            "props": {"title": "Verdict", "items": [{"id": "v1", "text": "Roman engineers"}]},
        }

    errors = _errors(no_meter)
    assert "a meter cue needs a Meter beat" in errors


def test_case_file_entities_enter_props_only_by_reference():
    inline = casefile.resolved(casefile.from_dict(ef.casefile()))["e1"]
    errors = _errors(lambda d: d["beats"][5]["visual"]["props"].update(evidence=inline))
    assert 'b06: props.evidence must reference the case file ({"$ref": <evidence id>})' in errors
    errors = _errors(lambda d: d["beats"][2]["visual"]["props"].update(clip=sf.manifests()))
    assert 'b03: props.clip must reference a capture ({"$capture": <capture id>})' in errors
    errors = _errors(lambda d: d["beats"][1]["visual"]["props"].update(claims=[{"$ref": "e1"}]))
    assert 'b02: props.claims must reference the case file ([{"$ref": <claim id>}])' in errors


def test_captures_are_declared_named_and_of_the_blocks_kind():
    errors = _errors(
        lambda d: d["beats"][2]["visual"].update(props={"clip": {"$capture": "platform-09"}})
    )
    assert "b03: $capture 'platform-09' is not declared in captures" in errors
    errors = _errors(lambda d: d["captures"][0].update(id="Platform_01"))
    assert "capture 'Platform_01': id must match ^[a-z0-9][a-z0-9-]{0,47}$" in errors

    def globe_take(d):
        d["captures"].append({"id": "g1", "kind": "globe", "scene": "mapbox_flyin"})
        d["beats"][2]["visual"]["props"]["clip"] = {"$capture": "g1"}

    assert "b03: props.clip: PlatformClip needs a platform capture, 'g1' is globe" in _errors(
        globe_take
    )


def test_a_globe_block_takes_only_its_own_globe_scenes():
    def flyover_of(scene):
        def mutate(d):
            d["captures"].append({"id": "g2", "kind": "globe", "scene": scene})
            d["beats"][3]["visual"] = {
                "block": "MapboxFlyover",
                "props": {"clip": {"$capture": "g2"}},
            }

        return mutate

    wrong = (
        "b04: props.clip: MapboxFlyover needs a globe take of scene "
        "['mapbox_flyin', 'mapbox_orbit'], 'g2' is 'flyto'"
    )
    assert wrong in _errors(flyover_of("flyto"))
    assert not [e for e in _errors(flyover_of("mapbox_orbit")) if "globe take" in e]


def test_a_clip_must_cover_its_scene():
    data = sf.script()
    short = sf.manifests()
    short["platform-01"]["duration_s"] = 4.0
    errors = _validate(data, words=sf.words_for(data), captures=short).errors
    assert (
        "b03: capture platform-01 is 4.0 s long; the scene needs 5.950 s from 0 s "
        "(record a longer take or shorten the beat)" in errors
    )


def test_scene_frames_round_up_to_a_whole_frame_without_float_noise():
    # max(3.0, 0.35 + 5.0 + 0.6) = 5.95 s -> 357 frames; a thousandth more starts frame 358
    assert script.scene_frames({"min_s": 3.0}, 5.0) == 357
    assert script.scene_frames({"min_s": 3.0}, 5.001) == 358
    # 8.3 * 60 is 498.00000000000006 in floats: the scene is 498 frames, not 499
    assert 8.3 * script.FPS > 498
    assert script.scene_frames({"min_s": 8.3}, 1.0) == 498


def test_capture_specs_show_only_verified_case_file_data():
    quarry = {"lat": 33.99917, "lng": 36.20028}

    def distribution(cid, places, site_ids):
        spec = {"id": cid, "kind": "globe", "scene": "distribution", "duration_s": 16}
        return {**spec, "places": places, "site_ids": site_ids}

    def specs(d):
        d["captures"] += [
            {
                "id": "g1",
                "kind": "globe",
                "scene": "flyto",
                "lat": 34.0,
                "lng": 36.2,
                "place": {"id": "p1", "label": "Baalbek quarry"},
            },
            {
                "id": "g2",
                "kind": "globe",
                "scene": "flyto",
                **quarry,
                "place": {"id": "p1", "label": "Temple of Jupiter"},
            },
            {"id": "g3", "kind": "globe", "scene": "flyto", **quarry, "place": "p1"},
            {"id": "td1", "kind": "mapbox_topdown", "pins": [{"id": "p9", "lat": 1, "lng": 2}]},
            {"id": "td2", "kind": "mapbox_topdown", "pins": 5},
            {"id": "src-x", "kind": "source", "url": "https://example.org/x", "quote": "q"},
            {"id": "paper-ev", "kind": "source", "paper": "the-megaliths", "anchor": "ev-07"},
            distribution("g4", [{"id": "w9", "label": "Somewhere", "lat": 1, "lng": 2}], []),
            distribution(
                "g5",
                [{"id": "p1", "label": "Baalbek quarry", **quarry}],
                ["be81c1a6-0000-4000-8000-000000000001", "383a0107-b7f7-4431-a752-590f3c0a42b2"],
            ),
            distribution("g6", [{"id": "p1", **quarry}], ["s-1", "s-1"]),
            distribution("g7", [], [f"s-{n}" for n in range(501)]),
            {
                "id": "g8",
                "kind": "globe",
                "scene": "places",
                "places": [{"id": "p1", "label": "Baalbek quarry", **quarry}],
                "site_ids": ["383a0107-b7f7-4431-a752-590f3c0a42b2"],
            },
            {"id": "m1", "kind": "globe", "scene": "mapbox_flyin", "lat": 1, "lng": 2},
            {"id": "m2", "kind": "globe", "scene": "mapbox_orbit", **quarry},
            {
                "id": "pf9",
                "kind": "platform",
                "target": "local",
                "actions": [
                    {"do": "search", "q": "Baalbek"},
                    {"do": "measure", "a": quarry, "b": {"lat": 34.01, "lng": 36.21}},
                    {"do": "proximity", "at": quarry},
                    {"do": "proximity", "at": {"lat": 1, "lng": 2}},
                ],
            },
        ]

    errors = _errors(specs)
    assert "capture g1: place p1 lat/lng differ from the case file" in errors
    assert (
        "capture g2: place p1 label 'Temple of Jupiter' is not the case file's name "
        "'Baalbek quarry'" in errors
    )
    assert "capture g3: place must be {id, label}" in errors
    assert "capture td1: place p9 is not in the case file" in errors
    assert "capture td2: pins must be a list" in errors
    assert "capture g4: place w9 is not in the case file" in errors
    assert not [e for e in errors if e.startswith("capture g5")]
    assert (
        "capture g6: place p1 needs its label (a distribution's places are its named pins; "
        "further sites go in site_ids)" in errors
    )
    assert "capture g6: site_ids must be a list of unique site ids" in errors
    assert (
        "capture g7: a distribution shows 1 to 500 points (places plus site_ids), got 501" in errors
    )
    assert [e for e in errors if e.startswith("capture g8")] == [
        "capture g8: site_ids belong only to a globe distribution take (owner decision 15)"
    ]
    assert "capture m1: lat/lng are not the coordinates of a case-file place" in errors
    assert not [e for e in errors if e.startswith("capture m2")]
    assert [e for e in errors if e.startswith("capture pf9")] == [
        "capture pf9: actions[1].b is not the coordinates of a case-file place",
        "capture pf9: actions[3].at is not the coordinates of a case-file place",
    ]
    assert (
        "capture src-x: quote is not the verified quote of a case-file evidence item from "
        "https://example.org/x" in errors
    )
    assert "capture paper-ev: anchor ev-07 is not the paper_anchor of a verified evidence item" in (
        errors
    )


def test_a_mapbox_country_is_bound_to_the_site_of_its_place():
    """C7: the `country` a Mapbox take highlights is shown data: the case-file place the take
    centres on carries a site_id, and episode.country_problems compares `country` with that
    site's country in the site export."""
    quarry = {"lat": 33.99917, "lng": 36.20028}
    take = {"id": "m3", "kind": "globe", "scene": "mapbox_orbit", **quarry, "country": "Lebanon"}
    errors = _errors(lambda d: d["captures"].append(take))
    assert (
        "capture m3: country needs case-file place p1 to carry a site_id (the country is the "
        "site export's country of that site)" in errors
    )
    cf = casefile.from_dict(ef.mutated(places__0__site_id="383a0107-b7f7-4431-a752-590f3c0a42b2"))
    assert not [e for e in _errors(lambda d: d["captures"].append(take), cf=cf) if "m3" in e]
    blank = {**take, "country": " "}
    errors = _errors(lambda d: d["captures"].append(blank), cf=cf)
    assert "capture m3: country must be a non-empty string" in errors


def test_a_source_viewer_shows_its_own_evidence():
    def viewer(page):
        def mutate(d):
            d["captures"].append({"id": "page", "kind": "source", **page})
            d["beats"][5]["visual"] = {
                "block": "SourceViewer",
                "props": {"page": {"$capture": "page"}, "evidence": {"$ref": "e1"}},
            }
            d["beats"][5]["cues"][0]["at_word"] = "measured"

        return mutate

    quote = {"url": "https://www.dainst.org/baalbek-report", "quote": "weighs about 1000 tons"}
    assert [e for e in _errors(viewer(quote)) if "page" in e] == []
    paper = {"paper": "the-megaliths", "anchor": "ev-01"}
    assert [e for e in _errors(viewer(paper)) if "page" in e] == []
    wrong = {"paper": "the-megaliths", "anchor": "ev-01"}
    data = ef.mutated(evidence__0__paper_anchor="ev-02")
    errors = _validate(sf.mutated_script(viewer(wrong)), cf=casefile.from_dict(data)).errors
    assert (
        "b06: SourceViewer page page does not show evidence e1 (url/quote or paper/anchor differ)"
        in errors
    )


def test_a_full_episode_keeps_the_case_file_spine():
    errors = _errors(lambda d: d["beats"].pop())
    assert "full episode lacks a closing ShareCard beat" in errors
    errors = _errors(lambda d: d["beats"][4].pop("role"))
    assert "full episode lacks a beat with role 'twist'" in errors
    errors = _errors(
        lambda d: (d["beats"][4].update(role="verdict"), d["beats"][6].update(role="twist"))
    )
    assert "full episode needs the roles twist, verdict, change_mind in that order" in errors
    assert _validate(sf.mutated_script(lambda d: d["beats"].pop()), fmt="slice").errors == []


def test_every_drawn_string_needs_a_brand_font_glyph():
    assert glyphs.unsupported_char("Vinča, Çatalhöyük, Şanlıurfa: 1,000–1,650 t × 2 …") is None
    assert glyphs.unsupported_char("Κνωσός") == "Κ"
    assert glyphs.unsupported_char("Baalbek → Rome") == "→"
    # inside the fonts' declared unicode-range, but in no loaded file (a system font would draw them)
    assert glyphs.unsupported_char("Ḫattuša") == "Ḫ"
    assert glyphs.unsupported_char("non‑breaking") == "‑"
    assert glyphs.unsupported_char("5‰") == "‰"
    errors = _errors(lambda d: d["chapters"][1].update(title="Κνωσός"))
    assert f'chapters[1].title: "Κ" (U+039A) {GLYPH_ERROR}' in errors

    def greek_hook(d):
        d["beats"][0]["spoken"] += " At Κνωσός."
        d["beats"][0]["display"] += " At Κνωσός."

    errors = _errors(greek_hook)
    assert f'b01: display token 13: "Κ" (U+039A) {GLYPH_ERROR}' in errors
    cf = casefile.from_dict(ef.mutated(media__0__attribution="Γιάννης Δ."))
    errors = _validate(sf.script(), cf=cf).errors
    # the attribution is drawn only inside the credit line, never as props.image.attribution
    assert [e for e in errors if GLYPH_ERROR in e] == [
        f'b01: credit of media m1: "Γ" (U+0393) {GLYPH_ERROR}'
    ]
    cf = casefile.from_dict(ef.mutated(claims__0__label="Κνωσός was built by giants"))
    errors = _validate(sf.script(), cf=cf).errors
    assert f'b02: props.claims[0].label: "Κ" (U+039A) {GLYPH_ERROR}' in errors
    errors = _errors(lambda d: d["thumbnails"][0].update(text="Who moved Κνωσός?"))
    assert f'thumbnails[0].text: "Κ" (U+039A) {GLYPH_ERROR}' in errors
    # µ and ẖ are in no loaded file; CSS upper case maps ƒ to Ƒ, which none maps either
    assert glyphs.unsupported_char("1 µm") == "µ"
    assert glyphs.unsupported_char("ẖ") == "ẖ"
    errors = _errors(lambda d: d["thumbnails"][0].update(text="Set ƒ/8?"))
    assert (
        f'thumbnails[0].text: "ƒ" (U+0192) draws as "Ƒ" (U+0191) in upper case, which '
        f"{GLYPH_ERROR}" in errors
    )


def test_a_source_viewer_may_show_a_non_latin_quote():
    """Owner decision 32: an original quote inside a captured page is pixels, not drawn text."""
    greek = "Ὁ λίθος κεῖται ἐν τῷ λατομείῳ"
    cf = casefile.from_dict(ef.mutated(evidence__0__source__quote=greek))

    def viewer(d):
        d["captures"].append(
            {
                "id": "page",
                "kind": "source",
                "url": "https://www.dainst.org/baalbek-report",
                "quote": greek,
            }
        )
        d["beats"][5]["visual"] = {
            "block": "SourceViewer",
            "props": {"page": {"$capture": "page"}, "evidence": {"$ref": "e1"}},
        }

    data = sf.mutated_script(viewer)
    page = {
        "id": "page",
        "kind": "source",
        "path": "captures/page.png",
        "fps": None,
        "duration_s": None,
        "width": 2560,
        "height": 3000,
        "events": [
            {
                "t": 0.0,
                "name": "page",
                "url": "https://el.wikipedia.org/wiki/Κνωσός",
                "title": "DAI",
            },
            {"t": 1.0, "name": "highlight", "box": [10, 20, 300, 40], "target": "e1"},
        ],
        "credits": ["Source page: el.wikipedia.org"],
    }
    captures = {**sf.manifests(), "page": page}
    report = _validate(data, cf=cf, words=sf.words_for(data), captures=captures)
    assert report.errors == [] and report.deferred == []
    # the page's own <title> is a record, never drawn: a Greek page title passes
    titled = {**page, "events": [{**page["events"][0], "title": "Κνωσός"}, page["events"][1]]}
    report = _validate(data, cf=cf, words=sf.words_for(data), captures={**captures, "page": titled})
    assert report.errors == [] and report.deferred == []
    credited = {**titled, "credits": ["Source page: Κνωσός"]}
    errors = _validate(
        data, cf=cf, words=sf.words_for(data), captures={**captures, "page": credited}
    ).errors
    assert errors == [f'b06: capture page.credits[0]: "Κ" (U+039A) {GLYPH_ERROR}']


def test_thumbnails_never_show_the_answer():
    """Owner decisions 24-25: three A/B candidates, each a 2-4 word teaser at a frame before
    any verdict."""
    assert _errors(lambda d: d["thumbnails"].pop()) == [
        "thumbnails must be a list of exactly 3 candidates"
    ]

    def candidate(i, **item):
        return lambda d: d["thumbnails"][i].update(item)

    errors = _errors(candidate(0, beat="b05"))
    assert "thumbnails[0]: beat b05 is the twist beat: a thumbnail never shows the answer" in errors
    errors = _errors(candidate(1, beat="b09"))
    assert (
        "thumbnails[1]: beat b09 comes after the first verdict cue (beat b06): a thumbnail "
        "never shows the answer" in errors
    )
    assert "thumbnails[2]: beat 'b99' is not a beat of the script" in _errors(
        candidate(2, beat="b99")
    )
    assert "thumbnails[0]: at is the share of the beat's scene, 0 <= at < 1" in _errors(
        candidate(0, at=1.0)
    )
    assert "thumbnails[0]: the teaser has 1 words; it has 2-4" in _errors(candidate(0, text="Who?"))
    assert "thumbnails[0]: the teaser has 5 words; it has 2-4" in _errors(
        candidate(0, text="Who really moved this stone?")
    )
    assert "thumbnails[1]: the teaser names the answer (TRUE): never show it" in _errors(
        candidate(1, text="Is it true?")
    )
    assert "thumbnails[2] must be exactly {beat, at, text}" in _errors(candidate(2, frame=10))
    errors = _errors(lambda d: d["thumbnails"].__setitem__(2, dict(d["thumbnails"][0])))
    assert "thumbnails[2]: the same candidate as thumbnails[0]" in errors


def test_a_visual_credit_is_a_non_empty_string():
    for credit in (5, " ", ["© Mapbox"]):
        errors = _errors(lambda d, c=credit: d["beats"][2]["visual"].update(credit=c))
        assert "b03: visual.credit must be a non-empty string" in errors


def test_chapters_after_voice():
    data = sf.script()
    report = _validate(
        data, words=sf.words_for(data, seconds_per_beat=2.0), captures=sf.manifests()
    )
    assert "chapter 'The stone' lasts 6.0 s (min 10 s)" in report.errors
    errors = _errors(lambda d: d.update(chapters=[{"title": "x", "beat": "b02"}]))
    assert "the first chapter must start at the first beat (0:00)" in errors
    assert "a full episode has at least 3 chapters" in errors


def test_episode_slug_and_shape():
    assert _validate(sf.mutated_script(lambda d: d.update(episode="other"))).errors == [
        "episode 'other' is not this episode ('baalbek-c5')"
    ]
    assert _validate({"version": 1}).errors[0].startswith("script keys: missing")


def test_version_speed_and_captures_are_typed():
    """True == 1 in Python, so a bool passed the version and speed checks; a captures dict or
    string was walked key by key or character by character."""
    assert _errors(lambda d: d.update(version=True)) == ["version must be 1"]
    assert _errors(lambda d: d["voice"].update(speed=True)) == [
        "voice.speed must be between 0.5 and 2.0"
    ]
    for captures in ({"platform-01": {}}, "platform-01"):
        errors = _errors(lambda d, c=captures: d.update(captures=c))
        assert "captures must be a list" in errors
        assert not [e for e in errors if "needs a string id" in e]


def test_list_values_where_strings_belong_are_errors_not_crashes():
    """A malformed script is an error, never a crash ('unhashable type: list')."""
    data = sf.script()
    full = {"words": sf.words_for(data), "captures": sf.manifests()}

    def errors(mutate):
        return _validate(sf.mutated_script(mutate), **full).errors

    # the recorder refuses the action at capture; the script check must not crash on it
    assert errors(lambda d: d["captures"][0]["actions"].append({"do": ["measure"]})) == []
    assert "b01 cue 1: do must be one of" in " ".join(
        errors(lambda d: d["beats"][0]["cues"][0].update(do=["show"]))
    )
    assert errors(lambda d: d["beats"][5]["cues"][0].update(target=["c1"])) == [
        "b06 cue 1: target must be a non-empty string",
        "claim c1: no status beat after its evidence",
    ]
    # a malformed visual skips the rest of its beat, as before (so b03 is no platform moment)
    assert "b03: a $capture names a capture id (a string), got ['x']" in errors(
        lambda d: d["beats"][2]["visual"]["props"].update(clip={"$capture": ["x"]})
    )
    assert "b06: a $ref names a case-file id (a string), got ['e1']" in errors(
        lambda d: d["beats"][5]["visual"]["props"].update(evidence={"$ref": ["e1"]})
    )
    assert "b07: visual must be {block, props (object), credit?}" in errors(
        lambda d: d["beats"][6]["visual"].update(block=["Meter"])
    )
    assert "thumbnails[0]: beat ['b01'] is not a beat of the script" in errors(
        lambda d: d["thumbnails"][0].update(beat=["b01"])
    )

    def list_ids(d):
        d["beats"][2]["id"] = ["b03"]
        d["beats"][3]["id"] = ["b03"]

    listed = errors(list_ids)
    assert "#3: id must be a string" in listed and "#4: id must be a string" in listed


def test_a_beat_that_is_not_an_object_stops_the_timed_checks():
    """_chapters slices the beats by the positions of the object beats; with a word timing
    it measured the string 'oops' as a beat (TypeError)."""
    words = sf.words_for(sf.script())
    data = sf.mutated_script(lambda d: d["beats"].insert(2, "oops"))
    report = _validate(data, words=words, captures=sf.manifests())
    assert "beat 3: not an object" in report.errors
    assert "chapter lengths are checked after the voice step" in report.deferred


def test_a_flyto_with_a_null_place_is_a_regional_view():
    """capture/globe.py reads "place": null as no place (a regional view), and so does the
    script check."""
    take = {"id": "g9", "kind": "globe", "scene": "flyto", "lat": 1, "lng": 2, "place": None}
    assert not [e for e in _errors(lambda d: d["captures"].append(take)) if "g9" in e]


def test_capture_spec_labels_are_glyph_checked_before_the_take():
    """A place label the renderer draws (flyto, places, distribution and top-down pins) is
    refused before the take is recorded, not only on its manifest afterwards."""
    cf = casefile.from_dict(ef.mutated(places__0__name="Ḫattuša"))
    quarry = {"lat": 33.99917, "lng": 36.20028}
    specs = [
        {"id": "g1", "kind": "globe", "scene": "flyto", **quarry, "place": {"id": "p1"}},
        {"id": "g2", "kind": "globe", "scene": "places", "places": [{"id": "p1", **quarry}]},
        {"id": "td1", "kind": "mapbox_topdown", "pins": [{"id": "p1", **quarry}]},
    ]
    specs[0]["place"]["label"] = "Ḫattuša"
    specs[1]["places"][0]["label"] = "Ḫattuša"
    specs[2]["pins"][0]["label"] = "Ḫattuša"
    errors = _validate(sf.mutated_script(lambda d: d["captures"].extend(specs)), cf=cf).errors
    assert [e for e in errors if GLYPH_ERROR in e] == [
        f'capture {cid}: place p1 label: "Ḫ" (U+1E2A) {GLYPH_ERROR}' for cid in ("g1", "g2", "td1")
    ]


def test_an_unknown_ref_is_reported_before_the_capture():
    """resolve_refs stops at a capture not yet recorded, so an unknown $ref beside it was
    only reported once the page existed."""

    def viewer(d):
        d["captures"].append(
            {
                "id": "page",
                "kind": "source",
                "url": "https://www.dainst.org/baalbek-report",
                "quote": "weighs about 1000 tons",
            }
        )
        d["beats"][5]["visual"] = {
            "block": "SourceViewer",
            "props": {"page": {"$capture": "page"}, "evidence": {"$ref": "e99"}},
        }

    report = _validate(sf.mutated_script(viewer))
    assert "b06: $ref 'e99' is not in the case file" in report.errors
    assert not [d for d in report.deferred if d.startswith("b06: props")]


def test_one_rule_says_which_cue_shows_the_answer(monkeypatch):
    """The thumbnail rule of the script check and timeline.verdict_frame share one predicate."""
    assert script.is_verdict_cue({"do": "meter", "target": "meter", "value": [70, 30]})
    assert script.is_verdict_cue({"do": "status", "target": "c1", "value": "weakened"})
    assert not script.is_verdict_cue({"do": "status", "target": "c1", "value": "pending"})
    assert not script.is_verdict_cue({"do": "show", "target": "mk1"})
    monkeypatch.setattr(script, "is_verdict_cue", lambda cue: cue["do"] == "introduce")
    errors = _validate(sf.script()).errors
    assert (
        "thumbnails[2]: beat b06 comes after the first verdict cue (beat b02): a thumbnail "
        "never shows the answer" in errors
    )


def test_a_beats_lead_is_read_in_one_place():
    assert script.lead_seconds({"lead_s": 0.5}) == 0.5
    assert script.lead_seconds({}) == script.LEAD_S
    assert script.scene_seconds({"min_s": 1.0, "lead_s": 1.0}, 2.0) == 1.0 + 2.0 + script.TAIL_S
    # frames from the scene start: the lead, then the word's start in the narration
    timing = {"words": [{"w": "a", "s": 0.0, "e": 0.4}, {"w": "b", "s": 0.5, "e": 0.9}]}
    assert script.narration_start({"lead_s": 0.5}) == 30
    assert script.word_start({"lead_s": 0.5}, timing, 1) == 60
    assert script.word_start({}, timing, 1) == 21 + 30


# Owner Q16 (2026-09-30): `episode check` refuses a planned still picture longer than the
# render audit's FROZEN_MAX_S inside a clip scene, before the hours-long render.
GLOBE_REGISTRY = {**sf.REGISTRY, "GlobeShot": load_registry()["GlobeShot"]}
QUARRY = {"lat": 33.99917, "lng": 36.20028}
TEMPLE = {"lat": 34.00694, "lng": 36.20389}
HOLD_ADVICE = (
    "the render audit refuses a clip scene that holds one picture for more than 4 s (shorten "
    "the beat, record a take that moves at least every 4 s, or cut to a card)"
)


def _take(cid, events, *, duration_s=12.0, credits=()):
    return {
        "id": cid,
        "kind": "globe",
        "path": f"captures/{cid}.mp4",
        "fps": 60,
        "duration_s": duration_s,
        "width": 1920,
        "height": 1080,
        "events": events,
        "credits": list(credits),
    }


def _pin(pid, label, t):
    return {
        "t": t,
        "name": "place",
        "target": pid,
        "x": 960.0,
        "y": 540.0,
        "label": label,
        "track": [[960.0, 540.0]],
    }


FLYTO = {
    "id": "g1",
    "kind": "globe",
    "scene": "flyto",
    **QUARRY,
    "distance": 1.35,
    "rotate_s": 1.5,
    "zoom_s": 2.0,
    "duration_s": 12,
    "place": {"id": "p1", "label": "Baalbek quarry"},
}
FLYTO_TAKE = _take(
    "g1",
    [
        {"t": 0.0, "name": "rotate"},
        {"t": 1.5, "name": "zoom"},
        {"t": 3.5, "name": "arrive", "x": 960.0, "y": 540.0},
        _pin("p1", "Baalbek quarry", 3.5),
    ],
)


def _places_spec(lead_s=0.8):
    return {
        "id": "g2",
        "kind": "globe",
        "scene": "places",
        "places": [
            {"id": "p1", "label": "Baalbek quarry", **QUARRY},
            {"id": "p2", "label": "Temple of Jupiter", **TEMPLE},
        ],
        "lead_s": lead_s,
        "interval_s": 0.6,
        "duration_s": 10,
    }


def _places_take(lead_s=0.8):
    pins = [_pin("p1", "Baalbek quarry", lead_s), _pin("p2", "Temple of Jupiter", lead_s + 0.6)]
    return _take("g2", pins, duration_s=10.0)


def _two_places():
    data = ef.casefile()
    data["places"].append({**data["places"][0], "id": "p2", "name": "Temple of Jupiter", **TEMPLE})
    return casefile.from_dict(data)


def _held(spec, take, *, min_s, block="GlobeShot", props=None, cues=(), words=None, cf=None):
    """The errors and deferred checks of beat b04 showing `take` (a slice: b04 is no longer a
    platform moment)."""

    def mutate(d):
        d["captures"].append(spec)
        d["beats"][3]["visual"] = {
            "block": block,
            "props": {"clip": {"$capture": spec["id"]}, **(props or {})},
        }
        d["beats"][3].update(min_s=min_s, cues=list(cues))

    data = sf.mutated_script(mutate)
    report = script.validate_script(
        data,
        cf or _two_places(),
        GLOBE_REGISTRY,
        slug="baalbek-c5",
        fmt="slice",
        words=words or sf.words_for(data),
        captures={**sf.manifests(), spec["id"]: take},
    )
    return (
        [e for e in report.errors if e.startswith("b04")],
        [d for d in report.deferred if d.startswith("b04")],
    )


def test_the_hold_uses_the_render_audits_limit():
    assert script.FROZEN_MAX_S is render_audit.FROZEN_MAX_S
    assert script.frozen_max_frames is render_audit.frozen_max_frames
    assert render_audit.frozen_max_frames(60) == 240


def test_a_flyto_may_not_hold_still_after_arrival_for_more_than_4_s():
    # arrival and pin at 3.5 s (frame 210); a 9 s scene (540 frames) repeats frame 210 329 times
    assert _held(FLYTO, FLYTO_TAKE, min_s=9.0) == (
        [
            "b04: capture g1 holds one picture for 5.48 s, from 3.50 s into the scene (the "
            f"camera stops) to the scene's end; {HOLD_ADVICE}"
        ],
        [],
    )
    assert _held(FLYTO, FLYTO_TAKE, min_s=7.0) == ([], [])
    # the audit's limit: a run of 240 unchanged frames passes, 241 fail
    assert _held(FLYTO, FLYTO_TAKE, min_s=451 / 60) == ([], [])
    assert len(_held(FLYTO, FLYTO_TAKE, min_s=452 / 60)[0]) == 1
    # starting the clip after the arrival leaves no motion in the scene
    errors, _ = _held(FLYTO, FLYTO_TAKE, min_s=7.0, props={"start_s": 4.0})
    assert errors == [
        "b04: capture g1 holds one picture for 6.98 s, from the scene's start to the scene's "
        f"end; {HOLD_ADVICE}"
    ]


def test_a_fixed_pose_may_not_hold_still_after_or_before_its_places_light_up():
    # pins at 0.8 s and 1.4 s (frames 48, 84); a 6 s scene holds 4.58 s after the last one
    assert _held(_places_spec(), _places_take(), min_s=6.0) == (
        [
            "b04: capture g2 holds one picture for 4.58 s, from 1.40 s into the scene (place "
            f"p2 appears) to the scene's end; {HOLD_ADVICE}"
        ],
        [],
    )
    # a show cue delays its pin (GlobeShot): "where" starts 2.5 s into the narration
    shown = [{"at_word": "where", "do": "show", "target": "p2"}]
    assert _held(_places_spec(), _places_take(), min_s=6.0, cues=shown) == ([], [])
    # a lead of 5 s holds the pose from the scene's start until the first place lights up
    assert _held(_places_spec(5.0), _places_take(5.0), min_s=7.0) == (
        [
            "b04: capture g2 holds one picture for 4.98 s, from the scene's start to 5.00 s "
            f"into the scene (place p1 appears); {HOLD_ADVICE}"
        ],
        [],
    )


def test_a_show_cue_on_stale_word_timings_defers_the_hold():
    shown = [{"at_word": "where", "do": "show", "target": "p2"}]
    data = sf.script()
    words = sf.words_for(data)
    words["b04"]["words"][0]["w"] = "A"
    assert _held(_places_spec(), _places_take(), min_s=6.0, cues=shown, words=words) == (
        [],
        [
            "b04: the clip's still picture is checked once words.json holds this beat's "
            "display words (run `episode voice`)"
        ],
    )


def test_takes_that_move_to_their_end_pass():
    distribution = {
        "id": "g3",
        "kind": "globe",
        "scene": "distribution",
        "duration_s": 12,
        "places": [{"id": "p1", "label": "Baalbek quarry", **QUARRY}],
    }
    turn = _take("g3", [_pin("p1", "Baalbek quarry", 2.0)])
    assert _held(distribution, turn, min_s=11.0) == ([], [])
    sweep = {**_places_spec(), "sweep_lng_deg": 60, "cam_lat": 30, "cam_lng_from": 0}
    assert _held({**sweep, "distance": 2.2}, _places_take(), min_s=9.0) == ([], [])
    credit = ["© Mapbox © OpenStreetMap © Maxar"]
    flyin = {"id": "m1", "kind": "globe", "scene": "mapbox_flyin", **QUARRY, "name": "Baalbek"}
    events = [{"t": 0.0, "name": "space"}, {"t": 1.2, "name": "zoom"}, {"t": 3.6, "name": "orbit"}]
    take = _take("m1", events, credits=credit)
    assert _held(flyin, take, min_s=11.0, block="MapboxFlyover") == ([], [])


def test_an_orbit_that_does_not_turn_holds_one_picture():
    orbit = {
        "id": "m2",
        "kind": "globe",
        "scene": "mapbox_orbit",
        **QUARRY,
        "name": "Baalbek",
        "zoom": 16.5,
        "pitch": 60,
        "bearing_from": 20,
        "bearing_to": 110,
        "duration_s": 12,
    }
    credit = ["© Mapbox © OpenStreetMap © Maxar"]
    take = _take("m2", [{"t": 0.0, "name": "orbit"}], credits=credit)
    assert _held(orbit, take, min_s=6.0, block="MapboxFlyover") == ([], [])
    still = {**orbit, "bearing_to": 20}
    assert _held(still, take, min_s=6.0, block="MapboxFlyover") == (
        [
            "b04: capture m2 holds one picture for 5.98 s, from the scene's start to the "
            f"scene's end; {HOLD_ADVICE}"
        ],
        [],
    )


def test_a_platform_take_is_left_to_the_render_audit():
    """The live page moves on its own (the globe's rotation, flights, panels, tiles): its spec
    plans no still picture, so only the render audit can see one."""
    data = sf.mutated_script(lambda d: d["beats"][2].update(min_s=7.9))
    report = _validate(data, fmt="slice", words=sf.words_for(data), captures=sf.manifests())
    assert report.errors == []
