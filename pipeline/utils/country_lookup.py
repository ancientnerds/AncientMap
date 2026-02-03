"""
Country lookup utility for reverse geocoding coordinates to country names.

Uses a pre-built country boundaries dataset for fast point-in-polygon lookups.
Falls back to a simple lat/lon bounding box approach when shapely is not available.
"""

import json
from functools import lru_cache
from pathlib import Path

from loguru import logger

# Try to import shapely for precise polygon lookups
try:
    from shapely.geometry import Point, shape
    from shapely.strtree import STRtree
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False
    logger.warning("Shapely not available, using bounding box fallback for country lookup")


# Path to country boundaries data
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "boundaries"
COUNTRIES_FILE = DATA_DIR / "countries.geojson"


class CountryLookup:
    """
    Fast country lookup from coordinates using spatial indexing.

    Usage:
        lookup = CountryLookup()
        country = lookup.get_country(45.0, 12.0)  # Returns "Italy"
    """

    def __init__(self):
        self._countries: list[dict] = []
        self._spatial_index = None
        self._geometries = []
        self._loaded = False

    def _load_data(self):
        """Load country boundaries data lazily."""
        if self._loaded:
            return

        if not COUNTRIES_FILE.exists():
            logger.warning(f"Country boundaries file not found: {COUNTRIES_FILE}")
            logger.info("Run 'python -m pipeline.utils.country_lookup --download' to fetch data")
            self._loaded = True
            return

        try:
            with open(COUNTRIES_FILE, encoding="utf-8") as f:
                data = json.load(f)

            features = data.get("features", [])
            logger.info(f"Loading {len(features)} country boundaries...")

            if SHAPELY_AVAILABLE:
                # Build spatial index for fast lookups
                for feature in features:
                    props = feature.get("properties", {})
                    geom = feature.get("geometry")

                    if geom:
                        try:
                            shapely_geom = shape(geom)
                            self._geometries.append(shapely_geom)
                            self._countries.append({
                                "name": props.get("ADMIN") or props.get("name") or props.get("NAME"),
                                "iso_a2": props.get("ISO_A2") or props.get("iso_a2"),
                                "iso_a3": props.get("ISO_A3") or props.get("iso_a3"),
                            })
                        except Exception as e:
                            logger.debug(f"Failed to parse geometry: {e}")

                if self._geometries:
                    self._spatial_index = STRtree(self._geometries)
                    logger.info(f"Built spatial index with {len(self._geometries)} countries")
            else:
                # Fallback: store bounding boxes
                for feature in features:
                    props = feature.get("properties", {})
                    geom = feature.get("geometry")

                    if geom:
                        bbox = self._compute_bbox(geom)
                        if bbox:
                            self._countries.append({
                                "name": props.get("ADMIN") or props.get("name") or props.get("NAME"),
                                "iso_a2": props.get("ISO_A2") or props.get("iso_a2"),
                                "iso_a3": props.get("ISO_A3") or props.get("iso_a3"),
                                "bbox": bbox,
                                "geometry": geom,
                            })

                logger.info(f"Loaded {len(self._countries)} country bounding boxes")

        except Exception as e:
            logger.error(f"Failed to load country boundaries: {e}")

        self._loaded = True

    def _compute_bbox(self, geometry: dict) -> tuple[float, float, float, float] | None:
        """Compute bounding box from GeoJSON geometry."""
        coords = self._extract_all_coords(geometry)
        if not coords:
            return None

        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        return (min(lons), min(lats), max(lons), max(lats))

    def _extract_all_coords(self, geometry: dict) -> list[tuple[float, float]]:
        """Extract all coordinates from a GeoJSON geometry."""
        geom_type = geometry.get("type", "")
        coords = geometry.get("coordinates", [])

        result = []

        if geom_type == "Point":
            result.append(tuple(coords[:2]))
        elif geom_type == "MultiPoint" or geom_type == "LineString":
            result.extend([tuple(c[:2]) for c in coords])
        elif geom_type == "Polygon":
            for ring in coords:
                result.extend([tuple(c[:2]) for c in ring])
        elif geom_type == "MultiPolygon":
            for polygon in coords:
                for ring in polygon:
                    result.extend([tuple(c[:2]) for c in ring])
        elif geom_type == "MultiLineString":
            for line in coords:
                result.extend([tuple(c[:2]) for c in line])
        elif geom_type == "GeometryCollection":
            for geom in geometry.get("geometries", []):
                result.extend(self._extract_all_coords(geom))

        return result

    def _point_in_polygon(self, lon: float, lat: float, geometry: dict) -> bool:
        """Simple ray casting algorithm for point-in-polygon test."""
        coords = geometry.get("coordinates", [])
        geom_type = geometry.get("type", "")

        if geom_type == "Polygon":
            return self._point_in_polygon_rings(lon, lat, coords)
        elif geom_type == "MultiPolygon":
            for polygon in coords:
                if self._point_in_polygon_rings(lon, lat, polygon):
                    return True
        return False

    def _point_in_polygon_rings(self, lon: float, lat: float, rings: list) -> bool:
        """Check if point is in polygon defined by rings (exterior + holes)."""
        if not rings:
            return False

        # Check exterior ring
        exterior = rings[0]
        if not self._point_in_ring(lon, lat, exterior):
            return False

        # Check holes (should NOT be in any hole)
        for hole in rings[1:]:
            if self._point_in_ring(lon, lat, hole):
                return False

        return True

    def _point_in_ring(self, lon: float, lat: float, ring: list) -> bool:
        """Ray casting algorithm for point in ring."""
        n = len(ring)
        inside = False

        j = n - 1
        for i in range(n):
            xi, yi = ring[i][0], ring[i][1]
            xj, yj = ring[j][0], ring[j][1]

            if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
                inside = not inside
            j = i

        return inside

    def get_country(self, lat: float, lon: float) -> str | None:
        """
        Get country name for given coordinates.

        Args:
            lat: Latitude in degrees
            lon: Longitude in degrees

        Returns:
            Country name or None if not found
        """
        self._load_data()

        if not self._countries:
            return None

        if SHAPELY_AVAILABLE and self._spatial_index:
            point = Point(lon, lat)

            # Query spatial index for candidates
            candidates = self._spatial_index.query(point)

            for idx in candidates:
                if hasattr(idx, '__index__'):
                    idx = idx.__index__()
                if self._geometries[idx].contains(point):
                    return self._countries[idx]["name"]
        else:
            # Bounding box fallback
            for country in self._countries:
                bbox = country.get("bbox")
                if bbox:
                    min_lon, min_lat, max_lon, max_lat = bbox
                    if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
                        # Further check with polygon
                        if self._point_in_polygon(lon, lat, country.get("geometry", {})):
                            return country["name"]

        return None

    def get_country_iso(self, lat: float, lon: float) -> str | None:
        """Get ISO country code for given coordinates."""
        self._load_data()

        if not self._countries:
            return None

        if SHAPELY_AVAILABLE and self._spatial_index:
            point = Point(lon, lat)
            candidates = self._spatial_index.query(point)

            for idx in candidates:
                if hasattr(idx, '__index__'):
                    idx = idx.__index__()
                if self._geometries[idx].contains(point):
                    return self._countries[idx].get("iso_a2")
        else:
            for country in self._countries:
                bbox = country.get("bbox")
                if bbox:
                    min_lon, min_lat, max_lon, max_lat = bbox
                    if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
                        if self._point_in_polygon(lon, lat, country.get("geometry", {})):
                            return country.get("iso_a2")

        return None


