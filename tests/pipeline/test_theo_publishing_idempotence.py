"""Rule 7: a write is idempotent per input hash (report class H.1).

The 2026-10-04 campaign re-sent a correction and appended its log entry again:
42 byte-identical entries on 22 papers, because a build-status flag that stays
`true` after a successful build was read as "not yet sent" (report section H.1).
The input's sha256 decides now, not a boolean, and the decision is read from
the journal the write itself filled.

The correction entry below is the real one that landed 42 times: the 2026-10-04
audit note of the Stargate paper (099ad920-...), verbatim.
"""

from __future__ import annotations

import io
import json

import pytest

from pipeline.lyra import theo_publish as cli
from pipeline.lyra import theo_publishing as tp
from tests.pipeline.theo_publish_fixtures import (
    IMG_NAME,
    REQ,
    WRITER,
    PublishSession,
    capture_notices,
    journal_entry,
    research_row,
)
from tests.pipeline.test_theo_publishing_corrections import (
    NEW_REPORT,
    SLUG,
    _live_row,
)

from datetime import UTC, datetime

PUBLISHED_AT = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
SHA = "b" * 64
OTHER_SHA = "c" * 64

#: The entry that went onto 22 pages twice and 20 papers more than once.
AUDIT_NOTE = {
    "date": "2026-10-04",
    "text": (
        "Every claim in this paper was re-checked against the sources it cites, by an independent "
        "audit that fetched and read each source rather than accepting the stored verdict. Of 32 "
        "verifiable assertions, 21 did not hold up: they were unsupported, attributed to the wrong "
        "reference, or contradicted by the very source cited. 4 were confirmed as written. 11 "
        "replace claim, 5 delete claim, 4 reattribute, 2 replace date, 1 insert claim were applied. "
        "Each correction narrows a claim to what its source actually says, moves it to a source "
        "that does support it, or removes it where no source could. An honest limit: 6 of the 32 "
        "assertions rest on sources that could not be read at all - paywalls, bot protection, video "
        "without a transcript. Those claims are neither confirmed nor corrected here, and a reader "
        "cannot check them either. They are the weakest part of this paper's evidence base. The "
        "audit was performed and applied by an AI agent fleet; no line of the corrected text has "
        "been read by a human editor. A reference that resolves is not thereby right - it was read "
        "before it was trusted."
    ),
}


def _correction(**overrides) -> dict:
    correction = {
        "version": 1,
        "request_id": REQ,
        "writer": WRITER,
        "report": NEW_REPORT,
        "corrections_append": [AUDIT_NOTE],
    }
    correction.update(overrides)
    return correction


def _correct(session, images, correction=None, *, sha=SHA, dry_run=False):
    return tp.correct_paper(
        session,
        REQ,
        correction if correction is not None else _correction(),
        bundle_sha256=sha,
        dry_run=dry_run,
        images_root=images,
    )


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
        return {"indexnow": {"ok": True}, "qdrant": {"ok": True, "sections": 6}}

    monkeypatch.setattr(tp, "run_publish_side_effects", fake)
    return calls


@pytest.fixture(autouse=True)
def notices(monkeypatch) -> dict[str, list]:
    return capture_notices(monkeypatch)


# -- the reported defect -------------------------------------------------------------


def test_the_same_correction_sent_twice_appends_its_entry_once(images, effects):
    """The campaign's bug: 42 byte-identical entries on 22 papers.

    The second send of the same bytes is a no-op, so the page's correction log
    carries one copy of the note, not two.
    """
    session = PublishSession(_live_row())
    first = _correct(session, images)
    assert first.ok is True
    assert first.already_applied is False
    assert first.journal_id == 42

    second = _correct(session, images)
    assert second.ok is True
    assert second.already_applied is True
    assert second.journal_id == first.journal_id

    # One journal row, one write, one entry on the page.
    assert len(session.journal) == 1
    assert json.loads(session.written)["corrections"] == [AUDIT_NOTE]
    assert len(effects) == 1


def test_a_send_after_an_exit_four_reports_the_journal_row_and_its_missing_side_effects(
    images, effects
):
    """After a timeout or exit 4 the outcome is unknown; the old rule was "never
    re-run the write". Now the re-run is safe: it reads the journal, answers with
    that write's id, and does not touch the row."""
    session = PublishSession(_live_row())
    _correct(session, images)
    # The journal row of a run that committed but never got to its side effects
    # (the exit 4 case): side_effects is still NULL.
    written = session.journal[0]
    assert written.side_effects is None

    again = _correct(session, images)
    assert again.already_applied is True
    assert again.journal_id == written.id
    assert again.side_effects == {}
    # The gates of the first run are reported, so a caller sees why it wrote.
    assert again.gates == written.gates
    assert len(effects) == 1


