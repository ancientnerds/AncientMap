"""The site export: unified_sites ids -> the curated coordinates and country the globe shows.

Owner decision 15 (2026-09-26): the dots of a type-B world distribution come from our database
by site id, as the curated coordinates the globe shows, read from the repo-root export
`public/data/sites/index.json` ({"sites": [{"i": <site id>, "la": lat, "lo": lng,
"s": <source id>, "c": <country, only when known>, ...}]}); no network, no DB. Only curated
sites count: source `ancient_nerds`, the one source the globe shows on first load
(`source_meta.enabled_by_default`). The export also carries the raw sites of every other
source (1.9 million in all), whose coordinates nobody curated; a site id of another source, or
an unknown one, is a StudioError naming the id and, when the export has it, its source.

The export is gitignored and 360+ MB (reading it took 23 s, measured 2026-09-26 on the main
checkout's copy): I13 downloads the current one read-only from production into this checkout
(never the main checkout's copy of 2026-03-26). It is read only when a spec needs it (a
distribution's `site_ids`, a Mapbox take's `country`), once per process; the curated sites'
i, la, lo and c and every other site's source are kept. `doctor` reports its age.

A distribution capture spec names its dots as `site_ids`; `resolve_capture_spec` turns them
into unlabelled places after the labelled ones, the spec the recorder receives and the one
`capture_spec_sha256` hashes, so a changed export records the take again. `site_country` is
the country a Mapbox fly-in or orbit may highlight (C7, `episode.country_problems`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.studio.config import REPO
from pipeline.studio.errors import StudioError
from pipeline.utils.slugs import BASE_URL

SITES_INDEX = REPO / "public" / "data" / "sites" / "index.json"
EXPORT_URL = f"{BASE_URL}/data/sites/index.json"
#: The read-only download, run from the repo root: `--create-dirs` makes the gitignored
#: public/data/sites/, and `-R` keeps the server's Last-Modified as the file's mtime, the
#: export's age `doctor` reports.
DOWNLOAD = f"curl -sfR --create-dirs -o public/data/sites/index.json {EXPORT_URL}"
#: The curated source: the one the globe shows on first load (source_meta.enabled_by_default).
CURATED_SOURCE = "ancient_nerds"


@dataclass(frozen=True)
class Site:
    lat: float
    lng: float
    country: str | None


@dataclass(frozen=True)
class SiteExport:
    curated: dict[str, Site]
    other_sources: dict[str, str]


_LOADED: dict[Path, SiteExport] = {}


def site_export() -> SiteExport:
    """The repo-root export's curated sites and every other site's source, read once per
    process and path."""
    path = SITES_INDEX
    if path not in _LOADED:
        if not path.exists():
            raise StudioError(
                "public/data/sites/index.json is missing: download it from the repo root with "
                f"{DOWNLOAD}"
            )
        rows = json.loads(path.read_text(encoding="utf-8"))["sites"]
        _LOADED[path] = SiteExport(
            curated={
                r["i"]: Site(r["la"], r["lo"], r.get("c"))  # the exporter writes c only when known
                for r in rows
                if r["s"] == CURATED_SOURCE
            },
            other_sources={r["i"]: r["s"] for r in rows if r["s"] != CURATED_SOURCE},
        )
    return _LOADED[path]


def curated_site(cid: str, site_id: str) -> Site:
    """The curated site `site_id` that capture `cid` shows; any other id is a StudioError."""
    export = site_export()
    if site_id in export.curated:
        return export.curated[site_id]
    source = export.other_sources.get(site_id)
    if source is not None:
        raise StudioError(
            f"capture {cid}: site {site_id} comes from source {source}, not the curated "
            f"{CURATED_SOURCE} sites (only curated coordinates are shown)"
        )
    raise StudioError(f"capture {cid}: site {site_id} is not in public/data/sites/index.json")


def site_country(cid: str, site_id: str) -> str | None:
    """The export's country of the curated site `site_id`; None when it records none."""
    return curated_site(cid, site_id).country


def resolve_capture_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """The spec a recorder receives: a distribution's `site_ids` become unlabelled places
    {id, lat, lng} after its labelled places; any other spec is returned as it is."""
    if "site_ids" not in spec:
        return spec
    cid, site_ids = spec["id"], spec["site_ids"]
    if not isinstance(site_ids, list) or not all(isinstance(s, str) for s in site_ids):
        raise StudioError(f"capture {cid}: site_ids must be a list of unique site ids")
    dots = []
    for sid in site_ids:
        site = curated_site(cid, sid)
        dots.append({"id": sid, "lat": site.lat, "lng": site.lng})
    resolved = {k: v for k, v in spec.items() if k != "site_ids"}
    resolved["places"] = [*spec.get("places", []), *dots]
    return resolved
