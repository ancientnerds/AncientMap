"""Capture manifests: the one shape every capture function returns (plan C contract C7).

    {"id", "kind", "path", "fps", "duration_s", "width", "height",
     "events": [{"t", "name", ...}], "credits": [...]}

``kind`` is the spec's kind (platform | globe | source | mapbox_topdown). Capture ids and
kinds come from pipeline.studio.config (CAPTURE_ID_RE, CAPTURE_KINDS: plan C's script check
uses the same two, so the patterns exist once). ``path`` is
POSIX, relative to the episode directory and directly under ``captures/`` (the render
step links it into the Remotion public dir under the same relative path). ``fps`` and
``duration_s`` are both numbers for a clip and both null for a still. ``events`` are in
seconds of the captured media; an event may carry ``x``/``y`` (media pixels), ``box``
([x, y, w, h] media pixels), ``target`` (a case-file id), ``label``, ``url``, ``title``,
``lat``/``lng`` and ``track`` (globe place events: the place's [x, y] in every frame from
the event to the end of the take, null while hidden). ``pipeline.studio.captures`` stores
the manifest as captures/<id>.json.

Every capture failure is a CaptureError (a StudioError: plan C's CLI exits 2 with the
message). Spec values are read through as_number/as_int, so a missing or mistyped value
is a CaptureError too, and tool_failure turns a failed ffmpeg/ffprobe run into one.
"""

from __future__ import annotations

import math
import subprocess
from pathlib import Path
from typing import Any

from pipeline.studio.config import CAPTURE_ID_RE, CAPTURE_KINDS
from pipeline.studio.errors import StudioError
from pipeline.utils.geo import is_valid_coordinates
from pipeline.video.shorts_render import MAPBOX_CREDIT

CAPTURES_DIR = "captures"
EVENT_EXTRAS = frozenset(
    {"x", "y", "box", "target", "label", "url", "title", "lat", "lng", "track"}
)

# In-frame credits the renderer draws and the description lists.
CREDIT_MAPBOX_SATELLITE = MAPBOX_CREDIT  # satellite-v9: imagery only
CREDIT_MAPBOX_STREETS = "© Mapbox © OpenStreetMap © Maxar"  # satellite-streets-v12, the site's map


class CaptureError(StudioError):
    """A capture could not be made or its result is invalid. Never swallowed."""


def as_number(value: Any, where: str) -> float:
    """A spec value as a float; a string, a bool, None or a non-finite number is a CaptureError."""
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise CaptureError(f"{where} must be a number, got {value!r}")
    return float(value)


def as_coordinates(point: dict[str, Any], where: str, sep: str = ".") -> tuple[float, float]:
    """(lat, lng) of a spec point's "lat" and "lng": numbers that the shared
    pipeline.utils.geo.is_valid_coordinates accepts. `where` names the point; `sep` joins it
    to a key in the message ("actions[3].at" + "." + "lat", or "g1" + ": " + "lat")."""
    lat = as_number(point["lat"], f"{where}{sep}lat")
    lng = as_number(point["lng"], f"{where}{sep}lng")
    if not is_valid_coordinates(lat, lng):
        raise CaptureError(f"{where}: ({lat}, {lng}) is not a coordinate")
    return lat, lng


def as_int(value: Any, where: str) -> int:
    """A spec value that must be an integer (a JSON int, not a float or a bool)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise CaptureError(f"{where} must be an integer, got {value!r}")
    return value


def tool_failure(cid: str, exc: subprocess.CalledProcessError) -> CaptureError:
    """ffmpeg or ffprobe failed: the tool, its exit code and the end of its stderr.

    pipeline.video.media runs them with capture_output, so without this the reason (for
    example "No NVENC capable devices found") would be lost behind a bare exit code.
    """
    tool = Path(str(exc.cmd[0])).name
    return CaptureError(
        f"{cid}: {tool} failed (exit {exc.returncode}): {(exc.stderr or '').strip()[-2000:]}"
    )


def capture_id(spec: dict[str, Any]) -> str:
    """The spec's id; it names the media file, so it must be a safe slug."""
    cid = spec.get("id")
    if not isinstance(cid, str) or not CAPTURE_ID_RE.fullmatch(cid):
        raise CaptureError(f"capture id {cid!r} must match {CAPTURE_ID_RE.pattern}")
    return cid


def require_kind(spec: dict[str, Any], kind: str) -> str:
    """The spec's id after checking that the spec is of `kind`."""
    cid = capture_id(spec)
    if spec.get("kind") != kind:
        raise CaptureError(
            f"{cid}: this capture function takes kind {kind!r}, not {spec.get('kind')!r}"
        )
    return cid


def media_path(episode_dir: Path, cid: str, suffix: str) -> Path:
    return episode_dir / CAPTURES_DIR / f"{cid}{suffix}"


