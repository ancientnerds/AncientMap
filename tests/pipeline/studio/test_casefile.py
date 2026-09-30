from __future__ import annotations

import re

import pytest

from pipeline.studio import casefile
from tests.pipeline.studio import episode_fixtures as ef


def test_fixture_loads_and_round_trips(tmp_path):
    path = ef.write_casefile(tmp_path)
    cf = casefile.load_casefile(path, icons=ef.ICONS)
    assert cf.topic_type == "A"
    assert cf.media[0].markers[0].verified == "crop-check"
    assert casefile.from_dict(cf.to_dict()) == cf


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"topic_type": "E"}, "topic_type must be one of"),
        (
            {"media__0__markers__0__verified": "eyeballed"},
            "mk1: a marker must be verified by 'crop-check'",
        ),
        (
            {"media__0__markers__0__box": [0.9, 0.5, 0.2, 0.3]},
            "mk1: box must be [x, y, w, h] fractions",
        ),
        ({"places__0__coord_source": " "}, "p1: coord_source is required"),
        ({"media__0__license": ""}, "m1: license is required"),
        ({"media__0__path": "../secret.jpg"}, '"../secret.jpg" must lie under voice/, captures/'),
        ({"media__0__path": "media//a.jpg"}, '"media//a.jpg" is not a clean relative path'),
        ({"media__0__path": "media\\a.jpg"}, 'm1: "media\\a.jpg" must lie under'),
        ({"media__0__path": "media/C:x.jpg"}, '"media/C:x.jpg" is not a clean relative path'),
        ({"media__0__path": "voice/b01.mp3"}, "m1: path must be relative under media/"),
        (
            {"media__0__markers__0__box": [0.5, 0.2, 0.50005, 0.1]},
            "mk1: box must be [x, y, w, h] fractions",
        ),
        ({"claims__0__icon": "hammer"}, "c1: icon 'hammer' is not one of weight, ruler, clock"),
        ({"quantities__0__basis": ""}, "q1: a range must state its basis (sources differ)"),
        ({"quantities__0__value": [1650, 1500]}, "q1: a range is [low, high] with low < high"),
        ({"evidence__0__claim_id": "c9"}, "e1: claim_id c9 is not a claim"),
        ({"evidence__0__paper_anchor": "ev-1"}, "e1: paper_anchor must be ev-NN or null"),
        ({"meter__start": [60, 50]}, "meter.start must be two integers 0-100 summing to 100"),
        ({"places__0__id": "c1"}, "duplicate ids ['c1']"),
    ],
)
def test_rules(tmp_path, changes, message):
    path = ef.write_casefile(tmp_path, ef.mutated(**changes))
    with pytest.raises(casefile.CaseFileError, match=re.escape(message)):
        casefile.load_casefile(path, icons=ef.ICONS)


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), [1500, float("inf")]])
def test_a_quantity_value_is_a_finite_number(tmp_path, value):
    """A bool or a non-finite number would reach the renderer's JSON.parse (Python writes NaN)
    or be drawn as 'True'."""
    path = ef.write_casefile(tmp_path, ef.mutated(quantities__0__value=value))
    with pytest.raises(casefile.CaseFileError, match="q1: value must be a finite number"):
        casefile.load_casefile(path, icons=ef.ICONS)


@pytest.mark.parametrize("ids", [[{"x": 1}], [["e1"]], [3]])
def test_quantity_evidence_ids_are_strings_not_a_crash(tmp_path, ids):
    path = ef.write_casefile(tmp_path, ef.mutated(quantities__0__evidence=ids))
    with pytest.raises(casefile.CaseFileError, match="q1: evidence must list evidence ids"):
        casefile.load_casefile(path, icons=ef.ICONS)


def test_asset_paths_follow_the_renderers_rule():
    assert casefile.asset_path_problem("media/stone_person.jpg") is None
    assert casefile.asset_path_problem("captures/pf1.mp4") is None
    assert "must lie under" in casefile.asset_path_problem("fonts/orbitron-700.woff2")
    for bad in ("media//a.jpg", "media/./a.jpg", "voice/../b01.mp3", "music/C:bed.wav"):
        assert "is not a clean relative path" in casefile.asset_path_problem(bad)


def test_structure_errors_name_the_path(tmp_path):
    data = ef.casefile()
    data["evidence"][0]["source"]["tier"] = "1"
    path = ef.write_casefile(tmp_path, data)
    with pytest.raises(
        casefile.CaseFileError, match=r"evidence\[0\]\.source\.tier: expected \['int'\]"
    ):
        casefile.load_casefile(path, icons=ef.ICONS)
    data = ef.casefile()
    data["places"][0]["lat"] = True
    with pytest.raises(casefile.CaseFileError, match=r"places\[0\]\.lat: expected"):
        casefile.from_dict(data)
    data = ef.casefile()
    data["extra"] = 1
    with pytest.raises(casefile.CaseFileError, match=r"casefile: unknown keys \['extra'\]"):
        casefile.from_dict(data)


def test_ai_imagery_needs_the_episode_switch(tmp_path):
    data = ef.casefile()
    data["media"][0]["ai_generated"] = True
    path = ef.write_casefile(tmp_path, data)
    with pytest.raises(casefile.CaseFileError, match="AI-generated imagery is not allowed"):
        casefile.load_casefile(path, icons=ef.ICONS)
    assert casefile.load_casefile(path, icons=ef.ICONS, allow_ai_imagery=True).media[0].ai_generated


def test_resolve_refs_replaces_entities_and_captures():
    cf = casefile.from_dict(ef.casefile())
    entities = casefile.resolved(cf)
    props = {
        "image": {"$ref": "m1"},
        "items": [{"$ref": "e1"}],
        "clip": {"$capture": "platform-01"},
    }
    manifest = {
        "id": "platform-01",
        "kind": "platform",
        "path": "captures/platform-01.mp4",
        "fps": 60,
        "duration_s": 8.0,
        "width": 1920,
        "height": 1080,
        "events": [],
        "credits": [],
    }
    out = casefile.resolve_refs(props, entities, {"platform-01": manifest})
    assert out["image"]["src"] == "media/stone_person.jpg"
    assert out["image"]["markers"] == [
        {"id": "mk1", "box": [0.1, 0.5, 0.1, 0.3], "label": "1 PERSON"}
    ]
    assert out["items"][0]["source"]["url"] == "https://www.dainst.org/baalbek-report"
    assert out["clip"]["src"] == "captures/platform-01.mp4"
    assert casefile.refs_in(props) == ["m1", "e1"]


def test_capture_ids_in_finds_every_capture_ref_at_any_depth():
    props = {
        "clip": {"$capture": "platform-01"},
        "image": {"$ref": "m1"},
        "panels": [{"page": {"$capture": "source-01"}}, [{"$capture": "map-01"}]],
        "label": "$capture",
        "mixed": {"$capture": "not-a-ref", "extra": 1},
    }
    assert casefile.capture_ids_in(props) == ["platform-01", "source-01", "map-01"]
    assert casefile.capture_ids_in({"$ref": "m1"}) == []


def test_unrecorded_and_unknown_refs_fail_differently():
    entities = casefile.resolved(casefile.from_dict(ef.casefile()))
    with pytest.raises(casefile.CaptureNotRecorded):
        casefile.resolve_refs({"$capture": "x"}, entities, None)
    with pytest.raises(casefile.CaptureNotRecorded, match="'x' is not recorded yet"):
        casefile.resolve_refs({"$capture": "x"}, entities, {})
    with pytest.raises(casefile.CaseFileError, match="is not in the case file"):
        casefile.resolve_refs({"$ref": "zz"}, entities, {})
