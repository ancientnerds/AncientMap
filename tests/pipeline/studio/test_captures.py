from __future__ import annotations

import json

import pytest

from pipeline.studio import captures, sites
from pipeline.studio.episode import EpisodeWorkspace, capture_spec_sha256, load_captures
from pipeline.studio.errors import StudioError
from tests.pipeline.studio import script_fixtures as sf

SITE = {
    "i": "383a0107-b7f7-4431-a752-590f3c0a42b2",
    "n": "Aartswoud",
    "la": 52.74459,
    "lo": 4.95355,
    "s": "ancient_nerds",
}
QUARRY = {"id": "p1", "label": "Baalbek quarry", "lat": 33.99917, "lng": 36.20028}
G4 = {
    "id": "g4",
    "kind": "globe",
    "scene": "distribution",
    "duration_s": 16,
    "places": [QUARRY],
    "site_ids": [SITE["i"]],
}


def _ws(tmp_path):
    return EpisodeWorkspace(tmp_path / "ep", "baalbek-c5")


def fake_platform(episode_dir, spec):
    path = episode_dir / "captures" / f"{spec['id']}.mp4"
    path.write_bytes(b"mp4")
    return sf.manifests()[spec["id"]]


def test_every_declared_capture_is_recorded_and_stored(tmp_path):
    ws = _ws(tmp_path)
    out = captures.record_captures(ws, sf.script(), recorders={"platform": fake_platform})
    assert sorted(out) == ["platform-01", "platform-02", "platform-03"]
    stored = json.loads((ws.captures_dir / "platform-02.json").read_text(encoding="utf-8"))
    assert stored["path"] == "captures/platform-02.mp4"
    assert stored["spec_sha256"] == capture_spec_sha256(sf.script()["captures"][1])


def test_a_manifest_of_an_edited_spec_counts_as_not_recorded(tmp_path):
    ws = _ws(tmp_path)
    captures.record_captures(ws, sf.script(), recorders={"platform": fake_platform})
    assert sorted(load_captures(ws, sf.script())) == ["platform-01", "platform-02", "platform-03"]
    edited = sf.mutated_script(lambda d: d["captures"][0]["actions"].append({"do": "wait", "s": 1}))
    assert sorted(load_captures(ws, edited)) == ["platform-02", "platform-03"]
    dropped = sf.mutated_script(lambda d: d["captures"].pop(2))
    assert sorted(load_captures(ws, dropped)) == ["platform-01", "platform-02"]


def test_only_records_the_named_captures(tmp_path):
    ws = _ws(tmp_path)
    out = captures.record_captures(
        ws, sf.script(), only=["platform-03"], recorders={"platform": fake_platform}
    )
    assert list(out) == ["platform-03"]
    with pytest.raises(StudioError, match=r"no such captures in script.json: \['nope'\]"):
        captures.record_captures(
            ws, sf.script(), only=["nope"], recorders={"platform": fake_platform}
        )


def test_bad_manifests_are_refused(tmp_path):
    ws = _ws(tmp_path)

    def liar(episode_dir, spec):
        return {**sf.manifests()[spec["id"]], "id": "other", "fps": None, "width": 0}

    def escaper(episode_dir, spec):
        return {**sf.manifests()[spec["id"]], "path": "captures/../x.mp4"}

    with pytest.raises(StudioError, match="is not a clean relative path"):
        captures.record_captures(
            ws, sf.script(), only=["platform-01"], recorders={"platform": escaper}
        )

    with pytest.raises(StudioError) as exc:
        captures.record_captures(
            ws, sf.script(), only=["platform-01"], recorders={"platform": liar}
        )
    msg = str(exc.value)
    assert "manifest id/kind differ from the capture spec" in msg
    assert "captures/platform-01.mp4 does not exist" in msg
    assert "a still has neither fps nor duration_s; a clip has both" in msg
    assert "width must be a positive integer" in msg


def test_a_manifest_string_the_brand_fonts_cannot_draw_is_refused(tmp_path):
    ws = _ws(tmp_path)

    def greek(episode_dir, spec):
        fake_platform(episode_dir, spec)
        return {**sf.manifests()[spec["id"]], "credits": ["© Κνωσός"]}

    with pytest.raises(
        StudioError,
        match=r'capture platform-01: manifest\.credits\[0\]: "Κ" \(U\+039A\) has no glyph',
    ):
        captures.record_captures(
            ws, sf.script(), only=["platform-01"], recorders={"platform": greek}
        )
    assert not (ws.captures_dir / "platform-01.json").exists()


