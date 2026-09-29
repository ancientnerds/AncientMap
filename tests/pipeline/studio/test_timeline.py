from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.studio import casefile, episode, timeline
from pipeline.studio.errors import StudioError
from tests.pipeline.studio import episode_fixtures as ef
from tests.pipeline.studio import script_fixtures as sf

#: The compiled fixture episode, committed: stream D's video/test/contract.test.ts parses it.
GOLDEN = Path(__file__).with_name("golden_timeline.json")
EPISODE = {
    "music": {
        "file": "bed.wav",
        "credit": "Music: X",
        "gainDb": -8,
        "duck": {"underNarrationDb": -12, "attackFrames": 6, "releaseFrames": 24},
    }
}


def _compile(seconds=5.0):
    data = sf.script()
    return timeline.compile_timeline(
        data,
        sf.words_for(data, seconds),
        casefile.from_dict(ef.casefile()),
        sf.manifests(),
        EPISODE,
    )


def test_scene_frames_follow_min_lead_speech_tail():
    t = _compile()
    # max(3.0, 0.35 + 5.0 + 0.6) = 5.95 s -> 357 frames at 60 fps
    assert [s["durationInFrames"] for s in t["scenes"]] == [357] * 9
    assert [s["from"] for s in t["scenes"]][:3] == [0, 357, 714]
    assert t["durationInFrames"] == 9 * 357
    assert (t["fps"], t["width"], t["height"], t["version"]) == (60, 1920, 1080, 1)


def test_narration_starts_after_the_lead_and_cues_land_on_their_word():
    t = _compile()
    assert t["audio"]["narration"][0] == {"src": "voice/b01.mp3", "from": 21}
    assert t["audio"]["narration"][1] == {"src": "voice/b02.mp3", "from": 357 + 21}
    # "person" is display token 7 of 11 spread over 5 s: 7 * 5 / 11 = 3.1818 s -> 191 frames
    assert t["scenes"][0]["cues"] == [{"frame": 21 + 191, "do": "show", "target": "mk1"}]
    status = t["scenes"][5]["cues"][0]
    assert set(status) == {"frame", "do", "target", "value"} and status["value"] == "weakened"
    meter = t["scenes"][6]["cues"][0]
    assert set(meter) == {"frame", "do", "target", "value"} and meter["value"] == [70, 30]


def test_captions_only_for_hook_beats_uppercase_and_non_overlapping():
    t = _compile()
    texts = [c["text"] for c in t["captions"]]
    assert texts[:6] == ["THIS", "STONE", "WEIGHS", "ABOUT", "1,000", "TONNES."]
    assert len(texts) == 11 + 9
    assert all(c["to"] > c["from"] for c in t["captions"])
    assert all(a["to"] <= b["from"] for a, b in zip(t["captions"], t["captions"][1:], strict=False))
    assert t["captions"][-1]["to"] <= 2 * 357


def test_props_resolve_to_public_dir_paths():
    t = _compile()
    assert t["scenes"][0]["props"]["image"]["src"] == "media/stone_person.jpg"
    assert t["scenes"][2]["props"]["clip"]["src"] == "captures/platform-01.mp4"


def test_ticker_chapters_credits_and_music():
    t = _compile()
    assert t["ticker"]["evidence"] == [{"frame": 0, "n": 1}]
    assert t["chapters"] == [
        {"title": "The stone", "frame": 0},
        {"title": "On the globe", "frame": 714},
        {"title": "The verdict", "frame": 1785},
    ]
    assert {"sceneId": "b01", "text": "Photo: Jane Doe (CC BY-SA 4.0)"} in t["credits"]
    assert [c for c in t["credits"] if c["sceneId"] == "b03"] == [
        {"sceneId": "b03", "text": "© Mapbox © Maxar"}
    ]
    assert t["audio"]["music"] == {
        "src": "music/bed.wav",
        "gainDb": -8,
        "duck": {"underNarrationDb": -12, "attackFrames": 6, "releaseFrames": 24},
    }


def test_script_and_timeline_list_captures_with_the_case_file_walker():
    """The capture credits script.py checks are the ones the timeline emits: both modules take
    a beat's capture ids from casefile.capture_ids_in, neither keeps a copy of its own."""
    from pipeline.studio import script

    assert timeline.capture_ids_in is casefile.capture_ids_in
    assert script.capture_ids_in is casefile.capture_ids_in


def test_script_and_timeline_count_a_scene_with_one_scene_frames():
    """A clip `episode script` accepts is one the renderer takes: timeline.py emits the scene
    length script.scene_frames counts and keeps no frame rounding of its own. 8.3 s is
    498.00000000000006 frames in floats; both sides make it 498."""
    from pipeline.studio import script

    assert timeline.scene_frames is script.scene_frames
    data = sf.mutated_script(lambda d: d["beats"][2].update(min_s=8.3))
    words = sf.words_for(data)
    cf = casefile.from_dict(ef.casefile())
    t = timeline.compile_timeline(data, words, cf, sf.manifests(), EPISODE)
    frames = t["scenes"][2]["durationInFrames"]
    assert frames == 498

    def clip_errors(clip_frames):
        captures = sf.manifests()
        captures["platform-01"]["duration_s"] = clip_frames / 60
        report = script.validate_script(
            data, cf, sf.REGISTRY, slug="baalbek-c5", fmt="full", words=words, captures=captures
        )
        return [e for e in report.errors if "record a longer take" in e]

    assert clip_errors(frames) == []
    assert clip_errors(frames - 1) == [
        f"b03: capture platform-01 is {497 / 60} s long; the scene needs 8.300 s from 0 s "
        "(record a longer take or shorten the beat)"
    ]


