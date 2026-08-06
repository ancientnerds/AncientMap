"""Container-liveness heartbeat for the lyra docker healthcheck (audit P9).

The docker-compose healthcheck compares /tmp/lyra_heartbeat's mtime against
a 900s threshold; the orchestrator touches the file at every main-loop wake,
at each pipeline-step start, and around article generation. The touch must
be crash-safe — a full /tmp must never take down the pipeline loop.
"""

import os
import time

import pipeline.lyra.orchestrator as orch


def test_touch_heartbeat_creates_and_refreshes(tmp_path, monkeypatch):
    hb = tmp_path / "lyra_heartbeat"
    monkeypatch.setattr(orch, "HEARTBEAT_FILE", hb)

    orch._touch_heartbeat()
    assert hb.exists()

    # Backdate, touch again — the mtime must move forward (that is exactly
    # what the docker healthcheck measures).
    stale = time.time() - 3600
    os.utime(hb, (stale, stale))
    orch._touch_heartbeat()
    assert hb.stat().st_mtime > stale + 3000


def test_touch_heartbeat_never_raises(tmp_path, monkeypatch):
    # Point at a path whose parent doesn't exist: Path.touch raises OSError
    # (FileNotFoundError), which the helper must swallow.
    monkeypatch.setattr(orch, "HEARTBEAT_FILE", tmp_path / "missing-dir" / "hb")
    orch._touch_heartbeat()  # must not raise
