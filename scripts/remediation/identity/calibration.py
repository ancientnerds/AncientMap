"""Calibration pools of the identity questions (owner decision D6, 2026-10-08).

Every role passes a calibration before its first answer of a lane: it re-answers cases that were
judged already and is measured against them, with the threshold sealed first
(`calibrate_claude.py`: seal, prepare, compare, verdict). The identity questions are new, so no
earlier judgement is an answer to them - the earlier ones are of other questions (L5 asked whether a
*link* names a site, the scope review whether an entry is a *site*; a modern-town record passes both).
So a pool here is built in two steps, and the gold is always a real model's:

1. **Select** the cases the map names, deterministically (a seed), and export the lane's own
   questions for them into a pool: a stage directory (`ROUNDS.jsonl`, `contexts/r1.jsonl`) plus its
   handoff directory. The earlier judgement of a case (the N7 class of `bcases/names.jsonl`, the
   sample audit's four defects, the scope-e4 decisions, the review's counted `not_a_site`) is kept in
   `POOL.json` as a **hint** and is never in a prompt.
2. **Label**: the pilot judge (role `pilot_judge`, Opus xhigh) answers the pool through the same
   brief (`run.py ... brief --as-role pilot_judge --stage-dir POOL`). Its answers are the recorded
   ones: stamped Opus, `answered_by` `pilot_judge:<batch>`. `status` reports the pool unfit to seal
   until every question has one. A hint that disagrees with the label is listed (`disagreements`) for
   the orchestrator to read, never decided here.

Then the role under test is sealed against the pool, re-answers a copy and is compared:

    PY=./.venv/Scripts/python.exe; C=scripts/remediation/identity/calibration.py; I=scripts/remediation/identity
    CC=scripts/remediation/calibrate_claude.py
    $PY $C export --lane retarget --pool DIR --handoff DIR-h [--seed 20261009]
    $PY $I/run.py --lane retarget brief --stage retarget-web --stage-dir DIR --as-role pilot_judge --round r1 --batch-id r1-b01
    $PY $C status --pool DIR                       # 0 unanswered, or not fit to seal
    $PY $CC seal --id ID --role web_verifier --handoff DIR-h --batches r1-b01 ... --threshold 0.9 --write-verdicts NOT_A_SITE OUT_OF_WINDOW RETARGET RETIRE --max-false-writes 0
    $PY $C prepare --id ID --pool DIR              # the copy the role re-answers
    ...                                   # agents run the brief printed for <root>/ID-run
    $PY $CC compare --id ID
    $PY $CC verdict --id ID --false-sources N

The comparison counts the verdict and every value it writes (the item of a re-target, the year of a
`PERIOD_WRONG`, a new name, a spoken name) as units, and the seal's write verdicts
(`rounds.WRITE_VERDICTS`) with `--max-false-writes 0` fail the verdict on any answer that writes
what the pool does not support. The calibration of a stage is the one made on its own lane's pool:
`run.py import` refuses another lane's calibration and any answer given before the verdict.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(_HERE.parents[1]), str(REPO / "output" / "remediation" / "tools")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

import calibrate_claude as CC  # noqa: E402
import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402
from mechanical.scope_review import parse_export as parse_scope_export  # noqa: E402

from identity import common, export, funnel, names_judge, retarget, scope_judge  # noqa: E402
from identity import rounds as R  # noqa: E402
from identity.prompts import cache_entries, wiki_cache_dir  # noqa: E402
from identity.scope_window import ORIGIN_IMPORT  # noqa: E402
from pipeline.normalizers.dates import E3_CUTOFFS, e3_region  # noqa: E402

POOL_FILE = "POOL.json"
DEFAULT_SEED = 20261009
#: The four records the 2026-09-25 sample audit found to describe a modern place (plans/identity.md).
KNOWN_DEFECTS = {
    "6b978047-cbc3-4901-9d6d-7fb40104f015": "Chania",
    "7b3f1698-60de-4e2f-98cc-f405bfa01478": "Ravenglass",
    "1b68e8c4-22fd-4e5a-8708-92fb516034f0": "Bayston Hill",
    "13120650-2e61-45af-976c-b2e0665c49af": "Alba Fucens",
}
LANES = ("retarget", "scope-window", "names")
POOL_ROLE = "pilot_judge"


class PoolError(ValueError):
    """A pool that cannot be built or is not fit for the step asked. Nothing was written."""


@dataclass(frozen=True)
class PoolCase:
    """One case of a pool: the question's context, where the case comes from and what the earlier
    judgement said (the hint - never part of a prompt)."""

    site_id: str
    context: Mapping[str, Any]
    source: str
    hint: str


def seeded(items: Sequence[Any], seed: int, count: int, key: Any = lambda x: x) -> list[Any]:
    """`count` of `items` (all of them when fewer), the same ones for the same seed."""
    ordered = sorted(items, key=key)
    if len(ordered) <= count:
        return ordered
    return sorted(random.Random(seed).sample(ordered, count), key=key)  # noqa: S311 - a seeded draw


# ------------------------------------------------------------------------------------- retarget
def stub_funnel(row: Mapping[str, Any]) -> dict[str, Any]:
    """A funnel record for a site the funnel did not list: no signal, its first sentence."""
    return {
        "tier": "calibration",
        "p31": [],
        "p31_modern": [],
        "sentence1": funnel.first_sentence(row["description"]),
        "opening_match": None,
        "shared_with": [],
    }


def select_retarget(
    run: Path,
    *,
    root: Path | None = None,
    bcases_names: Path | None = None,
    seed: int = DEFAULT_SEED,
    n7_site: int = 8,
    n7_locality: int = 8,
    clean: int = 12,
) -> list[PoolCase]:
    """The D13 pool: the four audited defects, N7 records of both kinds, and sites the funnel did not
    list (no defect was found for them)."""
    exported = export.load_export(run / common.EXPORT_FILE)
    by_id = common.rows_by_id(exported.shown)
    listed = {r["id"]: r for r in common.read_jsonl(run / "IDENTITY_FUNNEL.jsonl")}
    ext: dict[str, dict[str, list[str]]] = {}
    for e in exported.ext_ids:
        ext.setdefault(e["site_id"], {}).setdefault(e["kind"], []).append(e["value"])
    names = {sid: row["name"] for sid, row in by_id.items()}
    cache = cache_entries(wiki_cache_dir(root))
    bcases = (
        bcases_names or (root or common.main_checkout()) / "output/remediation/bcases/names.jsonl"
    )
    n7 = [r for r in common.read_jsonl(bcases) if r["class"] == "N7" and r["site_id"] in by_id]

    def case(sid: str, source: str, hint: str) -> PoolCase:
        rec = listed.get(sid) or stub_funnel(by_id[sid])
        ctx = retarget.site_context(
            by_id[sid],
            rec,
            ext.get(sid, {}),
            retarget.merge_candidates(sid, rec["shared_with"], exported.pairs, names),
            cache.get(sid, []),
            exported.exported_at,
        )
        return PoolCase(sid, ctx, source, hint)

    cases = [
        case(
            sid,
            f"known-defect:{name}",
            "the sample audit found this record to describe a modern place",
        )
        for sid, name in sorted(KNOWN_DEFECTS.items())
        if sid in by_id
    ]
    taken = {c.site_id for c in cases}
    for kind, count in (("anchor-is-a-site", n7_site), ("anchor-is-locality", n7_locality)):
        pool = [r for r in n7 if r["n7"] == kind and r["site_id"] not in taken]
        for r in seeded(pool, seed, count, key=lambda r: r["site_id"]):
            taken.add(r["site_id"])
            cases.append(
                case(
                    r["site_id"],
                    f"bcases-n7:{kind}",
                    f"bcases N7 {kind} (a code class): stored name {r['name']!r}, English label "
                    f"{r['en_label']!r}, item classes {r['p31']}",
                )
            )
    rest = [sid for sid in by_id if sid not in listed and sid not in taken]
    for sid in seeded(rest, seed, clean):
        cases.append(case(sid, "not-in-funnel", "the funnel found no sign of a modern place"))
    return cases


# ------------------------------------------------------------------------------------ scope window
def snapshot_record(site: Mapping[str, Any], group: str) -> dict[str, Any]:
    """A `SCOPE_WINDOW.jsonl`-shaped record from a row of the scope review's snapshot: the
    discovery's fields, the provenance unknown (`import`)."""
    end = site["period_end"]
    date = end if end else site["period_start"]
    return {
        "id": str(site["id"]),
        "name": site["name"],
        "country": site["country"],
        "site_type": site["site_type"],
        "lat": site["lat"],
        "lon": site["lon"],
        "groups": [group],
        "museum_question": site["site_type"] == "Museum",
        "scope_status": site["scope_status"],
        "scope_reason": site["scope_reason"],
        "period_start": site["period_start"],
        "period_end": end,
        "period_name": None,
        "date_used": date,
        "origin": ORIGIN_IMPORT,
        "recheck_d10": False,
        "period_writes": {},
        "description": " ".join(str(site["excerpt"]).split())[:300],
        "source_url": site["source_url"],
        "images": 0,
    }


