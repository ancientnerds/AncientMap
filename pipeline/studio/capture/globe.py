"""Globe and Mapbox takes through the Puppeteer recorder (spec 2026-09-26 section 4.5).

Wraps ``npm run video:record`` (ancient-nerds-map/video/record.ts) with the landscape
studio scenes of ancient-nerds-map/video/scenes/studio-globe.ts and studio-mapbox.ts.
The scene input goes to ``captures/<id>.rec/input.json`` (``--input``; record.ts exposes
it as STUDIO_SCENE_INPUT). The scenes grab every frame exactly
(video/scenes/studio-frames.ts) into ``captures/<id>.rec/frames``; this module checks
the count, encodes the sequence (encode.sequence_to_mp4) and builds the manifest. Every
scene writes the page's WebGL renderer to renderer.json before its first frame, which must
name the NVIDIA (spec 4.11; the recorder launches Chrome with the NVIDIA flags) and becomes
the "gpu" event; the take reads it while the recorder runs (wait_recorder), so a take drawn
on another GPU stops at its first frame. The recorder gets RECORD_FRAME_S per frame. The
places scene, and a fly-to with a place, also write where the page drew each place in every
grabbed frame (points.json: {place id: [[x, y] | null, ...]}, one entry
per frame, from window.__DEMO.screenPoint): the owner's rule for globe markers is to
project them per frame from their coordinates, so the renderer's pins follow the globe
when the camera moves. The display is held awake for the take.

Specs (kind "globe"; duration_s is the length of the take, at most 30 s)::

    {"id": "g1", "kind": "globe", "scene": "flyto", "lat": 34.0067, "lng": 36.2033,
     "distance": 1.35, "empire": "roman" | null, "rotate_s": 1.5, "zoom_s": 2.0,
     "duration_s": 5, "place": {"id": "p1", "label": "Baalbek"}}  (empire, place optional)
    {"id": "g2", "kind": "globe", "scene": "places",
     "places": [{"id": "p1", "label": "Baalbek", "lat": .., "lng": ..}, ...],
     "lead_s": 0.8, "interval_s": 0.6, "duration_s": 6}           (a fixed pose framing all)
    {... "scene": "places", ..., "sweep_lng_deg": 120, "cam_lat": 30,
     "cam_lng_from": 0, "distance": 2.2}                            (the camera sweeps east)
    {"id": "g3", "kind": "globe", "scene": "distribution", "duration_s": 20,
     "places": [{"id": "p1", "lat": .., "lng": .., "label": "Baalbek"},
                {"id": "<site id>", "lat": .., "lng": ..}, ...]}     (1-500, label optional)
    {"id": "m1", "kind": "globe", "scene": "mapbox_flyin", "name": "Baalbek", "lat": ..,
     "lng": .., "country": "Lebanon", "orbit_zoom": 15.5, "duration_s": 8}
    {"id": "m2", "kind": "globe", "scene": "mapbox_orbit", "name": "Baalbek", "lat": ..,
     "lng": .., "zoom": 16.5, "pitch": 60, "bearing_from": 20, "bearing_to": 110,
     "duration_s": 6}

Events: flyto "rotate", "zoom", "arrive" (the frame centre) and, with a place, the
place's "place" event; places one "place" event per place at the first frame from
lead_s + i * interval_s on where the page draws it inside PLACES_BAND; a distribution
(one full turn of the globe, the whole globe in frame, at a camera latitude from which
one turn can show every place: distribution_pose) one "place" event per place at the
first frame the place faces the camera, where unlabelled places are dots the band does
not apply to; a "place" event carries x/y of its frame and ``track``, the pixel in
every frame from there to the end of the take (null while hidden or, for a labelled
place, outside PLACES_BAND). Place ids are case-file place ids and a label is the
case-file place's name (plan C binds both to the verified case file before a take): the
renderer's GlobeShot pins and their show cues use them. The unlabelled places of a
distribution are its dots: plan C resolves the script's `site_ids` from the repo-root
public/data/sites export into {id: <site id>, lat, lng} (owner decision 15), so their ids
are site ids and never cue targets. A Mapbox take's optional "country" is the country the
take highlights: plan C binds it to the site export's country of its place, and the
recorder refuses a name the site's country table does not know (studio-mapbox.ts
checkCountry), so the recorder exits 1 and the take is a CaptureError.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pipeline.historical_boundaries.empire_metadata import EMPIRE_METADATA
from pipeline.studio.capture.encode import frame_size, sequence_length, sequence_to_mp4
from pipeline.studio.capture.gpu import gpu_event, require_nvidia
from pipeline.studio.capture.manifest import (
    CREDIT_MAPBOX_STREETS,
    CaptureError,
    as_coordinates,
    as_number,
    build_manifest,
    event,
    media_path,
    require_kind,
    tool_failure,
)
from pipeline.studio.capture.projection import (
    GLOBE_MAX_DISTANCE,
    GLOBE_MIN_DISTANCE,
    PLACES_BAND,
    fit_globe_distance,
    globe_to_pixel,
)
from pipeline.studio.capture.vite import (
    FRONTEND_DIR,
    PRODUCTION_URL,
    display_awake,
    kill_tree,
    require_mapbox_token,
    require_tool,
)

FPS = 60
WIDTH, HEIGHT = 1920, 1080
MAX_TAKE_S = 30.0
# How long the recorder may run: its start plus a time per frame. A Mapbox fly-in waits for
# its tiles on every frame: 5 s (300 frames) took 17 min on 2026-09-26, ~3.4 s a frame, so
# RECORD_FRAME_S leaves ~1.8x of that (record_timeout_s).
RECORD_START_S = 10 * 60
RECORD_FRAME_S = 6.0
# How often the take looks at the running recorder (its renderer, its exit, its timeout).
RECORDER_POLL_S = 1.0
RECORDER_SCENES = {
    "flyto": "studio-globe-flyto",
    "places": "studio-globe-places",
    "distribution": "studio-globe-places",
    "mapbox_flyin": "studio-mapbox-flyin",
    "mapbox_orbit": "studio-mapbox-orbit",
}
_BASE_KEYS = {"id", "kind", "scene", "duration_s"}
SPEC_KEYS = {
    "flyto": frozenset(
        _BASE_KEYS | {"lat", "lng", "distance", "empire", "rotate_s", "zoom_s", "place"}
    ),
    "places": frozenset(
        _BASE_KEYS
        | {"places", "lead_s", "interval_s", "sweep_lng_deg", "cam_lat", "cam_lng_from", "distance"}
    ),
    "distribution": frozenset(_BASE_KEYS | {"places"}),
    "mapbox_flyin": frozenset(_BASE_KEYS | {"name", "lat", "lng", "country", "orbit_zoom"}),
    "mapbox_orbit": frozenset(
        _BASE_KEYS
        | {"name", "lat", "lng", "country", "zoom", "pitch", "bearing_from", "bearing_to"}
    ),
}
SWEEP_KEYS = frozenset({"cam_lat", "cam_lng_from", "distance"})
MAX_PLACES = 12
MAX_DISTRIBUTION_PLACES = 500
# A world distribution: the whole globe in frame, one full turn over the take.
DISTRIBUTION_DISTANCE = GLOBE_MAX_DISTANCE
DISTRIBUTION_SWEEP_DEG = 360.0
DISTRIBUTION_MAX_LAT = 45
# A dot faces the camera of the turn when it lies within the horizon, acos(1 / distance)
# from the point under the camera (65.8 degrees at 2.44), less this margin at the limb.
DISTRIBUTION_HORIZON_MARGIN_DEG = 5.0
DISTRIBUTION_DOT_REACH_DEG = (
    math.degrees(math.acos(1 / DISTRIBUTION_DISTANCE)) - DISTRIBUTION_HORIZON_MARGIN_DEG
)
# Camera longitudes of one full turn relative to a place, in whole degrees, nearest first.
TURN_DELTAS_DEG = sorted(range(-180, 180), key=abs)
# Mirrors of ancient-nerds-map/video/scenes/studio-mapbox.ts (the path timing the events describe).
FLYIN_ROTATE_S = 1.2
FLYIN_ZOOM_S = 2.4
# Our vector globe carries no third-party map data; the Mapbox takes use satellite-streets.
CREDITS = {
    "flyto": [],
    "places": [],
    "distribution": [],
    "mapbox_flyin": [CREDIT_MAPBOX_STREETS],
    "mapbox_orbit": [CREDIT_MAPBOX_STREETS],
}


def _num(spec: dict[str, Any], key: str, lo: float, hi: float) -> float:
    if key not in spec:
        raise CaptureError(f"{spec.get('id')}: missing {key!r}")
    value = as_number(spec[key], f"{spec.get('id')}: {key}")
    if not lo <= value <= hi:
        raise CaptureError(f"{spec.get('id')}: {key}={value} outside {lo}..{hi}")
    return value


def _coords(spec: dict[str, Any], where: str) -> tuple[float, float]:
    for key in ("lat", "lng"):
        if key not in spec:
            raise CaptureError(f"{where}: missing {key!r}")
    return as_coordinates(spec, where, sep=": ")


def _label(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CaptureError(f"{where}: needs a non-empty label")
    return value


def _places(spec: dict[str, Any], most: int, label_required: bool) -> list[dict[str, Any]]:
    """The spec's places, each {id, lat, lng} plus its label (required, or optional)."""
    cid = spec.get("id")
    places = spec.get("places")
    if not isinstance(places, list) or not 1 <= len(places) <= most:
        raise CaptureError(f"{cid}: places must list 1-{most} places")
    out = []
    for i, place in enumerate(places):
        keys = set(place) if isinstance(place, dict) else set()
        allowed = {"id", "label", "lat", "lng"}
        needed = allowed if label_required else allowed - {"label"}
        if not isinstance(place, dict) or not needed <= keys <= allowed:
            shape = "{id, label, lat, lng}" if label_required else "{id, lat, lng, label?}"
            raise CaptureError(f"{cid}: places[{i}] must be {shape}")
        if not isinstance(place["id"], str) or not place["id"]:
            raise CaptureError(f"{cid}: places[{i}] needs a place id")
        lat, lng = _coords(place, f"{cid}: place {place['id']}")
        clean = {"id": place["id"], "lat": lat, "lng": lng}
        if "label" in place:
            clean["label"] = _label(place["label"], f"{cid}: places[{i}]")
        out.append(clean)
    if len({p["id"] for p in out}) != len(out):
        raise CaptureError(f"{cid}: place ids must be unique")
    return out