# Global singleton instance
_lookup_instance: CountryLookup | None = None


def get_country_lookup() -> CountryLookup:
    """Get singleton CountryLookup instance."""
    global _lookup_instance
    if _lookup_instance is None:
        _lookup_instance = CountryLookup()
    return _lookup_instance


@lru_cache(maxsize=10000)
def lookup_country(lat: float, lon: float) -> str | None:
    """
    Lookup country name from coordinates (cached).

    Args:
        lat: Latitude in degrees
        lon: Longitude in degrees

    Returns:
        Country name or None if not found
    """
    return get_country_lookup().get_country(lat, lon)


def download_country_boundaries():
    """Download Natural Earth country boundaries."""
    import io
    import urllib.request
    import zipfile

    # Natural Earth 110m cultural vectors (countries)
    # Small file (~800KB) good enough for most lookups
    url = "https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip"

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Downloading country boundaries from Natural Earth...")
    logger.info(f"URL: {url}")

    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()

        logger.info(f"Downloaded {len(data) / 1024:.1f} KB")

        # Extract GeoJSON from shapefile in zip
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            # Look for the .shp file and convert to GeoJSON
            shp_name = None
            for name in zf.namelist():
                if name.endswith('.shp'):
                    shp_name = name
                    break

            if shp_name:
                # We need to use a different approach - download GeoJSON directly
                pass

    except Exception as e:
        logger.warning(f"Failed to download shapefile: {e}")

    # Try GeoJSON endpoint instead
    geojson_url = "https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson"

    logger.info(f"Trying GeoJSON endpoint: {geojson_url}")

    try:
        with urllib.request.urlopen(geojson_url, timeout=120) as response:
            data = response.read()

        logger.info(f"Downloaded {len(data) / 1024 / 1024:.1f} MB")

        # Validate JSON
        json.loads(data)

        # Save to file
        with open(COUNTRIES_FILE, "wb") as f:
            f.write(data)

        logger.info(f"Saved to {COUNTRIES_FILE}")
        return True

    except Exception as e:
        logger.error(f"Failed to download GeoJSON: {e}")
        return False


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Country lookup utility")
    parser.add_argument("--download", action="store_true", help="Download country boundaries data")
    parser.add_argument("--test", action="store_true", help="Test lookup functionality")
    parser.add_argument("--lat", type=float, help="Latitude to lookup")
    parser.add_argument("--lon", type=float, help="Longitude to lookup")

    args = parser.parse_args()

    if args.download:
        success = download_country_boundaries()
        if success:
            print("Download successful!")
        else:
            print("Download failed!")
            exit(1)

    elif args.lat is not None and args.lon is not None:
        country = lookup_country(args.lat, args.lon)
        if country:
            print(f"Country: {country}")
        else:
            print("Country not found")

    elif args.test:
        # Test some known locations
        test_cases = [
            (41.9028, 12.4964, "Italy"),      # Rome
            (51.5074, -0.1278, "United Kingdom"),  # London
            (40.7128, -74.0060, "United States of America"),  # New York
            (35.6762, 139.6503, "Japan"),     # Tokyo
            (31.2304, 121.4737, "China"),     # Shanghai
            (-33.8688, 151.2093, "Australia"),  # Sydney
        ]

        print("Testing country lookup...")
        for lat, lon, expected in test_cases:
            result = lookup_country(lat, lon)
            status = "OK" if result and expected.lower() in result.lower() else "FAIL"
            print(f"  ({lat}, {lon}): {result} [{status}]")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
