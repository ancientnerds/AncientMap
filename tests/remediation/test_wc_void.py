"""`verify-void` (owner decision D10, 2026-10-08; master plan X6): the MiniMax-answered verification
answers of a lane WC run move aside so that a Claude agent answers the same questions and the round
is imported again. A round is written once, so this is the one tested way to take it back - and it
never moves a Claude answer, never touches a built run and is a dry run unless asked.

The three real cases it was built for are the runs `mass-2026-09-27-03` (round 1 exported and
answered by MiniMax, not imported), `-04` (round 1 imported with 109 MiniMax of 480 answers, round 2
exported with 60 MiniMax answers) and `-05` (both rounds imported, round 2 all MiniMax). No socket, no
model, no database.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from wc import cli as C  # noqa: E402
from wc import void as V  # noqa: E402

from tests.remediation import wc_fixtures as FX  # noqa: E402
from tests.remediation.test_wc_verify import _checked, _hv  # noqa: E402
from tests.remediation.wc_fixtures import OH, WC4, wiki_cache  # noqa: E402,F401


def _stamp(handoff: Path, label: str, model: str) -> None:
    """Re-stamp a recorded answer as the model that 'really' wrote it - the state of the rounds
    answered between 2026-10-03 and 2026-10-07, whose agent names say `opus-...`."""
    for line in OH.manifest(handoff):
        if line["label"] == label:
            path = handoff / line["answer_path"]
            stored = json.loads(path.read_text(encoding="utf-8"))
            stored["model"] = model
            path.write_text(json.dumps(stored), encoding="utf-8")


def _answer_path(handoff: Path, label: str) -> Path:
    (line,) = [line for line in OH.manifest(handoff) if line["label"] == label]
    return handoff / line["answer_path"]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _exported(tmp_path: Path, model: str = OH.MINIMAX_MODEL) -> Path:
    """The `mass-03` case: verification round 1 exported, answered, not imported."""
    run = _checked(tmp_path)
    C.cmd_verify_export(run, _hv(tmp_path), batch_size=5)
    FX.record_answers(
        _hv(tmp_path),
        {
            FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED"] * 3),
            FX.SITE_B: FX.verification(FX.SITE_B, ["SUPPORTED"] * 2),
        },
        by="opus-wc",
        model=model,
    )
    return run


def _round_one_imported(tmp_path: Path) -> Path:
    """Round 1 imported over Claude answers; site A's answer then re-stamped MiniMax (the `mass-04`
    case: 109 of 480), site B's WRONG so that `verify2` is due for it."""
    run = _checked(tmp_path)
    C.cmd_verify_export(run, _hv(tmp_path), batch_size=5)
    FX.record_answers(
        _hv(tmp_path),
        {
            FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED", "SUPPORTED", "WRONG"]),
            FX.SITE_B: FX.verification(FX.SITE_B, ["SUPPORTED", "SUPPORTED"]),
        },
        by="opus-wc",
        model=OH.SONNET_MODEL,
    )
    C.cmd_verify_import(run, _hv(tmp_path), client=FX.FakeClient(), pace=0.0)
    _stamp(_hv(tmp_path), FX.SITE_A, OH.MINIMAX_MODEL)
    return run


def test_the_dry_run_reports_what_would_move_and_moves_nothing(tmp_path: Path) -> None:
    run = _exported(tmp_path)
    before = {p: _sha(p) for p in (_hv(tmp_path)).rglob("*.answer.json")}
    report = V.verify_void(run, base=tmp_path)
    assert report["applied"] is False and report["void_from"] == 1
    assert report["answers_to_void"] == 2 and report["rounds_taken_back"] == []
    (summary,) = report["rounds"]
    assert (summary["questions"], summary["minimax"], summary["claude"]) == (2, 2, 0)
    assert {p: _sha(p) for p in (_hv(tmp_path)).rglob("*.answer.json")} == before
    assert not list((run / "verify").glob("VOID-*"))


