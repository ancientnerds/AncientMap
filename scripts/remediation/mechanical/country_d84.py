"""Owner decisions D84 and D149: the Baltic Sea Anomaly holds no country - a `country-d84-<wave>` lane.

## The decision

`output/remediation/OWNER_DECISIONS_2026-10-08.md`. D84 (2026-11-05): "D50 country of the Baltic
Sea Anomaly - Empty / international waters, no country page." D149 (2026-11-10): "Baltic Sea
Anomaly without a country (D84) has no /sites/ page at all - Globe only: no route without a
country." The site (`c8d2c13e`, one of the six D50 sites) holds `country = 'Baltic Sea'`, which no
journalled lane wrote (read on production 2026-11-11). Shown with it, it would get the page
`/sites/baltic-sea/...` and a country hub; shown without a country it is a dot on the globe, and
the site pages, the country hubs, the sitemap and IndexNow leave it out (each reads
`pipeline.utils.public_sites.curated_page`: curated, with a country, not retired).

The site and the value it held live in `lane.D84_NO_COUNTRY_SITES`. The lane
(`identity_lanes.country_d84_lane`) is a cell lane whose one column may be emptied
(`Column.clears`): it writes NULL and owns no value, its invariant refuses inside the transaction
a planned site that keeps a country or that D84 does not name, and every row carries its name,
its point and its scope status as its premise (guard 5).

## The order, and what holds it

The site is retired while this lane writes it, and that is the order the decisions ask for: the
un-retire (`scope_unretire.py`, `scope-unretire-<wave>`) shows a D84 site only without a country
(`d84-country-not-cleared` until then, and the same test in its invariant), and its premise holds
the country, so its export is read after this lane's apply. The undo runs the other way round:
retire the site again (the un-retire's `ROLLBACK.sql`) before this lane's `ROLLBACK.sql` gives
the country back. That order is a guard, not a sentence: only a retired row is planned
(`row-not-retired`) and the premise holds `scope_status`, so guard 5 refuses this lane's
`ROLLBACK.sql` while the site is shown - a wrong-order undo commits nothing, and no file of the
lane leaves a D84 site shown with a country.

## Waves

A lane like every wave lane: `--write --wave <label>` plans into
`output/remediation/mechanical_country_d84/<label>/` for `apply.py --lane country-d84-<label>`
(stamp `<label>_mechanical-country-d84`). A stamp is applied once and a wave that has journalled
a row is never re-planned, so a write that was undone is made again under the next label: after
both reversals the row holds the country again and its journal ends there, which is all a new
wave asks.

## How the row is decided (`classify`, the first failure refuses)

1. the row is curated; 2. it is still named as the decision names it (a re-targeted record, D13,
   is another subject); 3. it holds the country the decision empties - a row that holds none is
   listed `already-empty`, one that holds another value `stored-value-moved`; 4. it is retired
   (`row-not-retired`: the reversal of a write on a shown site would show it with a country); 5.
   its `country` journal ends at that value (`plan.journal_break`: nothing wrote it around the
   journal).

A refused row is listed in `SKIPPED.jsonl` with its reason and is not written. A row the read
does not return, and a wave that has journalled a row already, stop the plan.

`--write --wave <label>` reads production (read-only, one snapshot), keeps the read as
`READ.jsonl` and writes `PLAN.jsonl`, `SKIPPED.jsonl`, `PLAN.md` and `ROLLBACK.sql` into the
wave's directory. Nothing is written to production here: `apply.py --lane country-d84-<label>`
renders, rehearses, probes and runs the transaction.

`card_stats.civilization` follows the site's country only through a card_stats wave
(`card_stats.py`), which never empties a column: it lists this site `new-value-null`, and the
read-back counts the card that differs.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from prod_write import send  # noqa: E402

from mechanical import plan as P  # noqa: E402
from mechanical.identity_lanes import (  # noqa: E402
    COUNTRY_D84_LANE,
    COUNTRY_D84_ROOT,
    COUNTRY_D84_TEST_ID,
    country_d84_lane,
)
from mechanical.lane import D84_NO_COUNTRY_SITES, Lane, sql_literal  # noqa: E402
from pipeline.utils.public_sites import RETIRED  # noqa: E402

DEFAULT_OUT = REPO / "output" / "remediation" / COUNTRY_D84_ROOT
DECISION_SOURCE = "output/remediation/OWNER_DECISIONS_2026-10-08.md"
RULE = "d84-no-country"
#: The two decisions, as the decisions file words them: every planned row's evidence.
DECISIONS: tuple[dict[str, Any], ...] = (
    {
        "source": DECISION_SOURCE,
        "url": None,
        "quote": "D84 (2026-11-05): D50 country of the Baltic Sea Anomaly - Empty / international "
        "waters, no country page (rec).",
    },
    {
        "source": DECISION_SOURCE,
        "url": None,
        "quote": "D149 (2026-11-10): Baltic Sea Anomaly without a country (D84) has no /sites/ "
        "page at all - Globe only (rec): no route without a country.",
    },
)


# ------------------------------------------------------------------------------ the read
def read_parts(lane: Lane) -> tuple[tuple[str, str], ...]:
    """What the plan reads, each part one query of one read-only snapshot: the decided rows with
    their premise, their `country` journal, and the journal rows this wave's stamps hold."""
    ids = P.sql_ids(D84_NO_COUNTRY_SITES)
    site = (
        "SELECT u.id::text AS id, u.name, u.country, u.source_id, u.scope_status, "
        f"{lane.premise_sql} AS premise FROM unified_sites u WHERE u.id::text IN ({ids}) "
        "ORDER BY u.id"
    )
    journal = (
        "SELECT id, row_pk, run_stamp, coalesce(test_id, '') AS test_id, old_value, new_value "
        "FROM remediation_change_log WHERE table_name = 'unified_sites' "
        f"AND column_name = 'country' AND row_pk IN ({ids}) ORDER BY id"
    )
    stamps = (
        "SELECT run_stamp, count(*) AS n FROM remediation_change_log WHERE run_stamp IN ("
        + ", ".join(sql_literal(stamp) for stamp in (lane.run_stamp, lane.rollback_run_stamp))
        + ") GROUP BY run_stamp ORDER BY run_stamp"
    )
    return (("site", site), ("journal", journal), ("stamp", stamps))


