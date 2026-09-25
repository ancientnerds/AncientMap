"""Phase 6 acceptance, section 9: the thresholds, fixed before the draw, and the reported numbers.

**An error** is a stage-1 `WRONG` that stage 2 `CONFIRMED`, or that stage 2 left `UNDECIDED` and the
third judge `CONFIRMED` (`outcomes`). Its class is stage 1's, unless stage 2 named a lower one (the
parser only lets it name a lower one). A chain that is not finished refuses: nothing is scored on
half a run.

**Validity** (VOID unless all hold): V1 every question has a counted verdict or stands UNVERIFIABLE
after two re-asks; V2 at least 9 of the 10 canaries end CONFIRMED; V3 no journal row above the
draw's high-water mark on a drawn site. **Acceptance** (PASS only when all hold, else FAIL): A1 no
confirmed severe error in a real question; A2 at most 3 of the 60 sites carry a confirmed error in a
real question; A3 D1-D6 all hold. The canary questions never count in A1 or A2.

**Reported, not gating:** confirmed errors per field and class; UNVERIFIABLE per field and overall;
the site error rate beside the assessment's 32 of 60 (stratified, unweighted - a different
estimator, stated, not compared); stage 2's refutation rate; the canaries' recall at both stages.
Every rate carries its exact (Clopper-Pearson) 95 % interval.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from acceptance import questions as QN

CANARY_COUNT = 10
CANARY_MIN_CONFIRMED = 9
MAX_SITES_WITH_ERROR = 3
ASSESSMENT = {
    "k": 32,
    "n": 60,
    "note": "the 2026-09 assessment: 60 sites stratified by rarity_tier, unweighted - "
    "reported beside this simple random sample, not compared as the same estimator",
}


class ScoreError(ValueError):
    """The run cannot be scored yet, or its key does not fit its questions."""


# ------------------------------------------------------------------------------ Clopper-Pearson
def _pmf(i: int, n: int, p: float) -> float:
    log = (
        math.lgamma(n + 1)
        - math.lgamma(i + 1)
        - math.lgamma(n - i + 1)
        + i * math.log(p)
        + (n - i) * math.log1p(-p)
    )
    return math.exp(log)


def _cdf(k: int, n: int, p: float) -> float:
    return sum(_pmf(i, n, p) for i in range(k + 1))


def _root(f: Callable[[float], float]) -> float:
    """The p in (0, 1) where the increasing `f` crosses zero, by bisection."""
    low, high = 0.0, 1.0
    for _ in range(200):
        middle = (low + high) / 2
        if f(middle) < 0:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """The exact binomial interval: P(X >= k | lower) = alpha/2 = P(X <= k | upper)."""
    if n < 1 or not 0 <= k <= n:
        raise ValueError(f"{k} of {n} is no proportion")
    low = 0.0 if k == 0 else _root(lambda p: 1 - _cdf(k - 1, n, p) - alpha / 2)
    high = 1.0 if k == n else _root(lambda p: alpha / 2 - _cdf(k, n, p))
    return low, high


def rate(k: int, n: int) -> dict[str, Any]:
    if n == 0:
        return {"k": 0, "n": 0, "rate": None, "ci95": None}
    low, high = clopper_pearson(k, n)
    return {"k": k, "n": n, "rate": round(k / n, 6), "ci95": [round(low, 6), round(high, 6)]}


# ------------------------------------------------------------------------------ the outcomes
@dataclass(frozen=True)
class Outcome:
    """Where one stage-1 question ended."""

    label: str
    site_id: str
    field: str
    value: str
    stage1: str
    stage1_via: str
    stage2: str | None
    stage3: str | None
    confirmed: bool
    severity: str | None


def outcomes(
    questions: Sequence[QN.Question],
    stage1: Mapping[str, Mapping[str, Any]],
    stage2: Mapping[str, Mapping[str, Any]],
    stage3: Mapping[str, Mapping[str, Any]],
) -> list[Outcome]:
    """Each question's chain, from the final of each stage (`{verdict, via, answer}`)."""
    wrong = {label for label, final in stage1.items() if final["verdict"] == "WRONG"}
    stray = sorted(set(stage2) - wrong)
    if stray:
        raise ScoreError(f"stage 2 judged {stray}: not a stage-1 WRONG")
    out = []
    for q in questions:
        first = stage1.get(q.label)
        if first is None:
            raise ScoreError(f"{q.label}: stage 1 is not finished")
        second = third = None
        confirmed, severity = False, None
        if first["verdict"] == "WRONG":
            second = stage2.get(q.label)
            if second is None:
                raise ScoreError(f"{q.label}: a stage-1 WRONG that stage 2 has not finished")
            if second["verdict"] == "UNDECIDED":
                third = stage3.get(q.label)
                if third is None:
                    raise ScoreError(f"{q.label}: an UNDECIDED that stage 3 has not finished")
            confirmed = (third or second)["verdict"] == "CONFIRMED"
            if confirmed:
                lowered = second["answer"]["severity"] if second["verdict"] == "CONFIRMED" else None
                severity = lowered or first["answer"]["severity"]
        out.append(
            Outcome(
                label=q.label,
                site_id=q.site_id,
                field=q.field,
                value=q.value,
                stage1=first["verdict"],
                stage1_via=first["via"],
                stage2=None if second is None else second["verdict"],
                stage3=None if third is None else third["verdict"],
                confirmed=confirmed,
                severity=severity,
            )
        )
    return out


