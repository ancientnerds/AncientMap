"""Two renames of 2026-10-01 (lane `name-fix`): a site named for the wrong city, and a stray U+200C.

## The decision

Owner order of 2026-10-01 (the finish-the-database sitting, "alles online finden"): a curated site is
renamed only to the sourced name of that very site. Both renames below are the site's own English
Wikipedia title - the `enwiki_title` external id the row already carries - and each is a defect of the
stored name, read from production on 2026-10-01 (read-only):

* **`4a07cc38-1b55-4254-b0ad-fe875310caf7`, "Temple of Augustus, Split" -> "Temple of Augustus,
  Pula".** The row carries `enwiki_title=Temple of Augustus, Pula` and `wikidata_qid=Q770030`; its
  description is the Pula temple's ("a well-preserved Roman temple in the city of Pula, Croatia");
  its stored point (44.87026, 13.84220) lies 28 m from Q770030's coordinate (44.8702, 13.84185); the
  English Wikipedia and Wikidata know no Temple of Augustus in Split (a search of both names none).
  The name is simply wrong, and its siblings use the same form (`Temple of Augustus, Pozzuoli`,
  `Temple of Augustus, Barcelona`).
* **`f9cfc5f7-a6c8-4c6f-9d82-f30151a36d6c`, "Gate of All Nations<U+200C> Persepolis" -> "Gate of All
  Nations".** The only curated name with a zero-width character (read: 1 of 5,004). The row carries
  `enwiki_title=Gate of All Nations` and `wikidata_qid=Q5527015` (English label "Gate of All Nations");
  the curated siblings at Persepolis carry the monument's own name without the place ("Apadana
  Palace", "Persepolis"), so the place suffix that the U+200C replaced a comma for is not the project's
  form - the place is the `country` and the `Persepolis` row beside it.

Both are the shape of `name-l5` and `chiapa-name`: `name` and its match key in one transaction, the key
computed by Postgres from the new name in this plan's own read (`l5.plan.keys_sql`; FIELD_CONTRACT 2.2,
never a Python key), and the lane's invariant refusing a key that is not the new name's.

## What is checked before anything is planned (`build`, the first failure refuses both)

Neither stamp journals a row yet (a lane that has written is never re-planned). Each site exists, is
curated and not retired, holds exactly the old name (compared byte for byte, as hex, so the U+200C
is read and not assumed) and a match key, and its `name` and `name_normalized` journals end at the
live values. The new name is the site's `enwiki_title` and holds no zero-width character, and no
visible curated row but the site itself carries its key. The premise carried by every cell is the
site's external ids as Postgres prints them (`lane.NAME_FIX_PREMISE_SQL`): guard 5 refuses the write,
and its reversal, once those ids moved, because the new name is derived from one of them.

`--write` reads production read-only in one snapshot (kept as `mechanical_name_fix/READ.jsonl`) and
writes `PLAN.jsonl`, `PLAN.md`, `ROLLBACK.sql`; `apply.py --lane name-fix` emits, rehearses, probes,
applies and verifies (runbook: docs/procedures/SITES_DB_REMEDIATION_2026-09.md, "Two renames of
2026-10-01"; `apply.py --emit` also writes `APPLY.sql`, committed beside the plan).
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from l5 import plan as L5P  # noqa: E402

from mechanical import plan as P  # noqa: E402
from mechanical.lane import NAME_FIX, sql_literal  # noqa: E402
from pipeline.lyra.site_key import site_key_sql  # noqa: E402
from pipeline.utils.public_sites import RETIRED  # noqa: E402

log = logging.getLogger("mechanical.name_fix")

ROOT = REPO / "output" / "remediation"
READ_PATH = Path(NAME_FIX.out_dir_name) / "READ.jsonl"
DECISION_SOURCE = "owner order 2026-10-01: Wikipedia/Wikidata suffice as the one source"
ENWIKI_TITLE = "enwiki_title"
#: U+200B-U+200F, U+2060, U+FEFF: the characters a name must not carry (`lane.ZERO_WIDTH_NAME`).
ZERO_WIDTH = re.compile("[\u200b-\u200f\u2060\ufeff]")
NAME_COLUMN_CHARS = 500
EVIDENCE_READ = "read 2026-10-01 through the public MediaWiki and Wikidata APIs"


@dataclass(frozen=True)
class Rename:
    """One decided rename: the row, the exact old name, the new name and what carries it."""

    site_id: str
    old: str
    new: str
    note: str
    evidence: tuple[Mapping[str, Any], ...]


def _page(title: str) -> str:
    return "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")


RENAMES = (
    Rename(
        site_id="4a07cc38-1b55-4254-b0ad-fe875310caf7",
        old="Temple of Augustus, Split",
        new="Temple of Augustus, Pula",
        note=(
            "the stored name puts the Pula temple in Split: the row's own Wikipedia title and "
            "Wikidata item (Q770030) are the temple of Pula, its description and its point are "
            "Pula's, and no Temple of Augustus is known in Split"
        ),
        evidence=(
            {
                "source": f"en.wikipedia.org, article 'Temple of Augustus, Pula' ({EVIDENCE_READ})",
                "url": _page("Temple of Augustus, Pula"),
                "quote": (
                    "The Temple of Augustus (Croatian: Augustov hram; Italian: Tempio di Augusto) "
                    "is a well-preserved Roman temple in the city of Pula, Croatia"
                ),
            },
            {
                "source": f"wikidata:Q770030 ({EVIDENCE_READ})",
                "url": "https://www.wikidata.org/wiki/Q770030",
                "quote": (
                    "label 'Temple of Augustus', description 'Roman temple in Pula, Croatia', "
                    "coordinate location 44.8702, 13.84185; the site's stored point 44.87026, "
                    "13.84220 is 28 m from it"
                ),
            },
            {
                "source": f"wikidata search 'Temple of Augustus' ({EVIDENCE_READ})",
                "url": "https://www.wikidata.org/w/index.php?search=Temple+of+Augustus",
                "quote": (
                    "ten items named for a Temple of Augustus (Pula, Barcelona, Ankara, Vienne, "
                    "Philae, Antioch in Pisidia, Cartagena, Rome, Nimes, Leptis Magna), none in Split"
                ),
            },
        ),
    ),
    Rename(
        site_id="f9cfc5f7-a6c8-4c6f-9d82-f30151a36d6c",
        old="Gate of All Nations\u200c Persepolis",
        new="Gate of All Nations",
        note=(
            "the stored name carries a U+200C between 'Nations' and 'Persepolis'; the monument's "
            "own name - its Wikipedia title and Wikidata label - is 'Gate of All Nations', as the "
            "curated siblings at Persepolis are named without the place"
        ),
        evidence=(
            {
                "source": f"en.wikipedia.org, article 'Gate of All Nations' ({EVIDENCE_READ})",
                "url": _page("Gate of All Nations"),
                "quote": (
                    "also known as the Gate of Xerxes, is located in the ruins of the ancient city "
                    "of Persepolis, Iran."
                ),
            },
            {
                "source": f"wikidata:Q5527015 ({EVIDENCE_READ})",
                "url": "https://www.wikidata.org/wiki/Q5527015",
                "quote": "English label 'Gate of All Nations'; enwiki sitelink 'Gate of All Nations'",
            },
        ),
    ),
)


# ------------------------------------------------------------------------------ the read
def read_parts() -> tuple[tuple[str, str], ...]:
    """What the plan reads, each part one query of one read-only snapshot."""
    ids = P.sql_ids(r.site_id for r in RENAMES)
    site = (
        "SELECT u.id::text AS id, u.name, encode(convert_to(u.name, 'UTF8'), 'hex') AS name_hex, "
        "u.name_normalized, u.source_id, u.scope_status, "
        f"{NAME_FIX.premise_sql} AS premise FROM unified_sites u WHERE u.id IN ({ids}) "
        "ORDER BY u.id"
    )
    ext = (
        "SELECT e.site_id::text AS id, e.kind, e.value FROM site_external_ids e "
        f"WHERE e.site_id IN ({ids}) ORDER BY e.site_id, e.kind, e.value"
    )
    names = ", ".join(f"({sql_literal(r.new)})" for r in RENAMES)
    holders = (
        "SELECT u.id::text AS id, u.name, u.name_normalized, u.scope_status FROM unified_sites u "
        "WHERE u.source_id = 'ancient_nerds' AND u.name_normalized IN "
        f"(SELECT {site_key_sql('n')} FROM (VALUES {names}) AS v(n)) ORDER BY u.id"
    )
    journal = (
        "SELECT id, row_pk, column_name, run_stamp, coalesce(test_id, '') AS test_id, old_value, "
        "new_value FROM remediation_change_log WHERE table_name = 'unified_sites' "
        f"AND row_pk IN ({ids}) AND column_name IN ('name', 'name_normalized') ORDER BY id"
    )
    stamps = (
        "SELECT run_stamp, count(*) AS n FROM remediation_change_log WHERE run_stamp IN ("
        + ", ".join(sql_literal(s) for s in (NAME_FIX.run_stamp, NAME_FIX.rollback_run_stamp))
        + ") GROUP BY run_stamp ORDER BY run_stamp"
    )
    return (
        ("site", site),
        ("ext", ext),
        ("key", L5P.keys_sql([r.new for r in RENAMES])),
        ("holder", holders),
        ("journal", journal),
        ("stamp", stamps),
    )


@dataclass(frozen=True)
class Read:
    """The production read the plan rests on."""

    sites: Mapping[str, Mapping[str, Any]]
    ext: Mapping[str, tuple[tuple[str, str], ...]]
    keys: Mapping[str, str]
    holders: tuple[Mapping[str, Any], ...]
    journal: Mapping[tuple[str, str], tuple[P.JournalLink, ...]]
    stamps: Mapping[str, int]
    read_at: str


def parse_read(text: str) -> Read:
    """The tagged read (`plan.parse_tagged_export` refuses a line of another kind and a read
    without its one snapshot line)."""
    rows, read_at = P.parse_tagged_export(text, (kind for kind, _sql in read_parts()))
    journal: dict[tuple[str, str], list[P.JournalLink]] = {}
    for r in sorted(rows["journal"], key=lambda r: int(r["id"])):
        journal.setdefault((str(r["row_pk"]), str(r["column_name"])), []).append(
            P.JournalLink(
                int(r["id"]), str(r["run_stamp"]), str(r["test_id"]), r["old_value"], r["new_value"]
            )
        )
    ext: dict[str, list[tuple[str, str]]] = {}
    for r in rows["ext"]:
        ext.setdefault(str(r["id"]), []).append((str(r["kind"]), str(r["value"])))
    return Read(
        sites={str(r["id"]): r for r in rows["site"]},
        ext={sid: tuple(pairs) for sid, pairs in ext.items()},
        keys={str(r["name"]): str(r["key"]) for r in rows["key"]},
        holders=tuple(rows["holder"]),
        journal={cell: tuple(links) for cell, links in journal.items()},
        stamps={str(r["run_stamp"]): int(r["n"]) for r in rows["stamp"]},
        read_at=read_at,
    )


def write_read(path: Path) -> Path:
    """Read production (read-only, one snapshot) and keep the answer as it came."""
    return P.write_tagged_export(P.tagged_export_script(read_parts()), path)


# ------------------------------------------------------------------------------ the decision
def _refuse(rename: Rename, why: str) -> P.PlanError:
    return P.PlanError(f"{rename.old!r} ({rename.site_id}): {why}")


def check_rename(read: Read, rename: Rename) -> Mapping[str, Any]:
    """One site as the decision renames it - or the refusal that says why not."""
    if not 0 < len(rename.new) <= NAME_COLUMN_CHARS or rename.new != rename.new.strip():
        raise _refuse(rename, f"{rename.new!r} is not a name that fits `name` as it stands")
    if ZERO_WIDTH.search(rename.new):
        raise _refuse(rename, f"the new name {rename.new!r} holds a zero-width character")
    site = read.sites.get(rename.site_id)
    if site is None:
        raise _refuse(rename, "the row is not in unified_sites")
    if site["source_id"] != P.CURATED_SOURCE:
        raise _refuse(rename, f"not a curated site: {site['source_id']!r}")
    if site["scope_status"] == RETIRED:
        raise _refuse(rename, "the site is retired")
    if site["name_hex"] != rename.old.encode("utf-8").hex():
        raise _refuse(rename, f"the row holds {site['name']!r} (hex {site['name_hex']}), not it")
    if site["name_normalized"] is None:
        raise _refuse(rename, "the row has no match key to move")
    for column in ("name", "name_normalized"):
        broken = P.journal_break(read.journal.get((rename.site_id, column), ()), site[column])
        if broken is not None:
            raise _refuse(rename, f"{column}: {broken[0]} - {broken[1]}")
    titles = [value for kind, value in read.ext.get(rename.site_id, ()) if kind == ENWIKI_TITLE]
    if titles != [rename.new]:
        raise _refuse(
            rename, f"its {ENWIKI_TITLE} is {titles!r}; the new name is the site's own title"
        )
    if f"{ENWIKI_TITLE}={rename.new}" not in site["premise"]:
        raise _refuse(rename, f"the premise {site['premise']!r} does not carry the title")
    key = read.keys.get(rename.new)
    if key is None:
        raise _refuse(rename, "the read holds no match key of the new name")
    others = sorted(
        str(h["id"])
        for h in read.holders
        if h["name_normalized"] == key and h["scope_status"] != RETIRED
    )
    if [sid for sid in others if sid != rename.site_id]:
        raise _refuse(
            rename,
            f"{', '.join(others)} carries the key {key!r} and is visible: two visible rows would "
            f"be called {rename.new!r}",
        )
    return site


def build(read: Read, built_at: str) -> P.Plan:
    """The plan of both renames: a pure function of the read - no network, no database, no clock."""
    written = {stamp: n for stamp, n in read.stamps.items() if n}
    if written:
        raise P.PlanError(
            f"{written} journal row(s) exist for this lane: a lane that has written is never "
            "re-planned - its ROLLBACK.sql may be the only undo"
        )
    changes: list[P.Verdict] = []
    for rename in RENAMES:
        site = check_rename(read, rename)
        seen = {
            "source": "production:unified_sites",
            "url": None,
            "quote": (
                f"name {site['name']!r} (utf-8 hex {site['name_hex']}), key "
                f"{site['name_normalized']!r}, external ids {site['premise']} (read {read.read_at})"
            ),
        }
        changes += L5P.name_verdicts(
            rename.site_id,
            rename.old,
            str(site["name_normalized"]),
            rename.new,
            read.keys[rename.new],
            (*rename.evidence, seen),
            f"{DECISION_SOURCE}: {rename.note}",
            premise=str(site["premise"]),
        )
    return P.Plan(
        changes=tuple(changes),
        skipped=(),
        built_at=built_at,
        counters={"sites": len(RENAMES), "cells": len(changes)},
        lane=NAME_FIX,
    )


# ------------------------------------------------------------------------------ the output
_GUARDS = (
    "guard 1: the row is a curated site",
    "guard 2: real changes, only in `name` and `name_normalized`, each within 500 characters",
    "guard 3: the row still holds the planned old name and its key",
    "guard 5: the site's external ids are still the ones the new name was read from",
    "invariant 3: the key written is the key Postgres derives from the name written",
    "one journal row per cell, and exactly the planned cells moved",
)


def plan_md(plan: P.Plan, read: Read) -> str:
    lane = plan.lane
    lines = [
        f"# Two renames of 2026-10-01 (`{lane.name}`): plan",
        "",
        f"Built {plan.built_at} by `scripts/remediation/mechanical/name_fix.py` from the read-only "
        f"production read of {read.read_at} (`READ.jsonl`). Lane `{lane.name}`: run stamp "
        f"`{lane.run_stamp}`, journal test id `{lane.test_id}`, change keys "
        f"`{lane.key_prefix}:<site_id>:<column>`, premise `{lane.premise_sql}`. Decision: "
        f"{DECISION_SOURCE}.",
        "",
        f"**{plan.counters['sites']} sites, {plan.counters['cells']} cells.**",
        "",
        "| site | cell | old | new |",
        "|---|---|---|---|",
    ]
    for v in plan.changes:
        old = "NULL" if v.old_value is None else f"`{v.old_value!a}`"
        lines.append(f"| {v.site_name!a} (`{v.site_id}`) | {v.column} | {old} | `{v.new_value}` |")
    lines += ["", "## What the transaction checks", "", *[f"* {g}" for g in _GUARDS], ""]
    for rename in RENAMES:
        lines += [f"## {rename.new} (`{rename.site_id}`)", "", rename.note, ""]
        lines += [f"* {e['source']}: {e['quote']}" for e in rename.evidence]
        lines.append("")
    lines += [
        "## Run",
        "",
        "```bash",
        "PY=./.venv/Scripts/python.exe",
        *[
            f"$PY scripts/remediation/mechanical/apply.py --lane {lane.name} {flag}"
            for flag in (
                "--check-primitive",
                "--verify",
                "--interests",
                "--emit",
                "--rehearse",
                "--probe-guards",
                "--apply",
                "--verify",
                "--rehearse-rollback",
            )
        ],
        "```",
        "",
        "Undo, only as a decision: `ROLLBACK.sql` restores both old names and keys. Lyra's next boot "
        "adds each new name to `unified_site_names` as a `label` row (the old name stays there, so "
        "an exact search finds both).",
        "",
    ]
    return "\n".join(lines)


def write_plan(plan: P.Plan, read: Read, root: Path) -> Path:
    """The lane's files in its directory under `root` (`apply.lane_dir` for the default)."""
    directory = root / plan.lane.out_dir_name
    directory.mkdir(parents=True, exist_ok=True)
    P.write_plan_jsonl(plan, directory / "PLAN.jsonl")
    (directory / "PLAN.md").write_text(plan_md(plan, read), encoding="utf-8", newline="\n")
    # ROLLBACK before APPLY: apply.py --emit refuses to write an apply without its undo
    P.write_rollback_sql(plan, directory / "ROLLBACK.sql", plan_path=directory / "PLAN.jsonl")
    return directory


# ------------------------------------------------------------------------------------- CLI
def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Plan the two renames of 2026-10-01 (lane name-fix)")
    ap.add_argument("--root", type=Path, default=ROOT, help="default: output/remediation")
    ap.add_argument(
        "--write",
        action="store_true",
        help="read production (read-only) and write PLAN.jsonl, PLAN.md and ROLLBACK.sql",
    )
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if not args.write:
        ap.print_help()
        return 0
    try:
        path = write_read(args.root / READ_PATH)
        read = parse_read(path.read_text(encoding="utf-8"))
        plan = build(read, P._now())
    except P.PlanError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    write_plan(plan, read, args.root)
    print(json.dumps(dict(plan.counters), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
