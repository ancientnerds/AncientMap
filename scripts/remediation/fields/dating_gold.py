"""D70/D71: the dating extractor's gold - built and sealed, measured once per round, judged.

Owner decision D71 (2026-11-05): the extractor's cells are written without a model check only when
its precision on a **sealed** gold set is at least 95 %. The discipline is `calibrate_claude`'s (a
set drawn and pinned before the thing measured is final, measured once, never relabelled), but the
extractor is no role, so that module is not reused (design section 3).

**The pool** (`gold_pool`): shown curated sites whose live `period_start` equals a Claude keep or
replace decision of the field lanes that a found quote stands behind. Excluded: rule rows
(`answered_by` "rule:..."), MiniMax answers, an answer without a model (WD1's rows: no census proves
them Claude), an adversarial `unclear` or `reject` (unless the owner accepted it - then the site is a
`hard` one), a retired site, an undated one. **The hard stratum** (`hard`): sites whose period was
first left `unresolved` and later dated (the reader-gap re-asks, the D68/D69 owner-accepted cells) -
measured and reported apart, never gated (the 615 are the hard cases; the gold is easier, design
section 6 and the owner item).

**The draw** (`draw`): 400 gold sites and a disjoint DEV set of 300, seeded, stratified by region and
article size in the shape of the undated sites (stubs and the Americas are what the 615 are), with
era band and type group reported. The extractor is developed on DEV only.

    dating_gold.py build   --gold DIR --stored STORED.jsonl --harvest ROOT --undated FILE --seed S
                           [--fields-dir DIR]     round-NN/: GOLD.jsonl, DEV.jsonl, HARD.jsonl,
                                                  GOLD.sha256, SEAL.json (the next round after a
                                                  failed one: its gold and hard become DEV data)
    dating_gold.py freeze  --gold DIR             FROZEN.json: the sha256 of the extractor's code
                                                  and CONFIG (`dating.code_hashes`)
    dating_gold.py measure --gold DIR --harvest ROOT [--fields-dir DIR]
                                                  RESULTS.jsonl, MEASURE.json - refused when the
                                                  code is not the frozen code, and refused a second
                                                  time: a measured gold is never measured again
    dating_gold.py verdict --gold DIR             VERDICT.json: pass or fail, and why
    dating_gold.py conflicts --stored STORED.jsonl --harvest ROOT --out FILE
                                                  D72: every dated site whose bucket the extractor
                                                  reads differently, with the quotes; never written

**The gate** (`judge`, design section 7): bucket precision = emitted starts in the gold's bucket /
emitted, at least `THRESHOLD` with at least `MIN_GOLD` gold sites and `MIN_EMITTED` emitted; the
Wilson 95 % interval is reported beside it. Every tier that decided at least one gold cell, and a
decision on a period word alone, is judged on its own: below the threshold, or with fewer than
`TIER_MIN` cells, the verdict fails and names it - the tier is switched off in `dating.CONFIG` (a
code change, a new freeze, a new round), never kept as a fallback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from fields import dating as DT  # noqa: E402
from pipeline.normalizers.dates import AMERICAS_LON_MAX, AMERICAS_LON_MIN, in_oceania  # noqa: E402
from pipeline.utils.text import PERIOD_BUCKETS, categorize_period  # noqa: E402

THRESHOLD = 0.95
MIN_GOLD = 200
MIN_EMITTED = 100
#: A tier (or the period-word-only decisions) judged on its own needs at least this many cells.
TIER_MIN = 20
GOLD_N, DEV_N = 400, 300
WILSON_Z = 1.96
GOLD_ROOT = REPO / "output" / "remediation" / "fields" / "wd5x" / "gold"
#: The field runs whose decisions the pool reads, oldest first: a later run's decision of a field is
#: the one that stands.
GOLD_RUNS = ("wd1-pilot", "wd1", "wd1-rest-pilot", "wd1-rest", "wd3-pilot", "wd3", "wd4",
             "wd5-pilot", "wd5", "wd5-reask")  # fmt: skip
GOLD_FILE, DEV_FILE, HARD_FILE = "GOLD.jsonl", "DEV.jsonl", "HARD.jsonl"
PIN_FILE, SEAL_FILE, FROZEN_FILE = "GOLD.sha256", "SEAL.json", "FROZEN.json"
RESULTS_FILE, MEASURE_FILE, VERDICT_FILE = "RESULTS.jsonl", "MEASURE.json", "VERDICT.json"
EMITTING = (DT.SINGLE, DT.RANGE, DT.SCOPE_HOLD)


class GoldError(ValueError):
    """The gold is not in the state the command needs: nothing is written."""


# ------------------------------------------------------------------------------ the strata
REGIONS = ("europe-mediterranean", "near-east-egypt", "americas", "south-east-asia", "africa",
           "oceania")  # fmt: skip
#: The Near East and Egypt, by the stored country (the census spellings).
NEAR_EAST = frozenset(
    {"egypt", "israel", "palestine", "state of palestine", "jordan", "lebanon", "syria", "iraq",
     "iran", "turkey", "türkiye", "turkiye", "saudi arabia", "yemen", "oman",
     "united arab emirates", "kuwait", "bahrain", "qatar", "armenia", "georgia", "azerbaijan",
     "sudan"}
)  # fmt: skip


def region_of(site: Mapping[str, Any]) -> str:
    """The stratum region of a site from its point and country (design section 6)."""
    lat, lon = float(site["lat"]), float(site["lon"])
    country = str(site.get("country") or "")
    if in_oceania(country, lat, lon):
        return "oceania"
    if AMERICAS_LON_MIN <= lon <= AMERICAS_LON_MAX:
        return "americas"
    if country.casefold() in NEAR_EAST:
        return "near-east-egypt"
    if lon > 60:
        return "south-east-asia"
    if lat < 35 and -20 < lon < 52:
        return "africa"
    return "europe-mediterranean"


def size_of(chars: int | None) -> str:
    """The article-size stratum: none, a stub (< 1,500 characters), medium (< 8,000), long."""
    if not chars:
        return "none"
    return "stub" if chars < 1500 else "medium" if chars < 8000 else "long"


ERA_BANDS = {
    PERIOD_BUCKETS[0][0]: "deep", PERIOD_BUCKETS[1][0]: "deep",
    PERIOD_BUCKETS[2][0]: "bronze", PERIOD_BUCKETS[3][0]: "iron",
    PERIOD_BUCKETS[4][0]: "classical", PERIOD_BUCKETS[5][0]: "classical",
    PERIOD_BUCKETS[6][0]: "late", PERIOD_BUCKETS[7][0]: "late", PERIOD_BUCKETS[8][0]: "late",
}  # fmt: skip
TYPE_GROUPS = (
    ("cave/rock art", ("cave", "rock", "petroglyph", "art", "shelter")),
    ("megalith/circle", ("megalith", "stone", "circle", "dolmen", "menhir", "henge", "cairn")),
    ("fort", ("fort", "castle", "hillfort", "citadel", "defens", "wall")),
    ("temple/tomb", ("temple", "tomb", "burial", "pyramid", "sanctuary", "shrine", "religious",
                     "necropolis", "mound", "barrow")),  # fmt: skip
    ("settlement", ("settlement", "city", "town", "village", "urban", "port", "villa")),
)


def type_group(site_type: str | None) -> str:
    low = str(site_type or "").casefold()
    for group, words in TYPE_GROUPS:
        if any(w in low for w in words):
            return group
    return "other"


# ------------------------------------------------------------------------------ the pool
def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise GoldError(f"{path} is missing")
    return [json.loads(raw) for raw in path.read_text(encoding="utf-8").splitlines() if raw.strip()]


def _int(value: Any) -> int | None:
    if value is None or (isinstance(value, str) and not re.fullmatch(r"-?\d+", value.strip())):
        return None
    return int(value)


def _is_claude(decision: Mapping[str, Any]) -> bool:
    return "claude" in str(decision.get("model") or "").casefold()


def _quoted(decision: Mapping[str, Any]) -> bool:
    return any(q.get("outcome") == "found" for q in decision.get("quotes") or ())


def period_histories(fields_dir: Path, runs: Sequence[str] = GOLD_RUNS) -> dict[str, list[dict]]:
    """Every `period_start` decision of `runs` per site, oldest run first (a missing run is none)."""
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        path = fields_dir / run / "DECISIONS.jsonl"
        if not path.exists():
            continue
        for row in _read_jsonl(path):
            if row["field"] == "period_start":
                out[str(row["site_id"])].append({**row, "_run": run})
    return out


def _value_of(decision: Mapping[str, Any]) -> int | None:
    if decision["decision"] == "keep":
        return _int(decision.get("stored"))
    return _int(decision.get("value"))


def provenance(decision: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "run": decision["_run"],
        "decision": decision["decision"],
        "answered_by": decision.get("answered_by"),
        "model": decision.get("model"),
        "adversarial": (decision.get("adversarial") or {}).get("verdict")
        if isinstance(decision.get("adversarial"), dict)
        else None,
        "owner": bool(decision.get("owner")),
        "sources": sorted({str(q.get("source")) for q in decision.get("quotes") or ()}),
    }


def gold_pool(
    stored: Iterable[Mapping[str, Any]], histories: Mapping[str, Sequence[Mapping[str, Any]]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """`(pool, hard)`: the gold rows of the module docstring - `{site_id, name, gold_year,
    gold_bucket, provenance}` - each sorted by site id."""
    pool, hard = [], []
    for row in stored:
        sid = str(row["site_id"])
        year = _int(row.get("period_start"))
        if year is None or row.get("scope_status") == "retired":
            continue
        history = histories.get(sid, ())
        settled = [d for d in history if d["decision"] in ("keep", "replace")]
        if not settled:
            continue
        last = settled[-1]
        if _value_of(last) != year or not _is_claude(last) or not _quoted(last):
            continue
        if str(last.get("answered_by") or "").startswith("rule:"):
            continue
        verdict = provenance(last)["adversarial"]
        line = {
            "site_id": sid,
            "name": row.get("name"),
            "gold_year": year,
            "gold_bucket": categorize_period(year),
            "provenance": provenance(last),
        }
        was_open = any(d["decision"] == "unresolved" for d in history[: history.index(last)])
        if was_open or (verdict in ("unclear", "reject") and last.get("owner")):
            hard.append({**line, "stratum": "hard"})
        elif verdict not in ("unclear", "reject"):
            pool.append({**line, "stratum": "gold"})
    return sorted(pool, key=lambda r: r["site_id"]), sorted(hard, key=lambda r: r["site_id"])


# ------------------------------------------------------------------------------ the draw
def strata(
    rows: Iterable[Mapping[str, Any]],
    sites: Mapping[str, Mapping[str, Any]],
    sizes: Mapping[str, int | None],
) -> dict[str, tuple[str, str]]:
    """`site_id -> (region, size)` for each row."""
    return {
        str(r["site_id"]): (region_of(sites[str(r["site_id"])]), size_of(sizes.get(str(r["site_id"]))))
        for r in rows
    }


def draw(
    pool: Sequence[Mapping[str, Any]],
    cells: Mapping[str, tuple[str, str]],
    shape: Mapping[tuple[str, str], int],
    n: int,
    seed: int,
) -> list[dict[str, Any]]:
    """`n` rows of `pool`, seeded, allocated over the (region, size) cells in the proportion of
    `shape` (the undated sites' counts); a cell the pool cannot fill gives its rest to the others in
    the pool's own proportion."""
    if n > len(pool):
        raise GoldError(f"a draw of {n} from a pool of {len(pool)}")
    rng = random.Random(seed)  # noqa: S311 - a seeded draw, not a key
    by_cell: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in sorted(pool, key=lambda r: r["site_id"]):
        by_cell[cells[str(row["site_id"])]].append(row)
    for rows in by_cell.values():
        rng.shuffle(rows)
    total = sum(shape.values()) or 1
    want = {cell: round(n * count / total) for cell, count in shape.items()}
    chosen: list[Mapping[str, Any]] = []
    for cell in sorted(want):
        chosen.extend(by_cell.get(cell, [])[: want[cell]])
    taken = {r["site_id"] for r in chosen}
    rest = [r for cell in sorted(by_cell) for r in by_cell[cell] if r["site_id"] not in taken]
    rng.shuffle(rest)
    chosen = chosen[:n] + rest[: max(0, n - len(chosen))]
    return sorted((dict(r) for r in chosen), key=lambda r: r["site_id"])


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows),
        encoding="utf-8",
        newline="\n",
    )


