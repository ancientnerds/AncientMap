from __future__ import annotations

import json

import pytest

from pipeline.studio import casefile, episode, review, script, sites
from pipeline.studio.errors import StudioError
from pipeline.studio.paper import workspace
from tests.pipeline.studio import episode_fixtures as ef
from tests.pipeline.studio import script_fixtures as sf

PAPER = ef.PAPER
SITE = {
    "i": "383a0107-b7f7-4431-a752-590f3c0a42b2",
    "n": "Aartswoud",
    "la": 52.74459,
    "lo": 4.95355,
    "s": "ancient_nerds",
    "c": "Netherlands",
}
#: A raw import of another source: in the export, never shown (owner decision 15).
RAW = {"i": "raw-1", "n": "A raw import", "la": 1.0, "lo": 2.0, "s": "osm_historic"}
QUARRY = {"id": "p1", "label": "Baalbek quarry", "lat": 33.99917, "lng": 36.20028}
DISTRIBUTION = {
    "id": "g4",
    "kind": "globe",
    "scene": "distribution",
    "duration_s": 16,
    "places": [QUARRY],
    "site_ids": [SITE["i"]],
}


def _ws(tmp_path):
    return episode.EpisodeWorkspace(tmp_path / "episodes" / "baalbek-c5", "baalbek-c5")


def _init(tmp_path):
    ws = _ws(tmp_path)
    music = episode.music_config("bed.wav", "Music: Jonathan Carlile, Floating In Our Own Dreams")
    episode.init_episode(ws, paper=PAPER, topic_type="A", fmt="full", music=music)
    ef.ready_workspace(ws.root)
    ws.script.write_text(json.dumps(sf.script()), encoding="utf-8")
    return ws


def test_init_writes_defaults_and_refuses_a_second_init(tmp_path):
    ws = _init(tmp_path)
    data = episode.load_episode(ws)
    assert data["voice"] == {"id": "English_expressive_narrator", "speed": 1.0}
    assert data["music"]["duck"] == {
        "underNarrationDb": -12,
        "attackFrames": 6,
        "releaseFrames": 24,
    }
    assert (ws.root / "voice").is_dir() and (ws.root / "package").is_dir()
    with pytest.raises(StudioError, match="exists already"):
        episode.init_episode(ws, paper=None, topic_type="A", fmt="full", music=None)


def test_music_needs_a_credit():
    with pytest.raises(StudioError, match="needs its credit line"):
        episode.music_config("bed.wav", " ")


def test_episode_problems():
    assert episode.episode_problems({"slug": "x"}, "x")[0].startswith("episode.json keys")
    ws_data = {
        "version": 1,
        "slug": "x",
        "paper": None,
        "topic_type": "Z",
        "format": "long",
        "voice": {},
        "music": None,
        "title_candidates": [],
        "tags": [3],
        "allow_ai_imagery": "no",
    }
    assert episode.episode_problems(ws_data, "x") == [
        "topic_type must be one of ['A', 'B', 'C', 'D']",
        "format must be one of ['full', 'slice']",
        "voice must be {id, speed}",
        "tags must be a list of strings",
        "allow_ai_imagery must be a boolean",
    ]


def test_load_all_validates_with_words_and_captures(tmp_path):
    ws = _init(tmp_path)
    loaded = episode.load_all(ws, sf.REGISTRY)
    assert loaded.report.errors == [] and loaded.words is None and loaded.captures is None
    wrong = sf.mutated_script(lambda d: d["voice"].update(speed=1.06))
    ws.script.write_text(json.dumps(wrong), encoding="utf-8")
    assert (
        "script.json voice differs from episode.json voice"
        in episode.load_all(ws, sf.REGISTRY).report.errors
    )
    ws.script.write_text(json.dumps(sf.script()), encoding="utf-8")
    episode.require_valid(loaded, final=False)
    with pytest.raises(StudioError, match="not ready"):
        episode.require_valid(loaded, final=True)
    ws.words.write_text(json.dumps(sf.words_for(sf.script())), encoding="utf-8")
    (ws.voice_dir / "manifest.json").write_text(json.dumps(sf.voice_manifest()), encoding="utf-8")
    for cid, manifest in sf.stored_manifests().items():
        (ws.captures_dir / f"{cid}.json").write_text(json.dumps(manifest), encoding="utf-8")
    loaded = episode.load_all(ws, sf.REGISTRY)
    episode.require_valid(loaded, final=True)


