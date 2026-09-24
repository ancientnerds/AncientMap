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
from opus_audit import run as R  # noqa: E402

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
        (("revert", "keep", "keep"), {"p2": True}, ["p2"], "keep"),
        # Ferrybridge Henge: the tie saw a pass 2 that does not count, so only pass 2 is judged again
        (("revert", "keep", "keep"), {"p2": True, "tie": True}, ["p2"], "keep"),
    ],
)
def test_a_deciding_verdict_that_fails_its_quote_check_sends_the_row_back(
    route: tuple[str, ...], failed: dict[str, bool], rejudge: list[str], route_decision: str
) -> None:
    got = decide_one(route, rights=("Settlement",) * 3, **failed)
    assert got["decision"] == "rejudge"
    assert got["rejudge"] == rejudge
    assert got["pending"] == []
    assert got["route_decision"] == route_decision
    assert got["proposed_value"] is None


def test_a_third_judge_that_failed_its_quote_check_leaves_the_row_waiting_on_a_tie() -> None:
    """The pair it judged still stands, so the row waits for a counted tie (TIE_ROUND2.json)."""
    got = decide_one(("revert", "keep", "revert"), tie=True)
    assert got["decision"] == "pending"
    assert got["pending"] == ["tie"] and got["rejudge"] == []
    assert got["route_decision"] == "revert"
    assert got["reversal"] is False


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
    # a failed tie is not judged again here: the row waits on a tie (TIE_ROUND2.json)
    assert {k: v for k, v in got.items() if k != "about"} == {
        "p1": ["phase3:a", "phase3:b"],
        "p2": ["phase3:b"],
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
    v["p2"]["phase3:k1"]["quotes"] = [{"source": EVIDENCE, "quote": "p2 keeps"}]
    v["tie"]["phase3:k1"]["quotes"] = [
        {"source": EVIDENCE, "quote": "q"},  # the same line p1 quoted: listed once
        {"source": EVIDENCE, "quote": "tie reverts"},
    ]
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
    assert line["quotes"] == [
        {"source": EVIDENCE, "text": "q"},
        {"source": EVIDENCE, "text": "tie reverts"},
    ]
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
    got = D.decision_counts(decisions)
    assert got["decisions"] == {"keep": 1, "revert": 2, "rejudge": 1, "pending": 0}
    assert got["revert_by_column"] == {"period_start": 1, "site_type": 1}
    assert got["revert_by_superseded"] == {"false": 1, "true": 1}
    assert got["wrong_both_proposals"] == 1
    assert got["reversal_rows"] == 1
    assert got["rejudge_by_pass"] == {"p1": 1, "p2": 0}
    assert got["pending_by_pass"] == {"p2": 0, "tie": 0}
    assert D.verdict_counts(v, c)["p1"] == {
        "verdicts": 4,
        "by_verdict": {"keep": 2, "revert": 1, "wrong-both": 1},
        "counted": 3,
        "failed": 1,
        "failed_by_reason": {Q.NOT_FOUND: 1},
        "quotes_by_outcome": {Q.FOUND: 3, Q.NOT_FOUND: 1},
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


# ------------------------------------------------------------------------------ rule 4, fired
def decide_fired(route: tuple[str, ...], **failed: bool) -> dict[str, Any]:
    """One row decided once rule 4 has fired, on the route verdicts `route` (p1, then p2, then tie)."""
    r = row()
    v = verdicts(r["change_key"], *route, rights=("Settlement",) * 3)
    return D.decide_row(r, v, checks(r["change_key"], **failed), second_judgement=True)


def test_once_rule_4_fires_a_pass_1_keep_waits_for_its_second_judgement() -> None:
    got = decide_fired(("keep",))
    assert got["decision"] == "pending"
    assert got["pending"] == ["p2"] and got["rejudge"] == []
    assert got["basis"] == [{"pass": "p1", "verdict": "keep", "counted": True}]
    assert got["route_decision"] is None
    assert got["reversal"] is False


def test_once_rule_4_fires_a_second_keep_keeps_the_row() -> None:
    got = decide_fired(("keep", "keep"))
    assert got["decision"] == "keep"
    assert [b["pass"] for b in got["basis"]] == ["p1", "p2"]
    assert got["pending"] == [] and got["rejudge"] == []


@pytest.mark.parametrize("second", ["revert", "wrong-both", "undecidable"])
def test_once_rule_4_fires_a_second_judge_who_does_not_keep_calls_the_third(second: str) -> None:
    """RULES.md rule 3 on a pass-1 keep: the two judges disagree, so a third judge decides."""
    got = decide_fired(("keep", second))
    assert got["decision"] == "pending"
    assert got["pending"] == ["tie"]
    assert got["route_decision"] is None


@pytest.mark.parametrize(
    ("third", "decision"), [("keep", "keep"), ("revert", "revert"), ("wrong-both", "revert")]
)
def test_once_rule_4_fires_the_third_judge_decides_a_split_keep(third: str, decision: str) -> None:
    got = decide_fired(("keep", "revert", third))
    assert got["decision"] == decision
    assert [b["pass"] for b in got["basis"]] == ["p1", "p2", "tie"]


def test_a_second_judgement_that_failed_its_quote_check_leaves_the_keep_waiting() -> None:
    """It does not count, so the keep still lacks its second judgement (SECOND_JUDGE.json)."""
    got = decide_fired(("keep", "revert"), p2=True)
    assert got["decision"] == "pending"
    assert got["pending"] == ["p2"] and got["rejudge"] == []


def test_before_rule_4_fires_a_pass_1_keep_stands_beside_a_second_verdict() -> None:
    r = row()
    got = D.decide_row(r, verdicts(r["change_key"], "keep", "revert"), checks())
    assert got["decision"] == "keep"
    assert [b["pass"] for b in got["basis"]] == ["p1"]


def test_a_failed_pass_1_is_judged_again_before_anything_waits_on_it() -> None:
    got = decide_fired(("keep",), p1=True)
    assert got["decision"] == "rejudge"
    assert got["rejudge"] == ["p1"] and got["pending"] == []


def sample_of(names: list[str], failed: frozenset[int] = frozenset()) -> tuple[dict, dict]:
    keys = [f"phase3:s{i:02d}" for i in range(len(names))]
    sample = {
        k: verdict(k, n, "Settlement" if n == "wrong-both" else None)
        for k, n in zip(keys, names, strict=True)
    }
    return sample, {k: FAILED if i in failed else OK for i, k in enumerate(keys)}


def test_rule_4_fires_when_more_than_3_of_the_60_are_not_keep() -> None:
    fired = D.rule_4(*sample_of(["keep"] * 56 + ["revert", "wrong-both", "undecidable", "revert"]))
    assert fired["fired"] is True
    assert [fired[k] for k in ("sample", "counted", "not_keep", "threshold")] == [60, 60, 4, 3]
    assert fired["by_verdict"] == {"keep": 56, "revert": 2, "undecidable": 1, "wrong-both": 1}
    held = D.rule_4(*sample_of(["keep"] * 57 + ["revert"] * 3))
    assert held["fired"] is False and held["not_keep"] == 3


def test_a_sample_verdict_that_failed_its_quote_check_is_not_counted_for_rule_4() -> None:
    got = D.rule_4(*sample_of(["keep"] * 55 + ["revert"] * 5, failed=frozenset({59})))
    assert (got["counted"], got["not_keep"], got["fired"]) == (59, 4, True)
    assert got["not_counted"] == ["phase3:s59"]


def test_rule_4_is_not_decided_while_a_failed_sample_verdict_could_tip_it() -> None:
    with pytest.raises(D.AuditError, match="rule 4"):
        D.rule_4(*sample_of(["keep"] * 56 + ["revert"] * 4, failed=frozenset({59})))


# ------------------------------------------------------------------------------ round 2
def merged(routes: dict[str, tuple[str, ...]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {"p1": {}, "p2": {}, "tie": {}}
    for key, route in routes.items():
        rights = tuple("Settlement" if n == "wrong-both" else None for n in route)
        for p, x in verdicts(key, *route, rights=rights).items():
            out[p].update(x)
    return out


def checked(v: dict[str, dict[str, Any]], **failed: set[str]) -> dict:
    """Every verdict of `v` counted, except the keys `failed` names under their section."""
    return {s: {k: FAILED if k in failed.get(s, ()) else OK for k in v[s]} for s in v}


def round_2(**sections: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {"sample": {}, "p1": {}, "p2": {}, **sections}


def anew(key: str, name: str) -> dict[str, Any]:
    """A round-2 verdict: another judge, so another reasoning than round 1's."""
    return verdict(key, name, "Settlement" if name == "wrong-both" else None, quote="round 2")


def test_a_counted_round_2_verdict_replaces_the_failed_round_1_verdict_of_its_pass() -> None:
    raw = merged({"phase3:a": ("revert", "revert")})
    r2 = round_2(p1={"phase3:a": anew("phase3:a", "keep")})
    ov = D.overlay(raw, checked(raw, p1={"phase3:a"}), r2, checked(r2))
    assert ov.verdicts["p1"]["phase3:a"] == anew("phase3:a", "keep")
    assert ov.checks["p1"]["phase3:a"].counted is True
    assert ov.origin["p1"]["phase3:a"] == "VERDICTS_ROUND2.json p1"
    assert ov.origin["p2"]["phase3:a"] == "VERDICTS_RAW.json p2"
    assert ov.set_aside["phase3:a"] == [
        {
            "from": "VERDICTS_RAW.json p1",
            "verdict": "revert",
            "counted": False,
            "reason": Q.NOT_FOUND,
            "why": D.REPLACED,
        }
    ]


def test_a_round_2_verdict_that_fails_its_quote_check_replaces_nothing() -> None:
    raw = merged({"phase3:a": ("revert", "revert")})
    r2 = round_2(p2={"phase3:a": anew("phase3:a", "keep")})
    ov = D.overlay(raw, checked(raw, p2={"phase3:a"}), r2, checked(r2, p2={"phase3:a"}))
    assert ov.verdicts["p2"]["phase3:a"] == raw["p2"]["phase3:a"]
    assert ov.checks["p2"]["phase3:a"].counted is False
    assert [(x["from"], x["why"]) for x in ov.set_aside["phase3:a"]] == [
        ("VERDICTS_ROUND2.json p2", D.NOT_COUNTED)
    ]
    got = D.decide_row(row("phase3:a"), ov.verdicts, ov.checks, second_judgement=True)
    assert got["decision"] == "rejudge" and got["rejudge"] == ["p2"]


def test_a_round_2_verdict_over_a_counted_round_1_verdict_is_refused() -> None:
    """A counted verdict is never judged again: a second opinion must not be shopped for."""
    raw = merged({"phase3:a": ("revert", "revert")})
    r2 = round_2(p1={"phase3:a": anew("phase3:a", "keep")})
    with pytest.raises(D.AuditError, match="counted"):
        D.overlay(raw, checked(raw), r2, checked(r2))


def test_a_counted_sample_verdict_is_its_keep_rows_second_judgement() -> None:
    raw = merged({"phase3:a": ("keep",), "phase3:b": ("keep",)})
    r2 = round_2(
        sample={"phase3:a": anew("phase3:a", "revert"), "phase3:b": anew("phase3:b", "keep")}
    )
    ov = D.overlay(raw, checked(raw), r2, checked(r2, sample={"phase3:b"}))
    assert ov.verdicts["p2"]["phase3:a"] == anew("phase3:a", "revert")
    assert ov.origin["p2"]["phase3:a"] == "VERDICTS_ROUND2.json sample"
    # a sample verdict that does not count is no second judgement
    assert "phase3:b" not in ov.verdicts["p2"]
    assert [(x["from"], x["why"]) for x in ov.set_aside["phase3:b"]] == [
        ("VERDICTS_ROUND2.json sample", D.NOT_COUNTED)
    ]
    decisions = D.decide(
        [row("phase3:a"), row("phase3:b")], ov.verdicts, ov.checks, second_judgement=True
    )
    assert [d["pending"] for d in decisions] == [["tie"], ["p2"]]


def test_a_round_1_tie_stands_only_while_the_pair_it_was_shown_is_unchanged() -> None:
    raw = merged({"phase3:a": ("revert", "keep", "keep"), "phase3:b": ("revert", "keep", "keep")})
    # a: pass 2 failed and a counted round-2 pass 2 replaces it; b: only the tie failed
    raw_checks = checked(raw, p2={"phase3:a"}, tie={"phase3:a", "phase3:b"})
    r2 = round_2(p2={"phase3:a": anew("phase3:a", "keep")})
    ov = D.overlay(raw, raw_checks, r2, checked(r2))
    assert "phase3:a" not in ov.verdicts["tie"] and "phase3:a" not in ov.checks["tie"]
    assert ov.set_aside["phase3:a"][-1] == {
        "from": "VERDICTS_RAW.json tie",
        "verdict": "keep",
        "counted": False,
        "reason": Q.NOT_FOUND,
        "why": D.STALE_TIE,
    }
    assert ov.verdicts["tie"]["phase3:b"] == raw["tie"]["phase3:b"]
    decisions = D.decide(
        [row("phase3:a"), row("phase3:b")], ov.verdicts, ov.checks, second_judgement=True
    )
    assert [(d["decision"], d["pending"]) for d in decisions] == [
        ("pending", ["tie"]),
        ("pending", ["tie"]),
    ]


def test_a_counted_round_1_tie_goes_stale_when_a_new_pass_1_changes_its_pair() -> None:
    raw = merged({"phase3:a": ("revert", "keep", "revert")})
    r2 = round_2(p1={"phase3:a": anew("phase3:a", "undecidable")})
    ov = D.overlay(raw, checked(raw, p1={"phase3:a"}), r2, checked(r2))
    assert "phase3:a" not in ov.verdicts["tie"]
    (got,) = D.decide([row("phase3:a")], ov.verdicts, ov.checks, second_judgement=True)
    assert got["decision"] == "pending" and got["pending"] == ["tie"]


def test_a_new_pass_2_that_agrees_with_pass_1_ends_the_route_without_a_tie() -> None:
    raw = merged({"phase3:a": ("revert", "keep", "keep")})
    r2 = round_2(p2={"phase3:a": anew("phase3:a", "revert")})
    ov = D.overlay(raw, checked(raw, p2={"phase3:a"}, tie={"phase3:a"}), r2, checked(r2))
    (got,) = D.decide([row("phase3:a")], ov.verdicts, ov.checks, second_judgement=True)
    assert got["decision"] == "revert"
    assert [b["pass"] for b in got["basis"]] == ["p1", "p2"]


def test_the_trace_names_where_each_verdict_came_from_and_what_was_set_aside() -> None:
    raw = merged({"phase3:a": ("revert", "revert"), "phase3:b": ("keep",)})
    r2 = round_2(
        p1={"phase3:a": anew("phase3:a", "revert")}, sample={"phase3:b": anew("phase3:b", "keep")}
    )
    ov = D.overlay(raw, checked(raw, p1={"phase3:a"}), r2, checked(r2))
    decisions = D.trace(D.decide([row("phase3:a"), row("phase3:b")], ov.verdicts, ov.checks), ov)
    assert [b["from"] for b in decisions[0]["basis"]] == [
        "VERDICTS_ROUND2.json p1",
        "VERDICTS_RAW.json p2",
    ]
    assert decisions[0]["set_aside"] == ov.set_aside["phase3:a"]
    assert decisions[1]["set_aside"] == []


def test_the_round_2_file_must_judge_exactly_the_stated_sample(tmp_path: Path) -> None:
    raw = merged({"phase3:a": ("keep",), "phase3:b": ("keep",)})
    path = tmp_path / "VERDICTS_ROUND2.json"
    path.write_text(json.dumps(round_2(sample={"phase3:a": anew("phase3:a", "keep")})), "utf-8")
    assert D.read_round_2(path, raw, ["phase3:a"])["sample"]["phase3:a"]["verdict"] == "keep"
    with pytest.raises(D.AuditError, match="sample"):
        D.read_round_2(path, raw, ["phase3:a", "phase3:b"])


def test_a_round_2_verdict_for_a_pass_round_1_never_gave_is_refused(tmp_path: Path) -> None:
    raw = merged({"phase3:a": ("keep",)})
    path = tmp_path / "VERDICTS_ROUND2.json"
    path.write_text(json.dumps(round_2(p2={"phase3:a": anew("phase3:a", "revert")})), "utf-8")
    with pytest.raises(D.AuditError, match="p2"):
        D.read_round_2(path, raw, [])


def test_a_round_2_verdict_is_held_to_the_shape_of_round_1(tmp_path: Path) -> None:
    raw = merged({"phase3:a": ("revert", "revert")})
    path = tmp_path / "VERDICTS_ROUND2.json"
    path.write_text(json.dumps(round_2(p1={"phase3:a": verdict("phase3:a", "maybe")})), "utf-8")
    with pytest.raises(D.AuditError, match="maybe"):
        D.read_round_2(path, raw, [])


# ------------------------------------------------------------------------------ the lists
def test_second_judge_lists_every_pass_1_keep_without_a_counted_second_judgement() -> None:
    v = merged(
        {
            "phase3:a": ("keep",),
            "phase3:b": ("keep", "keep"),
            "phase3:c": ("keep", "keep"),
            "phase3:d": ("revert", "revert"),
            "phase3:e": ("keep", "revert"),  # counted, and split: it waits on a tie instead
        }
    )
    rows = [row(k) for k in ("phase3:a", "phase3:b", "phase3:c", "phase3:d", "phase3:e")]
    decisions = D.decide(rows, v, checked(v, p2={"phase3:c"}), second_judgement=True)
    stated = {"fired": True, "not_keep": 9, "sample": 60}
    got = D.second_judge(decisions, stated)
    assert got["keys"] == ["phase3:a", "phase3:c"] and got["count"] == 2
    assert got["rule_4"] == stated


def test_tie_round_2_embeds_both_judgements_of_every_split_pair_without_a_counted_tie() -> None:
    v = merged(
        {
            "phase3:a": ("keep", "wrong-both"),
            "phase3:b": ("revert", "keep", "keep"),
            "phase3:c": ("revert", "keep", "revert"),
            "phase3:d": ("keep", "keep"),
            "phase3:e": ("keep",),  # waits on its second judgement, not on a tie
        }
    )
    rows = [row(k) for k in ("phase3:a", "phase3:b", "phase3:c", "phase3:d", "phase3:e")]
    decisions = D.decide(rows, v, checked(v, tie={"phase3:b"}), second_judgement=True)
    got = D.tie_round_2(decisions, v)
    assert got["count"] == 2
    assert [r["change_key"] for r in got["rows"]] == ["phase3:a", "phase3:b"]
    first = got["rows"][0]
    assert set(first) == {"change_key", "judge_1", "judge_2"}
    assert first["judge_1"] == {
        "verdict": "keep",
        "right_value": None,
        "reason": "keep because",
        "quotes": [{"source": EVIDENCE, "quote": "q"}],
    }
    assert first["judge_2"]["verdict"] == "wrong-both"
    assert first["judge_2"]["right_value"] == "Settlement"


def test_no_pending_row_reaches_the_reversal_input() -> None:
    v = merged(
        {"phase3:a": ("keep", "revert"), "phase3:b": ("keep",), "phase3:c": ("revert", "revert")}
    )
    rows = [row(k) for k in ("phase3:a", "phase3:b", "phase3:c")]
    decisions = D.decide(rows, v, checked(v), second_judgement=True)
    assert [d["decision"] for d in decisions] == ["pending", "pending", "revert"]
    assert [x["change_key"] for x in D.reversal_input(decisions, v)] == ["phase3:c"]
    counted = D.decision_counts(decisions)
    assert counted["decisions"] == {"keep": 0, "revert": 1, "rejudge": 0, "pending": 2}
    assert counted["pending_by_pass"] == {"p2": 1, "tie": 1}
    assert counted["reversal_rows"] == 1


# ------------------------------------------------------------------------------ the whole run
def write_audit(tmp_path: Path, rows: list[dict[str, Any]], raw: dict) -> tuple[Path, dict]:
    audit = tmp_path / "audit"
    audit.mkdir()
    (tmp_path / EVIDENCE).parent.mkdir(parents=True)
    (tmp_path / EVIDENCE).write_text('{"extract":"an antigua llacta inca"}', encoding="utf-8")
    (audit / "RULES.md").write_bytes(b"rules\n")
    (audit / "INPUT.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    (audit / "VERDICTS_RAW.json").write_text(json.dumps(raw), encoding="utf-8")
    return audit, {
        "rules_sha256": D.sha256_file(audit / "RULES.md"),
        "input_sha256": D.sha256_file(audit / "INPUT.jsonl"),
    }


KEEPS = [f"phase3:k{i:02d}" for i in range(62)]


def round_2_audit(tmp_path: Path) -> tuple[Path, dict, list[str]]:
    """62 pass-1 keeps (60 of them the sample, 4 of those judged revert) and four other rows."""
    rows = [row(k) for k in [*KEEPS, "phase3:r1", "phase3:r2", "phase3:f1", "phase3:t1"]]
    raw: dict[str, dict[str, Any]] = {"p1": {}, "p2": {}, "tie": {}}
    for key in KEEPS:
        raw["p1"][key] = verdict(key, "keep", quote="antigua llacta")
    raw["p1"]["phase3:r1"] = verdict("phase3:r1", "revert", quote="llacta inca")
    raw["p2"]["phase3:r1"] = verdict("phase3:r1", "revert", quote="an antigua")
    raw["p1"]["phase3:r2"] = verdict("phase3:r2", "revert", quote="a paraphrase")
    raw["p2"]["phase3:r2"] = verdict("phase3:r2", "revert", quote="an antigua")
    raw["p1"]["phase3:f1"] = verdict("phase3:f1", "revert", quote="a paraphrase")
    raw["p2"]["phase3:f1"] = verdict("phase3:f1", "revert", quote="an antigua")
    raw["p1"]["phase3:t1"] = verdict("phase3:t1", "revert", quote="llacta inca")
    raw["p2"]["phase3:t1"] = verdict("phase3:t1", "keep", quote="an antigua")
    raw["tie"]["phase3:t1"] = verdict("phase3:t1", "keep", quote="a paraphrase")
    audit, seal = write_audit(tmp_path, rows, raw)
    sample = D.write_keep_sample(audit, **seal)["keys"]
    r2 = round_2(
        sample={
            k: verdict(k, "revert" if k in sample[:4] else "keep", quote="llacta") for k in sample
        },
        p1={
            "phase3:r2": verdict("phase3:r2", "keep", quote="antigua"),
            "phase3:f1": verdict("phase3:f1", "revert", quote="still a paraphrase"),
        },
    )
    (audit / "VERDICTS_ROUND2.json").write_text(json.dumps(r2), encoding="utf-8")
    return audit, seal, sample


def test_the_run_applies_round_2_and_writes_every_output_the_same_twice(tmp_path: Path) -> None:
    audit, seal, sample = round_2_audit(tmp_path)
    first = D.run(audit, repo=tmp_path, **seal)
    before = {name: (audit / name).read_bytes() for name in D.OUTPUTS}
    second = D.run(audit, repo=tmp_path, **seal)
    assert first == second
    assert {name: (audit / name).read_bytes() for name in D.OUTPUTS} == before
    assert b"\r\n" not in b"".join(before.values())
    assert first["rule_4"]["fired"] is True and first["rule_4"]["not_keep"] == 4
    # 56 sample keeps kept; the 4 split sample rows, r2 (a new pass-1 keep beside a revert) and t1
    # (its tie failed) wait on a tie; the 2 unsampled keeps wait on a second judgement
    assert first["decisions"] == {"keep": 56, "revert": 1, "rejudge": 1, "pending": 8}
    lines = [json.loads(x) for x in before["DECISIONS.jsonl"].decode().splitlines()]
    decided = {d["change_key"]: d for d in lines}
    assert decided["phase3:f1"]["rejudge"] == ["p1"]
    assert decided["phase3:r2"]["pending"] == ["tie"]
    assert decided["phase3:r2"]["basis"][0]["from"] == "VERDICTS_ROUND2.json p1"
    assert decided[sample[-1]]["basis"][1]["from"] == "VERDICTS_ROUND2.json sample"
    assert json.loads(before["SECOND_JUDGE.json"])["keys"] == sorted(set(KEEPS) - set(sample))
    ties = json.loads(before["TIE_ROUND2.json"])["rows"]
    assert [t["change_key"] for t in ties] == sorted([*sample[:4], "phase3:r2", "phase3:t1"])
    assert json.loads(before["REJUDGE.json"])["p1"] == ["phase3:f1"]
    reversal = before["REVERSAL_3_INPUT.jsonl"].decode().splitlines()
    assert [json.loads(x)["change_key"] for x in reversal] == ["phase3:r1"]
    assert first["inputs"]["VERDICTS_ROUND2.json"] == D.sha256_file(audit / "VERDICTS_ROUND2.json")
    assert first["inputs"]["KEEP_SAMPLE.json"] == D.sha256_file(audit / "KEEP_SAMPLE.json")
    assert first["round_2"]["p1"]["failed"] == 1
    assert first["overlay"]["replaced"] == {"p1": 1, "p2": 0}


def test_the_run_refuses_a_keep_sample_that_is_not_the_draw_from_these_verdicts(
    tmp_path: Path,
) -> None:
    audit, seal, _sample = round_2_audit(tmp_path)
    stated = json.loads((audit / "KEEP_SAMPLE.json").read_text(encoding="utf-8"))
    stated["keys"] = stated["keys"][::-1]
    (audit / "KEEP_SAMPLE.json").write_text(json.dumps(stated), encoding="utf-8")
    with pytest.raises(D.AuditError, match="KEEP_SAMPLE"):
        D.run(audit, repo=tmp_path, **seal)


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


def test_the_fetch_collects_the_urls_only_round_2_cites() -> None:
    raw = merged({"phase3:a": ("keep",)})
    raw["p1"]["phase3:a"]["quotes"].append({"source": "https://a.example/one", "quote": "x"})
    cited = [{"source": "https://b.example/two", "quote": "y"}, {"source": EVIDENCE, "quote": "z"}]
    r2 = round_2(sample={"phase3:a": {**anew("phase3:a", "keep"), "quotes": cited}})
    assert R.cited_urls(raw, r2) == ["https://a.example/one", "https://b.example/two"]