def select_scope(
    run: Path,
    *,
    scope_decisions: Path,
    review_snapshot: Path,
    review_answers: Path,
    root: Path | None = None,
    seed: int = DEFAULT_SEED,
    reviewed: int = 12,
) -> list[PoolCase]:
    """The D20 pool: the scope-e4 decisions (a quote-backed keep or retire of a dated entry, 36),
    and the review's counted `not_a_site` answers, over the entries as the review saw them."""
    exported = export.load_export(run / common.EXPORT_FILE)
    ext: dict[str, dict[str, list[str]]] = {}
    for e in exported.ext_ids:
        ext.setdefault(e["site_id"], {}).setdefault(e["kind"], []).append(e["value"])
    cache = cache_entries(wiki_cache_dir(root))
    snapshot = parse_scope_export(review_snapshot.read_text(encoding="utf-8")).by_id()
    decisions = json.loads(scope_decisions.read_text(encoding="utf-8"))["decisions"]

    def case(sid: str, source: str, hint: str) -> PoolCase | None:
        site = snapshot.get(sid)
        if site is None or site["lon"] is None:
            return None
        date = site["period_end"] or site["period_start"]
        region = e3_region(site)
        outside = date is not None and region is not None and date > E3_CUTOFFS[region]
        group = "outside_window" if outside else "calibration"
        record = snapshot_record(site, group)
        ctx = scope_judge.site_context(
            record, ext.get(sid, {}), cache.get(sid, []), exported.exported_at
        )
        return PoolCase(sid, ctx, source, hint)

    cases = []
    for d in sorted(decisions, key=lambda d: d["site_id"]):
        built = case(
            d["site_id"],
            f"scope-e4:{d['rule']}:{d['status']}",
            f"scope-e4 rule {d['rule']} decided {d['status']}: {d.get('note') or d['quote']}",
        )
        if built is not None:
            cases.append(built)
    taken = {c.site_id for c in cases}
    counted = [
        r
        for r in common.read_jsonl(review_answers)
        if r["decision"] == "not_a_site" and r["counted"] and r["site_id"] not in taken
    ]
    for r in seeded(counted, seed, reviewed, key=lambda r: r["site_id"]):
        built = case(
            r["site_id"],
            "scope-review:not_a_site",
            f"counted not_a_site ({r['kind']}): {r['reason']}",
        )
        if built is not None:
            cases.append(built)
    return cases


