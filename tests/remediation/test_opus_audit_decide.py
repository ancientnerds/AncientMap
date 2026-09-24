"""The decision rule of the Opus re-verification (`scripts/remediation/opus_audit/decide.py`).

RULES.md "Decision rule", applied only to verdicts that passed the quote check: a pass-1 keep
stands; two passes that are not keep revert the row; a pass-2 keep goes to a third judge; a failed
quote check on a deciding verdict sends the row back to be judged again. Superseded rows are decided
but never reverted (rule 6); a wrong-both proposal is carried, never written (rule 5). The quote
checks are built by the tests, so nothing here reads a page.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from opus_audit import decide as D  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

from pipeline.utils.text import categorize_period  # noqa: E402

EVIDENCE = "runs/batch-0001/evidence/site-1%2Fenwiki.txt"
OK = Q.VerdictCheck(True, (Q.QuoteResult(EVIDENCE, "q", Q.FOUND, "as served"),), "")
FAILED = Q.VerdictCheck(False, (Q.QuoteResult(EVIDENCE, "q", Q.NOT_FOUND, ""),), Q.NOT_FOUND)


def row(key: str = "phase3:k1", **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "change_key": key,
        "site_id": f"site-{key}",
        "site_name": "Tarmatambo",
        "column": "site_type",
        "old_value": "City/town/settlement",
        "written_value": "Archaeological site",
        "current_value": "Archaeological site",
        "superseded": False,
        "evidence_files": [EVIDENCE],
    }
    base.update(over)
    return base


def verdict(key: str, name: str, right: str | None = None, quote: str = "q") -> dict[str, Any]:
    return {
        "change_key": key,
        "verdict": name,
        "right_value": right,
        "reason": f"{name} because",
        "quotes": [{"source": EVIDENCE, "quote": quote}],
    }


def verdicts(key: str = "phase3:k1", *route: str, rights: tuple[str | None, ...] = ()) -> dict:
    """The raw verdicts of one row whose route is `route` (p1, then p2, then tie)."""
    out: dict[str, dict[str, Any]] = {"p1": {}, "p2": {}, "tie": {}}
    for i, (name, stage) in enumerate(zip(route, D.PASSES, strict=False)):
        right = rights[i] if i < len(rights) else None
        out[stage][key] = verdict(key, name, right)
    return out


def checks(key: str = "phase3:k1", **failed: bool) -> dict[str, dict[str, Q.VerdictCheck]]:
    return {p: {key: FAILED if failed.get(p) else OK} for p in D.PASSES}


def decide_one(route: tuple[str, ...], **kw: Any) -> dict[str, Any]:
    r = kw.pop("the_row", row())
    v = verdicts(r["change_key"], *route, rights=kw.pop("rights", ()))
    D.validate([r], v)
    return D.decide_row(r, v, checks(r["change_key"], **kw))


# ------------------------------------------------------------------------------ the rule
def test_a_counted_pass_1_keep_stands() -> None:
    got = decide_one(("keep",))
    assert got["decision"] == "keep"
    assert got["basis"] == [{"pass": "p1", "verdict": "keep", "counted": True}]
    assert got["rejudge"] == []


@pytest.mark.parametrize("first", ["revert", "wrong-both", "undecidable"])
@pytest.mark.parametrize("second", ["revert", "wrong-both", "undecidable"])
def test_two_passes_that_are_not_keep_revert_the_row(first: str, second: str) -> None:
    got = decide_one((first, second), rights=("Settlement",) * 2)
    assert got["decision"] == "revert"
    assert [b["pass"] for b in got["basis"]] == ["p1", "p2"]


@pytest.mark.parametrize(
    ("third", "decision"), [("keep", "keep"), ("revert", "revert"), ("wrong-both", "revert")]
)
def test_a_pass_2_keep_goes_to_the_third_judge_who_decides(third: str, decision: str) -> None:
    got = decide_one(("revert", "keep", third), rights=(None, None, "Settlement"))
    assert got["decision"] == decision
    assert [b["pass"] for b in got["basis"]] == ["p1", "p2", "tie"]


@pytest.mark.parametrize(
    ("route", "failed", "rejudge", "route_decision"),
    [
        (("keep",), {"p1": True}, ["p1"], "keep"),
        (("revert", "revert"), {"p2": True}, ["p2"], "revert"),
        (("revert", "revert"), {"p1": True}, ["p1"], "revert"),
        (("revert", "wrong-both"), {"p1": True, "p2": True}, ["p1", "p2"], "revert"),
        (("revert", "keep", "revert"), {"tie": True}, ["tie"], "revert"),
        (("revert", "keep", "keep"), {"p2": True}, ["p2"], "keep"),
    ],
)
def test_a_deciding_verdict_that_fails_its_quote_check_sends_the_row_back(
    route: tuple[str, ...], failed: dict[str, bool], rejudge: list[str], route_decision: str
) -> None:
    got = decide_one(route, rights=("Settlement",) * 3, **failed)
    assert got["decision"] == "rejudge"
    assert got["rejudge"] == rejudge
    assert got["route_decision"] == route_decision
    assert got["proposed_value"] is None


def test_a_failed_verdict_off_the_rows_route_changes_nothing() -> None:
    """The route decides which verdicts count: a p1 keep has no p2 to fail."""
    r = row()
    v = verdicts("phase3:k1", "keep")
    got = D.decide_row(r, v, {"p1": {"phase3:k1": OK}, "p2": {}, "tie": {}})
    assert got["decision"] == "keep"


def test_every_decision_line_carries_the_row_and_its_quote_check() -> None:
    got = decide_one(("revert", "revert"), p2=True)
    for field in ("change_key", "site_name", "column", "old_value", "written_value"):
        assert got[field] == row()[field]
    assert got["current_value"] == "Archaeological site" and got["superseded"] is False
    assert got["quote_check"]["p1"] == {
        "counted": True,
        "reason": "",
        "quotes": [{"source": EVIDENCE, "outcome": Q.FOUND, "detail": "as served"}],
    }
    assert got["quote_check"]["p2"]["counted"] is False
    assert got["quote_check"]["p2"]["reason"] == Q.NOT_FOUND
    assert "tie" not in got["quote_check"]


# ------------------------------------------------------------------------------ rules 5 and 6
def test_a_superseded_row_is_decided_but_never_goes_to_the_reversal() -> None:
    superseded = row("phase3:k2", superseded=True, current_value="Settlement")
    live = row("phase3:k1")
    v = {
        p: {
            **verdicts("phase3:k1", "revert", "revert")[p],
            **verdicts("phase3:k2", "revert", "revert")[p],
        }
        for p in D.PASSES
    }
    both = {p: {"phase3:k1": OK, "phase3:k2": OK} for p in D.PASSES}
    D.validate([live, superseded], v)
    decisions = D.decide([live, superseded], v, both)
    assert [d["decision"] for d in decisions] == ["revert", "revert"]
    assert [d["reversal"] for d in decisions] == [True, False]
    assert [r["change_key"] for r in D.reversal_input(decisions, v)] == ["phase3:k1"]


def test_a_wrong_both_proposal_is_carried_and_never_the_value_to_write() -> None:
    got = decide_one(("wrong-both", "revert"), rights=("Settlement", "City/town/settlement"))
    assert got["decision"] == "revert"
    assert got["proposed_value"] == "Settlement"
    assert got["proposals"] == [{"pass": "p1", "value": "Settlement"}]
    (line,) = D.reversal_input([got], verdicts("phase3:k1", "wrong-both", "revert"))
    assert line["old_value"] == "City/town/settlement"  # the value restored is the old one
    assert "Settlement" not in (line["old_value"], line["new_value"])


def test_two_judges_proposing_different_values_propose_none() -> None:
    got = decide_one(("wrong-both", "wrong-both"), rights=("Settlement", "Hillfort"))
    assert got["decision"] == "revert"
    assert got["proposed_value"] is None
    assert got["proposals"] == [
        {"pass": "p1", "value": "Settlement"},
        {"pass": "p2", "value": "Hillfort"},
    ]


def test_a_proposal_the_third_judge_overruled_is_not_proposed() -> None:
    got = decide_one(("wrong-both", "keep", "keep"), rights=("Settlement",))
    assert got["decision"] == "keep"
    assert got["proposed_value"] is None


def test_a_keep_decision_has_nothing_to_propose_and_nothing_to_reverse() -> None:
    got = decide_one(("keep",))
    assert got["proposed_value"] is None and got["proposals"] == []
    assert got["reversal"] is False


# ------------------------------------------------------------------------------ the input's shape
def test_a_verdict_off_the_route_is_refused() -> None:
    v = verdicts("phase3:k1", "keep")
    v["p2"]["phase3:k1"] = verdict("phase3:k1", "revert")
    with pytest.raises(D.AuditError, match="p2"):
        D.validate([row()], v)


def test_a_row_without_the_second_verdict_its_route_needs_is_refused() -> None:
    with pytest.raises(D.AuditError, match="p2"):
        D.validate([row()], verdicts("phase3:k1", "revert"))


def test_a_pass_2_keep_without_its_third_verdict_is_refused() -> None:
    with pytest.raises(D.AuditError, match="tie"):
        D.validate([row()], verdicts("phase3:k1", "revert", "keep"))


def test_a_third_judge_that_is_undecidable_is_refused() -> None:
    """RULES.md rule 3: the third judge decides keep or revert."""
    with pytest.raises(D.AuditError, match="undecidable"):
        D.validate([row()], verdicts("phase3:k1", "revert", "keep", "undecidable"))


def test_a_verdict_name_the_rules_do_not_know_is_refused() -> None:
    with pytest.raises(D.AuditError, match="maybe"):
        D.validate([row()], verdicts("phase3:k1", "maybe"))


def test_a_verdict_filed_under_another_key_is_refused() -> None:
    v = verdicts("phase3:k1", "keep")
    v["p1"]["phase3:k1"]["change_key"] = "phase3:k9"
    with pytest.raises(D.AuditError, match="k9"):
        D.validate([row()], v)


def test_a_pass_1_that_does_not_cover_the_input_is_refused() -> None:
    with pytest.raises(D.AuditError, match="k2"):
        D.validate([row(), row("phase3:k2")], verdicts("phase3:k1", "keep"))


def test_a_wrong_both_without_its_value_is_refused() -> None:
    with pytest.raises(D.AuditError, match="right_value"):
        D.validate([row()], verdicts("phase3:k1", "wrong-both", "revert"))


# ------------------------------------------------------------------------------ the lists
def test_the_rejudge_list_groups_the_failed_verdicts_by_pass() -> None:
    decisions = [
        decide_one(("keep",), the_row=row("phase3:a"), p1=True),
        decide_one(("revert", "revert"), the_row=row("phase3:b"), p1=True, p2=True),
        decide_one(("revert", "keep", "keep"), the_row=row("phase3:c"), tie=True),
        decide_one(("revert", "revert"), the_row=row("phase3:d")),
    ]
    got = D.rejudge(decisions)
    assert {p: got[p] for p in D.PASSES} == {
        "p1": ["phase3:a", "phase3:b"],
        "p2": ["phase3:b"],
        "tie": ["phase3:c"],
    }


def test_the_keep_sample_is_random_20260923_over_the_sorted_pass_1_keeps() -> None:
    keys = [f"phase3:{i:03d}" for i in range(150)]
    shuffled = keys[::-1]
    v: dict[str, dict[str, Any]] = {"p1": {}, "p2": {}, "tie": {}}
    for i, key in enumerate(shuffled):
        v["p1"][key] = verdict(key, "keep" if i % 3 else "revert")
    keeps = sorted(k for k, x in v["p1"].items() if x["verdict"] == "keep")
    got = D.keep_sample(v)
    assert got["seed"] == 20260923 and got["size"] == 60
    assert got["population"] == len(keeps) == 100
    assert got["keys"] == random.Random(20260923).sample(keeps, 60)  # noqa: S311 - a seeded draw
    assert set(got["keys"]) <= set(keeps)
    assert "random.Random(20260923).sample" in got["method"]


def test_the_reversal_input_restores_the_old_value_on_the_counted_quotes() -> None:
    r = row(column="period_start", old_value="-4500", written_value="-1000", current_value="-1000")
    v = verdicts("phase3:k1", "revert", "keep", "revert")
    decisions = D.decide([r], v, checks())
    (line,) = D.reversal_input(decisions, v)
    assert line["journal_id"] is None  # resolved read-only by change_key before the lane runs
    assert line["change_key"] == "phase3:k1" and line["site_id"] == r["site_id"]
    assert (line["column"], line["old_value"], line["new_value"]) == (
        "period_start",
        "-4500",
        "-1000",
    )
    # the quotes are the counted ones of the verdicts that decided to revert: p1 and the tie
    assert line["quotes"] == [{"source": EVIDENCE, "text": "q"}, {"source": EVIDENCE, "text": "q"}]
    assert [j["pass"] for j in line["judges"]] == ["p1", "p2", "tie"]
    assert line["period_bucket"] == {
        "restored": categorize_period(-4500),
        "written": categorize_period(-1000),
        "changes": categorize_period(-4500) != categorize_period(-1000),
    }


def test_a_rejudge_or_keep_row_is_not_in_the_reversal_input() -> None:
    decisions = [
        decide_one(("revert", "revert"), the_row=row("phase3:a"), p2=True),
        decide_one(("keep",), the_row=row("phase3:b")),
    ]
    assert D.reversal_input(decisions, {"p1": {}, "p2": {}, "tie": {}}) == []


# ------------------------------------------------------------------------------ the counts
def test_the_counts_split_the_reverts_by_column_and_by_superseded() -> None:
    rows = [
        row("phase3:a"),
        row("phase3:b", column="period_start", superseded=True),
        row("phase3:c"),
        row("phase3:d"),
    ]
    routes = {
        "phase3:a": ("revert", "revert"),
        "phase3:b": ("wrong-both", "revert"),
        "phase3:c": ("keep",),
        "phase3:d": ("keep",),
    }
    v: dict[str, dict[str, Any]] = {"p1": {}, "p2": {}, "tie": {}}
    for key, route in routes.items():
        for p, x in verdicts(key, *route, rights=("Settlement",)).items():
            v[p].update(x)
    c = {p: dict.fromkeys(v[p], OK) for p in D.PASSES}
    c["p1"]["phase3:d"] = FAILED
    decisions = D.decide(rows, v, c)
    got = D.counts(v, c, decisions)
    assert got["decisions"] == {"keep": 1, "revert": 2, "rejudge": 1}
    assert got["revert_by_column"] == {"period_start": 1, "site_type": 1}
    assert got["revert_by_superseded"] == {"false": 1, "true": 1}
    assert got["wrong_both_proposals"] == 1
    assert got["reversal_rows"] == 1
    assert got["rejudge_by_pass"] == {"p1": 1, "p2": 0, "tie": 0}
    assert got["quote_check"]["p1"] == {
        "checked": 4,
        "counted": 3,
        "failed": 1,
        "failed_by_reason": {Q.NOT_FOUND: 1},
    }


# ------------------------------------------------------------------------------ the seal
def test_a_rules_file_that_moved_after_its_seal_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "RULES.md"
    path.write_bytes(b"# rules\n")
    with pytest.raises(D.AuditError, match="sealed"):
        D.sealed(path, "0" * 64)


def test_the_real_rules_and_input_keep_the_digests_sealed_before_the_first_verdict() -> None:
    audit = REPO / "output" / "remediation" / "opus_audit"
    assert D.sealed(audit / "RULES.md", D.RULES_SHA256) == D.RULES_SHA256
    assert D.sealed(audit / "INPUT.jsonl", D.INPUT_SHA256) == D.INPUT_SHA256


# ------------------------------------------------------------------------------ the whole run
def test_the_run_writes_every_output_and_writes_it_the_same_twice(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    audit.mkdir()
    (tmp_path / EVIDENCE).parent.mkdir(parents=True)
    (tmp_path / EVIDENCE).write_text('{"extract":"an antigua llacta inca"}', encoding="utf-8")
    rows = [row("phase3:a"), row("phase3:b"), row("phase3:c")]
    (audit / "RULES.md").write_bytes(b"rules\n")
    (audit / "INPUT.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    raw = {"p1": {}, "p2": {}, "tie": {}}
    raw["p1"]["phase3:a"] = verdict("phase3:a", "keep", quote="antigua llacta")
    raw["p1"]["phase3:b"] = verdict("phase3:b", "revert", quote="llacta inca")
    raw["p2"]["phase3:b"] = verdict("phase3:b", "revert", quote="an antigua")
    raw["p1"]["phase3:c"] = verdict("phase3:c", "keep", quote="a paraphrase")
    (audit / "VERDICTS_RAW.json").write_text(json.dumps(raw), encoding="utf-8")
    seal = {
        "rules_sha256": D.sha256_file(audit / "RULES.md"),
        "input_sha256": D.sha256_file(audit / "INPUT.jsonl"),
    }
    first = D.run(audit, repo=tmp_path, **seal)
    outputs = ["DECISIONS.jsonl", "COUNTS.json", "REJUDGE.json", "REVERSAL_3_INPUT.jsonl"]
    before = {name: (audit / name).read_bytes() for name in outputs}
    second = D.run(audit, repo=tmp_path, **seal)
    assert first == second
    assert {name: (audit / name).read_bytes() for name in outputs} == before
    decisions = [json.loads(x) for x in before["DECISIONS.jsonl"].decode().splitlines()]
    assert [d["decision"] for d in decisions] == ["keep", "revert", "rejudge"]
    assert json.loads(before["REJUDGE.json"])["p1"] == ["phase3:c"]
    reversal = before["REVERSAL_3_INPUT.jsonl"].decode().splitlines()
    assert [json.loads(x)["change_key"] for x in reversal] == ["phase3:b"]
    assert first["inputs"]["VERDICTS_RAW.json"] == D.sha256_file(audit / "VERDICTS_RAW.json")
    assert b"\r\n" not in b"".join(before.values())


def test_a_stated_keep_sample_is_never_drawn_again_differently(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    audit.mkdir()
    rows = [row(f"phase3:{i:03d}") for i in range(70)]
    (audit / "RULES.md").write_bytes(b"rules\n")
    (audit / "INPUT.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), "utf-8")
    raw = {
        "p1": {r["change_key"]: verdict(r["change_key"], "keep") for r in rows},
        "p2": {},
        "tie": {},
    }
    (audit / "VERDICTS_RAW.json").write_text(json.dumps(raw), encoding="utf-8")
    seal = {
        "rules_sha256": D.sha256_file(audit / "RULES.md"),
        "input_sha256": D.sha256_file(audit / "INPUT.jsonl"),
    }
    first = D.write_keep_sample(audit, **seal)
    assert D.write_keep_sample(audit, **seal) == first  # the same draw, restated, is accepted
    stated = json.loads((audit / "KEEP_SAMPLE.json").read_text(encoding="utf-8"))
    stated["keys"] = stated["keys"][::-1]
    (audit / "KEEP_SAMPLE.json").write_text(json.dumps(stated), encoding="utf-8")
    with pytest.raises(D.AuditError, match="another sample"):
        D.write_keep_sample(audit, **seal)


def test_the_run_refuses_inputs_that_are_not_the_sealed_ones(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    audit.mkdir()
    (audit / "RULES.md").write_bytes(b"rules, loosened\n")
    with pytest.raises(D.AuditError, match="sealed"):
        D.run(audit, repo=tmp_path, rules_sha256="0" * 64, input_sha256="0" * 64)