def _write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise GoldError(f"{path} is missing")
    return json.loads(path.read_text(encoding="utf-8"))


def rounds(gold_root: Path) -> list[Path]:
    return sorted(p for p in gold_root.glob("round-*") if p.is_dir())


def current_round(gold_root: Path) -> Path:
    found = rounds(gold_root)
    if not found:
        raise GoldError(f"{gold_root} holds no round - `dating_gold.py build` first")
    return found[-1]


def build(
    gold_root: Path,
    *,
    stored: Sequence[Mapping[str, Any]],
    histories: Mapping[str, Sequence[Mapping[str, Any]]],
    sites: Mapping[str, Mapping[str, Any]],
    sizes: Mapping[str, int | None],
    undated: Sequence[str],
    seed: int,
    gold_n: int = GOLD_N,
    dev_n: int = DEV_N,
) -> dict[str, Any]:
    """The next round: its gold, DEV and hard sets, pinned and sealed. A round after a measured one
    is drawn only when that one failed, and that one's gold and hard sets join DEV (a failed gold is
    never measured again after tuning - it becomes development data)."""
    earlier = rounds(gold_root)
    used: set[str] = set()
    dev_carried: list[dict[str, Any]] = []
    if earlier:
        last = earlier[-1]
        verdict = last / VERDICT_FILE
        if not verdict.exists():
            raise GoldError(f"{last} is not judged yet: a new round follows a failed verdict")
        if _read_json(verdict)["pass"]:
            raise GoldError(f"{last} passed: no new round is drawn after a passing gold")
        for r in earlier:
            for name in (GOLD_FILE, DEV_FILE, HARD_FILE):
                rows = _read_jsonl(r / name)
                used.update(row["site_id"] for row in rows)
                if r == last:
                    dev_carried.extend({**row, "stratum": "dev"} for row in rows)
    pool, hard = gold_pool(stored, histories)
    missing = sorted({r["site_id"] for r in pool + hard} - set(sites))
    if missing:
        raise GoldError(f"{len(missing)} pool site(s) are not in the harvest: {missing[:3]}")
    cells = strata(pool, sites, sizes)
    undated_cells = [(region_of(sites[s]), size_of(sizes.get(s))) for s in undated if s in sites]
    shape = Counter(undated_cells)
    free = [r for r in pool if r["site_id"] not in used]
    gold = draw(free, cells, shape, gold_n, seed)
    taken = {r["site_id"] for r in gold}
    if earlier:
        dev = sorted(dev_carried, key=lambda r: r["site_id"])
        hard_now: list[dict[str, Any]] = []
    else:
        hard_now = [r for r in hard if r["site_id"] not in used]
        dev_pool = [r for r in free if r["site_id"] not in taken]
        dev = [{**r, "stratum": "dev"} for r in draw(dev_pool, cells, shape, dev_n, seed + 1)]
    number = len(earlier) + 1
    target = gold_root / f"round-{number:02d}"
    target.mkdir(parents=True, exist_ok=False)
    _write_jsonl(target / GOLD_FILE, gold)
    _write_jsonl(target / DEV_FILE, dev)
    _write_jsonl(target / HARD_FILE, hard_now)
    pin = _sha256(target / GOLD_FILE)
    (target / PIN_FILE).write_text(pin + "\n", encoding="utf-8", newline="\n")
    gold_cells = Counter(f"{cells[r['site_id']][0]}/{cells[r['site_id']][1]}" for r in gold)
    seal = {
        "round": number,
        "seed": seed,
        "threshold": THRESHOLD,
        "min_gold": MIN_GOLD,
        "min_emitted": MIN_EMITTED,
        "tier_min": TIER_MIN,
        "gold_sha256": pin,
        "dev_sha256": _sha256(target / DEV_FILE),
        "hard_sha256": _sha256(target / HARD_FILE),
        "gold": len(gold),
        "dev": len(dev),
        "hard": len(hard_now),
        "pool": len(pool),
        "pool_free": len(free),
        "strata": {
            "region/size": dict(sorted(gold_cells.items())),
            "undated_shape": {f"{a}/{b}": n for (a, b), n in sorted(shape.items())},
            "era": dict(sorted(Counter(ERA_BANDS[r["gold_bucket"]] for r in gold).items())),
            "type": dict(sorted(Counter(
                type_group(_stored_type(stored, r["site_id"])) for r in gold).items())),
        },
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }  # fmt: skip
    _write_json(target / SEAL_FILE, seal)
    return {k: seal[k] for k in ("round", "gold", "dev", "hard", "pool", "gold_sha256")}


