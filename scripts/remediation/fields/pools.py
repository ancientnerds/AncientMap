"""Lane wd5: the calibration pools of the field researcher and the adversarial checker (D6, 2026-10-08).

Owner decision D6: every role passes a calibration against already-judged cases, with the threshold
sealed before the run (`calibrate_claude.py`); a failing role moves up one tier. The map for the
fields workstream (`output/remediation/final-2026-10-08/plans/fields.md`, "Calibration") names three
pools, built here from the run tree. Each is a directory `<out>/handoff` (the questions, with the
answers where the gold is an answer) and `<out>/run` (the source run that registers the round, which
`calibrate_claude.py prepare --run` copies from):

* **general** - role `field_researcher` on **60 sites** of WD1's round 0, stratified by field: the
  sites whose every asked field was decided on a counted answer in round 0 (two quotes of two source
  families), the question and the recorded answer copied byte for byte. The agent re-answers under
  WD1's own rule and prompt; gold is the recorded answer. Compared unit by unit on the cells both
  decide (a point within 1 km, a start in the same bucket, the same type, the same page), with the
  share of cells nobody decided - `clear` and `unresolved` - bounded above the gold's.
* **bp** - role `field_researcher` on **about 25 sites** whose earlier agents named an age in years
  before the present and so lost the answer to a reader that could not read it: the six sites the
  30-site audit confirmed in the band "< 4500 BC" (Le Moustier, Bruniquel, Cro-Magnon, Apidima,
  Boxgrove, Lake Mungo), one bucket-edge case (a number whose tolerance reaches 6,450 BP) and a seeded
  fill of sites whose earlier reasoning dated them in one bucket. The question is wd5's (the BP
  reader is taught in it). Gold is a truth file: the buckets the earlier reasoning stated, with the
  basis of each (`audit-confirmed`, `earlier-reasoning`, `edge`); it is not an answer, so no recorded
  answer is faked. A site passes when the fresh answer is counted - its quote found in its page at
  import - and lies in an accepted bucket; an unresolved answer is a miss.
* **adversarial** - role `adversarial` on **40 cells** of `opus_audit/DECISIONS.jsonl`, 20 `keep` and
  20 `revert` (half period, half type), asked in the form of the wd5 check (`adversarial.py`): keep
  is `confirm`, revert is `reject`. It is Opus judging what Opus judged, so it measures stability
  and the share of `unclear` answers, not truth.

    pools.py build-general     --out DIR --seed N
    pools.py build-bp          --out DIR --seed N
    pools.py build-adversarial --out DIR --seed N
    pools.py prepare --id ID --run DIR/run     calibrate_claude prepare + what the pool's tools read
    pools.py compare --id ID                   the comparison the seal names
    pools.py audit-quotes --id ID              the quotes to spot-check for false sources (O18)

The seal itself is `calibrate_claude.py seal`, with the arguments each build prints.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

import calibrate_claude as CC  # noqa: E402
import mcode_driver as D  # noqa: E402
import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402
from acceptance.answers import AnswerError  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

from fields import adversarial as AD  # noqa: E402
from fields import answers as A  # noqa: E402
from fields import classify as C  # noqa: E402
from fields import handoff as HO  # noqa: E402
from fields import harvest as H  # noqa: E402
from fields import population as POP  # noqa: E402
from fields import rule as R  # noqa: E402

POOLS_ROOT = CC.CALIBRATION_ROOT / "pools"
AUDIT_DIR = D.REPO / "output" / "remediation" / "opus_audit"
GENERAL_SIZE = 60
BP_SIZE = 25
ADV_PER_CLASS = 20
#: The sealed thresholds of the map: at least 90 % agreement on the cells both sides decide, no false
#: source (`calibrate_claude.MAX_FALSE_SOURCES`), the fresh share of undecided cells at most 10
#: points above the gold's.
THRESHOLD = 0.9
MAX_UNDECIDED_EXCESS = 0.10
COMPARISON_DECIDED, COMPARISON_BP, COMPARISON_ADV = "fields-decided", "bp-bucket", "adv-truth"
GENERAL_STAGE = "frg"
#: The model the BP pool's round is exported for: the registry's, so the brief names it.
RESEARCHER_MODEL = RO.role("field_researcher").model
TRUTH_FILE = "TRUTH.json"
STRATA_FILE = "STRATA.json"
#: What an answer that decides nothing is called in each pool's answers.
UNDECIDED = frozenset({A.UNRESOLVED, A.CLEAR, HO.HELD, AD.UNCLEAR})
#: The sites the 30-site audit confirmed in the band "< 4500 BC" (map, "Same role, BP set").
NAMED_BP_SITES = (
    "Le Moustier",
    "Bruniquel",
    "Cro-Magnon",
    "Apidima",
    "Boxgrove",
    "Lake Mungo",
)
FIRST_BUCKET = "< 4500 BC"
AUDIT_CONFIRMED = "audit-confirmed"
EARLIER_REASONING = "earlier-reasoning"
EDGE = "edge"
#: An earlier agent's reasoning that says the BP age was the obstacle ("which is not read", "cannot
#: be read as a year"), and one that says the sources disagree - a date the sites' own reasoning
#: does not settle is no gold.
UNREADABLE = re.compile(
    r"not read|cannot be read|can't be read|unreadable|not a year|does not read|not readable|"
    r"readable (?:year|form|page)|cannot be (?:stated|quoted)",
    re.I,
)
DISPUTED = re.compile(r"disagree|inconsistent|conflict|contradict|loose|disputed", re.I)
BP_MENTION = re.compile(
    r"years? ago|\bBP\b|\bka\b|\bkya\b|\bMa\b|\bmya\b|before present", re.I
)  # the same words the BP reader reads
LATER_RUNS = POP.HISTORY_RUNS


class PoolError(ValueError):
    """The pool cannot be built from these records. Nothing is half-written: `out` is empty or
    refused up front."""


def _need_empty(out: Path) -> None:
    if out.exists() and any(out.iterdir()):
        raise PoolError(f"{out} is not empty: a pool is built once, in a directory of its own")


def _seal_command(
    out: Path, *, role: str, batches: Sequence[str], comparison: str, truth: bool, kind: str
) -> str:
    """The `calibrate_claude.py seal` command of a built pool, as the operator runs it."""
    parts = [
        "./.venv/Scripts/python.exe scripts/remediation/calibrate_claude.py seal",
        f"--id {kind}-001 --role {role}",
        f"--handoff {HO._shown(out / 'handoff')}",
        f"--batches {' '.join(batches)}",
        f"--threshold {THRESHOLD}",
        f"--max-undecided-excess {MAX_UNDECIDED_EXCESS}" if comparison != COMPARISON_BP else "",
        f"--comparison {comparison}",
        f"--truth {HO._shown(out / TRUTH_FILE)}" if truth else "",
    ]
    return " ".join(p for p in parts if p)


# ------------------------------------------------------------------------------ the general pool
@dataclass(frozen=True)
class Eligible:
    """A WD1 site whose round-0 answer is gold: where its question and answer live."""

    site: str
    run: Path
    batch: str
    handoff: Path
    fields: tuple[str, ...]
    line: Mapping[str, Any]


def _answer_stamp_problem(path: Path) -> str | None:
    stamp = json.loads(path.read_text(encoding="utf-8")).get("model")
    if stamp == OH.MINIMAX_MODEL:
        return "answered by MiniMax - never ground truth (D10)"
    if stamp not in OH.ANSWER_MODELS.values():
        return f"carries no stamp of ANSWER_MODELS ({stamp!r})"
    return None


def recorded_handoff(round_record: Mapping[str, Any], fields_dir: Path) -> Path:
    """The handoff directory a round recorded: a path relative to the checkout that ran it, which is
    the checkout `fields_dir` belongs to (`<checkout>/output/remediation/fields`) - the run tree of
    the main checkout is read from a worktree too."""
    recorded = Path(round_record["handoff"])
    return recorded if recorded.is_absolute() else fields_dir.parents[2] / recorded


def wd1_eligible(fields_dir: Path) -> dict[str, Eligible]:
    """The WD1 sites whose every asked field was decided on a counted answer in round 0 (two quotes
    of two source families, found in their pages), by a Claude agent. Their round-0 question and
    answer are the pool's gold; a field decided only after a re-ask has a question that differs from
    the round-0 one and is left out."""
    eligible: dict[str, Eligible] = {}
    for name in POP.WD1_RUN_NAMES:
        run = fields_dir / name
        rounds = HO.read_rounds(run)
        if not rounds or rounds[0]["round"] != 0:
            raise PoolError(f"{run} has no round 0")
        round0 = rounds[0]
        decisions = {(d["site_id"], d["field"]): d for d in HO._read_jsonl(run / HO.DECISIONS_FILE)}
        classified = HO.read_classified(run)
        handoff = recorded_handoff(round0, fields_dir)
        for batch, labels in round0["batches"].items():
            for label in labels:
                fields = tuple(round0["fields"][label])
                # a decision of round 0 is a counted one: exhaustion comes after round 2
                counted = all(
                    (d := decisions.get((label, f))) is not None and d["round"] == 0 for f in fields
                )
                path = handoff / batch / HO.STAGE / f"{label}{OH.ANSWER_SUFFIX}"
                if counted and path.exists() and _answer_stamp_problem(path) is None:
                    eligible[label] = Eligible(
                        label, run, batch, handoff, fields, classified[label]
                    )
    return eligible


def stratify(eligible: Mapping[str, Eligible], size: int, rng: random.Random) -> dict[str, str]:
    """`{site: the field it was drawn for}`: round-robin over the fields in `C.FIELDS` order, each
    draw a seeded random eligible site that asks the field and was not drawn yet, until `size` sites
    are chosen (a field with no sites left gives its turn to the others)."""
    lines = {
        field: sorted(s for s, e in eligible.items() if field in e.fields) for field in C.FIELDS
    }
    for sites in lines.values():
        rng.shuffle(sites)
    picked: dict[str, str] = {}
    while len(picked) < size and any(lines.values()):
        for field in C.FIELDS:
            while lines[field] and lines[field][-1] in picked:
                lines[field].pop()
            if lines[field] and len(picked) < size:
                picked[lines[field].pop()] = field
    if len(picked) < size:
        raise PoolError(f"only {len(picked)} WD1 sites are eligible, {size} are wanted")
    return picked


def build_general(
    out: Path, *, seed: int, size: int = GENERAL_SIZE, fields_dir: Path = POP.FIELDS_DIR
) -> dict[str, Any]:
    """`<out>/handoff` (batches of 8 sites by country and name, each question and its recorded answer
    byte for byte), `<out>/run` (RUN.json under WD1's rule, CLASSIFIED.jsonl, ROUNDS.jsonl)."""
    _need_empty(out)
    eligible = wd1_eligible(fields_dir)
    picked = stratify(eligible, size, random.Random(seed))  # noqa: S311 - a seeded, recorded draw
    classified = {s: dict(eligible[s].line) for s in picked}
    groups = HO.batches(sorted(picked), classified, 0, GENERAL_STAGE)
    handoff, run = out / "handoff", out / "run"
    for batch_id, labels in groups:
        for label in labels:
            e = eligible[label]
            stage = e.handoff / e.batch / HO.STAGE
            prompt = (stage / f"{label}{OH.PROMPT_SUFFIX}").read_bytes().decode("utf-8")
            OH.export(
                handoff, batch_id=batch_id, stage=HO.STAGE, label=label, field="+".join(e.fields),
                prompt=prompt,
            )  # fmt: skip
            shutil.copyfile(
                stage / f"{label}{OH.ANSWER_SUFFIX}",
                handoff / batch_id / HO.STAGE / f"{label}{OH.ANSWER_SUFFIX}",
            )
    check = OH.validate(handoff)
    if not check.ok:
        raise PoolError(f"the copied pool does not validate: {check.to_dict()}")
    R.write_run(run, R.TWO_FAMILIES, built_from={"pool": GENERAL_STAGE, "seed": seed})
    HO._write_jsonl(run / C.CLASSIFIED_FILE, [classified[s] for s in sorted(picked)])
    HO._write_jsonl(
        run / HO.ROUNDS_FILE,
        [
            {
                "round": 0, "handoff": HO._shown(handoff), "model": None, "batches": dict(groups),
                "fields": {s: list(eligible[s].fields) for s in sorted(picked)}, "notes": {},
                "exported_at": H.now(),
            }
        ],
    )  # fmt: skip
    strata = Counter(picked.values())
    HO._write_json(
        run / STRATA_FILE,
        {
            "seed": seed,
            "size": size,
            "drawn_for": dict(sorted(strata.items())),
            "asked_fields": dict(
                sorted(Counter(f for s in picked for f in eligible[s].fields).items())
            ),
            "sites": {s: {"for": picked[s], "run": HO._shown(eligible[s].run),
                          "batch": eligible[s].batch} for s in sorted(picked)},
        },
    )  # fmt: skip
    batches = [b for b, _ in groups]
    return {
        "pool": GENERAL_STAGE,
        "sites": len(picked),
        "batches": batches,
        "drawn_for": dict(sorted(strata.items())),
        "seal": _seal_command(
            out, role="field_researcher", batches=batches, comparison=COMPARISON_DECIDED,
            truth=False, kind="fr-general",
        ),
    }  # fmt: skip


# ------------------------------------------------------------------------------ the BP pool
@dataclass(frozen=True)
class BpCandidate:
    """A site whose earlier reasoning named an age in years before the present."""

    site: str
    name: str
    line: Mapping[str, Any]
    reasonings: tuple[str, ...]
    ages: tuple[int, ...]
    buckets: frozenset[str]
    edge: bool
    clean: bool

    @property
    def snippet(self) -> str:
        return self.reasonings[-1][:300]


def bp_buckets(texts: Sequence[str]) -> tuple[frozenset[str], tuple[int, ...], bool]:
    """The buckets the BP ages of some reasonings reach, the ages (years before the present), and
    whether one age's tolerance reaches the first bucket's edge (6,450 BP, 4500 BC): each age states
    a year within `bp_dates`' tolerance, so a number near that edge lies in two buckets. A number
    that is near any other bucket's edge is simply ambiguous, and no gold."""
    buckets: set[str] = set()
    ages: list[int] = []
    edge = False
    for text in texts:
        for year, tolerance in A.bp_dates(text):
            ages.append(A.BP_PRESENT - year)
            reached = {C.bucket(year - tolerance), C.bucket(year), C.bucket(year + tolerance)}
            buckets |= reached
            edge = edge or (FIRST_BUCKET in reached and len(reached) > 1)
    return frozenset(buckets), tuple(ages), edge


def bp_candidates(fields_dir: Path) -> dict[str, BpCandidate]:
    """The sites a WD1, WD3 or WD4 agent left without a period for want of the BP reader, whose
    latest classification (WD4, WD3, its pilot) asked the period: `period_start` ended `clear`,
    `unresolved` or `held` and an answer's reasoning names an age in years before the present."""
    reasonings: dict[str, list[str]] = {}
    final: dict[str, str] = {}
    names: dict[str, str] = {}
    for name in (*POP.WD1_RUN_NAMES, *LATER_RUNS):
        run = fields_dir / name
        for d in HO._read_jsonl(run / HO.DECISIONS_FILE):
            if d["field"] == "period_start":
                final[d["site_id"]], names[d["site_id"]] = d["decision"], d["name"]
        for a in HO._read_jsonl(run / HO.ATTEMPTS_FILE):
            text = (a["answer"] or {}).get("reasoning") if a["field"] == "period_start" else None
            if text and BP_MENTION.search(text):
                reasonings.setdefault(a["site_id"], []).append(text)
    lines: dict[str, Mapping[str, Any]] = {}
    for name in LATER_RUNS:  # the latest classification wins
        for line in HO._read_jsonl(fields_dir / name / C.CLASSIFIED_FILE):
            if "period_start" in line["asked"]:
                lines[line["site_id"]] = line
    out: dict[str, BpCandidate] = {}
    for site, texts in reasonings.items():
        if final.get(site) not in (A.CLEAR, A.UNRESOLVED, HO.HELD) or site not in lines:
            continue
        buckets, ages, edge = bp_buckets(texts)
        stated = [t for t in texts if A.bp_dates(t)]
        clean = (
            bool(buckets)
            and (len(buckets) == 1 or (edge and len(buckets) == 2))
            and any(UNREADABLE.search(t) for t in stated)
            and not any(DISPUTED.search(t) for t in stated)
        )
        out[site] = BpCandidate(site, names[site], lines[site], tuple(texts), ages, buckets, edge,
                                clean)  # fmt: skip
    return out


def pick_bp(
    candidates: Mapping[str, BpCandidate], size: int, rng: random.Random
) -> dict[str, tuple[str, frozenset[str]]]:
    """`{site: (basis, accepted buckets)}`: the named sites (audit-confirmed in the first bucket), one
    edge case (both buckets its tolerance reaches), and a seeded fill of clean candidates."""
    picked: dict[str, tuple[str, frozenset[str]]] = {}
    for word in NAMED_BP_SITES:
        found = sorted(c.site for c in candidates.values() if word.casefold() in c.name.casefold())
        if not found:
            raise PoolError(f"{word}: no candidate with that name - the audit's site is missing")
        for site in found[:1]:
            picked[site] = (AUDIT_CONFIRMED, frozenset({FIRST_BUCKET}))
    edges = sorted(
        c.site for c in candidates.values() if c.edge and c.clean and c.site not in picked
    )
    if not edges:
        raise PoolError("no clean bucket-edge case among the candidates")
    rng.shuffle(edges)
    picked[edges[0]] = (EDGE, candidates[edges[0]].buckets)
    rest = sorted(c.site for c in candidates.values() if c.clean and c.site not in picked)
    rng.shuffle(rest)
    for site in rest:
        if len(picked) >= size:
            break
        picked[site] = (EARLIER_REASONING, candidates[site].buckets)
    if len(picked) < size:
        raise PoolError(f"only {len(picked)} clean BP candidates, {size} are wanted")
    return picked


def build_bp(
    out: Path, *, seed: int, size: int = BP_SIZE, fields_dir: Path = POP.FIELDS_DIR
) -> dict[str, Any]:
    """`<out>/handoff` (wd5's question per site, its `period_start` alone, no answer), `<out>/run`
    (a wd5 run of those sites) and `<out>/TRUTH.json` (`{site: {expected, basis, ...}}`)."""
    _need_empty(out)
    candidates = bp_candidates(fields_dir)
    picked = pick_bp(candidates, size, random.Random(seed))  # noqa: S311 - a seeded, recorded draw
    run, handoff = out / "run", out / "handoff"
    R.write_run(run, R.RECHECK, built_from={"pool": "bp", "seed": seed})
    lines = []
    for site in sorted(picked):
        line = dict(candidates[site].line)
        line["asked"] = ["period_start"]
        line["open"] = {"period_start": line["open"]["period_start"]}
        lines.append(line)
    HO._write_jsonl(run / C.CLASSIFIED_FILE, lines)
    result = HO.export(run, handoff, RESEARCHER_MODEL)
    truth = {
        site: {
            "name": candidates[site].name,
            "expected": sorted(buckets),
            "basis": basis,
            "ages_bp": list(candidates[site].ages),
            "evidence": candidates[site].snippet,
        }
        for site, (basis, buckets) in sorted(picked.items())
    }
    HO._write_json(out / TRUTH_FILE, truth)
    batches = list(HO.read_rounds(run)[0]["batches"])
    return {
        "pool": "bp",
        "sites": len(picked),
        "batches": batches,
        "basis": dict(sorted(Counter(b for b, _ in picked.values()).items())),
        "export": result,
        "seal": _seal_command(
            out, role="field_researcher", batches=batches, comparison=COMPARISON_BP,
            truth=True, kind="fr-bp",
        ),
    }  # fmt: skip


# ------------------------------------------------------------------------------ the adversarial pool
def audit_candidates(audit_dir: Path) -> list[dict[str, Any]]:
    """The audit's decided, not superseded `keep` and `revert` rows of the two columns wd5 writes,
    each joined to its input row (the finder's quote and evidence files)."""
    inputs = {r["change_key"]: r for r in HO._read_jsonl(audit_dir / "INPUT.jsonl")}
    rows = []
    for d in HO._read_jsonl(audit_dir / "DECISIONS.jsonl"):
        row = inputs.get(d["change_key"])
        if (
            row is not None
            and not d["superseded"]
            and d["decision"] in ("keep", "revert")
            and d["column"] in ("period_start", "site_type")
            and row["finder_quote"]
            and row["evidence_files"]
            and row["written_value"]
        ):
            rows.append({**row, "audit": d["decision"]})
    return sorted(rows, key=lambda r: r["change_key"])


def audit_cell(row: Mapping[str, Any], repo: Path) -> dict[str, Any]:
    """The frozen check question of one audit row, in the wd5 form: the written value is the
    decision under check, the finder's quote the quote, the evidence file the page. A row whose quote
    is in none of its evidence files is refused (`AdversarialError`)."""
    library = Q.Library(repo, repo / "output" / "remediation" / "_no_pages")
    quotes = []
    for found in row["finder_quote"]:
        for rel in row["evidence_files"]:
            try:
                quote = AD.quote_packet({"source": rel, "quote": found["quote"]}, library)
            except AD.AdversarialError:
                continue
            quotes.append({**quote, "url": found["url"]})
            break
    if not quotes:
        raise AD.AdversarialError(f"{row['change_key']}: no finder quote in its evidence files")
    return {
        "cell": AD.cell_id(row["site_id"], row["column"]),
        "site_id": row["site_id"],
        "field": row["column"],
        "name": row["site_name"],
        "country": row["country_now"],
        "stored_point": None,
        "qid": None,
        "enwiki": None,
        "stored": row["old_value"],
        "decision": "replace",
        "value": row["written_value"],
        "via": "audit",
        "round": 0,
        "answered_by": "the Phase 3 finder",
        "model": None,
        "why_open": None,
        "made": None,
        "reasoning": str(row["reviewer_reason"])[: AD.REASONING_SHOWN],
        "value_page": None,
        "quotes": quotes,
        "wiki": None,
    }


def build_adversarial(
    out: Path,
    *,
    seed: int,
    per_class: int = ADV_PER_CLASS,
    audit_dir: Path = AUDIT_DIR,
    repo: Path = D.REPO,
) -> dict[str, Any]:
    """`<out>/handoff` (the check question per audit cell), `<out>/run` (CELLS.json, ROUNDS.jsonl, a
    wd5 RUN.json) and `<out>/TRUTH.json` (`{cell: {expected: confirm|reject, ...}}`): `per_class`
    keeps and `per_class` reverts, half of each from each column."""
    if per_class % 2:
        raise PoolError(f"{per_class} cells per class do not split in two columns")
    _need_empty(out)
    rng = random.Random(seed)  # noqa: S311 - a seeded, recorded draw
    rows = audit_candidates(audit_dir)
    chosen: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for verdict in ("keep", "revert"):
        for column in ("period_start", "site_type"):
            pool = [r for r in rows if r["audit"] == verdict and r["column"] == column]
            rng.shuffle(pool)
            taken = 0
            for row in pool:
                if taken == per_class // 2:
                    break
                try:
                    chosen.append((row, audit_cell(row, repo)))
                except AD.AdversarialError:
                    continue
                taken += 1
            if taken < per_class // 2:
                raise PoolError(
                    f"only {taken} usable {verdict} rows of {column}, {per_class // 2} wanted"
                )
    run, handoff = out / "run", out / "handoff"
    R.write_run(run, R.RECHECK, built_from={"pool": "adversarial", "seed": seed})
    (run / C.CLASSIFIED_FILE).write_text("", encoding="utf-8", newline="\n")
    cells = sorted((cell for _, cell in chosen), key=lambda c: c["cell"])
    HO._write_json(run / AD.CELLS_FILE, {"seed": seed, "cells": cells})
    AD._export_round(run, handoff, 0, [c["cell"] for c in cells], {})
    truth = {
        cell["cell"]: {
            "expected": AD.CONFIRM if row["audit"] == "keep" else AD.REJECT,
            "audit_decision": row["audit"],
            "change_key": row["change_key"],
            "column": row["column"],
            "name": row["site_name"],
        }
        for row, cell in chosen
    }
    HO._write_json(out / TRUTH_FILE, truth)
    batches = list(AD.read_rounds(run)[0]["batches"])
    return {
        "pool": "adversarial",
        "cells": len(cells),
        "expected": dict(sorted(Counter(t["expected"] for t in truth.values()).items())),
        "batches": batches,
        "seal": _seal_command(
            out, role="adversarial", batches=batches, comparison=COMPARISON_ADV, truth=True,
            kind="adv",
        ),
    }  # fmt: skip


# ------------------------------------------------------------------------------ the comparisons
def _unit_verdicts(text: str) -> dict[str, str] | None:
    pairs = D._verdicts(text)
    return None if pairs is None else dict(pairs)


def _word(verdict: str) -> str:
    return verdict.split(":", 1)[0]


def _point(value: str) -> tuple[float, float]:
    lat, lon = value.split(",")
    return float(lat), float(lon)


def units_equal(field: str, old: str, new: str) -> bool:
    """Whether two verdicts of one cell are the same decision: the same word, and - for a replace -
    the same value in the terms the database keeps it: a point within `KEEP_KM` of the other, a start
    in the same bucket, the same type, the same page."""
    if _word(old) != _word(new):
        return False
    if _word(old) != A.REPLACE:
        return True
    left, right = old.split(": ", 1)[1], new.split(": ", 1)[1]
    if field == "coordinates":
        return A._km(_point(left), _point(right)) <= A.KEEP_KM
    if field == "period_start":
        return C.bucket(int(left)) == C.bucket(int(right))
    if field == "source_url":
        return C.same_page(left, right)
    return left.casefold() == right.casefold()


def _report(
    role: str, labels: Sequence[str], units: int, agreed: int, unanswered: Sequence[str],
    disagreements: Sequence[Mapping[str, Any]], **extra: Any,
) -> dict[str, Any]:  # fmt: skip
    return {
        "lane": role,
        "labels": list(labels),
        "units": units,
        "agreed": agreed,
        "agreement": round(agreed / units, 4) if units else 0.0,
        "unanswered": list(unanswered),
        "disagreements": list(disagreements),
        **extra,
    }


def _disagreement(
    label: str, unit: str, recorded: str, fresh: str, fresh_text: str
) -> dict[str, Any]:
    return {
        "label": label,
        "unit": unit,
        "recorded": recorded,
        "fresh": fresh,
        "recorded_sources": [],
        "fresh_sources": list(D._sources(fresh_text)),
    }


def compare_decided(
    sealed: dict[str, Any], recorded: dict[str, str], fresh: dict[str, str], out: Path
) -> dict[str, Any]:
    """The map's comparison for an answered pool: agreement on the cells both sides decide, and the
    fresh share of cells nobody decided less the gold's."""
    units = agreed = gold_units = gold_undecided = fresh_units = fresh_undecided = 0
    unanswered: list[str] = []
    disagreements: list[dict[str, Any]] = []
    for label in sorted(recorded):
        old = _unit_verdicts(recorded[label])
        new = None if label not in fresh else _unit_verdicts(fresh[label])
        if old is None or new is None:
            unanswered.append(label)
            continue
        gold_units += len(old)
        gold_undecided += sum(_word(v) in UNDECIDED for v in old.values())
        fresh_units += len(new)
        fresh_undecided += sum(_word(v) in UNDECIDED for v in new.values())
        for unit, verdict in new.items():
            gold = old.get(unit)
            if gold is None or _word(gold) in UNDECIDED or _word(verdict) in UNDECIDED:
                continue
            units += 1
            if units_equal(unit, gold, verdict):
                agreed += 1
            else:
                disagreements.append(_disagreement(label, unit, gold, verdict, fresh[label]))
    gold_rate = gold_undecided / gold_units if gold_units else 0.0
    fresh_rate = fresh_undecided / fresh_units if fresh_units else 0.0
    return _report(
        sealed["role"], sorted(recorded), units, agreed, unanswered, disagreements,
        undecided={"gold": round(gold_rate, 4), "fresh": round(fresh_rate, 4),
                   "gold_units": gold_units, "fresh_units": fresh_units},
        undecided_excess=round(fresh_rate - gold_rate, 4),
    )  # fmt: skip


def _truth(sealed: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(Path(sealed["truth"]).read_text(encoding="utf-8"))


def bp_miss(attempt: Mapping[str, Any], expected: set[str]) -> str | None:
    """Why an imported attempt is not a hit of the BP pool, or `None`: a hit is a replace or keep
    whose quote the importer found in its page and whose value lies in an accepted bucket."""
    answer = attempt["answer"]
    if answer is None:
        return f"not in shape: {attempt['problem']}"
    if answer["decision"] not in (A.REPLACE, A.KEEP):
        return str(answer["decision"])
    if not attempt["counted"]:
        return f"{answer['decision']} {answer['value']}: not counted ({attempt['reason']})"
    bucket = C.bucket(int(answer["value"]))
    return None if bucket in expected else f"{answer['decision']} {answer['value']}: {bucket}"


def compare_bp(
    sealed: dict[str, Any], recorded: dict[str, str], fresh: dict[str, str], out: Path
) -> dict[str, Any]:
    """The BP pool: a site passes when its fresh answer counted (the quote found in its page when the
    calibration run was imported) and its value lies in an accepted bucket. Needs
    `handoff.py import --run <calibration run>` first. An unresolved answer is a miss."""
    truth = _truth(sealed)
    attempts_file = D.calibration_run(out) / HO.ATTEMPTS_FILE
    if not attempts_file.exists():
        raise CC.CalibrationError(
            f"{attempts_file} is missing: import the calibration run first "
            f"(handoff.py import --run {HO._shown(D.calibration_run(out))})"
        )
    attempts = {
        a["site_id"]: a for a in HO._read_jsonl(attempts_file) if a["field"] == "period_start"
    }
    agreed = 0
    unanswered: list[str] = []
    disagreements: list[dict[str, Any]] = []
    by_basis: Counter[str] = Counter()
    for site in sorted(truth):
        attempt = attempts.get(site)
        if site not in fresh or attempt is None:
            unanswered.append(site)
            continue
        expected = set(truth[site]["expected"])
        miss = bp_miss(attempt, expected)
        if miss is None:
            agreed += 1
            by_basis[truth[site]["basis"]] += 1
        else:
            disagreements.append(
                _disagreement(
                    site, "period_start", " or ".join(sorted(expected)), miss, fresh[site]
                )
            )
    units = len(truth) - len(unanswered)
    return _report(
        sealed["role"], sorted(truth), units, agreed, unanswered, disagreements,
        agreed_by_basis=dict(sorted(by_basis.items())),
    )  # fmt: skip


def compare_adv(
    sealed: dict[str, Any], recorded: dict[str, str], fresh: dict[str, str], out: Path
) -> dict[str, Any]:
    """The adversarial pool: confirm against the audit's keep, reject against its revert, on the
    cells the fresh answer decides; an `unclear` (or an answer not in shape) decides nothing and is
    counted in the undecided rate, whose gold is 0."""
    truth = _truth(sealed)
    units = agreed = undecided = 0
    unanswered: list[str] = []
    disagreements: list[dict[str, Any]] = []
    for cell in sorted(truth):
        if cell not in fresh:
            unanswered.append(cell)
            continue
        try:
            verdict = AD.parse_answer(fresh[cell], cell.rsplit(".", 1)[1])[0]
        except AnswerError:
            verdict = AD.UNCLEAR
        if verdict == AD.UNCLEAR:
            undecided += 1
            continue
        units += 1
        if verdict == truth[cell]["expected"]:
            agreed += 1
        else:
            disagreements.append(
                _disagreement(cell, "verdict", truth[cell]["expected"], verdict, fresh[cell])
            )
    answered = len(truth) - len(unanswered)
    rate = undecided / answered if answered else 0.0
    return _report(
        sealed["role"], sorted(truth), units, agreed, unanswered, disagreements,
        undecided={"gold": 0.0, "fresh": round(rate, 4), "gold_units": len(truth),
                   "fresh_units": answered},
        undecided_excess=round(rate, 4),
    )  # fmt: skip


COMPARATORS: dict[str, CC.Comparator] = {
    COMPARISON_DECIDED: compare_decided,
    COMPARISON_BP: compare_bp,
    COMPARISON_ADV: compare_adv,
}


def prepare(root: Path, *, calibration_id: str, run: Path) -> dict[str, Any]:
    """`calibrate_claude.prepare`, then what the pool's tools read in the calibration run that the
    generic registration does not copy: the round's `notes` and `model` (the import re-renders every
    prompt with them) and - for the adversarial pool - the frozen cells."""
    report = CC.prepare(root, calibration_id=calibration_id, run=run)
    calibration_run = Path(report["calibration_run"])
    rounds_path = calibration_run / HO.ROUNDS_FILE
    [round_] = HO._read_jsonl(rounds_path)
    source, _ = D._source_round(run, Path(CC._sealed(root, calibration_id)["handoff"]))
    round_.setdefault("notes", {})
    round_.setdefault("model", source.get("model"))
    HO._write_jsonl(rounds_path, [round_])
    if (run / AD.CELLS_FILE).exists():
        shutil.copyfile(run / AD.CELLS_FILE, calibration_run / AD.CELLS_FILE)
    return report


def audit_quotes(root: Path, *, calibration_id: str) -> dict[str, Any]:
    """The quotes to spot-check for false sources (O18): every fresh quote the checker did not find
    in its page, and the sources both sides cited for each disagreement. The count the orchestrator
    gives `calibrate_claude.py verdict --false-sources` is its own, after reading these."""
    sealed = CC._sealed(root, calibration_id)
    out = root / calibration_id
    calibration_run = D.calibration_run(out)
    missing = []
    for name in (
        HO.ATTEMPTS_FILE,
        AD.VERDICTS_FILE,
    ):  # a field round's attempts, a check's verdicts
        path = calibration_run / name
        if not path.exists():
            continue
        for row in HO._read_jsonl(path):
            missing.extend(
                {
                    "cell": row.get("cell") or row["site_id"],
                    **{k: q[k] for k in ("source", "quote", "outcome")},
                }
                for q in row.get("quotes") or []
                if q["outcome"] != Q.FOUND
            )
    comparison = out / CC.COMPARISON_FILE
    disagreements = (
        json.loads(comparison.read_text(encoding="utf-8"))["disagreements"]
        if comparison.exists()
        else []
    )
    return {
        "calibration_id": calibration_id,
        "role": sealed["role"],
        "quotes_not_found": missing,
        "disagreements": [
            {k: d[k] for k in ("label", "unit", "recorded", "fresh", "fresh_sources")}
            for d in disagreements
        ],
    }


# ------------------------------------------------------------------------------------------ the CLI
def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    commands = {
        name: sub.add_parser(name)
        for name in ("build-general", "build-bp", "build-adversarial", "prepare", "compare",
                     "audit-quotes")
    }  # fmt: skip
    for name in ("build-general", "build-bp", "build-adversarial"):
        commands[name].add_argument("--out", type=Path, required=True)
        commands[name].add_argument("--seed", type=int, required=True)
    commands["build-general"].add_argument("--size", type=int, default=GENERAL_SIZE)
    commands["build-bp"].add_argument("--size", type=int, default=BP_SIZE)
    commands["build-adversarial"].add_argument("--per-class", type=int, default=ADV_PER_CLASS)
    for name in ("build-general", "build-bp"):
        commands[name].add_argument("--fields-dir", type=Path, default=POP.FIELDS_DIR)
    commands["build-adversarial"].add_argument("--audit-dir", type=Path, default=AUDIT_DIR)
    for name in ("prepare", "compare", "audit-quotes"):
        commands[name].add_argument("--root", type=Path, default=CC.CALIBRATION_ROOT)
        commands[name].add_argument("--id", required=True, dest="calibration_id")
    commands["prepare"].add_argument("--run", type=Path, required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "build-general":
            result: Any = build_general(
                args.out, seed=args.seed, size=args.size, fields_dir=args.fields_dir
            )
        elif args.command == "build-bp":
            result = build_bp(args.out, seed=args.seed, size=args.size, fields_dir=args.fields_dir)
        elif args.command == "build-adversarial":
            result = build_adversarial(
                args.out, seed=args.seed, per_class=args.per_class, audit_dir=args.audit_dir
            )
        elif args.command == "prepare":
            result = prepare(args.root, calibration_id=args.calibration_id, run=args.run)
        elif args.command == "compare":
            result = CC.compare(
                args.root, calibration_id=args.calibration_id, comparators=COMPARATORS
            )
        else:
            result = audit_quotes(args.root, calibration_id=args.calibration_id)
    except (PoolError, CC.CalibrationError, AD.AdversarialError, HO.HandoffStepError,
            OH.HandoffError, D.DriverError) as exc:  # fmt: skip
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
