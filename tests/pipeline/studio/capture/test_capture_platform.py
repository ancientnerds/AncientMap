"""Planning logic of platform takes (pipeline/studio/capture/platform.py); the take needs headed
Chrome, the driver's clicks run here on small synthetic pages in headless Chrome."""

import asyncio
import base64
import importlib.util
import itertools
import json
import math
import time
import types
from contextlib import nullcontext

import pytest

from pipeline.historical_boundaries.empire_metadata import EMPIRE_METADATA
from pipeline.studio.capture import platform as platform_take
from pipeline.studio.capture.encode import concat_script
from pipeline.studio.capture.manifest import CaptureError
from pipeline.studio.capture.platform import (
    KEY_DELAY_MS,
    MAP_CANVAS,
    MAX_TAKE_S,
    MOVE_S,
    START_POS,
    VIEWPORT,
    Take,
    _Driver,
    _Screencast,
    eased_path,
    events_from_marks,
    frame_size,
    measure_gap_ok,
    measurement_label,
    motion_fps,
    parse_measurement_count,
    parse_zoom_percent,
    record_platform,
    screen_point_or_fail,
    take_url,
    validate_actions,
    wait_ready,
)
from pipeline.utils import geo


def test_validate_accepts_the_declarative_vocabulary():
    actions = [
        {"do": "pause_rotation"},
        {"do": "search", "q": "baalbek"},
        {"do": "click_result", "title": "Baalbek Stones"},
        {"do": "fly_wait", "s": 3},
        {"do": "zoom", "to": 90},
        {"do": "open_details", "title": "Baalbek Stones"},
        {"do": "measure", "a": {"lat": 34.0, "lng": 36.2}, "b": {"lat": 34.01, "lng": 36.21}},
        {"do": "toggle_layer", "label": "Empire Borders", "empire": "roman"},
        {"do": "proximity", "at": {"lat": 34.0067, "lng": 36.2033}},
        {"do": "filter", "mode": "category", "label": "Pyramid"},
        {"do": "wait", "s": 1.5},
        {"do": "toggle_layer", "label": "Coastlines"},
    ]
    out = validate_actions(actions)
    assert [a["do"] for a in out] == [a["do"] for a in actions]
    assert out[3]["s"] == 3.0 and out[4]["to"] == 90
    assert out[7] == {"do": "toggle_layer", "label": "Empire Borders", "empire": "roman"}
    assert out[8]["at"] == {"lat": 34.0067, "lng": 36.2033}
    assert out[9] == {"do": "filter", "mode": "category", "label": "Pyramid"}
    assert out[11] == {"do": "toggle_layer", "label": "Coastlines"}


@pytest.mark.parametrize(
    ("actions", "message"),
    [
        ([], "non-empty"),
        ([{"do": "scroll"}], "unknown action"),
        ([{"do": "search"}], r"needs exactly \['q'\]"),
        ([{"do": "search", "q": "x", "extra": 1}], "needs exactly"),
        ([{"do": "search", "q": " "}], "non-empty string"),
        ([{"do": "wait", "s": 0}], r"must be in \(0, 10\]"),
        ([{"do": "measure", "a": {"lat": 1}, "b": {"lat": 1, "lng": 2}}], "must be"),
        (
            [{"do": "measure", "a": {"lat": 91, "lng": 0}, "b": {"lat": 1, "lng": 2}}],
            "not a coordinate",
        ),
        ([{"do": "wait", "s": 10}] * 4, f"exceed the {MAX_TAKE_S:.0f} s take limit"),
        ([{"do": "wait", "s": "3"}], r"actions\[0\]\.s must be a number"),
        ([{"do": "zoom", "to": 101}], "zoom-slider percent 0..100"),
        ([{"do": "zoom", "to": 50.5}], r"actions\[0\]\.to must be an integer"),
        ([{"do": "proximity", "at": {"lat": 34.0}}], "must be"),
        ([{"do": "filter", "mode": "age", "label": "x"}], "mode must be one of"),
        # owner correction 2026-09-26: no satellite toggle in globe sections
        (
            [{"do": "toggle_layer", "label": " satellite "}],
            r"actions\[0\]: no satellite toggle in globe sections",
        ),
        # the Empire Borders toggle only opens its window: without an empire it draws nothing
        (
            [{"do": "toggle_layer", "label": "Empire Borders"}],
            r"actions\[0\]: 'Empire Borders' only opens its window; name the empire to show",
        ),
        (
            [{"do": "toggle_layer", "label": "Empire Borders", "empire": "atlantis"}],
            r"actions\[0\]\.empire must be an empire id of "
            r"pipeline/historical_boundaries/empire_metadata\.py, got 'atlantis'",
        ),
        (
            [{"do": "toggle_layer", "label": "Empire Borders", "empire": ["roman"]}],
            r"actions\[0\]\.empire must be an empire id",
        ),
        (
            [{"do": "toggle_layer", "label": "Coastlines", "empire": "roman"}],
            r"actions\[0\]: only 'Empire Borders' takes an empire, not 'Coastlines'",
        ),
        # a second click on Empire Borders closes its window (Globe.tsx): one empire per take
        (
            [
                {"do": "toggle_layer", "label": "Empire Borders", "empire": "roman"},
                {"do": "wait", "s": 1.0},
                {"do": "toggle_layer", "label": "empire borders", "empire": "parthian"},
            ],
            r"actions\[2\]: a take shows at most one empire: 'Empire Borders' at actions\[0\] "
            r"opened its window, and a second click closes it",
        ),
        (
            [{"do": "toggle_layer", "label": "Historical Routes"}],
            r"actions\[0\]: 'Historical Routes' only opens its picker window",
        ),
        (
            [{"do": "toggle_layer", "label": "geological layers"}],
            r"actions\[0\]: 'geological layers' only opens its picker window",
        ),
        (
            [{"do": "search", "q": "x", "empire": "roman"}],
            r"actions\[0\] \(search\) needs exactly \['q'\], got \['empire', 'q'\]",
        ),
        (
            [{"do": "toggle_layer", "empire": "roman"}],
            r"\(toggle_layer\) needs exactly \['label'\] \(optional \['empire'\]\)",
        ),
    ],
)
def test_validate_rejects_bad_actions(actions, message):
    with pytest.raises(CaptureError, match=message):
        validate_actions(actions)


