"""The decision rule of the Opus re-verification, over the verdicts that pass the quote check.

`output/remediation/opus_audit/RULES.md`, "Decision rule", sealed before the first verdict (its
sha256 and INPUT.jsonl's are `RULES_SHA256` and `INPUT_SHA256`; a run on other bytes is refused).

**The route** of a row (`route`) is the verdicts the rule reads, in order: a pass-1 `keep` stands
alone (rule 4); any other pass-1 verdict goes to pass 2 (rule 2); both not `keep` revert the row;
a pass-2 `keep` goes to the third judge, whose `keep` keeps and whose `revert` or `wrong-both`
reverts (rule 3 - a `wrong-both` says the written value is wrong, so it cannot keep it).

**Only counting verdicts decide** (`quotes.check_verdict`). A row with a verdict on its route that
failed the quote check is `rejudge`, and `rejudge` names every such pass; `route_decision` records
what the route would have decided, for the reader and nothing else.

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
from pathlib import Path
from typing import Any

from opus_audit import quotes as Q
from pipeline.utils.text import categorize_period

AuditError = Q.AuditError

PASSES = ("p1", "p2", "tie")
KEEP, REVERT, WRONG_BOTH, UNDECIDABLE = "keep", "revert", "wrong-both", "undecidable"
REJUDGE = "rejudge"
VERDICT_NAMES = frozenset({KEEP, REVERT, WRONG_BOTH, UNDECIDABLE})
#: RULES.md rule 3: "a third judge sees the evidence and both reasonings and decides keep or revert".
TIE_NAMES = frozenset({KEEP, REVERT, WRONG_BOTH})
DECISIONS = (KEEP, REVERT, REJUDGE)

#: The digests the rules and the input were sealed with (commit 02260ee, 2026-09-23 14:24).
RULES_SHA256 = "671ef6d68faea2cdda5046c110a3dc53dce63e8cd727b5fccc5637b985469f31"
INPUT_SHA256 = "099c9380f252e77ca6a086a6a0b532dbfb1175b4f62817b7c15a9dfc553a6c11"

SAMPLE_SEED = 20260923
SAMPLE_SIZE = 60
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

OUTPUTS = ("DECISIONS.jsonl", "COUNTS.json", "REJUDGE.json", "REVERSAL_3_INPUT.jsonl")


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


def validate(rows: Sequence[Mapping[str, Any]], verdicts: Mapping[str, Mapping[str, Any]]) -> None:
    """Refuse verdicts that are not exactly the routes RULES.md gives these rows."""
    for stage in PASSES:
        for key, v in verdicts[stage].items():
            if v["change_key"] != key:
                raise AuditError(f"{stage}: the verdict filed under {key} is for {v['change_key']}")
            if v["verdict"] not in VERDICT_NAMES:
                raise AuditError(f"{stage} {key}: {v['verdict']!r} is not a verdict of RULES.md")
            if stage == "tie" and v["verdict"] not in TIE_NAMES:
                raise AuditError(
                    f"tie {key}: the third judge decides keep or revert, not {v['verdict']}"
                )
            if v["verdict"] == WRONG_BOTH and not v["right_value"]:
                raise AuditError(f"{stage} {key}: a wrong-both verdict without its right_value")
            if not isinstance(v["quotes"], list):
                raise AuditError(f"{stage} {key}: quotes is not a list")
    keys = {r["change_key"] for r in rows}
    _differ("p1 against INPUT.jsonl", keys, set(verdicts["p1"]))
    second = {k for k in keys if verdicts["p1"][k]["verdict"] != KEEP}
    _differ("p2 against the pass-1 verdicts that are not keep", second, set(verdicts["p2"]))
    third = {k for k in second if verdicts["p2"][k]["verdict"] == KEEP}
    _differ("tie against the pass-2 verdicts that are keep", third, set(verdicts["tie"]))


# ------------------------------------------------------------------------------ the rule
def route(key: str, verdicts: Mapping[str, Mapping[str, Any]]) -> tuple[str, ...]:
    if verdicts["p1"][key]["verdict"] == KEEP:
        return ("p1",)
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
) -> dict[str, Any]:
    """One row's decision line (DECISIONS.jsonl)."""
    key = row["change_key"]
    stages = route(key, verdicts)
    basis = [
        {"pass": p, "verdict": verdicts[p][key]["verdict"], "counted": checks[p][key].counted}
        for p in stages
    ]
    failed = [b["pass"] for b in basis if not b["counted"]]
    route_decision = KEEP if basis[-1]["verdict"] == KEEP else REVERT
    decision = REJUDGE if failed else route_decision
    proposals = [
        {"pass": p, "value": verdicts[p][key]["right_value"]}
        for p in stages
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
        "rejudge": failed,
        "proposed_value": values.pop() if decision == REVERT and len(values) == 1 else None,
        "proposals": proposals,
        "reversal": decision == REVERT and not row["superseded"],
        "quote_check": {p: _check_record(checks[p][key]) for p in stages},
    }