def test_an_unimported_round_loses_its_minimax_answers_and_is_answered_again_by_claude(
    tmp_path: Path,
) -> None:
    run = _exported(tmp_path)
    handoff = _hv(tmp_path)
    paths = {label: _answer_path(handoff, label) for label in (FX.SITE_A, FX.SITE_B)}
    hashes = {label: _sha(path) for label, path in paths.items()}
    report = V.verify_void(run, base=tmp_path, apply=True, tag="t1")
    assert report["applied"] is True and report["answers_to_void"] == 2
    archive = handoff.with_name(handoff.name + ".void-t1")
    for label, path in paths.items():
        assert not path.exists()  # the answer left the handoff ...
        moved = archive / path.relative_to(handoff)
        assert _sha(moved) == hashes[label]  # ... byte for byte, in the same layout
    # the questions stay: the same prompts are answered again, and validate finds exactly those
    assert len(OH.manifest(handoff)) == 2
    assert not OH.validate(handoff).ok and len(OH.validate(handoff).missing) == 2
    record = json.loads((run / "verify" / "VOID-t1.json").read_text(encoding="utf-8"))
    assert record["status"] == "applied" and len(record["answers"]) == 2
    assert {a["sha256"] for a in record["answers"]} == set(hashes.values())
    # a Claude agent answers them, and the round imports as it never had
    FX.record_answers(
        handoff,
        {
            FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED"] * 3),
            FX.SITE_B: FX.verification(FX.SITE_B, ["SUPPORTED"] * 2),
        },
        by="sonnet-wc",
        model=OH.SONNET_MODEL,
    )
    assert C.cmd_verify_import(run, handoff, client=FX.FakeClient(), pace=0.0)["sites"] == 2


