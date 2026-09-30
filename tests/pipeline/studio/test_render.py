from __future__ import annotations

import json
import re
import subprocess

import pytest

from pipeline.studio import render
from pipeline.studio.errors import StudioError
from pipeline.video.shorts_audit import Check
from pipeline.video.shorts_ledger import sha256_file
from tests.pipeline.studio import episode_fixtures as ef

NVIDIA = (
    "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Laptop GPU (0x0000249C) Direct3D11 vs_5_0 ps_5_0, "
    "D3D11)"
)
AMD = "ANGLE (AMD, AMD Radeon(TM) Graphics (0x00001638) Direct3D11 vs_5_0 ps_5_0, D3D11)"


def _runner(ws, calls, gpu=NVIDIA):
    def runner(script, args, timeout):
        calls.append(script)
        if script == "still.ts":
            for name in render.thumbnail_files(int(args[args.index("--candidate") + 1])):
                (ws.render_dir / name).write_bytes(b"img")
        if script == "render.ts":
            (ws.render_dir / "raw.mp4").write_bytes(b"raw")
        return subprocess.CompletedProcess([script], 0, f"gpu: {gpu}\nok", "")

    return runner


def test_collect_srcs_finds_every_src():
    timeline = {
        "audio": {"narration": [{"src": "voice/b01.mp3"}], "music": {"src": "music/a.wav"}},
        "scenes": [{"props": {"image": {"src": "media/x.jpg", "markers": []}}}],
    }
    assert render.collect_srcs(timeline) == ["voice/b01.mp3", "music/a.wav", "media/x.jpg"]


def test_public_dir_links_every_referenced_file_and_the_fonts(tmp_path, monkeypatch):
    ws = ef.ready_episode(tmp_path, monkeypatch)
    from pipeline.studio.timeline import build_timeline

    timeline = build_timeline(ws)
    placed = render.populate_public_dir(
        ws, timeline, music_dir=tmp_path / "video-assets" / "music", fonts_dir=render.FONTS_DIR
    )
    assert "voice/b01.mp3" in placed and "music/bed.wav" in placed
    assert "captures/platform-01.mp4" in placed and "media/stone_person.jpg" in placed
    assert (ws.public_dir / "fonts" / "orbitron-700.woff2").read_bytes() == b"font"


def test_public_dir_refuses_missing_files(tmp_path, monkeypatch):
    ws = ef.ready_episode(tmp_path, monkeypatch)
    timeline = {"scenes": [{"props": {"image": {"src": "media/missing.jpg"}}}]}
    with pytest.raises(StudioError, match=r"missing: \['media/missing.jpg'\]"):
        render.populate_public_dir(ws, timeline, music_dir=tmp_path, fonts_dir=render.FONTS_DIR)


def test_render_runs_lint_render_still_audit_and_ledger_in_order(tmp_path, monkeypatch):
    ws = ef.ready_episode(tmp_path, monkeypatch)
    calls = []
    runner = _runner(ws, calls)

    def loudness(raw, out):
        out.write_bytes(b"final")
        return 1.5

    rows = []
    monkeypatch.setattr("pipeline.video.shorts_ledger.current_commit", lambda: "f" * 40)
    out = render.render_episode(
        ws,
        runner=runner,
        loudness=loudness,
        auditor=lambda video, timeline, path: (True, [Check("duration", True, "ok")]),
        record=lambda row: rows.append(row) or {"ok": True, "inserted": True},
    )
    assert calls == ["lint.ts", "render.ts", "still.ts", "still.ts", "still.ts"]
    assert sorted(p.name for p in ws.render_dir.glob("thumbnail_*")) == sorted(render.THUMBNAILS)
    assert out["gain_db"] == 1.5
    row = rows[0]
    assert row["paper_request_id"] == ef.REQ and row["topic_type"] == "A"
    assert row["duration_s"] == round(9 * 357 / 60, 3)
    assert row["renderer"] == NVIDIA
    ledger = json.loads((ws.render_dir / "ledger.json").read_text(encoding="utf-8"))
    assert ledger["row"] == row
    assert ledger["timeline_sha256"] == sha256_file(ws.timeline)
    assert ledger["words_sha256"] == sha256_file(ws.words)
    assert row["script_sha256"] == sha256_file(ws.script)
    assert row["casefile_sha256"] == sha256_file(ws.casefile)