def test_the_action_contract_is_the_one_plan_d_hands_to_the_skill():
    """Review of Task 36: b2f484f added `empire` and refused three toggles, and nothing
    carried that to the files that teach the contract. Plan D's cross-stream request 9 (the
    studio-video skill's platform row) and request 3 (STUDIO.md) state exactly this
    vocabulary; a change here must change both requests in the same commit."""
    assert {do: sorted(keys) for do, keys in platform_take.ACTIONS.items()} == {
        "pause_rotation": [],
        "search": ["q"],
        "click_result": ["title"],
        "fly_wait": ["s"],
        "zoom": ["to"],
        "open_details": ["title"],
        "measure": ["a", "b"],
        "toggle_layer": ["label"],
        "proximity": ["at"],
        "filter": ["label", "mode"],
        "wait": ["s"],
    }
    assert platform_take.OPTIONAL == {"toggle_layer": frozenset({"empire"})}
    assert platform_take.SATELLITE_LAYER == "satellite"
    assert platform_take.EMPIRE_LAYER == "empire borders"
    assert platform_take.PICKER_LAYERS == {"geological layers", "historical routes"}


def test_coordinates_are_checked_by_the_shared_geo_utility():
    # repo rule: import a utility, never duplicate it (capture/mapbox.py does the same)
    assert platform_take.is_valid_coordinates is geo.is_valid_coordinates
    assert validate_actions([{"do": "proximity", "at": {"lat": -90, "lng": 180}}])[0]["at"] == {
        "lat": -90.0,
        "lng": 180.0,
    }
    with pytest.raises(
        CaptureError, match=r"actions\[0\]\.at: \(0\.0, 180\.5\) is not a coordinate"
    ):
        validate_actions([{"do": "proximity", "at": {"lat": 0, "lng": 180.5}}])


def test_take_url_turns_on_demo_and_video_mode():
    assert (
        take_url("http://localhost:5198/", 1.3)
        == "http://localhost:5198/globe.html?demo=1&video=1&hud=1.3"
    )


def test_eased_path_is_fast_then_slow_and_ends_on_target():
    path = eased_path((0.0, 0.0), (100.0, 50.0), 15)
    assert len(path) == 15
    assert path[-1] == pytest.approx((100.0, 50.0))
    steps = [path[0][0]] + [b[0] - a[0] for a, b in zip(path, path[1:], strict=False)]
    assert steps == sorted(steps, reverse=True)


def test_measure_points_come_from_the_page_or_fail():
    where = {"lat": 34.0, "lng": 36.2}
    assert screen_point_or_fail({"x": 960, "y": 540}, "measure point a", where) == (960.0, 540.0)
    with pytest.raises(CaptureError, match="measure point b .* is not on screen"):
        screen_point_or_fail(None, "measure point b", {"lat": -34.0, "lng": -143.8})


def test_measure_points_need_room_on_screen():
    # a measurement between two clicks 50 px apart on the globe measures nothing: zoom in first
    assert measure_gap_ok((0.0, 0.0), (60.0, 0.0))
    assert not measure_gap_ok((100.0, 100.0), (130.0, 140.0))


def test_the_zoom_slider_reading_is_a_percent():
    assert (parse_zoom_percent("66%"), parse_zoom_percent(" 100 % ")) == (66, 100)
    with pytest.raises(CaptureError, match="not a percent"):
        parse_zoom_percent("Map")


