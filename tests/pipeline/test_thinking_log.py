"""thinking_log helper — best-effort activity feed writer (spec §7)."""

import logging

from pipeline.lyra import thinking_log as tl


class _FakeSession:
    def __init__(self, delete_rowcount=0):
        self.executed = []
        self.commits = 0
        self._delete_rowcount = delete_rowcount

    @property
    def committed(self):
        return self.commits > 0

    def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params))
        rowcount = self._delete_rowcount

        class _R:
            pass

        _R.rowcount = rowcount
        return _R()

    def commit(self):
        self.commits += 1

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


# --- retention pruning (audit P12, 2026-08-06) -------------------------------


def test_prune_thinking_log_sql_shape():
    fake = _FakeSession(delete_rowcount=7)
    deleted = tl.prune_thinking_log(fake)
    assert deleted == 7
    assert fake.committed
    (stmt, params) = fake.executed[0]
    assert "DELETE FROM thinking_log" in stmt
    # Everything older than the failure horizon goes unconditionally...
    assert "created_at < NOW() - make_interval(days => :failure_days)" in stmt
    # ...while between the two horizons only non-failure entries are deleted.
    assert "created_at < NOW() - make_interval(days => :default_days)" in stmt
    assert "COALESCE(details->>'failed', 'false') <> 'true'" in stmt
    assert params == {"default_days": 90, "failure_days": 365}


def test_curator_entry_triggers_prune_once_per_pass(monkeypatch):
    # The curator writes exactly ONE entry per nightly pass, so hooking the
    # prune on kind == 'curator' runs it once per pass — after the entry's
    # own commit, in the same session.
    fake = _FakeSession()
    monkeypatch.setattr(tl, "_session_factory", lambda: fake)
    tl.log_thinking("curator", "Denkstunde: 3 claims", {"claims": 3})
    stmts = [stmt for stmt, _ in fake.executed]
    assert len(stmts) == 2
    assert "INSERT INTO thinking_log" in stmts[0]
    assert "DELETE FROM thinking_log" in stmts[1]
    assert fake.commits == 2  # entry committed before the prune runs


def test_non_curator_entries_do_not_prune(monkeypatch):
    fake = _FakeSession()
    monkeypatch.setattr(tl, "_session_factory", lambda: fake)
    tl.log_thinking("miner", "Miner: 4 candidates", None)
    tl.log_thinking("run_event", "run started", None)
    assert all("DELETE FROM thinking_log" not in stmt for stmt, _ in fake.executed)
