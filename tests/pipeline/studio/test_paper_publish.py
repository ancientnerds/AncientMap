from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import PurePosixPath

import pytest
from PIL import Image

from pipeline.lyra.theo_publishing import poster_web_path
from pipeline.studio import remote
from pipeline.studio.errors import StudioError
from pipeline.studio.paper import bundle, gates, numbering, publish
from pipeline.studio.paper.workspace import write_json
from tests.pipeline.studio import fixtures as fx

STATUS = {"passed": True, "is_public": False, "apply_allowed": True}
DRY_OK = {"ok": True, "gates": {"status": STATUS}}
EFFECTS = {
    "indexnow": {"ok": True},
    "qdrant": {"ok": True, "sections": 7},
    "notify": {"discord": False},
}
APPLIED = {
    "ok": True,
    "slug": "the-megaliths",
    "url": "https://ancientnerds.com/research/the-megaliths",
    "side_effects": EFFECTS,
    "journal_id": 12,
}
YT = "dQw4w9WgXcQ"
RUN = "11111111-2222-3333-4444-555555555555"  # a fresh Theo run on the paper's question


@pytest.fixture
def checked(tmp_path):
    ws = fx.complete_workspace(tmp_path)
    assert gates.run_check(ws)["passed"]
    return ws


class FakeRemote:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []
        self.uploads = []
        self.events = []

    def run_module(self, module, args, *, stdin=None, timeout):
        self.calls.append((module, args, stdin, timeout))
        self.events.append(("run", args))
        code, outcome = self.answers.pop(0)
        stdout = outcome if isinstance(outcome, bytes) else json.dumps(outcome).encode("utf-8")
        return remote.RemoteResult(code, stdout, "")

    def upload(self, request_id, files, timeout=900):
        self.uploads.append((request_id, [p.name for p in files]))
        self.events.append(("upload", [p.read_bytes() for p in files]))


def _patch(monkeypatch, fake):
    monkeypatch.setattr(remote, "run_module", fake.run_module)
    monkeypatch.setattr(remote, "upload_research_images", fake.upload)


def _as_rewrite(ws):
    """The workspace as `paper pull <REQ> --dossier-from RUN` leaves it: RUN's dossier."""
    data = fx.dossier_dict()
    data["request"]["id"] = RUN
    ws.dossier_gz.write_bytes(fx.dossier_gz_bytes(data))
    write_json(ws.dossier_from, {"request_id": RUN})


def _as_published(ws):
    """The workspace after a successful `paper publish`: published_bundle.json = bundle.json."""
    b = bundle.write_bundle(ws)
    ws.published_bundle.write_bytes(ws.bundle.read_bytes())
    return b


def test_the_research_model_names_who_did_the_research():
    """A stamp that names another model is a false claim on a public page (owner rule:
    model stamps must be true). The papers of the current campaign were researched and
    written in the mcode session, and the constant still named the pipeline's model, so
    the dossier's own researcher decides."""
    session = bundle.writer_for(
        {"manifest": {"research": {"researcher": "MiniMax-M3.1-Flash-Preview (mcode session)"}}}
    )
    assert session["research_model"] == "MiniMax-M3.1-Flash-Preview"
    assert session["model"] == bundle.WRITER["model"], "the writing model stays as it is"
    # a dossier from a Theo run carries that worker's name, and nothing else changes
    worker = bundle.writer_for({"manifest": {"research": {"researcher": "MiniMax-M3"}}})
    assert worker["research_model"] == "MiniMax-M3"
    assert worker["tool"] == bundle.WRITER["tool"]
    # no name to read: the constant stands, it is never invented
    assert bundle.writer_for({}) == bundle.WRITER
    assert bundle.writer_for(None) == bundle.WRITER
    assert bundle.writer_for({"manifest": {"research": {"researcher": ""}}}) == bundle.WRITER


def test_bundle_carries_the_published_snapshot(checked):
    b = bundle.write_bundle(checked)
    assert set(b) == {"version", "request_id", "writer", "result"}
    r = b["result"]
    assert r["report"] == r["published_report"] == checked.paper.read_text(encoding="utf-8")
    assert r["hero_image"] == r["published_hero_image"]
    assert r["hero_image"]["src"] == r["probative_images"][0]["web_path"]
    assert set(r["probative_images"][0]) == set(bundle.PROBATIVE_KEYS)
    assert r["writer"] == b["writer"] == bundle.WRITER
    assert r["writer"]["human_review"] is False
    assert r["corrections"] == [] and r["published_block_ids"] == []
    assert r["quality_score"]["passed"] is True
    assert json.loads(checked.bundle.read_text(encoding="utf-8")) == b
    # every probative image of the paper plus the hero, as a sorted set: the
    # house draft now carries one image per section, not one for the whole paper
    expected = sorted(
        {PurePosixPath(e["web_path"]).name for e in r["probative_images"]}
        | {PurePosixPath(r["hero_image"]["src"]).name}
        | {PurePosixPath(r["hero_image"]["web_path"]).name}
    )
    assert bundle.upload_names(r) == expected


