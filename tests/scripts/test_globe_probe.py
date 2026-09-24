"""scripts/globe_probe/probe.py: the pure parts of the globe load probe.

The browser-driving parts need Playwright and a real Chromium, which the CI
tests job does not install; they are exercised by running the probe itself
(see scripts/globe_probe/README.md). What is tested here is everything a
probe number is computed from: the byte ledger, the local-build routing, the
simulated `fields=globe` projection, the long-task window and the image diff.
"""

from __future__ import annotations

import gzip
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

# By file: a dependency installs a top-level package named `scripts` into
# site-packages, which shadows our scripts/ directory for a plain import.
_SPEC = importlib.util.spec_from_file_location(
    "globe_probe", Path(__file__).resolve().parents[2] / "scripts" / "globe_probe" / "probe.py"
)
assert _SPEC is not None and _SPEC.loader is not None
probe = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = probe  # dataclasses resolve their module by name
_SPEC.loader.exec_module(probe)


# --- fields=globe simulation -------------------------------------------------


def _full_site(**extra: object) -> dict:
    site = {
        "id": "a",
        "n": "Dara Fortress",
        "la": 37.1,
        "lo": 40.9,
        "s": "ancient_nerds",
        "t": "Fortress",
        "p": 750,
        "pn": "500 - 1000 AD",
        "d": "A long description",
        "c": "Türkiye",
        "u": "https://en.wikipedia.org/wiki/Dara",
        "eb": "someone",
        "ea": "2026-04-25T01:56:41",
    }
    site.update(extra)
    return site


def test_projection_keeps_only_the_globe_keys_and_the_envelope():
    payload = {"count": 1, "sites": [_full_site()], "dataSource": "postgres"}
    out = probe.project_globe_payload(payload)
    assert out["count"] == 1 and out["dataSource"] == "postgres"
    assert set(out["sites"][0]) == {"id", "n", "la", "lo", "s", "t", "p", "pn", "c"}
    assert payload["sites"][0]["d"] == "A long description"  # input untouched


def test_projection_leaves_absent_keys_absent():
    site = {"id": "b", "n": "Pin", "la": 1.0, "lo": 2.0, "s": "ancient_nerds", "d": "x"}
    out = probe.project_globe_payload({"count": 1, "sites": [site], "dataSource": "postgres"})
    assert out["sites"] == [{"id": "b", "n": "Pin", "la": 1.0, "lo": 2.0, "s": "ancient_nerds"}]


def test_is_globe_projected_detects_a_server_that_ignores_fields():
    assert not probe.is_globe_projected({"count": 1, "sites": [_full_site()]})
    projected = probe.project_globe_payload({"count": 1, "sites": [_full_site()]})
    assert probe.is_globe_projected(projected)


def test_without_query_param_drops_only_that_param():
    url = "https://ancientnerds.com/api/sites/all?limit=100000&source=ancient_nerds&fields=globe&_v=abc"
    assert (
        probe.without_query_param(url, "fields")
        == "https://ancientnerds.com/api/sites/all?limit=100000&source=ancient_nerds&_v=abc"
    )


# --- byte accounting for route-fulfilled local files ---------------------------


def test_counted_bytes_mirror_nginx_gzip_types_and_min_length():
    body = json.dumps({"k": ["value"] * 500}).encode()
    assert len(body) >= 1024
    assert probe.counted_bytes(body, "application/json") == len(gzip.compress(body, 6, mtime=0))
    assert probe.counted_bytes(body, "application/javascript") < len(body)
    small = b'{"a":1}'
    assert probe.counted_bytes(small, "application/json") == len(small)  # gzip_min_length 1024
    blob = bytes(range(256)) * 20
    assert probe.counted_bytes(blob, "image/webp") == len(blob)
    assert probe.counted_bytes(blob, "font/woff2") == len(blob)