def test_the_cursor_is_fast_even_when_each_move_takes_time():
    assert (MOVE_S, KEY_DELAY_MS) == (0.25, 45)

    class SlowMouse:
        """Each move blocks like a CDP round trip (5 ms)."""

        def __init__(self):
            self.times: list[float] = []

        async def move(self, x, y):
            time.sleep(0.005)
            self.times.append(time.time())

    page = types.SimpleNamespace(mouse=SlowMouse())
    driver = _Driver(page, Take())
    asyncio.run(driver.move(900.0, 500.0))
    started, _ended = driver.take.moves[0]
    assert page.mouse.times[-1] - started <= MOVE_S + 1 / 60
    assert driver.pos == (900.0, 500.0)


def test_events_are_relative_to_the_first_frame_in_media_pixels():
    marks = [(100.5, "search", {"x": 190.0, "y": 120.0}), (101.25, "fly_wait", {})]
    assert events_from_marks(marks, t0=100.0, scale=1.5) == [
        {"t": 0.5, "name": "search", "x": 285.0, "y": 180.0},
        {"t": 1.25, "name": "fly_wait"},
    ]


def test_motion_fps_is_the_worst_move():
    timestamps = [i / 60 for i in range(120)]
    assert motion_fps(timestamps, [(0.0, 0.5), (1.0, 1.5)]) == pytest.approx(62, abs=1)
    sparse = [0.0, 0.1, 0.2, 1.0, 1.25, 1.5]
    assert motion_fps(sparse, [(0.0, 0.5), (1.0, 1.5)]) == pytest.approx(6)
    assert motion_fps(sparse, []) == float("inf")


def test_record_platform_validates_before_starting_anything(tmp_path):
    with pytest.raises(CaptureError, match="takes kind 'platform'"):
        record_platform(tmp_path, {"id": "pf1", "kind": "globe"})
    base = {"id": "platform-01", "kind": "platform", "actions": [{"do": "pause_rotation"}]}
    with pytest.raises(CaptureError, match="target must be"):
        record_platform(tmp_path, {**base, "target": "staging"})
    with pytest.raises(CaptureError, match=r"unknown keys \['zoom'\]"):
        record_platform(tmp_path, {**base, "target": "local", "zoom": 2})
    with pytest.raises(CaptureError, match="unknown action"):
        record_platform(tmp_path, {**base, "target": "local", "actions": [{"do": "dance"}]})
    with pytest.raises(CaptureError, match=r"hud 3.0 outside 0.5..2.0"):
        record_platform(tmp_path, {**base, "target": "local", "hud": 3})
    with pytest.raises(CaptureError, match="hud must be a number"):
        record_platform(tmp_path, {**base, "target": "local", "hud": "1.3"})
    satellite = [{"do": "toggle_layer", "label": "Satellite"}]
    with pytest.raises(CaptureError, match="satellite shows in the details page or a Mapbox take"):
        record_platform(tmp_path, {**base, "target": "local", "actions": satellite})
    assert not (tmp_path / "captures").exists()


def test_frame_size_is_read_from_the_first_frame(tmp_path):
    from PIL import Image

    Image.new("RGB", (2880, 1620), "black").save(tmp_path / "f000000.jpg")
    assert frame_size(tmp_path) == (2880, 1620)


def test_a_page_that_never_gets_ready_names_the_likely_cause():
    playwright = pytest.importorskip("playwright.async_api")

    class NeverReady:
        async def wait_for_function(self, js, timeout):
            raise playwright.TimeoutError(f"Timeout {timeout}ms exceeded.")

    with pytest.raises(
        CaptureError,
        match=r"window.__VIDEO.ready not true within 120 s \(production needs the \?video=1 "
        r"frontend deployed; use target local\)",
    ):
        asyncio.run(wait_ready(NeverReady()))


def test_a_browser_failure_is_a_capture_error_with_its_cause(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.async_api")

    async def crash(base_url, hud, actions, frames_dir):
        raise playwright.TimeoutError("Timeout 10000ms exceeded.")

    monkeypatch.setattr(platform_take, "_record", crash)
    monkeypatch.setattr(platform_take, "display_awake", nullcontext)
    spec = {
        "id": "platform-01",
        "kind": "platform",
        "target": "production",
        "actions": [{"do": "pause_rotation"}],
    }
    with pytest.raises(CaptureError, match="platform-01: Timeout 10000ms exceeded.") as err:
        record_platform(tmp_path, spec)
    assert isinstance(err.value.__cause__, playwright.TimeoutError)


def test_a_venv_without_playwright_is_a_capture_error(tmp_path, monkeypatch):
    find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *args: None if name == "playwright" else find_spec(name, *args),
    )
    spec = {
        "id": "platform-01",
        "kind": "platform",
        "target": "local",
        "actions": [{"do": "pause_rotation"}],
    }
    with pytest.raises(CaptureError, match="platform-01: Playwright is not installed in this venv"):
        record_platform(tmp_path, spec)
    assert not (tmp_path / "captures").exists()