# ------------------------------------------------------------------------------------------ names
def select_names(
    run: Path, *, root: Path | None = None, seed: int = DEFAULT_SEED, hard: int = 12, comma: int = 8
) -> list[PoolCase]:
    """The D23 pool: records the triage could not repair itself, hard defects and comma-only ones in
    the proportion the triage has them (170 hard, 131 comma-only)."""
    exported = export.load_export(run / common.EXPORT_FILE)
    by_id = common.rows_by_id(exported.shown)
    ext: dict[str, dict[str, list[str]]] = {}
    for e in exported.ext_ids:
        ext.setdefault(e["site_id"], {}).setdefault(e["kind"], []).append(e["value"])
    cache = cache_entries(wiki_cache_dir(root))
    triage = [t for t in common.read_jsonl(run / names_judge.TRIAGE_FILE) if t["needs_model"]]
    cases = []
    for severity, count in (("hard", hard), ("comma_only", comma)):
        for t in seeded(
            [t for t in triage if t["severity"] == severity], seed, count, key=lambda t: t["id"]
        ):
            ctx = names_judge.clean_context(
                t,
                by_id[t["id"]],
                ext.get(t["id"], {}),
                cache.get(t["id"], []),
                exported.exported_at,
            )
            cases.append(
                PoolCase(
                    t["id"],
                    ctx,
                    f"triage:{severity}",
                    f"triage defects {t['defects']}, no repair by rule",
                )
            )
    return cases