@pytest.mark.parametrize(
    ("name", "old", "new"),
    [
        ("timeline.json", '"The stone"', '"The quarry stone"'),
        ("script.json", "This stone", "That stone"),
        ("casefile.json", "about 1,000 tonnes.", "about 1,242 tonnes."),
        ("voice/words.json", '"duration_s": 5.0', '"duration_s": 4.6'),
    ],
)
def test_a_file_edited_during_the_render_is_not_ledgered(tmp_path, monkeypatch, name, old, new):
    # A render runs for hours; the ledger hashes the files at its end, and `episode package`
    # trusts those hashes to describe the video.
    ws = ef.ready_episode(tmp_path, monkeypatch)
    path = ws.root / name
    inner = _runner(ws, [])

    def runner(script, args, timeout):
        if script == "render.ts":
            text = path.read_text(encoding="utf-8")
            assert old in text
            path.write_text(text.replace(old, new), encoding="utf-8")
        return inner(script, args, timeout)

    def loudness(raw, out):
        out.write_bytes(b"final")
        return 0.0

    rows = []
    with pytest.raises(StudioError, match=rf"^{re.escape(name)} changed during the render"):
        render.render_episode(
            ws,
            runner=runner,
            loudness=loudness,
            auditor=lambda *a: (True, []),
            record=lambda row: rows.append(row) or {"ok": True},
        )
    assert rows == []
    assert not (ws.render_dir / "ledger.json").exists()


@pytest.mark.parametrize(
    ("gpu", "message"),
    [
        (AMD, "not the NVIDIA GPU"),
        (None, "render.ts printed no `gpu:` line"),
        ("two", r"render.ts reported no single renderer"),
    ],
)
def test_the_render_must_prove_the_nvidia(tmp_path, monkeypatch, gpu, message):
    ws = ef.ready_episode(tmp_path, monkeypatch)
    inner = _runner(ws, [], NVIDIA if gpu in (None, "two") else gpu)

    def runner(script, args, timeout):
        out = inner(script, args, timeout)
        if gpu is None and script == "render.ts":
            return subprocess.CompletedProcess([script], 0, "ok", "")
        if gpu == "two" and script == "render.ts":
            other = NVIDIA.replace("Laptop GPU", "GPU")
            return subprocess.CompletedProcess([script], 0, f"gpu: {NVIDIA}\ngpu: {other}", "")
        return out

    with pytest.raises(StudioError, match=message):
        render.render_episode(
            ws,
            runner=runner,
            loudness=lambda r, o: 0.0,
            auditor=lambda *a: (True, []),
            record=lambda row: {"ok": True},
        )


def test_lint_violations_block_the_render(tmp_path, monkeypatch):
    ws = ef.ready_episode(tmp_path, monkeypatch)
    earlier = ["raw.mp4", f"{ws.slug}.mp4", *render.THUMBNAILS, "audit.json", "ledger.json"]
    for name in earlier:
        (ws.render_dir / name).write_bytes(b"from the previous render")

    def runner(script, args, timeout):
        return subprocess.CompletedProcess(
            [script],
            1,
            "",
            '{"type":"layout-violation","frame":12,"a":"captions","b":"b01:lt","reason":"overlap"}'
            "\nError: 1 layout violation(s) in 100 checked frames",
        )

    with pytest.raises(StudioError, match="lint.ts exited 1"):
        render.render_episode(
            ws,
            runner=runner,
            loudness=lambda r, o: 0.0,
            auditor=lambda *a: (True, []),
            record=lambda row: {"ok": True},
        )
    assert "overlap" in (ws.render_dir / "lint_report.txt").read_text(encoding="utf-8")
    assert [name for name in earlier if (ws.render_dir / name).exists()] == []


def test_a_failed_audit_records_nothing(tmp_path, monkeypatch):
    ws = ef.ready_episode(tmp_path, monkeypatch)

    runner = _runner(ws, [])
    rows = []
    with pytest.raises(StudioError, match=r"render audit failed \['loudness'\]"):
        render.render_episode(
            ws,
            runner=runner,
            loudness=lambda r, o: 0.0,
            auditor=lambda *a: (False, [Check("loudness", False, "-17 LUFS")]),
            record=lambda row: rows.append(row),
        )
    assert rows == []


def _final(raw, out):
    out.write_bytes(b"final")
    return 0.0