def test_a_screencast_without_frames_is_a_capture_error(tmp_path, monkeypatch):
    pytest.importorskip("playwright")

    async def no_frames(base_url, hud, actions, frames_dir):
        # a take without cursor moves: motion_fps has nothing to measure
        return Take()

    monkeypatch.setattr(platform_take, "_record", no_frames)
    monkeypatch.setattr(platform_take, "display_awake", nullcontext)
    spec = {
        "id": "platform-01",
        "kind": "platform",
        "target": "production",
        "actions": [{"do": "pause_rotation"}],
    }
    with pytest.raises(CaptureError, match="platform-01: the screencast delivered no frames"):
        record_platform(tmp_path, spec)


class _ScreencastCdp:
    """A CDP session that emits a screencast frame, stamped now, on `frame()`; its
    Page.stopScreencast delivers one last frame before it returns."""

    def __init__(self):
        self.listeners = {}
        self.sent = []

    def on(self, event, handler):
        self.listeners.setdefault(event, []).append(handler)

    def remove_listener(self, event, handler):
        self.listeners[event].remove(handler)

    def frame(self):
        params = {
            "data": base64.b64encode(b"jpeg").decode(),
            "metadata": {"timestamp": time.time()},
            "sessionId": 1,
        }
        for handler in self.listeners.get("Page.screencastFrame", []):
            handler(params)

    async def send(self, method, params=None):
        self.sent.append(method)
        if method == "Page.stopScreencast":
            self.frame()


def _screencast_take(frames_dir, after_stop=lambda cdp: None):
    """Start a screencast on `_ScreencastCdp`, take one frame, stop it, then `after_stop(cdp)`."""
    cdp, take = _ScreencastCdp(), Take()

    async def go():
        screencast = _Screencast(cdp, take, frames_dir)
        await screencast.start()
        cdp.frame()
        await asyncio.sleep(0)
        await screencast.stop()
        after_stop(cdp)
        await asyncio.sleep(0)

    asyncio.run(go())
    return cdp, take


def test_the_take_ends_after_the_frame_that_arrives_with_the_stop(tmp_path, monkeypatch):
    """The globe renders every frame, so a frame swapped while the stop is on its way can
    arrive with the stop's response; a take that ended before it would fail the encode."""
    clock = itertools.count(100)
    monkeypatch.setattr(time, "time", lambda: float(next(clock)))
    cdp, take = _screencast_take(tmp_path)
    assert len(take.timestamps) == 2
    assert take.end_ts >= max(take.timestamps)
    assert concat_script(take.timestamps, take.end_ts, 60)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["f000000.jpg", "f000001.jpg"]
    # the last frame is written and acknowledged before stop() returns
    assert cdp.sent == [
        "Page.startScreencast",
        "Page.screencastFrameAck",
        "Page.stopScreencast",
        "Page.screencastFrameAck",
    ]


def test_a_frame_sent_after_the_stop_is_not_part_of_the_take(tmp_path):
    """Chrome can send a frame after the stop's response (measured 2026-09-29: 4 of 25
    stops); it would land while the browser closes and fail its ack there."""
    cdp, take = _screencast_take(tmp_path, after_stop=lambda cdp: cdp.frame())
    assert len(take.timestamps) == 2
    assert take.end_ts >= max(take.timestamps)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["f000000.jpg", "f000001.jpg"]
    assert cdp.sent.count("Page.screencastFrameAck") == 2
    assert cdp.listeners["Page.screencastFrame"] == []


def _drive(html, steps):
    """Run `steps(driver, page)` on a synthetic `html` page in headless Chrome at the take's viewport."""
    pytest.importorskip("playwright")
    from playwright.async_api import async_playwright

    async def go():
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page(viewport={"width": VIEWPORT[0], "height": VIEWPORT[1]})
            await page.set_content(html)
            await page.mouse.move(*START_POS)
            return await steps(_Driver(page, Take()), page)

    return asyncio.run(go())


# every click the page receives, as tag.class of its target
RECORD_CLICKS_JS = (
    "<script>window.clicks = []; document.addEventListener('click', (e) => window.clicks.push("
    "[e.target.tagName.toLowerCase(), ...e.target.classList].join('.')))</script>"
)

# 60 legend rows in a 200 px scroll list over a full-viewport globe, like the Filter
# panel's .category-legend-list (overflow-y: auto, styles/index.css)
LEGEND_PAGE = (
    "<style>body{margin:0} .globe{position:fixed;inset:0}"
    " .category-legend-list{position:fixed;left:20px;top:100px;width:300px;height:200px;"
    "overflow-y:auto} .category-legend-item{height:30px}</style>"
    "<div class='globe'></div><div class='category-legend-list'>"
    + "".join(f"<div class='category-legend-item'>Category {i}</div>" for i in range(60))
    + "</div>"
    + RECORD_CLICKS_JS
)


def test_a_click_scrolls_its_target_into_view_inside_its_list():
    # unscrolled, "Category 20" lies at y 700-730, below the list's visible rows: a click
    # at its box would hit the globe there and toggle nothing
    async def steps(driver, page):
        await driver.click_locator(driver.legend_item("category", "Category 20"), "filter")
        return await page.evaluate("window.clicks"), driver.take.marks[0][2]

    clicks, point = _drive(LEGEND_PAGE, steps)
    assert clicks == ["div.category-legend-item"]
    # the click (and its manifest event) is inside the list's visible 100-300 px
    assert 100 <= point["y"] <= 300