# ------------------------------------------------------------------------------------------- pool
def spec_of(lane: str) -> R.StageSpec:
    """The web stage a lane's pool is made of (holders are not needed to render a prompt)."""
    return {
        "retarget": lambda: retarget.web_spec({}),
        "scope-window": scope_judge.web_spec,
        "names": names_judge.clean_spec,
    }[lane]()


def export_pool(
    pool: Path, lane: str, handoff: Path, cases: Sequence[PoolCase], *, seed: int
) -> dict[str, Any]:
    """Export the lane's questions for `cases` into `pool` (a stage directory) and `handoff`, and
    keep each case's source and hint beside them (`POOL.json`). Refused for an empty pool."""
    if not cases:
        raise PoolError("the pool selected no case")
    spec = spec_of(lane)
    record = R.export_round(pool, spec, handoff, [R.Question(c.site_id, c.context) for c in cases])
    manifest = {
        "lane": lane,
        "stage": spec.stage,
        "seed": seed,
        "handoff": handoff.as_posix(),
        "batches": sorted(record.batches),
        "cases": [{"site_id": c.site_id, "source": c.source, "hint": c.hint} for c in cases],
    }
    (pool / POOL_FILE).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return {"questions": len(cases), "batches": len(record.batches), "handoff": str(handoff)}


def load_manifest(pool: Path) -> dict[str, Any]:
    path = pool / POOL_FILE
    if not path.exists():
        raise PoolError(f"{path} does not exist: export the pool first")
    return json.loads(path.read_text(encoding="utf-8"))


def status(pool: Path) -> dict[str, Any]:
    """Whether the pool is fit to seal: every question answered, by the pilot judge, in shape."""
    manifest = load_manifest(pool)
    check = OH.validate(Path(manifest["handoff"]))
    wrong = []
    for line in OH.manifest(Path(manifest["handoff"])):
        path = Path(manifest["handoff"]) / line["answer_path"]
        if path.exists():
            answer = json.loads(path.read_text(encoding="utf-8"))
            if RO.role_of(answer["answered_by"]) != POOL_ROLE:
                wrong.append(line["label"])
    problems = check.to_dict()
    return {
        "questions": problems["questions"],
        "answered": problems["answered"],
        "unanswered": [m["label"] for m in problems["missing"]],
        "stale_or_malformed": len(problems["stale"]) + len(problems["malformed"]),
        "not_the_pilot_judge": wrong,
        "fit_to_seal": check.ok and not wrong,
    }


def disagreements(pool: Path) -> list[dict[str, Any]]:
    """The labelled cases whose label is not what the hint suggests, for the orchestrator to read."""
    manifest = load_manifest(pool)
    handoff = Path(manifest["handoff"])
    out = []
    labels: dict[str, str] = {}
    for line in OH.manifest(handoff):
        path = handoff / line["answer_path"]
        if path.exists():
            labels[line["label"]] = json.loads(
                json.loads(path.read_text(encoding="utf-8"))["text"]
            )["verdict"]
    for case in manifest["cases"]:
        verdict = labels.get(case["site_id"])
        if (
            verdict is not None
            and _hint_verdicts(case["source"])
            and verdict not in _hint_verdicts(case["source"])
        ):
            out.append(
                {
                    **case,
                    "label": verdict,
                    "expected_one_of": sorted(_hint_verdicts(case["source"])),
                }
            )
    return out