def test_missing_words_are_an_error():
    data = sf.script()
    words = sf.words_for(data)
    del words["b03"]
    with pytest.raises(StudioError, match="b03: no word timings"):
        timeline.compile_timeline(
            data, words, casefile.from_dict(ef.casefile()), sf.manifests(), EPISODE
        )


def test_a_cue_lands_on_its_whole_word_not_inside_an_earlier_one():
    data = sf.mutated_script(lambda d: d["beats"][0]["cues"][0].update(at_word="one"))
    t = timeline.compile_timeline(
        data, sf.words_for(data), casefile.from_dict(ef.casefile()), sf.manifests(), EPISODE
    )
    # "One" is display token 6 of 11 ("stone", token 1, only contains the letters):
    # 6 * 5 / 11 = 2.727 s -> 164 frames after the lead
    assert t["scenes"][0]["cues"][0]["frame"] == 21 + round(6 * 5 / 11 * 60) == 185


def test_stale_words_and_cues_outside_their_scene_are_refused():
    data = sf.script()
    words = sf.words_for(data)
    data["beats"][0]["display"] = "This stone weighs about 1000 tonnes. One person gives the scale."
    cf = casefile.from_dict(ef.casefile())
    with pytest.raises(StudioError, match="b01: words.json was aligned to another display text"):
        timeline.compile_timeline(data, words, cf, sf.manifests(), EPISODE)
    data = sf.script()
    words = sf.words_for(data)
    words["b01"]["words"][7]["s"] = 50.0  # "person", the cue word
    with pytest.raises(StudioError, match=r"b01 cue 1: frame 3021 outside the scene \[0, 357\)"):
        timeline.compile_timeline(data, words, cf, sf.manifests(), EPISODE)


def test_build_timeline_refuses_before_voice(tmp_path, monkeypatch):
    ws = episode.EpisodeWorkspace(tmp_path / "episodes" / "baalbek-c5", "baalbek-c5")
    episode.init_episode(ws, paper=ef.PAPER, topic_type="A", fmt="full", music=None)
    ef.ready_workspace(ws.root)
    ws.script.write_text(json.dumps(sf.script()), encoding="utf-8")
    monkeypatch.setattr(episode, "load_registry", lambda: sf.REGISTRY)
    with pytest.raises(StudioError, match="not ready"):
        timeline.build_timeline(ws)
    ws.words.write_text(json.dumps(sf.words_for(sf.script())), encoding="utf-8")
    for cid, manifest in sf.stored_manifests().items():
        (ws.captures_dir / f"{cid}.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(StudioError, match="voice/manifest.json does not exist"):
        timeline.build_timeline(ws)
    stale = sf.voice_manifest()
    stale["b02"]["speed"] = 1.06
    (ws.voice_dir / "manifest.json").write_text(json.dumps(stale), encoding="utf-8")
    with pytest.raises(StudioError, match="b02: voice/b02.mp3 is stale"):
        timeline.build_timeline(ws)
    (ws.voice_dir / "manifest.json").write_text(json.dumps(sf.voice_manifest()), encoding="utf-8")
    t = timeline.build_timeline(ws)
    assert json.loads(ws.timeline.read_text(encoding="utf-8")) == t
    assert t["audio"]["music"] is None


def test_thumbnail_candidates_compile_to_frames_before_any_verdict():
    t = _compile()
    # b01 60 % of 357, b04 from 3 * 357 plus 50 %, b06 from 5 * 357 plus 10 %
    assert t["thumbnails"] == [
        {"frame": 214, "text": "Who moved it?"},
        {"frame": 1071 + 178, "text": "A thousand tonnes?"},
        {"frame": 1785 + 35, "text": "Lifted by hand?"},
    ]
    # the status cue of b06 ("measured") sits at frame 1785 + 21 + 86
    assert timeline.verdict_frame(t) == 1892
    roles = {"b05": "twist", "b07": "verdict", "b08": "change_mind"}
    assert timeline.thumbnail_problem(t, roles, 1891) is None
    assert timeline.thumbnail_problem(t, roles, 1892) == (
        "frame 1892 is at or after the first verdict cue (frame 1892): a thumbnail never "
        "shows the answer"
    )
    assert timeline.thumbnail_problem(t, roles, 1500) == (
        "frame 1500 lies in beat b05 (twist): a thumbnail never shows the answer"
    )
    assert timeline.thumbnail_problem(t, roles, 9 * 357) == (
        "frame 3213 is not a frame of the episode (0 to 3212)"
    )


def test_a_thumbnail_after_the_verdict_cue_in_its_beat_is_refused():
    data = sf.script()
    data["thumbnails"][2]["at"] = 0.5  # 1785 + 178 = 1963, after the status cue at 1892
    with pytest.raises(StudioError, match=r"thumbnails\[2\]: frame 1963 is at or after the first"):
        timeline.compile_timeline(
            data, sf.words_for(data), casefile.from_dict(ef.casefile()), sf.manifests(), EPISODE
        )


def test_golden_timeline_is_current():
    """Regenerate golden_timeline.json with the command of Task 21 Step 4 when the compiler's
    output changes on purpose; stream D's contract test must then still pass on it."""
    assert json.loads(GOLDEN.read_text(encoding="utf-8")) == json.loads(json.dumps(_compile()))
