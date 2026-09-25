"""Phase 6 item 2: recompute the curated match keys in SQL, with `unaccent` - never in Python.

## The key

`unified_sites.name_normalized` and `unified_site_names.name_normalized` are the match key
`left(lower(unaccent(name)), 500)` (`pipeline/lyra/site_key.py`, the one definition).
`site_matcher` and the prospector's dedup bind the raw name and compute their side in Postgres,
so a row whose stored key is not its name's key is unreachable by an exact lookup of that name.
The plan (docs/procedures/SITES_DB_REMEDIATION_2026-09.md, Phase 6 item 2) says: recompute in SQL
using `unaccent`, not via `normalize_name()`.

## What production held (read-only, 2026-09-25 12:50 UTC)

* `unified_sites`: **0** curated rows (`ancient_nerds` 5,004, `lyra` 24) whose key differs. No
  remediation lane ever wrote `name` (the journal holds no `name` or `name_normalized` row; the UK
  lane wrote `country`), and Lyra's boot migration reconciles the curated sources' site keys on
  every start (`pipeline/lyra/orchestrator.py::_run_migrations`).
* `unified_site_names`: **0** rows of `ancient_nerds` sites. **11** rows of six Lyra-promoted
  sites (source `lyra`: Yap 4, Charnwood Forest 2, Doggerland 2, North Sentinel Island, Roopkund
  Lake, Cerutti Mastodon site), all `wikidata_alias`, written by Lyra's
  `_store_wikidata_aliases` with Python's `normalize_name` (the writer is fixed in the same
  change): its NFKD strips the Japanese (han)dakuten (ヤップ島 -> ヤッフ島), leaves Hangul as jamo,
  and cuts a parenthesised part ("Cerutti Mastodon (CM) site" -> "cerutti mastodon  site"). The
  boot's alias UPDATE compares the stored key with *itself* (`lower(unaccent(name_normalized))`),
  so it never repairs these. None collides with another row of its site. The writer writes
  `ancient_nerds` rows only (guard 1), so the plan lists these 11 and plans nothing: whether the
  remediation's journal may write a `lyra` row is the owner's call.

## The rule (K1)

`name_normalized := left(lower(unaccent(name)), 500)`, the value Postgres computed in the read
(`sql_key`) - this module never computes a key. Written through the shared chunk writer
(`gallery_audit/chunk_writer.py`): guard 2b (a name row belongs to the site the plan names) and
guard 2c (the planned key is the key Postgres derives from the row's name *at write time*; a name
changed since the read refuses the whole transaction) run inside the transaction.

Listed, never planned: a row of a source the writer does not write (`lyra`,
`ancient_nerds_community`: the writer's guard 1 takes `ancient_nerds` only), and an alias whose key
another row of its site already holds (uq_usn would refuse it; the row is then a duplicate, and
removing it is a DELETE - not this lane's).

## Commands

    plan.py chunk --out output/remediation/name_key/name-key-<date>
        reads production read-only (two statements), keeps the read as READ.json and writes
        chunk-001/ (journal lane `name-key`, test id `P6/name-key`, run stamp
        `name-key-<date>-001`); exit 1 when nothing differs
    chunk_writer.py <out>/chunk-001 --check|--rehearse|--apply|--readback|--rehearse-rollback
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (ROOT, ROOT / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from gallery_audit import chunk_writer as CW  # noqa: E402

from pipeline.lyra.site_key import KEY_SQL_TEMPLATE, site_key_sql  # noqa: E402

WRITER_SOURCE = CW.CURATED_SOURCE
CURATED_SOURCES = ("ancient_nerds", "lyra", "ancient_nerds_community")
OUT_RE = re.compile(r"name-key-(\d{4}-\d{2}-\d{2})")
RULE = "K1"
KEY_SOURCE = "pipeline/lyra/site_key.py"


class NameKeyError(CW.ChunkError):
    """A read or a plan this lane must not turn into a write. Nothing was sent."""


def chunk_lane(out: Path) -> CW.Lane:
    """The journal identity of a key chunk, stamped with its directory's date."""
    match = OUT_RE.fullmatch(out.name)
    if match is None:
        raise NameKeyError(f"{out} is not a key directory (name-key-YYYY-MM-DD)")
    return CW.Lane(
        "name-key",
        "P6/name-key",
        f"name-key-{match.group(1)}",
        "authoritative",
        "name key recompute",
    )


# ------------------------------------------------------------------------------------ the read
_IN_CURATED = "u.source_id IN (" + ", ".join(f"'{s}'" for s in CURATED_SOURCES) + ")"