#: The verdicts an earlier judgement makes likely, by the prefix of a case's source - a sanity check
#: on the label, never a gold. A source that is not listed expects nothing.
HINT_VERDICTS = (
    ("known-defect:", {"RETARGET", "MERGE"}),
    ("bcases-n7:anchor-is-locality", {"RETARGET", "RETIRE", "MERGE"}),
    ("bcases-n7:anchor-is-a-site", {"KEEP"}),
    ("not-in-funnel", {"KEEP"}),
    ("scope-e4:d:in_scope", {"MUSEUM_KEEP"}),
    ("scope-e4:d:retired", {"OUT_OF_WINDOW", "NOT_A_SITE"}),
    ("scope-e4:a:pending", {"PERIOD_WRONG"}),
    ("scope-e4:b:retired", {"OUT_OF_WINDOW", "NOT_A_SITE"}),
    ("scope-review:not_a_site", {"NOT_A_SITE"}),
)


def _hint_verdicts(source: str) -> set[str]:
    for prefix, verdicts in HINT_VERDICTS:
        if source.startswith(prefix):
            return verdicts
    return set()


def prepare(root: Path, calibration_id: str, pool: Path) -> dict[str, Any]:
    """`calibrate_claude.prepare` on the sealed pool, then the copy's contexts: the copy is the stage
    directory the role under test is briefed from (`run.py ... --stage-dir <root>/<id>-run`)."""
    summary = CC.prepare(root, calibration_id=calibration_id, run=pool)
    copy_run = Path(summary["calibration_run"])
    shutil.copytree(pool / R.CONTEXTS_DIR, copy_run / R.CONTEXTS_DIR)
    return {**summary, "stage_dir": str(copy_run)}


# ---------------------------------------------------------------------------------------------- CLI
def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--root", type=Path, default=None, help="the main checkout")
    sub = parser.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("export", help="select the cases and export the lane's questions")
    exp.add_argument("--lane", required=True, choices=LANES)
    exp.add_argument("--pool", required=True, type=Path)
    exp.add_argument("--handoff", required=True, type=Path)
    exp.add_argument("--seed", type=int, default=DEFAULT_SEED)
    for name in ("status", "disagreements"):
        sub.add_parser(name).add_argument("--pool", required=True, type=Path)
    prep = sub.add_parser("prepare", help="the sealed pool's copy and its contexts")
    prep.add_argument("--id", required=True, dest="calibration_id")
    prep.add_argument("--pool", required=True, type=Path)
    prep.add_argument("--calibration-root", type=Path, default=CC.CALIBRATION_ROOT)
    args = parser.parse_args(list(argv) if argv is not None else None)
    run = args.run_dir or common.run_dir()
    root = args.root or common.main_checkout()
    try:
        if args.command == "export":
            remediation = root / "output" / "remediation"
            if args.lane == "retarget":
                cases = select_retarget(run, root=root, seed=args.seed)
            elif args.lane == "scope-window":
                cases = select_scope(
                    run,
                    scope_decisions=remediation / "mechanical_scope" / "DECISIONS.json",
                    review_snapshot=remediation / "mechanical_scope_review" / "SNAPSHOT_R0.jsonl",
                    review_answers=remediation / "mechanical_scope_review" / "NONSITE_R0.jsonl",
                    root=root,
                    seed=args.seed,
                )
            else:
                cases = select_names(run, root=root, seed=args.seed)
            payload: Any = export_pool(
                args.pool.resolve(), args.lane, args.handoff.resolve(), cases, seed=args.seed
            )
        elif args.command == "status":
            payload = status(args.pool)
        elif args.command == "disagreements":
            payload = disagreements(args.pool)
        else:
            payload = prepare(args.calibration_root, args.calibration_id, args.pool)
    except (
        PoolError,
        R.RoundError,
        CC.CalibrationError,
        common.IdentityError,
        OH.HandoffError,
    ) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))
    return 0 if args.command != "status" or payload["fit_to_seal"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
