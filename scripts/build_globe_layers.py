#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Build the globe's coastline and country-border tiers.

The globe used to fetch `coast_hires.geojson` (25 MB, 15 decimals, no gzip)
twice and the Natural Earth border lines twice from GitHub before its first
frame. This script derives what the frontend loads instead, offline and
reproducibly:

  coast_start    / borders_start    - loaded before the globe is shown
  coast_detail   / borders_detail   - swapped in by the background queue

Each output is a compact GeoJSON FeatureCollection of MultiLineStrings named by
its content hash (`coast_start.<sha256[:8]>.json`), so a deploy never serves a
stale copy and the URL is stable while the content is. The manifest the bundle
imports, `ancient-nerds-map/src/data/globeLayers.generated.json`, maps layer and
tier to those URLs. Never edit either by hand; rerun this script.

Inputs are downloaded into a temporary directory at build time only, never at
runtime, and checked against pinned sha256 digests so every run on every machine
produces the same bytes:

  --coast    the repo's LFS file `public/data/layers/coast_hires.geojson`
             (default: the copy production serves; the worktree holds a pointer)
  --borders  Natural Earth 5.1.2 `ne_10m_admin_0_boundary_lines_land`

Run from the repo root:  python scripts/build_globe_layers.py
Idempotent: a second run leaves the working tree unchanged.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import tempfile
import urllib.request
from collections.abc import Iterable, Sequence
from pathlib import Path
from urllib.parse import urlparse

from shapely.geometry import LineString

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "public" / "data" / "layers" / "globe"
MANIFEST_PATH = ROOT / "ancient-nerds-map" / "src" / "data" / "globeLayers.generated.json"
URL_PREFIX = "/data/layers/globe/"

COAST_URL = "https://ancientnerds.com/data/layers/coast_hires.geojson"
# = the LFS oid of public/data/layers/coast_hires.geojson (25,035,507 bytes).
COAST_SHA256 = "4bd630fb4213c077c8eff254169e9df6c8d728a07978f5d9977eee057c13d7aa"
BORDERS_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/"
    "geojson/ne_10m_admin_0_boundary_lines_land.geojson"
)
BORDERS_SHA256 = "74d9c16229c095fde65943a9919e337682f044bcebccb120764f38edf3b70f4a"

DOWNLOAD_TIMEOUT_S = 120

# One tolerance per tier, chosen so the simplified line stays within half a device
# pixel of the source line in the closest view the tier is shown in:
#   start  - the start view, camera distance 2.44 at FOV 60: ~4.9 km per device px,
#            so 0.5 px ~ 2.4 km ~ 0.022 deg.
#   detail - the closest Three.js view before Mapbox takes over, distance 1.304 at
#            the telephoto FOV 13.2: ~0.21 km per device px, so 0.5 px ~ 0.001 deg.
# Coordinates are rounded to a tenth of the tolerance or finer (3 decimals =
# 0.001 deg, 4 decimals = 0.0001 deg). The borders' detail tier is the 10 m source
# unsimplified (tolerance 0), as the globe draws it today.
TIERS: dict[str, dict[str, str | float | int]] = {
    "coast_start": {
        "layer": "coastlines",
        "tier": "start",
        "source": "coast",
        "tolerance": 0.02,
        "decimals": 3,
    },
    "coast_detail": {
        "layer": "coastlines",
        "tier": "detail",
        "source": "coast",
        "tolerance": 0.001,
        "decimals": 4,
    },
    "borders_start": {
        "layer": "countryBorders",
        "tier": "start",
        "source": "borders",
        "tolerance": 0.02,
        "decimals": 3,
    },
    "borders_detail": {
        "layer": "countryBorders",
        "tier": "detail",
        "source": "borders",
        "tolerance": 0.0,
        "decimals": 4,
    },
}

LINES_PER_FEATURE = 5_000

Point = list[float]
Line = list[Point]


def flatten_lines(fc: dict) -> list[Line]:
    """Every line and ring of a FeatureCollection, walked like `vectorRenderer.ts`."""
    lines: list[Line] = []
    for feature in fc["features"]:
        geometry = feature["geometry"]
        kind = geometry["type"]
        coords = geometry["coordinates"]
        if kind == "LineString":
            parts = [coords]
        elif kind in ("MultiLineString", "Polygon"):
            parts = coords
        elif kind == "MultiPolygon":
            parts = [ring for polygon in coords for ring in polygon]
        else:
            raise ValueError(f"unsupported geometry type {kind!r} in a line layer")
        lines.extend([[float(p[0]), float(p[1])] for p in part] for part in parts)
    return lines


