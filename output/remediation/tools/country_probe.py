"""Which country actually contains a site's coordinates, according to the project's own boundaries.

The country proposals are where the finder's evidence is least trustworthy: it matches a *name*, and a
name collides across continents (Lamay in the Yucatan against Lamay in Peru, Aquae Helveticae in Baden
against the word "Sweden"). The stored coordinates, by contrast, are not touched by any of these
writes and were curated for the map, so a proposed country has to agree with them.

`data/boundaries/countries.geojson` ships with the project and shapely is installed, so this is a
point-in-polygon test rather than a judgement. The probe prints what the polygons say for the ten rows
the reviewer cleared, and names the country feature's property key instead of guessing it.
"""

from __future__ import annotations

import json
import pathlib
import sys

import shapely
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

ROOT = pathlib.Path(r"C:/PythonProjects/AncientMap")
BOUNDARIES = ROOT / "data/boundaries/countries.geojson"

#: The ten rows the reviewer cleared on `country`, with the stored and the proposed value, read from
#: the run's own report (`review_totals.txt`), and the coordinates from `unified_sites`.
ROWS = [
    ("Tempio di Zeus, Selinunte", 37.588380040430636, 12.835345631334164, "Greece", "Italy"),
    ("Annadorn Dolmen", 54.342240332788286, -5.803509989113114, "Ireland", "United Kingdom"),
    ("Dooey's Cairn", 55.00172171882956, -6.404324529549039, "Ireland", "United Kingdom"),
    ("Giant's Ring", 54.54040225496907, -5.950000002593157, "Ireland", "United Kingdom"),
    ("Aquae Helveticae", 47.480571237954464, 8.31230218349371, "Sweden", "Switzerland"),
    ("Lamay", 18.643071631900728, -88.77041608886492, "Mexico", "Peru"),
    ("San Claudio", 17.33611505430358, -91.15885364841871, "Mexico", "Spain"),
    ("Soura", 36.24420044578491, 29.94544131414281, "Türkiye", "India"),
    ("Jaffa Gate", 31.776773353045204, 35.22802433664251, "Israel", "Palestine"),
    ("Ahin Posh Tape", 33.66801142959909, 70.95519786406209, "Afghanistan", "Pakistan"),
]


def load(shapes_path: pathlib.Path) -> list[tuple[str, BaseGeometry]]:
    try:
        payload = json.loads(shapes_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{shapes_path}: the country boundaries are not readable: {exc}") from exc
    features = payload.get("features") or []
    if not features:
        raise ValueError(f"{shapes_path}: no features")
    properties = features[0].get("properties") or {}
    key = next(
        (name for name in ("ADMIN", "NAME", "name", "admin", "SOVEREIGNT") if name in properties),
        None,
    )
    if key is None:
        raise ValueError(f"{shapes_path}: no country name property among {sorted(properties)}")
    print(
        f"Grenzdatei: {shapes_path.name}, {len(features)} Flaechen, Namensfeld '{key}'", flush=True
    )
    named = [
        (str(feature["properties"].get(key) or "?"), shape(feature["geometry"]))
        for feature in features
    ]
    return named


def main() -> int:
    named = load(BOUNDARIES)
    print(f"\n{'Site':26} {'Bestand':16} {'Vorschlag':16} {'laut Grenzen':16} Urteil")
    for name, lat, lon, stored, proposed in ROWS:
        point = shapely.Point(lon, lat)
        hits = [country for country, geometry in named if geometry.contains(point)]
        actual = ", ".join(hits) if hits else "(keine Flaeche)"
        if not hits:
            verdict = "unklar (keine Flaeche)"
        elif proposed in hits:
            verdict = "Vorschlag passt"
        elif stored in hits:
            verdict = "Vorschlag widerspricht den Koordinaten"
        else:
            verdict = "beide falsch laut Grenzen"
        print(f"{name:26} {stored:16} {proposed:16} {actual:16} {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
