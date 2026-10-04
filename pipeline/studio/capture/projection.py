"""Pure projection math for captures (spec 2026-09-26 section 4.5).

* Web Mercator with 512-px tiles, as Mapbox GL and the Static Images API use it:
  lat/lng -> pixel of an image with a given centre, zoom and bearing (top-down pins).
* Our Three.js globe: lat/lng -> pixel for the site's perspective camera at `distance`
  from the centre of the unit globe, looking at the centre, with the lat/lng mapping of
  latLngToPosition (ancient-nerds-map/src/utils/geoUtils.ts) and the site's telephoto
  field of view: 60 degrees at CAMERA.MAX_DISTANCE (2.44), narrowing linearly to 1.5
  degrees at CAMERA.MIN_DISTANCE (1.02) (Globe/rendering/animationLoop.ts). The places
  take reads the exact pixels from the page (window.__DEMO.screenPoint); this model only
  chooses a pose that frames all places.
"""

from __future__ import annotations

import math

TILE_SIZE = 512
EARTH_CIRCUMFERENCE_M = 40_075_016.686
# Web Mercator's latitude limit (atan(sinh(pi))): the square world Mapbox draws ends here.
MERCATOR_MAX_LAT = 85.05112878
# CAMERA.MIN_DISTANCE / MAX_DISTANCE of ancient-nerds-map/src/config/globeConstants.ts
CAMERA_MIN_DISTANCE = 1.02
CAMERA_MAX_DISTANCE = 2.44
FOV_AT_MAX_DEG = 60.0
FOV_RANGE_DEG = 58.5
# Studio globe takes stay at or above this distance so the page never leaves our vector
# globe. The frontend hands over to Mapbox by zoom state, not by
# CAMERA_EXTENDED.MAPBOX_ENABLE_DISTANCE: the animation loop (Globe/rendering/
# animationLoop.ts) sets the zoom state to round(min(66, ((2.44 - d) / 1.42 * 100) / 80 * 66))
# (THREEJS_CAMERA_MAX 80 of globeConstants.ts), and createAutoSwitchEffect
# (Globe/rendering/mapboxEffects.ts) turns on Mapbox mode at TRANSITION_POINT 66 once Mapbox
# is ready, and during a take the background queue gets it ready. Zoom state 66 holds for every
# d <= ~1.3126; before Mapbox is ready, orbitMinDistance clamps the orbit at
# MAPBOX_SWITCH_DISTANCE (1.304, globeConstants.ts), so a closer pose is silently drawn from
# there. 1.32 is the closest 0.02 step whose zoom state rounds to 65
# (tests/pipeline/studio/capture/test_capture_projection.py recomputes it from the sources).
GLOBE_MIN_DISTANCE = 1.32
GLOBE_MAX_DISTANCE = CAMERA_MAX_DISTANCE
# Where a lit place may sit in a 1920x1080 globe shot, as fractions (x0, y0, x1, y1): the
# renderer's GlobeShot draws each label to the right of its pin, and labels must stay in
# the title-safe area above the hook captions and the YouTube controls (the layout lint
# refused a label at y 946 of the first real places take, 2026-09-26).
PLACES_BAND = (0.12, 0.15, 0.78, 0.74)

Vec3 = tuple[float, float, float]


def mercator_world_px(lat: float, lng: float, zoom: float) -> tuple[float, float]:
    """World pixel of a point at `zoom` (world width TILE_SIZE * 2**zoom)."""
    if not -MERCATOR_MAX_LAT <= lat <= MERCATOR_MAX_LAT:
        raise ValueError(f"latitude {lat} outside the Web Mercator range")
    world = TILE_SIZE * 2**zoom
    x = (lng + 180.0) / 360.0 * world
    phi = math.radians(lat)
    y = (1 - math.log(math.tan(phi) + 1 / math.cos(phi)) / math.pi) / 2 * world
    return x, y


def mercator_to_pixel(
    lat: float,
    lng: float,
    *,
    center_lat: float,
    center_lng: float,
    zoom: float,
    bearing: float,
    width: float,
    height: float,
) -> tuple[float, float]:
    """Pixel of (lat, lng) in a width x height view centred on the centre point.

    Bearing is the compass direction at the top of the view (Mapbox), so the map is
    rotated counter-clockwise by `bearing` on screen.
    """
    cx, cy = mercator_world_px(center_lat, center_lng, zoom)
    px, py = mercator_world_px(lat, lng, zoom)
    dx, dy = px - cx, py - cy
    world = TILE_SIZE * 2**zoom
    if dx > world / 2:
        dx -= world
    elif dx < -world / 2:
        dx += world
    th = math.radians(-bearing)
    sx = dx * math.cos(th) - dy * math.sin(th)
    sy = dx * math.sin(th) + dy * math.cos(th)
    return width / 2 + sx, height / 2 + sy