COVERED_PAGE = (
    "<style>body{margin:0} .globe-container{position:fixed;inset:0}"
    " .globe-container canvas{display:block;width:100%;height:100%}"
    " .toggle-btn{position:fixed;left:40px;top:40px;width:120px;height:30px}"
    " .empire-window{position:fixed;left:20px;top:20px;width:400px;height:300px}"
    " .site-hover-tooltip{position:fixed;left:880px;top:490px;width:160px;height:24px}</style>"
    "<div class='globe-container'><canvas></canvas></div>"
    "<div class='toggle-buttons'><button class='toggle-btn'>Country</button></div>"
    "<div class='empire-window'></div>"
    "<div class='site-hover-tooltip selected-site-label'>Baalbek Stones</div>" + RECORD_CLICKS_JS
)


def test_a_click_whose_target_is_covered_fails_naming_what_it_would_hit():
    async def steps(driver, page):
        # a floating window (Empire Borders) over the Filter panel's mode button
        with pytest.raises(
            CaptureError,
            match=r"^filter_mode: the click at \(100, 55\) would hit div\.empire-window, "
            r"not its target$",
        ):
            await driver.click_locator(page.locator(".toggle-btn").first, "filter_mode")
        # a measure point under the selected site's label is no click on the map
        canvas = page.locator(MAP_CANVAS)
        with pytest.raises(
            CaptureError,
            match=r"^measure_a: the click at \(900, 500\) would hit "
            r"div\.site-hover-tooltip\.selected-site-label, not its target$",
        ):
            await driver.click_at(900, 500, "measure_a", canvas)
        await driver.click_at(1500, 800, "measure_b", canvas)
        return await page.evaluate("window.clicks")

    assert _drive(COVERED_PAGE, steps) == ["canvas"]


# the Search tab's result list (FilterPanel.tsx): title left, info button right, always shown
RESULTS_PAGE = (
    "<style>body{margin:0}"
    " .search-results-list{position:fixed;left:20px;top:300px;width:400px;height:120px;"
    "overflow-y:auto} .search-result-item{display:flex;align-items:center;height:40px}"
    " .search-result-main{flex:1} .search-result-info-btn{width:32px;height:32px}</style>"
    "<button class='tab-btn active'>Search</button><div class='search-results-list'>"
    + "".join(
        "<div class='search-result-item'><div class='search-result-main'>"
        f"<div class='search-result-title'>{title}</div></div>"
        "<button class='search-result-info-btn'></button></div>"
        for title in ("Byblos", "Baalbek Stones", "Tyre")
    )
    + "</div><script>window.moves = []; window.opened = [];"
    " addEventListener('mousemove', (e) => window.moves.push([e.clientX, e.clientY]), true);"
    " document.querySelectorAll('.search-result-info-btn').forEach((b) => b.addEventListener("
    "'click', () => window.opened.push(b.parentElement.textContent)))</script>"
)


def test_open_details_moves_the_cursor_in_one_eased_path_to_the_info_button():
    # the NERV cursor follows mousemove: a hover first would jump it to the row's centre
    # (220, 360) and back, two cuts in every details moment
    async def steps(driver, page):
        await page.evaluate("window.moves = []")
        await driver.run({"do": "open_details", "title": "Baalbek Stones"})
        button = await page.locator(".search-result-info-btn").nth(1).bounding_box()
        return await page.evaluate("[window.moves, window.opened]"), button, driver.pos

    (moves, opened), button, pos = _drive(RESULTS_PAGE, steps)
    assert opened == ["Baalbek Stones"]
    end = (button["x"] + button["width"] / 2, button["y"] + button["height"] / 2)
    assert pos == pytest.approx(end)
    (x0, y0), (x1, y1) = START_POS, end
    length = math.dist(START_POS, end)
    assert len(moves) >= 5
    for x, y in moves:
        # every cursor position lies on the straight path from where it was to the button
        assert abs((x1 - x0) * (y0 - y) - (x0 - x) * (y1 - y0)) / length < 1.5
        assert min(x0, x1) - 1 <= x <= max(x0, x1) + 1


def test_the_measure_tab_count_is_read_as_the_page_writes_it():
    assert [measurement_label(n) for n in (1, 2)] == ["1 measurement", "2 measurements"]
    assert parse_measurement_count(" 3 measurements ") == 3
    with pytest.raises(CaptureError, match="not a measurement count"):
        parse_measurement_count("Click to set end point...")