def _faces_camera(place: dict[str, Any], cam_lat: float) -> bool:
    """Whether one turn of the distribution camera at `cam_lat` can show the place.

    A dot must lie within the horizon less a margin; a labelled place must be drawn inside
    PLACES_BAND at some camera longitude of the turn, by projection.py's globe camera (the
    model fit_globe_distance uses; the page's own pixels decide later, in take_events).
    """
    if "label" not in place:
        return abs(place["lat"] - cam_lat) <= DISTRIBUTION_DOT_REACH_DEG
    for delta in TURN_DELTAS_DEG:
        px = globe_to_pixel(
            place["lat"],
            place["lng"],
            cam_lat=cam_lat,
            cam_lng=place["lng"] + delta,
            distance=DISTRIBUTION_DISTANCE,
            width=WIDTH,
            height=HEIGHT,
        )
        if px is not None and _in_band(px):
            return True
    return False


def distribution_pose(cid: str, places: list[dict[str, Any]]) -> tuple[float, float]:
    """(cam_lat, cam_lng_from) of a world distribution.

    The camera starts opposite the places' mean longitude, so the densest region turns
    into view in the middle of the take. Its latitude is the midpoint of the places'
    lowest and highest latitude, or else the whole degree nearest it, within +-45, at
    which one turn can show every place (_faces_camera); the mean latitude would follow
    the dots and lose an outlying place. Raises before any side effect when no latitude
    shows them all.
    """
    lats = [p["lat"] for p in places]
    mid = max(-DISTRIBUTION_MAX_LAT, min(DISTRIBUTION_MAX_LAT, (min(lats) + max(lats)) / 2))
    whole = range(-DISTRIBUTION_MAX_LAT, DISTRIBUTION_MAX_LAT + 1)
    candidates = sorted([mid, *(float(c) for c in whole)], key=lambda c: abs(c - mid))
    cam_lat = next((c for c in candidates if all(_faces_camera(p, c) for p in places)), None)
    if cam_lat is None:
        ids = [p["id"] for p in places if not _faces_camera(p, mid)]
        raise CaptureError(
            f"{cid}: places {ids} cannot face the camera in one turn of the globe; "
            "split the distribution"
        )
    x = sum(math.cos(math.radians(p["lng"])) for p in places)
    y = sum(math.sin(math.radians(p["lng"])) for p in places)
    start = math.degrees(math.atan2(y, x)) - 180.0
    return cam_lat, start + 360.0 if start < -180.0 else start


