"""HUMAN_ONLY B2-L: the two country cells the B2 classifier found wrong - the `country-b2` lane.

## The decision

`output/remediation/HUMAN_ONLY_DECISIONS_2026-09-26.md`, B2-L, decided on 2026-09-26 under the
owner's O9 ("nach meiner Empfehlung entscheiden"): Achladia `Germany -> Greece`, Delphinion
`Greece -> Türkiye`. The B2 classifier (`scripts/remediation/bcases/`, `bcases/b2.jsonl`) had
listed both as "falsches Land" with the way "eine mechanische Länder-Lane"; no lane writes
`country` since. The two pairs live in `lane.COUNTRY_B2_DECISIONS`, the lane owns exactly their
new values, and every row carries its point as its premise (guard 5).

## How a row is decided (`classify_b2`, first failure refuses)

1. the row exists, is curated and is not retired; 2. it still holds the decided old value; 3. its
   `country` journal ends at that value (`journal_break`: nothing wrote it around the journal);
4. the decided value is canonical in the census T05 vocabulary (`COUNTRY_CODES` or
   `normalize_country` knows it) and resolves to an ISO code;
5. **Natural Earth** - the premise the decision rests on ("Prämisse = gespeicherter Punkt"): the
   stored point lies inside the decided country's admin-0 polygon or within T02's 1000 m of it
   (`plan._geography`);
6. the row's item, where it states them, must not contradict: a decisive **`P17`** must resolve to
   the decided ISO code (`plan.check_wikidata`), a non-deprecated **`P625`** must lie in the decided
   country too - the B2 classifier's route, "point and P625 agree". An item that states neither
   (Delphinion's Q2677787 is the class "ancient sanctuaries dedicated to Apollo Delphinius", its
   only P625 deprecated - a link L5 reads) leaves the point as the one witness, as decided.

A refused row is listed in `SKIPPED.jsonl` with its reason and is not written.

`--collect` reads production (read-only) and asks Wikidata (`wbgetentities` through the
`mechanical.plan` helpers, with this lane's `USER_AGENT` - no contact address, no name, the standing
rule of the 2026-09-26 finish) into `output/remediation/cache/mechanical_country_b2_witnesses.json`;
`--write` reads production (read-only) again and writes `PLAN.jsonl`, `SKIPPED.jsonl`, `PLAN.md`
and `ROLLBACK.sql` into `output/remediation/mechanical_country_b2/`. Nothing is written to
production here: `apply.py --lane country-b2` renders, rehearses, probes and runs the transaction.

`card_stats.civilization` follows the site's country only through the next card_stats wave
(`card_stats.py`, a lane of its own): the read-back counts the cards that differ, as the UK lane's.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

import research_web  # noqa: E402
from census.tests.t05_country_values import _is_canonical, _iso, _vocabulary  # noqa: E402

from mechanical import plan as P  # noqa: E402
from mechanical.lane import COUNTRY_B2, COUNTRY_B2_DECISIONS  # noqa: E402
from pipeline.utils.geo import haversine_distance  # noqa: E402

log = logging.getLogger("mechanical.country_b2")

LANE = COUNTRY_B2
DEFAULT_OUT = REPO / "output" / "remediation" / LANE.out_dir_name
DEFAULT_CACHE = REPO / "output" / "remediation" / "cache"
WITNESS_FILE = "mechanical_country_b2_witnesses.json"
DECISION_SOURCE = "output/remediation/HUMAN_ONLY_DECISIONS_2026-09-26.md"
RULE = "b2-decided-country"
#: Every web request of the WE lanes names itself with the lanes' one User-Agent, nothing personal.
USER_AGENT = research_web.USER_AGENT

#: `(country, lat, lon) -> (inside, note, evidence)`: `plan._geography` over Natural Earth,
#: injected so the decision is testable without the geo stack the CI job does not install.
Geography = Callable[[str, float, float], tuple[bool, str, dict[str, Any] | None]]


@dataclass(frozen=True)
class Candidate:
    """One decided row as production holds it now."""

    site: P.Site
    decided_old: str
    decided_new: str
    scope_status: str | None
    premise: str | None
    qid: str | None
    journal: tuple[P.JournalLink, ...] = ()


def candidate_sql() -> str:
    ids = P.sql_ids(site for site, _name, _old, _new in COUNTRY_B2_DECISIONS)
    return (
        "SELECT u.id::text AS id, u.name, u.country, u.lat::text AS lat, u.lon::text AS lon, "
        f"u.source_id, u.scope_status, {LANE.premise_sql} AS premise, "
        "(SELECT e.value FROM site_external_ids e WHERE e.site_id = u.id "
        "AND e.kind = 'wikidata_qid') AS qid "
        f"FROM unified_sites u WHERE u.id::text IN ({ids}) ORDER BY u.id"
    )


def load_candidates(reader: Callable[[str], list[dict[str, Any]]]) -> list[Candidate]:
    """The decided rows, read from production with their item and `country` journal. Read-only."""
    rows = {str(r["id"]): r for r in reader(candidate_sql())}
    journal = P.load_journal(reader, LANE.column, list(rows))
    out: list[Candidate] = []
    for site_id, name, old, new in COUNTRY_B2_DECISIONS:
        row = rows.get(site_id)
        if row is None:
            raise P.PlanError(f"{name} ({site_id}) is not in unified_sites")
        out.append(
            Candidate(
                site=P.Site(
                    site_id=site_id,
                    name=str(row["name"]),
                    country=row["country"],
                    lat=None if row["lat"] is None else float(row["lat"]),
                    lon=None if row["lon"] is None else float(row["lon"]),
                    source_id=str(row["source_id"]),
                ),
                decided_old=old,
                decided_new=new,
                scope_status=row["scope_status"],
                premise=row["premise"],
                qid=row["qid"],
                journal=journal.get(site_id, ()),
            )
        )
    return out


# ------------------------------------------------------------------------------ the decision
def classify_b2(
    candidate: Candidate,
    *,
    codes: Mapping[str, str],
    normalize: Any,
    witnesses: Mapping[str, Any],
    countries: Mapping[str, Any],
    geography: Geography,
) -> P.Verdict:
    """Decide one row. Every check is named, and the first failure is the reason."""
    site = candidate.site
    new = candidate.decided_new

    def verdict(ok: bool, reason: str, note: str, evidence: Sequence[dict[str, Any]]) -> P.Verdict:
        return P.Verdict(
            site_id=site.site_id,
            site_name=site.name,
            ok=ok,
            old_value=site.country,
            new_value=new,
            rule=RULE if ok else "",
            reason=reason,
            note=note,
            phase3=False,
            finding_test_id="B2/country",
            evidence=tuple(evidence),
            premise=candidate.premise if ok else None,
        )

    decision = {
        "source": DECISION_SOURCE,
        "url": None,
        "quote": f"B2-L: {site.name} {candidate.decided_old} -> {new} (O9, 2026-09-26)",
    }
    if site.source_id != P.CURATED_SOURCE:
        return verdict(False, "row-not-in-curated-source", f"source_id={site.source_id!r}", ())
    if candidate.scope_status == "retired":
        return verdict(
            False, "retired", "the site is retired - hidden, nothing of it is written", ()
        )
    if site.country != candidate.decided_old:
        return verdict(
            False,
            "stored-value-moved",
            f"the row holds {site.country!r}, the decision replaces {candidate.decided_old!r}",
            (),
        )
    broken = P.journal_break(candidate.journal, site.country)
    if broken is not None:
        return verdict(False, broken[0], broken[1], ())
    if site.lat is None or site.lon is None or candidate.premise is None:
        return verdict(False, "no-point", "the row carries no point to locate", ())
    iso = _iso(new, normalize)
    if not _is_canonical(new, codes, normalize) or iso is None:
        return verdict(
            False,
            "not-canonical",
            f"{new!r} is not a value the census T05 vocabulary knows with an ISO code",
            (),
        )
    inside, geo_note, geo = geography(new, site.lat, site.lon)
    if not inside or geo is None:
        return verdict(False, "outside-new-country", geo_note, ())
    witness = witnesses.get(candidate.qid) if candidate.qid is not None else None
    if candidate.qid is not None and witness is None:
        return verdict(False, "witness-missing", f"{candidate.qid} is not in the witness file", ())
    evidence: list[dict[str, Any]] = [decision, geo]
    notes = [f"the stored point lies in {new} (Natural Earth)"]
    if witness is not None and witness["p17"]:
        ok, note, p17 = P.check_wikidata(
            P.Anchor(str(candidate.qid), "site_external_ids:wikidata_qid"),
            {**witness, "countries": countries},
            iso,
        )
        if ok is False or p17 is None:
            return verdict(False, "wikidata-p17", note, ())
        evidence.append(p17)
        notes.append(f"{candidate.qid} P17 agrees")
    else:
        notes.append(f"{candidate.qid or 'no item'} states no P17")
    point = witness.get("p625") if witness is not None else None
    if point:
        lat, lon = float(point[0]), float(point[1])
        agrees, where, _ = geography(new, lat, lon)
        if not agrees:
            return verdict(
                False,
                "wikidata-p625-elsewhere",
                f"{candidate.qid} P625 ({lat}, {lon}) does not lie in {new}: {where}",
                (),
            )
        metres = 1000.0 * haversine_distance(site.lat, site.lon, lat, lon)
        evidence.append(
            {
                "source": f"wikidata:{candidate.qid}:P625",
                "url": f"https://www.wikidata.org/entity/{candidate.qid}",
                "retrieved_at": witness.get("fetched_at") if witness is not None else None,
                "quote": f"{candidate.qid} P625 ({lat}, {lon}) lies in {new}, {metres:.0f} m "
                f"from the stored point",
            }
        )
        notes.append(f"{candidate.qid} P625 lies in {new}, {metres:.0f} m away")
    else:
        notes.append(f"{candidate.qid or 'no item'} states no (non-deprecated) P625")
    return verdict(
        True, "", f"{candidate.decided_old} -> {new}: " + "; ".join(notes), tuple(evidence)
    )


def build_b2_plan(
    candidates: Sequence[Candidate],
    *,
    codes: Mapping[str, str],
    normalize: Any,
    witnesses: Mapping[str, Any],
    countries: Mapping[str, Any],
    geography: Geography,
    built_at: str,
) -> P.Plan:
    """A pure function of its inputs: no network, no database, no clock of its own."""
    verdicts = [
        classify_b2(
            c,
            codes=codes,
            normalize=normalize,
            witnesses=witnesses,
            countries=countries,
            geography=geography,
        )
        for c in sorted(candidates, key=lambda c: c.site.site_id)
    ]
    changes = tuple(v for v in verdicts if v.ok)
    skipped = tuple(v for v in verdicts if not v.ok)
    counters = {
        "candidates": len(verdicts),
        "changes": len(changes),
        "skipped": len(skipped),
        **{f"skip:{k}": n for k, n in sorted(Counter(s.reason for s in skipped).items())},
    }
    return P.Plan(changes=changes, skipped=skipped, built_at=built_at, counters=counters, lane=LANE)


# ------------------------------------------------------------------------------ the witnesses
def collect_witnesses(qids: Sequence[str], *, fetched_at: str) -> dict[str, Any]:
    """P17 and P625 per item, P297 and label per country it names. One attempt per request."""
    if not qids:
        raise P.PlanError("no Wikidata item to collect")
    entities = P.fetch_entities(qids, "claims", user_agent=USER_AGENT)
    out = {
        qid: {
            "p17": P._p17_claims(entity),
            "p625": list(P._coordinate(entity) or ()) or None,
            "fetched_at": fetched_at,
        }
        for qid, entity in sorted(entities.items())
    }
    countries = sorted({str(c["id"]) for record in out.values() for c in record["p17"]})
    return {
        "generated_at": fetched_at,
        "user_agent": USER_AGENT,
        "query": "action=wbgetentities&props=claims",
        "entities": out,
        "countries": P.country_codes(countries, user_agent=USER_AGENT),
    }


# ------------------------------------------------------------------------------ the output
def write_plan_md(plan: P.Plan, path: Path, witnesses: Mapping[str, Any]) -> None:
    lines = [
        "# B2-L - the two decided country cells: plan",
        "",
        f"Built {plan.built_at} by `scripts/remediation/mechanical/country_b2.py`. Lane "
        f"`{LANE.name}`, run stamp `{plan.run_stamp}`, journal test id `{plan.test_id}`. Decision: "
        f"`{DECISION_SOURCE}`, B2-L (O9, 2026-09-26). Witnesses: Wikidata, "
        f"{witnesses.get('generated_at')}, User-Agent `{witnesses.get('user_agent')}`.",
        "",
        f"**{len(plan.changes)} row(s) will be written, {len(plan.skipped)} refused.**",
        "",
        "| site | stored | written | premise (the stored point) |",
        "|---|---|---|---|",
    ]
    for change in plan.changes:
        lines.append(
            f"| {change.site_name} (`{change.site_id}`) | `{change.old_value}` | "
            f"`{change.new_value}` | `{change.premise}` |"
        )
    lines += ["", "## Evidence per row", ""]
    for change in plan.changes:
        lines.append(f"* **{change.site_name}**")
        lines += [f"  * {e['source']}: {e['quote']}" for e in change.evidence]
    if plan.skipped:
        lines += ["", "## Refused", "", "| site | reason | note |", "|---|---|---|"]
        lines += [f"| {v.site_name} | `{v.reason}` | {v.note} |" for v in plan.skipped]
    lines += [
        "",
        "## Run it (the orchestrator's job, in this order)",
        "",
        "```bash",
        "PY=./.venv/Scripts/python.exe",
        "$PY scripts/remediation/mechanical/country_b2.py --collect   # read-only + Wikidata",
        "$PY scripts/remediation/mechanical/country_b2.py --write     # read-only",
        f"$PY scripts/remediation/mechanical/apply.py --lane {LANE.name} --emit",
        f"$PY scripts/remediation/mechanical/apply.py --lane {LANE.name} --rehearse",
        f"$PY scripts/remediation/mechanical/apply.py --lane {LANE.name} --probe-guards",
        f"$PY scripts/remediation/mechanical/apply.py --lane {LANE.name} --apply",
        f"$PY scripts/remediation/mechanical/apply.py --lane {LANE.name} --verify",
        f"$PY scripts/remediation/mechanical/apply.py --lane {LANE.name} --rehearse-rollback",
        "```",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def natural_earth() -> Geography:
    """`plan._geography` over the census's Natural Earth countries (needs the geo stack)."""
    atlas, retrieved = P._atlas()

    def locate(country: str, lat: float, lon: float) -> tuple[bool, str, dict[str, Any] | None]:
        return P._geography(atlas, country, lat, lon, retrieved)

    return locate


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Plan the B2-L country cells (mechanical lane)")
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument(
        "--collect", action="store_true", help="the Wikidata witnesses (network; reads prod)"
    )
    ap.add_argument(
        "--write",
        action="store_true",
        help="write PLAN.jsonl, SKIPPED.jsonl, PLAN.md, ROLLBACK.sql (reads prod)",
    )
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    witness_path = args.cache / WITNESS_FILE
    try:
        if args.collect:
            candidates = load_candidates(P.psql_json_reader())
            qids = sorted({c.qid for c in candidates if c.qid is not None})
            payload = collect_witnesses(qids, fetched_at=P._now())
            witness_path.parent.mkdir(parents=True, exist_ok=True)
            witness_path.write_text(
                json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            log.info("wrote %s (%d items)", witness_path, len(payload["entities"]))
            return 0
        if not args.write:
            ap.print_help()
            return 0
        if not witness_path.exists():
            raise P.PlanError(f"{witness_path} is missing - run country_b2.py --collect first")
        witnesses = json.loads(witness_path.read_text(encoding="utf-8"))
        codes, normalize = _vocabulary()
        plan = build_b2_plan(
            load_candidates(P.psql_json_reader()),
            codes=codes,
            normalize=normalize,
            witnesses=witnesses["entities"],
            countries=witnesses["countries"],
            geography=natural_earth(),
            built_at=P._now(),
        )
    except P.PlanError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    P.write_plan_jsonl(plan, args.out / "PLAN.jsonl")
    P.write_skipped_jsonl(plan, args.out / "SKIPPED.jsonl")
    write_plan_md(plan, args.out / "PLAN.md", witnesses)
    # ROLLBACK before APPLY: apply.py --emit refuses to write an apply without its undo.
    P.write_rollback_sql(plan, args.out / "ROLLBACK.sql", plan_path=args.out / "PLAN.jsonl")
    print(json.dumps(dict(plan.counters), indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
