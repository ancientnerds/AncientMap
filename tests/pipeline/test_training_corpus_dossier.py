"""Corpus writes the dossier relies on: replace semantics, ids, best archive rows."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from pipeline.lyra import training_corpus as tc
from tests.fake_sql import RecordingSession


class _Result:
    def __init__(self) -> None:
        self.rowcount = 1

    def scalar_one(self) -> int:
        return 7


class _CaptureSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.commits = 0

    def execute(self, stmt, params=None):
        self.calls.append((stmt.text, params))
        return _Result()

    def commit(self) -> None:
        self.commits += 1

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None


@pytest.fixture
def session(monkeypatch) -> _CaptureSession:
    capture = _CaptureSession()
    monkeypatch.setattr(tc, "_session_factory", lambda: capture)
    return capture


def test_replace_deletes_the_current_row_first_in_one_transaction(session):
    artifact_id = tc.save_artifact("req-1", "dossier", {"version": 1}, "", replace=True)
    (delete_sql, delete_params), (insert_sql, _insert_params) = session.calls
    assert delete_sql.strip().startswith("DELETE FROM research_artifacts")
    assert delete_params == {"request_id": "req-1", "kind": "dossier", "ref": ""}
    assert "RETURNING id" in insert_sql
    assert session.commits == 1
    assert artifact_id == 7


def test_plain_save_appends_and_returns_the_id(session):
    assert tc.save_artifact(None, "curator_output", {"x": 1}, "2026-09-26") == 7
    ((insert_sql, _params),) = session.calls
    assert insert_sql.strip().startswith("INSERT INTO research_artifacts")


def test_replace_needs_a_run_identity():
    with pytest.raises(ValueError, match="needs a request_id"):
        tc.save_artifact(None, "moderated", {}, replace=True)


def test_run_links_never_downgrade_cited(session):
    tc.record_run_links(
        "req-1", [{"source_id": "a1b2c3d4e5f6", "angle_id": "", "search_query": "", "cited": False}]
    )
    sql, _params = session.calls[0]
    assert "cited = theo_source_archive_runs.cited OR EXCLUDED.cited" in sql


def _row(source_id, content_type, text_chars, tdm=False, full_text=None):
    return SimpleNamespace(
        source_id=source_id,
        url=f"https://x.example/{source_id}",
        content_type=content_type,
        text_chars=text_chars,
        fetched_at=datetime(2026, 9, 28, tzinfo=UTC),
        tdm_opt_out=tdm,
        full_text=full_text,
    )


def test_best_archive_rows_ask_for_one_row_per_source_full_text_first():
    session = RecordingSession(
        {"FROM theo_source_archive": [_row("s1", "text/html", 900, full_text="body")]}
    )
    rows = tc.best_archive_rows_in(session, ["s1", "s1", "s2"], with_text=True)
    sql, params = session.log[0]
    assert "DISTINCT ON (source_id)" in sql
    assert "WHEN tdm_opt_out THEN 1" in sql
    assert "full_text" in sql
    assert params["ids"] == ["s1", "s2"]
    assert rows == {
        "s1": {
            "source_id": "s1",
            "url": "https://x.example/s1",
            "content_type": "text/html",
            "text_chars": 900,
            "fetched_at": datetime(2026, 9, 28, tzinfo=UTC),
            "tdm_opt_out": False,
            "full_text": "body",
        }
    }


def test_best_archive_rows_without_text_do_not_load_bodies():
    session = RecordingSession({})
    assert tc.best_archive_rows_in(session, [], with_text=False) == {}
    assert session.log == []
    tc.best_archive_rows_in(session, ["s1"], with_text=False)
    assert "NULL::text AS full_text" in session.log[0][0]


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (None, "missing"),
        ({"content_type": "text/html", "text_chars": 10, "tdm_opt_out": False}, "full_text"),
        (
            {"content_type": "adapter/snippet", "text_chars": 10, "tdm_opt_out": False},
            "abstract_only",
        ),
        ({"content_type": "text/html", "text_chars": 0, "tdm_opt_out": True}, "tdm_reserved"),
        ({"content_type": "text/html", "text_chars": 0, "tdm_opt_out": False}, "missing"),
    ],
)
def test_classify_archive_row(row, expected):
    assert tc.classify_archive_row(row) == expected
