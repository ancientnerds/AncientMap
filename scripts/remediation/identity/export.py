"""The one production read of the identity discovery (read-only, one repeatable-read snapshot).

`python scripts/remediation/identity/export.py` sends `build_script()` to the production database
the way every lane reads it (`mechanical.plan.write_tagged_export`: ssh, then psql in the database
container, the statement on stdin) and keeps the answer as it came in `EXPORT.jsonl`. Nothing else
in this package touches the database; every other module reads that file.

**Read-only twice over.** The script starts with `SET default_transaction_read_only = on;` and runs
inside `BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY`; `test_identity_export.py` also refuses
any part whose SQL names a write verb.

The parts (the kind names the line's meaning):

* `shown`   - the curated sites that are not retired (4,900 on 2026-10-08), with the facts every
              module needs, and `outside_window`: the E3 window rule of the scope lane
              (`mechanical.lane.outside_e3_window`), built from the project's own constants;
* `ext_ids` - every `site_external_ids` row of those sites (a site can hold more than one item);
* `names`   - the English alias rows and the label row of `unified_site_names`;
* `pairs`   - two shown sites of one country within 300 m whose normalised names have a trigram
              similarity above 0.5 (computed here, in SQL, on the stored `name_normalized` key);
* `losers`  - the curated rows already retired as `duplicate_of:<survivor>`, with what they and
              their survivor still hold;
* `period_journal` - the last journalled write of `period_start`, `period_end` and `period_name`
              of the sites the scope module studies, and the models the write's evidence names.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _root in (str(_HERE.parents[3]), str(_HERE.parents[1])):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from mechanical.lane import outside_e3_window  # noqa: E402
from mechanical.plan import (  # noqa: E402
    parse_tagged_export,
    tagged_export_script,
    write_tagged_export,
)

from identity import common  # noqa: E402

QUIET = "\\set QUIET on\n"
READ_ONLY_SET = "SET default_transaction_read_only = on;\n"
KINDS = ("shown", "ext_ids", "names", "pairs", "losers", "period_journal")

#: The pinned id prefix of "Hadrian's Wall Path" (a footpath opened in 2003, no scope decision).
HADRIANS_WALL_PATH_PREFIX = "360a4afb"

SHOWN = "u.source_id = 'ancient_nerds' AND u.scope_status IS DISTINCT FROM 'retired'"
#: The sites the period journal is read for: outside the window, pending, and the footpath.
STUDIED = (
    f"({outside_e3_window('u.')} OR u.scope_status = 'pending' "
    f"OR u.id::text LIKE '{HADRIANS_WALL_PATH_PREFIX}%')"
)

SHOWN_SQL = f"""
SELECT u.id::text AS id, u.name, u.country, u.site_type, u.lat, u.lon, u.period_start,
       u.period_end, u.period_name, u.source_url, u.scope_status, u.scope_reason,
       u.created_at::text AS created_at, u.parent_site_id::text AS parent_site_id,
       left(coalesce(u.description, ''), 600) AS description,
       length(coalesce(u.description, '')) AS description_chars,
       u.raw_data->'_description_provenance'->>'lane' AS description_lane,
       (SELECT count(*) FROM wiki_images w WHERE w.site_id = u.id AND NOT w.is_excluded) AS images,
       (SELECT count(*) FROM wiki_images w WHERE w.site_id = u.id) AS images_all,
       (SELECT count(*) FROM site_content_links c WHERE c.site_id = u.id) AS links,
       (SELECT count(*) FROM unified_site_names n WHERE n.site_id = u.id) AS names_rows,
       EXISTS (SELECT 1 FROM card_stats cs WHERE cs.site_id = u.id
               AND cs.card_description IS NOT NULL) AS has_card,
       coalesce({outside_e3_window("u.")}, false) AS outside_window
  FROM unified_sites u
 WHERE {SHOWN}
 ORDER BY u.id"""

EXT_IDS_SQL = f"""
SELECT e.site_id::text AS site_id, e.kind, e.value
  FROM site_external_ids e JOIN unified_sites u ON u.id = e.site_id
 WHERE {SHOWN}
 ORDER BY e.site_id, e.kind, e.value"""

NAMES_SQL = f"""
SELECT n.site_id::text AS site_id, n.name, n.name_type, n.language_code
  FROM unified_site_names n JOIN unified_sites u ON u.id = n.site_id
 WHERE {SHOWN} AND (n.name_type = 'label' OR n.language_code = 'en')
 ORDER BY n.site_id, n.name_type, n.name"""

PAIRS_SQL = """
SELECT a.id::text AS a, b.id::text AS b,
       round(ST_Distance(a.geom::geography, b.geom::geography)::numeric, 1)::float8 AS metres,
       round(similarity(a.name_normalized, b.name_normalized)::numeric, 3)::float8 AS similarity
  FROM unified_sites a
  JOIN unified_sites b ON b.source_id = 'ancient_nerds' AND a.id < b.id
   AND b.scope_status IS DISTINCT FROM 'retired' AND b.country = a.country
   AND ST_DWithin(a.geom::geography, b.geom::geography, 300)
   AND similarity(a.name_normalized, b.name_normalized) > 0.5
 WHERE a.source_id = 'ancient_nerds' AND a.scope_status IS DISTINCT FROM 'retired'
 ORDER BY a.id, b.id"""

LOSERS_SQL = """
WITH l AS (
  SELECT u.id, u.name, u.name_normalized, u.created_at, u.scope_reason,
         substring(u.scope_reason from 'duplicate_of:([0-9a-f-]{36})')::uuid AS survivor_id
    FROM unified_sites u
   WHERE u.source_id = 'ancient_nerds' AND u.scope_status = 'retired'
     AND u.scope_reason LIKE 'duplicate_of:%')