def canary_labels(
    questions: Sequence[QN.Question], canaries: Sequence[Mapping[str, Any]]
) -> set[str]:
    """The question each canary of the key is: its site, its field, its value as shown."""
    labels = set()
    for canary in canaries:
        field = QN.CANARY_FIELDS[str(canary["field"])]
        raw = str(canary["canary_value"])
        value = raw if field == "country" else QN.canary_point(raw)
        match = [
            q.label
            for q in questions
            if q.site_id == canary["site_id"] and q.field == field and q.value == value
        ]
        if len(match) != 1:
            raise ScoreError(f"canary {canary['site_id']}/{field} is {len(match)} questions, not 1")
        labels.add(match[0])
    return labels


# ------------------------------------------------------------------------------ the score
def score(
    results: Sequence[Outcome],
    *,
    canary_labels: set[str],
    deterministic: Mapping[str, Any],
    journal_after_draw: Sequence[Mapping[str, Any]],
    sites: int,
) -> dict[str, Any]:
    real = [o for o in results if o.label not in canary_labels]
    canary = [o for o in results if o.label in canary_labels]
    confirmed = [o for o in real if o.confirmed]
    severe = [o for o in confirmed if o.severity == "severe"]
    error_sites = sorted({o.site_id for o in confirmed})
    canaries_confirmed = sum(o.confirmed for o in canary)
    finished = all(
        o.stage1_via == "counted" or (o.stage1_via == "exhausted" and o.stage1 == "UNVERIFIABLE")
        for o in results
    )
    validity = {
        "V1": {
            "holds": finished,
            "counted": sum(o.stage1_via == "counted" for o in results),
            "unverifiable_after_reasks": sum(o.stage1_via == "exhausted" for o in results),
        },
        "V2": {
            "holds": len(canary) == CANARY_COUNT and canaries_confirmed >= CANARY_MIN_CONFIRMED,
            "confirmed": canaries_confirmed,
            "canaries": len(canary),
            "needed": CANARY_MIN_CONFIRMED,
        },
        "V3": {"holds": not journal_after_draw, "rows": list(journal_after_draw)},
    }
    validity["valid"] = all(validity[v]["holds"] for v in ("V1", "V2", "V3"))
    acceptance = {
        "A1": {"holds": not severe, "severe": len(severe), "labels": [o.label for o in severe]},
        "A2": {
            "holds": len(error_sites) <= MAX_SITES_WITH_ERROR,
            "sites": len(error_sites),
            "site_ids": error_sites,
            "allowed": MAX_SITES_WITH_ERROR,
        },
        "A3": {"holds": deterministic["all_hold"] is True},
    }
    if not validity["valid"]:
        verdict = "VOID"
    elif all(acceptance[a]["holds"] for a in ("A1", "A2", "A3")):
        verdict = "PASS"
    else:
        verdict = "FAIL"
    return {
        "outcome": verdict,
        "questions": {"total": len(results), "real": len(real), "canary": len(canary)},
        "validity": validity,
        "acceptance": acceptance,
        "reported": _reported(real, canary, confirmed, error_sites, sites),
        "errors": [
            {"label": o.label, "site_id": o.site_id, "field": o.field, "severity": o.severity}
            for o in confirmed
        ],
    }


