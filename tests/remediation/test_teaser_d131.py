"""Owner decisions D131 and D132 of 2026-11-07 in lane WB's run (`teaser/run.py`).

D131 ("first make it cheaper, then run a2"): a shorts-v1 run that records `ECONOMY.json` stops a
site after `rewrite-v` when that rewrite named a sentence of the description for a contradicted
claim - D81/O7 hold such a card anyway, and wave a1 spent 121 answers judging cards it could never
write. The web agents' brief names the web.archive.org block. D132: `select --redo` writes a live,
checked card again, every writer of the site shown the owner's findings on it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import opus_handoff as OH  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from teaser import prompts as P  # noqa: E402
from teaser import prompts_shorts as PS  # noqa: E402
from teaser import run as R  # noqa: E402

from pipeline.utils import card_provenance as CP  # noqa: E402
from tests.remediation import shorts_cases as S  # noqa: E402
from tests.remediation import teaser_cases as T  # noqa: E402
from tests.remediation.test_teaser_shorts_run import (  # noqa: E402
    HUACA,
    MP,
    PAGE,
    check_json,
    make_run,
    passes,
    production_row,
    rates,
    sid,
    step,
    verifies,
    writes,
)

CONTRADICTED = T.judge_answer(
    T.judged_claim(),
    T.judged_claim(
        "CONTRADICTED", "occupied from roughly 3180 BC to around 2500 BC", PAGE, "built by the Inca"
    ),
)


def rewrite_json(repeats: list[str | None]) -> str:
    fields = ("card", "basis", "anchors", "reserve", "hook_type")
    return json.dumps({**{k: S.BY_NAME[MP][k] for k in fields}, "repeats": repeats})


def to_rewrite_v(tmp_path: Path, *, economy: bool) -> Path:
    """A run of Machu Picchu whose first verification contradicted a claim: due at `rewrite-v`."""
    run = make_run(tmp_path, [MP])
    step(run, tmp_path, "write", writes([MP]))
    step(run, tmp_path, "rate", rates(run, [MP]))
    step(run, tmp_path, "check", passes([MP]))
    step(run, tmp_path, "verify", {sid(MP): CONTRADICTED})
    if economy:
        R.record_economy(run, "D131")
    return run


# ------------------------------------------------------------------------------ D131: the stop
class TestTheDefectStop:
    def test_a_rewrite_that_names_a_description_sentence_ends_the_chain(
        self, tmp_path: Path
    ) -> None:
        run = to_rewrite_v(tmp_path, economy=True)
        step(run, tmp_path, "rewrite-v", {sid(MP): rewrite_json(["S5"])})
        state = R.states(run)[sid(MP)]
        assert (state.status, state.reason) == (R.CLEARED, R.DESCRIPTION_DEFECT_STOP)
        assert step(run, tmp_path, "check-v", {})["questions"] == 0
        R.outcomes(run)
        row = next(r for r in R.read_outcomes(run) if r["site_id"] == sid(MP))
        assert (row["status"], row["reason"], row["card"]) == (
            R.KEPT,
            R.DESCRIPTION_DEFECT_STOP,
            None,
        )
        assert [len(row["verifications"])] == [1]
        # the contradicted sentence still goes to the description's repair (D81)
        defects = R.read_jsonl(run / "DESCRIPTION_DEFECTS.jsonl")
        assert [(d["stage"], d["sentence"]) for d in defects] == [("verify", 5)]

    def test_a_rewrite_that_names_no_sentence_goes_on_to_its_check(self, tmp_path: Path) -> None:
        run = to_rewrite_v(tmp_path, economy=True)
        step(run, tmp_path, "rewrite-v", {sid(MP): rewrite_json([None])})
        assert R.status(run)["states"] == {"due check-v": 1}
        step(run, tmp_path, "check-v", passes([MP]))
        step(run, tmp_path, "verify2", verifies([MP]))
        assert R.status(run)["states"] == {"accepted": 1}

    def test_without_the_record_the_chain_is_as_before(self, tmp_path: Path) -> None:
        run = to_rewrite_v(tmp_path, economy=False)
        step(run, tmp_path, "rewrite-v", {sid(MP): rewrite_json(["S5"])})
        assert R.status(run)["states"] == {"due check-v": 1}
        assert R.spec_of(run) is R.SHORTS_SPEC and not R.SHORTS_SPEC.defect_stop

    def test_the_record_moves_only_the_run_that_has_it(self, tmp_path: Path) -> None:
        run = to_rewrite_v(tmp_path, economy=True)
        spec = R.spec_of(run)
        assert spec.defect_stop and spec.name == R.SHORTS and spec.stages == R.SHORTS_SPEC.stages
        record = json.loads((run / R.ECONOMY_FILE).read_text(encoding="utf-8"))
        assert (record["decision"], record["defect_stop"], record["run"]) == (
            "D131",
            True,
            run.name,
        )

    def test_the_record_is_refused_once_check_v_was_exported(self, tmp_path: Path) -> None:
        run = to_rewrite_v(tmp_path, economy=False)
        step(run, tmp_path, "rewrite-v", {sid(MP): rewrite_json(["S5"])})
        R.export_stage(run, "check-v", tmp_path / "handoff-check-v")
        with pytest.raises(R.RunError, match="exported \\['check-v'\\] already"):
            R.record_economy(run, "D131")
        assert not (run / R.ECONOMY_FILE).exists()

    def test_the_record_is_written_once(self, tmp_path: Path) -> None:
        run = to_rewrite_v(tmp_path, economy=True)
        with pytest.raises(R.RunError, match="recorded once"):
            R.record_economy(run, "D131")

    def test_a_v1_run_takes_no_record(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [MP], contract=R.V1)
        with pytest.raises(R.RunError, match="the economy is shorts-v1's"):
            R.record_economy(run, "D131")
        (run / R.ECONOMY_FILE).write_text(json.dumps({"defect_stop": True}), encoding="utf-8")
        with pytest.raises(R.RunError, match="not an economy record of a shorts-v1 run"):
            R.spec_of(run)

    def test_a_record_that_does_not_stop_is_refused(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [MP])
        (run / R.ECONOMY_FILE).write_text(json.dumps({"defect_stop": False}), encoding="utf-8")
        with pytest.raises(R.RunError, match="not an economy record"):
            R.spec_of(run)

    def test_the_command_line_records_it(self, tmp_path: Path) -> None:
        run = to_rewrite_v(tmp_path / "a", economy=False)
        assert R.main(["economy", "--run", str(run), "--decision", "D131"]) == 0
        assert R.spec_of(run).defect_stop


# ------------------------------------------------------------------------------ D131: the brief
class TestTheArchiveNote:
    def test_every_web_agent_is_told_and_no_other(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [MP])
        step(run, tmp_path, "write", writes([MP]))
        step(run, tmp_path, "rate", rates(run, [MP]))
        step(run, tmp_path, "check", passes([MP]))
        handoff = tmp_path / "handoff-verify"
        R.export_stage(run, "verify", handoff)
        assert R.ARCHIVE_NOTE in R.brief(run, handoff, "verify-001")
        assert "web.archive.org" in R.ARCHIVE_NOTE
        writer = R.brief(run, tmp_path / "handoff-write", "write-001")
        assert R.ARCHIVE_NOTE not in writer


# ------------------------------------------------------------------------------ D132: --redo
LIVE_STAMP = OH.OPUS_MODEL


def current_row(name: str) -> dict[str, Any]:
    """A production row whose live card is a checked version-3 card of shorts-v1: current."""
    live = production_row(name)
    provenance = CP.build_v3(
        run="wb-shorts-wave-a1", ai_system=M.AI_SYSTEM_CLAUDE, card=live["card"],
        description=live["description"], stage="check", checker="card_fact_checker:t-1",
        checked_at="2026-11-06T12:00:00+00:00", claims=[{"claim": "c", "support": ["S1"]}],
        verify={"verdict": "VERIFIED", "stage": "verify", "by": "card_web_verifier:t-2",
                "at": "2026-11-06T13:00:00+00:00", "claims": 1, "unproven": 0,
                "text_sha256": CP.text_sha256(live["card"])},
        web_facts=[], models=dict.fromkeys(("write", "rate", "check", "verify"), LIVE_STAMP),
        hook={"type": "object", "rating": 4, "variant": 1}, anchors=["x"], reserve=["S2"],
        shorts_ready=True,
    )  # fmt: skip
    return {**live, "card_provenance": provenance}


REASON = "The register says half-moon, not crescent: do not state the shape as a crescent."


def redo_file(tmp_path: Path, name: str, card: str | None = None) -> Path:
    path = tmp_path / "REDO.json"
    entry = {
        "card": card if card is not None else S.BY_NAME[name]["live_card"],
        "reasons": [REASON],
    }
    path.write_text(json.dumps({"decision": "D132", "sites": {sid(name): entry}}), "utf-8")
    return path


def redo_run(
    tmp_path: Path,
    rows: list[dict[str, Any]],
    sites: list[str],
    redo: Path,
    contract: str = R.SHORTS,
) -> Path:
    run = tmp_path / "runs" / "wb-shorts-redo"
    export = T.tagged({"site": rows})
    listed = tmp_path / "SITES.txt"
    listed.write_text("\n".join(sites) + "\n", "utf-8")

    def read(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(export, encoding="utf-8", newline="\n")

    R.select(
        run,
        read=read,
        sites_file=listed,
        pilot=None,
        exclude=[],
        contract=contract,
        redo_file=redo,
    )
    return run


class TestTheRedo:
    def test_a_current_card_is_asked_again_with_the_finding(self, tmp_path: Path) -> None:
        rows = [current_row(MP), production_row(HUACA)]
        run = redo_run(tmp_path, rows, [sid(MP), sid(HUACA)], redo_file(tmp_path, MP))
        record = json.loads((run / "RUN.json").read_text(encoding="utf-8"))
        assert record["redo"]["decision"] == "D132" and record["sites"] == 2
        site = R.bases(run)[sid(MP)]
        assert site.redo == ((S.BY_NAME[MP]["live_card"], (REASON,)),)
        assert R.bases(run)[sid(HUACA)].redo == ()
        handoff = tmp_path / "handoff-write"
        R.export_stage(run, "write", handoff)
        prompts = {
            line["label"]: (handoff / line["prompt_path"]).read_text("utf-8")
            for line in OH.manifest(handoff)
        }
        finding = P.Finding(S.BY_NAME[MP]["live_card"], (REASON,))
        assert prompts[sid(MP)] == PS.rewrite_prompt(site, (finding,))
        assert REASON in prompts[sid(MP)]
        # every other site is asked exactly as before
        assert prompts[sid(HUACA)] == PS.writer_prompt(R.bases(run)[sid(HUACA)])

    def test_the_finding_stays_before_the_checkers_findings(self, tmp_path: Path) -> None:
        run = redo_run(tmp_path, [current_row(MP)], [sid(MP)], redo_file(tmp_path, MP))
        step(run, tmp_path, "write", writes([MP]))
        step(run, tmp_path, "rate", rates(run, [MP]))
        step(run, tmp_path, "check", {sid(MP): check_json("FAIL")})
        handoff = tmp_path / "handoff-rewrite1"
        R.export_stage(run, "rewrite1", handoff)
        prompt = (handoff / OH.manifest(handoff)[0]["prompt_path"]).read_text("utf-8")
        state = R.states(run)[sid(MP)]
        finding = P.Finding(S.BY_NAME[MP]["live_card"], (REASON,))
        assert prompt == PS.rewrite_prompt(R.bases(run)[sid(MP)], (finding, *state.findings))
        assert prompt.index(REASON) < prompt.index("No sentence says it.")

    def test_the_live_card_must_be_the_one_the_finding_is_about(self, tmp_path: Path) -> None:
        with pytest.raises(R.RunError, match="not the card the finding is about"):
            redo_run(tmp_path, [current_row(MP)], [sid(MP)], redo_file(tmp_path, MP, "Other."))

    def test_only_a_current_card_is_written_again(self, tmp_path: Path) -> None:
        with pytest.raises(R.RunError, match="not as a current card"):
            redo_run(tmp_path, [production_row(MP)], [sid(MP)], redo_file(tmp_path, MP))

    def test_a_redo_site_must_be_in_the_sites_file(self, tmp_path: Path) -> None:
        rows = [current_row(MP), production_row(HUACA)]
        with pytest.raises(R.RunError, match="must be in the run's --sites file"):
            redo_run(tmp_path, rows, [sid(HUACA)], redo_file(tmp_path, MP))

    def test_a_redo_is_shorts_v1s(self, tmp_path: Path) -> None:
        with pytest.raises(R.RunError, match="--contract shorts-v1"):
            redo_run(tmp_path, [current_row(MP)], [sid(MP)], redo_file(tmp_path, MP), R.V1)

    def test_a_redo_file_names_a_decision_and_a_reason(self, tmp_path: Path) -> None:
        path = tmp_path / "BAD.json"
        path.write_text(json.dumps({"decision": "", "sites": {}}), "utf-8")
        with pytest.raises(R.RunError, match="no owner decision"):
            R.read_redo(path)
        path.write_text(json.dumps({"decision": "D132", "sites": {"x": {"card": "c"}}}), "utf-8")
        with pytest.raises(R.RunError, match="at least one reason"):
            R.read_redo(path)
