from __future__ import annotations

import io
import json
import re
from contextlib import contextmanager
from pathlib import Path

import pytest

from pipeline.studio import ledger, ledger_cli, ledger_client, remote
from pipeline.studio.errors import StudioError
from tests.fake_sql import RecordingSession

MIGRATION = Path(__file__).resolve().parents[3] / "migrations" / "0026_studio_episodes.sql"
ROW = {
    "slug": "baalbek-c5",
    "paper_request_id": "95fa3798-1c2d-4e5f-8a9b-0c1d2e3f4a5b",
    "topic_type": "A",
    "casefile_sha256": "a" * 64,
    "script_sha256": "b" * 64,
    "voice_id": "English_expressive_narrator",
    "pipeline_commit": "0123456789abcdef0123456789abcdef01234567",
    "video_sha256": "c" * 64,
    "duration_s": 312.5,
    "rendered_at": "2026-09-27T10:00:00+00:00",
    "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Laptop GPU Direct3D11 vs_5_0 ps_5_0, D3D11)",
}


def test_migration_vocabulary_matches_the_code():
    sql = MIGRATION.read_text(encoding="utf-8")
    statuses = re.search(r"status IN \(([^)]*)\)", sql).group(1)
    assert {s.strip().strip("'") for s in statuses.split(",")} == set(ledger.STATUSES)
    topics = re.search(r"topic_type IN \(([^)]*)\)", sql).group(1)
    assert {s.strip().strip("'") for s in topics.split(",")} == set(ledger.TOPIC_TYPES)
    assert "paper_request_id  UUID REFERENCES research_requests (id) ON DELETE SET NULL" in sql
    assert "CONSTRAINT studio_episodes_video_unique UNIQUE (video_sha256)" in sql
    assert "renderer          TEXT          NOT NULL," in sql
    assert "status <> 'published' OR (youtube_id IS NOT NULL AND published_at IS NOT NULL)" in sql
    assert "status <> 'withdrawn' OR status_reason IS NOT NULL" in sql
    assert "CASCADE" not in sql
    assert sql.count("BEGIN;") == 1 and sql.count("COMMIT;") == 1


def test_no_other_migration_claims_the_number():
    """The deploy applies migrations by file name: a second 0026_*.sql (from a later merge of
    main) would run beside this one unnoticed."""
    assert [p.name for p in MIGRATION.parent.glob("0026_*.sql")] == [MIGRATION.name]


def test_row_validation():
    row = ledger.row_from_json(ROW)
    assert row.rendered_at.tzinfo is not None
    for key, bad, message in [
        ("video_sha256", "xyz", "video_sha256 is not a sha256"),
        ("paper_request_id", "nope", "paper_request_id must be a request uuid or null"),
        ("topic_type", "E", "topic_type must be one of"),
        ("duration_s", 0, "duration_s must be a positive number"),
        ("rendered_at", "2026-09-27T10:00:00", "rendered_at must carry a timezone"),
        ("renderer", "", "renderer must name the NVIDIA GPU"),
        ("renderer", "ANGLE (AMD, AMD Radeon(TM) Graphics)", "renderer must name the NVIDIA GPU"),
    ]:
        with pytest.raises(ledger.LedgerError, match=re.escape(message)):
            ledger.row_from_json({**ROW, key: bad})


def test_record_inserts_idempotently():
    session = RecordingSession({"INSERT INTO studio_episodes": [object()]})
    assert ledger.record(session, ledger.row_from_json(ROW)) is True
    sql = session.statement_with("INSERT INTO studio_episodes")
    assert "ON CONFLICT (video_sha256) DO NOTHING" in sql
    assert ledger.record(RecordingSession(), ledger.row_from_json(ROW)) is False


def test_publish_changes_exactly_one_rendered_row():
    params = ledger.publish_params(
        {
            "video_sha256": "c" * 64,
            "youtube_id": "dQw4w9WgXcQ",
            "published_at": "2026-10-01T18:00:00+00:00",
        }
    )
    ledger.publish(RecordingSession({"UPDATE studio_episodes": [object()]}), params)
    with pytest.raises(ledger.LedgerError, match="0 rows changed"):
        ledger.publish(RecordingSession(), params)
    with pytest.raises(ledger.LedgerError, match="youtube_id is not a YouTube video id"):
        ledger.publish_params(
            {**params, "youtube_id": "x", "published_at": "2026-10-01T18:00:00+00:00"}
        )


def _factory(answers):
    sessions = []

    @contextmanager
    def factory():
        s = RecordingSession(answers)
        sessions.append(s)
        yield s

    return factory, sessions


def test_cli_records_and_reads_back(monkeypatch, capsys):
    factory, sessions = _factory(
        {"INSERT INTO studio_episodes": [object()], "SELECT COUNT(*)": [(1,)]}
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(ROW)))
    assert ledger_cli.main(["--record"], factory) == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "inserted": True}
    assert len(sessions) == 2 and "SELECT COUNT(*)" in sessions[1].statements()[0]


def test_cli_refuses_when_the_write_is_not_visible(monkeypatch, capsys):
    factory, _ = _factory({"INSERT INTO studio_episodes": [object()], "SELECT COUNT(*)": [(0,)]})
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(ROW)))
    assert ledger_cli.main(["--record"], factory) == 1
    assert json.loads(capsys.readouterr().out) == {
        "ok": False,
        "error": "the row is not readable after the commit",
    }


def test_client_raises_on_refusal(monkeypatch):
    def fake(module, args, *, stdin, timeout):
        assert module == "pipeline.studio.ledger_cli" and args == ["--publish"]
        return remote.RemoteResult(1, b'{"ok": false, "error": "0 rows changed"}', "")

    monkeypatch.setattr(remote, "run_module", fake)
    with pytest.raises(StudioError, match="ledger_cli --publish refused: 0 rows changed"):
        ledger_client.publish_remote("c" * 64, "dQw4w9WgXcQ", "2026-10-01T18:00:00+00:00")