# The globe's clicks as createClickHandler handles them (eventHandlers.ts): a canvas click
# acts only after a delay, and a click inside it replaces the pending one. The delay is
# 400 ms here, not the page's 250 ms, so a driver that does not wait for point a loses it
# every time instead of now and then. The Measure tab renders as FilterPanel.tsx does.
MEASURE_PAGE = """<style>body{margin:0} .globe-container{position:fixed;inset:0}
.globe-container canvas{display:block;width:100%;height:100%}
.panel{position:fixed;left:20px;top:20px;width:300px}</style>
<div class='globe-container'><canvas></canvas></div>
<div class='panel'><button class='tab-btn'>Measure</button><div class='content'></div></div>
<script>(() => {
window.measurements = []; window.takeClicks = Infinity
let current = [], active = false, pending = null, timer = null, clicks = 0
const render = () => {
  if (!active) return
  const n = window.measurements.length
  document.querySelector('.content').innerHTML = '<div class="proximity-tab-content">'
    + (current.length === 1 ? '<div class="radius-label">Click to set end point...</div>' : '')
    + (n > 0 ? `<div class="search-results-header"><span>${n} measurement${n !== 1 ? 's' : ''}`
      + '</span><button>x</button></div>' : '')
    + '</div>'
}
document.querySelector('.tab-btn').addEventListener('click', () => { active = true; render() })
document.querySelector('canvas').addEventListener('click', (e) => {
  if (++clicks > window.takeClicks) return
  pending = e
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => {
    current.push([pending.clientX, pending.clientY])
    if (current.length === 2) { window.measurements.push(current); current = [] }
    render()
  }, 400)
})
window.__DEMO = {screenPoint: (lat, lng) => ({x: 1000 + (lng - 36.2) * 1e4, y: 500 - (lat - 34) * 1e4})}
})()</script>"""


def test_each_measure_point_shows_on_the_page_before_the_cursor_moves_on(monkeypatch):
    monkeypatch.setattr(platform_take, "REGISTER_TIMEOUT_MS", 1_000)
    measure = {"do": "measure", "a": {"lat": 34.0, "lng": 36.2}, "b": {"lat": 34.01, "lng": 36.21}}

    async def steps(driver, page):
        await driver.run(measure)
        await page.wait_for_timeout(500)  # past the page's delay: no click is pending any more
        [(a, b)] = await page.evaluate("window.measurements")
        assert (a, b) == (pytest.approx([1000, 500], abs=1), pytest.approx([1100, 400], abs=1))
        # a page that never takes point b (or a): the take fails instead of filming it
        for take_clicks, message in [
            (1, r"^measure point b: the Measure tab does not show '1 measurement' within 1 s"),
            (0, r"^measure point a: the Measure tab does not show 'Click to set end point\.\.\.'"),
        ]:
            await page.set_content(MEASURE_PAGE)
            await page.evaluate(f"window.takeClicks = {take_clicks}")
            with pytest.raises(CaptureError, match=message):
                await driver.run(measure)

    _drive(MEASURE_PAGE, steps)


def _layers_page(regions):
    """The Layers panel and the Empire Borders window as the app renders and wires them
    (MapLayersPanel.tsx, HistoricalLayersSection.tsx, EmpireBordersPanel.tsx; controlled
    checkboxes, as React keeps them): "Coastlines" flips on a click; "Labels" is disabled, as
    in Mapbox mode; "Empire Borders" opens its window and is checked while an empire is
    shown. The window's "By Period" is on, its list shows the empires of the open regions
    (Mediterranean at first), and window.shown records each empire shown with the
    timeline's state at that moment. `regions`: region -> [(id, name), ...]."""
    return (
        "<style>body{margin:0} .layer-toggle-panel{position:fixed;right:20px;top:300px;width:220px}"
        " .layer-toggle{display:flex;align-items:center;height:24px}"
        " .empire-borders-window{position:fixed;left:600px;top:100px;width:280px}"
        " .region-header-compact{height:22px} .empire-row-inline{display:flex;height:24px}</style>"
        "<div class='layer-toggle-panel'>"
        "<label class='layer-toggle'><input type='checkbox'><span class='layer-label'>Coastlines"
        "</span></label><label class='layer-toggle mapbox-unavailable'><input type='checkbox'"
        " checked disabled><span class='layer-label'>Labels</span></label>"
        "<label class='layer-toggle'><input type='checkbox' id='empires'>"
        "<span class='layer-label'>Empire Borders</span></label></div>"
        "<div class='empire-borders-window' style='display:none'><div class='empire-options-row'>"
        "<label class='layer-toggle'><input type='checkbox' id='period' checked>"
        "<span class='layer-label'>By Period</span></label></div>"
        "<div class='empire-borders-list'></div></div>"
        "<script>(() => {\n"
        f"const regions = {json.dumps(regions)}\n"
        """const open = new Set(['Mediterranean']), visible = new Set()
let period = true
window.shown = []
const win = document.querySelector('.empire-borders-window')
const render = () => {
  document.getElementById('empires').checked = visible.size > 0
  document.getElementById('period').checked = period
  document.querySelector('.empire-borders-list').innerHTML = Object.entries(regions).map(
    ([region, empires]) => '<div class="empire-region-compact">'
      + `<div class="region-header-compact" data-region="${region}">`
      + `<span class="region-chevron">${open.has(region) ? '−' : '+'}</span>`
      + `<span>${region}</span></div>`
      + (open.has(region) ? empires.map(([id, name]) => '<label class="empire-row-inline">'
        + `<input type="checkbox" data-id="${id}" ${visible.has(id) ? 'checked' : ''}>`
        + `<span class="empire-name-truncated" title="${name}">${name}</span></label>`).join('') : '')
      + '</div>').join('')
}
document.getElementById('empires').addEventListener('change', () => {
  win.style.display = win.style.display === 'none' ? 'block' : 'none'
  render()
})
document.getElementById('period').addEventListener('change', (e) => { period = e.target.checked; render() })
win.addEventListener('click', (e) => {
  const header = e.target.closest('.region-header-compact')
  if (!header) return
  const region = header.dataset.region
  open.has(region) ? open.delete(region) : open.add(region)
  render()
})
win.addEventListener('change', (e) => {
  const id = e.target.dataset.id
  if (!id) return
  if (visible.has(id)) visible.delete(id)
  else { visible.add(id); window.shown.push([id, period]) }
  render()
})
render()
})()</script>"""
    )