def test_the_bundle_carries_the_sentence_evidence_card_without_touching_the_report(checked):
    """The audit artefact of the defect report, and the promise that it changes
    nothing a reader sees: the rendered markdown is byte-identical, the markers
    stay paragraph-level, and the card says per sentence which source's fetched
    text carries it."""
    b = bundle.build_bundle(checked)
    card = b["result"]["sentence_evidence"]
    assert card["version"] == 1
    counts = card["counts"]
    assert counts["sentences"] > 0
    assert counts["with_refs"] == counts["located"] + counts["unlocated"]
    assert counts["sentences"] == counts["with_refs"] + counts["sentences_without_refs"]

    located = [
        sentence
        for para in card["paragraphs"]
        for sentence in para["sentences"]
        if sentence["quote"]
    ]
    assert located, "the fixture's archive texts must locate at least one of its sentences"
    built = numbering.number(checked)
    by_number = gates.texts_by_number(
        built, gates.source_texts(checked, gates.load_dossier(checked))
    )
    for sentence in located:
        # Every quote is a contiguous run of the named source's text, at the offset
        # the card gives, so a reader can check it without redoing the research.
        source = by_number[sentence["quote_source"]]
        start = sentence["quote_start"]
        assert start >= 0
        assert source[start : start + len(sentence["quote"])] == sentence["quote"]
        assert sentence["quote_source"] in sentence["refs"]

    # Nothing else moved: the report the page renders is the same text, and the
    # marker grammar is untouched.
    assert b["result"]["report"] == b["result"]["published_report"]
    assert "[S:" not in b["result"]["report"]


def test_bundle_refuses_a_stale_or_failing_check(checked):
    checked.draft.write_text(
        checked.draft.read_text(encoding="utf-8").replace("still lies", "still sits"),
        encoding="utf-8",
    )
    with pytest.raises(StudioError, match="changed after the last check"):
        bundle.build_bundle(checked)
    report = json.loads(checked.check_report.read_text(encoding="utf-8"))
    report["passed"] = False
    report["gates"][0]["passed"] = False
    checked.check_report.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(StudioError, match=r"failing gates \['artifact'\]"):
        bundle.build_bundle(checked)


def test_bundle_refuses_evidence_or_meta_changed_after_the_check(checked):
    original = checked.evidence.read_text(encoding="utf-8")
    edited = json.loads(original)
    edited[0]["quote"] = "A sentence no source contains."
    write_json(checked.evidence, edited)
    with pytest.raises(StudioError, match="evidence.json changed after the last check"):
        bundle.write_bundle(checked)
    checked.evidence.write_text(original, encoding="utf-8")
    meta = json.loads(checked.meta.read_text(encoding="utf-8"))
    meta["card_description"] += " Edited."
    write_json(checked.meta, meta)
    with pytest.raises(StudioError, match="paper_meta.json changed after the last check"):
        bundle.write_bundle(checked)


def test_bundle_refuses_evidence_deleted_after_the_check(checked):
    checked.evidence.unlink()
    with pytest.raises(StudioError, match="evidence.json does not exist"):
        bundle.write_bundle(checked)


def test_publish_uploads_then_dry_runs_then_applies(monkeypatch, checked):
    bundle.write_bundle(checked)
    fake = FakeRemote([(0, DRY_OK), (0, APPLIED)])
    _patch(monkeypatch, fake)
    record = publish.publish(checked, dry_run=False)
    # every image of the paper is uploaded: the house draft has one per section
    assert fake.uploads[0][0] == fx.REQ
    assert len(fake.uploads[0][1]) == len(
        json.loads(checked.bundle.read_text(encoding="utf-8"))["result"]["probative_images"]
    )
    assert [c[1] for c in fake.calls] == [["--dry-run"], ["--apply"]]
    assert fake.calls[0][2] == checked.bundle.read_bytes()
    assert record["apply"]["url"] == "https://ancientnerds.com/research/the-megaliths"
    assert record["apply"]["side_effects"]["notify"] == {"discord": False}
    stored = json.loads(checked.publish_outcome.read_text(encoding="utf-8"))
    assert stored["bundle_sha256"] == record["bundle_sha256"]
    assert (stored["dry_run_exit_code"], stored["apply_exit_code"]) == (0, 0)
    assert stored["apply"]["side_effects"] == EFFECTS
    assert checked.published_bundle.read_bytes() == checked.bundle.read_bytes()


