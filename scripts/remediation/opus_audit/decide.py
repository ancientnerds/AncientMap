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
(TIE_ROUND<n>.json) - not given yet, or given and failed. `route_decision` records what the verdicts
on a complete route would have decided, for the reader and nothing else.

**The rounds after round 1** (`VERDICTS_ROUND2.json`, `VERDICTS_ROUND3.json`, ...: `round_files`,
`read_round`, `overlay`) are laid over round 1 one after the other, in number order and through one
code path. Every verdict of every round is quote-checked exactly like round 1; one that fails does
not count and replaces nothing. A round was judged from the lists the run before it wrote, so each
of its verdicts is laid on the routes as they stood before the round, and refused unless its row
waited on exactly that verdict (a counted verdict is never judged again). What a counted verdict of
each section does (`SECTIONS`):

* `p1`, `p2` - the failed verdict of that pass judged anew (REJUDGE.json): it replaces that verdict;
* `sample` - rule 4's stated sample judged again, in one round only; it never saw pass 1, so it is
  its pass-1 keep's second judgement and stands as the row's p2; rule 4 is decided on these
  verdicts at the end of their round (`rule_4`);
* `second` - rule 4's second judgement of a pass-1 keep that lacks a counted one (SECOND_JUDGE.json),
  only once rule 4 fired in an earlier round: it stands as the row's p2 under rule 3;
* `tie` - the third judge of a pair that disagrees (TIE_ROUND<n>.json of the round before): it
  decides the row only while the p1 and p2 on its route are the very pair it was shown
  (`PAIR_RULE`); a tie whose pair a later round replaced is set aside as stale.

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
import re
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
#: A round after round 1: VERDICTS_ROUND2.json, VERDICTS_ROUND3.json, ... (`round_files`).
ROUND_FILE = re.compile(r"VERDICTS_ROUND([1-9][0-9]*)\.json")
#: The sections a round file may hold, in the order a round is laid, and the pass each one fills.
SECTIONS = ("p1", "p2", "sample", "second", "tie")
STAGE_OF = {"p1": "p1", "p2": "p2", "sample": "p2", "second": "p2", "tie": "tie"}
#: Why a verdict is no longer on its row's route (`Overlay.set_aside`).
REPLACED = "failed the quote check; a counted verdict of a later round replaces it"
NOT_COUNTED = "failed the quote check: it does not count and replaces nothing"
STALE_TIE = "a later round replaced the p1 or p2 verdict it was shown: its pair is not the route's"
PAIR_RULE = (
    "A tie counts only while the p1 and the p2 verdict on the row's route are, as JSON records, the "
    "very pair it was shown: a round-1 tie the row's VERDICTS_RAW.json p1 and p2, a later round's "
    "tie the p1 and p2 on the route before that round (the pair TIE_ROUND<n>.json of the round "
    "before listed); once a later round replaces either, the tie is set aside as stale, and a pair "
    "that still disagrees needs a new tie."
)


