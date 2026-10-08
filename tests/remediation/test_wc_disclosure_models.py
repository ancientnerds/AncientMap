"""Lane WC and WN: the AI disclosure of a new write is derived from the models that answered
(owner decision D6, 2026-10-08), not named by a constant.

`wc/cli.py build` reads the stamp of every check or write answer (`ANSWERS.jsonl`, key `model`) and
of every verification answer (`VERIFIED.jsonl`, key `model`) and passes the disclosure
`model4.ai_system_for` derives to the check record, the evidence and the provenance. Nothing here
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
        (OH.SONNET_MODEL, OH.OPUS_MODEL, M.AI_SYSTEM_CLAUDE_ONLY),
        (OH.HAIKU_MODEL, OH.SONNET_MODEL, M.AI_SYSTEM_CLAUDE_ONLY),
        (OH.MINIMAX_MODEL, OH.OPUS_MODEL, M.AI_SYSTEM),
        (OH.SONNET_MODEL, OH.MINIMAX_MODEL, M.AI_SYSTEM),
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
    # and the stamps are in the run's own files, where the derivation read them
    (answers,) = read_jsonl(run / "round-1" / "ANSWERS.jsonl")
    assert answers["model"] == writer
    (verified,) = read_jsonl(run / "verify" / "round-1" / "VERIFIED.jsonl")
    assert verified["model"] == verifier


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


def _attempt(round_no: int = 1, **extra: str) -> dict:
    return {"round": round_no, "answered_by": f"agent-{round_no}", **extra}


def test_disclosure_of_reads_every_check_round_and_every_verifier() -> None:
    checked = _checked(_attempt(1, model=OH.SONNET_MODEL), _attempt(2, model=OH.OPUS_MODEL))
    assert cli.disclosure_of(checked, [OH.HAIKU_MODEL]) == M.AI_SYSTEM_CLAUDE_ONLY
    assert cli.disclosure_of(checked, [OH.MINIMAX_MODEL]) == M.AI_SYSTEM
    minimax_in_round_two = _checked(
        _attempt(1, model=OH.SONNET_MODEL), _attempt(2, model=OH.MINIMAX_MODEL)
    )
    assert cli.disclosure_of(minimax_in_round_two, []) == M.AI_SYSTEM


def test_disclosure_of_refuses_an_attempt_imported_before_the_stamp_was_kept() -> None:
    """A round imported before 2026-10-08 kept no `model`: nothing says who answered, and the
    disclosure is not guessed (the in-flight MiniMax runs are exactly the case that matters)."""
    checked = _checked(_attempt(1, model=OH.SONNET_MODEL), _attempt(2))
    with pytest.raises(cli.WcRunError, match="round 2.*model"):
        cli.disclosure_of(checked, [OH.OPUS_MODEL])


def test_a_verification_round_imported_before_the_stamp_was_kept_is_refused(
    tmp_path: Path,
) -> None:
    run, _ = _built(tmp_path)
    path = run / "verify" / "round-1" / "VERIFIED.jsonl"
    rows = read_jsonl(path)
    for row in rows:
        del row["model"]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    with pytest.raises(cli.WcRunError, match="verification round 1.*model"):
        cli._verification_stamps(run)


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
