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
* **adversarial-truth** - role `adversarial` on about **50 cells whose truth is known**, asked in the
  form of the wd5 check (`adversarial.py`): known-wrong cells (the periods the 2026-10-08 sample audit
  confirmed wrong, the band-rule Palaeolithic caves at 500 BC, and seeded perturbations of WD1
  two-source keeps - a start in a far bucket, a wrong canonical type, a point moved 40-120 km - each
  under the original quotes) must be `reject`ed, known-right cells (WD1 two-source keeps as decided)
  `confirm`ed. Its first design (`adv-001`, 40 cells of the DeepSeek audit's keep and revert verdicts)
  measured the audit's verdicts, a different question on different evidence, and failed at 0.575
  with 12 of 17 disagreements carrying no source on either side; see `FIELDS_WD5.md` section 3.

    pools.py build-general     --out DIR --seed N [--id fr-general-002]
    pools.py build-bp          --out DIR --seed N [--id fr-bp-002]
    pools.py build-adversarial-truth --out DIR --seed N [--id adv-truth-001]
    pools.py prepare --id ID --run DIR/run     calibrate_claude prepare + what the pool's tools read
    pools.py compare --id ID                   the comparison the seal names
    pools.py audit-quotes --id ID              the quotes to spot-check for false sources (O18)

The seal itself is `calibrate_claude.py seal`, with the arguments each build prints.
"""

from __future__ import annotations

import argparse
import json
import math
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
from fields import wiki as W  # noqa: E402

POOLS_ROOT = CC.CALIBRATION_ROOT / "pools"
GENERAL_SIZE = 60
BP_SIZE = 25
#: The sealed thresholds of the map: at least 90 % agreement on the cells both sides decide, no false
#: source (`calibrate_claude.MAX_FALSE_SOURCES`), the fresh share of undecided cells at most 10
#: points above the gold's.
THRESHOLD = 0.9
MAX_UNDECIDED_EXCESS = 0.10
COMPARISON_DECIDED, COMPARISON_BP = "fields-decided", "bp-bucket"
COMPARISON_ADV_KNOWN = "adv-known-truth"
#: The calibration ids of the second round (2026-10-09, after the tier move of `field_researcher` and
#: the redesign of the adversarial pool; the `-001` ones are recorded as run and stay).
GENERAL_CALIBRATION_ID = "fr-general-002"
BP_CALIBRATION_ID = "fr-bp-002"
ADV_CALIBRATION_ID = "adv-truth-001"
#: The calibrations lane wd5 needs passed before its first write: `(role, comparison)`. The seal of
#: each must bind the role's registry entry as it is now, so the researcher's two pools are
#: measured again on Opus, and the checker is measured on cells whose truth is known.
WD5_CALIBRATIONS = (
    ("field_researcher", COMPARISON_DECIDED),
    ("field_researcher", COMPARISON_BP),
    ("adversarial", COMPARISON_ADV_KNOWN),
)
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
    r"not read|cannot be read|can't be read|unreadable|not a year|does not read|not readable|not accepted|"
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
    out: Path, *, role: str, batches: Sequence[str], comparison: str, truth: bool,
    calibration_id: str,
) -> str:  # fmt: skip
    """The `calibrate_claude.py seal` command of a built pool, as the operator runs it."""
    parts = [
        "./.venv/Scripts/python.exe scripts/remediation/calibrate_claude.py seal",
        f"--id {calibration_id} --role {role}",
        f"--handoff {HO._shown(out / 'handoff')}",
        f"--batches {' '.join(batches)}",
        f"--threshold {THRESHOLD}",
        f"--max-undecided-excess {MAX_UNDECIDED_EXCESS}"
        if comparison == COMPARISON_DECIDED
        else "",
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
    out: Path, *, seed: int, size: int = GENERAL_SIZE, fields_dir: Path = POP.FIELDS_DIR,
    calibration_id: str = GENERAL_CALIBRATION_ID,
) -> dict[str, Any]:  # fmt: skip
    """`<out>/handoff` (batches of 8 sites by country and name, each question and its recorded answer
    byte for byte), `<out>/run` (RUN.json under WD1's rule, CLASSIFIED.jsonl, ROUNDS.jsonl)."""
    _need_empty(out)
    eligible = wd1_eligible(fields_dir)
    picked = stratify(eligible, size, random.Random(seed))  # noqa: S311 - a seeded, recorded draw
    classified = {s: dict(eligible[s].line) for s in picked}
    groups = HO.batches(sorted(picked), classified, 0, GENERAL_STAGE, HO.LEGACY_BATCH_SIZE)
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
                "batch_size": HO.LEGACY_BATCH_SIZE,
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
            truth=False, calibration_id=calibration_id,
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
    `unresolved` or `held` and an answer's reasoning names an age in years before the present. A
    MiniMax agent's reasoning is read as nothing (D10): its attempts name the model, WD1's name none.
    A run file that is not there is refused - a missing run would shrink the candidates unseen."""
    reasonings: dict[str, list[str]] = {}
    final: dict[str, str] = {}
    names: dict[str, str] = {}
    for name in (*POP.WD1_RUN_NAMES, *LATER_RUNS):
        run = fields_dir / name
        for d in POP._read_jsonl(run / HO.DECISIONS_FILE):
            if d["field"] == "period_start":
                final[d["site_id"]], names[d["site_id"]] = d["decision"], d["name"]
        for a in POP._read_jsonl(run / HO.ATTEMPTS_FILE):
            # MiniMax is never ground truth (D10, X6); WD1's attempts name no model: Claude's
            if "minimax" in str(a.get("model") or "").lower():
                continue
            text = (a["answer"] or {}).get("reasoning") if a["field"] == "period_start" else None
            if text and BP_MENTION.search(text):
                reasonings.setdefault(a["site_id"], []).append(text)
    lines: dict[str, Mapping[str, Any]] = {}
    for name in LATER_RUNS:  # the latest classification wins
        for line in POP._read_jsonl(fields_dir / name / C.CLASSIFIED_FILE):
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
    out: Path, *, seed: int, size: int = BP_SIZE, fields_dir: Path = POP.FIELDS_DIR,
    calibration_id: str = BP_CALIBRATION_ID,
) -> dict[str, Any]:  # fmt: skip
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
    result = HO.export(run, handoff, RESEARCHER_MODEL, batch_size=HO.LEGACY_BATCH_SIZE)
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
            truth=True, calibration_id=calibration_id,
        ),
    }  # fmt: skip


# ------------------------------------------------------------------------------ the known-truth pool
#: Cells whose truth is known, not judged by a model (the adversarial calibration of 2026-10-09; its
#: first design, 40 cells of the DeepSeek audit's keep/revert verdicts, measured gold drift - the
#: `adv-001` verdict - and was replaced). Every cell is presented in the one form: a stored value
#: the researcher says stands on the quote(s) below ("keep"), with a neutral reasoning, so that
#: nothing in a cell tells its class but the quotes and the value. `reject` is right for a
#: known-wrong cell, `confirm` for a known-right one.
KNOWN_WRONG, KNOWN_RIGHT = "known-wrong", "known-right"
#: The two classes and the rate each is held to (`compare_adv_known`).
CLASSES = {
    KNOWN_WRONG: "reject rate on the known-wrong cells",
    KNOWN_RIGHT: "confirm rate on the known-right cells",
}
EARTH_RADIUS_KM = 6371.0088
SAMPLE_AUDIT, BAND_RULE = "sample-audit-2026-10-08", "band-rule-cave"
WD1_KEEP = "wd1-two-source-keep"
PERTURBED_PERIOD, PERTURBED_TYPE, PERTURBED_POINT = (
    "perturbed-period", "perturbed-type", "perturbed-point"
)  # fmt: skip
#: The fields the pool asks, its cells per field and class (about 50 in all: 9 audit, 16 perturbed,
#: 25 known-right).
TRUTH_FIELDS = ("period_start", "site_type", "coordinates")
PERTURBED_QUOTA = {"period_start": 6, "site_type": 5, "coordinates": 5}
RIGHT_QUOTA = {"period_start": 9, "site_type": 8, "coordinates": 8}
NEUTRAL_REASONING = "The stored value stands on the quote(s) below."
#: A perturbed start lies at least this many buckets of the map's nine from the true one; a moved
#: point at least this far (km) from the true one (and at most `MAX_MOVE_KM`, still on land).
MIN_BUCKET_GAP = 3
MIN_MOVE_KM, MAX_MOVE_KM = 40.0, 120.0
#: A known-right point lies this close to the point its quotes give.
EXACT_POINT_KM = 0.1
#: A year in the middle of each bucket, to put a perturbed start in a chosen one.
BUCKET_YEARS = {
    "< 4500 BC": -6000,
    "4500 - 3000 BC": -3800,
    "3000 - 1500 BC": -2200,
    "1500 - 500 BC": -1000,
    "500 BC - 1 AD": -250,
    "1 - 500 AD": 250,
    "500 - 1000 AD": 750,
    "1000 - 1500 AD": 1250,
    "1500+ AD": 1700,
}
#: Canonical types no site of this corpus is mistaken for another's by a reader: a perturbed type
#: is one of them that no quote of the cell holds a word of.
WRONG_TYPES = (
    "Shipwreck", "Impact crater", "Harbor", "Stadium", "Mine/quarry", "Museum", "Aqueduct",
    "Bridge", "Well", "Magnetic anomaly", "Minaret/tower", "Mosque", "Stone cross", "Theatre",
    "Quarry", "Elongated skulls",
)  # fmt: skip


@dataclass(frozen=True)
class KnownWrong:
    """A stored period the sample audit of 2026-10-08 (30 sites, drawn 'draw-2026-10-08') confirmed
    wrong, or a Palaeolithic cave the band rule dated at 500 BC. `quote` is a sentence of the
    site's own cached English Wikipedia article, the page a researcher would stand the value on; it
    does not state the value."""

    site_id: str
    name: str
    value: int
    basis: str
    quote: str
    why: str


#: The site ids are production's (`unified_sites`, source ancient_nerds, read-only 2026-10-09).
KNOWN_WRONG_PERIODS: tuple[KnownWrong, ...] = (
    KnownWrong(
        "68677772-b461-49a3-bf2b-376e2b0e970b", "Lake Mungo", -500, SAMPLE_AUDIT,
        "These original inhabitants arrived approximately 50,000 years ago, and would have "
        "consumed emus and marsupials, as well as aquatic life such as crustaceans, freshwater "
        "mussels, and fish.",
        "stored -500 (500 BC - 1 AD); the occupation is dated to about 50,000 years ago",
    ),
    KnownWrong(
        "4caf5522-6a45-44b4-bba0-e98186c081f1", "Broadbury Castle", -4000, SAMPLE_AUDIT,
        "Historic England state that it is the remains of a Roman marching camp, although firm "
        "evidence for this is lacking and an alternative interpretation as an Iron Age or "
        "Roman-British civilian settlement has also been proposed.",
        "stored -4000 (Neolithic); the camp is Roman or Iron Age",
    ),
    KnownWrong(
        "61f1e287-c3bc-40ad-b3fe-af956af4cb1b", "Tappoch Broch", -800, SAMPLE_AUDIT,
        "Tappoch Broch, better known as Torwood Broch, is an iron-age broch located in a remote "
        "spot in dense woodland near Falkirk, Scotland.",
        "stored -800 (1500 - 500 BC); the audit found the broch dated to the last century or two "
        "BC or the first century or two AD (Undiscovered Scotland); 'iron-age' names the class, "
        "not the start of this broch",
    ),
    KnownWrong(
        "c2cd2a6a-8f1d-4fce-9645-234908ef7d37", "Hodson Stone Circle", -4000, SAMPLE_AUDIT,
        "The ring was part of a tradition of stone circle construction that spread throughout "
        "much of Britain, Ireland, and Brittany during the Late Neolithic and Early Bronze Age, "
        "over a period between 3300 and 900 BCE.",
        "stored -4000 (4500 - 3000 BC); the article dates the class of stone circles, not this "
        "lost circle",
    ),
    KnownWrong(
        "73106998-2108-42c6-8b07-3a1c79783968", "Le Moustier", -500, BAND_RULE,
        'The skeleton known as "Le Moustier" is estimated to be approximately 45,000 years old.',
        "stored -500 by the band rule; a Middle Palaeolithic site, the skeleton is about 45,000 "
        "years old",
    ),
    KnownWrong(
        "9d58f665-8cc3-4438-9dc5-99885deb90d0", "Bruniquel Cave", -500, BAND_RULE,
        "The constructions have been dated to approximately 176,500 years ago.",
        "stored -500 by the band rule; the constructions are about 176,500 years old",
    ),
    KnownWrong(
        "cb282d61-5c81-44f2-92dc-576a4ad1895e", "Cro-Magnon Rock Shelter", -500, BAND_RULE,
        "Most notably, it is the site of the discovery of anatomically modern human remains, "
        "apparently buried at the site, dated to about 28,000 years ago.",
        "stored -500 by the band rule; an Upper Palaeolithic site, the remains are about 28,000 "
        "years old",
    ),
    KnownWrong(
        "996e0b32-f8ca-4d04-8900-ed937b729269", "Apidima Cave", -500, BAND_RULE,
        "The second cranium, labeled Apidima 2 and dated more than 150 thousand years ago, is "
        "more obviously related to Neanderthals",
        "stored -500 by the band rule; the crania are more than 150,000 years old",
    ),
    KnownWrong(
        "c070b6b0-3fd2-4d6c-acbe-105539188253", "Eartham Pit, Boxgrove", -500, BAND_RULE,
        "The Boxgrove Palaeolithic site is a complex of internationally important Lower "
        "Palaeolithic archaeological sites in the former Eartham Quarry, north-east of Boxgrove "
        "in West Sussex, dating to around 480,000 years ago during the Middle Pleistocene.",
        "stored -500 by the band rule; the site is about 480,000 years old",
    ),
)  # fmt: skip


class PerturbationError(PoolError):
    """A cell cannot be perturbed the way the pool asks (no wrong type free of the quotes, no wrong
    bucket): the candidate is left out, never bent."""


class InexactKeepError(PoolError):
    """A WD1 keep whose stored value is not what its own quotes say (a period start only in the
    same bucket, a point off the quoted one): no known-right cell, since a checker that holds the
    stored value to the quote must reject it. The candidate is left out, never bent."""


def wrong_year(true_year: int, rng: random.Random) -> int:
    """A year in a bucket at least `MIN_BUCKET_GAP` buckets away from the true year's."""
    here = C.BUCKETS.index(C.bucket(true_year))
    far = [b for i, b in enumerate(C.BUCKETS) if abs(i - here) >= MIN_BUCKET_GAP]
    return BUCKET_YEARS[rng.choice(far)]


def wrong_type(true_type: str, line: Mapping[str, Any], quotes: Sequence[Mapping[str, Any]],
               rng: random.Random) -> str:  # fmt: skip
    """A canonical type that is not the true one, not one the item's classes name, and none of whose
    stems a quote (or the passage around it, or the head of its page) holds a word of."""
    named = set(line["fields"]["site_type"]["evidence"].get("types") or ())
    texts = [t for q in quotes for t in (q["quote"], q["passage"], q["head"])]
    options = [
        t for t in WRONG_TYPES
        if t != true_type and t not in named
        and not any(A.holds_stem(text, stem) for text in texts for stem in A.type_stems(t))
    ]  # fmt: skip
    if not options:
        raise PerturbationError(f"no wrong type free of the quotes for {true_type!r}")
    return rng.choice(options)


def moved_point(point: tuple[float, float], rng: random.Random) -> str:
    """The point moved `MIN_MOVE_KM`..`MAX_MOVE_KM` km on a seeded bearing, written as the database
    writes a stored point (`lat, lon`)."""
    km = rng.uniform(MIN_MOVE_KM, MAX_MOVE_KM)
    bearing = math.radians(rng.uniform(0, 360))
    lat, lon = point
    d = km / EARTH_RADIUS_KM
    lat2 = math.asin(
        math.sin(math.radians(lat)) * math.cos(d)
        + math.cos(math.radians(lat)) * math.sin(d) * math.cos(bearing)
    )
    lon2 = math.radians(lon) + math.atan2(
        math.sin(bearing) * math.sin(d) * math.cos(math.radians(lat)),
        math.cos(d) - math.sin(math.radians(lat)) * math.sin(lat2),
    )
    moved = (math.degrees(lat2), (math.degrees(lon2) + 540) % 360 - 180)
    if A._km(point, moved) < MIN_MOVE_KM - 1:
        raise PerturbationError(f"the moved point is {A._km(point, moved):.1f} km away")
    return f"{moved[0]:.6f}, {moved[1]:.6f}"


def _wiki_quote(page: Mapping[str, Any], quote: str) -> dict[str, Any]:
    """`adversarial.quote_packet`'s shape for a sentence of a cached Wikipedia article, which the
    caller found in the article's text (`known_wrong_cells`), whitespace-normalised like the
    machine's own reading."""
    text = Q.normalise(str(page["text"]))
    wanted = Q.normalise(quote)
    return {
        "url": W.article_url(page),
        "quote": quote,
        "outcome": Q.FOUND,
        "reading": "visible text",
        "head": text[: AD.HEAD_CHARS],
        "passage": AD.excerpt(text, wanted),
    }


def _truth_cell(
    line: Mapping[str, Any], field: str, *, stored: Any, value: Any,
    quotes: Sequence[Mapping[str, Any]], wiki: W.WikiCache | None,
    stored_point: str | None = None,
) -> dict[str, Any]:  # fmt: skip
    """One cell of the pool: the stored value kept on the quotes, under the neutral reasoning."""
    decision = {
        "site_id": line["site_id"], "field": field, "stored": stored, "decision": A.KEEP,
        "value": value, "via": "counted", "round": 0, "answered_by": "the calibration pool",
        "model": None, "reasoning": NEUTRAL_REASONING, "value_page": None,
    }  # fmt: skip
    cell = AD.framed(decision, line, quotes, wiki)
    # the wd5 classification's open reason names the class of the cell ("rule-made"): a pool cell
    # tells the checker its value and its quotes and nothing else
    cell["why_open"] = cell["made"] = None
    if stored_point is not None:
        cell["stored_point"] = stored_point
    return cell


def known_wrong_cells(
    fields_dir: Path, wiki: W.WikiCache, entries: Sequence[KnownWrong]
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """`[(cell, truth entry)]` of the sample audit's wrong periods and the band-rule caves: the
    wd5 classification of the site (its name must be the entry's), the stored value, the article's
    sentence. A site the wd5 run lacks, a name that differs, an article the cache lacks or a sentence
    the article does not hold is refused by name."""
    classified = HO.read_classified(fields_dir / R.RECHECK.stage)
    out = []
    for entry in entries:
        line = classified.get(entry.site_id)
        if line is None:
            raise PoolError(f"{entry.name}: {entry.site_id} is not in the wd5 classification")
        if line["name"] != entry.name:
            raise PoolError(f"{entry.site_id} is {line['name']!r}, not {entry.name!r}")
        pages = [p for p in wiki.pages(entry.site_id) if not p.get("missing")]
        if not pages:
            raise PoolError(f"{entry.name}: the Wikipedia cache holds no article of the site")
        held = [p for p in pages if Q.normalise(entry.quote) in Q.normalise(str(p["text"]))]
        if not held:
            raise PoolError(f"{entry.name}: its sentence is in none of its cached articles")
        cell = _truth_cell(line, "period_start", stored=entry.value, value=str(entry.value),
                           quotes=[_wiki_quote(held[0], entry.quote)], wiki=wiki)  # fmt: skip
        truth = {
            "expected": AD.REJECT, "class": KNOWN_WRONG, "basis": entry.basis,
            "column": "period_start", "name": entry.name, "why": entry.why,
        }  # fmt: skip
        out.append((cell, truth))
    return out


@dataclass(frozen=True)
class Wd1Keep:
    """A WD1 `keep` decided on two quotes of two source families (the rule `two-families`, found in
    their pages by the machine): the stored value stands, with its sources."""

    decision: Mapping[str, Any]
    line: Mapping[str, Any]
    pages: Path


def wd1_keeps(fields_dir: Path) -> dict[str, list[Wd1Keep]]:
    """`{field: keeps}` of the four WD1 runs, in site order: a counted `keep` of a field of
    `TRUTH_FIELDS` whose every quote the machine found. A run that is not there is refused - a
    missing run would shrink the pool unseen."""
    out: dict[str, list[Wd1Keep]] = {f: [] for f in TRUTH_FIELDS}
    seen: set[tuple[str, str]] = set()
    for name in POP.WD1_RUN_NAMES:
        run = fields_dir / name
        classified = HO.read_classified(run)
        for d in sorted(HO._read_jsonl(run / HO.DECISIONS_FILE), key=lambda d: d["site_id"]):
            if (
                d["via"] == "counted" and d["decision"] == A.KEEP and d["field"] in TRUTH_FIELDS
                and len(d["quotes"]) >= 2 and all(q["outcome"] == Q.FOUND for q in d["quotes"])
                and d["site_id"] in classified and d["value"] is not None
                and d["stored"] is not None and (d["site_id"], d["field"]) not in seen
            ):  # fmt: skip
                out[d["field"]].append(Wd1Keep(d, classified[d["site_id"]], run / AD.PAGES_DIR))
                seen.add((d["site_id"], d["field"]))
    return out


def _exact(d: Mapping[str, Any]) -> bool:
    """Whether a keep's stored value is the value its quotes give: the same start year (WD1 keeps a
    start in the same bucket), a point within `EXACT_POINT_KM` (WD1 keeps one within 1 km), the same
    type."""
    if d["field"] == "period_start":
        return int(d["stored"]) == int(d["value"])
    if d["field"] == "coordinates":
        return A._km(_point(str(d["stored"])), _point(str(d["value"]))) <= EXACT_POINT_KM
    return str(d["stored"]) == str(d["value"])


def _right_cell(keep: Wd1Keep, wiki: W.WikiCache | None) -> tuple[dict[str, Any], dict[str, Any]]:
    d = keep.decision
    if not _exact(d):
        raise InexactKeepError(
            f"{keep.line['name']}: the stored {d['field']} {d['stored']!r} is not the quoted "
            f"{d['value']!r}"
        )
    quotes = [AD.quote_packet(q, Q.Library(D.REPO, keep.pages)) for q in d["quotes"]]
    cell = _truth_cell(keep.line, d["field"], stored=d["stored"], value=d["value"], quotes=quotes,
                       wiki=wiki)  # fmt: skip
    truth = {
        "expected": AD.CONFIRM, "class": KNOWN_RIGHT, "basis": WD1_KEEP, "column": d["field"],
        "name": keep.line["name"],
        "why": f"WD1 kept the stored {d['field']} on two quotes of two source families",
    }  # fmt: skip
    return cell, truth


def _perturbed_cell(
    keep: Wd1Keep, wiki: W.WikiCache | None, rng: random.Random
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The keep with its stored value replaced by a wrong one, under the original quotes (which state
    the true value)."""
    d = keep.decision
    field = d["field"]
    quotes = [AD.quote_packet(q, Q.Library(D.REPO, keep.pages)) for q in d["quotes"]]
    stored_point = None
    if field == "period_start":
        wrong: Any = wrong_year(int(d["stored"]), rng)
        stored, value, basis = wrong, str(wrong), PERTURBED_PERIOD
        what = f"{d['stored']} (the quotes' year {d['value']}) moved to {wrong}"
    elif field == "site_type":
        wrong = wrong_type(str(d["stored"]), keep.line, quotes, rng)
        stored, value, basis = wrong, wrong, PERTURBED_TYPE
        what = f"{d['stored']!r} swapped to {wrong!r}"
    else:
        wrong = moved_point(_point(str(d["stored"])), rng)
        stored, value, basis, stored_point = wrong, wrong, PERTURBED_POINT, wrong
        what = f"{d['stored']} moved to {wrong}"
    cell = _truth_cell(keep.line, field, stored=stored, value=value, quotes=quotes, wiki=wiki,
                       stored_point=stored_point)  # fmt: skip
    truth = {
        "expected": AD.REJECT, "class": KNOWN_WRONG, "basis": basis, "column": field,
        "name": keep.line["name"],
        "why": f"{what}; the quotes are WD1's, two sources of two families, for the true value",
    }  # fmt: skip
    return cell, truth


def build_adversarial_truth(
    out: Path,
    *,
    seed: int,
    fields_dir: Path = POP.FIELDS_DIR,
    wiki_root: Path = W.WIKI_CACHE,
    known_wrong: Sequence[KnownWrong] | None = None,
    perturbed: Mapping[str, int] | None = None,
    right: Mapping[str, int] | None = None,
    calibration_id: str = ADV_CALIBRATION_ID,
) -> dict[str, Any]:
    """`<out>/handoff` (the check question per cell), `<out>/run` (CELLS.json, ROUNDS.jsonl, a wd5
    RUN.json) and `<out>/TRUTH.json` (`{cell: {expected: confirm|reject, class, basis, why}}`).

    **Known wrong**: the sample audit's wrong periods and the band-rule caves (`KNOWN_WRONG_PERIODS`)
    and seeded perturbations of WD1 two-source keeps - a start in a bucket `MIN_BUCKET_GAP` away, a
    wrong canonical type, a point moved 40-120 km - each under the original quotes. **Known right**:
    other WD1 two-source keeps as they were decided. A site is in the pool once. The table and the
    quotas are `KNOWN_WRONG_PERIODS`, `PERTURBED_QUOTA` and `RIGHT_QUOTA` unless given."""
    _need_empty(out)
    known_wrong = KNOWN_WRONG_PERIODS if known_wrong is None else known_wrong
    perturbed = PERTURBED_QUOTA if perturbed is None else perturbed
    right = RIGHT_QUOTA if right is None else right
    rng = random.Random(seed)  # noqa: S311 - a seeded, recorded draw
    wiki = W.WikiCache(wiki_root)
    keeps = wd1_keeps(fields_dir)
    cells: list[tuple[dict[str, Any], dict[str, Any]]] = known_wrong_cells(
        fields_dir, wiki, known_wrong
    )
    taken = {c["site_id"] for c, _ in cells}
    for field in TRUTH_FIELDS:
        pool = [k for k in keeps[field] if k.decision["site_id"] not in taken]
        rng.shuffle(pool)
        for kind, quota, make in (
            ("right", right[field], lambda k: _right_cell(k, wiki)),
            ("perturbed", perturbed[field], lambda k: _perturbed_cell(k, wiki, rng)),
        ):
            made = 0
            while made < quota and pool:
                keep = pool.pop()
                try:
                    cells.append(make(keep))
                except (AD.AdversarialError, PerturbationError, InexactKeepError):
                    continue  # a page that cannot be read or a value that cannot be bent: left out
                taken.add(keep.decision["site_id"])
                made += 1
            if made < quota:
                raise PoolError(f"only {made} usable {kind} {field} cells, {quota} wanted")
    ids = [cell["cell"] for cell, _ in cells]
    if len(set(ids)) != len(ids):
        raise PoolError("a cell is in the pool twice")
    run, handoff = out / "run", out / "handoff"
    R.write_run(run, R.RECHECK, built_from={"pool": "adversarial-truth", "seed": seed})
    (run / C.CLASSIFIED_FILE).write_text("", encoding="utf-8", newline="\n")
    ordered = sorted(cells, key=lambda pair: pair[0]["cell"])
    HO._write_json(run / AD.CELLS_FILE, {"seed": seed, "cells": [c for c, _ in ordered]})
    AD._export_round(run, handoff, 0, [c["cell"] for c, _ in ordered], {}, AD.LEGACY_BATCH_SIZE)
    truth = {cell["cell"]: entry for cell, entry in ordered}
    HO._write_json(out / TRUTH_FILE, truth)
    batches = list(AD.read_rounds(run)[0]["batches"])
    return {
        "pool": "adversarial-truth",
        "cells": len(ordered),
        "expected": dict(sorted(Counter(t["expected"] for t in truth.values()).items())),
        "basis": dict(sorted(Counter(t["basis"] for t in truth.values()).items())),
        "batches": batches,
        "seal": _seal_command(
            out, role="adversarial", batches=batches, comparison=COMPARISON_ADV_KNOWN, truth=True,
            calibration_id=calibration_id,
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


def compare_adv_known(
    sealed: dict[str, Any], recorded: dict[str, str], fresh: dict[str, str], out: Path
) -> dict[str, Any]:
    """The known-truth adversarial pool: `reject` is right for a known-wrong cell, `confirm` for a
    known-right one. Every answered cell counts - an `unclear` (or an answer not in shape) is a
    miss in its class, because a known-wrong cell that is not rejected is not caught. The seal's
    threshold holds twice, as a rate per class: the reject rate on the known-wrong cells and the
    confirm rate on the known-right ones (`lane_failures`, which `verdict` reads)."""
    truth = _truth(sealed)
    units = agreed = unclear = 0
    unanswered: list[str] = []
    disagreements: list[dict[str, Any]] = []
    answered: Counter[str] = Counter()
    hits: Counter[str] = Counter()
    by_basis: Counter[str] = Counter()
    for cell in sorted(truth):
        if cell not in fresh:
            unanswered.append(cell)
            continue
        try:
            verdict = AD.parse_answer(fresh[cell], cell.rsplit(".", 1)[1])[0]
        except AnswerError:
            verdict = AD.UNCLEAR
        entry = truth[cell]
        units += 1
        answered[entry["class"]] += 1
        if verdict == entry["expected"]:
            agreed += 1
            hits[entry["class"]] += 1
            by_basis[entry["basis"]] += 1
        else:
            unclear += verdict == AD.UNCLEAR
            disagreements.append(
                _disagreement(cell, "verdict", entry["expected"], verdict, fresh[cell])
            )
    rates = {c: round(hits[c] / answered[c], 4) if answered[c] else None for c in CLASSES}
    failures = [
        f"no {c} cell was answered"
        if rates[c] is None
        else f"the {what} {rates[c]} is below the sealed threshold {sealed['threshold']}"
        for c, what in CLASSES.items()
        if rates[c] is None or rates[c] < sealed["threshold"]
    ]
    return _report(
        sealed["role"], sorted(truth), units, agreed, unanswered, disagreements,
        reject_rate_known_wrong=rates[KNOWN_WRONG], confirm_rate_known_right=rates[KNOWN_RIGHT],
        answered_by_class=dict(sorted(answered.items())), unclear=unclear,
        agreed_by_basis=dict(sorted(by_basis.items())), lane_failures=failures,
    )  # fmt: skip


COMPARATORS: dict[str, CC.Comparator] = {
    COMPARISON_DECIDED: compare_decided,
    COMPARISON_BP: compare_bp,
    COMPARISON_ADV_KNOWN: compare_adv_known,
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
        for name in ("build-general", "build-bp", "build-adversarial-truth", "prepare", "compare",
                     "audit-quotes")
    }  # fmt: skip
    builds = {
        "build-general": GENERAL_CALIBRATION_ID,
        "build-bp": BP_CALIBRATION_ID,
        "build-adversarial-truth": ADV_CALIBRATION_ID,
    }
    for name, default_id in builds.items():
        commands[name].add_argument("--out", type=Path, required=True)
        commands[name].add_argument("--seed", type=int, required=True)
        commands[name].add_argument("--id", default=default_id, dest="calibration_id")
        commands[name].add_argument("--fields-dir", type=Path, default=POP.FIELDS_DIR)
    commands["build-general"].add_argument("--size", type=int, default=GENERAL_SIZE)
    commands["build-bp"].add_argument("--size", type=int, default=BP_SIZE)
    commands["build-adversarial-truth"].add_argument("--wiki-root", type=Path, default=W.WIKI_CACHE)
    for name in ("prepare", "compare", "audit-quotes"):
        commands[name].add_argument("--root", type=Path, default=CC.CALIBRATION_ROOT)
        commands[name].add_argument("--id", required=True, dest="calibration_id")
    commands["prepare"].add_argument("--run", type=Path, required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "build-general":
            result: Any = build_general(
                args.out, seed=args.seed, size=args.size, fields_dir=args.fields_dir,
                calibration_id=args.calibration_id,
            )  # fmt: skip
        elif args.command == "build-bp":
            result = build_bp(
                args.out, seed=args.seed, size=args.size, fields_dir=args.fields_dir,
                calibration_id=args.calibration_id,
            )  # fmt: skip
        elif args.command == "build-adversarial-truth":
            result = build_adversarial_truth(
                args.out, seed=args.seed, fields_dir=args.fields_dir, wiki_root=args.wiki_root,
                calibration_id=args.calibration_id,
            )  # fmt: skip
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
