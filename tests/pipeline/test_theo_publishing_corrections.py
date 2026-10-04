"""correct_paper and register_video (spec 2.7): public papers change only through the journal."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime

import pytest

from pipeline.lyra import theo_publishing as tp
from pipeline.lyra.theo_citations import validate_paper_artifact
from tests.pipeline.theo_publish_fixtures import (
    DOSSIER_SUMMARY,
    EVIDENCE,
    IMG_NAME,
    REPORT,
    REQ,
    TITLE,
    WRITER,
    PublishSession,
    capture_notices,
    make_result,
    research_row,
)

SHA = "b" * 64
SLUG = "the-baalbek-trilithon"
# Correction dates must lie between the publication day and today: both are in
# the past for any run of this suite.
PUBLISHED_AT = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
NEW_REPORT = REPORT.replace(
    "The quarry dates to the Roman period, which the excavation layers confirm [2].",
    "The quarry dates to the Roman period, as the stratified excavation layers confirm [2].",
)


def _live_row(**result_overrides):
    stored = {
        **make_result(),
        "audit": validate_paper_artifact(REPORT),
        "writer": WRITER,
        "dossier": DOSSIER_SUMMARY,
    }
    stored.update(result_overrides)
    return research_row(
        status="completed",
        is_public=True,
        slug=SLUG,
        published_by="Theo",
        published_at=PUBLISHED_AT,
        result_json=json.dumps(stored),
    )


def _legacy_row(published_by: str = "Theo"):
    """A public M3 paper: no writer, no evidence, no dossier, a stored verdict that fails today's gate."""
    stored = {
        "title": "Who Cut the Baalbek Stones?",
        "report": "# Who Cut the Baalbek Stones?\n\nAn M3 text.\n",
        "published_report": "# Who Cut the Baalbek Stones?\n\nAn M3 text.\n",
        "card_description": "An old card.",
        "hero_image": None,
        "published_hero_image": None,
        "probative_images": [],
        "quality_score": {
            "score": 71,
            "passed": False,
            "audit_gate_failures": {"audit_passed": False, "hallucination_final": 4},
        },
        "approved_by": "Theo",
    }
    return research_row(
        status="completed",
        is_public=True,
        slug="who-cut-the-baalbek-stones",
        published_by=published_by,
        published_at=PUBLISHED_AT,
        result_json=json.dumps(stored),
    )


@pytest.fixture
def images(tmp_path):
    """The site's `research-images` directory, so `images.parent` is the served root."""
    root = tmp_path / "research-images"
    (root / REQ).mkdir(parents=True)
    (root / REQ / IMG_NAME).write_bytes(b"jpeg")
    return root


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
    """The owner notice a full republish or a `rewrite` sends (owner decision 21)."""
    return capture_notices(monkeypatch)


def _correction(**overrides) -> dict:
    correction = {
        "version": 1,
        "request_id": REQ,
        "writer": WRITER,
        "report": NEW_REPORT,
        "corrections_append": [
            {
                "date": "2026-09-22",
                "text": "Clarified how the dating was established.",
                "evidence_id": "ev-02",
            }
        ],
    }
    correction.update(overrides)
    return correction


def _correct(session, images, correction, *, dry_run=False):
    return tp.correct_paper(
        session,
        REQ,
        correction,
        bundle_sha256=SHA,
        dry_run=dry_run,
        images_root=images,
        served_root=images.parent,
    )


def test_a_correction_replaces_both_texts_and_logs_itself(images, effects, notices):
    session = PublishSession(_live_row())
    outcome = _correct(session, images, _correction())

    assert outcome.ok is True
    assert outcome.action == "correct"
    assert outcome.slug == SLUG
    assert outcome.journal_id == 42
    assert set(outcome.gates) == {
        "status",
        "shape",
        "retention",
        "artifact",
        "quality",
        "evidence",
        "images",
        "pictures",
        "page",
    }
    stored = json.loads(session.written)
    assert stored["report"] == NEW_REPORT
    assert stored["published_report"] == NEW_REPORT
    assert stored["corrections"] == _correction()["corrections_append"]
    assert [entry["id"] for entry in stored["evidence"]] == ["ev-01", "ev-02"]
    update = session.statement_with("UPDATE research_requests")
    assert "result_json = :previous" in update
    assert "published_by" not in update  # no correction re-credits the paper (owner decision 19)
    journal_params = next(
        p for sql, p in session.log if "INSERT INTO theo_paper_publications" in sql
    )
    assert journal_params["action"] == "correct"
    (call,) = effects
    assert call["reindex"] is True
    assert call["paper_text"] == NEW_REPORT
    assert call["published_at"] == "2026-09-20T10:00:00+00:00"
    # Only a full republish or a `rewrite` sends the owner notice (owner decision 21).
    assert outcome.side_effects == {"indexnow": {"ok": True}, "qdrant": {"ok": True, "sections": 6}}
    assert notices == {"thinking": [], "discord": []}


