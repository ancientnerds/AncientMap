"""Pure projection math of pipeline/studio/capture/projection.py."""

import math
import re
from pathlib import Path

import pytest

from pipeline.studio.capture.projection import (
    CAMERA_MAX_DISTANCE,
    CAMERA_MIN_DISTANCE,
    GLOBE_MAX_DISTANCE,
    GLOBE_MIN_DISTANCE,
    PLACES_BAND,
    fit_globe_distance,
    globe_fov_deg,
    globe_to_pixel,
    mercator_to_pixel,
    mercator_world_px,
    meters_per_pixel,
    surface_point,
)


def test_mercator_world_origin_and_edges():
    assert mercator_world_px(0, 0, 0) == pytest.approx((256, 256))
    assert mercator_world_px(0, -180, 1)[0] == pytest.approx(0)
    assert mercator_world_px(0, 180, 1)[0] == pytest.approx(1024)


def test_mercator_rejects_polar_latitudes():
    with pytest.raises(ValueError, match="Web Mercator range"):
        mercator_world_px(89, 0, 3)


def test_centre_maps_to_the_middle_of_the_view():
    assert mercator_to_pixel(
        34.0, 36.2, center_lat=34.0, center_lng=36.2, zoom=15, bearing=0, width=1280, height=720
    ) == pytest.approx((640, 360))


def test_bearing_rotates_the_map_under_the_view():
    east = {"center_lat": 0.0, "center_lng": 0.0, "zoom": 10, "width": 1000, "height": 1000}
    x0, y0 = mercator_to_pixel(0.0, 0.01, bearing=0, **east)
    assert x0 > 500 and y0 == pytest.approx(500)
    x90, y90 = mercator_to_pixel(0.0, 0.01, bearing=90, **east)
    assert x90 == pytest.approx(500) and y90 < 500  # bearing 90 puts east at the top


def test_meters_per_pixel_at_the_equator():
    assert meters_per_pixel(0, 0) == pytest.approx(78271.517, rel=1e-6)
    assert meters_per_pixel(60, 1) == pytest.approx(78271.517 / 4, rel=1e-6)


def test_the_site_narrows_its_field_of_view_when_zoomed_in():
    assert globe_fov_deg(2.44) == pytest.approx(60)
    assert globe_fov_deg(1.02) == pytest.approx(1.5)
    assert globe_fov_deg(1.35) == pytest.approx(15.1, abs=0.05)
    with pytest.raises(ValueError, match="outside 1.02..2.44"):
        globe_fov_deg(3)


def test_surface_point_matches_the_frontend_mapping():
    assert surface_point(0, 0) == pytest.approx((1, 0, 0), abs=1e-12)
    assert surface_point(90, 0)[1] == pytest.approx(1)


def test_camera_target_projects_to_the_centre():
    px = globe_to_pixel(
        34.0, 36.2, cam_lat=34.0, cam_lng=36.2, distance=1.8, width=1920, height=1080
    )
    assert px == pytest.approx((960, 540), abs=1e-6)


def test_points_east_and_north_land_right_and_up():
    kw = {"cam_lat": 0.0, "cam_lng": 0.0, "distance": 2.0, "width": 1920, "height": 1080}
    east = globe_to_pixel(0.0, 10.0, **kw)
    north = globe_to_pixel(10.0, 0.0, **kw)
    assert east is not None and east[0] > 960 and east[1] == pytest.approx(540)
    assert north is not None and north[1] < 540 and north[0] == pytest.approx(960)


def test_the_telephoto_view_spreads_nearby_places():
    near = globe_to_pixel(
        33.0, 36.2, cam_lat=34.0, cam_lng=36.2, distance=1.35, width=1920, height=1080
    )
    far = globe_to_pixel(
        33.0, 36.2, cam_lat=34.0, cam_lng=36.2, distance=2.4, width=1920, height=1080
    )
    assert near is not None and far is not None
    assert near[1] - 540 > 3 * (far[1] - 540)


def test_far_side_is_not_visible_and_poles_are_refused():
    kw = {"cam_lat": 0.0, "cam_lng": 0.0, "distance": 2.0, "width": 1920, "height": 1080}
    assert globe_to_pixel(0.0, 180.0, **kw) is None
    with pytest.raises(ValueError, match="poles"):
        globe_to_pixel(0, 0, cam_lat=89, cam_lng=0, distance=2, width=10, height=10)