def test_music_as_the_renderer_plays_it():
    bed = episode.music_config("bed.wav", "Music: X")
    assert episode.music_problems(bed) == []
    bad = {
        "file": "sub/bed.wav",
        "credit": " ",
        "gainDb": 2,
        "duck": {"underNarrationDb": 3, "attackFrames": 1.5, "releaseFrames": -1},
    }
    assert episode.music_problems(bad) == [
        "music.file must be a bare file name (in video-assets/music/)",
        "music.credit must name the track (it goes into the description)",
        "music.gainDb must be a number <= 0",
        "music.duck.underNarrationDb must be a number <= 0 (relative to gainDb)",
        "music.duck.attackFrames must be an integer >= 0",
        "music.duck.releaseFrames must be an integer >= 0",
    ]
    assert episode.music_problems({**bed, "duck": {"underNarrationDb": -12}}) == [
        "music.duck keys must be exactly ['attackFrames', 'releaseFrames', 'underNarrationDb']"
    ]


def test_a_partial_capture_defers_the_rest(tmp_path):
    ws = _init(tmp_path)
    ws.words.write_text(json.dumps(sf.words_for(sf.script())), encoding="utf-8")
    manifest = sf.stored_manifests()["platform-01"]
    (ws.captures_dir / "platform-01.json").write_text(json.dumps(manifest), encoding="utf-8")
    report = episode.load_all(ws, sf.REGISTRY).report
    assert report.errors == []
    assert any(d.startswith("b04: props not checked yet") for d in report.deferred)
    assert any(d.startswith("b05: props not checked yet") for d in report.deferred)


