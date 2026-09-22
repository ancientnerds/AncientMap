"""Which stored country contradicts the site's own coordinates, per the project's boundary file.

This is the cheapest possible check on a field the finder has to guess from prose: the coordinates are
part of every row and the polygons ship with the repository, so a point-in-polygon test needs no model,
no network and no judgement. It answers two questions at once - which stored countries are wrong
(a correction nobody has to review) and, for the writer, whether a *proposed* country agrees with the
place it claims to describe.

The alias map is derived from the database's own vocabulary, not from imagination: the query over all
5,004 curated sites returns 96 spellings, and only these groups differ from the boundary file's names.
`England`, `Wales`, `Scotland` and `Northern Ireland` are parts of the United Kingdom and are therefore
not contradictions - they are *more* specific, the same distinction the `site_type` proposals show.

Usage: point it at a JSONL whose lines carry `lat`/`lon`/`country` (`--input`), or let it read the
database snapshot from `output/remediation/logs/_sites_geo.txt`, which this file does not fetch: a
census query is a deliberate step, not a side effect of a report.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys
import unicodedata

import shapely
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

ROOT = pathlib.Path(r"C:/PythonProjects/AncientMap")
BOUNDARIES = ROOT / "data/boundaries/countries.geojson"

#: Spellings the database uses for a country the boundary file names differently. Measured against
#: `SELECT DISTINCT country` over the 5,004 curated sites on 2026-09-21: these are all of them.
ALIASES: dict[str, str] = {
    "england": "united kingdom",
    "wales": "united kingdom",
    "scotland": "united kingdom",
    "northern ireland": "united kingdom",
    "turkiye": "turkey",
    "serbia": "serbia",
    "republic of serbia": "serbia",
    "usa": "united states of america",
    "united states": "united states of america",
    "republic of the gambia": "gambia",
}


def fold(name: str) -> str:
    """A comparable spelling: no accents, no case, no hyphen noise."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(plain.lower().replace("-", " ").split())


def canonical(name: str) -> str:
    return ALIASES.get(fold(name), fold(name))


def load_countries() -> tuple[list[str], list[BaseGeometry], shapely.STRtree]:
    try:
        payload = json.loads(BOUNDARIES.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{BOUNDARIES}: the country boundaries are not readable: {exc}") from exc
    features = payload.get("features") or []
    if not features:
        raise ValueError(f"{BOUNDARIES}: no features")
    names: list[str] = []
    geometries: list[BaseGeometry] = []
    for feature in features:
        names.append(str((feature.get("properties") or {}).get("name") or "?"))
        geometries.append(shape(feature["geometry"]))
    return names, geometries, shapely.STRtree(geometries)


def country_at(
    names: list[str], geometries: list[BaseGeometry], tree: shapely.STRtree, lat: float, lon: float
) -> list[str]:
    point = shapely.Point(lon, lat)
    return sorted(
        {names[index] for index in tree.query(point) if geometries[index].contains(point)}
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="country-census")
    parser.add_argument("--input", default=str(ROOT / "output/remediation/logs/_sites_geo.txt"))
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument(
        "--out", default="", help="write every contradiction as id|name|stored|found|lat|lon"
    )
    args = parser.parse_args()

    names, geometries, tree = load_countries()
    rows: list[tuple[str, str, str, float, float]] = []
    for number, line in enumerate(
        pathlib.Path(args.input).read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) != 5:
            raise ValueError(f"{args.input}:{number}: expected 5 fields, found {len(parts)}")
        site_id, name, country, lat_text, lon_text = parts
        try:
            latitude, longitude = float(lat_text), float(lon_text)
        except ValueError as exc:
            raise ValueError(
                f"{args.input}:{number}: coordinates are not numbers: {lat_text!r}/{lon_text!r}"
            ) from exc
        rows.append((site_id, name, country, latitude, longitude))

    agree = disagree = outside = 0
    details: list[str] = []
    by_pair: collections.Counter[tuple[str, str]] = collections.Counter()
    examples: dict[tuple[str, str], tuple[str, str]] = {}
    for site_id, name, country, latitude, longitude in rows:
        found_names = country_at(names, geometries, tree, latitude, longitude)
        if not found_names:
            outside += 1
            continue
        if canonical(country) in {canonical(item) for item in found_names}:
            agree += 1
            continue
        disagree += 1
        pair = (country, ", ".join(found_names))
        by_pair[pair] += 1
        examples.setdefault(pair, (site_id, name))
        details.append(
            f"{site_id}|{name}|{country}|{', '.join(found_names)}|{latitude}|{longitude}"
        )

    print(f"Sites geprueft: {len(rows)} | Land passt zu den Koordinaten: {agree}")
    print(f"Land widerspricht den Koordinaten: {disagree} | Punkt in keiner Flaeche: {outside}")
    print("\n-- die haeufigsten Widersprueche (Bestand -> laut Grenzen):")
    for (stored, found_text), count in by_pair.most_common(args.limit):
        site_id, name = examples[(stored, found_text)]
        print(f"   {count:5}x  {stored!r:24} -> {found_text:26} z. B. {name[:34]} ({site_id[:8]})")
    if args.out:
        pathlib.Path(args.out).write_text("\n".join(details) + "\n", encoding="utf-8")
        print(f"\nListe aller Widersprueche: {args.out} ({len(details)} Zeilen)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