def test_the_lookups_newest_row_makes_a_different_correction_in_between_apply_again(
    images, effects
):
    """Idempotence is per input *and* per current state: A, B, A applies the third
    A, because the paper is no longer in the first A's result."""
    session = PublishSession(_live_row())
    _correct(session, images, sha=SHA)
    _correct(session, images, _correction(report=NEW_REPORT + "\n"), sha=OTHER_SHA)
    assert len(session.journal) == 2

    third = _correct(session, images, sha=SHA)
    assert third.ok is True
    assert third.already_applied is False
    assert len(session.journal) == 3
    assert len(json.loads(session.written)["corrections"]) == 3


def test_a_dry_run_of_an_applied_correction_says_so_and_writes_nothing(images, effects):
    session = PublishSession(_live_row())
    _correct(session, images)
    written = session.written

    dry = _correct(session, images, dry_run=True)
    assert dry.ok is True
    assert dry.already_applied is True
    assert dry.dry_run is True
    assert session.written == written
    assert len(session.journal) == 1
    assert len(effects) == 1


def test_an_older_journal_row_with_the_same_hash_is_not_treated_as_applied(images, effects):
    """The newest row is a publish; the correction's own hash is older. The paper
    is not in that correction's result, so the correction applies."""
    session = PublishSession(
        _live_row(),
        journal=[
            journal_entry(7, action="correct", bundle_sha256=SHA),
            journal_entry(9, action="publish", bundle_sha256="a" * 64),
        ],
    )
    outcome = _correct(session, images)
    assert outcome.ok is True
    assert outcome.already_applied is False


# -- the other two write paths --------------------------------------------------------


def test_a_publish_bundle_sent_twice_publishes_once(tmp_path):
    from tests.pipeline.theo_publish_fixtures import make_result

    (tmp_path / REQ).mkdir()
    (tmp_path / REQ / IMG_NAME).write_bytes(b"jpeg")
    session = PublishSession(research_row())
    result = make_result()
    first = tp.publish_paper(
        session,
        REQ,
        result,
        writer=WRITER,
        dry_run=False,
        bundle_sha256=SHA,
        images_root=tmp_path,
    )
    assert first.ok is True
    assert first.already_applied is False

    second = tp.publish_paper(
        session,
        REQ,
        result,
        writer=WRITER,
        dry_run=False,
        bundle_sha256=SHA,
        images_root=tmp_path,
    )
    assert second.ok is True
    assert second.already_applied is True
    assert second.journal_id == first.journal_id
    assert len(session.journal) == 1


def test_a_video_registration_sent_twice_registers_once(tmp_path, monkeypatch):
    posted: list[list[str]] = []
    monkeypatch.setattr(
        "pipeline.indexnow.submit", lambda urls: posted.append(urls) or {"ok": True}
    )
    video = {
        "version": 1,
        "request_id": REQ,
        "writer": WRITER,
        "youtube_id": "dQw4w9WgXcQ",
        "title": "The Baalbek trilithon",
        "published_at": "2026-10-05T16:00:00+00:00",
        "evidence_timestamps": {"ev-01": 42},
    }
    session = PublishSession(_live_row(), journal=[journal_entry(1, action="correct", bundle_sha256="a" * 64)])
    first = tp.register_video(session, REQ, video, bundle_sha256=SHA, dry_run=False)
    assert first.ok is True
    assert first.already_applied is False

    second = tp.register_video(session, REQ, video, bundle_sha256=SHA, dry_run=False)
    assert second.ok is True
    assert second.already_applied is True
    assert len(json.loads(session.written)["videos"]) == 1
    assert len(posted) == 1


# -- end to end through the CLI, where the hash is the sha256 of the bytes ----------


def test_the_cli_sends_the_same_bytes_twice_and_writes_once(images, monkeypatch, effects):
    """The report's own words: "the input's hash must be the thing that decides"."""
    session = PublishSession(_live_row())
    monkeypatch.setattr(cli, "get_session", lambda: session)
    # The CLI's correct_paper has no images_root, so it reads the production
    # directory; this test is about the hash, so the images gate is stubbed.
    monkeypatch.setattr(tp, "check_images", lambda *a, **k: {"passed": True, "issues": []})
    raw = json.dumps(_correction()).encode("utf-8")

    out = io.StringIO()
    assert cli.main(["--correct"], stdin=io.BytesIO(raw), stdout=out) == 0
    first = json.loads(out.getvalue())
    assert first["already_applied"] is False

    out = io.StringIO()
    assert cli.main(["--correct"], stdin=io.BytesIO(raw), stdout=out) == 0
    second = json.loads(out.getvalue())
    assert second["already_applied"] is True
    assert second["journal_id"] == first["journal_id"]
    assert json.loads(session.written)["corrections"] == [AUDIT_NOTE]