def _regions(*ids):
    """region -> [(id, name)] of `ids` as pipeline/historical_boundaries/empire_metadata.py has them."""
    out = {}
    for empire_id in ids:
        meta = EMPIRE_METADATA[empire_id]
        out.setdefault(meta["region"], []).append((empire_id, meta["name"]))
    return out


LAYERS_PAGE = _layers_page(_regions("greek", "roman", "achaemenid", "parthian"))
LAYERS_CHECKED_JS = (
    "[...document.querySelectorAll('.layer-toggle-panel input')].map((b) => b.checked)"
)


def test_a_layer_toggle_fails_the_take_unless_its_checkbox_flips(monkeypatch):
    """Review of Task 36: the Empire Borders label only opens its window, and the old
    driver clicked it and went on, a toggle_layer event for a layer that never came on."""
    monkeypatch.setattr(platform_take, "REGISTER_TIMEOUT_MS", 1_000)

    async def steps(driver, page):
        await driver.run({"do": "toggle_layer", "label": "Coastlines"})
        on = await page.evaluate(LAYERS_CHECKED_JS)
        await driver.run({"do": "toggle_layer", "label": "Coastlines"})
        off = await page.evaluate(LAYERS_CHECKED_JS)
        for label, turn in [("Labels", "off"), ("Empire Borders", "on")]:
            # validate_actions refuses the second without an empire; the driver fails it too
            with pytest.raises(
                CaptureError,
                match=rf"^toggle_layer '{label}': its checkbox does not turn {turn} within 1 s, "
                r"so the page did not take the click$",
            ):
                await driver.run({"do": "toggle_layer", "label": label})
        return on, off, [name for _, name, _ in driver.take.marks]

    on, off, marks = _drive(LAYERS_PAGE, steps)
    assert on == [True, True, False] and off == [False, True, False]
    assert marks == ["toggle_layer"] * 4


def test_empire_borders_draws_the_named_empire_at_its_peak_extent(monkeypatch):
    """The Empire Borders moment picks its empire with the window's "By Period" timeline off:
    on, at the 500 BC the page loads with, Rome draws Latium only (take g1e, 2026-09-30)."""
    monkeypatch.setattr(platform_take, "REGISTER_TIMEOUT_MS", 1_000)
    roman = {"do": "toggle_layer", "label": "Empire Borders", "empire": "roman"}
    # Persian/Central Asia is closed when the window opens: its region opens first
    parthian = {**roman, "empire": "parthian"}

    async def steps(driver, page):
        results = []
        for action in (roman, parthian):
            await page.set_content(LAYERS_PAGE)
            driver.take.marks.clear()
            await driver.run(validate_actions([action])[0])
            results.append(
                (
                    await page.evaluate("window.shown"),
                    await page.evaluate("document.getElementById('empires').checked"),
                    await page.evaluate("document.getElementById('period').checked"),
                    [name for _, name, _ in driver.take.marks],
                )
            )
        return results

    assert _drive(LAYERS_PAGE, steps) == [
        ([["roman", False]], True, False, ["toggle_layer", "empire_timeline", "empire"]),
        (
            [["parthian", False]],
            True,
            False,
            ["toggle_layer", "empire_timeline", "empire_region", "empire"],
        ),
    ]


def test_an_empire_the_window_does_not_show_fails_the_take(monkeypatch):
    """An empire whose row does not switch on is a failed take, never a Layers panel event
    for borders that were not drawn."""
    monkeypatch.setattr(platform_take, "REGISTER_TIMEOUT_MS", 1_000)
    # every empire row's checkbox is disabled: a click on the row switches nothing
    page_html = LAYERS_PAGE.replace("${visible.has(id) ? 'checked' : ''}", "disabled")

    async def steps(driver, page):
        with pytest.raises(
            CaptureError,
            match=r"^empire 'Roman Empire': its checkbox does not turn on within 1 s",
        ):
            await driver.run({"do": "toggle_layer", "label": "Empire Borders", "empire": "roman"})
        return await page.evaluate("[window.shown, document.getElementById('empires').checked]")

    assert _drive(page_html, steps) == [[], False]


