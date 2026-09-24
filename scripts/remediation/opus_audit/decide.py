"""The decision rule of the Opus re-verification, over the verdicts that pass the quote check.

`output/remediation/opus_audit/RULES.md`, "Decision rule", sealed before the first verdict (its
sha256 and INPUT.jsonl's are `RULES_SHA256` and `INPUT_SHA256`; a run on other bytes is refused).

**The route** of a row (`route`) is the verdicts the rule reads, in order. Pass 1 first; any pass-1
verdict other than `keep` goes to pass 2 (rule 2); both not `keep` revert the row; a pass-2 `keep`
goes to the third judge, whose `keep` keeps and whose `revert` or `wrong-both` reverts (rule 3 - a
`wrong-both` says the written value is wrong, so it cannot keep it). A pass-1 `keep` stands alone
(rule 4) - until rule 4 fires (`rule_4`): then every pass-1 `keep` needs a second, independent
judgement under rule 3 (`second_judgement`), which keeps the row when it is `keep` too and otherwise
calls the third judge, the same as two passes that disagree the other way round.

**Only counting verdicts decide** (`quotes.check_verdict`). A row waits, and never reaches the
reversal, while its route lacks a counted verdict: `rejudge` when pass 1 failed the quote check, or
the pass 2 of a pass-1 verdict that is not `keep` did (REJUDGE.json, by pass); `pending` when it
waits for rule 4's second judgement of a pass-1 `keep` (SECOND_JUDGE.json) or for a third judge
(TIE_ROUND2.json) - not given yet, or given and failed. `route_decision` records what the verdicts
on a complete route would have decided, for the reader and nothing else.

**Round 2** (`VERDICTS_ROUND2.json`, `read_round_2` and `overlay`): the 60 keys of rule 4's sample
judged again independently, and the failed p1 and p2 verdicts of round 1 judged anew. Each is
quote-checked exactly like round 1; one that fails does not count and replaces nothing. A counted
round-2 p1 or p2 verdict replaces the failed round-1 verdict of its pass (a counted verdict is never
judged again). A counted sample verdict never saw pass 1, so it is its pass-1 keep's second judgement
and stands as the row's p2. A round-1 tie counts only while the p1 and p2 on the row's route are
the very verdicts it was shown (`PAIR_RULE`); otherwise it is set aside as stale.

**Rule 5**: the `right_value` of the route's `wrong-both` verdicts is carried as `proposals`, and as
`proposed_value` when the row is reverted and every such verdict names one value. It is never
written: the reversal restores the old value. **Rule 6**: a `superseded` row is decided like any
other, and never goes to the reversal (`reversal` is false).

**Rule 4's sample** (`keep_sample`): `random.Random(20260923).sample` of 60 over the pass-1 `keep`
change keys sorted ascending, stated in AUDIT_LOG.md before any judge sees it.

**The reversal input** (`reversal_input`) is one line per row decided `revert` and not superseded, in
the shape of the journal-reversal lane's `REASONS.json` entries (`mechanical/reversal.py`), with
`journal_id` left null: the journal row is found read-only by its `change_key` before a lane reads it.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opus_audit import quotes as Q
from pipeline.utils.text import categorize_period

AuditError = Q.AuditError

PASSES = ("p1", "p2", "tie")
KEEP, REVERT, WRONG_BOTH, UNDECIDABLE = "keep", "revert", "wrong-both", "undecidable"
REJUDGE, PENDING = "rejudge", "pending"
VERDICT_NAMES = frozenset({KEEP, REVERT, WRONG_BOTH, UNDECIDABLE})
#: RULES.md rule 3: "a third judge sees the evidence and both reasonings and decides keep or revert".
TIE_NAMES = frozenset({KEEP, REVERT, WRONG_BOTH})
DECISIONS = (KEEP, REVERT, REJUDGE, PENDING)
#: The passes whose failed verdict is judged again (REJUDGE.json): pass 1, and the pass 2 of a
#: pass-1 verdict that is not keep (rule 2).
REJUDGE_PASSES = ("p1", "p2")
#: What a pending row waits for: rule 4's second judgement of a pass-1 keep, or the third judge.
PENDING_PASSES = ("p2", "tie")

#: The digests the rules and the input were sealed with (commit 02260ee, 2026-09-23 14:24).
RULES_SHA256 = "671ef6d68faea2cdda5046c110a3dc53dce63e8cd727b5fccc5637b985469f31"
INPUT_SHA256 = "099c9380f252e77ca6a086a6a0b532dbfb1175b4f62817b7c15a9dfc553a6c11"

SAMPLE_SEED = 20260923
SAMPLE_SIZE = 60
#: RULES.md rule 4: "more than 3 of the 60 (5 %)".
SAMPLE_THRESHOLD = 3
SAMPLE_METHOD = (
    "random.Random(20260923).sample(population, 60), population = the change_keys of the pass-1 "
    "verdicts that are 'keep', sorted ascending (Python str order); keys in the order sample returns"
)
SAMPLE_RULE = (
    "RULES.md rule 4: if more than 3 of the 60 (5 %) come back not 'keep', every pass-1 'keep' is "
    "judged a second time under rule 3"
)

NORMALISATION = (
    "Unicode NFC, then every maximal run of characters for which Python's str.isspace() is true "
    "becomes one U+0020 space, then both ends are stripped; nothing else"
)

RESIDUAL = (
    "The field is open again, not corrected: the reversal withdraws a write the Opus "
    "re-verification did not confirm, and does not claim the restored value is right "
    "(opus_audit/RULES.md)."
)

RAW = "VERDICTS_RAW.json"
ROUND_2 = "VERDICTS_ROUND2.json"
ROUND_2_SECTIONS = ("sample", "p1", "p2")
#: Why a verdict is no longer on its row's route (`Overlay.set_aside`).
REPLACED = "failed the quote check; a counted round-2 verdict of the same pass replaces it"
NOT_COUNTED = "failed the quote check: it does not count and replaces nothing"
STALE_TIE = "a later round replaced the p1 or p2 verdict it was shown: its pair is not the route's"
PAIR_RULE = (
    "A round-1 tie counts only while the p1 and the p2 verdict on the row's route are, as JSON "
    "records, the very VERDICTS_RAW.json p1 and p2 of the row it was shown; once a later round "
    "replaces either, the tie is set aside as stale, and a pair that still disagrees needs a new tie."
)

OUTPUTS = (
    "DECISIONS.jsonl",
    "COUNTS.json",
    "REJUDGE.json",
    "REVERSAL_3_INPUT.jsonl",
    "SECOND_JUDGE.json",
    "TIE_ROUND2.json",
)


# ------------------------------------------------------------------------------ the inputs
def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sealed(path: Path, expected: str) -> str:
    """`path`'s sha256, refused unless it is the digest sealed before the first verdict."""
    actual = sha256_file(path)
    if actual != expected:
        raise AuditError(
            f"{path.name} is not the file sealed before the first verdict: sha256 {actual}, "
            f"sealed {expected}"
        )
    return actual