def test_fit_frames_every_place_inside_the_label_band():
    places = [(29.98, 31.13), (37.97, 23.73), (41.89, 12.49), (34.0, 36.2)]
    lat, lng, distance = fit_globe_distance(places, width=1920, height=1080)
    assert distance <= GLOBE_MAX_DISTANCE
    x0, y0, x1, y1 = PLACES_BAND
    for p_lat, p_lng in places:
        px = globe_to_pixel(
            p_lat, p_lng, cam_lat=lat, cam_lng=lng, distance=distance, width=1920, height=1080
        )
        assert px is not None
        assert 1920 * x0 <= px[0] <= 1920 * x1 and 1080 * y0 <= px[1] <= 1080 * y1


def test_fit_refuses_places_around_the_whole_globe():
    with pytest.raises(ValueError):
        fit_globe_distance([(0, 0), (0, 120), (0, -120)], width=1920, height=1080)
    with pytest.raises(ValueError, match="no places"):
        fit_globe_distance([], width=1920, height=1080)


def test_fit_centres_a_single_place():
    lat, lng, _ = fit_globe_distance([(34.0, 36.2)], width=1920, height=1080)
    assert lat == pytest.approx(34.0) and lng == pytest.approx(36.2)
    assert math.isfinite(lat)


_GLOBE_SRC = Path(__file__).resolve().parents[4] / "ancient-nerds-map" / "src"


def _ts_number(path: Path, pattern: str) -> float:
    match = re.search(pattern, path.read_text(encoding="utf-8"))
    assert match, f"{pattern!r} not found in {path.name}"
    return float(match.group(1))


def test_globe_takes_stay_below_the_frontends_mapbox_switch():
    """GLOBE_MIN_DISTANCE keeps the page's zoom state under TRANSITION_POINT, read from the sources."""
    constants = _GLOBE_SRC / "config" / "globeConstants.ts"
    rendering = _GLOBE_SRC / "components" / "Globe" / "rendering"
    camera_block = r"export const CAMERA = \{[^}]*?"
    min_dist = _ts_number(constants, camera_block + r"\bMIN_DISTANCE:\s*([\d.]+)")
    max_dist = _ts_number(constants, camera_block + r"\bMAX_DISTANCE:\s*([\d.]+)")
    threejs_camera_max = _ts_number(constants, r"export const THREEJS_CAMERA_MAX = ([\d.]+)")
    transition = _ts_number(
        _GLOBE_SRC / "utils" / "unifiedZoom.ts", r"export const MAPBOX_SWITCH_PERCENT = ([\d.]+)"
    )
    effects = (rendering / "mapboxEffects.ts").read_text(encoding="utf-8")
    assert "export const TRANSITION_POINT = MAPBOX_SWITCH_PERCENT" in effects
    assert (min_dist, max_dist) == (CAMERA_MIN_DISTANCE, CAMERA_MAX_DISTANCE)
    scene_init = (rendering / "sceneInit.ts").read_text(encoding="utf-8")
    assert "const minDist = CAMERA.MIN_DISTANCE" in scene_init
    assert "const maxDist = CAMERA.MAX_DISTANCE" in scene_init
    loop = (rendering / "animationLoop.ts").read_text(encoding="utf-8")
    assert (
        "const scaledZoom = ((maxDist - cameraDist) / (maxDist - minDist)) * 100" in loop
        and "Math.min(66, (scaledZoom / THREEJS_CAMERA_MAX) * 66)" in loop
        and "ctx.setZoom(Math.round(zoomPct))" in loop
    ), "the animation loop's zoom sync changed; recompute GLOBE_MIN_DISTANCE"

    def zoom_state(distance: float) -> int:
        scaled = (max_dist - distance) / (max_dist - min_dist) * 100
        return math.floor(max(0.0, min(66.0, scaled / threejs_camera_max * 66)) + 0.5)

    # the orbit clamp before Mapbox is ready, as globeConstants.ts defines and applies it
    source = constants.read_text(encoding="utf-8")
    assert re.search(
        r"export const MAPBOX_SWITCH_DISTANCE =\s*CAMERA\.MAX_DISTANCE - \(THREEJS_CAMERA_MAX / "
        r"100\) \* \(CAMERA\.MAX_DISTANCE - CAMERA\.MIN_DISTANCE\)\n",
        source,
    ), "MAPBOX_SWITCH_DISTANCE changed; recompute GLOBE_MIN_DISTANCE"
    assert (
        "return state === 'ready' || state === 'failed' ? CAMERA.MIN_DISTANCE : "
        "MAPBOX_SWITCH_DISTANCE" in source
    ), "orbitMinDistance changed; recompute GLOBE_MIN_DISTANCE"
    switch_distance = max_dist - threejs_camera_max / 100 * (max_dist - min_dist)
    assert GLOBE_MIN_DISTANCE > switch_distance  # above the orbitMinDistance clamp
    assert zoom_state(GLOBE_MIN_DISTANCE) < transition
    assert zoom_state(round(GLOBE_MIN_DISTANCE - 0.02, 2)) >= transition  # the closest step
