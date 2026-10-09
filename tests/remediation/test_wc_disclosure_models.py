"""Lane WC and WN: the AI disclosure of a new write is derived from the models that answered
(owner decision D6, 2026-10-08), not named by a constant.

`wc/cli.py build` reads the stamp of every check, write and verification answer from that answer's
own write-once file in the round's handoff directory (`answer_stamp`; `ANSWERS.jsonl` and
`VERIFIED.jsonl` keep no copy, so a round imported before the stamp existed builds too) and passes
the disclosure `model4.ai_system_for` derives to the check record, the evidence and the provenance. Nothing here
opens a socket, calls a model or touches a database.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _path in (REPO / "scripts" / "remediation", REPO / "output" / "remediation" / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import opus_handoff as OH  # noqa: E402
from phase3.run import read_jsonl  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import wc4 as WC4  # noqa: E402
from wc import cli  # noqa: E402

from tests.remediation import wc_fixtures as FX  # noqa: E402
from tests.remediation import wn_fixtures as WX  # noqa: E402


def _rows() -> list[dict]:
    return [WX.wn_row(WX.SITE_N)]


def _built(tmp_path: Path, **models: str) -> tuple[Path, WC4.WcOutcome]:
    run, plan = WX.build_wn_run(
        tmp_path, _rows(), {WX.SITE_N: WX.good(WX.SITE_N)}, pilot=False, **models
    )
    (batch,) = read_jsonl(plan)
    (outcome,) = [WC4.WcOutcome.from_dict(o) for o in batch["outcomes"]]
    return run, outcome


def _disclosures(outcome: WC4.WcOutcome) -> set[str]:
    assert outcome.raw_data is not None
    return {
        outcome.raw_data[M.PROVENANCE_KEY]["ai_system"],
        outcome.raw_data[WC4.CHECK_KEY]["checker"],
        outcome.evidence["checker"],
    }


@pytest.mark.parametrize(
    ("writer", "verifier", "expected"),
    [
        (OH.SONNET_MODEL, OH.OPUS_MODEL, M.AI_SYSTEM_CLAUDE),
        (OH.HAIKU_MODEL, OH.SONNET_MODEL, M.AI_SYSTEM_CLAUDE_HAIKU),
        # a MiniMax answer is no longer imported (2026-10-09, `cli._require_role`): the rows MiniMax
        # answered were written before, and `disclosure_of` below still reads their stamps
    ],
)
def test_the_provenance_the_check_record_and_the_evidence_name_the_derived_disclosure(
    tmp_path: Path, writer: str, verifier: str, expected: str
) -> None:
    run, outcome = _built(tmp_path, writer_model=writer, verifier_model=verifier)

    assert _disclosures(outcome) == {expected}
    # the gate's own invariants accept the derived disclosure, whichever it is
    assert WC4.wc_problems(outcome.description, outcome.raw_data, marking="none") == []
    assert WC4.evidence_problems(outcome.evidence, outcome.description, outcome.raw_data) == []
    # the stamps are read from the answer files, and the run's own records keep no copy of them
    (answers,) = read_jsonl(run / "round-1" / "ANSWERS.jsonl")
    assert "model" not in answers
    (verified,) = read_jsonl(run / "verify" / "round-1" / "VERIFIED.jsonl")
    assert "model" not in verified
    assert (
        cli.answer_stamp(answers["handoff"], answers["batch_id"], cli.WRITE_STAGE, answers["label"])
        == writer
    )
    assert cli._verification_stamps(run) == {verified["site_id"]: [verifier]}


def test_the_verified_row_keeps_the_stamp_beside_the_round_not_inside_it(tmp_path: Path) -> None:
    """The round is `wc4.ROUND_KEYS` exactly (the journal's evidence pins that shape); the stamp is
    the row's own key, like `site_id`, and `_verification_inputs` hands the round on without it."""
    run, _ = _built(tmp_path)
    inputs = cli._verification_inputs(run)
    (rounds,) = inputs.values()
    assert all(set(r) == WC4.ROUND_KEYS for r in rounds)


# ------------------------------------------------------------------------------- disclosure_of
def _checked(*attempts: dict) -> cli.Checked:
    return cli.Checked({"site_id": "s"}, {}, list(attempts), [], {})


def _answered(tmp_path: Path, round_no: int, model: str, stage: str = cli.STAGE) -> dict:
    """A check attempt as `ANSWERS.jsonl` keeps it - no `model` key - and the answer file it names."""
    batch, label = f"wc-000{round_no}", "s"
    path = tmp_path / "handoff" / f"r{round_no}" / OH.answer_relpath(batch, stage, label)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"model": model}), encoding="utf-8")
    return {
        "round": round_no,
        "handoff": (tmp_path / "handoff" / f"r{round_no}").as_posix(),
        "batch_id": batch,
        "label": label,
        "answered_by": f"agent-{round_no}",
    }


def test_disclosure_of_reads_every_check_round_and_every_verifier(tmp_path: Path) -> None:
    checked = _checked(
        _answered(tmp_path, 1, OH.SONNET_MODEL), _answered(tmp_path, 2, OH.OPUS_MODEL)
    )
    assert cli.disclosure_of(checked, [OH.OPUS_MODEL]) == M.AI_SYSTEM_CLAUDE
    assert cli.disclosure_of(checked, [OH.HAIKU_MODEL]) == M.AI_SYSTEM_CLAUDE_HAIKU
    assert cli.disclosure_of(checked, [OH.MINIMAX_MODEL]) == M.AI_SYSTEM
    minimax_in_round_two = _checked(
        _answered(tmp_path, 3, OH.SONNET_MODEL), _answered(tmp_path, 4, OH.MINIMAX_MODEL)
    )
    assert cli.disclosure_of(minimax_in_round_two, []) == M.AI_SYSTEM


def test_a_round_imported_before_the_stamp_was_kept_builds_from_its_answer_files(
    tmp_path: Path,
) -> None:
    """Every check round on disk before 2026-10-08 (pilot-27 to mass-05) has attempts without a
    `model` key; the write-once answer files hold the stamps, so such a round discloses from them."""
    attempt = _answered(tmp_path, 1, OH.OPUS_MODEL)
    assert "model" not in attempt
    assert cli.disclosure_of(_checked(attempt), [OH.SONNET_MODEL]) == M.AI_SYSTEM_CLAUDE


def test_a_write_round_is_read_at_the_write_stage(tmp_path: Path) -> None:
    attempt = _answered(tmp_path, 1, OH.MINIMAX_MODEL, stage=cli.WRITE_STAGE)
    assert cli.disclosure_of(_checked(attempt), [OH.OPUS_MODEL], cli.KIND_WN) == M.AI_SYSTEM
    with pytest.raises(FileNotFoundError):
        cli.disclosure_of(_checked(attempt), [OH.OPUS_MODEL], cli.KIND_WC)


# ------------------------------------------------------------------- the provenance helpers
def test_provenance_after_gives_a_web_text_the_disclosure_it_is_handed() -> None:
    site = FX.plan_site(FX.row(WX.SITE_N, None, raw_data=None))
    for system in sorted(M.AI_SYSTEMS):
        provenance = WC4.provenance_after(site, "A text.", ai_system=system)
        assert isinstance(provenance, M.WebProvenance) and provenance.ai_system == system


def test_a_foreign_disclosure_is_refused_where_it_is_handed_on() -> None:
    site = FX.plan_site(FX.row(WX.SITE_N, None, raw_data=None))
    with pytest.raises(ValueError, match="ai_system"):
        WC4.provenance_after(site, "A text.", ai_system="someone else")