def read_input(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    keys = [r["change_key"] for r in rows]
    if len(set(keys)) != len(keys):
        raise AuditError(f"{path.name} lists a change_key twice")
    return rows


def read_verdicts(path: Path) -> dict[str, dict[str, dict[str, Any]]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if set(raw) != set(PASSES):
        raise AuditError(f"{path.name} holds {sorted(raw)}, not the passes {list(PASSES)}")
    return raw


def _differ(what: str, want: set[str], have: set[str]) -> None:
    if want != have:
        missing, extra = sorted(want - have)[:5], sorted(have - want)[:5]
        raise AuditError(f"{what}: missing {missing}, not on any route {extra}")


def _verdict_shape(stage: str, key: str, v: Mapping[str, Any]) -> None:
    """Refuse a verdict that is not a verdict of RULES.md, or not filed under its own key."""
    if v["change_key"] != key:
        raise AuditError(f"{stage}: the verdict filed under {key} is for {v['change_key']}")
    if v["verdict"] not in VERDICT_NAMES:
        raise AuditError(f"{stage} {key}: {v['verdict']!r} is not a verdict of RULES.md")
    if stage == "tie" and v["verdict"] not in TIE_NAMES:
        raise AuditError(f"tie {key}: the third judge decides keep or revert, not {v['verdict']}")
    if v["verdict"] == WRONG_BOTH and not v["right_value"]:
        raise AuditError(f"{stage} {key}: a wrong-both verdict without its right_value")
    if not isinstance(v["quotes"], list):
        raise AuditError(f"{stage} {key}: quotes is not a list")


def validate(rows: Sequence[Mapping[str, Any]], verdicts: Mapping[str, Mapping[str, Any]]) -> None:
    """Refuse round-1 verdicts that are not exactly the routes RULES.md gives these rows."""
    for stage in PASSES:
        for key, v in verdicts[stage].items():
            _verdict_shape(stage, key, v)
    keys = {r["change_key"] for r in rows}
    _differ("p1 against INPUT.jsonl", keys, set(verdicts["p1"]))
    second = {k for k in keys if verdicts["p1"][k]["verdict"] != KEEP}
    _differ("p2 against the pass-1 verdicts that are not keep", second, set(verdicts["p2"]))
    third = {k for k in second if verdicts["p2"][k]["verdict"] == KEEP}
    _differ("tie against the pass-2 verdicts that are keep", third, set(verdicts["tie"]))


def read_round_2(
    path: Path, raw: Mapping[str, Mapping[str, Any]], sample_keys: Sequence[str]
) -> dict[str, dict[str, dict[str, Any]]]:
    """VERDICTS_ROUND2.json: the stated sample judged again, and failed round-1 verdicts anew.

    Refused unless every verdict has round 1's shape, the sample is exactly KEEP_SAMPLE.json's
    keys, and every p1 or p2 verdict has a round-1 verdict of its pass to replace (whether that one
    failed is the quote check's to say: `overlay`).
    """
    got = json.loads(path.read_text(encoding="utf-8"))
    if set(got) != set(ROUND_2_SECTIONS):
        raise AuditError(f"{path.name} holds {sorted(got)}, not {list(ROUND_2_SECTIONS)}")
    for section in ROUND_2_SECTIONS:
        for key, v in got[section].items():
            _verdict_shape(section, key, v)
    if set(got["sample"]) != set(sample_keys):
        raise AuditError(f"{path.name}'s sample is not the keys KEEP_SAMPLE.json states")
    for stage in ("p1", "p2"):
        orphans = sorted(set(got[stage]) - set(raw[stage]))
        if orphans:
            raise AuditError(
                f"round 2 {stage}: no round-1 {stage} verdict to replace: {orphans[:5]}"
            )
    return got


# ------------------------------------------------------------------------------ the rule
def route(
    key: str, verdicts: Mapping[str, Mapping[str, Any]], second_judgement: bool = False
) -> tuple[str, ...]:
    """The passes the rule reads for this row; `second_judgement` is rule 4 having fired."""
    if verdicts["p1"][key]["verdict"] == KEEP:
        if not second_judgement:
            return ("p1",)
        if key not in verdicts["p2"] or verdicts["p2"][key]["verdict"] == KEEP:
            return ("p1", "p2")
        return ("p1", "p2", "tie")
    if verdicts["p2"][key]["verdict"] != KEEP:
        return ("p1", "p2")
    return ("p1", "p2", "tie")


def _check_record(check: Q.VerdictCheck) -> dict[str, Any]:
    return {
        "counted": check.counted,
        "reason": check.reason,
        "quotes": [
            {"source": q.source, "outcome": q.outcome, "detail": q.detail} for q in check.quotes
        ],
    }


def decide_row(
    row: Mapping[str, Any],
    verdicts: Mapping[str, Mapping[str, Any]],
    checks: Mapping[str, Mapping[str, Q.VerdictCheck]],
    *,
    second_judgement: bool = False,
) -> dict[str, Any]:
    """One row's decision line (DECISIONS.jsonl)."""
    key = row["change_key"]
    stages = route(key, verdicts, second_judgement)
    given = [p for p in stages if key in verdicts[p]]
    basis = [
        {"pass": p, "verdict": verdicts[p][key]["verdict"], "counted": checks[p][key].counted}
        for p in given
    ]
    uncounted = [p for p in stages if p not in given or not checks[p][key].counted]
    pass_1_keep = basis[0]["verdict"] == KEEP
    rejudge = [p for p in uncounted if p == "p1" or (p == "p2" and not pass_1_keep)]
    # a route is read in order: a row waits for the first verdict it lacks, never a later one
    pending = [] if rejudge else uncounted[:1]
    route_decision = None
    if len(given) == len(stages):
        route_decision = KEEP if basis[-1]["verdict"] == KEEP else REVERT
    decision = REJUDGE if rejudge else PENDING if pending else route_decision
    proposals = [
        {"pass": p, "value": verdicts[p][key]["right_value"]}
        for p in given
        if verdicts[p][key]["verdict"] == WRONG_BOTH
    ]
    values = {x["value"] for x in proposals}
    return {
        "change_key": key,
        "site_id": row["site_id"],
        "site_name": row["site_name"],
        "column": row["column"],
        "old_value": row["old_value"],
        "written_value": row["written_value"],
        "current_value": row["current_value"],
        "superseded": row["superseded"],
        "decision": decision,
        "route_decision": route_decision,
        "basis": basis,
        "rejudge": rejudge,
        "pending": pending,
        "proposed_value": values.pop() if decision == REVERT and len(values) == 1 else None,
        "proposals": proposals,
        "reversal": decision == REVERT and not row["superseded"],
        "quote_check": {p: _check_record(checks[p][key]) for p in given},
    }


def decide(
    rows: Iterable[Mapping[str, Any]],
    verdicts: Mapping[str, Mapping[str, Any]],
    checks: Mapping[str, Mapping[str, Q.VerdictCheck]],
    *,
    second_judgement: bool = False,
) -> list[dict[str, Any]]:
    return [decide_row(r, verdicts, checks, second_judgement=second_judgement) for r in rows]


# ------------------------------------------------------------------------------ round 2
def rule_4(
    sample: Mapping[str, Mapping[str, Any]], sample_checks: Mapping[str, Q.VerdictCheck]
) -> dict[str, Any]:
    """Whether rule 4 fired, on the counted verdicts of the sample judged again.

    A sample verdict that failed its quote check has not come back; while such verdicts could still
    tip the count over the threshold, rule 4 is not decided and the run is refused.
    """
    counted = sorted(k for k in sample if sample_checks[k].counted)
    not_keep = [k for k in counted if sample[k]["verdict"] != KEEP]
    not_counted = sorted(set(sample) - set(counted))
    fired = len(not_keep) > SAMPLE_THRESHOLD
    if not fired and len(not_keep) + len(not_counted) > SAMPLE_THRESHOLD:
        raise AuditError(
            f"rule 4 is not decided: {len(not_keep)} counted sample verdicts are not keep and "
            f"{len(not_counted)} failed the quote check - judge these again first: {not_counted}"
        )
    return {
        "rule": SAMPLE_RULE,
        "sample": len(sample),
        "counted": len(counted),
        "not_counted": not_counted,
        "by_verdict": _sorted(Counter(sample[k]["verdict"] for k in counted)),
        "not_keep": len(not_keep),
        "not_keep_keys": not_keep,
        "threshold": SAMPLE_THRESHOLD,
        "fired": fired,
    }


@dataclass(frozen=True)
class Overlay:
    """The verdicts on the routes after round 2 (p1, p2, tie), the quote check of each, the file and
    section each came from, and per change key the verdicts no longer on its route and why."""

    verdicts: dict[str, dict[str, dict[str, Any]]]
    checks: dict[str, dict[str, Q.VerdictCheck]]
    origin: dict[str, dict[str, str]]
    set_aside: dict[str, list[dict[str, Any]]]


def _aside(where: str, v: Mapping[str, Any], check: Q.VerdictCheck, why: str) -> dict[str, Any]:
    return {
        "from": where,
        "verdict": v["verdict"],
        "counted": check.counted,
        "reason": check.reason,
        "why": why,
    }


def overlay(
    raw: Mapping[str, Mapping[str, Any]],
    raw_checks: Mapping[str, Mapping[str, Q.VerdictCheck]],
    round2: Mapping[str, Mapping[str, Any]],
    round2_checks: Mapping[str, Mapping[str, Q.VerdictCheck]],
) -> Overlay:
    """Round 2 laid over round 1 (module docstring); refused where it re-judges a counted verdict."""
    verdicts = {p: dict(raw[p]) for p in PASSES}
    checks = {p: dict(raw_checks[p]) for p in PASSES}
    origin = {p: dict.fromkeys(raw[p], f"{RAW} {p}") for p in PASSES}
    aside: dict[str, list[dict[str, Any]]] = {}
    for stage in ("p1", "p2"):
        for key, v in sorted(round2[stage].items()):
            if raw_checks[stage][key].counted:
                raise AuditError(
                    f"round 2 {stage} {key}: the round-1 verdict counted, and a counted verdict is "
                    "never judged again"
                )
            new = round2_checks[stage][key]
            if not new.counted:
                aside.setdefault(key, []).append(_aside(f"{ROUND_2} {stage}", v, new, NOT_COUNTED))
                continue
            old = _aside(f"{RAW} {stage}", raw[stage][key], raw_checks[stage][key], REPLACED)
            aside.setdefault(key, []).append(old)
            verdicts[stage][key], checks[stage][key] = v, new
            origin[stage][key] = f"{ROUND_2} {stage}"
    for key, v in sorted(round2["sample"].items()):
        new = round2_checks["sample"][key]
        if not new.counted:
            aside.setdefault(key, []).append(_aside(f"{ROUND_2} sample", v, new, NOT_COUNTED))
            continue
        # it never saw pass 1: the keep's second, independent judgement under rule 3
        verdicts["p2"][key], checks["p2"][key] = v, new
        origin["p2"][key] = f"{ROUND_2} sample"
    for key in sorted(raw["tie"]):
        if verdicts["p1"][key] == raw["p1"][key] and verdicts["p2"][key] == raw["p2"][key]:
            continue
        aside.setdefault(key, []).append(
            _aside(f"{RAW} tie", raw["tie"][key], raw_checks["tie"][key], STALE_TIE)
        )
        del verdicts["tie"][key], checks["tie"][key], origin["tie"][key]
    return Overlay(verdicts, checks, origin, aside)


def trace(decisions: Iterable[Mapping[str, Any]], ov: Overlay) -> list[dict[str, Any]]:
    """Each decision line with where each route verdict came from and what was set aside."""
    return [
        {
            **d,
            "basis": [{**b, "from": ov.origin[b["pass"]][d["change_key"]]} for b in d["basis"]],
            "set_aside": ov.set_aside.get(d["change_key"], []),
        }
        for d in decisions
    ]


# ------------------------------------------------------------------------------ the lists
def rejudge(decisions: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The change keys whose verdict at each pass failed the quote check (REJUDGE.json)."""
    by_pass: dict[str, list[str]] = {p: [] for p in REJUDGE_PASSES}
    for d in decisions:
        for stage in d["rejudge"]:
            by_pass[stage].append(d["change_key"])
    return {
        "about": (
            "Rows whose route holds a pass-1 verdict, or the pass-2 verdict of a pass-1 verdict "
            "that is not keep, that failed the quote check with nothing counted in its place "
            "(RULES.md: it does not count; the row is judged again), by that pass. A p2 verdict "
            "never sees p1, so a counted p2 stays valid when p1 is re-run. Rows waiting on rule "
            "4's second judgement or on a third judge are in SECOND_JUDGE.json and TIE_ROUND2.json."
        ),
        **{p: sorted(keys) for p, keys in by_pass.items()},
    }


def second_judge(
    decisions: Iterable[Mapping[str, Any]], rule4: Mapping[str, Any]
) -> dict[str, Any]:
    """The pass-1 keeps that still lack a counted second judgement (SECOND_JUDGE.json)."""
    keys = sorted(d["change_key"] for d in decisions if d["pending"] == ["p2"])
    return {
        "about": (
            "RULES.md rule 4 fired: every pass-1 keep is judged a second time under rule 3. These "
            "are the pass-1 keeps without a counted second judgement - never judged a second time, "
            "or judged and failed the quote check. Each is judged by an independent Opus judge who "
            "does not see pass 1; a keep keeps the row, any other verdict calls the third judge."
        ),
        "rule_4": rule4,
        "count": len(keys),
        "keys": keys,
    }


def _judgement(v: Mapping[str, Any]) -> dict[str, Any]:
    return {field: v[field] for field in ("verdict", "right_value", "reason", "quotes")}


def tie_round_2(
    decisions: Iterable[Mapping[str, Any]], verdicts: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    """The rows whose counted p1 and p2 disagree and lack a counted tie (TIE_ROUND2.json)."""
    keys = sorted(d["change_key"] for d in decisions if d["pending"] == ["tie"])
    return {
        "about": (
            "RULES.md rule 3: the p1 and p2 verdicts of each row disagree (one keep, one not) and "
            "no counted third verdict decides the pair. A third judge sees the evidence and both "
            "judgements (judge_1 = p1, judge_2 = p2) and decides keep or revert."
        ),
        "pair_rule": PAIR_RULE,
        "count": len(keys),
        "rows": [
            {
                "change_key": key,
                "judge_1": _judgement(verdicts["p1"][key]),
                "judge_2": _judgement(verdicts["p2"][key]),
            }
            for key in keys
        ],
    }


def keep_sample(verdicts: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """RULES.md rule 4's seeded sample of the pass-1 keeps (KEEP_SAMPLE.json)."""
    population = sorted(k for k, v in verdicts["p1"].items() if v["verdict"] == KEEP)
    # a reproducible draw, not a secret: the seed is published before the draw is judged
    keys = random.Random(SAMPLE_SEED).sample(population, SAMPLE_SIZE)  # noqa: S311
    return {
        "method": SAMPLE_METHOD,
        "seed": SAMPLE_SEED,
        "size": SAMPLE_SIZE,
        "population": len(population),
        "population_sha256": hashlib.sha256("\n".join(population).encode("utf-8")).hexdigest(),
        "rule": SAMPLE_RULE,
        "keys": keys,
    }


def _bucket(value: str) -> str | None:
    return categorize_period(int(value))


def reversal_input(
    decisions: Iterable[Mapping[str, Any]], verdicts: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """The rows to undo, in the shape of the journal-reversal lane's REASONS.json entries."""
    out: list[dict[str, Any]] = []
    for d in decisions:
        if not d["reversal"]:
            continue
        key = d["change_key"]
        stages = [b["pass"] for b in d["basis"]]
        judges = [
            {
                "pass": p,
                "verdict": verdicts[p][key]["verdict"],
                "reason": verdicts[p][key]["reason"],
            }
            for p in stages
        ]
        against = [j["pass"] for j in judges if j["verdict"] != KEEP]
        residual = RESIDUAL
        if d["proposed_value"] is not None:
            residual += (
                f" A judge proposed {d['proposed_value']!r}; it is not written here (RULES.md "
                "rule 5)."
            )
        line: dict[str, Any] = {
            "journal_id": None,
            "change_key": key,
            "site_id": d["site_id"],
            "name": d["site_name"],
            "column": d["column"],
            "old_value": d["old_value"],
            "new_value": d["written_value"],
            "reason": "the Opus re-verification decided to revert this write (opus_audit/RULES.md "
            "rule 3): " + ", ".join(f"{j['pass']} {j['verdict']}" for j in judges),
            # each (source, text) once, in the order the judges quoted it
            "quotes": [
                {"source": s, "text": t}
                for s, t in dict.fromkeys(
                    (q["source"], q["quote"]) for p in against for q in verdicts[p][key]["quotes"]
                )
            ],
            "residual": residual,
            "judges": judges,
        }
        if d["column"] == "period_start":
            restored, written = _bucket(d["old_value"]), _bucket(d["written_value"])
            line["period_bucket"] = {
                "restored": restored,
                "written": written,
                "changes": restored != written,
            }
        out.append(line)
    return out


# ------------------------------------------------------------------------------ the counts
def _sorted(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items()))


def verdict_counts(
    verdicts: Mapping[str, Mapping[str, Any]], checks: Mapping[str, Mapping[str, Q.VerdictCheck]]
) -> dict[str, Any]:
    """Per pass or section: the verdicts, by name, and how they fared in the quote check."""
    return {
        section: {
            "verdicts": len(given),
            "by_verdict": _sorted(Counter(v["verdict"] for v in given.values())),
            "counted": sum(c.counted for c in checks[section].values()),
            "failed": sum(not c.counted for c in checks[section].values()),
            "failed_by_reason": _sorted(
                Counter(c.reason for c in checks[section].values() if not c.counted)
            ),
            "quotes_by_outcome": _sorted(
                Counter(q.outcome for c in checks[section].values() for q in c.quotes)
            ),
        }
        for section, given in verdicts.items()
    }


def overlay_counts(ov: Overlay, round2_checks: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    origins = Counter(o for p in PASSES for o in ov.origin[p].values())
    return {
        "replaced": {p: origins[f"{ROUND_2} {p}"] for p in ("p1", "p2")},
        "sample_as_p2": origins[f"{ROUND_2} sample"],
        "not_counted": {
            s: sum(not c.counted for c in round2_checks[s].values()) for s in ROUND_2_SECTIONS
        },
        "ties_set_aside": sum(x["why"] == STALE_TIE for xs in ov.set_aside.values() for x in xs),
    }


def decision_counts(decisions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    reverts = [d for d in decisions if d["decision"] == REVERT]
    reversal = [d for d in decisions if d["reversal"]]
    return {
        "decisions": {name: sum(d["decision"] == name for d in decisions) for name in DECISIONS},
        "revert_by_column": _sorted(Counter(d["column"] for d in reverts)),
        "revert_by_superseded": {
            "false": sum(not d["superseded"] for d in reverts),
            "true": sum(bool(d["superseded"]) for d in reverts),
        },
        "rejudge_by_pass": {p: sum(p in d["rejudge"] for d in decisions) for p in REJUDGE_PASSES},
        "pending_by_pass": {p: sum(p in d["pending"] for d in decisions) for p in PENDING_PASSES},
        "wrong_both_proposals": sum(d["proposed_value"] is not None for d in reverts),
        "wrong_both_disagreements": sum(
            bool(d["proposals"]) and d["proposed_value"] is None for d in reverts
        ),
        "reversal_rows": len(reversal),
        "reversal_by_column": _sorted(Counter(d["column"] for d in reversal)),
        "reversal_period_bucket_changes": sum(
            d["column"] == "period_start" and _bucket(d["old_value"]) != _bucket(d["written_value"])
            for d in reversal
        ),
    }


# ------------------------------------------------------------------------------ the run
def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )


def _write_jsonl(path: Path, lines: Iterable[Mapping[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines),
        encoding="utf-8",
        newline="\n",
    )


def load(audit: Path, rules_sha256: str, input_sha256: str) -> tuple[list, dict, dict[str, str]]:
    """The sealed rules and input, and the round-1 verdicts - refused unless they fit the rules."""
    inputs = {
        "RULES.md": sealed(audit / "RULES.md", rules_sha256),
        "INPUT.jsonl": sealed(audit / "INPUT.jsonl", input_sha256),
        RAW: sha256_file(audit / RAW),
    }
    rows = read_input(audit / "INPUT.jsonl")
    verdicts = read_verdicts(audit / RAW)
    validate(rows, verdicts)
    return rows, verdicts, inputs


def load_rounds(
    audit: Path, rules_sha256: str, input_sha256: str
) -> tuple[list, dict, dict, dict[str, str]]:
    """`load`, then the stated keep sample and round 2 - each refused unless it fits round 1."""
    rows, raw, inputs = load(audit, rules_sha256, input_sha256)
    stated = json.loads((audit / "KEEP_SAMPLE.json").read_text(encoding="utf-8"))
    if stated != keep_sample(raw):
        raise AuditError(f"KEEP_SAMPLE.json is not rule 4's draw from {RAW}")
    round2 = read_round_2(audit / ROUND_2, raw, stated["keys"])
    inputs["KEEP_SAMPLE.json"] = sha256_file(audit / "KEEP_SAMPLE.json")
    inputs[ROUND_2] = sha256_file(audit / ROUND_2)
    return rows, raw, round2, inputs


def write_keep_sample(
    audit: Path, *, rules_sha256: str = RULES_SHA256, input_sha256: str = INPUT_SHA256
) -> dict[str, Any]:
    """KEEP_SAMPLE.json, once: a sample already stated is never drawn again differently."""
    _rows, verdicts, _inputs = load(audit, rules_sha256, input_sha256)
    sample = keep_sample(verdicts)
    path = audit / "KEEP_SAMPLE.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != sample:
        raise AuditError(f"{path} already states another sample")
    _write_json(path, sample)
    return sample


def _check_all(
    verdicts: Mapping[str, Mapping[str, Any]],
    by_key: Mapping[str, Mapping[str, Any]],
    library: Q.Library,
) -> dict[str, dict[str, Q.VerdictCheck]]:
    return {
        section: {k: Q.check_verdict(v, by_key[k], library) for k, v in sorted(given.items())}
        for section, given in verdicts.items()
    }


def run(
    audit: Path,
    *,
    repo: Path = Q.REPO,
    rules_sha256: str = RULES_SHA256,
    input_sha256: str = INPUT_SHA256,
    pdf_text: Callable[[bytes], str] = Q.pdftotext,
) -> dict[str, Any]:
    """Check every quote of both rounds, lay round 2 over round 1, decide every row and write the
    outputs (`OUTPUTS`); returns COUNTS.json."""
    rows, raw, round2, inputs = load_rounds(audit, rules_sha256, input_sha256)
    library = Q.Library(repo, audit / "pages", pdf_text)
    by_key = {r["change_key"]: r for r in rows}
    raw_checks = _check_all(raw, by_key, library)
    round2_checks = _check_all(round2, by_key, library)
    ov = overlay(raw, raw_checks, round2, round2_checks)
    rule4 = rule_4(round2["sample"], round2_checks["sample"])
    decisions = trace(decide(rows, ov.verdicts, ov.checks, second_judgement=rule4["fired"]), ov)
    second = second_judge(decisions, rule4)
    ties = tie_round_2(decisions, ov.verdicts)
    summary = {
        "inputs": inputs,
        "normalisation": NORMALISATION,
        "pair_rule": PAIR_RULE,
        "round_1": verdict_counts(raw, raw_checks),
        "round_2": verdict_counts(round2, round2_checks),
        "overlay": overlay_counts(ov, round2_checks),
        "rule_4": rule4,
        "on_the_routes": verdict_counts(ov.verdicts, ov.checks),
        **decision_counts(decisions),
        "second_judge": second["count"],
        "tie_round_2": ties["count"],
    }
    _write_jsonl(audit / "DECISIONS.jsonl", decisions)
    _write_json(audit / "COUNTS.json", summary)
    _write_json(audit / "REJUDGE.json", rejudge(decisions))
    _write_jsonl(audit / "REVERSAL_3_INPUT.jsonl", reversal_input(decisions, ov.verdicts))
    _write_json(audit / "SECOND_JUDGE.json", second)
    _write_json(audit / "TIE_ROUND2.json", ties)
    return summary