def scene_input(spec: dict[str, Any], work: Path) -> dict[str, Any]:
    """Validate a globe spec and build the recorder scene input (studio-*.ts) for `work`."""
    cid = spec.get("id")
    scene = spec.get("scene")
    if scene not in RECORDER_SCENES:
        raise CaptureError(f"{cid}: scene must be one of {sorted(RECORDER_SCENES)}, got {scene!r}")
    unknown = set(spec) - SPEC_KEYS[scene]
    if unknown:
        raise CaptureError(f"{cid}: unknown keys {sorted(unknown)} for scene {scene}")
    duration = _num(spec, "duration_s", 1.0, MAX_TAKE_S)
    base: dict[str, Any] = {
        "scene": "places" if scene == "distribution" else scene,
        "duration_s": duration,
        "frames_dir": (work / "frames").as_posix(),
        "renderer_path": (work / "renderer.json").as_posix(),
    }
    points_path = (work / "points.json").as_posix()
    if scene == "flyto":
        lat, lng = _coords(spec, str(cid))
        rotate_s = _num(spec, "rotate_s", 0.5, 5.0)
        zoom_s = _num(spec, "zoom_s", 0.5, 5.0)
        if duration < rotate_s + zoom_s + 0.5:
            raise CaptureError(f"{cid}: duration_s {duration} < rotate_s + zoom_s + 0.5 s hold")
        empire = spec.get("empire")
        if empire is not None and empire not in EMPIRE_METADATA:
            raise CaptureError(
                f"{cid}: empire must be null or an empire id of "
                f"pipeline/historical_boundaries/empire_metadata.py, got {empire!r}"
            )
        place = spec.get("place")
        if place is not None and (not isinstance(place, dict) or set(place) != {"id", "label"}):
            raise CaptureError(f"{cid}: place must be {{'id': <place id>, 'label': ...}}")
        if place is not None and (not isinstance(place["id"], str) or not place["id"]):
            raise CaptureError(f"{cid}: place needs a place id, got {place['id']!r}")
        out = {
            **base,
            "lat": lat,
            "lng": lng,
            "distance": _num(spec, "distance", GLOBE_MIN_DISTANCE, GLOBE_MAX_DISTANCE),
            "empire": empire,
            "rotate_s": rotate_s,
            "zoom_s": zoom_s,
        }
        if place is not None:
            _label(place["label"], f"{cid}: place")
            out["places"] = [{"id": place["id"], "lat": lat, "lng": lng}]
            out["points_path"] = points_path
        return out
    if scene == "places":
        places = _places(spec, MAX_PLACES, label_required=True)
        lead = _num(spec, "lead_s", 0.0, duration)
        interval = _num(spec, "interval_s", 0.1, 5.0)
        if lead + (len(places) - 1) * interval > duration:
            raise CaptureError(
                f"{cid}: place {places[-1]['id']} would light up after the take ends "
                f"(lead_s + {len(places) - 1} * interval_s > duration_s)"
            )
        sweep = _num(spec, "sweep_lng_deg", -360.0, 360.0) if "sweep_lng_deg" in spec else 0.0
        if sweep == 0:
            if SWEEP_KEYS & set(spec):
                raise CaptureError(
                    f"{cid}: {sorted(SWEEP_KEYS & set(spec))} belong to a sweep "
                    "(sweep_lng_deg != 0); a fixed pose is fitted to the places"
                )
            try:
                cam_lat, cam_lng, distance = fit_globe_distance(
                    [(p["lat"], p["lng"]) for p in places], width=WIDTH, height=HEIGHT
                )
            except ValueError as err:
                raise CaptureError(f"{cid}: {err}") from err
        else:
            cam_lat = _num(spec, "cam_lat", -60.0, 60.0)
            cam_lng = _num(spec, "cam_lng_from", -180.0, 180.0)
            distance = _num(spec, "distance", GLOBE_MIN_DISTANCE, GLOBE_MAX_DISTANCE)
        return {
            **base,
            "cam_lat": cam_lat,
            "cam_lng": cam_lng,
            "distance": distance,
            "sweep_lng_deg": sweep,
            "places": [{"id": p["id"], "lat": p["lat"], "lng": p["lng"]} for p in places],
            "points_path": points_path,
        }
    if scene == "distribution":
        places = _places(spec, MAX_DISTRIBUTION_PLACES, label_required=False)
        cam_lat, cam_lng = distribution_pose(str(cid), places)
        return {
            **base,
            "cam_lat": cam_lat,
            "cam_lng": cam_lng,
            "distance": DISTRIBUTION_DISTANCE,
            "sweep_lng_deg": DISTRIBUTION_SWEEP_DEG,
            "places": [{"id": p["id"], "lat": p["lat"], "lng": p["lng"]} for p in places],
            "points_path": points_path,
        }
    lat, lng = _coords(spec, str(cid))
    out = {**base, "name": _label(spec.get("name"), str(cid)), "lat": lat, "lng": lng}
    country = spec.get("country")
    if country is not None:
        if not isinstance(country, str) or not country.strip():
            raise CaptureError(f"{cid}: country must be a country name, got {country!r}")
        out["country"] = country
    if scene == "mapbox_flyin":
        if duration < FLYIN_ROTATE_S + FLYIN_ZOOM_S + 1:
            raise CaptureError(
                f"{cid}: a fly-in needs at least {FLYIN_ROTATE_S + FLYIN_ZOOM_S + 1} s"
            )
        out["orbit_zoom"] = _num(spec, "orbit_zoom", 10.0, 18.0)
    else:
        out["zoom"] = _num(spec, "zoom", 10.0, 18.5)
        out["pitch"] = _num(spec, "pitch", 0.0, 80.0)
        out["bearing_from"] = _num(spec, "bearing_from", -360.0, 360.0)
        out["bearing_to"] = _num(spec, "bearing_to", -360.0, 360.0)
    return out


