# SPDX-License-Identifier: AGPL-3.0-only
"""scripts/build_globe_layers.py - the globe's coastline and border tiers.

The pure steps (walk, clean, simplify, serialise, name) are tested on tiny inline
lines; the committed output is tested for what the frontend relies on: the
manifest points at files that exist, carry their content hash and stay within
their gzip budgets. No network, no LFS.
"""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "build_globe_layers.py"


@pytest.fixture(scope="module")
def mod() -> ModuleType:
    # By file: a dependency installs a top-level package named `scripts` into
    # site-packages, which shadows our scripts/ directory for a plain import.
    spec = importlib.util.spec_from_file_location("build_globe_layers", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_simplify_drops_artificial_antarctic_segments_before_simplifying(mod):
    # vertical segment at a round longitude below -60 spanning > 2 degrees, like isArtificialAntarcticBoundary
    lines = [[[180.0, -70.0], [180.0, -80.0]], [[10.0, 50.0], [10.5, 50.2], [11.0, 50.0]]]
    out = mod.clean_and_simplify(lines, tolerance=0.0, decimals=3)
    assert [[180.0, -70.0], [180.0, -80.0]] not in out
    assert out == [[[10.0, 50.0], [10.5, 50.2], [11.0, 50.0]]]


def test_artificial_segment_splits_a_line_instead_of_bridging_it(mod):
    # A real coast that runs into a sector line at 0 deg and continues after it: the
    # artificial piece goes, both real pieces stay, and nothing joins them.
    line = [[-3.0, -69.0], [0.1, -70.0], [0.2, -75.0], [3.0, -74.0]]
    out = mod.clean_and_simplify([line], tolerance=0.0, decimals=3)
    assert out == [[[-3.0, -69.0], [0.1, -70.0]], [[0.2, -75.0], [3.0, -74.0]]]


def test_simplification_cannot_create_an_artificial_segment(mod):
    # The middle point is off the chord by 0.45 deg, under the 0.5 deg tolerance, so
    # Douglas-Peucker alone would reduce the line to one segment from 0.1 to 0.2 deg
    # longitude spanning 10 deg latitude - a segment the renderer's filter drops, which
    # would cut a real coast. The original points between its ends come back instead.
    line = [[0.1, -65.0], [0.6, -70.0], [0.2, -75.0]]
    assert not any(mod.is_artificial_antarctic(a, b) for a, b in zip(line, line[1:], strict=False))
    out = mod.clean_and_simplify([line], tolerance=0.5, decimals=3)
    assert out == [line]


def test_simplification_restores_only_the_offending_stretch(mod):
    # A far-away bend is simplified as usual while the Antarctic stretch keeps its points.
    line = [[0.1, -65.0], [0.6, -70.0], [0.2, -75.0], [5.0, -75.0], [10.0, -75.001], [15.0, -75.0]]
    out = mod.clean_and_simplify([line], tolerance=0.5, decimals=3)
    assert out == [[[0.1, -65.0], [0.6, -70.0], [0.2, -75.0], [15.0, -75.0]]]


def test_rounding_and_min_two_points(mod):
    out = mod.clean_and_simplify(
        [[[1.23456, 2.34567], [1.23457, 2.34568]]], tolerance=0.01, decimals=3
    )
    assert all(len(line) >= 2 for line in out)
    assert all(p == [round(p[0], 3), round(p[1], 3)] for line in out for p in line)


def test_consecutive_duplicates_are_dropped_after_rounding(mod):
    out = mod.clean_and_simplify(
        [[[1.00001, 1.0], [1.00002, 1.0], [2.0, 2.0]]], tolerance=0.0, decimals=3
    )
    assert out == [[[1.0, 1.0], [2.0, 2.0]]]


def test_closed_ring_stays_closed_after_simplification(mod):
    ring = [[0.0, 0.0], [1.0, 0.001], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0], [0.0, 0.0]]
    (out,) = mod.clean_and_simplify([ring], tolerance=0.01, decimals=3)
    assert out[0] == out[-1]
    assert [1.0, 0.001] not in out  # the near-collinear point went
    assert len(out) == 5


def test_closed_ring_below_the_tolerance_stays_a_speck(mod):
    # An islet smaller than the tolerance: plain Douglas-Peucker on the closed line
    # collapses it to its start point, and a zero-length line draws nothing. Split at
    # its farthest point, the ring keeps a segment there and back, so it still draws.
    islet = [[5.0, 5.0], [5.004, 5.001], [5.006, 5.005], [5.001, 5.004], [5.0, 5.0]]
    out = mod.clean_and_simplify([islet], tolerance=0.02, decimals=3)
    assert out == [[[5.0, 5.0], [5.006, 5.005], [5.0, 5.0]]]


