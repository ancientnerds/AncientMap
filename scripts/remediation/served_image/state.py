"""Which image each curated site serves, read from production (read-only).

## How the served image is chosen (read at the source, 2026-09-26)

* The **site page** (`api/routes/sites_html.py`, the SSR detail route) and the **country hub** show
  the first `wiki_images` row of the site that is not excluded, `ORDER BY is_hero DESC, is_lead
  DESC, sort_order` - `gallery_audit.worklist.served_row`, the one spelling of that rule. The hub
  falls back to `unified_sites.thumbnail_url` when the site has no such row.
* The **globe popup** (`SitePopup/gallery/useGalleryData.ts`: `heroImageOverride || thumbnailUrl ||
  wikiHero`) shows `thumbnail_url` first, and the static export's `im` falls back to it.

So a site serves (a) its served gallery row, on the page and the hub, and (b) its `thumbnail_url`
on the globe - which is why the lane keeps the two on one file: the thumbnail of a site whose
served row is confirmed or replaced becomes that row's local file (`gallery_audit/decide.py` rule
T1, `hero_repair/thumbnail.py`). A site without a live row serves its `thumbnail_url` alone.

Measured on production (read-only, 2026-09-26): 4,926 curated sites are not retired; 3,927 have a
live row (at most 20), 999 have none, 157 of those carry a `thumbnail_url` (144 Commons hotlinks);
133 sites with live rows have no hero flag, none has two.

## A served image's Commons file

The page's row names its Commons file in `original_url` or `commons_page_url` (T09's helper via
`hero_repair.plan.commons_file_name`, never `title`). A thumbnail names it in its URL - an original
(`/wikipedia/commons/a/ab/Name.jpg`) or a thumbnail (`/wikipedia/commons/thumb/a/ab/Name.jpg/400px-
Name.jpg`, whose last segment is the rendering, not the file) - or it is a local path, whose file
is the Commons file of the site's own row with that local file. The name is compared in MediaWiki's
title form (`canonical_file`): underscores are spaces, runs of spaces are one, the first letter is
upper case.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (ROOT, ROOT / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from census.tests.t09_commons_dimensions import (  # noqa: E402 - T09's URL reading, not a copy
    _file_name_from_url,
)
from gallery_audit import chunk_writer as CW  # noqa: E402
from gallery_audit.worklist import served_row  # noqa: E402
from hero_repair.plan import commons_file_name  # noqa: E402
from hero_repair.thumbnail import local_path  # noqa: E402

CURATED_SOURCE = "ancient_nerds"

GALLERY = "gallery"
THUMBNAIL = "thumbnail"
NONE = "none"


class StateError(CW.ChunkError):
    """The read cannot be trusted or does not say what the lane needs. Nothing was written."""


# ------------------------------------------------------------------------------- the read
#: Every curated site the platform shows, with what the globe draws.
SITES_SQL = """SELECT row_to_json(t) FROM (
  SELECT u.id::text AS id, u.name, u.country, u.site_type, u.lat, u.lon, u.thumbnail_url
    FROM unified_sites u
   WHERE u.source_id = 'ancient_nerds' AND u.scope_status IS DISTINCT FROM 'retired'
   ORDER BY u.id
) t;"""

#: Every image row of those sites, excluded ones included (a thumbnail may name one).
IMAGES_SQL = """SELECT row_to_json(t) FROM (
  SELECT w.id, w.site_id::text AS site_id, w.filename, w.title, w.commons_page_url,
         w.original_url, w.is_hero, w.is_lead, w.is_excluded, w.sort_order, w.file_size_bytes
    FROM wiki_images w JOIN unified_sites u ON u.id = w.site_id
   WHERE u.source_id = 'ancient_nerds' AND u.scope_status IS DISTINCT FROM 'retired'
   ORDER BY w.site_id, w.id
) t;"""


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_production() -> dict[str, Any]:
    """The sites and their image rows, two read-only statements (`persist_verdicts.read_rows`)."""
    return {
        "read_at": _now(),
        "sites": CW.pv.read_rows(SITES_SQL),
        "images": CW.pv.read_rows(IMAGES_SQL),
    }


def write_read(path: Path, data: Mapping[str, Any]) -> str:
    """READ.json, written once per run directory. Returns its sha256."""
    if path.exists():
        raise StateError(f"{path} exists - a run's read is never replaced; use a new run directory")
    text = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=1) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return sha256_text(text)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    """sha256 of a text file read with universal newlines (a checkout may hand back CRLF)."""
    return sha256_text(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class State:
    """The read: the sites in id order and every image row of each."""

    read_at: str
    sites: Mapping[str, Mapping[str, Any]]
    rows: Mapping[str, tuple[Mapping[str, Any], ...]]
    sha256: str

    def site_ids(self) -> list[str]:
        return list(self.sites)


def load_read(path: Path) -> State:
    """READ.json as the lane reads it; a row of a site the read does not hold is refused."""
    if not path.is_file():
        raise StateError(f"{path} does not exist - run `run.py read` first")
    data = json.loads(path.read_text(encoding="utf-8"))
    sites = {str(s["id"]): s for s in data["sites"]}
    if not sites:
        raise StateError(f"{path} holds no site")
    rows: dict[str, list[Mapping[str, Any]]] = {}
    for row in data["images"]:
        sid = str(row["site_id"])
        if sid not in sites:
            raise StateError(f"image {row['id']} belongs to {sid}, which the read does not hold")
        rows.setdefault(sid, []).append(row)
    return State(
        read_at=str(data["read_at"]),
        sites=sites,
        rows={sid: tuple(rs) for sid, rs in rows.items()},
        sha256=file_sha256(path),
    )


# ------------------------------------------------------------------------- Commons names
_SPACES = re.compile(r" +")


def canonical_file(name: str) -> str:
    """A Commons file name in MediaWiki's title form: no `File:`, spaces, first letter upper."""
    text = name.strip()
    if text[:5].lower() == "file:":
        text = text[5:]
    text = _SPACES.sub(" ", text.replace("_", " ")).strip()
    if not text:
        raise StateError(f"{name!r} names no file")
    return text[0].upper() + text[1:]


