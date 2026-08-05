"""thinking_log helper — best-effort activity feed writer (spec §7)."""

import logging

from pipeline.lyra import thinking_log as tl


class _FakeSession:
    def __init__(self):
        self.executed = []
        self.committed = False

    def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params))

    def commit(self):
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_log_thinking_writes_row(monkeypatch):
    fake = _FakeSession()
    monkeypatch.setattr(tl, "_session_factory", lambda: fake)
    tl.log_thinking("curator", "3 claims updated", {"claims": 3})
    assert fake.committed
    (stmt, params) = fake.executed[0]
    assert "INSERT INTO thinking_log" in stmt
    assert params["kind"] == "curator"
    assert params["summary"] == "3 claims updated"
    assert params["details"] == '{"claims": 3}'


def test_log_thinking_never_raises(monkeypatch):
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(tl, "_session_factory", boom)
    tl.log_thinking("miner", "x", None)  # must not raise


def test_log_thinking_swallows_and_logs(monkeypatch, caplog):
    class _Exploding(_FakeSession):
        def execute(self, stmt, params=None):
            raise RuntimeError("relation thinking_log does not exist")

    monkeypatch.setattr(tl, "_session_factory", lambda: _Exploding())
    with caplog.at_level(logging.ERROR):
        tl.log_thinking("miner", "x", None)  # must not raise
    assert "log_thinking failed" in caplog.text