def expected_frames(duration_s: float) -> int:
    """Frames of a take, as studio-frames.ts counts them: JS Math.round(seconds * fps).

    Python's round() rounds half to even (5.075 s * 60 = 304.5 -> 304) where Math.round
    rounds half up (305), so the count is floor(x + 0.5).
    """
    return math.floor(duration_s * FPS + 0.5)


def first_frame(t: float) -> int:
    """The first frame at or after `t` seconds of the take."""
    return math.ceil(t * FPS - 1e-9)


def _in_band(point: Sequence[float]) -> bool:
    fx, fy = point[0] / WIDTH, point[1] / HEIGHT
    return PLACES_BAND[0] <= fx <= PLACES_BAND[2] and PLACES_BAND[1] <= fy <= PLACES_BAND[3]


def _track(spec: dict[str, Any], points: dict[str, Any] | None, pid: str, frames: int) -> list:
    if points is None:
        raise CaptureError(f"{spec['id']}: the scene wrote no points")
    track = points.get(pid)
    held = len(track) if isinstance(track, list) else "no"
    if not isinstance(track, list) or len(track) != frames:
        raise CaptureError(
            f"{spec['id']}: points.json holds {held} points for place {pid}, the take has {frames} frames"
        )
    return track


def _place_event(
    cid: str, place: dict[str, Any], track: list, start: int, labelled: bool
) -> dict[str, Any]:
    """The place's event at the first frame from `start` on where the page draws it (inside
    PLACES_BAND when it carries a label), with its track from there to the end of the take."""
    pid = place["id"]
    if start >= len(track):
        raise CaptureError(f"{cid}: place {pid} would light up after the take ends")
    visible = [f for f in range(start, len(track)) if track[f] is not None]
    if not visible:
        raise CaptureError(
            f"{cid}: place {pid} is not visible in the take after {start / FPS:.2f} s "
            "(behind the globe or off screen)"
        )
    if labelled:
        in_band = [f for f in visible if _in_band(track[f])]
        if not in_band:
            fx, fy = track[visible[0]][0] / WIDTH, track[visible[0]][1] / HEIGHT
            raise CaptureError(
                f"{cid}: the page draws place {pid} at ({fx:.2f}, {fy:.2f}) of the frame, "
                f"outside the label band {PLACES_BAND}"
            )
        frame = in_band[0]
        rest = [p if p is not None and _in_band(p) else None for p in track[frame:]]
        extra = {"label": place["label"]}
    else:
        frame = visible[0]
        rest = track[frame:]
        extra = {}
    x, y = track[frame]
    return event(frame / FPS, "place", target=pid, x=x, y=y, track=rest, **extra)


