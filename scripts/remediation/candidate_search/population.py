"""D17, stage A of the picture research: the sites that serve no picture, and what is known of each.

Owner decision D17 (2026-10-08): "research all 952". The population is re-derived at the moment of the
write (map `plans/images.md`, stage 0): every shown curated site that has **no live image row and no
`thumbnail_url`**. A site retired by D20 or merged by D14 meanwhile is not in it; a site D15 just
cleared is.

Owner decision D59 (2026-10-24) adds the sites whose only picture is a **third-party** hotlinked
thumbnail (a blog, a museum CDN, megalithic.co.uk - 9 on 2026-10-24): they join the research, a
checked Commons picture with its credit replaces the thumbnail, and where none is found the thumbnail
goes NULL (`image_roles/d59.py`). A site whose only picture is a hotlinked **Commons** file is not in
this population: D59 gives it a credited row of that same file instead (`d59.py`). Each line carries
the `thumbnail_url` the site serves, so the INSERT wave can tell the two kinds of first row apart.

**One production read, read-only** (`population_sql`), and one source for each identifier: the
Wikidata item and the English Wikipedia title come from `site_external_ids` - not from WD1's harvest
(2026-09-26), which the first pre-check used and which is older than the L5 link repairs. A site that
carries **two** different items (or titles) has no single identity: it is listed with
`qid_conflict` and its item is not read, because a picture routed through the wrong item is the error
this stage exists to avoid (Pukara, Vilcas Huaman, Blaskovina and three Gyeongju "Belt" sites have a
known wrong link).

The point is **sourced** when its `raw_data._coord_provenance` marker (`mechanical.field_prov`) names
a kind other than `unsourced` and hashes the point it describes; only then may the geotag route
(`search.py`) look for files within 300 m of it. A site without the marker is simply not sourced.

`held_files` are the Commons files of **every** row of the site, excluded ones too: an excluded row was
judged (or removed) before, and unhiding a file needs a judgement of its own.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _path in (_HERE.parents[3], _HERE.parents[1]):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from mechanical.field_prov import COORD, SPECS, UNSOURCED, sha_sql  # noqa: E402
from served_image import state as ST  # noqa: E402

POPULATION_FILE = "POPULATION.jsonl"
#: The hosts a Commons file is served from; a thumbnail on any other host is a third-party hotlink.
COMMONS_HOSTS = ("upload.wikimedia.org", "thumb.wikimedia.org")
QID_KIND = "wikidata_qid"
ENWIKI_KIND = "enwiki_title"
#: How much of the description goes to the judges (the head says what the site is and where).
DESCRIPTION_CHARS = 700

_COORD = SPECS[COORD]
SOURCED_KINDS = frozenset(_COORD.kinds) - {UNSOURCED}


class PopulationError(ST.StateError):
    """The read is not in the layout the population needs, or two lines name one site."""


def commons_thumbnail_sql(column: str = "u.thumbnail_url") -> str:
    """The SQL predicate of a thumbnail that is a Commons file: on a Commons host, under
    `/wikipedia/commons/` (`served_image.state.file_of_url` reads the same shape)."""
    hosts = ", ".join(f"'{host}'" for host in COMMONS_HOSTS)
    return (
        f"(split_part({column}, '/', 3) IN ({hosts}) AND split_part({column}, '/', 4) = 'wikipedia' "
        f"AND split_part({column}, '/', 5) = 'commons')"
    )


def third_party_thumbnail_sql(column: str = "u.thumbnail_url") -> str:
    """The SQL predicate of a thumbnail hotlinked from a third party (D59): an http(s) address
    that is no Commons file."""
    return f"({column} ~* '^https?://' AND NOT {commons_thumbnail_sql(column)})"


def is_commons_thumbnail(url: str | None) -> bool:
    """`commons_thumbnail_sql` in Python, for one value."""
    parts = str(url or "").split("/")
    return len(parts) > 4 and parts[2] in COMMONS_HOSTS and parts[3:5] == ["wikipedia", "commons"]


def is_third_party_thumbnail(url: str | None) -> bool:
    """`third_party_thumbnail_sql` in Python, for one value."""
    text = str(url or "")
    return text.lower().startswith(("http://", "https://")) and not is_commons_thumbnail(text)


#: Which thumbnail a population line may carry: the research's (none, or a third-party hotlink,
#: D17 and D59) or D59's credit lane (a hotlinked Commons file).
RESEARCH, COMMONS_THUMBNAIL = "research", "commons_thumbnail"


def population_sql(sites: Sequence[str] | None = None, *, kind: str = RESEARCH) -> str:
    """The read-only statement. With `sites` it is restricted to those ids (a pilot, or the 47
    heroes D15 clears); the definition of "serves no picture" is the same either way. `kind`
    `commons_thumbnail` reads the sites D59 credits instead: no live row, and a thumbnail that is a
    hotlinked Commons file."""
    restriction = ""
    if sites is not None:
        ids = ", ".join(f"'{sid}'::uuid" for sid in sites)
        restriction = f"AND u.id IN ({ids})"
    if kind == RESEARCH:
        thumbnail = f"(coalesce(u.thumbnail_url, '') = '' OR {third_party_thumbnail_sql()})"
    elif kind == COMMONS_THUMBNAIL:
        thumbnail = commons_thumbnail_sql()
    else:
        raise PopulationError(f"kind {kind!r} is not {RESEARCH!r} or {COMMONS_THUMBNAIL!r}")
    return f"""SELECT row_to_json(t) FROM (
  SELECT u.id::text AS site_id, u.name, u.country, u.site_type, u.lat, u.lon, u.thumbnail_url,
         left(coalesce(u.description, ''), {DESCRIPTION_CHARS}) AS description,
         coalesce((SELECT json_agg(DISTINCT e.value) FROM site_external_ids e
                    WHERE e.site_id = u.id AND e.kind = '{QID_KIND}'), '[]'::json) AS qids,
         coalesce((SELECT json_agg(DISTINCT e.value) FROM site_external_ids e
                    WHERE e.site_id = u.id AND e.kind = '{ENWIKI_KIND}'), '[]'::json)
           AS enwiki_titles,
         u.raw_data -> '{_COORD.key}' ->> 'kind' AS coord_kind,
         (u.raw_data -> '{_COORD.key}' ->> 'sha') IS NOT DISTINCT FROM {sha_sql(_COORD, "u.")}
           AS coord_marker_current,
         coalesce((SELECT json_agg(json_build_object(
                     'filename', w.filename, 'original_url', w.original_url,
                     'commons_page_url', w.commons_page_url, 'is_excluded', w.is_excluded))
                    FROM wiki_images w WHERE w.site_id = u.id), '[]'::json) AS rows
    FROM unified_sites u
   WHERE u.source_id = 'ancient_nerds' AND u.scope_status IS DISTINCT FROM 'retired'
     AND NOT EXISTS (SELECT 1 FROM wiki_images w WHERE w.site_id = u.id AND NOT w.is_excluded)
     AND {thumbnail} {restriction}
   ORDER BY u.id
) t;"""


def _single(values: Sequence[str]) -> tuple[str | None, list[str] | None]:
    """`(the value, None)` for one value, `(None, None)` for none, `(None, all of them)` for a
    conflict."""
    distinct = sorted({v for v in values if v})
    if len(distinct) == 1:
        return distinct[0], None
    return (None, None) if not distinct else (None, distinct)


def held_files(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """The Commons files the site's rows (excluded ones too) name, in title form, each once."""
    out: list[str] = []
    for row in rows:
        name = ST.file_of_row(row)
        if name and name not in out:
            out.append(name)
    return out