def is_artificial_antarctic(a: Sequence[float], b: Sequence[float]) -> bool:
    """Port of `isArtificialAntarcticBoundary` (ancient-nerds-map/src/components/Globe/rendering/segmentBuilder.ts).

    The sector lines that cut the Antarctic ice sheet at 0, +-90 and +-180 degrees
    longitude, and the connections along the South Pole. The renderer skips them.
    """
    lon1, lat1 = a[0], a[1]
    lon2, lat2 = b[0], b[1]
    if lat1 > -60 and lat2 > -60:
        return False
    for round_lon in (0, 90, -90, 180, -180):
        if abs(lon1 - round_lon) < 0.5 and abs(lon2 - round_lon) < 0.5 and abs(lat1 - lat2) > 2:
            return True
    return abs(lat1 - (-90)) < 0.5 and abs(lat2 - (-90)) < 0.5 and abs(lon1 - lon2) > 10


def _round_dedupe(line: Iterable[Sequence[float]], decimals: int) -> Line:
    out: Line = []
    for p in line:
        q = [round(p[0], decimals), round(p[1], decimals)]
        if not out or q != out[-1]:
            out.append(q)
    return out


def _split_at_artificial(line: Line) -> list[Line]:
    pieces: list[Line] = []
    current: Line = [line[0]]
    for a, b in zip(line, line[1:], strict=False):
        if is_artificial_antarctic(a, b):
            pieces.append(current)
            current = [b]
        else:
            current.append(b)
    pieces.append(current)
    return pieces


def _simplify(piece: Line, tolerance: float) -> Line:
    """Douglas-Peucker on one piece that holds no artificial segment.

    A closed piece (an island) is split at the point farthest from its start and
    both halves are simplified, so it stays closed and an islet smaller than the
    tolerance keeps a segment to its far side instead of collapsing to a point that
    draws nothing. For larger rings this is the split plain Douglas-Peucker makes
    first anyway.
    """
    if tolerance == 0 or len(piece) < 3:
        return piece
    if piece[0] == piece[-1]:
        x0, y0 = piece[0]
        far = max(
            range(len(piece)), key=lambda k: (piece[k][0] - x0) ** 2 + (piece[k][1] - y0) ** 2
        )
        return (
            _simplify_open(piece[: far + 1], tolerance) + _simplify_open(piece[far:], tolerance)[1:]
        )
    return _simplify_open(piece, tolerance)


def _simplify_open(piece: Line, tolerance: float) -> Line:
    """Douglas-Peucker on a line with distinct end points; a subsequence of its points.

    Where simplification would join two points by a segment the renderer takes for
    an artificial boundary - which would cut a real coast - the original points
    between them are kept.
    """
    if len(piece) < 3:
        return piece
    kept = [
        [x, y] for x, y in LineString(piece).simplify(tolerance, preserve_topology=False).coords
    ]
    out: Line = [piece[0]]
    i = 0  # index in `piece` of out[-1]
    for q in kept[1:]:
        j = i + 1
        while piece[j] != q:
            j += 1
        if is_artificial_antarctic(piece[i], q):
            out.extend(piece[i + 1 : j + 1])
        else:
            out.append(q)
        i = j
    return out


def clean_and_simplify(lines: Iterable[Line], tolerance: float, decimals: int) -> list[Line]:
    """Round, drop artificial Antarctic segments, simplify, keep pieces of >= 2 points.

    Rounding comes first, so the artificial-segment test sees the coordinates the
    renderer will see and the renderer's own filter finds nothing left to skip.
    """
    out: list[Line] = []
    for line in lines:
        rounded = _round_dedupe(line, decimals)
        if len(rounded) < 2:
            continue
        for piece in _split_at_artificial(rounded):
            if len(piece) < 2:
                continue
            simplified = _round_dedupe(_simplify(piece, tolerance), decimals)
            if len(simplified) >= 2:
                out.append(simplified)
    return out