def test_content_types_are_the_production_ones():
    assert probe.content_type_for(Path("a/globe.html")) == "text/html"
    assert probe.content_type_for(Path("assets/main-x.js")) == "application/javascript"
    assert probe.content_type_for(Path("assets/x.css")) == "text/css"
    assert probe.content_type_for(Path("x/coast_start.1a2b3c4d.json")) == "application/json"
    assert probe.content_type_for(Path("fonts/inter.woff2")) == "font/woff2"
    assert probe.content_type_for(Path("manifest.webmanifest")) == "application/manifest+json"
    assert probe.content_type_for(Path("a.webp")) == "image/webp"
    assert probe.content_type_for(Path("a.svg")) == "image/svg+xml"
    # nginx default_type for anything its mime table lacks
    assert probe.content_type_for(Path("a.unknownext")) == "application/octet-stream"


# --- local build routing ---------------------------------------------------------


@pytest.fixture
def trees(tmp_path: Path) -> tuple[Path, Path]:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "data" / "snapshots").mkdir(parents=True)
    (dist / "globe.html").write_text("<html></html>")
    (dist / "index.html").write_text("<html></html>")
    (dist / "sw.js").write_text("self")
    (dist / "assets" / "main-abc.js").write_text("x")
    (dist / "data" / "snapshots" / "s.json").write_text("{}")
    layers = tmp_path / "public" / "data" / "layers" / "globe"
    layers.mkdir(parents=True)
    (layers / "coast_start.1a2b3c4d.json").write_text("{}")
    (tmp_path / "secret.txt").write_text("no")
    return dist, layers


def test_local_files_come_from_dist_and_the_globe_layer_dir(trees):
    dist, layers = trees
    base = "https://ancientnerds.com"
    assert probe.local_file_for(f"{base}/globe.html?demo=1", dist, layers) == dist / "globe.html"
    assert probe.local_file_for(f"{base}/", dist, layers) == dist / "index.html"
    assert probe.local_file_for(f"{base}/sw.js", dist, layers) == dist / "sw.js"
    assert (
        probe.local_file_for(f"{base}/assets/main-abc.js", dist, layers)
        == dist / "assets" / "main-abc.js"
    )
    assert (
        probe.local_file_for(f"{base}/data/layers/globe/coast_start.1a2b3c4d.json", dist, layers)
        == layers / "coast_start.1a2b3c4d.json"
    )


def test_everything_else_goes_to_production(trees):
    dist, layers = trees
    base = "https://ancientnerds.com"
    # other /data/ files, even the snapshot copy vite puts into dist
    assert probe.local_file_for(f"{base}/data/snapshots/s.json", dist, layers) is None
    assert probe.local_file_for(f"{base}/data/basemaps/gray_dark_med.webp", dist, layers) is None
    assert probe.local_file_for(f"{base}/data/layers/globe/missing.json", dist, layers) is None
    assert probe.local_file_for(f"{base}/api/sites/all?limit=1", dist, layers) is None
    assert probe.local_file_for(f"{base}/assets/not-built.js", dist, layers) is None
    assert probe.local_file_for("https://api.mapbox.com/assets/main-abc.js", dist, layers) is None


def test_local_routing_never_leaves_the_served_trees(trees):
    dist, layers = trees
    base = "https://ancientnerds.com"
    assert probe.local_file_for(f"{base}/..%2Fsecret.txt", dist, layers) is None
    assert probe.local_file_for(f"{base}/assets/..%2F..%2Fsecret.txt", dist, layers) is None
    assert (
        probe.local_file_for(
            f"{base}/data/layers/globe/..%2F..%2F..%2F..%2Fsecret.txt", dist, layers
        )
        is None
    )


# --- CDP byte ledger ---------------------------------------------------------------