def test_a_correction_indexes_the_naive_utc_publication_time_with_its_offset(images, effects):
    """research_requests.published_at is `timestamp without time zone` (NOW() in the UTC
    database), so production hands correct_paper a naive datetime; Qdrant gets the same
    '+00:00' form a first publish sends."""
    row = _live_row()
    row.published_at = datetime(2026, 9, 20, 10, 0)
    session = PublishSession(row)
    assert _correct(session, images, _correction()).ok is True
    (call,) = effects
    assert call["published_at"] == "2026-09-20T10:00:00+00:00"


def test_a_log_entry_keeps_both_texts_and_is_gated_on_the_served_one(images, effects):
    # The founder block workflow stores a published_report assembled from the
    # approved blocks, so report can differ from it: here a draft with a
    # dangling citation [7] that the page never serves.
    draft = REPORT.replace("podium [2].", "podium [7].")
    session = PublishSession(_live_row(report=draft, published_report=NEW_REPORT))
    entry = {"date": "2026-09-22", "text": "Noted a second survey of the quarry."}
    correction = {"version": 1, "request_id": REQ, "writer": WRITER, "corrections_append": [entry]}

    outcome = _correct(session, images, correction)

    assert outcome.ok is True  # the gates saw NEW_REPORT; on the draft the artifact gate fails
    stored = json.loads(session.written)
    assert stored["report"] == draft
    assert stored["published_report"] == NEW_REPORT
    assert stored["corrections"] == [entry]
    (call,) = effects
    assert call["paper_text"] == NEW_REPORT


def test_only_a_rewrite_stores_the_writer_and_notifies_the_owner(images, effects, notices):
    # C5 `rewrite`: a legacy paper rewritten from its stored text (--report-file,
    # owner decision 18) is a republish in all but the image set: it carries the
    # Claude disclosure and sends the same paper_published notice as a first
    # publish (owner decision 21, spec 0: the owner is notified). A small fix
    # such as the Roswell date (owner decision 6) keeps the stored writer and
    # sends none.
    earlier = {**WRITER, "model": "claude-opus-5"}
    fixed = PublishSession(_live_row(writer=earlier))
    fixed_outcome = _correct(fixed, images, _correction())
    assert fixed_outcome.ok is True
    assert json.loads(fixed.written)["writer"] == earlier
    assert "notify" not in fixed_outcome.side_effects
    assert notices == {"thinking": [], "discord": []}

    dry = _correct(
        PublishSession(_live_row(writer=earlier)), images, _correction(rewrite=True), dry_run=True
    )
    assert dry.ok is True
    assert dry.side_effects == {}
    assert notices == {"thinking": [], "discord": []}

    rewritten = PublishSession(_live_row(writer=earlier))
    outcome = _correct(rewritten, images, _correction(rewrite=True))
    assert outcome.ok is True
    assert json.loads(rewritten.written)["writer"] == WRITER
    assert outcome.side_effects["notify"] == {"discord": False}
    (event,) = notices["thinking"]
    assert event[2]["event"] == "paper_published"
    assert event[2]["slug"] == SLUG
    assert event[2]["writer_model"] == "claude-opus-5-5"
    assert len(notices["discord"]) == 1
    recorded = next(
        p for sql, p in rewritten.log if "UPDATE theo_paper_publications SET side_effects" in sql
    )
    assert json.loads(recorded["side_effects"])["notify"] == {"discord": False}


