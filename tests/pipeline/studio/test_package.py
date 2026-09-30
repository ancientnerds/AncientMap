from __future__ import annotations

import json
import re

import pytest
from PIL import Image

from pipeline import research_html_renderer
from pipeline.research_html_renderer import video_clock
from pipeline.studio import casefile, package, render, timeline
from pipeline.studio.episode import load_all
from pipeline.studio.errors import StudioError
from pipeline.video.shorts_ledger import sha256_file
from tests.pipeline.studio import episode_fixtures as ef
from tests.pipeline.studio import script_fixtures as sf

EPISODE = {
    "paper": {"request_id": ef.REQ, "slug": "the-megaliths"},
    "format": "full",
    "music": {
        "file": "bed.wav",
        "credit": "Music: Jonathan Carlile, Floating In Our Own Dreams",
        "gainDb": -8,
        "duck": {},
    },
}


def _parts(seconds=5.0):
    data = sf.script()
    words = sf.words_for(data, seconds)
    cf = casefile.from_dict(ef.casefile())
    t = timeline.compile_timeline(data, words, cf, sf.manifests(), EPISODE)
    return data, words, cf, t


def test_clock():
    # The description's chapter and evidence times and the paper page's "Video at" links name
    # the same moments: one formatter prints both.
    assert package.video_clock is research_html_renderer.video_clock
    assert video_clock(0) == "0:00"
    assert video_clock(71.9) == "1:11"
    assert video_clock(3725) == "1:02:05"


def test_srt_uses_display_words_and_never_overlaps():
    data, words, _cf, t = _parts()
    text = package.srt(data, words, t)
    assert "1,000 tonnes." in text
    times = re.findall(r"(\d\d):(\d\d):(\d\d),(\d{3}) --> (\d\d):(\d\d):(\d\d),(\d{3})", text)
    spans = [
        (
            int(a) * 3600 + int(b) * 60 + int(c) + int(d) / 1000,
            int(e) * 3600 + int(f) * 60 + int(g) + int(h) / 1000,
        )
        for a, b, c, d, e, f, g, h in times
    ]
    assert all(start < end for start, end in spans)
    assert all(prev[1] <= nxt[0] for prev, nxt in zip(spans, spans[1:], strict=False))
    # the first cue starts after the 0.35 s lead
    assert spans[0][0] == pytest.approx(0.35, abs=0.01)


def test_chapters_follow_youtube_rules():
    _data, _words, _cf, t = _parts()
    assert package.chapters(t, "full") == [
        {"title": "The stone", "start_s": 0},
        {"title": "On the globe", "start_s": 11},
        {"title": "The verdict", "start_s": 29},
    ]
    assert package.chapters(t, "slice") == []
    short = {**t, "chapters": t["chapters"][:2]}
    with pytest.raises(StudioError, match="at least 3"):
        package.chapters(short, "full")
    _d, _w, _c, t2 = _parts(seconds=2.0)
    with pytest.raises(StudioError, match="shorter than 10 s"):
        package.chapters(t2, "full")


def test_description_carries_evidence_links_credits_and_disclosure():
    data, _words, cf, t = _parts()
    stamps = package.evidence_timestamps(data, cf, t)
    assert stamps == {"ev-01": 0}
    text = package.description(data, cf, t, EPISODE, package.chapters(t, "full"), stamps)
    assert text.startswith("This stone weighs about 1,000 tonnes.\n")
    assert "0:11 On the globe" in text
    assert (
        "0:00 The Stone of the Pregnant Woman weighs about 1,000 tonnes. "
        "https://ancientnerds.com/research/the-megaliths?utm_source=youtube&utm_medium=longform#ev-01"
    ) in text
    assert (
        "Image: Jane Doe (CC BY-SA 4.0) https://commons.wikimedia.org/wiki/File:Stone.jpg" in text
    )
    assert "© Mapbox © Maxar" in text
    assert text.endswith(package.DISCLOSURE)
    assert "<" not in text and ">" not in text


def test_description_byte_limit_counts_utf8_bytes():
    data, _words, cf, t = _parts()
    long_credit = "Music: " + "ä" * 2600  # 5,200 bytes, 2,607 characters
    episode = {**EPISODE, "music": {**EPISODE["music"], "credit": long_credit}}
    with pytest.raises(StudioError, match="UTF-8 bytes"):
        package.description(data, cf, t, episode, [], {})


