"""publish_paper (spec 2.6): gates, one guarded transaction with its journal row, re-read, side effects, notice."""

from __future__ import annotations

import copy
import json

import pytest

from pipeline.lyra import theo_publishing as tp
from tests.fake_sql import FakeResult
from tests.pipeline.theo_publish_fixtures import (
    DOSSIER_SUMMARY,
    EVIDENCE,
    IMG_NAME,
    REPORT,
    REQ,
    WRITER,
    PublishSession,
    capture_notices,
    make_result,
    research_row,
)

SHA = "a" * 64
EFFECTS = {"indexnow": {"ok": True}, "qdrant": {"ok": True, "sections": 6}}
URL = "https://ancientnerds.com/research/the-baalbek-trilithon"


@pytest.fixture
def images(tmp_path):
    (tmp_path / REQ).mkdir()
    (tmp_path / REQ / IMG_NAME).write_bytes(b"jpeg")
    return tmp_path


@pytest.fixture
def effects(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    def fake(**kwargs):
        calls.append(kwargs)
        return EFFECTS

    monkeypatch.setattr(tp, "run_publish_side_effects", fake)
    return calls


@pytest.fixture(autouse=True)
def notices(monkeypatch) -> dict[str, list]:
    """The owner notice: the thinking_log event and the Discord webhook (unset: returns False)."""
    return capture_notices(monkeypatch)


def _publish(session, images, *, dry_run=False, result=None):
    return tp.publish_paper(
        session,
        REQ,
        result or make_result(),
        writer=WRITER,
        dry_run=dry_run,
        bundle_sha256=SHA,
        images_root=images,
    )


def test_publish_writes_journals_verifies_and_announces(images, effects, notices):
    session = PublishSession(research_row())
    outcome = _publish(session, images)

    assert outcome.ok is True
    assert outcome.slug == "the-baalbek-trilithon"
    assert outcome.url == URL
    assert outcome.journal_id == 42
    assert outcome.side_effects == {**EFFECTS, "notify": {"discord": False}}
    assert set(outcome.gates) == {
        "status",
        "shape",
        "snapshot",
        "artifact",
        "quality",
        "evidence",
        "retention",
        "images",
        "page",
    }

    update = session.statement_with("UPDATE research_requests")
    assert "status IN ('researched', 'completed') AND is_public = FALSE" in update
    assert "published_by = :author" in update
    stored = json.loads(session.written)
    assert stored["dossier"] == DOSSIER_SUMMARY
    assert stored["writer"] == WRITER
    assert stored["audit"]["passed"] is True
    assert stored["published_report"] == REPORT

    journal_params = next(
        p for sql, p in session.log if "INSERT INTO theo_paper_publications" in sql
    )
    assert journal_params["action"] == "publish"
    assert journal_params["bundle_sha256"] == SHA
    assert json.loads(journal_params["writer"]) == WRITER
    recorded = next(
        p for sql, p in session.log if "UPDATE theo_paper_publications SET side_effects" in sql
    )
    assert json.loads(recorded["side_effects"])["notify"] == {"discord": False}
    assert session.commits == 2

    (call,) = effects
    assert call["slug"] == "the-baalbek-trilithon"
    assert call["author_username"] == "Theo"
    assert call["reindex"] is False
    assert call["paper_text"] == REPORT

    (event,) = notices["thinking"]
    assert event == (
        "run_event",
        "Paper published: The Baalbek Trilithon",
        {
            "request_id": REQ,
            "event": "paper_published",
            "slug": "the-baalbek-trilithon",
            "url": URL,
            "journal_id": 42,
            "writer_model": "claude-opus-5-5",
        },
    )
    (embed,) = notices["discord"][0]["embeds"]
    assert embed["title"] == "Theo paper published (written by Claude)"
    assert URL in embed["description"]


def test_a_dry_run_writes_nothing_and_notifies_nobody(images, effects, notices):
    session = PublishSession(research_row())
    outcome = _publish(session, images, dry_run=True)
    assert outcome.ok is True
    assert outcome.journal_id is None
    assert outcome.side_effects == {}
    assert not [sql for sql in session.statements() if "UPDATE" in sql or "INSERT" in sql]
    assert effects == []
    assert notices == {"thinking": [], "discord": []}


def test_a_failed_gate_blocks_the_write(images, effects, notices):
    result = make_result()
    result["evidence"][0]["verdict"] = "partly"
    session = PublishSession(research_row())
    outcome = _publish(session, images, result=result)
    assert outcome.ok is False
    assert outcome.gates["evidence"]["passed"] is False
    assert not [sql for sql in session.statements() if "UPDATE" in sql]
    assert notices == {"thinking": [], "discord": []}


def test_a_public_row_passes_a_dry_run_but_refuses_apply(images, effects):
    row = research_row(status="completed", is_public=True, slug="the-baalbek-trilithon")
    dry = _publish(PublishSession(row), images, dry_run=True)
    assert dry.ok is True
    assert dry.gates["status"]["apply_allowed"] is False
    session = PublishSession(row)
    applied = _publish(session, images)
    assert applied.ok is False
    assert not [sql for sql in session.statements() if "UPDATE" in sql]


def test_an_unpublished_paper_keeps_its_evidence_ids_log_and_videos(images, effects):
    # The founder route's unpublish (api/routes/theo.py) leaves the row completed
    # and not public, with the paper's public record still in result_json.
    earlier = {"date": "2026-09-21", "text": "An earlier fix."}
    video = {
        "youtube_id": "dQw4w9WgXcQ",
        "title": "Who Really Moved the Baalbek Stones?",
        "published_at": "2026-09-22T16:00:00+00:00",
        "evidence_timestamps": {"ev-01": 41, "ev-02": 312},
        "registered_at": "2026-09-22T16:05:00+00:00",
    }
    previous = {
        **make_result(),
        "writer": WRITER,
        "dossier": DOSSIER_SUMMARY,
        "corrections": [earlier],
        "videos": [video],
    }
    row = research_row(status="completed", result_json=json.dumps(previous))

    dropped = _publish(
        PublishSession(row), images, result=make_result(evidence=[copy.deepcopy(EVIDENCE[0])])
    )
    assert dropped.ok is False
    assert dropped.gates["retention"]["issues"] == [
        "ev-02 removed without a correction entry naming it"
    ]

    session = PublishSession(row)
    assert _publish(session, images).ok is True
    stored = json.loads(session.written)
    assert stored["corrections"] == [earlier]
    assert stored["videos"] == [video]
    assert stored["dossier"] == DOSSIER_SUMMARY


def test_a_row_changed_underneath_raises_a_conflict(images, effects, notices):
    session = PublishSession(research_row(), update_rowcount=0)
    with pytest.raises(tp.PublishConflictError):
        _publish(session, images)
    assert session.rollbacks == 1
    assert effects == []
    assert notices["thinking"] == []


def test_a_re_read_that_differs_raises_after_commit(images, effects, notices):
    session = PublishSession(research_row(), tamper=True)
    with pytest.raises(tp.PublishVerificationError, match="result_json differs"):
        _publish(session, images)
    assert effects == []
    assert notices["thinking"] == []


def test_an_unknown_request_is_an_input_error(images, effects):
    class Empty(PublishSession):
        def execute(self, stmt, params=None):
            if "published_by, published_at, result_json" in stmt.text:
                return FakeResult([])
            return super().execute(stmt, params)

    with pytest.raises(tp.PublishInputError, match="does not exist"):
        _publish(Empty(research_row()), images)


# --- side effects ---------------------------------------------------------------


def test_side_effects_record_a_qdrant_failure_without_raising(monkeypatch):
    submitted: list[list[str]] = []
    monkeypatch.setattr(
        "pipeline.indexnow.submit", lambda urls: submitted.append(list(urls)) or True
    )

    def down(**kwargs):
        raise RuntimeError("qdrant down")

    monkeypatch.setattr("pipeline.lyra.theo_research_index.index_paper", down)
    effects = tp.run_publish_side_effects(
        request_id=REQ,
        slug="s",
        title="T",
        paper_text=REPORT,
        author_username="Theo",
        author_discord_id="442000112756064260",
        published_at="2026-09-28T10:00:00+00:00",
        reindex=False,
    )
    assert effects == {
        "indexnow": {"ok": True},
        "qdrant": {"ok": False, "error": "RuntimeError: qdrant down"},
    }
    assert submitted == [
        ["https://ancientnerds.com/research/s", "https://ancientnerds.com/research/"]
    ]


def test_a_reindex_deletes_the_old_sections_first(monkeypatch):
    order: list[str] = []
    monkeypatch.setattr("pipeline.indexnow.submit", lambda urls: True)
    monkeypatch.setattr(
        "pipeline.lyra.theo_research_index.delete_paper",
        lambda paper_id: order.append("delete") or 1,
    )
    monkeypatch.setattr(
        "pipeline.lyra.theo_research_index.index_paper",
        lambda **kwargs: order.append("index") or 6,
    )
    effects = tp.run_publish_side_effects(
        request_id=REQ,
        slug="s",
        title="T",
        paper_text=REPORT,
        author_username="Theo",
        author_discord_id="442000112756064260",
        published_at="2026-09-28T10:00:00+00:00",
        reindex=True,
    )
    assert order == ["delete", "index"]
    assert effects["qdrant"] == {"ok": True, "sections": 6}


def test_the_notice_writes_thinking_log_and_calls_the_webhook(notices):
    assert tp.notify_published(REQ, "T" * 300, "s", "https://x/s", 7, WRITER) == {"discord": False}
    ((kind, summary, details),) = notices["thinking"]
    assert kind == "run_event"
    assert summary == "Paper published: " + "T" * 200
    assert details["event"] == "paper_published"
    assert len(notices["discord"]) == 1