def test_removing_an_evidence_id_needs_a_correction_that_names_it(images, effects):
    unnamed = _correction(
        evidence=[copy.deepcopy(EVIDENCE[0])],
        corrections_append=[{"date": "2026-09-22", "text": "Dropped a claim."}],
    )
    outcome = _correct(PublishSession(_live_row()), images, unnamed)
    assert outcome.ok is False
    assert outcome.gates["retention"]["issues"] == [
        "ev-02 removed without a correction entry naming it"
    ]

    named = _correction(
        evidence=[copy.deepcopy(EVIDENCE[0])],
        corrections_append=[
            {"date": "2026-09-22", "text": "Retired the dating claim.", "evidence_id": "ev-02"}
        ],
    )
    assert _correct(PublishSession(_live_row()), images, named).ok is True


def test_a_retired_evidence_id_is_never_reused_nor_named_again(images, effects):
    row = _live_row(
        corrections=[{"date": "2026-09-21", "text": "Retired ev-03.", "evidence_id": "ev-03"}]
    )
    reused = {
        **copy.deepcopy(EVIDENCE[1]),
        "id": "ev-03",
        "anchor_text": "Both blocks were cut from the same limestone bed",
    }
    correction = _correction(evidence=[*copy.deepcopy(EVIDENCE), reused])
    outcome = _correct(PublishSession(row), images, correction)
    assert outcome.ok is False
    assert "ev-03 was retired earlier and may not be reused" in outcome.gates["retention"]["issues"]

    # The retiring entry must stay the last one naming the id: the page anchors
    # a retired id on that entry (stream B's parse_corrections).
    renamed = _correction(
        corrections_append=[
            {"date": "2026-09-22", "text": "More on ev-03.", "evidence_id": "ev-03"}
        ]
    )
    outcome = _correct(PublishSession(row), images, renamed)
    assert outcome.gates["retention"]["issues"] == [
        "ev-03 was retired earlier; a retired id cannot be named again"
    ]


def test_a_correction_date_lies_between_publication_and_today(images, effects):
    early = _correction(
        corrections_append=[{"date": "2026-09-19", "text": "Before the paper existed."}]
    )
    late = _correction(corrections_append=[{"date": "2999-01-01", "text": "From the future."}])
    for correction in (early, late):
        outcome = _correct(PublishSession(_live_row()), images, correction, dry_run=True)
        assert outcome.gates["shape"]["issues"] == [
            "corrections_append[0].date must lie between the publication day and today"
        ]


def test_only_a_public_paper_takes_corrections(images, effects):
    outcome = _correct(PublishSession(research_row()), images, _correction())
    assert outcome.ok is False
    assert outcome.gates["status"]["passed"] is False


def test_a_correction_dry_run_writes_nothing(images, effects):
    session = PublishSession(_live_row())
    outcome = _correct(session, images, _correction(), dry_run=True)
    assert outcome.ok is True
    assert not [sql for sql in session.statements() if "UPDATE" in sql or "INSERT" in sql]


def test_a_concurrent_change_is_a_conflict(images, effects):
    with pytest.raises(tp.PublishConflictError):
        _correct(PublishSession(_live_row(), update_rowcount=0), images, _correction())


# --- full republish (C5 `result`) -----------------------------------------------------


def _republish(**overrides) -> dict:
    return {
        "version": 1,
        "request_id": REQ,
        "writer": WRITER,
        "result": make_result(**overrides),
        "corrections_append": [
            {"date": "2026-09-22", "text": "Rewritten by Claude from Theo's research."}
        ],
    }


def test_a_legacy_paper_is_republished_in_full(images, effects, notices):
    session = PublishSession(_legacy_row())
    outcome = _correct(session, images, _republish())

    assert outcome.ok is True
    assert outcome.slug == "who-cut-the-baalbek-stones"
    assert set(outcome.gates) == {
        "status",
        "shape",
        "snapshot",
        "retention",
        "artifact",
        "quality",
        "evidence",
        "images",
        "pictures",
        "page",
    }
    stored = json.loads(session.written)
    assert stored["title"] == TITLE
    assert stored["published_report"] == REPORT
    assert stored["writer"] == WRITER
    assert stored["evidence"] == EVIDENCE
    assert stored["corrections"] == _republish()["corrections_append"]
    assert stored["approved_by"] == "Theo"
    assert stored["quality_score"]["passed"] is True
    (call,) = effects
    assert call["reindex"] is True
    assert call["title"] == TITLE
    assert call["slug"] == "who-cut-the-baalbek-stones"
    # The same paper_published notice as a first publish (owner decision 21).
    assert outcome.side_effects == {
        "indexnow": {"ok": True},
        "qdrant": {"ok": True, "sections": 6},
        "notify": {"discord": False},
    }
    (event,) = notices["thinking"]
    assert event == (
        "run_event",
        f"Paper published: {TITLE}",
        {
            "request_id": REQ,
            "event": "paper_published",
            "slug": "who-cut-the-baalbek-stones",
            "url": "https://ancientnerds.com/research/who-cut-the-baalbek-stones",
            "journal_id": 42,
            "writer_model": "claude-opus-5-5",
        },
    )
    assert len(notices["discord"]) == 1
    recorded = next(
        p for sql, p in session.log if "UPDATE theo_paper_publications SET side_effects" in sql
    )
    assert json.loads(recorded["side_effects"])["notify"] == {"discord": False}