def _ledger_with_three_requests() -> object:
    """Monotonic clock 100 s == wall clock 1_000_000 s; timeOrigin at wall 1_000_000_000 ms."""
    led = probe.ByteLedger()
    led.request("1", "https://ancientnerds.com/globe.html", timestamp=100.0, wall_time=1_000_000.0)
    led.finished("1", timestamp=100.2, encoded_length=5_000)
    led.request(
        "2", "https://ancientnerds.com/data/big.json", timestamp=100.5, wall_time=1_000_000.5
    )
    led.finished("2", timestamp=103.0, encoded_length=70_000)
    led.request(
        "3", "https://ancientnerds.com/data/late.webp", timestamp=101.0, wall_time=1_000_001.0
    )
    return led


def test_ledger_counts_what_finished_before_ready_in_page_time():
    led = _ledger_with_three_requests()
    s = led.summary(ready_ms=2_500.0, time_origin_ms=1_000_000_000.0)
    assert s["bytes_before_ready"] == 5_000
    assert s["requests_before_ready"] == 1
    assert [r["url"] for r in s["in_flight_at_ready"]] == [
        "https://ancientnerds.com/data/big.json",
        "https://ancientnerds.com/data/late.webp",
    ]
    assert s["bytes_total"] == 75_000
    big = next(r for r in s["requests"] if r["url"].endswith("big.json"))
    assert big["start_ms"] == pytest.approx(500.0) and big["end_ms"] == pytest.approx(3_000.0)


def test_ledger_without_ready_reports_totals_only():
    s = _ledger_with_three_requests().summary(ready_ms=None, time_origin_ms=1_000_000_000.0)
    assert s["bytes_before_ready"] is None and s["in_flight_at_ready"] is None
    assert s["bytes_total"] == 75_000


def test_ledger_uses_the_counted_size_for_route_fulfilled_urls():
    led = _ledger_with_three_requests()
    led.fulfilled_locally("https://ancientnerds.com/globe.html", 1_234)
    s = led.summary(ready_ms=2_500.0, time_origin_ms=1_000_000_000.0)
    assert s["bytes_before_ready"] == 1_234
    page = next(r for r in s["requests"] if r["url"].endswith("globe.html"))
    assert page["local"] is True


def test_ledger_records_failures_and_marks_probe_blocks():
    led = probe.ByteLedger()
    led.request("9", "https://api.mapbox.com/v4/x", timestamp=1.0, wall_time=10.0)
    # Chromium names a Playwright route.abort("blockedbyclient") this way
    led.failed("9", timestamp=1.1, error_text="net::ERR_BLOCKED_BY_CLIENT.Inspector")
    led.request("8", "https://ipwho.is/", timestamp=1.0, wall_time=10.0)
    led.failed("8", timestamp=1.5, error_text="net::ERR_TIMED_OUT")
    s = led.summary(ready_ms=None, time_origin_ms=10_000.0)
    assert s["blocked"] == ["https://api.mapbox.com/v4/x"]
    assert s["failed"] == [{"url": "https://ipwho.is/", "error": "net::ERR_TIMED_OUT"}]
    assert s["bytes_total"] == 0


def test_ledger_ignores_non_http_urls():
    led = probe.ByteLedger()
    led.request("d", "data:image/png;base64,AAAA", timestamp=1.0, wall_time=10.0)
    led.finished("d", timestamp=1.0, encoded_length=0)
    assert led.summary(ready_ms=None, time_origin_ms=0.0)["requests"] == []


# --- long tasks ----------------------------------------------------------------------


def test_long_task_window_selects_by_start_and_lists_the_slow_ones():
    tasks = [
        {"start": 100.0, "duration": 900.0},  # before the window
        {"start": 1_000.0, "duration": 60.0},
        {"start": 5_000.0, "duration": 250.0},
        {"start": 31_000.0, "duration": 400.0},  # after the window
    ]
    w = probe.long_task_window(tasks, start_ms=1_000.0, end_ms=31_000.0)
    assert w["count"] == 2
    assert w["max_ms"] == 250.0 and w["total_ms"] == 310.0
    assert w["over_200ms"] == [{"start": 5_000.0, "duration": 250.0}]