def to_feature_collection_bytes(lines: Sequence[Line]) -> bytes:
    """A compact FeatureCollection: one MultiLineString feature per <= 5,000 lines."""
    features = [
        {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "MultiLineString",
                "coordinates": list(lines[i : i + LINES_PER_FEATURE]),
            },
        }
        for i in range(0, len(lines), LINES_PER_FEATURE)
    ]
    fc = {"type": "FeatureCollection", "features": features}
    return json.dumps(fc, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode(
        "utf-8"
    )


def hashed_name(stem: str, data: bytes) -> str:
    return f"{stem}.{hashlib.sha256(data).hexdigest()[:8]}.json"


def write_outputs(outputs: dict[str, bytes], out_dir: Path, manifest_path: Path) -> dict:
    """Write one file per tier, remove every other `*.json` in `out_dir`, write the manifest.

    The manifest is source code, not data: sorted keys, 2-space indent, LF, trailing newline.
    """
    if set(outputs) != set(TIERS):
        raise ValueError(f"outputs {sorted(outputs)} do not match the tiers {sorted(TIERS)}")
    out_dir.mkdir(parents=True, exist_ok=True)
    names = {stem: hashed_name(stem, data) for stem, data in outputs.items()}
    for stale in out_dir.glob("*.json"):
        if stale.name not in names.values():
            stale.unlink()
    manifest: dict[str, dict[str, str]] = {}
    for stem, data in outputs.items():
        (out_dir / names[stem]).write_bytes(data)
        spec = TIERS[stem]
        manifest.setdefault(str(spec["layer"]), {})[str(spec["tier"])] = URL_PREFIX + names[stem]
    text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    manifest_path.write_bytes(text.encode("utf-8"))
    return manifest


def _is_url(source: str) -> bool:
    return urlparse(source).scheme in ("http", "https")


def read_source(source: str, expected_sha256: str, tmp_dir: Path) -> bytes:
    """Bytes of a local file or of a URL downloaded into `tmp_dir`, verified by digest."""
    if _is_url(source):
        target = tmp_dir / Path(urlparse(source).path).name
        print(f"Downloading {source} ...", flush=True)
        with urllib.request.urlopen(source, timeout=DOWNLOAD_TIMEOUT_S) as response:
            target.write_bytes(response.read())
        data = target.read_bytes()
    else:
        data = Path(source).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_sha256:
        raise SystemExit(
            f"{source}: sha256 {digest} ({len(data):,} bytes) is not the pinned {expected_sha256}. "
            "If the source changed on purpose, update the pinned digest in this script."
        )
    return data


def build(coast: str, borders: str) -> dict[str, bytes]:
    with tempfile.TemporaryDirectory(prefix="globe_layers_") as tmp:
        tmp_dir = Path(tmp)
        sources = {
            "coast": flatten_lines(json.loads(read_source(coast, COAST_SHA256, tmp_dir))),
            "borders": flatten_lines(json.loads(read_source(borders, BORDERS_SHA256, tmp_dir))),
        }
    for name, lines in sources.items():
        print(f"{name:8s} source: {len(lines):>7,} lines {sum(map(len, lines)):>9,} points")
    outputs: dict[str, bytes] = {}
    for stem, spec in TIERS.items():
        lines = clean_and_simplify(
            sources[str(spec["source"])],
            tolerance=float(spec["tolerance"]),
            decimals=int(spec["decimals"]),
        )
        data = to_feature_collection_bytes(lines)
        outputs[stem] = data
        print(
            f"{stem:15s} tol {float(spec['tolerance']):<6g} dec {spec['decimals']}: "
            f"{len(lines):>7,} lines {sum(map(len, lines)):>9,} points "
            f"{len(data):>11,} B raw {len(gzip.compress(data, 6)):>10,} B gzip-6"
        )
    return outputs


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--coast", default=COAST_URL, help="coast_hires.geojson path or URL")
    parser.add_argument(
        "--borders", default=BORDERS_URL, help="ne_10m_admin_0_boundary_lines_land path or URL"
    )
    args = parser.parse_args(argv)
    outputs = build(args.coast, args.borders)
    manifest = write_outputs(outputs, OUT_DIR, MANIFEST_PATH)
    print(f"Wrote {MANIFEST_PATH.relative_to(ROOT).as_posix()}:")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