def site_record(row: Mapping[str, Any]) -> dict[str, Any]:
    """One population line from a read line: identity from `site_external_ids`, the point's
    provenance, the files held."""
    qid, qid_conflict = _single(row["qids"])
    title, title_conflict = _single(row["enwiki_titles"])
    kind = row.get("coord_kind")
    return {
        "site_id": str(row["site_id"]),
        "name": row["name"],
        "country": row.get("country"),
        "site_type": row.get("site_type"),
        "lat": row["lat"],
        "lon": row["lon"],
        "thumbnail_url": row.get("thumbnail_url") or None,
        "description": str(row.get("description") or "").strip() or None,
        "qid": qid,
        "qid_conflict": qid_conflict,
        "enwiki_title": title,
        "enwiki_conflict": title_conflict,
        "coord_kind": kind,
        "coord_sourced": bool(kind in SOURCED_KINDS and row.get("coord_marker_current")),
        "held_files": held_files(row["rows"]),
    }


def build(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The population lines, one per site, in id order; a site twice is refused."""
    out = [site_record(row) for row in rows]
    ids = [r["site_id"] for r in out]
    if len(set(ids)) != len(ids):
        raise PopulationError("the read names a site twice")
    return sorted(out, key=lambda r: r["site_id"])


def write_population(path: Path, sites: Sequence[Mapping[str, Any]]) -> str:
    """`POPULATION.jsonl`, written once. Returns its sha256."""
    if not sites:
        raise PopulationError("the population is empty - the read answered no site")
    return ST.write_text_once(path, ST.jsonl_text(sites))


def load_population(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise PopulationError(f"{path} does not exist - read the population first")
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def counts(sites: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """What the population is made of, for the report."""
    return {
        "sites": len(sites),
        "with_qid": sum(1 for s in sites if s["qid"]),
        "qid_conflict": sum(1 for s in sites if s["qid_conflict"]),
        "with_enwiki": sum(1 for s in sites if s["enwiki_title"]),
        "enwiki_conflict": sum(1 for s in sites if s["enwiki_conflict"]),
        "no_identity": sum(1 for s in sites if not s["qid"] and not s["enwiki_title"]),
        "coord_sourced": sum(1 for s in sites if s["coord_sourced"]),
        "with_excluded_rows": sum(1 for s in sites if s["held_files"]),
        "third_party_thumbnail": sum(
            1 for s in sites if is_third_party_thumbnail(s.get("thumbnail_url"))
        ),
    }
