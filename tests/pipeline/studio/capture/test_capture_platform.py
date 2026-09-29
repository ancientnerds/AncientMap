"""Planning logic of platform takes (pipeline/studio/capture/platform.py); the take needs headed
Chrome, the driver's clicks run here on small synthetic pages in headless Chrome."""

import asyncio
import importlib.util
import math
import time
import types
from contextlib import nullcontext

import pytest

from pipeline.studio.capture import platform as platform_take
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
    eased_path,
    events_from_marks,
    frame_size,
    measure_gap_ok,
    motion_fps,
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
        {"do": "toggle_layer", "label": "Empire Borders"},
        {"do": "proximity", "at": {"lat": 34.0067, "lng": 36.2033}},
        {"do": "filter", "mode": "category", "label": "Pyramid"},
        {"do": "wait", "s": 1.5},
    ]
    out = validate_actions(actions)
    assert [a["do"] for a in out] == [a["do"] for a in actions]
    assert out[3]["s"] == 3.0 and out[4]["to"] == 90
    assert out[8]["at"] == {"lat": 34.0067, "lng": 36.2033}
    assert out[9] == {"do": "filter", "mode": "category", "label": "Pyramid"}


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
    ],
)
def test_validate_rejects_bad_actions(actions, message):
    with pytest.raises(CaptureError, match=message):
        validate_actions(actions)


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