def read_production(script: str) -> str:
    """Send the read-only export to production and return its output as it came."""
    proc = send(script, rows=True, timeout=900)
    if proc.returncode != 0:
        raise P.PlanError(f"the read failed (psql exit {proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout


# ------------------------------------------------------------------------------ the decision
def classify(site_id: str, row: Mapping[str, Any], journal: Sequence[P.JournalLink]) -> P.Verdict:
    """Decide one decided row. Every check is named, and the first failure is the reason."""
    name, held = D84_NO_COUNTRY_SITES[site_id]

    def verdict(ok: bool, reason: str, note: str) -> P.Verdict:
        return P.Verdict(
            site_id=site_id,
            site_name=str(row["name"]),
            ok=ok,
            old_value=row["country"],
            new_value=None,
            rule=RULE if ok else "",
            reason=reason,
            note=note,
            phase3=False,
            finding_test_id=COUNTRY_D84_TEST_ID,
            evidence=DECISIONS if ok else (),
            premise=str(row["premise"]) if ok else None,
            column="country",
        )

    if row["source_id"] != P.CURATED_SOURCE:
        return verdict(False, "row-not-in-curated-source", f"source_id={row['source_id']!r}")
    if row["name"] != name:
        return verdict(
            False,
            "name-moved",
            f"the row is named {row['name']!r}; D84 decides the country of {name!r}",
        )
    if row["country"] is None:
        return verdict(False, "already-empty", "the row holds no country")
    if row["country"] != held:
        return verdict(
            False,
            "stored-value-moved",
            f"the row holds {row['country']!r}, the decision empties {held!r}",
        )
    if row["scope_status"] != RETIRED:
        return verdict(
            False,
            "row-not-retired",
            f"scope_status is {row['scope_status']!r}: the lane writes a D84 site while it is "
            "retired - its ROLLBACK.sql gives the country back, and a D84 site is shown only "
            "without one",
        )
    broken = P.journal_break(journal, row["country"])
    if broken is not None:
        return verdict(False, broken[0], broken[1])
    return verdict(
        True,
        "",
        f"country {held!r} -> NULL: international waters, no country page and no /sites/ route "
        "(D84, D149)",
    )


def build_plan(text: str, *, built_at: str, lane: Lane) -> P.Plan:
    """The plan of one read (`read_parts`' output) for one wave's lane. A pure function of the
    read: no network, no database, no clock of its own."""
    rows, _read_at = P.parse_tagged_export(text, (kind for kind, _sql in read_parts(lane)))
    written = {str(r["run_stamp"]): int(r["n"]) for r in rows["stamp"] if int(r["n"])}
    if written:
        raise P.PlanError(
            f"{written} journal row(s) exist for {lane.name}: a wave that has written is never "
            "re-planned - its ROLLBACK.sql may be the only undo; a write that was undone is "
            "planned again under the next wave label"
        )
    sites = {str(r["id"]): r for r in rows["site"]}
    journal: dict[str, list[P.JournalLink]] = {}
    for r in rows["journal"]:
        journal.setdefault(str(r["row_pk"]), []).append(
            P.JournalLink(
                int(r["id"]), str(r["run_stamp"]), str(r["test_id"]), r["old_value"], r["new_value"]
            )
        )
    verdicts = []
    for site_id, (name, _held) in sorted(D84_NO_COUNTRY_SITES.items()):
        if site_id not in sites:
            raise P.PlanError(f"{name} ({site_id}) is not in unified_sites")
        verdicts.append(classify(site_id, sites[site_id], journal.get(site_id, ())))
    changes = tuple(v for v in verdicts if v.ok)
    skipped = tuple(v for v in verdicts if not v.ok)
    counters = {
        "candidates": len(verdicts),
        "changes": len(changes),
        "skipped": len(skipped),
        **{f"skip:{k}": n for k, n in sorted(Counter(s.reason for s in skipped).items())},
    }
    return P.Plan(changes=changes, skipped=skipped, built_at=built_at, counters=counters, lane=lane)


# ------------------------------------------------------------------------------ the output
def write_plan_md(plan: P.Plan, path: Path) -> None:
    lane = plan.lane
    lines = [
        "# D84 - the Baltic Sea Anomaly holds no country: plan",
        "",
        f"Built {plan.built_at} by `scripts/remediation/mechanical/country_d84.py`. Lane "
        f"`{lane.name}`, run stamp `{plan.run_stamp}`, journal test id `{plan.test_id}`. Decisions: "
        f"`{DECISION_SOURCE}`, D84 (2026-11-05) and D149 (2026-11-10). Premise (guard 5): "
        f"`{lane.premise_sql}`.",
        "",
        f"**{len(plan.changes)} row(s) will be written, {len(plan.skipped)} refused.**",
        "",
        "| site | stored | written | premise (name, point and scope status) |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {c.site_name} (`{c.site_id}`) | `{c.old_value}` | NULL | `{c.premise}` |"
        for c in plan.changes
    ]
    if plan.skipped:
        lines += ["", "## Refused", "", "| site | reason | note |", "|---|---|---|"]
        lines += [f"| {v.site_name} | `{v.reason}` | {v.note} |" for v in plan.skipped]
    lines += [
        "",
        "## Run it (in this order, before the un-retire wave of the site)",
        "",
        "Undo: the un-retire wave's `ROLLBACK.sql` first, then this directory's - guard 5 refuses "
        "it while the site is shown.",
        "",
        "```bash",
        "PY=./.venv/Scripts/python.exe",
        "A=scripts/remediation/mechanical/apply.py",
        *(
            f"$PY $A --lane {lane.name} --{step}"
            for step in (
                "check-primitive",
                "verify",
                "emit",
                "rehearse",
                "probe-guards",
                "apply",
                "verify",
                "rehearse-rollback",
            )
        ),
        "```",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def write(out: Path, wave: str, *, read: Callable[[str], str], built_at: str) -> dict[str, Any]:
    """Read production (read-only) and write the wave's plan files into `out/<wave>/` (with the
    default `out` the lane's own directory, where `apply.py --lane country-d84-<wave>` reads
    them). Refused when the wave holds a plan (a delivered plan is never replaced) or the read
    leaves nothing to write."""
    lane = country_d84_lane(wave)
    out = out / wave
    if (out / "PLAN.jsonl").exists():
        raise P.PlanError(f"{out} holds a plan already - a delivered plan is never replaced")
    text = read(P.tagged_export_script(read_parts(lane)))
    plan = build_plan(text, built_at=built_at, lane=lane)
    if not plan.changes:
        raise P.PlanError(
            "the read leaves nothing to write - "
            + "; ".join(f"{v.site_name}: {v.reason} ({v.note})" for v in plan.skipped)
        )
    out.mkdir(parents=True, exist_ok=True)
    (out / "READ.jsonl").write_text(text, encoding="utf-8", newline="\n")
    P.write_plan_jsonl(plan, out / "PLAN.jsonl")
    P.write_skipped_jsonl(plan, out / "SKIPPED.jsonl")
    write_plan_md(plan, out / "PLAN.md")
    # ROLLBACK before APPLY: apply.py --emit refuses to write an apply without its undo.
    P.write_rollback_sql(plan, out / "ROLLBACK.sql", plan_path=out / "PLAN.jsonl")
    return dict(plan.counters) | {"lane": lane.name, "dir": str(out)}


def _wave(label: str) -> str:
    """`--wave`: a label `apply.py --lane country-d84-<label>` resolves, else argparse's error."""
    if COUNTRY_D84_LANE.match(f"country-d84-{label}") is None:
        raise argparse.ArgumentTypeError(f"{label!r} is not a wave label like 2026-11-11")
    return label


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument(
        "--write",
        action="store_true",
        help="write READ.jsonl, PLAN.jsonl, SKIPPED.jsonl, PLAN.md, ROLLBACK.sql (reads prod)",
    )
    ap.add_argument(
        "--wave", type=_wave, help="the wave's date label (2026-11-11, 2026-11-11b for a redo, ...)"
    )
    args = ap.parse_args(argv)
    if not args.write:
        ap.print_help()
        return 0
    if args.wave is None:
        ap.error("--write needs --wave <label>")
    try:
        result = write(args.out, args.wave, read=read_production, built_at=P._now())
    except P.PlanError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
