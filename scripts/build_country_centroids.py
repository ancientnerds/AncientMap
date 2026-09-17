"""One-off: Natural Earth 110m (public domain) -> the founders dashboard's map data.

Two files, both committed:

    ancient-nerds-map/src/data/world_land.json           land outline as outer rings (~65 KB, bundled)
    ancient-nerds-map/src/data/country_centroids.json    ISO-2 -> [lon, lat] bbox centre (~5 KB)

Umami stores country codes, not coordinates, so the visitor dots sit on the
centre of each country's bounding box -- of its largest polygon only: the
plain bbox put France in the Atlantic (French Guiana) and the United States
in Oregon (Alaska, Hawaii). Re-run only when Natural Earth changes (it
rarely does):

    python scripts/build_country_centroids.py
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
LAND_OUT = PROJECT_ROOT / "ancient-nerds-map" / "src" / "data" / "world_land.json"
CENTROIDS_OUT = PROJECT_ROOT / "ancient-nerds-map" / "src" / "data" / "country_centroids.json"


def ring_area(ring: list[list[float]]) -> float:
    """Shoelace area of one ring in square degrees (good enough to rank polygons)."""
    total = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1], strict=True):
        total += x1 * y2 - x2 * y1
    return abs(total) / 2


def bbox_center(geometry: dict) -> list[float]:
    """Centre of the bounding box of the largest polygon (outer ring), rounded to 0.01 deg."""
    polygons = (
        [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    )
    outer = max((polygon[0] for polygon in polygons), key=ring_area)
    xs = [x for x, _ in outer]
    ys = [y for _, y in outer]
    return [round((min(xs) + max(xs)) / 2, 2), round((min(ys) + max(ys)) / 2, 2)]


def iso2(properties: dict) -> str | None:
    """Natural Earth's ISO_A2 is -99 for France, Norway and a few others;
    ISO_A2_EH carries the code everybody else uses."""
    for key in ("ISO_A2_EH", "ISO_A2"):
        code = properties.get(key)
        if code and code != "-99":
            return code
    return None


#: Outer rings only, rounded to one decimal, specks dropped: the dashboard map
#: is 1000x500 px, where a tenth of a degree is under a pixel and an island of
#: half a square degree is invisible. Keeps the bundled file at ~65 KB, and out
#: of LFS (every *.geojson in this repo is an LFS object).
MIN_RING_AREA = 0.6


def _ring_area(ring: list) -> float:
    a = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False):
        a += x1 * y2 - x2 * y1
    return abs(a) / 2


def land_rings(land: dict) -> list:
    """Natural Earth land FeatureCollection -> [[ [lon, lat], ... ], ...]."""
    rings = []
    for feature in land["features"]:
        geometry = feature["geometry"]
        polygons = (
            [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        )
        for polygon in polygons:
            ring, last = [], None
            for x, y in polygon[0]:
                point = [round(x, 1), round(y, 1)]
                if point != last:
                    ring.append(point)
                    last = point
            if len(ring) >= 4 and _ring_area(ring) >= MIN_RING_AREA:
                rings.append(ring)
    return rings


#: Natural Earth 110m drops states smaller than a pixel at that scale, so
#: a visitor from Singapore or Bahrain had no dot on the dashboard map
#: (seen live 2026-09-17). Hand-set capital coordinates for the ones a
#: visitor realistically comes from.
SUPPLEMENT: dict[str, list[float]] = {
    "AD": [1.52, 42.51],
    "AW": [-69.97, 12.52],
    "BB": [-59.54, 13.19],
    "BH": [50.55, 26.07],
    "BM": [-64.75, 32.31],
    "CW": [-68.99, 12.17],
    "GG": [-2.58, 49.45],
    "GI": [-5.35, 36.14],
    "GU": [144.79, 13.44],
    "HK": [114.17, 22.32],
    "IM": [-4.55, 54.24],
    "JE": [-2.11, 49.21],
    "KY": [-81.25, 19.31],
    "LI": [9.55, 47.17],
    "MC": [7.42, 43.74],
    "MO": [113.54, 22.2],
    "MT": [14.38, 35.9],
    "MU": [57.55, -20.35],
    "MV": [73.51, 3.2],
    "SC": [55.49, -4.68],
    "SG": [103.82, 1.35],
    "SM": [12.46, 43.94],
    "VA": [12.45, 41.9],
}


def main() -> None:
    land = httpx.get(NE + "ne_110m_land.geojson", timeout=60, follow_redirects=True).json()
    LAND_OUT.parent.mkdir(parents=True, exist_ok=True)
    LAND_OUT.write_text(json.dumps(land_rings(land), separators=(",", ":")), encoding="utf-8")

    countries = httpx.get(
        NE + "ne_110m_admin_0_countries.geojson", timeout=60, follow_redirects=True
    ).json()
    out: dict[str, list[float]] = {}
    for feature in countries["features"]:
        code = iso2(feature["properties"])
        if code:
            out[code] = bbox_center(feature["geometry"])
    added = {k: v for k, v in SUPPLEMENT.items() if k not in out}
    out.update(added)
    print(f"{len(added)} supplementary centroids: {sorted(added)}")
    CENTROIDS_OUT.write_text(json.dumps(out, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"{len(land_rings(land))} land rings -> {LAND_OUT} ({LAND_OUT.stat().st_size // 1024} KB)"
    )
    print(f"{len(out)} countries -> {CENTROIDS_OUT}")


if __name__ == "__main__":
    main()