def test_a_republish_keeps_the_log_and_needs_its_own_passing_verdict(images, effects):
    earlier = {"date": "2026-09-21", "text": "An earlier fix."}
    row = _live_row(corrections=[earlier])
    # The bundle never carries the log (stream C's `paper bundle` always sends []):
    # the server keeps the stored one and appends corrections_append.
    carried = _correct(PublishSession(row), images, _republish(corrections=[earlier]), dry_run=True)
    assert carried.ok is False
    assert (
        "result.corrections must be []: the published log is kept and grows only through corrections_append"
        in carried.gates["shape"]["issues"]
    )
    quality = {**make_result()["quality_score"], "passed": False}
    held = _correct(PublishSession(row), images, _republish(quality_score=quality), dry_run=True)
    assert held.gates["shape"]["passed"] is True
    assert held.gates["quality"]["issues"] == ["quality_score.passed is not true"]

    session = PublishSession(row)
    assert _correct(session, images, _republish()).ok is True
    assert json.loads(session.written)["corrections"] == [
        earlier,
        *_republish()["corrections_append"],
    ]


def test_a_republish_keeps_the_founder_as_publisher(images, effects):
    # 7 of the 31 public papers carry a founder's name in published_by (read-only
    # check 2026-09-26); the public API shows it as the author. Owner decision 19:
    # the founder stays credited as publisher when Claude's rewrite replaces the
    # paper (the writer record discloses who wrote it, spec 3.7).
    session = PublishSession(_legacy_row(published_by="MrSchneebly"))
    assert _correct(session, images, _republish()).ok is True
    sql, params = next(
        (sql, p) for sql, p in session.log if sql.lstrip().startswith("UPDATE research_requests")
    )
    assert "published_by" not in sql
    assert "author" not in params
    assert session.published_by_after == "MrSchneebly"
    (call,) = effects
    assert call["author_username"] == "MrSchneebly"


# --- full republish from a fresh Theo run (C5 `dossier_request_id`) --------------------

RUN = "22222222-3333-4444-5555-666666666666"
RUN_DOSSIER = {**DOSSIER_SUMMARY, "artifact_id": 99, "created_at": "2026-10-01T08:00:00+00:00"}


def _fresh_run(**overrides):
    """A researched run on the legacy paper's question (owner decision 18)."""
    return research_row(
        id=RUN, result_json=json.dumps({"dossier": RUN_DOSSIER, "title": None}), **overrides
    )


