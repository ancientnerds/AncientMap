"""Empire tagger — tag each site with which empires it belonged to.

Uses point-in-polygon testing against the GeoJSON historical boundaries.
For each site, finds the closest snapshot year within the empire's date range,
then tests if the site's coordinates fall within that empire's polygon.
"""

import json
from pathlib import Path

from shapely.geometry import Point, shape

# Historical boundaries data directory
HISTORICAL_DIR = Path("public/data/historical")


def _load_empire_metadata(empire_dir: Path) -> dict | None:
    """Load metadata.json for an empire."""
    meta_path = empire_dir / "metadata.json"
    if not meta_path.exists():
        return None
    with open(meta_path, encoding="utf-8") as f:
        return json.load(f)


def _load_geojson(empire_dir: Path, year: int) -> dict | None:
    """Load a specific year's GeoJSON for an empire."""
    geojson_path = empire_dir / f"{year}.geojson"
    if not geojson_path.exists():
        return None
    with open(geojson_path, encoding="utf-8") as f:
        return json.load(f)


def _find_closest_year(years: list[int], target: int) -> int:
    """Find the year in the list closest to target."""
    return min(years, key=lambda y: abs(y - target))


def _point_in_geojson(lon: float, lat: float, geojson: dict) -> bool:
    """Test if a point falls within any polygon in the GeoJSON FeatureCollection."""
    point = Point(lon, lat)
    for feature in geojson.get("features", []):
        geom = feature.get("geometry")
        if not geom:
            continue
        polygon = shape(geom)
        if polygon.contains(point):
            return True
    return False


def _load_all_empires() -> dict[str, dict]:
    """Load all empire metadata from the historical boundaries directory.

    Returns: {empire_id: metadata_dict}
    """
    empires = {}
    if not HISTORICAL_DIR.exists():
        return empires

    for empire_dir in HISTORICAL_DIR.iterdir():
        if not empire_dir.is_dir():
            continue
        meta = _load_empire_metadata(empire_dir)
        if meta and meta.get("years"):
            empires[meta["id"]] = meta
    return empires


# Module-level cache for loaded empires and GeoJSON
_empire_cache: dict[str, dict] | None = None
_geojson_cache: dict[tuple[str, int], dict] = {}


def _get_empires() -> dict[str, dict]:
    """Get cached empire metadata."""
    global _empire_cache
    if _empire_cache is None:
        _empire_cache = _load_all_empires()
    return _empire_cache


def tag_site(
    lat: float,
    lon: float,
    period_start: int | None,
) -> list[str]:
    """Tag a site with all empires whose territory contains it.

    Args:
        lat: Site latitude
        lon: Site longitude
        period_start: Site's period_start year (negative for BCE)

    Returns:
        List of empire_id strings this site belongs to.
    """
    empires = _get_empires()
    matched: list[str] = []

    for empire_id, meta in empires.items():
        start_year = meta.get("startYear", 0)
        end_year = meta.get("endYear", 0)
        years = meta.get("years", [])

        if not years:
            continue

        # Only match if site's period_start falls within empire's date range
        if period_start is not None:
            if period_start < start_year or period_start > end_year:
                continue
            # Find the closest snapshot year to the site's period
            target_year = _find_closest_year(years, period_start)
        else:
            # No period_start — use the empire's peak year
            target_year = meta.get("peakYear", years[len(years) // 2])

        # Load GeoJSON (with cache)
        cache_key = (empire_id, target_year)
        if cache_key not in _geojson_cache:
            empire_dir = HISTORICAL_DIR / empire_id
            geojson = _load_geojson(empire_dir, target_year)
            if geojson is None:
                continue
            _geojson_cache[cache_key] = geojson
        else:
            geojson = _geojson_cache[cache_key]

        if _point_in_geojson(lon, lat, geojson):
            matched.append(empire_id)

    return matched


def tag_sites_batch(
    sites: list[dict],
) -> dict[str, list[str]]:
    """Tag a batch of sites with empire affiliations.

    Args:
        sites: List of dicts with keys: id, lat, lon, period_start

    Returns:
        {site_id: [empire_id, ...]}
    """
    results = {}
    for site in sites:
        empires = tag_site(
            lat=site["lat"],
            lon=site["lon"],
            period_start=site.get("period_start"),
        )
        results[site["id"]] = empires
    return results