def _voiced(ws, data, hook_s=20.0):
    """voice/ as `episode voice` leaves it for `data`, the two hook beats `hook_s` long."""
    words, manifest = sf.words_for(data), sf.voice_manifest(data)
    for bid in ("b01", "b02"):
        words[bid]["duration_s"] = manifest[bid]["duration_s"] = hook_s
    ws.words.write_text(json.dumps(words), encoding="utf-8")
    (ws.voice_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _edit_b01(ws, spoken, display=None):
    def mutate(d):
        d["beats"][0].update(spoken=spoken, display=display or spoken)

    ws.script.write_text(json.dumps(sf.mutated_script(mutate)), encoding="utf-8")


def test_a_beat_edited_after_its_voice_is_estimated_not_measured(tmp_path):
    ws = _init(tmp_path)
    _voiced(ws, sf.script())
    report = episode.load_all(ws, sf.REGISTRY).report
    assert "hook is 41.9 s of screen time (measured); max 32 s" in report.errors
    # The author shortens the hook beat: its old 20 s are the length of the old text, so the
    # step that measures the new text (`episode voice`) must not be refused by them.
    _edit_b01(ws, "One person gives the scale.")
    report = episode.load_all(ws, sf.REGISTRY).report
    assert report.errors == []
    assert "b01: voice/b01.mp3 is stale; run `episode voice`" in report.deferred
    assert "chapter 'The stone': length is checked after the voice step" in report.deferred
    assert not [d for d in report.deferred if d.startswith("b02")]
    episode.require_valid(episode.load_all(ws, sf.REGISTRY), final=False)
    with pytest.raises(StudioError, match="not ready: b01: voice/b01.mp3 is stale"):
        episode.require_valid(episode.load_all(ws, sf.REGISTRY), final=True)


def test_an_estimated_hook_is_reported_as_estimated(tmp_path):
    ws = _init(tmp_path)
    _voiced(ws, sf.script())
    _edit_b01(ws, "One person gives the scale. " + "This block was cut in the quarry. " * 12)
    errors = episode.load_all(ws, sf.REGISTRY).report.errors
    # 5 + 7 * 12 = 89 words at 2.6 per second and 0.95 s of lead and tail, then b02's 20.95 s
    assert errors == ["hook is 56.1 s of screen time (estimated); max 32 s"]


def test_a_beat_the_voice_never_timed_is_estimated(tmp_path):
    ws = _init(tmp_path)
    _voiced(ws, sf.script(), hook_s=10.0)
    words = json.loads(ws.words.read_text(encoding="utf-8"))
    del words["b05"]
    ws.words.write_text(json.dumps(words), encoding="utf-8")
    report = episode.load_all(ws, sf.REGISTRY).report
    assert report.errors == []
    assert "b05: no word timings; run `episode voice`" in report.deferred


def test_a_voice_that_still_describes_the_script_is_measured(tmp_path):
    ws = _init(tmp_path)
    _voiced(ws, sf.script(), hook_s=10.0)
    report = episode.load_all(ws, sf.REGISTRY).report
    assert [d for d in report.deferred if "voice" in d or "chapter" in d] == []


def test_the_paper_link_is_checked(tmp_path):
    ws = _init(tmp_path)
    papers = ws.root.parent.parent
    ef.write_paper_workspace(papers, evidence_ids=("ev-02",), slug="the-megaliths-2")
    errors = episode.load_all(ws, sf.REGISTRY).report.errors
    assert "e1: paper_anchor ev-01 is not an evidence id of paper " + ef.REQ in errors
    assert (
        "episode.json paper slug 'the-megaliths' is not the published slug 'the-megaliths-2'"
        in errors
    )
    (papers / "papers" / ef.REQ / "evidence.json").unlink()
    errors = episode.load_all(ws, sf.REGISTRY).report.errors
    assert "e1: paper_anchor cannot be verified (no paper workspace)" in errors
    other = ef.mutated(paper__slug="another-paper")
    ef.write_casefile(ws.root, other)
    errors = episode.load_all(ws, sf.REGISTRY).report.errors
    assert "casefile.json paper differs from episode.json paper" in errors


@pytest.mark.parametrize("content", [{"ev-01": "x"}, ["ev-01"], [{"claim": "no id"}]])
def test_a_malformed_paper_evidence_file_is_a_problem_not_a_crash(tmp_path, content):
    """The paper workspace's evidence.json is Claude's working file: mid-edit it can be
    anything, and `episode check` reports it instead of raising."""
    ws = _init(tmp_path)
    (ws.paper_dir(ef.REQ) / "evidence.json").write_text(json.dumps(content), encoding="utf-8")
    errors = episode.load_all(ws, sf.REGISTRY).report.errors
    assert (
        f"e1: paper_anchor cannot be verified: papers/{ef.REQ}/evidence.json is not a list "
        "of evidence entries {id, ...}" in errors
    )


def test_the_paper_link_is_checked_both_ways(tmp_path):
    ws = _init(tmp_path)
    ef.write_casefile(ws.root, ef.mutated(paper=None))
    assert episode.load_all(ws, sf.REGISTRY).report.errors == [
        "casefile.json paper differs from episode.json paper"
    ]
    bare = _ws(tmp_path / "bare")
    episode.init_episode(bare, paper=None, topic_type="A", fmt="full", music=None)
    ef.ready_workspace(bare.root)
    bare.script.write_text(json.dumps(sf.script()), encoding="utf-8")
    assert episode.load_all(bare, sf.REGISTRY).report.errors == [
        "casefile.json paper differs from episode.json paper",
        "e1: paper_anchor ev-01 needs the paper in episode.json",
    ]
    ef.write_casefile(bare.root, ef.mutated(paper=None))
    assert episode.load_all(bare, sf.REGISTRY).report.errors == [
        "e1: paper_anchor ev-01 needs the paper in episode.json"
    ]
    ef.write_casefile(bare.root, ef.mutated(paper=None, evidence__0__paper_anchor=None))
    assert episode.load_all(bare, sf.REGISTRY).report.errors == []


def test_a_json_syntax_error_is_a_studio_error(tmp_path):
    """A hand-written file with a syntax error is refused by name, not with a traceback:
    __main__ turns a StudioError into `error: ...` and exit 2."""
    ws = _init(tmp_path)
    evidence = ws.paper_dir(ef.REQ) / "evidence.json"
    manifest = ws.captures_dir / "platform-01.json"
    for path in (ws.script, ws.config, evidence, manifest):
        before = path.read_text(encoding="utf-8") if path.exists() else None
        path.write_text('{"id": "x",}', encoding="utf-8")
        with pytest.raises(StudioError, match=rf"^{path.name} is not valid JSON: "):
            episode.load_all(ws, sf.REGISTRY)
        if before is None:
            path.unlink()
        else:
            path.write_text(before, encoding="utf-8")
    assert episode.load_all(ws, sf.REGISTRY).report.errors == []


def test_episode_reuses_the_shared_json_reader_and_number_check():
    """No copies: the paper workspace's read_json and script's number predicate."""
    assert episode.load_json is workspace.read_json
    assert episode.is_number is script.is_number
    assert not hasattr(episode, "_number") and not hasattr(script, "_number")


def test_an_unchecked_marker_blocks_the_episode(tmp_path):
    ws = _init(tmp_path)
    moved = ef.mutated(media__0__markers__0__box=[0.2, 0.5, 0.1, 0.3])
    ef.write_casefile(ws.root, moved)
    errors = episode.load_all(ws, sf.REGISTRY).report.errors
    assert errors == ["mk1: no accepted crop check hits for the current image and box"]


def _export(path, monkeypatch, entries):
    """A site export in the repo-root format, as sites.SITES_INDEX."""
    path.write_text(json.dumps({"sites": entries}), encoding="utf-8")
    monkeypatch.setattr(sites, "SITES_INDEX", path)


def test_site_ids_become_unlabelled_places_from_the_export(tmp_path, monkeypatch):
    _export(tmp_path / "index.json", monkeypatch, [SITE, {**SITE, "i": "other", "la": 1.0}, RAW])
    resolved = sites.resolve_capture_spec(DISTRIBUTION)
    assert "site_ids" not in resolved
    assert resolved["places"] == [QUARRY, {"id": SITE["i"], "lat": 52.74459, "lng": 4.95355}]
    platform = {"id": "platform-01", "kind": "platform"}
    assert sites.resolve_capture_spec(platform) is platform
    with pytest.raises(StudioError, match="capture g4: site nope is not in public/data/sites"):
        sites.resolve_capture_spec({**DISTRIBUTION, "site_ids": ["nope"]})
    with pytest.raises(
        StudioError,
        match="capture g4: site raw-1 comes from source osm_historic, not the curated "
        "ancient_nerds sites",
    ):
        sites.resolve_capture_spec({**DISTRIBUTION, "site_ids": ["raw-1"]})
    assert sites.site_country("m3", SITE["i"]) == "Netherlands"
    assert sites.site_country("m3", "other") == "Netherlands"


def test_a_mapbox_country_is_the_export_country_of_its_place(tmp_path, monkeypatch):
    ws = _init(tmp_path)
    ef.write_casefile(ws.root, ef.mutated(places__0__site_id=SITE["i"]))
    take = {"id": "m3", "kind": "globe", "scene": "mapbox_orbit", "lat": 33.99917}
    take.update(lng=36.20028, country="Lebanon")
    data = sf.mutated_script(lambda d: d["captures"].append(take))
    ws.script.write_text(json.dumps(data), encoding="utf-8")
    _export(tmp_path / "index.json", monkeypatch, [SITE])
    assert episode.load_all(ws, sf.REGISTRY).report.errors == [
        "capture m3: country Lebanon is not the site export's country of place p1"
    ]
    _export(tmp_path / "lebanon.json", monkeypatch, [{**SITE, "c": "Lebanon"}])
    assert episode.load_all(ws, sf.REGISTRY).report.errors == []


def test_a_missing_export_names_its_download(tmp_path, monkeypatch):
    monkeypatch.setattr(sites, "SITES_INDEX", tmp_path / "absent.json")
    with pytest.raises(
        StudioError,
        match="curl -sfR --create-dirs -o public/data/sites/index.json "
        "https://ancientnerds.com/data/sites/",
    ):
        sites.resolve_capture_spec(DISTRIBUTION)


def test_a_truncated_export_is_a_studio_error(tmp_path, monkeypatch):
    """An interrupted `curl -o` leaves half a file."""
    path = tmp_path / "index.json"
    path.write_text('{"sites": [{"i": "a", "la": 1', encoding="utf-8")
    monkeypatch.setattr(sites, "SITES_INDEX", path)
    with pytest.raises(StudioError, match="index.json is not valid JSON"):
        sites.resolve_capture_spec(DISTRIBUTION)


def test_a_take_belongs_to_the_export_it_was_recorded_from(tmp_path, monkeypatch):
    ws = _init(tmp_path)
    data = sf.mutated_script(lambda d: d["captures"].append(DISTRIBUTION))
    _export(tmp_path / "index.json", monkeypatch, [SITE])
    recorded = episode.capture_spec_sha256(sites.resolve_capture_spec(DISTRIBUTION))
    stored = {"id": "g4", "kind": "globe", "spec_sha256": recorded}
    (ws.captures_dir / "g4.json").write_text(json.dumps(stored), encoding="utf-8")
    assert list(episode.load_captures(ws, data)) == ["g4"]
    _export(tmp_path / "newer.json", monkeypatch, [{**SITE, "la": 52.7446}])
    assert episode.load_captures(ws, data) is None


def test_review_table_marks_findings_and_timing(tmp_path):
    cf = casefile.from_dict(ef.casefile())
    data = sf.mutated_script(lambda d: d["beats"][2].update(evidence=["e2"]))
    rep = script.validate_script(data, cf, sf.REGISTRY, slug="baalbek-c5", fmt="full")
    page = review.render_review(data, cf, None, rep)
    assert "(estimated)" in page
    assert "b03: evidence e2 is unverified, not verified" in page
    assert "shown: This stone weighs about 1,000 tonnes." in page
    assert '<span class="bad">unverified</span>' in page
    assert page.count("<tr>") == 1 + len(data["beats"])