def test_a_refused_dry_run_never_applies(monkeypatch, checked):
    bundle.write_bundle(checked)
    refused = {
        "ok": False,
        "gates": {"status": STATUS, "images": {"passed": False}, "shape": {"passed": True}},
    }
    fake = FakeRemote([(1, refused)])
    _patch(monkeypatch, fake)
    with pytest.raises(StudioError, match=r"--dry-run refused: failing gates \['images'\]"):
        publish.publish(checked, dry_run=False)
    assert len(fake.calls) == 1
    stored = json.loads(checked.publish_outcome.read_text(encoding="utf-8"))
    assert stored["apply"] is None and stored["dry_run_exit_code"] == 1
    assert not checked.published_bundle.exists()


def test_an_already_public_paper_is_sent_to_correct(monkeypatch, checked):
    bundle.write_bundle(checked)
    public = {"passed": True, "is_public": True, "apply_allowed": False}
    passing = (0, {"ok": True, "gates": {"status": public}})
    # a rewritten paper checked against the live evidence often fails retention: the operator
    # is still sent to `paper correct`, not to the failing gates
    failing = (1, {"ok": False, "gates": {"status": public, "retention": {"passed": False}}})
    for answer in (passing, failing):
        for dry_run in (True, False):
            fake = FakeRemote([answer])
            _patch(monkeypatch, fake)
            with pytest.raises(StudioError, match="already public: change it with `paper correct`"):
                publish.publish(checked, dry_run=dry_run)
            assert len(fake.calls) == 1


def test_a_published_workspace_whose_row_is_public_is_not_published_again(monkeypatch, checked):
    bundle.write_bundle(checked)
    _patch(monkeypatch, FakeRemote([(0, DRY_OK), (0, APPLIED)]))
    publish.publish(checked, dry_run=False)
    record = checked.publish_outcome.read_bytes()
    public = {"passed": True, "is_public": True, "apply_allowed": False}
    for dry_run in (True, False):
        fake = FakeRemote([(0, {"ok": True, "gates": {"status": public}})])
        _patch(monkeypatch, fake)
        with pytest.raises(
            StudioError,
            match="already published as /research/the-megaliths: change it with `paper correct`",
        ):
            publish.publish(checked, dry_run=dry_run)
        assert [c[1] for c in fake.calls] == [["--dry-run"]]
    assert checked.publish_outcome.read_bytes() == record


def test_an_unpublished_paper_is_published_again_and_the_old_record_kept(monkeypatch, checked):
    bundle.write_bundle(checked)
    _patch(monkeypatch, FakeRemote([(0, DRY_OK), (0, APPLIED)]))
    publish.publish(checked, dry_run=False)
    first = checked.publish_outcome.read_bytes()
    at = json.loads(first)["at"]
    fake = FakeRemote([(0, DRY_OK), (0, dict(APPLIED, journal_id=13))])
    _patch(monkeypatch, fake)
    record = publish.publish(checked, dry_run=False)
    assert [c[1] for c in fake.calls] == [["--dry-run"], ["--apply"]]
    assert record["apply"]["journal_id"] == 13
    assert (checked.root / f"publish_outcome.{at.replace(':', '')}.json").read_bytes() == first
    stored = json.loads(checked.publish_outcome.read_text(encoding="utf-8"))
    assert stored["apply"]["journal_id"] == 13


def test_a_rewrite_workspace_is_sent_with_correct_republish(monkeypatch, checked):
    bundle.write_bundle(checked)
    _as_rewrite(checked)
    fake = FakeRemote([])
    _patch(monkeypatch, fake)
    with pytest.raises(StudioError, match=f"paper correct {fx.REQ} --republish"):
        publish.publish(checked, dry_run=True)
    assert fake.calls == [] and fake.uploads == []