def outputs(last: int) -> tuple[str, ...]:
    """What `run` writes once round `last` is laid; the lists it names are the next round's."""
    return (
        "DECISIONS.jsonl",
        "COUNTS.json",
        "REJUDGE.json",
        "REVERSAL_3_INPUT.jsonl",
        "SECOND_JUDGE.json",
        f"TIE_ROUND{last}.json",
        f"REJUDGE_ROUND{last}.json",
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


def round_files(audit: Path) -> list[Path]:
    """Every round after round 1 in `audit`, in number order: rounds 2, 3, ... without a gap."""
    found: dict[int, Path] = {}
    for path in audit.glob("VERDICTS_ROUND*.json"):
        match = ROUND_FILE.fullmatch(path.name)
        if match is None:
            raise AuditError(f"{path.name} is not a round file VERDICTS_ROUND<n>.json")
        found[int(match.group(1))] = path
    numbers = sorted(found)
    if numbers != list(range(2, 2 + len(numbers))):
        raise AuditError(f"the round files are rounds {numbers}: a gap, or no round 2")
    return [found[n] for n in numbers]


def round_number(name: str) -> int:
    match = ROUND_FILE.fullmatch(name)
    if match is None:
        raise AuditError(f"{name} is not a round file")
    return int(match.group(1))


def read_round(path: Path, sample_keys: Sequence[str]) -> dict[str, dict[str, dict[str, Any]]]:
    """A round file: sections of `SECTIONS`, every verdict of round 1's shape, and a sample of
    exactly KEEP_SAMPLE.json's keys. Whether a row waited on a verdict is `overlay`'s to say."""
    got = json.loads(path.read_text(encoding="utf-8"))
    unknown = sorted(set(got) - set(SECTIONS))
    if unknown:
        raise AuditError(f"{path.name} holds {unknown}: a round holds the sections {SECTIONS}")
    for section, given in got.items():
        for key, v in given.items():
            _verdict_shape(section, key, v)
    if got.get("sample") and set(got["sample"]) != set(sample_keys):
        raise AuditError(f"{path.name}'s sample is not the keys KEEP_SAMPLE.json states")
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


# ------------------------------------------------------------------------------ the rounds
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
class Round:
    """A round after round 1: its file name, its verdicts by section, the quote check of each."""

    name: str
    verdicts: Mapping[str, Mapping[str, Any]]
    checks: Mapping[str, Mapping[str, Q.VerdictCheck]]


@dataclass(frozen=True)
class Overlay:
    """The verdicts on the routes after every round (p1, p2, tie), the quote check of each, the file
    and section each came from, per change key the verdicts no longer on its route and why, rule 4
    as its sample decided it (None before any round judged the sample), and what each round laid."""

    verdicts: dict[str, dict[str, dict[str, Any]]]
    checks: dict[str, dict[str, Q.VerdictCheck]]
    origin: dict[str, dict[str, str]]
    set_aside: dict[str, list[dict[str, Any]]]
    rule_4: dict[str, Any] | None
    rounds: dict[str, dict[str, Any]]


def _aside(where: str, v: Mapping[str, Any], check: Q.VerdictCheck, why: str) -> dict[str, Any]:
    return {
        "from": where,
        "verdict": v["verdict"],
        "counted": check.counted,
        "reason": check.reason,
        "why": why,
    }


def _waits_on(
    where: str,
    section: str,
    key: str,
    verdicts: Mapping[str, Mapping[str, Any]],
    checks: Mapping[str, Mapping[str, Q.VerdictCheck]],
    fired: bool,
) -> None:
    """Refuse a round's verdict unless its row, as the routes stood before the round, waited on
    exactly that verdict: the section's rule in the module docstring."""
    if key not in verdicts["p1"]:
        raise AuditError(f"{where} {key}: not a row of INPUT.jsonl")
    stage = STAGE_OF[section]
    standing = key in verdicts[stage] and checks[stage][key].counted
    if section in ("p1", "p2"):
        if key not in verdicts[stage]:
            raise AuditError(f"{where} {key}: no {stage} verdict before this round to replace")
    elif section in ("sample", "second"):
        if verdicts["p1"][key]["verdict"] != KEEP:
            raise AuditError(f"{where} {key}: not a pass-1 keep, so no second judgement is due")
        if section == "second" and not fired:
            raise AuditError(f"{where} {key}: rule 4 had not fired before this round")
    else:
        p1, p2 = verdicts["p1"][key], verdicts["p2"].get(key)
        if p2 is None or (p1["verdict"] == KEEP) == (p2["verdict"] == KEEP):
            raise AuditError(f"{where} {key}: the row does not wait on a third judge")
        if p1["verdict"] == KEEP and not fired:
            raise AuditError(f"{where} {key}: rule 4 had not fired, so its pass-1 keep stands")
        if not (checks["p1"][key].counted and checks["p2"][key].counted):
            raise AuditError(f"{where} {key}: the pair a tie would decide does not count")
    if standing:
        raise AuditError(
            f"{where} {key}: the {stage} verdict before this round counted, and a counted verdict "
            "is never judged again"
        )


def overlay(
    raw: Mapping[str, Mapping[str, Any]],
    raw_checks: Mapping[str, Mapping[str, Q.VerdictCheck]],
    rounds: Sequence[Round],
) -> Overlay:
    """Every round laid over round 1 in order (module docstring), through one code path."""
    verdicts = {p: dict(raw[p]) for p in PASSES}
    checks = {p: dict(raw_checks[p]) for p in PASSES}
    origin = {p: dict.fromkeys(raw[p], f"{RAW} {p}") for p in PASSES}
    # the pair each tie on a route was shown
    shown = {key: (raw["p1"][key], raw["p2"][key]) for key in raw["tie"]}
    aside: dict[str, list[dict[str, Any]]] = {}
    rule4: dict[str, Any] | None = None
    laid: dict[str, dict[str, Any]] = {}
    for rnd in rounds:
        was = {p: dict(verdicts[p]) for p in PASSES}
        was_checks = {p: dict(checks[p]) for p in PASSES}
        fired = rule4 is not None and rule4["fired"]
        counts: dict[str, Counter[str]] = {"laid": Counter(), "not_counted": Counter()}
        replaced = 0
        for section in SECTIONS:
            for key, v in sorted(rnd.verdicts.get(section, {}).items()):
                where = f"{rnd.name} {section}"
                _waits_on(where, section, key, was, was_checks, fired)
                new = rnd.checks[section][key]
                if not new.counted:
                    aside.setdefault(key, []).append(_aside(where, v, new, NOT_COUNTED))
                    counts["not_counted"][section] += 1
                    continue
                stage = STAGE_OF[section]
                if key in verdicts[stage]:
                    old = _aside(
                        origin[stage][key], verdicts[stage][key], checks[stage][key], REPLACED
                    )
                    aside.setdefault(key, []).append(old)
                    replaced += 1
                verdicts[stage][key], checks[stage][key] = v, new
                origin[stage][key] = where
                counts["laid"][section] += 1
                if stage == "tie":
                    shown[key] = (was["p1"][key], was["p2"][key])
        if rnd.verdicts.get("sample"):
            if rule4 is not None:
                raise AuditError(f"{rnd.name}: rule 4's sample is judged in one round only")
            rule4 = rule_4(rnd.verdicts["sample"], rnd.checks["sample"])
        stale = 0
        for key in sorted(verdicts["tie"]):
            if (verdicts["p1"][key], verdicts["p2"][key]) == shown[key]:
                continue
            aside.setdefault(key, []).append(
                _aside(origin["tie"][key], verdicts["tie"][key], checks["tie"][key], STALE_TIE)
            )
            del verdicts["tie"][key], checks["tie"][key], origin["tie"][key], shown[key]
            stale += 1
        laid[rnd.name] = {
            "laid": _sorted(counts["laid"]),
            "not_counted": _sorted(counts["not_counted"]),
            "replaced": replaced,
            "ties_set_aside": stale,
        }
    return Overlay(verdicts, checks, origin, aside, rule4, laid)


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
            "4's second judgement or on a third judge are in SECOND_JUDGE.json and the last "
            "round's TIE_ROUND<n>.json."
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


def tie_list(
    decisions: Iterable[Mapping[str, Any]], verdicts: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    """The rows whose counted p1 and p2 disagree and lack a counted tie (TIE_ROUND<n>.json, n the
    last round laid): the next round's third judge sees each pair as listed here."""
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


def rejudge_round(rnd: Round, tie_file: str) -> dict[str, Any]:
    """The verdicts of round `rnd` that failed the quote check, by section (REJUDGE_ROUND<n>.json).

    Each is judged again: a failed verdict replaces nothing, so its row still waits on the verdict
    it did not deliver - a failed `second` in SECOND_JUDGE.json, a failed `tie` in `tie_file` (its
    pair unchanged), a failed `p1` or `p2` in REJUDGE.json.
    """
    failed = {
        section: [key for key, check in checks.items() if not check.counted]
        for section, checks in rnd.checks.items()
    }
    return {
        "about": (
            f"The verdicts of {rnd.name} that failed the quote check (RULES.md: it does not count; "
            "the row is judged again), by section. Each row still waits on the verdict it did not "
            f"deliver: a second judgement in SECOND_JUDGE.json, a third judge in {tie_file} (the "
            "pair is unchanged), a p1 or p2 in REJUDGE.json."
        ),
        "round": rnd.name,
        **{section: sorted(keys) for section, keys in failed.items()},
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
) -> tuple[list, dict, list[tuple[str, dict]], dict[str, str]]:
    """`load`, then the stated keep sample and every round after round 1 in order (`round_files`),
    each as (file name, verdicts by section) - refused unless it has round 1's shape and names only
    rows of INPUT.jsonl."""
    rows, raw, inputs = load(audit, rules_sha256, input_sha256)
    stated = json.loads((audit / "KEEP_SAMPLE.json").read_text(encoding="utf-8"))
    if stated != keep_sample(raw):
        raise AuditError(f"KEEP_SAMPLE.json is not rule 4's draw from {RAW}")
    inputs["KEEP_SAMPLE.json"] = sha256_file(audit / "KEEP_SAMPLE.json")
    keys = {r["change_key"] for r in rows}
    rounds: list[tuple[str, dict]] = []
    for path in round_files(audit):
        got = read_round(path, stated["keys"])
        strangers = sorted({k for given in got.values() for k in given} - keys)
        if strangers:
            raise AuditError(f"{path.name} judges rows INPUT.jsonl does not hold: {strangers[:5]}")
        rounds.append((path.name, got))
        inputs[path.name] = sha256_file(path)
    return rows, raw, rounds, inputs


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
    """Check every quote of every round, lay the rounds over round 1 in order, decide every row and
    write the outputs (`outputs` of the last round); returns COUNTS.json."""
    rows, raw, given, inputs = load_rounds(audit, rules_sha256, input_sha256)
    library = Q.Library(repo, audit / "pages", pdf_text)
    by_key = {r["change_key"]: r for r in rows}
    raw_checks = _check_all(raw, by_key, library)
    rounds = [Round(name, v, _check_all(v, by_key, library)) for name, v in given]
    ov = overlay(raw, raw_checks, rounds)
    if ov.rule_4 is None:
        raise AuditError("rule 4 is not decided: no round judged KEEP_SAMPLE.json's sample")
    decisions = trace(decide(rows, ov.verdicts, ov.checks, second_judgement=ov.rule_4["fired"]), ov)
    last = round_number(rounds[-1].name)
    names = outputs(last)
    tie_file, rejudge_file = names[-2], names[-1]
    second = second_judge(decisions, ov.rule_4)
    ties = tie_list(decisions, ov.verdicts)
    failed = rejudge_round(rounds[-1], tie_file)
    summary = {
        "inputs": inputs,
        "normalisation": NORMALISATION,
        "pair_rule": PAIR_RULE,
        "round_1": verdict_counts(raw, raw_checks),
        **{f"round_{round_number(r.name)}": verdict_counts(r.verdicts, r.checks) for r in rounds},
        "overlay": ov.rounds,
        "rule_4": ov.rule_4,
        "on_the_routes": verdict_counts(ov.verdicts, ov.checks),
        **decision_counts(decisions),
        "second_judge": second["count"],
        "tie_list": {"file": tie_file, "count": ties["count"]},
        "rejudge_round": {
            "file": rejudge_file,
            **{section: len(failed[section]) for section in rounds[-1].verdicts},
        },
    }
    _write_jsonl(audit / "DECISIONS.jsonl", decisions)
    _write_json(audit / "COUNTS.json", summary)
    _write_json(audit / "REJUDGE.json", rejudge(decisions))
    _write_jsonl(audit / "REVERSAL_3_INPUT.jsonl", reversal_input(decisions, ov.verdicts))
    _write_json(audit / "SECOND_JUDGE.json", second)
    _write_json(audit / tie_file, ties)
    _write_json(audit / rejudge_file, failed)
    return summary
