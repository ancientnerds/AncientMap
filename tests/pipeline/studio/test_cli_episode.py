from __future__ import annotations

import argparse
import functools
import json
import re
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from pipeline.lyra.theo_publishing import poster_web_path
from pipeline.studio import __main__ as cli
from pipeline.studio import cli_episode, config, doctor, episode, package, remote, voice
from pipeline.studio.errors import StudioError
from tests.pipeline.studio import episode_fixtures as ef
from tests.pipeline.studio import script_fixtures as sf


@pytest.fixture(autouse=True)
def _no_env_file(monkeypatch):
    monkeypatch.setattr(config, "load_env", lambda: None)


def test_every_episode_command_and_doctor_are_registered():
    parser = cli.build_parser()
    for command in (
        ["episode", "init", "baalbek-c5", "--topic", "A"],
        ["episode", "markers-export", "baalbek-c5"],
        ["episode", "markers-import", "baalbek-c5"],
        ["episode", "check", "baalbek-c5"],
        ["episode", "review", "baalbek-c5"],
        ["episode", "voice", "baalbek-c5"],
        ["episode", "capture", "baalbek-c5", "--only", "platform-01"],
        ["episode", "timeline", "baalbek-c5"],
        ["episode", "render", "baalbek-c5"],
        ["episode", "thumbnail", "baalbek-c5", "--candidate", "2", "--frame", "1200"],
        ["episode", "package", "baalbek-c5"],
        [
            "episode",
            "register-youtube",
            "baalbek-c5",
            "--youtube-id",
            "dQw4w9WgXcQ",
            "--title",
            "Who Really Moved the Baalbek Stones?",
            "--published-at",
            "2026-10-01T18:00:00+00:00",
            "--poster",
            "1",
        ],
        ["doctor"],
        ["doctor", "--fix-gpu"],
    ):
        assert callable(parser.parse_args(command).func)


def test_register_youtube_needs_one_of_the_three_candidates_as_poster():
    base = ["episode", "register-youtube", "x-1", "--youtube-id", "dQw4w9WgXcQ"]
    base += ["--title", "t", "--published-at", "2026-10-01T18:00:00+00:00"]
    for extra in ([], ["--poster", "4"]):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args([*base, *extra])