def _reported(
    real: Sequence[Outcome],
    canary: Sequence[Outcome],
    confirmed: Sequence[Outcome],
    error_sites: Sequence[str],
    sites: int,
) -> dict[str, Any]:
    by_field: dict[str, Counter[str]] = {}
    for o in confirmed:
        by_field.setdefault(o.field, Counter())[str(o.severity)] += 1
    unverifiable = {
        field.key: rate(
            sum(o.stage1 == "UNVERIFIABLE" for o in real if o.field == field.key),
            sum(o.field == field.key for o in real),
        )
        for field in QN.FIELDS
    }
    unverifiable["overall"] = rate(sum(o.stage1 == "UNVERIFIABLE" for o in real), len(real))
    judged = [o for o in (*real, *canary) if o.stage2 is not None]
    real_judged = [o for o in real if o.stage2 is not None]
    flagged = [o for o in canary if o.stage1 == "WRONG"]
    return {
        "confirmed_errors": {
            field: dict(sorted(c.items())) for field, c in sorted(by_field.items())
        },
        "unverifiable": unverifiable,
        "site_error_rate": {**rate(len(error_sites), sites), "assessment": ASSESSMENT},
        "stage2_refutation": {
            "all": {"refuted": sum(o.stage2 == "REFUTED" for o in judged), "stage2": len(judged)},
            "real": {
                "refuted": sum(o.stage2 == "REFUTED" for o in real_judged),
                "stage2": len(real_judged),
            },
        },
        "canaries": {
            "stage1_recall": {"k": len(flagged), "n": len(canary)},
            "stage2_recall": {"k": sum(o.confirmed for o in canary), "n": len(canary)},
            "confirmed_of_flagged": {
                "k": sum(o.confirmed for o in flagged),
                "n": len(flagged),
            },
        },
    }


def markdown(result: Mapping[str, Any]) -> str:
    """RESULT.md: the outcome and every number of section 9, for a reader."""
    v, a, r = result["validity"], result["acceptance"], result["reported"]
    q = result["questions"]
    lines = [
        f"# Phase 6 acceptance - {result['draw']}: **{result['outcome']}**",
        "",
        f"Questions: {q['total']} ({q['real']} real, {q['canary']} canary). "
        f"Written {result['written_at']}.",
        "",
        "| check | holds | detail |",
        "|---|---|---|",
        f"| V1 every question has a counted verdict | {v['V1']['holds']} | "
        f"{v['V1']['counted']} counted, {v['V1']['unverifiable_after_reasks']} UNVERIFIABLE "
        "after two re-asks |",
        f"| V2 at least 9 of 10 canaries CONFIRMED | {v['V2']['holds']} | "
        f"{v['V2']['confirmed']} of {v['V2']['canaries']} |",
        f"| V3 no write on a drawn site after the draw | {v['V3']['holds']} | "
        f"{len(v['V3']['rows'])} journal rows |",
        f"| A1 0 confirmed severe errors | {a['A1']['holds']} | {a['A1']['severe']} |",
        f"| A2 at most 3 of the sites with an error | {a['A2']['holds']} | {a['A2']['sites']} |",
        f"| A3 D1-D6 hold | {a['A3']['holds']} | DETERMINISTIC.json |",
        "",
        "## Reported, not gating",
        "",
        f"- Site error rate: {_fmt(r['site_error_rate'])}; the assessment: 32 of 60 (53 %), "
        "stratified and unweighted - beside, not compared.",
        f"- UNVERIFIABLE overall: {_fmt(r['unverifiable']['overall'])}.",
        f"- Stage 2 refuted {r['stage2_refutation']['all']['refuted']} of "
        f"{r['stage2_refutation']['all']['stage2']} flags "
        f"({r['stage2_refutation']['real']['refuted']} of "
        f"{r['stage2_refutation']['real']['stage2']} real).",
        f"- Canaries: stage 1 flagged {r['canaries']['stage1_recall']['k']} of "
        f"{r['canaries']['stage1_recall']['n']}, confirmed {r['canaries']['stage2_recall']['k']}.",
        "",
        "| field | UNVERIFIABLE | confirmed errors |",
        "|---|---|---|",
    ]
    for field in QN.FIELDS:
        errors = r["confirmed_errors"].get(field.key, {})
        shown = ", ".join(f"{s} {n}" for s, n in errors.items()) or "0"
        lines.append(
            f"| {field.number} {field.title} | {_fmt(r['unverifiable'][field.key])} | {shown} |"
        )
    return "\n".join(lines) + "\n"


def _fmt(value: Mapping[str, Any]) -> str:
    if value["rate"] is None:
        return "no questions"
    low, high = value["ci95"]
    return f"{value['k']} of {value['n']} ({value['rate']:.1%}, 95 % CI {low:.1%}-{high:.1%})"