def test_titles_and_tags():
    assert package.check_titles(["The Baalbek Stones"]) == ["The Baalbek Stones"]
    with pytest.raises(StudioError, match="title_candidates is empty"):
        package.check_titles([])
    with pytest.raises(StudioError, match="without < or >"):
        package.check_titles(["a <b>"])
    with pytest.raises(StudioError, match="tags take"):
        package.check_tags(["x" * 250, "y" * 250])


def test_one_title_is_measured_as_it_is_sent():
    # register-youtube sends the title unchanged, so the rule measures it unchanged: a trailing
    # space makes a 100-character title 101 characters on YouTube.
    longest = "x" * package.TITLE_MAX_CHARS
    assert package.check_title(longest) == longest
    for bad in (longest + " ", "", "   ", "a <b>", "a > b"):
        with pytest.raises(StudioError, match="without < or >"):
            package.check_title(bad)
    with pytest.raises(StudioError, match="without < or >"):
        package.check_titles(["The Baalbek Stones", longest + " "])


def test_failed_audit_marks_the_package_failed(tmp_path, monkeypatch):
    ws = ef.ready_episode(tmp_path, monkeypatch)
    ws.render_dir.mkdir(parents=True, exist_ok=True)
    (ws.render_dir / "audit.json").write_text(
        json.dumps(
            {"ok": False, "checks": [{"name": "loudness", "ok": False, "value": "-17 LUFS"}]}
        ),
        encoding="utf-8",
    )
    with pytest.raises(StudioError, match="package failed"):
        package.build_package(ws)
    failed = json.loads((ws.package_dir / "FAILED.json").read_text(encoding="utf-8"))
    assert failed == {"status": "failed", "reasons": ["loudness: -17 LUFS"]}