@pytest.mark.parametrize(
    ("code", "error", "message"),
    [
        (2, StudioError, "refused the input: unknown keys"),
        (3, StudioError, "the row changed underneath; nothing was committed"),
        (4, remote.RemoteOutcomeUnknown, "committed but the re-read differs"),
    ],
)
def test_exit_codes_say_what_happened(monkeypatch, checked, code, error, message):
    bundle.write_bundle(checked)
    fake = FakeRemote([(0, DRY_OK), (code, {"ok": False, "error": "unknown keys"})])
    _patch(monkeypatch, fake)
    with pytest.raises(error, match=message):
        publish.publish(checked, dry_run=False)
    stored = json.loads(checked.publish_outcome.read_text(encoding="utf-8"))
    assert stored["apply_exit_code"] == code
    assert not checked.published_bundle.exists()


def test_an_unknown_correct_or_video_write_is_not_told_to_avoid_apply():
    for step in ("theo_publish --correct", "theo_publish --register-video"):
        with pytest.raises(remote.RemoteOutcomeUnknown) as raised:
            publish.require_ok(step, 4, {"ok": False, "error": "re-read"})
        message = str(raised.value)
        assert message.startswith(f"{step}: committed but the re-read differs")
        assert "--apply" not in message and "do not run it again" in message


def test_a_retry_after_an_unknown_apply_keeps_its_record(monkeypatch, checked):
    """publish_outcome.json of an apply whose outcome is unknown carries the bundle_sha256 the
    adoption procedure compares with the journal: a re-run that finds the paper public (the
    apply did commit) is sent to the procedure and leaves that record as it was."""
    bundle.write_bundle(checked)
    _patch(monkeypatch, FakeRemote([(0, DRY_OK), (4, {"ok": False, "error": "re-read"})]))
    with pytest.raises(remote.RemoteOutcomeUnknown):
        publish.publish(checked, dry_run=False)
    record = checked.publish_outcome.read_bytes()
    public = {"passed": True, "is_public": True, "apply_allowed": False}
    for dry_run in (True, False):
        fake = FakeRemote([(0, {"ok": True, "gates": {"status": public}})])
        _patch(monkeypatch, fake)
        with pytest.raises(StudioError, match="already public: change it with `paper correct`"):
            publish.publish(checked, dry_run=dry_run)
        assert [c[1] for c in fake.calls] == [["--dry-run"]]
    assert checked.publish_outcome.read_bytes() == record


def test_a_write_without_json_is_an_unknown_outcome(monkeypatch, checked):
    bundle.write_bundle(checked)
    fake = FakeRemote([(0, DRY_OK), (137, b"Killed")])
    _patch(monkeypatch, fake)
    with pytest.raises(remote.RemoteOutcomeUnknown, match="may have committed"):
        publish.publish(checked, dry_run=False)


def test_an_unknown_apply_names_the_adoption_procedure(monkeypatch, checked):
    """The journal row of a committed write carries the sha256 of the bytes theo_publish
    read; the studio recorded the same hash before the apply, so the operator adopts a
    committed publish by hand instead of running the apply again."""
    bundle.write_bundle(checked)
    _patch(monkeypatch, FakeRemote([(0, DRY_OK), (4, {"ok": False, "error": "re-read"})]))
    with pytest.raises(remote.RemoteOutcomeUnknown) as raised:
        publish.publish(checked, dry_run=False)
    message = str(raised.value)
    sha = json.loads(checked.publish_outcome.read_text(encoding="utf-8"))["bundle_sha256"]
    assert sha == hashlib.sha256(checked.bundle.read_bytes()).hexdigest()
    assert message.startswith("theo_publish --apply: committed but the re-read differs")
    assert (
        "docker exec ancient_nerds_db psql -U ancient_map -d ancient_map -c "
        '\\"SELECT id, action, slug, bundle_sha256, side_effects FROM theo_paper_publications '
        f"WHERE request_id = '{fx.REQ}' ORDER BY id DESC LIMIT 1\\\"" in message
    )
    assert f"if its bundle_sha256 is {sha}, the write committed: never run it again" in message
    assert "byte for byte to published_bundle.json by hand" in message
    assert "takes the row's slug as `--paper-slug`" in message
    assert not checked.published_bundle.exists()