def test_a_rewrite_from_a_fresh_run_takes_its_dossier_and_closes_the_run(images, effects, notices):
    # Owner decisions 17 and 18: the legacy paper keeps its slug and
    # published_at; the studio pulled RUN's dossier into this paper's workspace
    # (`paper pull REQ --dossier-from RUN`), so every image path is this paper's.
    correction = {**_republish(), "dossier_request_id": RUN}
    dry = PublishSession(_legacy_row(), others=[_fresh_run()])
    assert _correct(dry, images, correction, dry_run=True).ok is True
    assert not [sql for sql in dry.statements() if "UPDATE" in sql or "INSERT" in sql]

    session = PublishSession(_legacy_row(), others=[_fresh_run()])
    outcome = _correct(session, images, correction)

    assert outcome.ok is True
    assert outcome.slug == "who-cut-the-baalbek-stones"
    assert outcome.gates["dossier_source"] == {
        "passed": True,
        "issues": [],
        "request_id": RUN,
        "status": "researched",
    }
    stored = json.loads(session.written)
    assert stored["dossier"] == RUN_DOSSIER
    assert stored["writer"] == WRITER
    # RUN is closed in the republish's own transaction (before its one commit):
    # it leaves theo_dossier list and the feeder's unwritten-dossier cap.
    close_sql = session.statement_with("SET status = 'cancelled'")
    assert "status = 'researched'" in close_sql
    assert session.closed == {"id": RUN, "reason": f"dossier used by the republish of {REQ}"}
    statements = session.statements()
    journal_sql = session.statement_with("INSERT INTO theo_paper_publications")
    assert statements.index(close_sql) < statements.index(journal_sql)
    journal_params = next(p for sql, p in session.log if sql == journal_sql)
    assert json.loads(journal_params["gates"])["dossier_source"]["request_id"] == RUN
    assert outcome.side_effects["notify"] == {"discord": False}


def _unusable_run(status):
    return [_fresh_run(status=status, is_public=True)]


@pytest.mark.parametrize(
    ("others", "run_id", "issue"),
    [
        ([], RUN, f"research request {RUN} does not exist"),
        (
            _unusable_run("completed"),
            RUN,
            f"research request {RUN} is 'completed', not 'researched'",
        ),
        ([], REQ, "dossier_request_id names the paper being republished"),
    ],
)
def test_the_dossier_source_is_another_researched_run(images, effects, others, run_id, issue):
    session = PublishSession(_legacy_row(), others=others)
    outcome = _correct(session, images, {**_republish(), "dossier_request_id": run_id})
    assert outcome.ok is False
    assert outcome.gates["dossier_source"]["issues"] == [issue]
    assert session.written is None
    assert effects == []


def test_a_run_closed_in_the_meantime_is_a_conflict(images, effects):
    session = PublishSession(_legacy_row(), others=[_fresh_run()], close_rowcount=0)
    with pytest.raises(tp.PublishConflictError, match="no longer 'researched'"):
        _correct(session, images, {**_republish(), "dossier_request_id": RUN})
    assert session.rollbacks == 1
    assert session.commits == 0
    assert effects == []


# --- register_video -------------------------------------------------------------


def _video(**overrides) -> dict:
    video = {
        "version": 1,
        "request_id": REQ,
        "writer": WRITER,
        "youtube_id": "dQw4w9WgXcQ",
        "title": "Who Really Moved the Baalbek Stones?",
        "published_at": "2026-10-05T16:00:00+00:00",
        "evidence_timestamps": {"ev-01": 41, "ev-02": 312},
    }
    video.update(overrides)
    return video


@pytest.fixture(autouse=True)
def api_cache(monkeypatch) -> None:
    monkeypatch.setattr("api.cache.cache_delete_pattern", lambda pattern: 1)


@pytest.fixture
def pinged(monkeypatch) -> list[list[str]]:
    urls: list[list[str]] = []
    monkeypatch.setattr("pipeline.indexnow.submit", lambda batch: urls.append(list(batch)) or True)
    return urls


def test_a_video_is_appended_and_announced(pinged):
    session = PublishSession(_live_row())
    outcome = tp.register_video(session, REQ, _video(), bundle_sha256=SHA, dry_run=False)
    assert outcome.ok is True
    assert set(outcome.gates) == {"status", "shape", "evidence_refs", "duplicate", "images", "page"}
    # Registered without a poster: a valid contract state (the page keeps its
    # posterless player), and no key is stored.
    assert outcome.gates["images"] == {
        "passed": True,
        "issues": [],
        "checked": 0,
        "missing": [],
        "foreign": [],
    }
    stored = json.loads(session.written)
    (video,) = stored["videos"]
    assert video["youtube_id"] == "dQw4w9WgXcQ"
    assert video["evidence_timestamps"] == {"ev-01": 41, "ev-02": 312}
    assert "registered_at" in video
    assert "poster" not in video
    assert outcome.side_effects == {
        "indexnow": {"ok": True},
        "api_cache": {"ok": True, "dropped": 1},
    }
    assert pinged == [[f"https://ancientnerds.com/research/{SLUG}"]]
    journal_params = next(
        p for sql, p in session.log if "INSERT INTO theo_paper_publications" in sql
    )
    assert journal_params["action"] == "register_video"


