# SPDX-License-Identifier: AGPL-3.0-only
"""Interval steps (backfill, library, prospect) run on elapsed time persisted
on disk, not on the in-memory cycle counter.

Until 2026-09-17 a daily step needed 24 uninterrupted hourly cycles; every
deploy recreates the Lyra container and reset the counter, so `library` and
`backfill` last ran on 08-26 and 09-13 and `prospect` never ran at all.
"""

from __future__ import annotations

import json

import pipeline.lyra.orchestrator as orch

DAY = 24 * orch.CYCLE_INTERVAL


def test_interval_due_rules():
    now = 1_000_000.0
    assert orch._interval_due("fetch", {}, now)  # no interval: every cycle
    assert orch._interval_due("library", {}, now)  # never ran
    assert not orch._interval_due("library", {"library": now - 3600}, now)
    assert not orch._interval_due("library", {"library": now - DAY + 600}, now)
    assert orch._interval_due("library", {"library": now - DAY + 30}, now)  # 60 s slack
    assert orch._interval_due("library", {"library": now - DAY - 1}, now)


def test_state_round_trip_and_corrupt_file(tmp_path, monkeypatch):
    state_file = tmp_path / "logs" / "lyra_step_state.json"
    monkeypatch.setattr(orch, "STEP_STATE_FILE", state_file)
    assert orch._load_step_state() == {}
    orch._save_step_state({"library": 123.5, "prospect": 7})
    assert json.loads(state_file.read_text()) == {"library": 123.5, "prospect": 7}
    assert orch._load_step_state() == {"library": 123.5, "prospect": 7.0}
    state_file.write_text("{not json")
    assert orch._load_step_state() == {}


def _stub_pipeline(monkeypatch, tmp_path, ran: list[str]):
    """run_pipeline with every side effect stubbed: steps record their name."""
    monkeypatch.setattr(orch, "STEP_STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(orch, "_run_step", lambda name, settings: (ran.append(name) or 0, 0.0))
    monkeypatch.setattr(orch, "_write_step_heartbeat", lambda *a, **k: None)
    monkeypatch.setattr(orch, "_log_cycle_summary", lambda *a, **k: None)
    import pipeline.lyra.channels as channels

    monkeypatch.setattr(channels, "seed_channels", lambda: None)


def test_fresh_container_runs_daily_steps_once_then_waits(tmp_path, monkeypatch):
    ran: list[str] = []
    _stub_pipeline(monkeypatch, tmp_path, ran)
    daily = set(orch.STEP_INTERVALS)

    step_data = orch.run_pipeline(settings=None)
    assert daily <= set(ran), "first cycle after a (re)start runs every interval step"
    assert all(step_data[s]["status"] == "done" for s in daily)

    ran.clear()
    step_data = orch.run_pipeline(settings=None)
    assert not daily & set(ran), "an hour later the daily steps are not due"
    assert all(step_data[s]["status"] == "skip" for s in daily)
    assert set(ran) == set(orch.STEP_ORDER) - daily

    # A day later (state file backdated, as if the container had been
    # recreated ten times in between) they run again.
    state = json.loads((tmp_path / "state.json").read_text())
    (tmp_path / "state.json").write_text(json.dumps({k: v - DAY for k, v in state.items()}))
    ran.clear()
    orch.run_pipeline(settings=None)
    assert daily <= set(ran)


def test_forced_single_step_ignores_the_interval(tmp_path, monkeypatch):
    ran: list[str] = []
    _stub_pipeline(monkeypatch, tmp_path, ran)
    orch.run_pipeline(settings=None)
    ran.clear()
    orch.run_pipeline(settings=None, only_step="prospect")
    assert ran == ["prospect"]
