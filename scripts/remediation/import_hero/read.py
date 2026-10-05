"""This lane's own read: the columns the plan writes, and nothing the plan does not.

Two reasons it cannot reuse WD2's read (`served_image.state.IMAGES_SQL`):

* the join needs `unified_sites.source_url` - the key the period lane proved, and the one that
  matched 4,318 of 4,997 curated sites to the import's feature;
* the plan's `old_value` for `width`/`height` must be the value production holds, because
  `chunk_writer`'s guard 3 refuses a write whose planned old value differs. WD2's read carries
  neither column.

Three read-only statements, the same transport as the rest of the remediation
(`persist_verdicts.read_rows`). Nothing is written to production.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (ROOT, ROOT / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from gallery_audit import chunk_writer as CW  # noqa: E402
from served_image.state import StateError, json_text, sha256_text, write_text_once  # noqa: E402

READ = "READ.json"

#: The curated sites the platform shows, with the two keys the join needs: `source_url` and the
#: name the folded-title fallback compares.
SITES_SQL = """SELECT row_to_json(t) FROM (
  SELECT u.id::text AS id, u.name, u.country, u.site_type, u.lat, u.lon,
         u.thumbnail_url, u.source_url
    FROM unified_sites u
   WHERE u.source_id = 'ancient_nerds' AND u.scope_status IS DISTINCT FROM 'retired'
   ORDER BY u.id
) t;"""

#: Every image row of those sites, with the local derivative's own size: `width`/`height` decide
#: whether the flag may move (the hero must be at least 1600x900) and are the old values of the
#: fetch's file columns.
IMAGES_SQL = """SELECT row_to_json(t) FROM (
  SELECT w.id, w.site_id::text AS site_id, w.filename, w.title, w.commons_page_url,
         w.original_url, w.is_hero, w.is_lead, w.is_excluded, w.sort_order, w.file_size_bytes,
         w.width, w.height
    FROM wiki_images w JOIN unified_sites u ON u.id = w.site_id
   WHERE u.source_id = 'ancient_nerds' AND u.scope_status IS DISTINCT FROM 'retired'
   ORDER BY w.site_id, w.id
) t;"""

#: The curated sites that are retired: the platform does not show them, so the lane has no say.
RETIRED_SQL = """SELECT row_to_json(t) FROM (
  SELECT u.id::text AS id FROM unified_sites u
   WHERE u.source_id = 'ancient_nerds' AND u.scope_status = 'retired'
   ORDER BY u.id
) t;"""


#: When the read ran. `row_to_json` because `persist_verdicts.read_rows` parses one JSON object
#: per line, and a bare scalar is not one.
READ_AT_SQL = """SELECT row_to_json(t) FROM (
  SELECT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS read_at
) t;"""


def read_production() -> dict[str, Any]:
    """Production as the plan needs it: the shown sites, their rows, the retired ids."""
    sites = CW.pv.read_rows(SITES_SQL)
    if not sites:
        raise StateError("the read holds no curated site: the scope guard is in the statement")
    return {
        "read_at": str(CW.pv.read_rows(READ_AT_SQL)[0]["read_at"]),
        "sites": sites,
        "images": CW.pv.read_rows(IMAGES_SQL),
        "retired": [row["id"] for row in CW.pv.read_rows(RETIRED_SQL)],
    }


def write_read(path: Path, data: dict[str, Any]) -> str:
    """READ.json, written once per run directory. Returns the sha256 of its text."""
    return write_text_once(path, json_text(data))


def dimensions(data: dict[str, Any]) -> dict[int, tuple[int | None, int | None]]:
    """`{row id: (width, height)}` - the local derivative's own size, as the read holds it."""
    out: dict[int, tuple[int | None, int | None]] = {}
    for row in data["images"]:
        out[int(row["id"])] = (row.get("width"), row.get("height"))
    return out


def digest(data: dict[str, Any]) -> str:
    """The sha256 of the read's text, for the run's summary."""
    return sha256_text(json_text(data))