def test_a_correction_records_the_hash_of_the_bytes_it_sent(monkeypatch, checked):
    bundle.write_bundle(checked)
    fake = FakeRemote([(0, {"ok": True}), (137, b"Killed")])
    _patch(monkeypatch, fake)
    entries = [{"date": "2026-10-02", "text": "Rewritten by Claude."}]
    with pytest.raises(remote.RemoteOutcomeUnknown) as raised:
        publish.correct(checked, entries, republish=True)
    (journal,) = (checked.root / "corrections").glob("*.json")
    stored = json.loads(journal.read_text(encoding="utf-8"))
    assert stored["body_sha256"] == hashlib.sha256(fake.calls[1][2]).hexdigest()
    assert stored["apply"] is None
    message = str(raised.value)
    assert "may have committed" in message
    assert f"if its bundle_sha256 is {stored['body_sha256']}, the write committed" in message
    assert "to published_bundle.json by hand" in message and "--paper-slug" not in message
    assert not checked.published_bundle.exists()

    def no_answer(module, args, *, stdin=None, timeout):
        if args == ["--correct"]:
            raise remote.RemoteOutcomeUnknown(f"{module} gave no answer: UNKNOWN")
        return remote.RemoteResult(0, b'{"ok": true}', "")

    monkeypatch.setattr(remote, "run_module", no_answer)
    with pytest.raises(remote.RemoteOutcomeUnknown, match="UNKNOWN") as raised:
        publish.correct(checked, entries)  # the log only: no bundle to adopt
    assert "the write committed: never run it again" in str(raised.value)
    assert "published_bundle.json" not in str(raised.value)


def test_publish_refuses_a_stale_bundle(monkeypatch, checked):
    bundle.write_bundle(checked)
    checked.draft.write_text(
        checked.draft.read_text(encoding="utf-8").replace("still lies", "still sits"),
        encoding="utf-8",
    )
    _patch(monkeypatch, FakeRemote([]))
    with pytest.raises(StudioError, match="bundle.json is stale"):
        publish.publish(checked, dry_run=True)


def test_non_json_output_of_a_dry_run_is_a_remote_error():
    with pytest.raises(remote.RemoteError, match="printed no JSON outcome"):
        publish.outcome_of(remote.RemoteResult(1, b"Traceback ...", "boom"), write=False)


def test_correction_entries_are_dated_and_checked():
    entries = publish.correction_entries(
        [{"text": "Retired ev-01."}, {"text": "Retired ev-02.", "evidence_id": "ev-02"}],
        date(2026, 10, 2),
    )
    assert entries == [
        {"date": "2026-10-02", "text": "Retired ev-01."},
        {"date": "2026-10-02", "text": "Retired ev-02.", "evidence_id": "ev-02"},
    ]
    with pytest.raises(StudioError, match="needs its text"):
        publish.correction_entries([{"text": " "}])
    with pytest.raises(StudioError, match="not an evidence id"):
        publish.correction_entries([{"text": "x", "evidence_id": "ev-1"}])
    with pytest.raises(StudioError, match="keys must be text"):
        publish.correction_entries([{"text": "x", "note": "y"}])


def test_correct_dry_runs_then_sends_the_append_and_journals_locally(monkeypatch, checked):
    fake = FakeRemote([(0, {"ok": True}), (0, {"ok": True, "journal_id": 7})])
    _patch(monkeypatch, fake)
    entries = publish.correction_entries(
        [
            {"text": "The block weighs 1000 tons, not 1100.", "evidence_id": "ev-01"},
            {"text": "Retired a second claim.", "evidence_id": "ev-02"},
        ],
        date(2026, 10, 2),
    )
    record = publish.correct(checked, entries)
    assert record["apply"]["journal_id"] == 7
    assert [c[1] for c in fake.calls] == [["--correct", "--dry-run"], ["--correct"]]
    sent = json.loads(fake.calls[1][2])
    assert sent == {
        "version": 1,
        "request_id": fx.REQ,
        "writer": bundle.WRITER,
        "corrections_append": [
            {
                "date": "2026-10-02",
                "text": "The block weighs 1000 tons, not 1100.",
                "evidence_id": "ev-01",
            },
            {"date": "2026-10-02", "text": "Retired a second claim.", "evidence_id": "ev-02"},
        ],
    }
    journal = list((checked.root / "corrections").glob("*.json"))
    assert len(journal) == 1
    stored = json.loads(journal[0].read_text(encoding="utf-8"))
    assert (stored["dry_run_exit_code"], stored["apply_exit_code"]) == (0, 0)
    assert stored["body_sha256"] == hashlib.sha256(fake.calls[1][2]).hexdigest()


def test_correct_with_report_sends_the_rechecked_paper(monkeypatch, checked):
    _as_published(checked)
    fake = FakeRemote([(0, {"ok": True}), (0, {"ok": True})])
    _patch(monkeypatch, fake)
    publish.correct(
        checked, [{"date": "2026-10-02", "text": "Rewrote the hook."}], with_report=True
    )
    sent = json.loads(fake.calls[1][2])
    assert sent["report"] == checked.paper.read_text(encoding="utf-8")
    assert sent["evidence"] == fx.EVIDENCE
    assert "rewrite" not in sent
    assert fake.uploads == []  # the images are on the VPS already