SITES_SQL = f"""SELECT row_to_json(t) FROM (
  SELECT u.id::text AS id, u.source_id, u.name, u.name_normalized,
         {site_key_sql("u.name")} AS sql_key
    FROM unified_sites u
   WHERE {_IN_CURATED}
     AND u.name_normalized IS DISTINCT FROM {site_key_sql("u.name")}
   ORDER BY u.id
) t;"""

NAMES_SQL = f"""SELECT row_to_json(t) FROM (
  SELECT n.id, n.site_id::text AS site_id, u.source_id, n.name, n.name_normalized, n.name_type,
         {site_key_sql("n.name")} AS sql_key,
         (SELECT min(o.id) FROM unified_site_names o
           WHERE o.site_id = n.site_id AND o.id <> n.id
             AND o.name_normalized = {site_key_sql("n.name")}) AS collides_with
    FROM unified_site_names n JOIN unified_sites u ON u.id = n.site_id
   WHERE {_IN_CURATED}
     AND n.name_normalized IS DISTINCT FROM {site_key_sql("n.name")}
   ORDER BY n.id
) t;"""


def read_production() -> dict[str, Any]:
    """Every curated site row and alias row whose key is not Postgres's key of its name, with that
    key as Postgres computes it. Read-only, two statements."""
    return {
        "read_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sites": CW.pv.read_rows(SITES_SQL),
        "names": CW.pv.read_rows(NAMES_SQL),
    }


# ------------------------------------------------------------------------------------ the plan
def _planned(
    table: str, row: Mapping[str, Any], site_id: str, what: str
) -> tuple[CW.Change | None, dict[str, str] | None]:
    """One read row as a change, or as a listed row with its reason."""
    row_key = str(row["id"])
    stored, key = row["name_normalized"], row["sql_key"]
    if not isinstance(key, str) or not key:
        raise NameKeyError(f"{table} {row_key}: the read carries no key from Postgres ({key!r})")
    if key == stored:
        raise NameKeyError(f"{table} {row_key}: already holds its key - the read is not the SELECT")
    if row["source_id"] != WRITER_SOURCE:
        reason = f"source-{row['source_id']}-not-the-writer-s"
        return None, {"table": table, "row": row_key, "reason": reason}
    if row.get("collides_with") is not None:
        reason = f"key-held-by-row-{row['collides_with']}"
        return None, {"table": table, "row": row_key, "reason": reason}
    evidence = [
        {
            "source": f"{table}:{row_key}",
            "quote": f"{what} name {row['name']!r}; stored key {stored!r}; "
            f"{site_key_sql('name')} = {key!r}",
        },
        {"source": KEY_SOURCE, "quote": f"KEY_SQL_TEMPLATE = {KEY_SQL_TEMPLATE!r}"},
    ]
    reason = (
        f"the stored key {stored!r} is not the match key of the name {row['name']!r}; "
        f"Postgres derives {key!r} (K1)"
    )
    change = CW.Change(
        table, "name_normalized", row_key, site_id, stored, key, RULE, reason, evidence
    )
    return change, None


def plan_keys(
    sites: Sequence[Mapping[str, Any]], names: Sequence[Mapping[str, Any]]
) -> tuple[list[CW.Change], list[dict[str, str]]]:
    """`(changes, listed)`: K1 for every read row the writer can write; the rest listed. Pure."""
    changes: list[CW.Change] = []
    listed: list[dict[str, str]] = []
    rows = [("unified_sites", r, str(r["id"]), "site") for r in sites]
    rows += [
        ("unified_site_names", r, str(r["site_id"]), f"{r.get('name_type') or 'name'} row")
        for r in names
    ]
    for table, row, site_id, what in rows:
        change, entry = _planned(table, row, site_id, what)
        if change is not None:
            changes.append(change)
        if entry is not None:
            listed.append(entry)
    return changes, listed


# ------------------------------------------------------------------------------------- the CLI
def command_chunk(args: argparse.Namespace) -> int:
    out = Path(args.out)
    lane = chunk_lane(out)
    read = read_production()
    changes, listed = plan_keys(read["sites"], read["names"])
    for entry in listed:
        print(f"listed, not planned: {entry['table']} {entry['row']} ({entry['reason']})")
    if not changes:
        raise NameKeyError(
            f"no curated key differs from Postgres's key of its name ({len(listed)} listed): "
            "nothing to plan"
        )
    for directory in CW.emit_chunks(out, CW.chunk_changes(lane, changes)):
        print(f"{directory}: {len(changes)} key(s), {len(listed)} row(s) listed")
    (out / "READ.json").write_text(
        json.dumps(read, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    chunk = sub.add_parser("chunk", help="read production (read-only) and emit the chunk")
    chunk.add_argument("--out", required=True, help="output/remediation/name_key/name-key-<date>")
    args = parser.parse_args(argv)
    try:
        return command_chunk(args)
    except CW.pv.PersistError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