def meters_per_pixel(lat: float, zoom: float) -> float:
    return EARTH_CIRCUMFERENCE_M * math.cos(math.radians(lat)) / (TILE_SIZE * 2**zoom)


def globe_fov_deg(distance: float) -> float:
    """The site's vertical field of view at a camera distance (the telephoto zoom)."""
    if not CAMERA_MIN_DISTANCE <= distance <= CAMERA_MAX_DISTANCE:
        raise ValueError(
            f"camera distance {distance} outside {CAMERA_MIN_DISTANCE}..{CAMERA_MAX_DISTANCE}"
        )
    zoom_t = (CAMERA_MAX_DISTANCE - distance) / (CAMERA_MAX_DISTANCE - CAMERA_MIN_DISTANCE)
    return FOV_AT_MAX_DEG - zoom_t * FOV_RANGE_DEG


def surface_point(lat: float, lng: float) -> Vec3:
    """latLngToPosition(lng, lat, 1) of the frontend."""
    phi = math.radians(90 - lat)
    theta = math.radians(lng + 180)
    return (-math.sin(phi) * math.cos(theta), math.cos(phi), math.sin(phi) * math.sin(theta))


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a: Vec3) -> Vec3:
    n = math.sqrt(_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n)


def globe_to_pixel(
    lat: float,
    lng: float,
    *,
    cam_lat: float,
    cam_lng: float,
    distance: float,
    width: float,
    height: float,
) -> tuple[float, float] | None:
    """Pixel of a surface point for the globe camera, or None on the far side of the globe."""
    if abs(cam_lat) > 85:
        raise ValueError(f"camera latitude {cam_lat}: lookAt degenerates near the poles")
    fov = globe_fov_deg(distance)
    cx, cy, cz = surface_point(cam_lat, cam_lng)
    cam = (cx * distance, cy * distance, cz * distance)
    point = surface_point(lat, lng)
    if _dot(point, cam) <= 1.0:
        return None
    forward = _norm((-cam[0], -cam[1], -cam[2]))
    right = _norm(_cross(forward, (0.0, 1.0, 0.0)))
    up = _cross(right, forward)
    v = (point[0] - cam[0], point[1] - cam[1], point[2] - cam[2])
    depth = _dot(v, forward)
    tan_half = math.tan(math.radians(fov) / 2)
    ndc_x = _dot(v, right) / (depth * tan_half * (width / height))
    ndc_y = _dot(v, up) / (depth * tan_half)
    return (ndc_x + 1) / 2 * width, (1 - ndc_y) / 2 * height


def fit_globe_distance(
    points: list[tuple[float, float]],
    *,
    width: float,
    height: float,
    band: tuple[float, float, float, float] = PLACES_BAND,
) -> tuple[float, float, float]:
    """Camera (lat, lng, distance) that shows every (lat, lng) inside `band` (fractions).

    The camera looks at the normalised mean of the surface points and moves out in
    0.02 steps from GLOBE_MIN_DISTANCE; raises when even GLOBE_MAX_DISTANCE cannot show
    them all (the places span too much of the globe for one shot).
    """
    if not points:
        raise ValueError("no places to frame")
    mean = [0.0, 0.0, 0.0]
    for lat, lng in points:
        p = surface_point(lat, lng)
        mean = [mean[i] + p[i] for i in range(3)]
    if math.sqrt(sum(c * c for c in mean)) < 1e-6:
        raise ValueError("places surround the globe; no single view shows them")
    c = _norm((mean[0], mean[1], mean[2]))
    cam_lat = math.degrees(math.asin(max(-1.0, min(1.0, c[1]))))
    cam_lng = math.degrees(math.atan2(c[2], -c[0])) - 180
    if cam_lng < -180:
        cam_lng += 360
    lo_x, lo_y, hi_x, hi_y = band[0] * width, band[1] * height, band[2] * width, band[3] * height
    steps = round((GLOBE_MAX_DISTANCE - GLOBE_MIN_DISTANCE) / 0.02)
    for i in range(steps + 1):
        d = round(GLOBE_MIN_DISTANCE + i * 0.02, 2)
        pixels = [
            globe_to_pixel(
                lat, lng, cam_lat=cam_lat, cam_lng=cam_lng, distance=d, width=width, height=height
            )
            for lat, lng in points
        ]
        if all(p is not None and lo_x <= p[0] <= hi_x and lo_y <= p[1] <= hi_y for p in pixels):
            return cam_lat, cam_lng, d
    raise ValueError(
        f"{len(points)} places do not fit one globe view (max distance {GLOBE_MAX_DISTANCE})"
    )