def file_of_url(url: str | None) -> str | None:
    """The Commons file a URL shows, in title form, or None when it is no Commons file URL.

    A thumbnail URL (`.../commons/thumb/<a>/<ab>/<file>/<width>px-<file>`) names its file in the
    segment before the rendering; every other form is T09's reading.
    """
    if not url:
        return None
    parts = [unquote(p) for p in urlsplit(url).path.split("/")]
    host = (urlsplit(url).hostname or "").lower()
    if host.endswith("wikimedia.org") and "commons" in parts and "thumb" in parts:
        at = parts.index("thumb")
        if len(parts) > at + 3 and parts[at + 3]:
            return canonical_file(parts[at + 3])
        return None
    name = _file_name_from_url(url)
    return canonical_file(name) if name else None


def file_of_row(row: Mapping[str, Any]) -> str | None:
    name = commons_file_name(row)
    return canonical_file(name) if name else None


# ---------------------------------------------------------------------------- the served image
@dataclass(frozen=True)
class Served:
    """What a site serves: its served gallery row, else its thumbnail, else nothing.

    `file` is the Commons file (title form) or None when the image names none; `url` is what is
    served - the row's local path, or the thumbnail value.
    """

    site_id: str
    kind: str
    image_id: int | None
    file: str | None
    url: str | None

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


def served_of(site: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> Served:
    sid = str(site["id"])
    row = served_row(rows)
    if row is not None:
        return Served(
            sid, GALLERY, int(row["id"]), file_of_row(row), local_path(sid, str(row["filename"]))
        )
    thumb = site.get("thumbnail_url")
    if not thumb:
        return Served(sid, NONE, None, None, None)
    if str(thumb).startswith("/data/"):
        named = [r for r in rows if local_path(sid, str(r["filename"])) == thumb]
        if len(named) > 1:
            raise StateError(f"{sid}: two image rows share the thumbnail's file {thumb}")
        if named:
            return Served(sid, THUMBNAIL, int(named[0]["id"]), file_of_row(named[0]), str(thumb))
        return Served(sid, THUMBNAIL, None, None, str(thumb))
    return Served(sid, THUMBNAIL, None, file_of_url(str(thumb)), str(thumb))


def live_rows(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The rows that are not excluded, in the order the page would serve them."""
    order = []
    remaining = [r for r in rows if not r.get("is_excluded")]
    while remaining:
        head = served_row(remaining)
        if head is None:
            break
        order.append(head)
        remaining = [r for r in remaining if r is not head]
    return order