def test_correct_with_report_keeps_the_published_images(monkeypatch, checked):
    entries = [{"date": "2026-10-02", "text": "x"}]
    _patch(monkeypatch, FakeRemote([]))
    bundle.write_bundle(checked)  # a bundle alone is no publish
    with pytest.raises(StudioError, match="no published bundle in this workspace"):
        publish.correct(checked, entries, with_report=True)
    b = _as_published(checked)
    b["result"]["probative_images"] = []
    write_json(checked.published_bundle, b)
    with pytest.raises(StudioError, match="a correction cannot change the images"):
        publish.correct(checked, entries, with_report=True)


def test_correct_with_report_keeps_the_published_title_and_card(monkeypatch, checked):
    _as_published(checked)
    meta = json.loads(checked.meta.read_text(encoding="utf-8"))
    meta["card_description"] = meta["card_description"].replace("differ", "vary")
    write_json(checked.meta, meta)
    assert gates.run_check(checked)["passed"]
    bundle.write_bundle(checked)  # a re-bundle does not move the published baseline
    fake = FakeRemote([])
    _patch(monkeypatch, fake)
    with pytest.raises(StudioError, match="cannot change the title or card description"):
        publish.correct(checked, [{"date": "2026-10-02", "text": "x"}], with_report=True)
    assert fake.calls == []


def test_correct_republish_sends_the_checked_result(monkeypatch, checked):
    b = bundle.write_bundle(checked)
    applied = {"ok": True, "journal_id": 9, "side_effects": EFFECTS}
    fake = FakeRemote([(0, {"ok": True}), (0, applied)])
    _patch(monkeypatch, fake)
    record = publish.correct(
        checked, [{"date": "2026-10-02", "text": "Rewritten by Claude."}], republish=True
    )
    sent = json.loads(fake.calls[1][2])
    assert sent["result"] == b["result"]
    assert sent["result"]["corrections"] == []  # theo_publish keeps the published log
    assert "report" not in sent and "evidence" not in sent
    assert fake.uploads == [(fx.REQ, bundle.upload_names(b["result"]))]
    assert record["apply"]["side_effects"]["notify"] == {"discord": False}
    assert checked.published_bundle.read_bytes() == checked.bundle.read_bytes()


def test_a_republish_envelope_carries_the_bundles_own_writer(monkeypatch, tmp_path):
    """The envelope's writer is the bundle's own writer, not the module constant.
    theo_publish's shape gate compares the two ("result.writer differs from the bundle's
    writer"), so a constant sent next to a bundle whose dossier named another researcher is
    refused: that is what blocked the four campaign papers, all researched in the session."""
    data = fx.dossier_dict()
    data["manifest"]["research"]["researcher"] = "MiniMax-M3.1-Flash-Preview (mcode session)"
    ws = fx.complete_workspace(tmp_path, dossier=data)
    assert gates.run_check(ws)["passed"]
    b = bundle.write_bundle(ws)
    assert b["writer"]["research_model"] != bundle.WRITER["research_model"]
    applied = {"ok": True, "journal_id": 9, "side_effects": EFFECTS}
    fake = FakeRemote([(0, {"ok": True}), (0, applied)])
    _patch(monkeypatch, fake)
    publish.correct(ws, [{"date": "2026-10-02", "text": "Writer stamp corrected."}], republish=True)
    sent = json.loads(fake.calls[1][2])
    assert sent["writer"] == sent["result"]["writer"] == b["writer"]
    assert sent["writer"]["research_model"] == "MiniMax-M3.1-Flash-Preview"


def test_the_first_republish_of_a_rewrite_names_the_fresh_run(monkeypatch, checked):
    b = bundle.write_bundle(checked)
    _as_rewrite(checked)
    applied = {"ok": True, "journal_id": 9, "side_effects": EFFECTS}
    fake = FakeRemote([(0, {"ok": True}), (0, applied), (0, {"ok": True}), (0, applied)])
    _patch(monkeypatch, fake)
    entries = [{"date": "2026-10-02", "text": "Rewritten by Claude from a fresh Theo run."}]
    publish.correct(checked, entries, republish=True)
    sent = json.loads(fake.calls[1][2])
    assert sent["request_id"] == fx.REQ and sent["dossier_request_id"] == RUN
    assert sent["result"] == b["result"]
    assert fake.uploads == [(fx.REQ, bundle.upload_names(b["result"]))]
    publish.correct(checked, entries, republish=True)  # the run is closed: never sent again
    assert "dossier_request_id" not in json.loads(fake.calls[3][2])


