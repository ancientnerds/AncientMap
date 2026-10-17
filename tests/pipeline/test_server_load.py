# SPDX-License-Identifier: AGPL-3.0-only
"""pipeline/server_load.py: the host's samples for the dashboard's server panel."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from pipeline import server_load as sl

STAT = "cpu  100 0 50 800 50 0 0 0 0 0\ncpu0 1 2 3 4 5 6 7 8 9 10\n"


def test_cpu_counters_leave_out_idle_and_iowait():
    busy, total = sl._cpu_times(STAT)
    assert (busy, total) == (150, 1000)


def test_a_sample_carries_cpu_only_once_it_has_a_previous_reading(monkeypatch, tmp_path):
    files = {
        "/proc/stat": STAT,
        "/proc/loadavg": "0.40 0.30 0.20 1/300 1234\n",
        "/proc/meminfo": "MemTotal:       12247040 kB\nMemFree:  1000000 kB\nMemAvailable:    8572040 kB\n",
    }

    class FakePath(type(tmp_path)):
        def read_text(self, *a, **kw):
            return files[str(self).replace("\\", "/")]

    monkeypatch.setattr(sl, "Path", FakePath)
    first, counters = sl.sample(None, tmp_path)
    assert first["cpu"] is None
    assert first["load5"] == 0.3
    assert first["mem_used"] == 30.0
    assert first["mem_total_mb"] == 11960
    assert 0 < first["disk_used"] < 100
    files["/proc/stat"] = "cpu  130 0 70 1000 50 0 0 0 0 0\n"
    second, _ = sl.sample(counters, tmp_path)
    # 50 busy jiffies of 250 since the first sample.
    assert second["cpu"] == 20.0


def line(t, cpu=3.0, mem=30.0, disk=59.0, load5=0.3):
    return json.dumps(
        {"t": t.isoformat(), "cpu": cpu, "load1": load5, "load5": load5, "mem_used": mem,
         "mem_total_mb": 11960, "disk_used": disk, "disk_free_gb": 80.0, "cores": 6}
    )  # fmt: skip


NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def test_the_report_folds_days_and_reads_the_newest_sample():
    samples = sl.parse_lines(
        [
            '_used": 1}',  # the tail starts mid-line
            line(NOW - timedelta(days=1, hours=2), cpu=10.0, mem=40.0, disk=None),
            line(NOW - timedelta(days=1, hours=1), cpu=30.0, mem=35.0, disk=None),
            line(NOW - timedelta(minutes=5), cpu=4.0, mem=31.0, disk=59.5),
        ]
    )
    out = sl.load_report(samples, NOW)
    assert out["days"][0] == {
        "day": "2026-10-09",
        "cpu_avg": 20.0,
        "cpu_peak": 30.0,
        "load_peak": 0.3,
        "mem_peak": 40.0,
        "disk_used": None,
    }
    assert out["now"]["cpu"] == 4.0 and out["now"]["disk_used"] == 59.5
    assert out["levels"] == {"disk": "ok", "memory": "ok", "cpu": "ok"}
    assert out["silent"] is False


def test_the_levels_turn_amber_and_red_at_their_limits():
    assert sl.level(79.9, sl.DISK_LIMITS) == "ok"
    assert sl.level(80.0, sl.DISK_LIMITS) == "warn"
    assert sl.level(91.0, sl.DISK_LIMITS) == "bad"
    assert sl.level(None, sl.DISK_LIMITS) == "ok"
    out = sl.load_report(
        sl.parse_lines([line(NOW - timedelta(minutes=5), mem=96.0, disk=85.0)]), NOW
    )
    assert out["levels"] == {"disk": "warn", "memory": "bad", "cpu": "ok"}


def test_a_quiet_sampler_is_reported():
    out = sl.load_report(sl.parse_lines([line(NOW - timedelta(minutes=30))]), NOW)
    assert out["silent"] is True
    assert sl.load_report([], NOW)["silent"] is True


def test_reading_a_missing_log_answers_none(monkeypatch, tmp_path):
    monkeypatch.setattr(sl, "LOG_PATH", tmp_path / "server_load.jsonl")
    assert sl.read_samples() is None


def test_the_sampler_writes_a_line_per_round_and_diffs_against_the_last(monkeypatch, tmp_path):
    path = tmp_path / "server_load.jsonl"
    calls = []

    class Done(Exception):
        pass

    def fake_sample(previous, disk):
        calls.append(previous)
        if len(calls) > 2:
            raise Done
        return {"t": NOW.isoformat(), "cpu": None if previous is None else 1.0}, (len(calls), 9)

    monkeypatch.setattr(sl, "sample", fake_sample)
    monkeypatch.setattr(sl.time, "sleep", lambda s: None)
    try:
        sl._run(path, 0)
    except Done:
        pass
    assert [json.loads(x)["cpu"] for x in path.read_text(encoding="utf-8").splitlines()] == [
        None,
        1.0,
    ]
    assert calls == [None, (1, 9), (2, 9)]


def test_the_sampler_runs_as_one_daemon_thread(monkeypatch, tmp_path):
    monkeypatch.setattr(sl, "_run", lambda path, interval: None)
    thread = sl.start_sampler(tmp_path / "x.jsonl", interval=1)
    thread.join(timeout=5)
    assert thread.daemon and thread.name == "server-load"