def _rendered(tmp_path, monkeypatch):
    """An episode as a passing `episode render` leaves it: timeline, video, stills, audit, ledger."""
    ws = ef.ready_episode(tmp_path, monkeypatch)
    data = json.loads(ws.config.read_text(encoding="utf-8"))
    data["title_candidates"] = [
        "The Baalbek Megaliths, Weighed",
        "Who Moved the 1,000-Tonne Stone?",
    ]
    data["tags"] = ["Baalbek", "archaeology"]
    ws.config.write_text(json.dumps(data), encoding="utf-8")
    timeline.build_timeline(ws)
    video = ws.render_dir / f"{ws.slug}.mp4"
    video.write_bytes(b"final")
    for k in (1, 2, 3):
        Image.new("RGB", (3840, 2160)).save(ws.render_dir / f"thumbnail_{k}_3840.png")
        Image.new("RGB", (1280, 720)).save(ws.render_dir / f"thumbnail_{k}_1280.jpg", quality=80)
    (ws.render_dir / "audit.json").write_text(
        json.dumps({"ok": True, "checks": []}), encoding="utf-8"
    )
    monkeypatch.setattr("pipeline.video.shorts_ledger.current_commit", lambda: "f" * 40)
    loaded = load_all(ws)
    t = json.loads(ws.timeline.read_text(encoding="utf-8"))
    ledger = {
        "row": render.ledger_row(ws, loaded.episode, loaded.script, t, video, "NVIDIA"),
        "timeline_sha256": sha256_file(ws.timeline),
        "words_sha256": sha256_file(ws.words),
    }
    (ws.render_dir / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    return ws


def _voiced(ws, data, seconds):
    """voice/words.json and manifest.json as `episode voice` leaves them for `data`."""
    ws.words.write_text(json.dumps(sf.words_for(data, seconds)), encoding="utf-8")
    manifest = sf.voice_manifest(data, seconds)
    (ws.voice_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_build_package_writes_every_file(tmp_path, monkeypatch):
    ws = _rendered(tmp_path, monkeypatch)
    out = package.build_package(ws)
    names = sorted(p.name for p in ws.package_dir.iterdir())
    assert names == sorted(
        [
            "baalbek-c5.mp4",
            "baalbek-c5.srt",
            "description.txt",
            "evidence_timestamps.json",
            "thumbnail_1.jpg",
            "thumbnail_1_3840.png",
            "thumbnail_2.jpg",
            "thumbnail_2_3840.png",
            "thumbnail_3.jpg",
            "thumbnail_3_3840.png",
            "titles.txt",
            "youtube.json",
        ]
    )
    yt = json.loads((ws.package_dir / "youtube.json").read_text(encoding="utf-8"))
    assert yt["thumbnails"] == ["thumbnail_1.jpg", "thumbnail_2.jpg", "thumbnail_3.jpg"]
    assert yt["title"] == "The Baalbek Megaliths, Weighed"
    assert yt["categoryId"] == 27 and yt["madeForKids"] is False
    assert yt["containsSyntheticMedia"] is False
    assert yt["captions"] == "baalbek-c5.srt"
    assert out["description_bytes"] <= 5000


def test_every_thumbnail_candidate_is_checked(tmp_path, monkeypatch):
    ws = _rendered(tmp_path, monkeypatch)
    (ws.render_dir / "thumbnail_2_1280.jpg").unlink()
    with pytest.raises(StudioError, match="render/thumbnail_2_1280.jpg is missing"):
        package.build_package(ws)
    Image.new("RGB", (1920, 1080)).save(ws.render_dir / "thumbnail_2_1280.jpg")
    with pytest.raises(StudioError, match="thumbnail_2_1280.jpg is 1920x1080, needs 1280x720"):
        package.build_package(ws)


def test_package_refuses_a_timeline_newer_than_the_render(tmp_path, monkeypatch):
    ws = _rendered(tmp_path, monkeypatch)
    rendered = ws.timeline.read_text(encoding="utf-8")
    ws.timeline.write_text(rendered.replace('"The stone"', '"The quarry stone"'), encoding="utf-8")
    with pytest.raises(StudioError, match="timeline.json changed since the render"):
        package.build_package(ws)
    ws.timeline.write_text(rendered, encoding="utf-8")
    (ws.render_dir / f"{ws.slug}.mp4").write_bytes(b"an older render")
    with pytest.raises(StudioError, match="is not the audited render"):
        package.build_package(ws)
    assert not (ws.package_dir / f"{ws.slug}.mp4").exists()


def test_package_refuses_a_script_revoiced_after_the_render(tmp_path, monkeypatch):
    # The owner's review loop: a line is changed and narrated again, the render is not. The
    # SRT and the hook sentence would carry the new line and the video the old one.
    ws = _rendered(tmp_path, monkeypatch)
    data = json.loads(ws.script.read_text(encoding="utf-8"))
    for key in ("spoken", "display"):
        data["beats"][0][key] = data["beats"][0][key].replace("This stone", "That stone")
    ws.script.write_text(json.dumps(data), encoding="utf-8")
    _voiced(ws, data, 4.6)
    with pytest.raises(StudioError, match=r"script\.json changed since the render"):
        package.build_package(ws)
    assert list(ws.package_dir.iterdir()) == []


def test_package_refuses_words_retimed_after_the_render(tmp_path, monkeypatch):
    # The same script narrated again (a lost mp3, a new take): other word times than the video's.
    ws = _rendered(tmp_path, monkeypatch)
    _voiced(ws, json.loads(ws.script.read_text(encoding="utf-8")), 4.6)
    with pytest.raises(StudioError, match=r"voice/words\.json changed since the render"):
        package.build_package(ws)
    assert list(ws.package_dir.iterdir()) == []


def test_package_refuses_a_casefile_changed_after_the_render(tmp_path, monkeypatch):
    # The description's evidence lines quote the case file; the video shows the rendered one.
    ws = _rendered(tmp_path, monkeypatch)
    rendered = ws.casefile.read_text(encoding="utf-8")
    edited = rendered.replace("weighs about 1,000 tonnes.", "weighs about 1,242 tonnes.")
    assert edited != rendered
    ws.casefile.write_text(edited, encoding="utf-8")
    with pytest.raises(StudioError, match=r"casefile\.json changed since the render"):
        package.build_package(ws)
    assert list(ws.package_dir.iterdir()) == []


def test_package_credits_only_the_music_the_render_mixed(tmp_path, monkeypatch):
    ws = _rendered(tmp_path, monkeypatch)
    data = json.loads(ws.config.read_text(encoding="utf-8"))
    # Titles, tags and the wording of the credit are the owner's after the render.
    data["title_candidates"] = ["Who Moved the 1,000-Tonne Stone?"]
    data["tags"] = ["Baalbek"]
    data["music"]["credit"] = "Music: X (CC BY 4.0)"
    ws.config.write_text(json.dumps(data), encoding="utf-8")
    package.build_package(ws)
    yt = json.loads((ws.package_dir / "youtube.json").read_text(encoding="utf-8"))
    assert yt["title"] == "Who Moved the 1,000-Tonne Stone?" and yt["tags"] == ["Baalbek"]
    assert "Music: X (CC BY 4.0)" in yt["description"]
    # Another track would be credited for a mix the video does not carry.
    data["music"]["file"] = "other.wav"
    ws.config.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(StudioError, match=r"music/other\.wav, the render mixed music/bed\.wav"):
        package.build_package(ws)
    data["music"] = None
    ws.config.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(StudioError, match=r"episode\.json music is none, the render mixed"):
        package.build_package(ws)