def test_correct_a_legacy_paper_from_a_report_file(monkeypatch, tmp_path):
    ws = fx.make_workspace(tmp_path)
    fake = FakeRemote([(0, {"ok": True}), (0, {"ok": True})])
    _patch(monkeypatch, fake)
    report = numbering.build_paper(ws).markdown
    entries = [{"date": "2026-10-02", "text": "The press release came out on 8 July 1947."}]
    publish.correct(ws, entries, report=report)
    sent = json.loads(fake.calls[0][2])
    assert sent["report"] == report and "evidence" not in sent and "rewrite" not in sent
    assert [c[1] for c in fake.calls] == [["--correct", "--dry-run"], ["--correct"]]
    with pytest.raises(StudioError, match="fails validate_paper_artifact"):
        publish.correct(ws, entries, report="# Title\n\nUncited text without any marker at all.\n")
    with pytest.raises(StudioError, match="choose one of"):
        publish.correct(ws, entries, republish=True, report=report)


def test_a_claude_rewrite_from_a_report_file_says_so(monkeypatch, tmp_path):
    ws = fx.make_workspace(tmp_path)
    applied = {"ok": True, "journal_id": 9, "side_effects": EFFECTS}
    fake = FakeRemote([(0, {"ok": True}), (0, applied)])
    _patch(monkeypatch, fake)
    report = numbering.build_paper(ws).markdown
    entries = [{"date": "2026-10-02", "text": "Rewritten by Claude from the stored paper."}]
    record = publish.correct(ws, entries, report=report, rewrite=True)
    sent = json.loads(fake.calls[1][2])
    assert sent["rewrite"] is True and sent["report"] == report
    # a legacy rewrite is a republish: A sends the paper_published notice (owner decision 21)
    assert record["apply"]["side_effects"]["notify"] == {"discord": False}
    for other in ({"with_report": True}, {"republish": True}, {}):
        with pytest.raises(StudioError, match="--rewrite goes with --report-file"):
            publish.correct(ws, entries, rewrite=True, **other)


def test_a_refused_correction_dry_run_never_applies(monkeypatch, checked):
    fake = FakeRemote([(1, {"ok": False, "gates": {"retention": {"passed": False}}})])
    _patch(monkeypatch, fake)
    with pytest.raises(StudioError, match=r"refused: failing gates \['retention'\]"):
        publish.correct(checked, [{"date": "2026-10-02", "text": "x"}])
    assert len(fake.calls) == 1


def test_video_payload_validation():
    ok = publish.video_payload(fx.REQ, YT, "Baalbek", "2026-10-01T18:00:00+00:00", {"ev-01": 42})
    assert ok == {
        "version": 1,
        "request_id": fx.REQ,
        "writer": bundle.WRITER,
        "youtube_id": YT,
        "title": "Baalbek",
        "published_at": "2026-10-01T18:00:00+00:00",
        "evidence_timestamps": {"ev-01": 42},
    }
    with_poster = publish.video_payload(
        fx.REQ, YT, "Baalbek", "2026-10-01T18:00:00+00:00", {}, with_poster=True
    )
    assert with_poster["poster"] == f"/data/research-images/{fx.REQ}/video_{YT}.jpg"
    assert with_poster["poster"] == poster_web_path(fx.REQ, YT)
    with pytest.raises(StudioError, match="not a YouTube video id"):
        publish.video_payload(fx.REQ, "short", "t", "2026-10-01T18:00:00+00:00", {})
    with pytest.raises(StudioError, match="must carry a timezone"):
        publish.video_payload(fx.REQ, YT, "t", "2026-10-01T18:00:00", {})
    with pytest.raises(StudioError, match="ISO 8601 with a timezone"):
        publish.video_payload(fx.REQ, YT, "t", "1 October", {})
    with pytest.raises(StudioError, match="whole seconds"):
        publish.video_payload(fx.REQ, YT, "t", "2026-10-01T18:00:00+00:00", {"ev-1": 3})
    with pytest.raises(StudioError, match="whole seconds"):
        publish.video_payload(fx.REQ, YT, "t", "2026-10-01T18:00:00+00:00", {"ev-01": True})
    with pytest.raises(StudioError, match="a JSON object"):
        publish.video_payload(fx.REQ, YT, "t", "2026-10-01T18:00:00+00:00", [["ev-01", 3]])
    with pytest.raises(StudioError, match="is not a research request id"):
        publish.video_payload("../x", YT, "t", "2026-10-01T18:00:00+00:00", {})
    # the title the paper page shows is the YouTube title: at most 100 characters, no < or >
    for title in ("x" * 101, "Baalbek <b>", " "):
        with pytest.raises(StudioError, match="a title must be 1-100 characters"):
            publish.video_payload(fx.REQ, YT, title, "2026-10-01T18:00:00+00:00", {})