def test_long_task_window_is_empty_without_tasks():
    assert probe.long_task_window([], 0.0, 1.0) == {
        "count": 0,
        "max_ms": 0.0,
        "total_ms": 0.0,
        "over_200ms": [],
    }


# --- image diff ------------------------------------------------------------------------


def test_identical_images_do_not_differ():
    a = Image.new("RGB", (10, 10), (30, 60, 90))
    stats, diff = probe.image_diff(a, a.copy())
    assert stats["mean_abs_diff"] == 0.0 and stats["share_over_threshold"] == 0.0
    assert diff.size == (10, 10)


def test_diff_counts_pixels_over_the_threshold_only():
    a = Image.new("RGB", (10, 10), (0, 0, 0))
    b = a.copy()
    b.putpixel((0, 0), (255, 0, 0))  # over 24 in one channel
    b.putpixel((1, 0), (20, 20, 20))  # under the threshold
    stats, _ = probe.image_diff(a, b, threshold=24)
    assert stats["share_over_threshold"] == pytest.approx(0.01)
    assert stats["mean_abs_diff"] == pytest.approx((255 + 60) / 300)
    assert stats["width"] == 10 and stats["height"] == 10 and stats["threshold"] == 24


def test_diff_accepts_rgba_screenshots():
    a = Image.new("RGBA", (4, 4), (10, 10, 10, 255))
    stats, _ = probe.image_diff(a, a.convert("RGB"))
    assert stats["mean_abs_diff"] == 0.0


def test_diff_refuses_different_sizes():
    with pytest.raises(ValueError, match="size"):
        probe.image_diff(Image.new("RGB", (2, 2)), Image.new("RGB", (3, 2)))


# --- arguments and devices ---------------------------------------------------------------


def test_parse_pose():
    assert probe.parse_pose("10,51,2.44") == (10.0, 51.0, 2.44)
    assert probe.parse_pose("-73.5, -13.2, 1.31") == (-73.5, -13.2, 1.31)
    with pytest.raises(ValueError):
        probe.parse_pose("10,51")
    with pytest.raises(ValueError):
        probe.parse_pose("10,95,2")  # latitude out of range
    with pytest.raises(ValueError):
        probe.parse_pose("10,51,0.5")  # inside the globe


def test_parser_defaults_block_mapbox_for_load_but_not_for_shot():
    p = probe.build_parser()
    load = p.parse_args(["load", "--target", "prod"])
    assert load.block_mapbox is True and load.device == "desktop" and load.cpu == 1
    assert load.net == "none" and load.gpu is False
    shot = p.parse_args(["shot", "--target", "prod", "--pose", "10,51,2.44"])
    assert shot.block_mapbox is False and shot.dpr == 1.0 and shot.after_bg is False
    assert shot.bg_tasks == "layers,basemap" and shot.labels is False
    assert p.parse_args(["shot", "--target", "local", "--pose", "1,2,3", "--labels"]).labels
    assert p.parse_args(
        ["shot", "--target", "local", "--pose", "1,2,3", "--block-mapbox"]
    ).block_mapbox
    nogl = p.parse_args(["nogl", "--target", "prod"])
    assert nogl.block_mapbox is True
    diff = p.parse_args(["diff", "a.png", "b.png"])
    assert diff.threshold == 24
    with pytest.raises(SystemExit):
        p.parse_args(["load", "--target", "staging"])