def test_only_the_drawn_strings_of_a_page_are_glyph_checked(tmp_path):
    """Owner decision 32: a page's URL and its own <title> are not drawn (SourceViewer and the
    source credit show only its ASCII hostname); its credit is."""
    ws = _ws(tmp_path)
    data = sf.mutated_script(
        lambda d: d["captures"].append(
            {"id": "src1", "kind": "source", "url": "https://el.wikipedia.org/wiki/Κνωσός"}
        )
    )

    def page(credit):
        def record(episode_dir, spec):
            (episode_dir / "captures" / "src1.png").write_bytes(b"png")
            title = "Κνωσός - Βικιπαίδεια"  # the real page's <title>: a record, never drawn
            event = {"t": 0.0, "name": "page", "url": spec["url"], "title": title}
            return {
                "id": "src1",
                "kind": "source",
                "path": "captures/src1.png",
                "fps": None,
                "duration_s": None,
                "width": 2560,
                "height": 3000,
                "events": [event],
                "credits": [credit],
            }

        return record

    recorders = {"source": page("Source page: el.wikipedia.org")}
    assert list(captures.record_captures(ws, data, only=["src1"], recorders=recorders)) == ["src1"]
    with pytest.raises(StudioError, match=r'capture src1: manifest\.credits\[0\]: "Κ"'):
        captures.record_captures(
            ws, data, only=["src1"], recorders={"source": page("Source page: Κνωσός")}
        )


def test_a_failed_retake_leaves_the_capture_not_recorded(tmp_path):
    ws = _ws(tmp_path)
    captures.record_captures(
        ws, sf.script(), only=["platform-01"], recorders={"platform": fake_platform}
    )
    assert (ws.captures_dir / "platform-01.json").exists()

    def boom(episode_dir, spec):
        raise StudioError("boom")

    with pytest.raises(StudioError, match="^capture platform-01: boom$"):
        captures.record_captures(
            ws, sf.script(), only=["platform-01"], recorders={"platform": boom}
        )
    assert not (ws.captures_dir / "platform-01.json").exists()
    assert "platform-01" not in (load_captures(ws, sf.script()) or {})


def test_a_distribution_records_its_site_dots_resolved(tmp_path, monkeypatch):
    ws = _ws(tmp_path)
    export = tmp_path / "index.json"
    export.write_text(json.dumps({"sites": [SITE]}), encoding="utf-8")
    monkeypatch.setattr(sites, "SITES_INDEX", export)
    data = sf.mutated_script(lambda d: d["captures"].append(G4))
    seen = {}

    def globe(episode_dir, spec):
        seen["spec"] = spec
        (episode_dir / "captures" / "g4.mp4").write_bytes(b"mp4")
        return {
            "id": "g4",
            "kind": "globe",
            "path": "captures/g4.mp4",
            "fps": 60,
            "duration_s": 16.0,
            "width": 1920,
            "height": 1080,
            "events": [{"t": 1.0, "name": "place", "target": SITE["i"], "x": 10, "y": 20}],
            "credits": [],
        }

    captures.record_captures(ws, data, only=["g4"], recorders={"globe": globe})
    assert "site_ids" not in seen["spec"]
    assert seen["spec"]["places"] == [QUARRY, {"id": SITE["i"], "lat": 52.74459, "lng": 4.95355}]
    stored = json.loads((ws.captures_dir / "g4.json").read_text(encoding="utf-8"))
    assert stored["spec_sha256"] == capture_spec_sha256(seen["spec"])
    assert list(load_captures(ws, data)) == ["g4"]
    unknown = sf.mutated_script(lambda d: d["captures"].append({**G4, "site_ids": ["nope"]}))
    with pytest.raises(StudioError, match="capture g4: site nope is not in public/data/sites"):
        captures.record_captures(ws, unknown, only=["g4"], recorders={"globe": globe})


def test_the_contract_names_four_functions():
    assert captures.KIND_FUNCTIONS == {
        "platform": "record_platform",
        "globe": "record_globe",
        "source": "capture_source",
        "mapbox_topdown": "mapbox_topdown",
    }
