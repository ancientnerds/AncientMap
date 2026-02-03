"""Geographic utility functions for the data pipeline."""

import math


def is_valid_coordinates(lat: float, lon: float) -> bool:
    """Check if latitude and longitude are valid.

    Args:
        lat: Latitude in degrees
        lon: Longitude in degrees

    Returns:
        True if coordinates are valid, False otherwise
    """
    return -90 <= lat <= 90 and -180 <= lon <= 180


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in kilometers.

    Uses the Haversine formula for accuracy on the Earth's surface.

    Args:
        lat1, lon1: First point coordinates in degrees
        lat2, lon2: Second point coordinates in degrees

    Returns:
        Distance in kilometers
    """
    R = 6371  # Earth radius in km

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = math.sin(delta_lat / 2) ** 2 + \
        math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def parse_wkt_point(wkt: str) -> tuple[float | None, float | None]:
    """Parse a WKT POINT string into lon, lat coordinates.

    Args:
        wkt: WKT string like "POINT(lon lat)" or "POINT (lon lat)"

    Returns:
        Tuple of (longitude, latitude) or (None, None) if parsing fails
    """
    if not wkt or not isinstance(wkt, str):
        return None, None

    wkt = wkt.strip().upper()
    if not wkt.startswith('POINT'):
        return None, None

    try:
        # Remove "POINT" prefix and parentheses
        coords_str = wkt.replace('POINT', '').strip()
        coords_str = coords_str.strip('()')

        # Split by space or comma
        parts = coords_str.replace(',', ' ').split()
        if len(parts) >= 2:
            lon = float(parts[0])
            lat = float(parts[1])
            return lon, lat
    except (ValueError, IndexError):
        pass

    return None, None


def get_centroid(geometry: dict) -> tuple[float | None, float | None]:
    """Extract centroid coordinates from a GeoJSON geometry object.

    Handles Point, Polygon, MultiPolygon, and other geometry types.

    Args:
        geometry: GeoJSON geometry dict with 'type' and 'coordinates'

    Returns:
        Tuple of (longitude, latitude) or (None, None) if extraction fails
    """
    if not geometry or not isinstance(geometry, dict):
        return None, None

    geom_type = geometry.get('type', '')
    coords = geometry.get('coordinates')

    if not coords:
        return None, None

    try:
        if geom_type == 'Point':
            return float(coords[0]), float(coords[1])

        elif geom_type == 'Polygon':
            # Use first ring (exterior)
            ring = coords[0] if coords else []
            if ring:
                lons = [p[0] for p in ring]
                lats = [p[1] for p in ring]
                return sum(lons) / len(lons), sum(lats) / len(lats)

        elif geom_type == 'MultiPolygon':
            # Centroid of all polygon centroids
            all_lons = []
            all_lats = []
            for polygon in coords:
                ring = polygon[0] if polygon else []
                for p in ring:
                    all_lons.append(p[0])
                    all_lats.append(p[1])
            if all_lons and all_lats:
                return sum(all_lons) / len(all_lons), sum(all_lats) / len(all_lats)

        elif geom_type == 'LineString':
            lons = [p[0] for p in coords]
            lats = [p[1] for p in coords]
            if lons and lats:
                return sum(lons) / len(lons), sum(lats) / len(lats)

        elif geom_type == 'MultiPoint':
            lons = [p[0] for p in coords]
            lats = [p[1] for p in coords]
            if lons and lats:
                return sum(lons) / len(lons), sum(lats) / len(lats)

    except (TypeError, IndexError, ValueError):
        pass

    return None, None


def normalize_coordinates(
    lat: float | None,
    lon: float | None
) -> tuple[float | None, float | None]:
    """Normalize and validate coordinate values.

    Args:
        lat: Latitude value (may need conversion)
        lon: Longitude value (may need conversion)

    Returns:
        Tuple of (lat, lon) if valid, or (None, None) if invalid
    """
    if lat is None or lon is None:
        return None, None

    try:
        lat = float(lat)
        lon = float(lon)

        # Handle common mistakes: swapped lat/lon
        if -180 <= lat <= 180 and -90 <= lon <= 90:
            if abs(lat) > 90 or abs(lon) > 180:
                # Might be swapped
                lat, lon = lon, lat

        if is_valid_coordinates(lat, lon):
            return lat, lon
    except (TypeError, ValueError):
        pass

    return None, None