def test_flatten_walks_every_geometry_like_the_renderer(mod):
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "MultiLineString",
                    "coordinates": [[[2, 2], [3, 3]], [[4, 4], [5, 5]]],
                },
            },
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [
                        [[[6, 6], [7, 6], [7, 7], [6, 6]]],
                        [[[8, 8], [9, 8], [9, 9], [8, 8]]],
                    ],
                },
            },
        ],
    }
    lines = mod.flatten_lines(fc)
    assert lines == [
        [[0.0, 0.0], [1.0, 1.0]],
        [[2.0, 2.0], [3.0, 3.0]],
        [[4.0, 4.0], [5.0, 5.0]],
        [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]],
        [[6.0, 6.0], [7.0, 6.0], [7.0, 7.0], [6.0, 6.0]],
        [[8.0, 8.0], [9.0, 8.0], [9.0, 9.0], [8.0, 8.0]],
    ]


def test_flatten_rejects_an_unknown_geometry(mod):
    fc = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}}],
    }
    with pytest.raises(ValueError, match="Point"):
        mod.flatten_lines(fc)


def test_feature_collection_is_compact_multilinestring(mod):
    raw = mod.to_feature_collection_bytes([[[0.0, 0.0], [1.0, 1.0]]])
    assert raw.startswith(b'{"type":"FeatureCollection"') and not raw.endswith(b"\n")
    fc = json.loads(raw)
    assert {f["geometry"]["type"] for f in fc["features"]} == {"MultiLineString"}


def test_feature_collection_splits_into_features_of_at_most_5000_lines(mod):
    lines = [[[float(i), 0.0], [float(i), 1.0]] for i in range(12_001)]
    fc = json.loads(mod.to_feature_collection_bytes(lines))
    sizes = [len(f["geometry"]["coordinates"]) for f in fc["features"]]
    assert sizes == [5000, 5000, 2001]
    assert [line for f in fc["features"] for line in f["geometry"]["coordinates"]] == lines


def test_hashed_name_is_content_addressed(mod):
    assert mod.hashed_name("coast_start", b"abc") == "coast_start.ba7816bf.json"


def test_write_outputs_replaces_stale_files_and_writes_the_manifest(mod, tmp_path):
    out_dir = tmp_path / "globe"
    out_dir.mkdir()
    (out_dir / "coast_start.00000000.json").write_bytes(b"{}")
    (out_dir / "keep.txt").write_bytes(b"not a layer file")
    manifest_path = tmp_path / "globeLayers.generated.json"
    outputs = {stem: f'{{"stem":"{stem}"}}'.encode() for stem in mod.TIERS}

    mod.write_outputs(outputs, out_dir, manifest_path)

    names = sorted(p.name for p in out_dir.glob("*.json"))
    assert names == sorted(mod.hashed_name(stem, data) for stem, data in outputs.items())
    assert (out_dir / "keep.txt").exists()
    text = manifest_path.read_bytes().decode()
    assert text.endswith("}\n") and "\r" not in text
    manifest = json.loads(text)
    assert manifest == {
        "coastlines": {
            "detail": "/data/layers/globe/"
            + mod.hashed_name("coast_detail", outputs["coast_detail"]),
            "start": "/data/layers/globe/" + mod.hashed_name("coast_start", outputs["coast_start"]),
        },
        "countryBorders": {
            "detail": "/data/layers/globe/"
            + mod.hashed_name("borders_detail", outputs["borders_detail"]),
            "start": "/data/layers/globe/"
            + mod.hashed_name("borders_start", outputs["borders_start"]),
        },
    }
    assert text == json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def test_committed_manifest_points_at_committed_files_within_budget():
    root = Path(__file__).resolve().parents[2]
    manifest = json.loads(
        (root / "ancient-nerds-map/src/data/globeLayers.generated.json").read_text()
    )
    # borders detail: the unsimplified 10 m lines at 4 decimals measure 467,995 B
    # (2026-09-23); simplifying them to fit 450 kB would coarsen the one view that
    # shows them as today (Three.js closer than the Mapbox switch when Mapbox failed).
    budgets_gz = {
        "coastlines": {"start": 700_000, "detail": 3_500_000},
        "countryBorders": {"start": 200_000, "detail": 500_000},
    }
    assert {layer: set(tiers) for layer, tiers in manifest.items()} == {
        "coastlines": {"start", "detail"},
        "countryBorders": {"start", "detail"},
    }
    for layer, tiers in manifest.items():
        for tier, url in tiers.items():
            path = root / "public" / url.lstrip("/")
            data = path.read_bytes()
            assert hashlib.sha256(data).hexdigest()[:8] in path.name
            assert len(gzip.compress(data, 6)) <= budgets_gz[layer][tier]
            fc = json.loads(data)
            assert fc["type"] == "FeatureCollection" and fc["features"]
            assert {f["geometry"]["type"] for f in fc["features"]} == {"MultiLineString"}
            assert not data.endswith(b"\n")


def test_committed_directory_holds_only_the_manifest_files():
    root = Path(__file__).resolve().parents[2]
    manifest = json.loads(
        (root / "ancient-nerds-map/src/data/globeLayers.generated.json").read_text()
    )
    referenced = {Path(url).name for tiers in manifest.values() for url in tiers.values()}
    present = {p.name for p in (root / "public/data/layers/globe").glob("*.json")}
    assert present == referenced