def test_init_without_music_then_check(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    assert (
        cli.main(
            [
                "episode",
                "init",
                "baalbek-c5",
                "--topic",
                "A",
                "--music",
                "none",
                "--paper",
                ef.REQ,
                "--paper-slug",
                "the-megaliths",
            ]
        )
        == 0
    )
    out = json.loads(capsys.readouterr().out)
    assert out["episode"]["music"] is None
    root = tmp_path / "episodes" / "baalbek-c5"
    ef.ready_workspace(root)
    (root / "script.json").write_text(json.dumps(sf.script()), encoding="utf-8")
    monkeypatch.setattr("pipeline.studio.episode.load_registry", lambda: sf.REGISTRY)
    assert cli.main(["episode", "check", "baalbek-c5"]) == 0
    assert json.loads(capsys.readouterr().out)["errors"] == []


def test_init_paper_needs_its_slug(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    assert (
        cli.main(["episode", "init", "x-1", "--topic", "A", "--music", "none", "--paper", ef.REQ])
        == 2
    )
    assert "--paper needs --paper-slug" in capsys.readouterr().err


def test_init_reads_the_published_slug(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    ef.write_paper_workspace(tmp_path, slug="the-megaliths-95fa3798")
    base = ["episode", "init", "x-1", "--topic", "A", "--music", "none", "--paper", ef.REQ]
    assert cli.main(base) == 0
    assert json.loads(capsys.readouterr().out)["episode"]["paper"] == {
        "request_id": ef.REQ,
        "slug": "the-megaliths-95fa3798",
    }
    assert cli.main([*base[:2], "x-2", *base[3:], "--paper-slug", "the-megaliths"]) == 2
    assert "is not the published slug 'the-megaliths-95fa3798'" in capsys.readouterr().err


def test_an_outcome_that_did_not_publish_names_no_slug(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    root = ef.write_paper_workspace(tmp_path)
    for record in (
        {"apply": {"ok": False, "slug": "x"}, "apply_exit_code": 1},
        {"apply": {"ok": False, "error": "e"}, "apply_exit_code": 3},
    ):
        (root / "publish_outcome.json").write_text(json.dumps(record), encoding="utf-8")
        with pytest.raises(StudioError, match="--paper needs --paper-slug"):
            cli_episode.paper_ref(ef.REQ, None)


class Narrator:
    """MiniMax and whisper replaced: `seconds` is how long each beat's narration comes out."""

    def __init__(self, script_path):
        self.script_path = script_path
        self.seconds = {"b01": 20.0, "b02": 20.0}
        self.narrated = []
        self.deaf = set()  # beats whose narration whisper recognises no word of

    def quota(self):
        return 99, 40

    def synth(self, text, out, voice_id, speed):
        out.write_bytes(b"mp3")
        self.narrated.append(out.stem)
        return self.seconds.get(out.stem, 5.0)

    def transcribe(self, audio):
        if audio.stem in self.deaf:
            return []
        beats = json.loads(self.script_path.read_text(encoding="utf-8"))["beats"]
        spoken = next(b["spoken"] for b in beats if b["id"] == audio.stem)
        return [(w, i * 0.2, i * 0.2 + 0.15) for i, w in enumerate(spoken.split())]


def _narrated_workspace(monkeypatch, tmp_path):
    """A script `episode voice` can be run on with Narrator standing in for MiniMax and whisper."""
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    monkeypatch.setattr("pipeline.studio.episode.load_registry", lambda: sf.REGISTRY)
    ws = episode.EpisodeWorkspace(tmp_path / "episodes" / "baalbek-c5", "baalbek-c5")
    episode.init_episode(ws, paper=ef.PAPER, topic_type="A", fmt="full", music=None)
    ef.ready_workspace(ws.root)
    ws.script.write_text(json.dumps(sf.script()), encoding="utf-8")
    narrator = Narrator(ws.script)
    monkeypatch.setattr(
        cli_episode,
        "voice_episode",
        functools.partial(
            voice.voice_episode,
            quota=narrator.quota,
            synth=narrator.synth,
            transcribe=narrator.transcribe,
        ),
    )
    return ws, narrator


def _shorten_b01(ws):
    def shorter(d):
        d["beats"][0].update(
            spoken="One person gives the scale.", display="One person gives the scale."
        )

    ws.script.write_text(json.dumps(sf.mutated_script(shorter)), encoding="utf-8")


def test_voice_measures_the_beats_the_author_fixed_after_the_first_voice(
    monkeypatch, tmp_path, capsys
):
    """The loop the studio-video skill prescribes: `episode voice` exits 1 with what the real
    timings broke (a hook over 32 s), the author shortens the beat, `episode voice` runs again."""
    ws, narrator = _narrated_workspace(monkeypatch, tmp_path)
    assert cli.main(["episode", "voice", "baalbek-c5"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["errors"] == ["hook is 41.9 s of screen time (measured); max 32 s"]
    assert len(narrator.narrated) == 9

    _shorten_b01(ws)
    narrator.seconds["b01"] = 2.0
    assert cli.main(["episode", "voice", "baalbek-c5"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["errors"] == []
    assert narrator.narrated[9:] == ["b01"]
    assert json.loads(ws.words.read_text(encoding="utf-8"))["b01"]["duration_s"] == 2.0


def test_voice_that_failed_to_time_the_fixed_beat_runs_again_without_narrating_it_twice(
    monkeypatch, tmp_path, capsys
):
    """The retry the runbook prescribes after `the display words cannot be timed`: the manifest
    already holds the new narration of b01 while words.json still holds the old 20 s, and those
    20 s must not refuse the step that times the new text."""
    ws, narrator = _narrated_workspace(monkeypatch, tmp_path)
    assert cli.main(["episode", "voice", "baalbek-c5"]) == 1
    capsys.readouterr()

    _shorten_b01(ws)
    narrator.seconds["b01"] = 2.0
    narrator.deaf.add("b01")
    assert cli.main(["episode", "voice", "baalbek-c5"]) == 2
    err = capsys.readouterr().err
    assert "b01: the display words cannot be timed against voice/b01.mp3" in err
    assert narrator.narrated[9:] == ["b01"]
    assert json.loads(ws.words.read_text(encoding="utf-8"))["b01"]["duration_s"] == 20.0

    narrator.deaf.clear()
    assert cli.main(["episode", "voice", "baalbek-c5"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["errors"] == []
    assert narrator.narrated[9:] == ["b01"]  # b01 was timed, not narrated again
    words = json.loads(ws.words.read_text(encoding="utf-8"))
    assert words["b01"]["duration_s"] == 2.0
    assert [w["w"] for w in words["b01"]["words"]] == "One person gives the scale.".split()


def test_check_reports_the_beat_whose_voice_is_stale_as_waiting_not_as_broken(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    monkeypatch.setattr("pipeline.studio.episode.load_registry", lambda: sf.REGISTRY)
    ws = ef.ready_episode(tmp_path, monkeypatch)
    words, manifest = sf.words_for(sf.script()), sf.voice_manifest()
    for bid in ("b01", "b02"):
        words[bid]["duration_s"] = manifest[bid]["duration_s"] = 20.0
    ws.words.write_text(json.dumps(words), encoding="utf-8")
    (ws.voice_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert cli.main(["episode", "check", "baalbek-c5"]) == 1
    assert json.loads(capsys.readouterr().out)["errors"] == [
        "hook is 41.9 s of screen time (measured); max 32 s"
    ]

    def shorter(d):
        d["beats"][0].update(
            spoken="One person gives the scale.", display="One person gives the scale."
        )

    ws.script.write_text(json.dumps(sf.mutated_script(shorter)), encoding="utf-8")
    assert cli.main(["episode", "check", "baalbek-c5"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["errors"] == []
    assert "b01: voice/b01.mp3 is stale; run `episode voice`" in out["deferred"]


def _published_package(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    ws = ef.ready_episode(tmp_path, monkeypatch)
    (ws.package_dir / "baalbek-c5.mp4").write_bytes(b"final")
    from pipeline.video.shorts_ledger import sha256_file

    (ws.render_dir / "ledger.json").write_text(
        json.dumps({"row": {"video_sha256": sha256_file(ws.package_dir / "baalbek-c5.mp4")}}),
        encoding="utf-8",
    )
    (ws.package_dir / "evidence_timestamps.json").write_text(
        json.dumps({"ev-01": 0}), encoding="utf-8"
    )
    for k in (1, 2, 3):
        Image.new("RGB", (1280, 720), (k, k, k)).save(ws.package_dir / f"thumbnail_{k}.jpg")
    return ws


def _recording_remote(monkeypatch, answer):
    """remote.run_module and the verified upload, logged in one list of events."""
    events = []

    def fake_run(module, args, *, stdin=None, timeout):
        events.append((module, args, json.loads(stdin)))
        return answer(module, args)

    def fake_upload(request_id, files, timeout=900):
        events.append(("upload", request_id, [(p.name, p.read_bytes()) for p in files]))

    monkeypatch.setattr(remote, "run_module", fake_run)
    monkeypatch.setattr(remote, "upload_research_images", fake_upload)
    return events


def test_register_youtube_proves_the_paper_then_ledger_then_paper(monkeypatch, tmp_path):
    ws = _published_package(tmp_path, monkeypatch)
    ok = remote.RemoteResult(0, b'{"ok": true}', "")
    events = _recording_remote(monkeypatch, lambda module, args: ok)
    title = "Who Really Moved the Baalbek Stones?"
    out = cli_episode.register_youtube(
        "baalbek-c5", "dQw4w9WgXcQ", title, "2026-10-01T18:00:00+00:00", 2
    )
    assert out == {"ledger": {"ok": True}, "paper": {"ok": True}}
    poster = poster_web_path(ef.REQ, "dQw4w9WgXcQ")
    thumb = (ws.package_dir / "thumbnail_2.jpg").read_bytes()
    assert [(e[0], e[1]) for e in events] == [
        ("pipeline.lyra.theo_publish", ["--register-video", "--dry-run"]),
        ("upload", ef.REQ),
        ("pipeline.lyra.theo_publish", ["--register-video", "--dry-run"]),
        ("pipeline.studio.ledger_cli", ["--publish"]),
        ("pipeline.lyra.theo_publish", ["--register-video"]),
    ]
    assert "poster" not in events[0][2]
    assert events[1][2] == [("video_dQw4w9WgXcQ.jpg", thumb)]
    assert events[2][2]["poster"] == events[4][2]["poster"] == poster
    assert events[4][2]["title"] == title
    assert events[4][2]["evidence_timestamps"] == {"ev-01": 0}
    assert events[4][2]["version"] == 1 and events[4][2]["writer"]["model"] == "claude-opus-5-5"


def test_a_refused_paper_dry_run_leaves_the_ledger_untouched(monkeypatch, tmp_path):
    _published_package(tmp_path, monkeypatch)
    refused = {"ok": False, "gates": {"evidence_refs": {"passed": False}}}
    answer = remote.RemoteResult(1, json.dumps(refused).encode("utf-8"), "")
    events = _recording_remote(monkeypatch, lambda module, args: answer)
    with pytest.raises(StudioError, match=r"failing gates \['evidence_refs'\]"):
        cli_episode.register_youtube(
            "baalbek-c5", "dQw4w9WgXcQ", "Baalbek", "2026-10-01T18:00:00+00:00", 1
        )
    assert [e[0] for e in events] == ["pipeline.lyra.theo_publish"]  # no upload, no ledger
    with pytest.raises(StudioError, match="1-100 characters without < or >"):
        cli_episode.register_youtube(
            "baalbek-c5", "dQw4w9WgXcQ", "<b>", "2026-10-01T18:00:00+00:00", 1
        )


def test_register_youtube_refuses_the_title_episode_package_refuses(monkeypatch, tmp_path):
    # One title rule (package.check_title): a 100-character title with a trailing space is 101
    # characters in theo_publish and on YouTube, so it stops before any remote step.
    _published_package(tmp_path, monkeypatch)
    events = _recording_remote(monkeypatch, lambda module, args: pytest.fail("no remote step"))
    title = "x" * package.TITLE_MAX_CHARS + " "
    with pytest.raises(StudioError, match="1-100 characters without < or >"):
        cli_episode.register_youtube(
            "baalbek-c5", "dQw4w9WgXcQ", title, "2026-10-01T18:00:00+00:00", 1
        )
    assert events == []
    with pytest.raises(StudioError, match="1-100 characters without < or >"):
        package.check_titles([title])


def test_a_failed_apply_after_the_ledger_names_the_way_to_finish(monkeypatch, tmp_path):
    ws = _published_package(tmp_path, monkeypatch)

    def answer(module, args):
        if args == ["--register-video"]:
            return remote.RemoteResult(3, b'{"ok": false, "error": "row changed"}', "")
        return remote.RemoteResult(0, b'{"ok": true}', "")

    events = _recording_remote(monkeypatch, answer)
    with pytest.raises(StudioError) as exc:
        cli_episode.register_youtube(
            "baalbek-c5", "dQw4w9WgXcQ", "Baalbek", "2026-10-01T18:00:00+00:00", 3
        )
    message = str(exc.value)
    assert "the row changed underneath" in message
    assert "the ledger is written; finish with: python -m pipeline.studio paper register-video" in (
        message
    )
    assert f"--poster {(ws.package_dir / 'thumbnail_3.jpg').as_posix()}" in message
    assert f"--timestamps {(ws.package_dir / 'evidence_timestamps.json').as_posix()}" in message
    assert [e[0] for e in events][-2:] == [
        "pipeline.studio.ledger_cli",
        "pipeline.lyra.theo_publish",
    ]


def test_register_youtube_refuses_a_different_file(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    root = tmp_path / "episodes" / "baalbek-c5"
    (root / "render").mkdir(parents=True)
    (root / "package").mkdir()
    (root / "package" / "baalbek-c5.mp4").write_bytes(b"other")
    (root / "render" / "ledger.json").write_text(
        json.dumps({"row": {"video_sha256": "0" * 64}}), encoding="utf-8"
    )
    with pytest.raises(StudioError, match="not the file the ledger recorded"):
        cli_episode.register_youtube(
            "baalbek-c5", "dQw4w9WgXcQ", "Baalbek", "2026-10-01T18:00:00+00:00", 1
        )


def test_register_youtube_needs_the_packaged_candidate(monkeypatch, tmp_path):
    ws = _published_package(tmp_path, monkeypatch)
    (ws.package_dir / "thumbnail_2.jpg").unlink()
    with pytest.raises(StudioError, match=r"package/thumbnail_2\.jpg does not exist"):
        cli_episode.register_youtube(
            "baalbek-c5", "dQw4w9WgXcQ", "Baalbek", "2026-10-01T18:00:00+00:00", 2
        )


def test_doctor_reports_the_site_export_and_its_age(monkeypatch, tmp_path):
    from pipeline.studio import sites

    monkeypatch.setattr(sites, "SITES_INDEX", tmp_path / "index.json")
    probe = doctor._site_export()
    assert not probe.ok and probe.detail.startswith("missing: download it from the repo root")
    assert "curl -sfR --create-dirs -o public/data/sites/index.json" in probe.detail
    (tmp_path / "index.json").write_text('{"sites": []}', encoding="utf-8")
    probe = doctor._site_export()
    assert probe.ok and re.search(r"from \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC", probe.detail)


def test_doctor_names_the_node_modules_or_the_install_command(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor, "VIDEO_DIR", tmp_path)
    assert doctor._node_modules() == doctor.Probe(
        "video/node_modules", False, "missing: run `npm ci` in video/"
    )
    (tmp_path / "node_modules").mkdir()
    assert doctor._node_modules() == doctor.Probe(
        "video/node_modules", True, str(tmp_path / "node_modules")
    )


def test_doctor_reports_each_probe_and_fails_on_any(monkeypatch, capsys):
    monkeypatch.setattr(
        doctor,
        "probes",
        lambda: [
            doctor.Probe("ffmpeg", True, "C:/ffmpeg/bin/ffmpeg"),
            doctor.Probe("ssh ancientnerds", False, "timeout"),
        ],
    )
    assert doctor.cmd_doctor(argparse.Namespace(fix_gpu=False)) == 1
    out = capsys.readouterr().out
    assert "ok    ffmpeg" in out and "FAIL  ssh ancientnerds" in out


def test_gpu_probes(monkeypatch):
    from pipeline.studio.capture import gpu
    from pipeline.studio.capture.manifest import CaptureError

    exe = Path("C:/video/node_modules/.remotion/chrome-headless-shell.exe")
    monkeypatch.setattr(gpu, "nvenc_problem", lambda: None)
    monkeypatch.setattr(gpu, "remotion_browser", lambda video_dir: exe)
    monkeypatch.setattr(gpu, "gpu_preference", lambda path: gpu.HIGH_PERFORMANCE)
    for name in ("_nvidia_smi", "_cuda", "_chrome_renderer", "_shell_renderer"):
        monkeypatch.setattr(doctor, name, lambda n=name: doctor.Probe(n, True, "ok"))
    assert all(p.ok for p in doctor.gpu_probes())
    monkeypatch.setattr(gpu, "gpu_preference", lambda path: None)
    monkeypatch.setattr(gpu, "nvenc_problem", lambda: "nvidia-smi not found: no NVIDIA driver")
    failed = {p.name: p.detail for p in doctor.gpu_probes() if not p.ok}
    assert failed == {
        "NVENC": "nvidia-smi not found: no NVIDIA driver",
        "remotion GPU preference": "not set: run `python -m pipeline.studio doctor --fix-gpu`",
    }

    def missing(video_dir):
        raise CaptureError("chrome-headless-shell.exe does not exist")

    monkeypatch.setattr(gpu, "remotion_browser", missing)
    assert [p.name for p in doctor.gpu_probes() if not p.ok] == ["NVENC", "remotion browser"]


def test_the_nvenc_probe_is_the_capture_gpu_encode_proof(monkeypatch):
    """gpu.nvenc_problem already encodes one frame per NVENC encoder on GPU 0 (its own test in
    test_capture_gpu.py): the doctor reports its answer and starts no encode of its own."""
    from pipeline.studio.capture import gpu

    def own_encode(cmd, **_k):
        raise AssertionError(f"the doctor ran its own encode: {cmd}")

    monkeypatch.setattr(doctor.subprocess, "run", own_encode)
    calls = []

    def encodes():
        calls.append(1)
        return None

    monkeypatch.setattr(gpu, "nvenc_problem", encodes)
    assert doctor._nvenc() == doctor.Probe(
        "NVENC", True, "h264_nvenc and hevc_nvenc encoded a test frame on GPU 0"
    )
    assert calls == [1]
    problem = "hevc_nvenc cannot encode on GPU 0 (exit 1): No capable devices found"
    monkeypatch.setattr(gpu, "nvenc_problem", lambda: problem)
    assert doctor._nvenc() == doctor.Probe("NVENC", False, problem)


def test_nvidia_smi_must_name_the_rtx_3080(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "C:/Windows/nvidia-smi.exe")
    for names, ok in (("NVIDIA GeForce RTX 3080 Laptop GPU\n", True), ("AMD Radeon\n", False)):
        monkeypatch.setattr(
            doctor.subprocess,
            "run",
            lambda *a, out=names, **k: subprocess.CompletedProcess(a, 0, out, ""),
        )
        assert doctor._nvidia_smi().ok is ok


def test_fix_gpu_pins_the_remotion_browser_first(monkeypatch, capsys):
    from pipeline.studio.capture import gpu

    pinned = []
    exe = Path("C:/video/node_modules/.remotion/chrome-headless-shell.exe")
    monkeypatch.setattr(gpu, "remotion_browser", lambda video_dir: exe)
    monkeypatch.setattr(gpu, "set_gpu_preference", pinned.append)
    monkeypatch.setattr(doctor, "probes", lambda: [doctor.Probe("x", True, "ok")])
    assert doctor.cmd_doctor(argparse.Namespace(fix_gpu=True)) == 0
    assert pinned == [exe]
    assert "pinned to the high-performance GPU" in capsys.readouterr().out