def _stored_type(stored: Sequence[Mapping[str, Any]], site_id: str) -> str | None:
    for row in stored:
        if str(row["site_id"]) == site_id:
            return row.get("site_type")
    return None


def read_sealed(round_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """SEAL.json and GOLD.jsonl - refused when GOLD.jsonl is not the pinned file."""
    seal = _read_json(round_dir / SEAL_FILE)
    pin = (round_dir / PIN_FILE).read_text(encoding="utf-8").strip()
    if _sha256(round_dir / GOLD_FILE) != pin or pin != seal["gold_sha256"]:
        raise GoldError(f"{round_dir / GOLD_FILE} is not the sealed gold: it was edited")
    return seal, _read_jsonl(round_dir / GOLD_FILE)


# ------------------------------------------------------------------------------ freeze, measure
def freeze(round_dir: Path, code: Mapping[str, str]) -> dict[str, Any]:
    """FROZEN.json: the code a round will be measured with. Refused once the round is measured."""
    if (round_dir / MEASURE_FILE).exists():
        raise GoldError(f"{round_dir} is measured: its frozen code stays as it was")
    read_sealed(round_dir)
    record = {"code": dict(code), "stamp": DT.code_stamp(code),
              "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}  # fmt: skip
    _write_json(round_dir / FROZEN_FILE, record)
    return record


def wilson(successes: int, n: int, z: float = WILSON_Z) -> tuple[float, float]:
    """The Wilson score interval of a proportion."""
    if n == 0:
        return 0.0, 0.0
    p = successes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return round(centre - half, 4), round(centre + half, 4)


def result_row(gold: Mapping[str, Any], decision: DT.Decision) -> dict[str, Any]:
    """One gold site measured: what the extractor decided and whether its bucket is the gold's."""
    emitted = decision.kind in EMITTING and decision.start is not None
    bucket = categorize_period(decision.start) if emitted else None
    span = 100
    if decision.decisive is not None:
        span = max(100, decision.decisive.hi - decision.decisive.lo)
    only_periods = bool(decision.candidates) and all(
        c.kind in (DT.PERIOD, DT.PLEIADES) for c in decision.candidates
    )
    return {
        "site_id": gold["site_id"],
        "stratum": gold["stratum"],
        "gold_year": gold["gold_year"],
        "gold_bucket": gold["gold_bucket"],
        "kind": decision.kind,
        "reason": decision.reason,
        "start": decision.start,
        "bucket": bucket,
        "tier": decision.tier if emitted else None,
        "decisive_kind": decision.decisive.kind if emitted and decision.decisive else None,
        "period_only": emitted and only_periods,
        "correct": emitted and bucket == gold["gold_bucket"],
        "year_agrees": emitted and abs(int(decision.start) - int(gold["gold_year"])) <= span,
        "in_range": emitted
        and decision.lo is not None
        and decision.lo <= int(gold["gold_year"]) <= int(decision.hi),
        "quote": decision.decisive.quote[:400] if emitted and decision.decisive else None,
        "url": decision.decisive.url if emitted and decision.decisive else None,
    }


def metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    emitted = [r for r in rows if r["kind"] in EMITTING and r["start"] is not None]
    correct = sum(1 for r in emitted if r["correct"])
    ranges = [r for r in emitted if r["kind"] == DT.RANGE]

    def group(key: str) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for value in sorted({str(r[key]) for r in emitted}):
            part = [r for r in emitted if str(r[key]) == value]
            ok = sum(1 for r in part if r["correct"])
            out[value] = {"emitted": len(part), "correct": ok,
                          "precision": round(ok / len(part), 4), "wilson": wilson(ok, len(part))}  # fmt: skip
        return out

    period_only = [r for r in emitted if r["period_only"]]
    return {
        "sites": len(rows),
        "emitted": len(emitted),
        "correct": correct,
        "precision": round(correct / len(emitted), 4) if emitted else 0.0,
        "wilson": wilson(correct, len(emitted)),
        "coverage": round(len(emitted) / len(rows), 4) if rows else 0.0,
        "year_agreement": round(sum(1 for r in emitted if r["year_agrees"]) / len(emitted), 4)
        if emitted
        else 0.0,
        "ranges": len(ranges),
        "range_holds_gold": round(sum(1 for r in ranges if r["in_range"]) / len(ranges), 4)
        if ranges
        else None,
        "scope_holds": sum(1 for r in emitted if r["kind"] == DT.SCOPE_HOLD),
        "by_tier": group("tier"),
        "by_decisive_kind": group("decisive_kind"),
        "period_only": {
            "emitted": len(period_only),
            "correct": sum(1 for r in period_only if r["correct"]),
        },
        "abstain_reasons": dict(sorted(Counter(
            str(r["reason"]).split(":")[0] for r in rows if r["kind"] == DT.ABSTAIN).items())),
    }  # fmt: skip


def gold_skip_urls(row: Mapping[str, Any]) -> frozenset[str]:
    """The pages the gold decision itself quoted: never read as tier 4 for that site (the gold
    would measure its own source)."""
    return frozenset(row["provenance"].get("sources") or ())


def measure(round_dir: Path, loaded: Any, code: Mapping[str, str]) -> dict[str, Any]:
    """The frozen extractor over the sealed gold and the hard stratum, once: RESULTS.jsonl and
    MEASURE.json."""
    if (round_dir / MEASURE_FILE).exists():
        raise GoldError(f"{round_dir} is measured: a gold is measured once (draw a new round)")
    seal, gold = read_sealed(round_dir)
    frozen = _read_json(round_dir / FROZEN_FILE)
    if dict(code) != frozen["code"]:
        changed = sorted(k for k in set(code) | set(frozen["code"])
                         if code.get(k) != frozen["code"].get(k))  # fmt: skip
        raise GoldError(f"the extractor is not the frozen code ({', '.join(changed)} changed)")
    hard = _read_jsonl(round_dir / HARD_FILE)
    rows = []
    for item in [*gold, *hard]:
        decision = loaded.decide(item["site_id"], skip_urls=gold_skip_urls(item))
        rows.append(result_row(item, decision))
    _write_jsonl(round_dir / RESULTS_FILE, rows)
    record = {
        "round": seal["round"],
        "code": frozen["code"],
        "stamp": frozen["stamp"],
        "gold_sha256": seal["gold_sha256"],
        "gold": metrics([r for r in rows if r["stratum"] == "gold"]),
        "hard": metrics([r for r in rows if r["stratum"] == "hard"]),
        "results_sha256": _sha256(round_dir / RESULTS_FILE),
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _write_json(round_dir / MEASURE_FILE, record)
    return {"gold": {k: record["gold"][k] for k in ("emitted", "precision", "wilson", "coverage")}}


def judge(seal: Mapping[str, Any], measured: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """Whether the measured gold passes the seal's gate, and every reason it does not."""
    gold = measured["gold"]
    threshold = float(seal["threshold"])
    reasons = []
    if gold["sites"] < seal["min_gold"]:
        reasons.append(f"{gold['sites']} gold sites, the gate needs {seal['min_gold']}")
    if gold["emitted"] < seal["min_emitted"]:
        reasons.append(f"{gold['emitted']} emitted, the gate needs {seal['min_emitted']}")
    if gold["precision"] < threshold:
        reasons.append(f"bucket precision {gold['precision']} < {threshold}")
    parts = {f"tier {t}": v for t, v in gold["by_tier"].items()}
    po = gold["period_only"]
    if po["emitted"]:
        parts["period word alone"] = {"emitted": po["emitted"], "correct": po["correct"],
                                      "precision": round(po["correct"] / po["emitted"], 4)}  # fmt: skip
    for name, part in sorted(parts.items()):
        if part["emitted"] < seal["tier_min"]:
            reasons.append(f"{name}: {part['emitted']} cell(s), too few to judge "
                           f"(< {seal['tier_min']}) - switch it off in dating.CONFIG")  # fmt: skip
        elif part["precision"] < threshold:
            reasons.append(f"{name}: precision {part['precision']} < {threshold} - switch it off "
                           "in dating.CONFIG")  # fmt: skip
    return not reasons, reasons


def verdict(round_dir: Path) -> dict[str, Any]:
    """VERDICT.json of a measured round."""
    if (round_dir / VERDICT_FILE).exists():
        raise GoldError(f"{round_dir / VERDICT_FILE} exists: a round is judged once")
    seal, _gold = read_sealed(round_dir)
    measured = _read_json(round_dir / MEASURE_FILE)
    if _sha256(round_dir / RESULTS_FILE) != measured["results_sha256"]:
        raise GoldError(f"{round_dir / RESULTS_FILE} is not the measured file")
    passed, reasons = judge(seal, measured)
    record = {
        "round": seal["round"],
        "pass": passed,
        "reasons": reasons,
        "code": measured["code"],
        "stamp": measured["stamp"],
        "gold_sha256": seal["gold_sha256"],
        "precision": measured["gold"]["precision"],
        "wilson": measured["gold"]["wilson"],
        "emitted": measured["gold"]["emitted"],
        "coverage": measured["gold"]["coverage"],
        "hard": {k: measured["hard"][k] for k in ("sites", "emitted", "precision", "coverage")},
        "judged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _write_json(round_dir / VERDICT_FILE, record)
    return record


def require_passed(gold_root: Path, code: Mapping[str, str]) -> dict[str, Any]:
    """The passing verdict of the extractor as it is now (`code`): a round whose VERDICT.json passes
    and pins exactly this code, its gold still the sealed file. `GoldError` otherwise - the lane
    writes nothing the gold has not measured (D71)."""
    for round_dir in reversed(rounds(gold_root)):
        path = round_dir / VERDICT_FILE
        if not path.exists():
            continue
        record = _read_json(path)
        if record["pass"] and record["code"] == dict(code):
            read_sealed(round_dir)
            return {"round": record["round"], "precision": record["precision"],
                    "wilson": record["wilson"], "stamp": record["stamp"],
                    "verdict": str(path)}  # fmt: skip
    raise GoldError(
        f"no round under {gold_root} passed with the extractor's current code "
        f"(stamp {DT.code_stamp(code)}): D71 writes only what a sealed gold measured"
    )


# ------------------------------------------------------------------------------ D72
def conflicts(loaded: Any, stored: Sequence[Mapping[str, Any]], out: Path) -> dict[str, Any]:
    """D72: the extractor over every dated shown site; each whose bucket it reads differently from
    the stored one is listed with its quote. Nothing is written to any run."""
    rows = []
    looked = 0
    for row in sorted(stored, key=lambda r: str(r["site_id"])):
        year = _int(row.get("period_start"))
        if year is None or row.get("scope_status") == "retired":
            continue
        if str(row["site_id"]) not in loaded.sites:
            continue
        looked += 1
        decision = loaded.decide(str(row["site_id"]))
        if decision.kind not in EMITTING or decision.start is None:
            continue
        if categorize_period(decision.start) != categorize_period(year):
            rows.append({
                "site_id": row["site_id"], "name": row.get("name"), "stored": year,
                "stored_bucket": categorize_period(year), "extracted": decision.start,
                "extracted_bucket": categorize_period(decision.start), "rule": decision.kind,
                "tier": decision.tier,
                "quote": decision.decisive.quote if decision.decisive else None,
                "url": decision.decisive.url if decision.decisive else None,
            })  # fmt: skip
    _write_jsonl(out, rows)
    return {"dated_sites": looked, "conflicts": len(rows)}


# ------------------------------------------------------------------------------ the CLI
def article_sizes(wiki_cache: Any, site_ids: Iterable[str]) -> dict[str, int | None]:
    """The length of each site's cached English article (None: none)."""
    out: dict[str, int | None] = {}
    for sid in site_ids:
        pages = [p for p in wiki_cache.pages(sid) if p.get("lang") == "en" and not p.get("missing")]
        out[sid] = len(str(pages[0].get("text") or "")) if pages else None
    return out


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    commands = {n: sub.add_parser(n) for n in ("build", "freeze", "measure", "verdict", "conflicts")}
    for name in ("build", "freeze", "measure", "verdict"):
        commands[name].add_argument("--gold", type=Path, default=GOLD_ROOT)
    for name in ("build", "conflicts"):
        commands[name].add_argument("--stored", type=Path, required=True)
    for name in ("build", "measure", "conflicts"):
        commands[name].add_argument("--harvest", type=Path, required=True)
        commands[name].add_argument("--fields-dir", type=Path,
                                    default=REPO / "output" / "remediation" / "fields")  # fmt: skip
    commands["build"].add_argument("--undated", type=Path, required=True)
    commands["build"].add_argument("--seed", type=int, required=True)
    commands["conflicts"].add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            from fields import harvest as H
            from fields import wiki as W

            stored = _read_jsonl(args.stored)
            sites = {s["site_id"]: s for s in H.read_sites(args.harvest)}
            result: Any = build(
                args.gold,
                stored=stored,
                histories=period_histories(args.fields_dir),
                sites=sites,
                sizes=article_sizes(W.WikiCache(), sites),
                undated=[str(r["site_id"]) for r in _read_jsonl(args.undated)],
                seed=args.seed,
            )
        elif args.command == "freeze":
            result = freeze(current_round(args.gold), DT.code_hashes())
        elif args.command == "measure":
            loaded = DT.default_sources(args.harvest, args.fields_dir).load()
            result = measure(current_round(args.gold), loaded, DT.code_hashes())
        elif args.command == "verdict":
            result = verdict(current_round(args.gold))
        else:
            loaded = DT.default_sources(args.harvest, args.fields_dir).load()
            result = conflicts(loaded, _read_jsonl(args.stored), args.out)
    except (GoldError, DT.DatingError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