SELECT l.id::text AS id, l.name, l.created_at::text AS created_at, l.survivor_id::text AS survivor_id,
       s.name AS survivor_name, s.scope_status AS survivor_scope_status,
       (SELECT count(*) FROM wiki_images w WHERE w.site_id = l.id AND NOT w.is_excluded) AS images,
       (SELECT count(*) FROM wiki_images w WHERE w.site_id = l.id) AS images_all,
       (SELECT count(*) FROM site_content_links c WHERE c.site_id = l.id) AS links,
       (SELECT count(*) FROM wiki_images w
         WHERE w.site_id = l.survivor_id AND NOT w.is_excluded) AS survivor_images,
       (SELECT count(*) FROM site_content_links c WHERE c.site_id = l.survivor_id) AS survivor_links,
       EXISTS (SELECT 1 FROM unified_site_names n WHERE n.site_id = l.survivor_id
                AND n.name_normalized = l.name_normalized) AS name_is_alias_on_survivor
  FROM l LEFT JOIN unified_sites s ON s.id = l.survivor_id
 ORDER BY l.id"""

PERIOD_JOURNAL_SQL = f"""
WITH w AS (SELECT u.id FROM unified_sites u WHERE {SHOWN} AND {STUDIED}),
last AS (
  SELECT DISTINCT ON (l.row_pk, l.column_name)
         l.row_pk, l.column_name, l.run_stamp, l.confidence, l.old_value, l.new_value,
         l.applied_at::text AS applied_at,
         CASE WHEN jsonb_typeof(l.evidence) = 'array' THEN
           (SELECT string_agg(DISTINCT e->>'model', '; ')
              FROM jsonb_array_elements(l.evidence) e
             WHERE jsonb_typeof(e) = 'object' AND e ? 'model') END AS models
    FROM remediation_change_log l
   WHERE l.table_name = 'unified_sites'
     AND l.column_name IN ('period_start', 'period_end', 'period_name')
     AND l.run_stamp NOT LIKE '%probe%'
     AND l.row_pk IN (SELECT id::text FROM w)
   ORDER BY l.row_pk, l.column_name, l.id DESC)
SELECT row_pk AS site_id, column_name, run_stamp, confidence, old_value, new_value, applied_at,
       models
  FROM last
 ORDER BY row_pk, column_name"""

PARTS: tuple[tuple[str, str], ...] = (
    ("shown", SHOWN_SQL),
    ("ext_ids", EXT_IDS_SQL),
    ("names", NAMES_SQL),
    ("pairs", PAIRS_SQL),
    ("losers", LOSERS_SQL),
    ("period_journal", PERIOD_JOURNAL_SQL),
)


def build_script() -> str:
    """The statement sent to production: `SET default_transaction_read_only = on`, then the
    tagged export's own read-only repeatable-read transaction."""
    script = tagged_export_script(PARTS)
    if not script.startswith(QUIET):
        raise common.IdentityError("the tagged export no longer starts with \\set QUIET on")
    return QUIET + READ_ONLY_SET + script[len(QUIET) :]


@dataclass(frozen=True)
class Export:
    """The parsed export: the rows of each kind and the snapshot's clock."""

    shown: list[dict[str, Any]]
    ext_ids: list[dict[str, Any]]
    names: list[dict[str, Any]]
    pairs: list[dict[str, Any]]
    losers: list[dict[str, Any]]
    period_journal: list[dict[str, Any]]
    exported_at: str


def load_export(path: Path) -> Export:
    rows, stamp = parse_tagged_export(path.read_text(encoding="utf-8"), KINDS)
    if not rows["shown"]:
        raise common.IdentityError(f"{path} holds no shown site: the read did not answer")
    return Export(exported_at=stamp, **rows)


def ids_by_site(ext_ids: Sequence[Mapping[str, Any]], kind: str) -> dict[str, list[str]]:
    """The values of one `site_external_ids` kind per site, in the table's order."""
    out: dict[str, list[str]] = defaultdict(list)
    for row in ext_ids:
        if row["kind"] == kind:
            out[row["site_id"]].append(row["value"])
    return dict(out)


def qids_by_site(ext_ids: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    return ids_by_site(ext_ids, "wikidata_qid")


def enwiki_by_site(ext_ids: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    return ids_by_site(ext_ids, "enwiki_title")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read production once, read-only.")
    parser.add_argument("--root", type=Path, default=None, help="main checkout (default: found)")
    args = parser.parse_args(argv)
    target = common.run_dir(args.root) / common.EXPORT_FILE
    write_tagged_export(build_script(), target)
    export = load_export(target)
    counts: dict[str, Any] = {kind: len(getattr(export, kind)) for kind in KINDS}
    counts["exported_at"] = export.exported_at
    common.record_counts(target.parent, "export", counts)
    print(counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