def event(t: float, name: str, **extra: Any) -> dict[str, Any]:
    """One manifest event, as the renderer's EVENT schema accepts it (video/src/blocks/
    schemas.ts): t >= 0; name, target, label and url non-empty strings; title a string
    (a page may have none); lat and lng in range; numbers where the schema has numbers.
    Unknown extra keys are a programming error."""
    if not isinstance(name, str) or not name:
        raise CaptureError(f"event name must be a non-empty string, got {name!r}")
    where = f"event {name!r}"
    unknown = set(extra) - EVENT_EXTRAS
    if unknown:
        raise CaptureError(f"{where} has unknown fields {sorted(unknown)}")
    seconds = as_number(t, f"{where}: t")
    if seconds < 0:
        raise CaptureError(f"{where}: t {seconds} is before the start of the capture")
    out: dict[str, Any] = {"t": round(seconds, 3), "name": name}
    for key in ("x", "y"):
        if key in extra:
            out[key] = round(as_number(extra[key], f"{where}: {key}"), 1)
    if "box" in extra:
        box = [round(as_number(v, f"{where}: box"), 1) for v in extra["box"]]
        if len(box) != 4 or box[2] <= 0 or box[3] <= 0:
            raise CaptureError(f"{where}: box {extra['box']!r} is not [x, y, w, h]")
        out["box"] = box
    for key in ("target", "label", "url"):
        if key in extra:
            if not isinstance(extra[key], str) or not extra[key]:
                raise CaptureError(f"{where}: {key} must be a non-empty string, got {extra[key]!r}")
            out[key] = extra[key]
    if "title" in extra:
        if not isinstance(extra["title"], str):
            raise CaptureError(f"{where}: title must be a string, got {extra['title']!r}")
        out["title"] = extra["title"]
    for key, limit in (("lat", 90.0), ("lng", 180.0)):
        if key in extra:
            value = as_number(extra[key], f"{where}: {key}")
            if not -limit <= value <= limit:
                raise CaptureError(f"{where}: {key} {value} outside {-limit:g}..{limit:g}")
            out[key] = round(value, 6)
    if "track" in extra:
        track: list[list[float] | None] = []
        for point in extra["track"]:
            if point is not None and len(point) != 2:
                raise CaptureError(f"{where}: track point {point!r} is not [x, y]")
            track.append(
                None
                if point is None
                else [round(as_number(v, f"{where}: track"), 1) for v in point]
            )
        out["track"] = track
    return out


def build_manifest(
    *,
    episode_dir: Path,
    cid: str,
    kind: str,
    path: Path,
    fps: float | None,
    duration_s: float | None,
    width: int,
    height: int,
    events: list[dict[str, Any]],
    credits: list[str],
) -> dict[str, Any]:
    """Validate and assemble a manifest; raises CaptureError on any defect.

    Events are compared with the duration as the manifest keeps both, in whole
    milliseconds: an event on the last frame of a clip is no event after its end."""
    capture_id({"id": cid})
    if kind not in CAPTURE_KINDS:
        raise CaptureError(f"unknown capture kind {kind!r}")
    captures = (episode_dir / CAPTURES_DIR).resolve()
    resolved = path.resolve()
    if resolved.parent != captures:
        raise CaptureError(f"{path} is not directly inside {captures}")
    if resolved.stem != cid:
        raise CaptureError(f"{path.name} is not named after capture {cid!r} ({cid}.<ext>)")
    if not resolved.is_file():
        raise CaptureError(f"{path} does not exist")
    if width <= 0 or height <= 0:
        raise CaptureError(f"{path}: bad size {width}x{height}")
    if (fps is None) != (duration_s is None):
        raise CaptureError(f"{path}: a clip has fps and duration_s, a still neither")
    if fps is not None and duration_s is not None:
        if fps <= 0 or duration_s <= 0:
            raise CaptureError(f"{path}: fps {fps} and duration {duration_s} must be positive")
        if width % 2 or height % 2:
            raise CaptureError(f"{path}: video size {width}x{height} must be even")
    end = round(duration_s, 3) if duration_s is not None else 0.0
    last = -math.inf
    for ev in events:
        if ev["t"] < last:
            raise CaptureError(f"{path}: events out of order at {ev}")
        if not 0 <= ev["t"] <= end:
            raise CaptureError(f"{path}: event {ev} outside 0..{end} s")
        last = ev["t"]
    if any(not isinstance(c, str) or not c.strip() for c in credits):
        raise CaptureError(f"{path}: empty credit in {credits!r}")
    return {
        "id": cid,
        "kind": kind,
        "path": resolved.relative_to(episode_dir.resolve()).as_posix(),
        "fps": fps,
        "duration_s": None if duration_s is None else round(duration_s, 3),
        "width": width,
        "height": height,
        "events": events,
        "credits": credits,
    }