def test_still_ts_renders_each_thumbnail_candidate(tmp_path, monkeypatch):
    ws = ef.ready_episode(tmp_path, monkeypatch)
    monkeypatch.setattr("pipeline.video.shorts_ledger.current_commit", lambda: "f" * 40)
    seen = []
    runner = _runner(ws, [])

    def recording(script, args, timeout):
        seen.append((script, args))
        return runner(script, args, timeout)

    render.render_episode(
        ws,
        runner=recording,
        loudness=_final,
        auditor=lambda *a: (True, []),
        record=lambda row: {"ok": True},
    )
    stills = [args for script, args in seen if script == "still.ts"]
    assert [a[a.index("--candidate") + 1] for a in stills] == ["1", "2", "3"]
    assert all("--frame" not in a for a in stills)
    assert stills[0][stills[0].index("--out-dir") + 1] == str(ws.render_dir.resolve())


def test_episode_thumbnail_rerenders_one_candidate_from_another_frame(tmp_path, monkeypatch):
    ws = ef.ready_episode(tmp_path, monkeypatch)
    monkeypatch.setattr("pipeline.video.shorts_ledger.current_commit", lambda: "f" * 40)
    runner = _runner(ws, [])
    render.render_episode(
        ws,
        runner=runner,
        loudness=_final,
        auditor=lambda *a: (True, []),
        record=lambda row: {"ok": True},
    )
    calls = []

    def recording(script, args, timeout):
        calls.append((script, args))
        return runner(script, args, timeout)

    out = render.render_thumbnail(ws, 2, 1500 - 300, runner=recording)
    assert out["files"] == list(render.thumbnail_files(2))
    [(script, args)] = calls
    assert script == "still.ts"
    assert args[args.index("--candidate") + 1] == "2" and args[args.index("--frame") + 1] == "1200"
    with pytest.raises(StudioError, match="--frame 1500: frame 1500 lies in beat b05 \\(twist\\)"):
        render.render_thumbnail(ws, 2, 1500, runner=recording)
    with pytest.raises(StudioError, match="--frame 2000: frame 2000 is at or after the first"):
        render.render_thumbnail(ws, 1, 2000, runner=recording)
    with pytest.raises(StudioError, match=r"--candidate must be one of \[1, 2, 3\]"):
        render.render_thumbnail(ws, 4, 10, runner=recording)
    ws.timeline.write_text(ws.timeline.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(StudioError, match="timeline.json changed since the render"):
        render.render_thumbnail(ws, 1, 10, runner=recording)
    assert len(calls) == 1


def test_a_rerendered_thumbnail_leaves_the_built_package_alone(tmp_path, monkeypatch):
    ws = ef.ready_episode(tmp_path, monkeypatch)
    monkeypatch.setattr("pipeline.video.shorts_ledger.current_commit", lambda: "f" * 40)
    render.render_episode(
        ws,
        runner=_runner(ws, []),
        loudness=_final,
        auditor=lambda *a: (True, []),
        record=lambda row: {"ok": True},
    )
    packaged = tmp_path / "thumbnail_2.jpg"
    render.link_or_copy(ws.render_dir / "thumbnail_2_1280.jpg", packaged)  # as package.py does

    def still_in_place(script, args, timeout):
        # renderStill rewrites its output in place (truncate, same inode)
        for name in render.thumbnail_files(int(args[args.index("--candidate") + 1])):
            (ws.render_dir / name).write_bytes(b"new")
        return subprocess.CompletedProcess([script], 0, f"gpu: {NVIDIA}\nok", "")

    render.render_thumbnail(ws, 2, 1200, runner=still_in_place)
    assert (ws.render_dir / "thumbnail_2_1280.jpg").read_bytes() == b"new"
    assert packaged.read_bytes() == b"img"


def test_normalize_loudness_corrects_the_limiter_residual(tmp_path, monkeypatch):
    raw = tmp_path / "raw.mp4"
    raw.write_bytes(b"raw")
    calls = []

    def run_ffmpeg(args, out):
        calls.append(args)
        out.write_bytes(b"audio")
        return out

    def measure_lufs(path):
        return -14.8 if path.name == "loudness.wav" else -20.0

    monkeypatch.setattr("pipeline.video.media.run_ffmpeg", run_ffmpeg)
    monkeypatch.setattr("pipeline.video.shorts_render.measure_lufs", measure_lufs)
    gain = render.normalize_loudness(raw, tmp_path / "final.mp4")
    assert gain == pytest.approx(6.8)
    assert [a[a.index("-c:a") + 1] for a in calls] == ["pcm_f32le", "aac"]
    assert calls[1][calls[1].index("-af") + 1].startswith("volume=6.80dB,alimiter=")
    assert not (tmp_path / "loudness.wav").exists()


def test_timeout_kills_the_tree_and_removes_the_bundle(tmp_path, monkeypatch):
    ws = ef.ready_episode(tmp_path, monkeypatch)

    def hung(script, args, timeout):
        if script == "lint.ts":
            return subprocess.CompletedProcess([script], 0, f"gpu: {NVIDIA}\nok", "")
        (ws.render_dir / "bundle" / "public").mkdir(parents=True)
        (ws.render_dir / "raw.mp4.parts").mkdir()
        raise StudioError(f"{script} did not finish within {timeout}s")

    with pytest.raises(StudioError, match="render.ts did not finish"):
        render.render_episode(
            ws,
            runner=hung,
            loudness=lambda r, o: 0.0,
            auditor=lambda *a: (True, []),
            record=lambda row: {"ok": True},
        )
    assert not (ws.render_dir / "bundle").exists()
    assert not (ws.render_dir / "raw.mp4.parts").exists()

    class Hanging:
        pid = 4242
        args = ["node"]
        timed_out = False

        def __init__(self, *args, **kwargs):
            pass

        def communicate(self, timeout=None):
            if not self.timed_out:
                self.timed_out = True
                raise subprocess.TimeoutExpired("node", timeout)
            return "", ""

    killed = []

    def taskkill(cmd, **kwargs):
        killed.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(render.shutil, "which", lambda name: "C:/node/node.exe")
    monkeypatch.setattr(render.subprocess, "Popen", Hanging)
    monkeypatch.setattr(render.subprocess, "run", taskkill)
    with pytest.raises(StudioError, match="within 5s; its process tree was killed"):
        render.run_node("render.ts", [], 5)
    assert killed == [["taskkill", "/PID", "4242", "/T", "/F"]]


@pytest.mark.parametrize("silent", ["lint.ts", "still.ts"])
def test_every_node_script_must_prove_its_browser(tmp_path, monkeypatch, silent):
    """lint.ts and still.ts open a Remotion browser too: each must print its `gpu:` line."""
    ws = ef.ready_episode(tmp_path, monkeypatch)
    inner = _runner(ws, [])

    def runner(script, args, timeout):
        out = inner(script, args, timeout)
        if script == silent:
            return subprocess.CompletedProcess([script], 0, "ok", "")
        return out

    with pytest.raises(StudioError, match=f"{silent} printed no `gpu:` line"):
        render.render_episode(
            ws,
            runner=runner,
            loudness=_final,
            auditor=lambda *a: (True, []),
            record=lambda row: {"ok": True},
        )
    assert not (ws.render_dir / "ledger.json").exists()


@pytest.mark.parametrize(
    ("taskkill_code", "message"),
    [
        (128, "within 5s; its process tree was killed"),
        (1, "taskkill /PID 4242 exited 1: Access is denied"),
    ],
)
def test_a_timeout_whose_kill_races_the_exit_stays_a_studio_error(
    monkeypatch, taskkill_code, message
):
    """taskkill exits 128 when node ended on its own between the timeout and the kill."""

    class Hanging:
        pid = 4242
        args = ["node"]
        timed_out = False

        def __init__(self, *args, **kwargs):
            pass

        def communicate(self, timeout=None):
            if not self.timed_out:
                self.timed_out = True
                raise subprocess.TimeoutExpired("node", timeout)
            return "", ""

    def taskkill(cmd, check=False, **_k):
        done = subprocess.CompletedProcess(cmd, taskkill_code, "", "Access is denied")
        if check:
            done.check_returncode()  # what subprocess.run(check=True) does
        return done

    monkeypatch.setattr(render.shutil, "which", lambda name: "C:/node/node.exe")
    monkeypatch.setattr(render.subprocess, "Popen", Hanging)
    monkeypatch.setattr(render.subprocess, "run", taskkill)
    with pytest.raises(StudioError, match=message):
        render.run_node("render.ts", [], 5)


def test_a_thumbnail_needs_the_script_the_render_was_made_from(tmp_path, monkeypatch):
    """The beat roles decide which frames may carry a thumbnail: they must be the rendered
    script's, as `episode package` requires."""
    ws = ef.ready_episode(tmp_path, monkeypatch)
    monkeypatch.setattr("pipeline.video.shorts_ledger.current_commit", lambda: "f" * 40)
    runner = _runner(ws, [])
    render.render_episode(
        ws,
        runner=runner,
        loudness=_final,
        auditor=lambda *a: (True, []),
        record=lambda row: {"ok": True},
    )
    ws.script.write_text(ws.script.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(StudioError, match="script.json changed since the render"):
        render.render_thumbnail(ws, 1, 10, runner=runner)
