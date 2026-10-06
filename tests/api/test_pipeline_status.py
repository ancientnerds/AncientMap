"""The ops dashboard must not report a dead journal run as a healthy pipeline.

On 2026-10-05 the journal run was killed by the 06:41 UTC deploy while it was in
a cluster. pipeline-status answered "online" and last_cycle_ok=true for the next
ten hours, because the row's status is written "ok" by _write_article_heartbeat
while the step it was in stayed "run". A leftover "run" step is the only trace a
killed process leaves, so it is what this route reads.
"""

from datetime import UTC, datetime, timedelta

from api.routes.news import get_pipeline_status


class _Result:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class FakeDB:
    def __init__(self, row):
        self._row = row

    def execute(self, stmt, params=None):
        return _Result(self._row)

    def rollback(self):
        return None


def _call(monkeypatch, row):
    monkeypatch.setattr("api.routes.news.cache_get", lambda key: None)
    monkeypatch.setattr("api.routes.news.cache_set", lambda key, value, ttl=0: None)
    return get_pipeline_status(pipeline="article", db=FakeDB(row))


def _row(step_data, *, status="ok", last_error=None, age_s=600):
    """The route reads the row by position: last_heartbeat, status, last_error,
    step_data."""
    last_hb = datetime.now(UTC) - timedelta(seconds=age_s)
    return (last_hb, status, last_error, step_data)


def test_a_killed_run_is_offline_and_not_ok(monkeypatch):
    # The exact state the row was in on 2026-10-06 morning: thirteen finished
    # clusters and one stuck in "run", status "ok".
    step_data = {
        "collect": {"count": 15, "elapsed": 37.0, "status": "done"},
        "research_Chimu funerary platform": {"count": 7, "elapsed": 2027.4, "status": "partial"},
        "research_2,800-year-old Yeha palace in ": {"count": 0, "elapsed": 0, "status": "run"},
    }

    result = _call(monkeypatch, _row(step_data))

    assert result.status == "offline"
    assert result.last_cycle_ok is False
    assert result.last_error is not None
    assert "research_2,800-year-old Yeha palace in" in result.last_error


def test_a_recorded_crash_reports_its_error(monkeypatch):
    step_data = {"collect": {"count": 15, "elapsed": 37.0, "status": "done"}}

    result = _call(
        monkeypatch,
        _row(step_data, status="error", last_error="TypeError: 'int' object is not iterable"),
    )

    assert result.last_cycle_ok is False
    assert result.last_error == "TypeError: 'int' object is not iterable"


def test_a_finished_run_is_online_and_ok(monkeypatch):
    step_data = {
        "collect": {"count": 15, "elapsed": 37.0, "status": "done"},
        "research_Chimu funerary platform": {"count": 7, "elapsed": 2027.4, "status": "partial"},
        "store": {"count": 5111, "elapsed": 12.0, "status": "done"},
    }

    result = _call(monkeypatch, _row(step_data))

    assert result.status == "online"
    assert result.last_cycle_ok is True
    assert result.last_error is None


def test_a_running_journal_is_online(monkeypatch):
    # A live run also holds a "run" step — but its heartbeat keeps moving.
    step_data = {"collect": {"count": 15, "elapsed": 37.0, "status": "done"}}

    result = _call(monkeypatch, _row(step_data, age_s=30))

    assert result.status == "online"
    assert result.last_cycle_ok is True


def test_the_news_pipeline_keeps_its_run_step(monkeypatch):
    # The news pipeline writes a "run" step for the whole cycle it is in, so
    # that state must not be read as a stall.
    monkeypatch.setattr("api.routes.news.cache_get", lambda key: None)
    monkeypatch.setattr("api.routes.news.cache_set", lambda key, value, ttl=0: None)
    step_data = {"fetch": {"count": 0, "elapsed": 0, "status": "run"}}

    result = get_pipeline_status(pipeline="news", db=FakeDB(_row(step_data, age_s=60)))

    assert result.status == "online"
    assert result.last_cycle_ok is True