def test_desktop_and_phone_contexts():
    desk = probe.device_options("desktop", dpr=None, chrome_major="140")
    assert desk["viewport"] == {"width": 1920, "height": 1080}
    assert desk["device_scale_factor"] == 1.0
    assert desk["is_mobile"] is False and desk["has_touch"] is False
    assert "Windows NT" in desk["user_agent"] and "Chrome/140." in desk["user_agent"]
    assert "Headless" not in desk["user_agent"]
    phone = probe.device_options("phone", dpr=None, chrome_major="140")
    assert phone["viewport"] == {"width": 412, "height": 915}
    assert phone["device_scale_factor"] == 2.625
    assert phone["is_mobile"] is True and phone["has_touch"] is True
    # the phone gate's UA rule: Android.*Mobile
    assert "Android" in phone["user_agent"] and "Mobile" in phone["user_agent"]
    assert (
        probe.device_options("desktop", dpr=2.0, chrome_major="140")["device_scale_factor"] == 2.0
    )


def test_fast4g_is_the_devtools_preset():
    fast = probe.NETWORK_PRESETS["fast4g"]
    assert fast == {
        "offline": False,
        "latency": 60 * 2.75,
        "downloadThroughput": 9 * 1000 * 1000 / 8 * 0.9,
        "uploadThroughput": 1.5 * 1000 * 1000 / 8 * 0.9,
    }
    assert probe.NETWORK_PRESETS["none"] is None


def test_run_dir_names_are_sortable_and_describe_the_run(tmp_path: Path):
    d = probe.run_dir(tmp_path, ["load", "prod", "phone"], datetime(2026, 9, 23, 21, 5, 9))
    assert d == tmp_path / "20260923-210509-load-prod-phone"
    assert d.is_dir()


def test_page_url_carries_demo_and_extra_query():
    # both targets are loaded under the production origin; only the routing differs
    assert probe.page_url(None) == "https://ancientnerds.com/globe.html?demo=1"
    assert probe.page_url("basemap=med") == "https://ancientnerds.com/globe.html?demo=1&basemap=med"


def test_only_the_globe_sites_request_is_simulated():
    base = "https://ancientnerds.com/api/sites/all"
    assert probe.is_sites_globe_request(
        f"{base}?limit=100000&source=ancient_nerds&fields=globe&_v=1"
    )
    assert not probe.is_sites_globe_request(f"{base}?limit=100000&source=ancient_nerds&_v=1")
    assert not probe.is_sites_globe_request(f"{base}?fields=all")
    assert not probe.is_sites_globe_request("https://ancientnerds.com/api/sites/x?fields=globe")
    assert not probe.is_sites_globe_request("https://example.com/api/sites/all?fields=globe")


def test_ledger_lists_http_errors_with_their_status():
    led = probe.ByteLedger()
    led.request("p", "https://ancientnerds.com/data/basemaps/gray_dark_low.png", 1.0, 10.0)
    led.response("p", 404)
    led.finished("p", timestamp=1.1, encoded_length=300)
    led.request("q", "https://ancientnerds.com/globe.html", 1.0, 10.0)
    led.response("q", 200)
    led.finished("q", timestamp=1.1, encoded_length=900)
    s = led.summary(ready_ms=None, time_origin_ms=10_000.0)
    assert s["http_errors"] == [
        {"url": "https://ancientnerds.com/data/basemaps/gray_dark_low.png", "status": 404}
    ]
    assert [r["status"] for r in s["requests"]] == [404, 200]
    assert s["bytes_total"] == 1_200  # an error body is still transferred


def test_reports_never_carry_the_mapbox_token():
    led = probe.ByteLedger()
    url = "https://api.mapbox.com/styles/v1/mapbox/dark-v11?sdk=js-3.18.0&access_token=pk.secret"
    led.request("m", url, 1.0, 10.0)
    led.failed("m", timestamp=1.1, error_text="net::ERR_BLOCKED_BY_CLIENT.Inspector")
    s = led.summary(ready_ms=None, time_origin_ms=10_000.0)
    assert "pk.secret" not in json.dumps(s)
    assert s["blocked"] == [
        "https://api.mapbox.com/styles/v1/mapbox/dark-v11?sdk=js-3.18.0&access_token=REDACTED"
    ]
