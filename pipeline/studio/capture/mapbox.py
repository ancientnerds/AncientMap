"""Exact top-down satellite frames from the Mapbox Static Images API with pins at their
projected pixels (spec 2026-09-26 section 4.5).

The image is requested at @2x (2 * width x 2 * height pixels, 16:9 like the frame the
renderer fills with it); pins are placed with projection.mercator_to_pixel for the same
centre, zoom and bearing, rounded as the URL carries them, so they sit on the
object whatever the renderer's camera does (the owner verified such pins to within
metres, 2026-09-26). The token is the frontend's public VITE_MAPBOX_ACCESS_TOKEN (the
Static API answers without a Referer, checked 2026-09-26). Pin ids are case-file place
ids and a pin's label is the case-file place's name (plan C binds both to the verified
case file); each pin event also carries its label and coordinates, from which the
renderer computes distance lines. Unknown spec keys, missing or non-numeric values and a refused
or failed request are CaptureErrors; no message carries the token.

Spec::

    {"id": "td1", "kind": "mapbox_topdown", "center": {"lat": 34.0022, "lng": 36.2018},
     "zoom": 16.1, "bearing": 0, "style": "satellite-v9", "width": 1280, "height": 720,
     "pins": [{"id": "p1", "label": "Quarry", "lat": 33.99917, "lng": 36.20028}, ...]}
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import httpx

from pipeline.studio.capture.manifest import (
    CREDIT_MAPBOX_SATELLITE,
    CREDIT_MAPBOX_STREETS,
    CaptureError,
    as_coordinates,
    as_int,
    as_number,
    build_manifest,
    event,
    media_path,
    require_kind,
)
from pipeline.studio.capture.projection import MERCATOR_MAX_LAT, mercator_to_pixel
from pipeline.studio.capture.vite import require_mapbox_token

STATIC_BASE = "https://api.mapbox.com/styles/v1/mapbox"
STYLES = {"satellite-v9": CREDIT_MAPBOX_SATELLITE, "satellite-streets-v12": CREDIT_MAPBOX_STREETS}
MAX_SIDE = 1280
RETINA = 2
# The renderer's frame (1920x1080) the image is cover-fitted into.
FRAME_ASPECT = (16, 9)
# Where a pin may sit, as fractions of the frame: the renderer cover-fits the frame to
# 1920x1080, pushes in 8 % and puts each pin's label above or below it, so a pin outside
# this band sends its label out of the title-safe area or under the YouTube controls
# (the layout lint caught exactly that on the first real frame, 2026-09-26).
PIN_BAND_X = (0.10, 0.90)
PIN_BAND_Y = (0.15, 0.80)
SUFFIXES = {"image/jpeg": ".jpg", "image/png": ".png"}
SPEC_KEYS = frozenset(
    {"id", "kind", "center", "zoom", "bearing", "style", "width", "height", "pins"}
)


def _mercator(cid: Any, what: str, lat: float) -> None:
    """Refuse a latitude past the square world the Static API draws (projection.py)."""
    if abs(lat) > MERCATOR_MAX_LAT:
        raise CaptureError(
            f"{cid}: {what} latitude {lat} outside the Web Mercator range +-{MERCATOR_MAX_LAT}"
        )


def _view(spec: dict[str, Any]) -> dict[str, Any]:
    """The checked view, its centre, zoom and bearing rounded as the URL carries them
    (static_url; Mapbox rounds a fractional zoom to 2 places itself), so pin_events
    projects the pins for exactly the image the API draws."""
    cid = spec.get("id")
    unknown = set(spec) - SPEC_KEYS
    if unknown:
        raise CaptureError(f"{cid}: unknown keys {sorted(unknown)}")
    center = spec.get("center")
    if not isinstance(center, dict) or set(center) != {"lat", "lng"}:
        raise CaptureError(f"{cid}: center must be {{'lat': .., 'lng': ..}}, got {center!r}")
    lat, lng = as_coordinates(center, f"{cid}: center")
    _mercator(cid, "center", lat)
    zoom = as_number(spec.get("zoom"), f"{cid}: zoom")
    bearing = as_number(spec.get("bearing", 0), f"{cid}: bearing")
    width = as_int(spec.get("width"), f"{cid}: width")
    height = as_int(spec.get("height"), f"{cid}: height")
    style = spec.get("style", "satellite-v9")
    if not 0 <= zoom <= 22:
        raise CaptureError(f"{cid}: zoom {zoom} outside 0..22")
    if not 0 <= bearing < 360:
        raise CaptureError(f"{cid}: bearing {bearing} outside 0..360")
    if not (1 <= width <= MAX_SIDE and 1 <= height <= MAX_SIDE):
        raise CaptureError(f"{cid}: {width}x{height} exceeds the Static API limit of {MAX_SIDE} px")
    if width * FRAME_ASPECT[1] != height * FRAME_ASPECT[0]:
        raise CaptureError(
            f"{cid}: {width}x{height} is not 16:9: the renderer fills its 16:9 frame with the "
            "image (cover), so another aspect is cropped and the pin band no longer holds"
        )
    if style not in STYLES:
        raise CaptureError(f"{cid}: style {style!r} not in {sorted(STYLES)}")
    return {
        "lat": round(lat, 6),
        "lng": round(lng, 6),
        "zoom": round(zoom, 2),
        "bearing": round(bearing, 1) % 360,
        "width": width,
        "height": height,
        "style": style,
    }


def static_url(spec: dict[str, Any], token: str) -> str:
    v = _view(spec)
    return (
        f"{STATIC_BASE}/{v['style']}/static/{v['lng']:.6f},{v['lat']:.6f},{v['zoom']:.2f},{v['bearing']:.1f},0/"
        f"{v['width']}x{v['height']}@2x?attribution=false&logo=false&access_token={token}"
    )


def pin_events(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """One "pin" event per pin with its pixel in the @2x image; a pin off the image is an error."""
    v = _view(spec)
    pins = spec.get("pins")
    if not isinstance(pins, list) or not pins:
        raise CaptureError(f"{spec['id']}: a top-down frame needs at least one pin")
    ids = [pin.get("id") if isinstance(pin, dict) else None for pin in pins]
    twice = next((pid for pid in ids if ids.count(pid) > 1), None)
    if twice is not None:
        raise CaptureError(f"{spec['id']}: pin ids must be unique, {twice} is there twice")
    events = []
    for i, pin in enumerate(pins):
        if not isinstance(pin, dict) or set(pin) != {"id", "label", "lat", "lng"}:
            raise CaptureError(f"{spec['id']}: pins[{i}] must be {{id, label, lat, lng}}")
        lat, lng = as_coordinates(pin, f"{spec['id']}: pins[{i}]")
        _mercator(spec["id"], f"pins[{i}]", lat)
        x, y = mercator_to_pixel(
            lat,
            lng,
            center_lat=v["lat"],
            center_lng=v["lng"],
            zoom=v["zoom"],
            bearing=v["bearing"],
            width=v["width"],
            height=v["height"],
        )
        if not (0 <= x <= v["width"] and 0 <= y <= v["height"]):
            raise CaptureError(f"{spec['id']}: pin {pin['id']} falls outside the frame")
        fx, fy = x / v["width"], y / v["height"]
        if not (PIN_BAND_X[0] <= fx <= PIN_BAND_X[1] and PIN_BAND_Y[0] <= fy <= PIN_BAND_Y[1]):
            raise CaptureError(
                f"{spec['id']}: pin {pin['id']} sits at ({fx:.2f}, {fy:.2f}) of the frame, outside "
                f"the band x {PIN_BAND_X}, y {PIN_BAND_Y} where its label stays readable: "
                "move the centre or zoom out"
            )
        events.append(
            event(
                0,
                "pin",
                target=pin["id"],
                label=pin["label"],
                x=x * RETINA,
                y=y * RETINA,
                lat=lat,
                lng=lng,
            )
        )
    return events


def mapbox_topdown(episode_dir: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """Fetch one top-down frame into captures/<id>.jpg|.png and return its manifest (a still)."""
    from PIL import Image

    cid = require_kind(spec, "mapbox_topdown")
    token = require_mapbox_token()
    v = _view(spec)
    events = pin_events(spec)
    try:
        response = httpx.get(static_url(spec, token), timeout=30)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        # httpx names the URL in its message, and the URL carries the token.
        raise CaptureError(f"{cid}: Mapbox Static API: {str(exc).replace(token, '***')}") from exc
    content_type = response.headers.get("content-type", "").split(";")[0].strip()
    if content_type not in SUFFIXES:
        raise CaptureError(f"{cid}: Static API answered {content_type!r}, not an image")
    width, height = v["width"] * RETINA, v["height"] * RETINA
    with Image.open(io.BytesIO(response.content)) as img:
        if img.size != (width, height):
            raise CaptureError(f"{cid}: Static API image is {img.size}, expected {(width, height)}")
    out = media_path(episode_dir, cid, SUFFIXES[content_type])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(response.content)
    return build_manifest(
        episode_dir=episode_dir,
        cid=cid,
        kind="mapbox_topdown",
        path=out,
        fps=None,
        duration_s=None,
        width=width,
        height=height,
        events=events,
        credits=[STYLES[v["style"]]],
    )