def take_events(
    spec: dict[str, Any], inp: dict[str, Any], points: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """Manifest events of a take in time order; pixels are media pixels of the 1920x1080 capture."""
    scene = spec["scene"]
    cid = spec["id"]
    frames = expected_frames(inp["duration_s"])
    if scene == "flyto":
        arrive = inp["rotate_s"] + inp["zoom_s"]
        events = [
            event(0, "rotate"),
            event(inp["rotate_s"], "zoom"),
            event(arrive, "arrive", x=WIDTH / 2, y=HEIGHT / 2),
        ]
        place = spec.get("place")
        if place is None:
            return events
        track = _track(spec, points, place["id"], frames)
        return [*events, _place_event(cid, place, track, first_frame(arrive), labelled=True)]
    if scene == "places":
        # scene_input validated lead_s and interval_s
        lead, interval = float(spec["lead_s"]), float(spec["interval_s"])
        found = [
            _place_event(
                cid,
                place,
                _track(spec, points, place["id"], frames),
                first_frame(lead + i * interval),
                labelled=True,
            )
            for i, place in enumerate(spec["places"])
        ]
        return sorted(found, key=lambda e: e["t"])
    if scene == "distribution":
        found = [
            _place_event(
                cid, place, _track(spec, points, place["id"], frames), 0, labelled="label" in place
            )
            for place in spec["places"]
        ]
        return sorted(found, key=lambda e: e["t"])
    if scene == "mapbox_flyin":
        return [
            event(0, "space"),
            event(FLYIN_ROTATE_S, "zoom"),
            event(FLYIN_ROTATE_S + FLYIN_ZOOM_S, "orbit"),
        ]
    return [event(0, "orbit")]


def recorder_command(npm: str, recorder_scene: str, input_path: Path, out_dir: Path) -> list[str]:
    return [
        npm,
        "run",
        "video:record",
        "--",
        recorder_scene,
        "--fps",
        str(FPS),
        "--input",
        input_path.as_posix(),
        "--out",
        out_dir.as_posix(),
    ]


def start_recorder(cmd: list[str], log: Any) -> subprocess.Popen[bytes]:
    """Start the recorder in the frontend with the production API and its output in `log`."""
    env = {**os.environ, "VITE_DEV_API_TARGET": PRODUCTION_URL}
    return subprocess.Popen(cmd, cwd=FRONTEND_DIR, env=env, stdout=log, stderr=subprocess.STDOUT)


def record_timeout_s(frames: int) -> float:
    """How long the recorder may take for a take of `frames` frames (RECORD_FRAME_S)."""
    return RECORD_START_S + frames * RECORD_FRAME_S


def scene_renderer(cid: str, work: Path) -> str:
    """The WebGL renderer the scene wrote to renderer.json; anything but the NVIDIA fails."""
    path = work / "renderer.json"
    if not path.is_file():
        raise CaptureError(f"{cid}: the recorder scene wrote no {path.name}")
    renderer = json.loads(path.read_text(encoding="utf-8"))["renderer"]
    return require_nvidia(renderer, f"{cid}: recorder")


def wait_recorder(
    proc: subprocess.Popen[bytes], cid: str, work: Path, timeout_s: float, log_path: Path
) -> None:
    """Wait until the recorder exits, stopping it on the first failure.

    Every scene writes renderer.json before it grabs its first frame (studio-frames.ts
    writeRenderer), so once f000000.jpg exists the renderer is proven: a take drawn on
    another GPU stops then, not after its whole length. A recorder still running after
    `timeout_s` is stopped too."""
    deadline = time.monotonic() + timeout_s
    proven = False
    while proc.poll() is None:
        if not proven and (work / "frames" / "f000000.jpg").exists():
            try:
                scene_renderer(cid, work)
            except CaptureError:
                kill_tree(proc)
                raise
            proven = True
        if time.monotonic() > deadline:
            kill_tree(proc)
            raise CaptureError(f"{cid}: recorder did not finish in {timeout_s:g} s; see {log_path}")
        time.sleep(RECORDER_POLL_S)


def record_globe(episode_dir: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """Record one globe or Mapbox take into captures/<id>.mp4 and return its manifest."""
    cid = require_kind(spec, "globe")
    work = media_path(episode_dir, cid, ".rec")
    frames_dir = work / "frames"
    inp = scene_input(spec, work)
    npm = require_tool("npm")
    if spec["scene"].startswith("mapbox_"):
        require_mapbox_token()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    input_path = work / "input.json"
    input_path.write_text(json.dumps(inp, indent=2), encoding="utf-8")
    log_path = work / "recorder.log"
    frames = expected_frames(inp["duration_s"])
    with display_awake(), log_path.open("wb") as log:
        proc = start_recorder(
            recorder_command(npm, RECORDER_SCENES[spec["scene"]], input_path, work), log
        )
        wait_recorder(proc, cid, work, record_timeout_s(frames), log_path)
    if proc.returncode != 0:
        raise CaptureError(f"{cid}: recorder failed (exit {proc.returncode}); see {log_path}")
    renderer = scene_renderer(cid, work)
    count = sequence_length(frames_dir)
    if count != frames:
        raise CaptureError(f"{cid}: the take has {count} frames, expected {frames}")
    size = frame_size(frames_dir)
    if size != (WIDTH, HEIGHT):
        raise CaptureError(f"{cid}: frames are {size}, expected {(WIDTH, HEIGHT)}")
    points = (
        json.loads((work / "points.json").read_text(encoding="utf-8"))
        if "points_path" in inp
        else None
    )
    events = [gpu_event(renderer), *take_events(spec, inp, points)]
    out = media_path(episode_dir, cid, ".mp4")
    try:
        sequence_to_mp4(frames_dir, FPS, out)
    except subprocess.CalledProcessError as exc:
        raise tool_failure(cid, exc) from exc
    shutil.rmtree(work)
    return build_manifest(
        episode_dir=episode_dir,
        cid=cid,
        kind="globe",
        path=out,
        fps=FPS,
        duration_s=count / FPS,
        width=WIDTH,
        height=HEIGHT,
        events=events,
        credits=CREDITS[spec["scene"]],
    )