def test_register_video_dry_run_and_apply(monkeypatch):
    fake = FakeRemote(
        [(0, {"ok": True}), (1, {"ok": False, "gates": {"duplicate": {"passed": False}}})]
    )
    _patch(monkeypatch, fake)
    payload = publish.video_payload(fx.REQ, YT, "t", "2026-10-01T18:00:00+00:00", {})
    assert publish.register_video(payload, dry_run=True) == {"ok": True}
    with pytest.raises(
        StudioError, match=r"--register-video refused: failing gates \['duplicate'\]"
    ):
        publish.register_video(payload, dry_run=False)
    assert [c[1] for c in fake.calls] == [["--register-video", "--dry-run"], ["--register-video"]]


def _jpeg(path):
    Image.new("RGB", (1280, 720), (20, 30, 40)).save(path, format="JPEG", quality=80)
    return path


def test_a_poster_is_uploaded_between_two_dry_runs(monkeypatch, tmp_path):
    fake = FakeRemote([(0, {"ok": True}), (0, {"ok": True})])
    _patch(monkeypatch, fake)
    thumb = _jpeg(tmp_path / "thumbnail_2.jpg")
    payload = publish.prepare_video(fx.REQ, YT, "t", "2026-10-01T18:00:00+00:00", {}, thumb)
    assert fake.events == [
        ("run", ["--register-video", "--dry-run"]),
        ("upload", [thumb.read_bytes()]),
        ("run", ["--register-video", "--dry-run"]),
    ]
    assert fake.uploads == [(fx.REQ, [f"video_{YT}.jpg"])]
    assert "poster" not in json.loads(fake.calls[0][2])
    assert json.loads(fake.calls[1][2])["poster"] == poster_web_path(fx.REQ, YT)
    assert payload["poster"] == poster_web_path(fx.REQ, YT)


def test_a_known_video_stops_before_its_poster_is_uploaded(monkeypatch, tmp_path):
    fake = FakeRemote([(1, {"ok": False, "gates": {"duplicate": {"passed": False}}})])
    _patch(monkeypatch, fake)
    thumb = _jpeg(tmp_path / "thumbnail_1.jpg")
    with pytest.raises(StudioError, match=r"failing gates \['duplicate'\]"):
        publish.prepare_video(fx.REQ, YT, "t", "2026-10-01T18:00:00+00:00", {}, thumb)
    assert fake.uploads == []


def test_without_a_poster_one_dry_run_proves_the_registration(monkeypatch):
    fake = FakeRemote([(0, {"ok": True})])
    _patch(monkeypatch, fake)
    payload = publish.prepare_video(fx.REQ, YT, "t", "2026-10-01T18:00:00+00:00", {}, None)
    assert "poster" not in payload and fake.uploads == []
    assert [c[1] for c in fake.calls] == [["--register-video", "--dry-run"]]


def test_a_poster_must_be_a_jpeg_file(monkeypatch, tmp_path):
    fake = FakeRemote([(0, {"ok": True}), (0, {"ok": True})])
    _patch(monkeypatch, fake)
    png = tmp_path / "thumb.png"
    Image.new("RGB", (64, 36)).save(png, format="PNG")
    with pytest.raises(StudioError, match="is PNG, not a JPEG"):
        publish.prepare_video(fx.REQ, YT, "t", "2026-10-01T18:00:00+00:00", {}, png)
    with pytest.raises(StudioError, match="does not exist"):
        publish.upload_poster(fx.REQ, YT, tmp_path / "missing.jpg")
    assert fake.uploads == []


def test_a_bad_poster_is_refused_before_any_production_call(monkeypatch, tmp_path):
    fake = FakeRemote([])
    _patch(monkeypatch, fake)
    png = tmp_path / "thumb.png"
    Image.new("RGB", (64, 36)).save(png, format="PNG")
    for poster in (png, tmp_path / "missing.jpg"):
        with pytest.raises(StudioError, match="poster"):
            publish.prepare_video(fx.REQ, YT, "t", "2026-10-01T18:00:00+00:00", {}, poster)
    assert fake.calls == [] and fake.uploads == []