def test_only_the_minimax_answers_of_the_round_move_and_a_claude_answer_stays(
    tmp_path: Path,
) -> None:
    run = _round_one_imported(tmp_path)
    handoff = _hv(tmp_path)
    claude = _answer_path(handoff, FX.SITE_B)
    kept_hash = _sha(claude)
    report = V.verify_void(run, base=tmp_path, apply=True, tag="t2")
    assert report["void_from"] == 1 and report["answers_to_void"] == 1
    assert claude.exists() and _sha(claude) == kept_hash  # a Claude answer is never moved
    assert not _answer_path(handoff, FX.SITE_A).exists()
    # the import record rests on the voided answer: it is set aside, and the round imports again
    verified = run / "verify" / "round-1"
    assert not (verified / "VERIFIED.jsonl").exists()
    assert (verified / "VERIFIED.jsonl.void").exists()
    FX.record_answers(
        handoff,
        {FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED"] * 3)},
        by="sonnet-wc",
        model=OH.SONNET_MODEL,
    )
    summary = C.cmd_verify_import(run, handoff, client=FX.FakeClient(), pace=0.0)
    assert summary["sites"] == 2 and summary["outcomes"] == {"verified": 2}


def test_the_stamp_is_read_from_the_file_not_from_the_agents_name(tmp_path: Path) -> None:
    """The MiniMax answers of 2026-10-03 to 2026-10-07 are named `opus-wc-verify-...`; a Claude
    answer named like a MiniMax agent is still Claude's."""
    run = _exported(tmp_path, model=OH.OPUS_MODEL)
    handoff = _hv(tmp_path)
    _stamp(handoff, FX.SITE_A, OH.MINIMAX_MODEL)
    assert "opus" in json.loads(_answer_path(handoff, FX.SITE_A).read_text("utf-8"))["answered_by"]
    report = V.verify_void(run, base=tmp_path, apply=True, tag="t3")
    assert report["answers_to_void"] == 1
    assert (
        not _answer_path(handoff, FX.SITE_A).exists() and _answer_path(handoff, FX.SITE_B).exists()
    )


def test_a_later_round_is_taken_back_whole_and_its_handoff_archived(tmp_path: Path) -> None:
    run = _round_one_imported(tmp_path)
    handoff2 = _hv(tmp_path, "verify2")
    # site A's WRONG sentence is dropped by round 1: round 2 asks about the text it left
    C.cmd_verify_export(run, handoff2, batch_size=5)
    FX.record_answers(
        handoff2,
        {FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED", "SUPPORTED"])},
        by="opus-wc",
        model=OH.MINIMAX_MODEL,
    )
    report = V.verify_void(run, base=tmp_path, apply=True, tag="t4")
    assert report["void_from"] == 1 and report["rounds_taken_back"] == [2]
    assert report["answers_to_void"] == 2  # round 1's MiniMax answer and round 2's
    # round 2 is gone as a round: no ROUND.json, no handoff - a fresh export may name the same path
    assert not (run / "verify" / "round-2" / "ROUND.json").exists()
    assert (run / "verify" / "void-t4" / "round-2-ROUND.json").exists()
    assert not handoff2.exists()
    archive = handoff2.with_name(handoff2.name + ".void-t4")
    assert any(archive.rglob("*.answer.json")) and any(archive.rglob("*.prompt.txt"))
    # the voided first round is answered again, imported, and round 2 is exported anew
    FX.record_answers(
        _hv(tmp_path),
        {FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED", "SUPPORTED", "WRONG"])},
        by="sonnet-wc",
        model=OH.SONNET_MODEL,
    )
    C.cmd_verify_import(run, _hv(tmp_path), client=FX.FakeClient(), pace=0.0)
    assert C.cmd_verify_export(run, handoff2, batch_size=5)["stage"] == "verify2"


def test_a_round_that_was_imported_alone_is_voided_alone(tmp_path: Path) -> None:
    """The `mass-05` case: round 1 stays, round 2's MiniMax answers and import record go."""
    run = _checked(tmp_path)
    C.cmd_verify_export(run, _hv(tmp_path), batch_size=5)
    FX.record_answers(
        _hv(tmp_path),
        {
            FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED", "SUPPORTED", "WRONG"]),
            FX.SITE_B: FX.verification(FX.SITE_B, ["SUPPORTED"] * 2),
        },
        by="sonnet-wc",
        model=OH.SONNET_MODEL,
    )
    C.cmd_verify_import(run, _hv(tmp_path), client=FX.FakeClient(), pace=0.0)
    handoff2 = _hv(tmp_path, "verify2")
    C.cmd_verify_export(run, handoff2, batch_size=5)
    FX.record_answers(
        handoff2,
        {FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED", "SUPPORTED"])},
        by="opus-wc",
        model=OH.MINIMAX_MODEL,
    )
    # round 2 was imported over a MiniMax answer before the import refused them: re-stamp after
    _stamp(handoff2, FX.SITE_A, OH.OPUS_MODEL)
    C.cmd_verify_import(run, handoff2, client=FX.FakeClient(), pace=0.0)
    _stamp(handoff2, FX.SITE_A, OH.MINIMAX_MODEL)
    one = {p: _sha(p) for p in _hv(tmp_path).rglob("*.answer.json")}
    report = V.verify_void(run, base=tmp_path, apply=True, tag="t5")
    assert report["void_from"] == 2 and report["rounds_taken_back"] == []
    assert {p: _sha(p) for p in _hv(tmp_path).rglob("*.answer.json")} == one  # round 1 untouched
    assert (run / "verify" / "round-1" / "VERIFIED.jsonl").exists()
    assert not (run / "verify" / "round-2" / "VERIFIED.jsonl").exists()
    assert (run / "verify" / "round-2" / "VERIFIED.jsonl.void").exists()
    assert (
        run / "verify" / "round-2" / "ROUND.json"
    ).exists()  # the same questions are asked again
    assert not _answer_path(handoff2, FX.SITE_A).exists()


def test_a_claude_answer_in_a_later_round_is_never_archived(tmp_path: Path) -> None:
    run = _round_one_imported(tmp_path)
    handoff2 = _hv(tmp_path, "verify2")
    C.cmd_verify_export(run, handoff2, batch_size=5)
    FX.record_answers(
        handoff2,
        {FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED", "SUPPORTED"])},
        by="sonnet-wc",
        model=OH.SONNET_MODEL,
    )
    with pytest.raises(V.VoidError, match="holds 1 Claude answer"):
        V.verify_void(run, base=tmp_path, apply=True, tag="t6")
    assert (run / "verify" / "round-2" / "ROUND.json").exists() and handoff2.exists()
    assert _answer_path(_hv(tmp_path), FX.SITE_B).exists()
    assert not list((run / "verify").glob("VOID-*"))


def test_a_run_without_a_minimax_answer_is_left_alone_even_when_applied(tmp_path: Path) -> None:
    run = _exported(tmp_path, model=OH.SONNET_MODEL)
    before = {p: _sha(p) for p in tmp_path.rglob("*") if p.is_file()}
    report = V.verify_void(run, base=tmp_path, apply=True, tag="t7")
    assert report["void_from"] is None and report["applied"] is False
    assert {p: _sha(p) for p in tmp_path.rglob("*") if p.is_file()} == before


def test_a_built_run_is_never_voided(tmp_path: Path) -> None:
    run = _exported(tmp_path)
    (run / "FINAL.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(V.VoidError, match="was built"):
        V.verify_void(run, base=tmp_path, apply=True)
    assert _answer_path(_hv(tmp_path), FX.SITE_A).exists()


def test_a_run_without_a_verification_round_has_nothing_to_void(tmp_path: Path) -> None:
    run = _checked(tmp_path)
    with pytest.raises(V.VoidError, match="no verification round"):
        V.verify_void(run, base=tmp_path)


def test_a_void_tag_is_used_once_and_a_second_void_of_one_round_is_refused(
    tmp_path: Path,
) -> None:
    run = _exported(tmp_path)
    V.verify_void(run, base=tmp_path, apply=True, tag="t8")
    FX.record_answers(  # MiniMax answered again, by hand: not a thing the answer command allows
        _hv(tmp_path),
        {FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED"] * 3)},
        by="opus-wc",
        model=OH.MINIMAX_MODEL,
    )
    with pytest.raises(V.VoidError, match="VOID-t8.json exists"):
        V.verify_void(run, base=tmp_path, apply=True, tag="t8")
    assert _answer_path(_hv(tmp_path), FX.SITE_A).exists()


def test_an_answer_file_that_cannot_be_read_stops_the_command_before_anything_moves(
    tmp_path: Path,
) -> None:
    run = _exported(tmp_path)
    _answer_path(_hv(tmp_path), FX.SITE_B).write_text("{not json", encoding="utf-8")
    with pytest.raises(V.VoidError, match="cannot be read"):
        V.verify_void(run, base=tmp_path, apply=True, tag="t9")
    assert _answer_path(_hv(tmp_path), FX.SITE_A).exists()


def test_the_stages_are_the_lanes_verification_stages() -> None:
    assert V.VERIFY_STAGES == WC4.VERIFY_STAGES


def test_the_command_line_is_a_dry_run_unless_apply_is_given(tmp_path: Path, capsys) -> None:
    run = _exported(tmp_path)
    assert C.main(["verify-void", "--run-dir", str(run)]) == 0
    out = capsys.readouterr().out
    assert '"applied": false' in out and "WC_EXIT=0" in out
    assert _answer_path(_hv(tmp_path), FX.SITE_A).exists()
    assert C.main(["verify-void", "--run-dir", str(run), "--apply", "--tag", "cli"]) == 0
    assert not _answer_path(_hv(tmp_path), FX.SITE_A).exists()
