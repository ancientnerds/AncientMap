"""The publish CLI: modes, envelope validation, bundle hash, exit codes (contract C8)."""

from __future__ import annotations

import hashlib
import io
import json

import pytest

from pipeline.lyra import theo_publish as cli
from pipeline.lyra.theo_publishing import PublishConflictError, PublishOutcome
from tests.fake_sql import RecordingSession
from tests.pipeline.theo_publish_fixtures import REQ, WRITER, make_result


def _raw(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _bundle(**overrides) -> dict:
    bundle = {"version": 1, "request_id": REQ, "writer": WRITER, "result": make_result()}
    bundle.update(overrides)
    return bundle


@pytest.fixture
def seen(monkeypatch) -> list[tuple]:
    calls: list[tuple] = []
    monkeypatch.setattr(cli, "get_session", lambda: RecordingSession())

    def fake_publish(session, request_id, result, *, writer, dry_run, bundle_sha256):
        calls.append(("publish", request_id, dry_run, bundle_sha256))
        return PublishOutcome(
            ok=True, action="publish", request_id=request_id, dry_run=dry_run, slug="t"
        )

    def fake_correct(session, request_id, correction, *, bundle_sha256, dry_run):
        calls.append(("correct", request_id, dry_run, bundle_sha256))
        return PublishOutcome(ok=True, action="correct", request_id=request_id, dry_run=dry_run)

    def fake_video(session, request_id, video, *, bundle_sha256, dry_run):
        calls.append(("register_video", request_id, dry_run, bundle_sha256))
        return PublishOutcome(
            ok=True, action="register_video", request_id=request_id, dry_run=dry_run
        )

    monkeypatch.setattr(cli, "publish_paper", fake_publish)
    monkeypatch.setattr(cli, "correct_paper", fake_correct)
    monkeypatch.setattr(cli, "register_video", fake_video)
    return calls


def _run(args: list[str], raw: bytes) -> tuple[int, dict]:
    out = io.StringIO()
    code = cli.main(args, stdin=io.BytesIO(raw), stdout=out)
    return code, json.loads(out.getvalue())


def test_a_dry_run_hashes_the_raw_bundle(seen):
    raw = _raw(_bundle())
    code, outcome = _run(["--dry-run"], raw)
    assert code == 0
    assert outcome["ok"] is True
    assert seen == [("publish", REQ, True, hashlib.sha256(raw).hexdigest())]


def test_apply_publishes(seen):
    code, _outcome = _run(["--apply"], _raw(_bundle()))
    assert code == 0
    assert seen[0][:3] == ("publish", REQ, False)


def test_correct_and_register_video_have_their_own_dry_runs(seen):
    correction = {"version": 1, "request_id": REQ, "writer": WRITER, "corrections_append": []}
    assert _run(["--correct"], _raw(correction))[0] == 0
    video = {
        "version": 1,
        "request_id": REQ,
        "writer": WRITER,
        "youtube_id": "dQw4w9WgXcQ",
        "title": "T",
        "published_at": "2026-10-05T16:00:00+00:00",
        "evidence_timestamps": {},
    }
    assert _run(["--register-video", "--dry-run"], _raw(video))[0] == 0
    assert [call[:3] for call in seen] == [("correct", REQ, False), ("register_video", REQ, True)]


def test_a_failed_gate_exits_1(seen, monkeypatch):
    monkeypatch.setattr(
        cli,
        "publish_paper",
        lambda session, request_id, result, **kw: PublishOutcome(
            ok=False, action="publish", request_id=request_id, dry_run=True
        ),
    )
    code, outcome = _run(["--dry-run"], _raw(_bundle()))
    assert code == 1
    assert outcome["ok"] is False


@pytest.mark.parametrize(
    "raw",
    [
        b"{not json",
        json.dumps(_bundle(version=2)).encode(),
        json.dumps(_bundle(request_id="not-a-uuid")).encode(),
        # A valid UUID in another spelling (REQ has no hex letters, so .upper() would not change it).
        json.dumps(_bundle(request_id=REQ.replace("-", ""))).encode(),
        json.dumps(_bundle(author="Somebody")).encode(),
        json.dumps({"version": 1, "request_id": REQ, "writer": WRITER}).encode(),
        json.dumps(_bundle(result=[])).encode(),
    ],
)
def test_unusable_input_exits_2(seen, raw):
    code, outcome = _run(["--apply"], raw)
    assert code == 2
    assert outcome["ok"] is False
    assert outcome["error"]
    assert seen == []


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_non_json_numbers_are_refused_before_any_write(seen, constant):
    """Python's json.loads reads NaN and Infinity, Postgres jsonb does not: such an input
    would fail after the commit (exit 4) or as a raw DataError."""
    raw = _raw(_bundle()).replace(b'"score": ', f'"score": {constant}, "was": '.encode(), 1)
    assert constant.encode() in raw
    code, outcome = _run(["--apply"], raw)
    assert code == 2
    assert outcome == {
        "ok": False,
        "error": f"the input carries {constant}, which is not JSON (Postgres jsonb refuses it)",
    }
    assert seen == []


@pytest.mark.parametrize("version", [True, 1.0, "1"])
def test_the_version_is_the_integer_1(seen, version):
    code, outcome = _run(["--apply"], _raw(_bundle(version=version)))
    assert code == 2
    assert "unsupported version" in outcome["error"]
    assert seen == []


def test_a_conflict_exits_3(seen, monkeypatch):
    def conflict(session, request_id, result, **kw):
        raise PublishConflictError("row changed")

    monkeypatch.setattr(cli, "publish_paper", conflict)
    code, outcome = _run(["--apply"], _raw(_bundle()))
    assert code == 3
    assert outcome == {"ok": False, "error": "row changed"}


def test_a_republish_excludes_report_and_evidence(seen):
    correction = {
        "version": 1,
        "request_id": REQ,
        "writer": WRITER,
        "corrections_append": [{"date": "2026-09-22", "text": "Rewritten."}],
        "result": make_result(),
        "report": "# T\n",
    }
    code, outcome = _run(["--correct"], _raw(correction))
    assert code == 2
    assert outcome == {
        "ok": False,
        "error": "result (a full republish) excludes report and evidence",
    }
    assert seen == []
    del correction["report"]
    assert _run(["--correct", "--dry-run"], _raw(correction))[0] == 0
    assert seen[0][:3] == ("correct", REQ, True)


@pytest.mark.parametrize(
    "extra",
    [
        {"rewrite": True},
        {"rewrite": False, "report": "# T\n"},
        {"rewrite": 1, "report": "# T\n"},
        {"rewrite": True, "result": make_result()},
        # A rewrite comes from `paper correct --report-file FILE --rewrite`: no evidence.
        {"rewrite": True, "report": "# T\n", "evidence": []},
    ],
)
def test_rewrite_needs_report_and_can_only_be_true(seen, extra):
    correction = {
        "version": 1,
        "request_id": REQ,
        "writer": WRITER,
        "corrections_append": [],
        **extra,
    }
    code, outcome = _run(["--correct"], _raw(correction))
    assert code == 2
    assert outcome == {
        "ok": False,
        "error": "rewrite needs report without evidence, excludes result and can only be true",
    }
    assert seen == []


RUN = "22222222-3333-4444-5555-666666666666"


@pytest.mark.parametrize(
    "extra",
    [
        {"dossier_request_id": RUN, "report": "# T\n"},
        {"dossier_request_id": RUN.replace("-", ""), "result": make_result()},
        {"dossier_request_id": 7, "result": make_result()},
    ],
)
def test_dossier_request_id_needs_result_and_a_canonical_id(seen, extra):
    correction = {
        "version": 1,
        "request_id": REQ,
        "writer": WRITER,
        "corrections_append": [],
        **extra,
    }
    code, outcome = _run(["--correct"], _raw(correction))
    assert code == 2
    assert outcome == {
        "ok": False,
        "error": "dossier_request_id needs result and a canonical lowercase UUID",
    }
    assert seen == []


def test_a_republish_may_name_the_fresh_run_it_was_written_from(seen):
    # Owner decisions 17 and 18: `paper pull REQ --dossier-from RUN`, then
    # `paper correct REQ --republish` sends RUN's id with the result (C5).
    correction = {
        "version": 1,
        "request_id": REQ,
        "writer": WRITER,
        "corrections_append": [
            {"date": "2026-09-22", "text": "Rewritten by Claude from a new Theo run."}
        ],
        "result": make_result(),
        "dossier_request_id": RUN,
    }
    assert _run(["--correct", "--dry-run"], _raw(correction))[0] == 0
    assert seen[0][:3] == ("correct", REQ, True)


def test_a_rewrite_is_a_text_correction(seen):
    correction = {
        "version": 1,
        "request_id": REQ,
        "writer": WRITER,
        "corrections_append": [{"date": "2026-09-22", "text": "Rewritten by Claude."}],
        "report": "# T\n",
        "rewrite": True,
    }
    assert _run(["--correct", "--dry-run"], _raw(correction))[0] == 0
    assert seen[0][:3] == ("correct", REQ, True)


def test_a_video_may_carry_a_poster_and_nothing_else(seen):
    video = {
        "version": 1,
        "request_id": REQ,
        "writer": WRITER,
        "youtube_id": "dQw4w9WgXcQ",
        "title": "T",
        "published_at": "2026-10-05T16:00:00+00:00",
        "evidence_timestamps": {},
        "poster": f"/data/research-images/{REQ}/video_dQw4w9WgXcQ.jpg",
    }
    assert _run(["--register-video", "--dry-run"], _raw(video))[0] == 0
    code, outcome = _run(["--register-video", "--dry-run"], _raw({**video, "thumbnail": "x.jpg"}))
    assert code == 2
    assert outcome == {"ok": False, "error": "unknown keys: ['thumbnail']"}
    assert [call[:3] for call in seen] == [("register_video", REQ, True)]


@pytest.mark.parametrize("args", [[], ["--apply", "--dry-run"], ["--apply", "--correct"]])
def test_exactly_one_mode(args):
    with pytest.raises(SystemExit) as exit_info:
        cli.main(args, stdin=io.BytesIO(b"{}"), stdout=io.StringIO())
    assert exit_info.value.code == 2