def test_a_poster_is_our_own_thumbnail_in_the_papers_folder(pinged, images):
    # Owner decision 13: the paper page shows the studio's own thumbnail, served
    # by us, so it makes no YouTube request before the click.
    poster = tp.poster_web_path(REQ, "dQw4w9WgXcQ")
    assert poster == f"/data/research-images/{REQ}/video_dQw4w9WgXcQ.jpg"

    # The studio uploads the file before the dry run; a missing file fails the images gate.
    missing = tp.register_video(
        PublishSession(_live_row()),
        REQ,
        _video(poster=poster),
        bundle_sha256=SHA,
        dry_run=True,
        images_root=images,
    )
    assert missing.ok is False
    assert missing.gates["images"]["missing"] == [poster]

    (images / REQ / "video_dQw4w9WgXcQ.jpg").write_bytes(b"jpeg")
    session = PublishSession(_live_row())
    outcome = tp.register_video(
        session, REQ, _video(poster=poster), bundle_sha256=SHA, dry_run=False, images_root=images
    )
    assert outcome.ok is True
    assert outcome.gates["images"] == {
        "passed": True,
        "issues": [],
        "checked": 1,
        "missing": [],
        "foreign": [],
    }
    (video,) = json.loads(session.written)["videos"]
    assert video["poster"] == poster

    # Any other path, even an existing image of this paper, is not the poster.
    other = f"/data/research-images/{REQ}/{IMG_NAME}"
    wrong = tp.register_video(
        PublishSession(_live_row()),
        REQ,
        _video(poster=other),
        bundle_sha256=SHA,
        dry_run=True,
        images_root=images,
    )
    assert wrong.ok is False
    assert wrong.gates["shape"]["issues"] == [
        "poster must be /data/research-images/<request_id>/video_<youtube_id>.jpg"
    ]
    assert "images" not in wrong.gates


def test_a_video_must_point_at_known_evidence_and_be_new(pinged):
    unknown = tp.register_video(
        PublishSession(_live_row()),
        REQ,
        _video(evidence_timestamps={"ev-09": 5}),
        bundle_sha256=SHA,
        dry_run=False,
    )
    assert unknown.ok is False
    assert unknown.gates["evidence_refs"]["issues"] == [
        "ev-09 is neither an evidence id of this paper nor retired by a correction"
    ]

    row = _live_row(videos=[{"youtube_id": "dQw4w9WgXcQ"}])
    duplicate = tp.register_video(
        PublishSession(row), REQ, _video(), bundle_sha256=SHA, dry_run=False
    )
    assert duplicate.ok is False
    assert duplicate.gates["duplicate"]["passed"] is False


def test_a_video_may_time_a_retired_evidence_id(pinged):
    # ev-03 was retired by a correction; a video made before that keeps its
    # timestamp, and the page anchors ev-03 on the correction entry.
    row = _live_row(
        corrections=[{"date": "2026-09-21", "text": "Retired ev-03.", "evidence_id": "ev-03"}]
    )
    outcome = tp.register_video(
        PublishSession(row),
        REQ,
        _video(evidence_timestamps={"ev-01": 41, "ev-03": 90}),
        bundle_sha256=SHA,
        dry_run=True,
    )
    assert outcome.ok is True


def test_a_malformed_video_fails_the_shape_gate(pinged):
    outcome = tp.register_video(
        PublishSession(_live_row()),
        REQ,
        _video(youtube_id="short", published_at="yesterday", evidence_timestamps={"ev-01": -3}),
        bundle_sha256=SHA,
        dry_run=True,
    )
    assert outcome.ok is False
    issues = outcome.gates["shape"]["issues"]
    assert "youtube_id must be an 11-character YouTube id" in issues
    assert "published_at must be an ISO 8601 date-time with a UTC offset" in issues
    assert "evidence_timestamps['ev-01'] must be a whole number of seconds >= 0" in issues
    trailing = tp.check_video_shape(
        _video(youtube_id="dQw4w9WgXcQ\n", evidence_timestamps={"ev-01": True})
    )
    assert trailing["issues"] == [
        "youtube_id must be an 11-character YouTube id",
        "evidence_timestamps['ev-01'] must be a whole number of seconds >= 0",
    ]