# The Layers panel in the Mapbox view as the app renders it: MapboxGlobeService.enablePrimaryMode
# marks the body, and MapLayersPanel.tsx disables the vector layers (Coastlines) and Labels. The
# panel's Maximize button stands for the first click a take makes when the panel is minimized.
MAPBOX_LAYERS_PAGE = (
    LAYERS_PAGE.replace(
        "<input type='checkbox'><span class='layer-label'>Coastlines",
        "<input type='checkbox' disabled><span class='layer-label'>Coastlines",
    ).replace(
        "<div class='layer-toggle-panel'>",
        "<div class='layer-toggle-panel'><button class='panel-minimize-btn' title='Maximize'>+"
        "</button>",
    )
    + "<script>document.body.classList.add('mapbox-primary-mode')</script>"
    + RECORD_CLICKS_JS
)
MAPBOX_VIEW_MESSAGE = (
    r"^toggle_layer '{label}' in the Mapbox view: the Layers panel's toggles are disabled "
    r"there and an empire only tints the map; put toggle_layer before the zoom$"
)
EMPIRE_STATE_JS = (
    "[window.shown, document.getElementById('empires').checked,"
    " document.querySelector('.empire-borders-window').style.display]"
)


@pytest.mark.parametrize(
    "action",
    [
        {"do": "toggle_layer", "label": "Coastlines"},
        {"do": "toggle_layer", "label": "Empire Borders", "empire": "roman"},
    ],
)
def test_a_layer_toggle_in_the_mapbox_view_fails_before_its_click(monkeypatch, action):
    """Review of Task 36: after a zoom into Mapbox, Coastlines failed with a message that blamed
    the page, and Empire Borders passed while the empire only tinted the map (take
    platform-02p). No toggle films anything there, so the take fails before any click."""
    monkeypatch.setattr(platform_take, "REGISTER_TIMEOUT_MS", 1_000)

    async def steps(driver, page):
        with pytest.raises(CaptureError, match=MAPBOX_VIEW_MESSAGE.format(label=action["label"])):
            await driver.run(validate_actions([action])[0])
        return (
            await page.evaluate("window.clicks"),
            driver.take.marks,
            driver.pos,
            await page.evaluate(EMPIRE_STATE_JS),
        )

    assert _drive(MAPBOX_LAYERS_PAGE, steps) == ([], [], START_POS, [[], False, "none"])


@pytest.mark.parametrize(
    "action",
    [
        {"do": "toggle_layer", "label": "Coastlines"},
        {"do": "toggle_layer", "label": "Empire Borders", "empire": "roman"},
    ],
)
def test_a_switch_to_the_mapbox_view_while_the_cursor_moves_fails_the_take(monkeypatch, action):
    """The page switches views a render or two after the zoom slider passes the switch point,
    so a toggle right after such a zoom can meet the globe before its move and the Mapbox view
    at its click. The take fails on the view there too, never on the checkbox the view disabled
    or with an empire picked for a tint."""
    monkeypatch.setattr(platform_take, "REGISTER_TIMEOUT_MS", 1_000)

    async def steps(driver, page):
        # the view switches with the cursor's first step towards the toggle
        await page.evaluate(
            "document.addEventListener('mousemove', () => {"
            " document.body.classList.add('mapbox-primary-mode');"
            " document.querySelector('.layer-toggle-panel input').disabled = true"
            "}, {once: true})"
        )
        with pytest.raises(CaptureError, match=MAPBOX_VIEW_MESSAGE.format(label=action["label"])):
            await driver.run(validate_actions([action])[0])
        return (
            await page.evaluate(LAYERS_CHECKED_JS),
            [name for _, name, _ in driver.take.marks],
            await page.evaluate("window.shown"),
        )

    checked, marks, shown = _drive(LAYERS_PAGE, steps)
    assert checked[0] is False and marks == ["toggle_layer"] and shown == []


def test_a_second_empire_borders_click_closes_the_window(monkeypatch):
    """Why validate_actions allows one Empire Borders toggle per take: the window stays open
    after the first, and the label toggles it (Globe.tsx `prev => !prev`), so a second one
    closes it with the first empire still drawn and picks nothing."""
    monkeypatch.setattr(platform_take, "REGISTER_TIMEOUT_MS", 1_000)
    roman = {"do": "toggle_layer", "label": "Empire Borders", "empire": "roman"}

    async def steps(driver, page):
        await driver.run(roman)
        with pytest.raises(
            CaptureError,
            match=r"^toggle_layer 'Empire Borders': the page does not show the Empire Borders "
            r"window within 1 s",
        ):
            await driver.run({**roman, "empire": "greek"})
        return await page.evaluate(
            "[window.shown, document.querySelector('.empire-borders-window').style.display]"
        )

    assert _drive(LAYERS_PAGE, steps) == [[["roman", False]], "none"]