def decide(
    rows: Iterable[Mapping[str, Any]],
    verdicts: Mapping[str, Mapping[str, Any]],
    checks: Mapping[str, Mapping[str, Q.VerdictCheck]],
) -> list[dict[str, Any]]:
    return [decide_row(r, verdicts, checks) for r in rows]


# ------------------------------------------------------------------------------ the lists
def rejudge(decisions: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The change keys whose verdict at each pass failed the quote check (REJUDGE.json)."""
    by_pass: dict[str, list[str]] = {p: [] for p in PASSES}
    for d in decisions:
        for stage in d["rejudge"]:
            by_pass[stage].append(d["change_key"])
    return {
        "about": (
            "Rows whose route holds a verdict that failed the quote check (RULES.md: it does not "
            "count; the row is judged again), by the pass whose verdict failed. Re-run p1 first: "
            "a new p1 'keep' ends the route there. A p2 verdict never sees p1, so a counted p2 "
            "stays valid when p1 is re-run. A tie saw both reasonings, so a row that reaches the "
            "tie again after a new p1 or p2 verdict needs a new tie too."
        ),
        **{p: sorted(keys) for p, keys in by_pass.items()},
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
            "quotes": [
                {"source": q["source"], "text": q["quote"]}
                for p in against
                for q in verdicts[p][key]["quotes"]
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


def counts(
    verdicts: Mapping[str, Mapping[str, Any]],
    checks: Mapping[str, Mapping[str, Q.VerdictCheck]],
    decisions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    reverts = [d for d in decisions if d["decision"] == REVERT]
    reversal = [d for d in decisions if d["reversal"]]
    return {
        "passes": {
            p: {
                "verdicts": len(verdicts[p]),
                "by_verdict": _sorted(Counter(v["verdict"] for v in verdicts[p].values())),
            }
            for p in PASSES
        },
        "quote_check": {
            p: {
                "checked": len(checks[p]),
                "counted": sum(c.counted for c in checks[p].values()),
                "failed": sum(not c.counted for c in checks[p].values()),
                "failed_by_reason": _sorted(
                    Counter(c.reason for c in checks[p].values() if not c.counted)
                ),
            }
            for p in PASSES
        },
        "quotes_by_outcome": {
            p: _sorted(Counter(q.outcome for c in checks[p].values() for q in c.quotes))
            for p in PASSES
        },
        "decisions": {name: sum(d["decision"] == name for d in decisions) for name in DECISIONS},
        "revert_by_column": _sorted(Counter(d["column"] for d in reverts)),
        "revert_by_superseded": {
            "false": sum(not d["superseded"] for d in reverts),
            "true": sum(bool(d["superseded"]) for d in reverts),
        },
        "rejudge_by_pass": {p: sum(p in d["rejudge"] for d in decisions) for p in PASSES},
        "rejudge_by_route_decision": _sorted(
            Counter(d["route_decision"] for d in decisions if d["decision"] == REJUDGE)
        ),
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
    """The sealed rules and input, and the verdicts - refused unless they fit the rules."""
    inputs = {
        "RULES.md": sealed(audit / "RULES.md", rules_sha256),
        "INPUT.jsonl": sealed(audit / "INPUT.jsonl", input_sha256),
        "VERDICTS_RAW.json": sha256_file(audit / "VERDICTS_RAW.json"),
    }
    rows = read_input(audit / "INPUT.jsonl")
    verdicts = read_verdicts(audit / "VERDICTS_RAW.json")
    validate(rows, verdicts)
    return rows, verdicts, inputs


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


def run(
    audit: Path,
    *,
    repo: Path = Q.REPO,
    rules_sha256: str = RULES_SHA256,
    input_sha256: str = INPUT_SHA256,
    pdf_text: Callable[[bytes], str] = Q.pdftotext,
) -> dict[str, Any]:
    """Check every quote, decide every row and write the four outputs; returns COUNTS.json."""
    rows, verdicts, inputs = load(audit, rules_sha256, input_sha256)
    library = Q.Library(repo, audit / "pages", pdf_text)
    by_key = {r["change_key"]: r for r in rows}
    checks = {
        p: {k: Q.check_verdict(v, by_key[k], library) for k, v in sorted(verdicts[p].items())}
        for p in PASSES
    }
    decisions = decide(rows, verdicts, checks)
    summary = {
        "inputs": inputs,
        "normalisation": NORMALISATION,
        **counts(verdicts, checks, decisions),
    }
    _write_jsonl(audit / "DECISIONS.jsonl", decisions)
    _write_json(audit / "COUNTS.json", summary)
    _write_json(audit / "REJUDGE.json", rejudge(decisions))
    _write_jsonl(audit / "REVERSAL_3_INPUT.jsonl", reversal_input(decisions, verdicts))
    return summary
