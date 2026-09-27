from __future__ import annotations

from pipeline.studio import casefile, glyphs, script
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
    assert "clip lengths are checked after the voice step" in report.deferred
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
