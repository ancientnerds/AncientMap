"""The pipelined production: stage plumbing and the recorder's batching."""

from __future__ import annotations

import threading

import pytest

from pipeline.video import orchestrator
from pipeline.video.orchestrator import next_batch, plan_sessions, run_pipeline, stage_steps


def test_stage_steps_split_around_the_recorder():
    prep, render = stage_steps()
    assert prep == "export,images,select,tts" and render == "render"
    assert "record" not in prep and "record" not in render


def test_sessions_are_capped():
    assert plan_sessions(list("abcdefghij"), 4) == [list("abcd"), list("efgh"), list("ij")]
    assert plan_sessions([], 4) == []
    assert next_batch(list("abcde"), 2) == (["a", "b"], ["c", "d", "e"])


def _fake_stage(tmp_path, monkeypatch, *, fail: set[str] = frozenset()):
    """Wire the orchestrator to fake subprocesses; returns the recorded calls."""
    calls: dict[str, list] = {"steps": [], "sessions": [], "audits": []}
    lock = threading.Lock()

    def fake_step(name, steps, log):
        with lock:
            calls["steps"].append((name, steps))
        return name not in fail

    def fake_session(targets, log, recorder_dir, api_target):
        with lock:
            calls["sessions"].append([t[0].parent.name for t in targets])
        for _, out in targets:  # the recorder writes both takes
            out.mkdir(parents=True, exist_ok=True)
            (out / "short-opening.mp4").write_bytes(b"x")
            (out / "short-return.mp4").write_bytes(b"x")
        return True

    def fake_module(args, log):
        with lock:
            calls["audits"].append(args)
        return True

    monkeypatch.setattr(orchestrator, "_step", fake_step)
    monkeypatch.setattr(orchestrator, "record_session", fake_session)
    monkeypatch.setattr(orchestrator, "_run_module", fake_module)
    monkeypatch.setattr(orchestrator, "RECORD_GATHER_S", 0.05)
    return calls


def test_every_site_runs_through_all_three_stages(tmp_path, monkeypatch):
    calls = _fake_stage(tmp_path, monkeypatch)
    names = [f"Site {i}" for i in range(5)]
    jobs = run_pipeline(
        names,
        log=tmp_path / "run.log",
        recorder_dir=tmp_path,
        api_target="https://example.invalid",
        site_dir_for=lambda name: tmp_path / name.replace(" ", "-"),
    )
    assert all(job.ok for job in jobs.values())
    assert sorted(n for n, s in calls["steps"] if s == "export,images,select,tts") == sorted(names)
    assert sorted(n for n, s in calls["steps"] if s == "render") == sorted(names)
    assert sorted(n for session in calls["sessions"] for n in session) == sorted(
        name.replace(" ", "-") for name in names
    )
    assert len(calls["audits"]) == len(names)


def test_a_failed_preparation_drops_only_that_site(tmp_path, monkeypatch):
    calls = _fake_stage(tmp_path, monkeypatch, fail={"Site 2"})
    names = [f"Site {i}" for i in range(4)]
    jobs = run_pipeline(
        names,
        log=tmp_path / "run.log",
        recorder_dir=tmp_path,
        api_target="https://example.invalid",
        site_dir_for=lambda name: tmp_path / name.replace(" ", "-"),
    )
    assert jobs["Site 2"].failed_stage == "prepare"
    assert [name for name, job in jobs.items() if job.ok] == ["Site 0", "Site 1", "Site 3"]
    recorded = [n for session in calls["sessions"] for n in session]
    assert "Site-2" not in recorded and len(recorded) == 3


def test_recorder_session_covers_several_sites_at_once(tmp_path, monkeypatch):
    calls = _fake_stage(tmp_path, monkeypatch)
    monkeypatch.setattr(orchestrator, "RECORD_GATHER_S", 5.0)  # gather instead of firing per site
    names = [f"Site {i}" for i in range(4)]
    run_pipeline(
        names,
        log=tmp_path / "run.log",
        recorder_dir=tmp_path,
        api_target="https://example.invalid",
        site_dir_for=lambda name: tmp_path / name.replace(" ", "-"),
        prep_workers=4,
    )
    assert max(len(session) for session in calls["sessions"]) > 1


def test_nothing_to_do(tmp_path, monkeypatch):
    _fake_stage(tmp_path, monkeypatch)
    assert (
        run_pipeline(
            [],
            log=tmp_path / "run.log",
            recorder_dir=tmp_path,
            api_target="https://example.invalid",
            site_dir_for=lambda name: tmp_path / name,
        )
        == {}
    )


@pytest.mark.parametrize("workers", [1, 3])
def test_worker_counts_do_not_change_the_outcome(tmp_path, monkeypatch, workers):
    _fake_stage(tmp_path, monkeypatch)
    names = [f"Site {i}" for i in range(3)]
    jobs = run_pipeline(
        names,
        log=tmp_path / "run.log",
        recorder_dir=tmp_path,
        api_target="https://example.invalid",
        site_dir_for=lambda name: tmp_path / name.replace(" ", "-"),
        prep_workers=workers,
        render_workers=workers,
    )
    assert all(job.ok for job in jobs.values())
