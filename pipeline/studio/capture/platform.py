"""Platform moments: a real take of ancientnerds.com (spec 2026-09-26 section 4.5).

Playwright drives Chrome (headed, GPU) at 1920x1080 CSS px with deviceScaleFactor 2; the
CDP screencast delivers frames up to the display's pixel size (2880x1620 on the
workstation, measured 2026-09-26), so the renderer's virtual camera can zoom to 1.5x
and stay sharp (PlatformClip refuses more). The manifest records the real frame size
and the events' x/y in those media pixels. The page runs in
``?demo=1&video=1&hud=<scale>``: panels hidden, HUD scaled, window.__VIDEO.ready at
globe_ready (ancient-nerds-map/src/utils/videoMode.ts). The cursor is fast on purpose
(retention, owner rule): 0.25 s moves, paced against a deadline so slow CDP round trips
never stretch them, and 45 ms keystrokes. Frames and their timestamps become a constant
60 fps clip (encode.frames_to_cfr_mp4); the start of every action goes into the
manifest's events, which the renderer's virtual camera can follow. Chrome runs with the
NVIDIA flags of gpu.py, and the take proves the GPU from the page's WebGL renderer
before the first frame (spec 4.11); the renderer string is the manifest's "gpu" event.
The display is held awake meanwhile, and the site's analytics tracker is blocked, so a
take of production counts as no visit.

Spec (kind "platform")::

    {"id": "platform-01", "kind": "platform", "target": "local" | "production", "hud": 1.3,
     "actions": [{"do": "pause_rotation"},
                 {"do": "search", "q": "baalbek"},
                 {"do": "click_result", "title": "Baalbek Stones"},
                 {"do": "fly_wait", "s": 3.0},
                 {"do": "zoom", "to": 90},
                 {"do": "open_details", "title": "Baalbek Stones"},
                 {"do": "measure", "a": {"lat": .., "lng": ..}, "b": {"lat": .., "lng": ..}},
                 {"do": "toggle_layer", "label": "Empire Borders"},
                 {"do": "proximity", "at": {"lat": .., "lng": ..}},
                 {"do": "filter", "mode": "country" | "category" | "source", "label": ".."},
                 {"do": "wait", "s": 1.0}]}

"hud" is optional (default 1.3, 0.5..2 as the page accepts). "zoom" scrolls the mouse
wheel at the centre of the view (the flown-to site) until the zoom slider reads "to"
percent; the app switches to Mapbox on its own. Measure and proximity points are clicked
where the page itself draws them (window.__DEMO.screenPoint), on the globe or on
Mapbox; measure points closer than MIN_MEASURE_GAP_PX on screen refuse the take.
"open_details" returns to the Search tab first (the result list shows only there).
"filter" clicks the Filter panel's mode button, then the legend entry named "label" (a
click toggles it). "toggle_layer" never takes the Satellite base map, in any case (owner
correction 2026-09-26: no satellite toggle in globe sections; satellite shows in the
details page or a Mapbox take): validate_actions refuses it before anything starts.
Playwright is a local-only dependency (in no requirements file); it is imported inside
the take, after the spec is validated, and a venv without it is a CaptureError.
"""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import math
import re
import shutil
import subprocess
import time
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from pipeline.studio.capture.encode import frames_to_cfr_mp4
from pipeline.studio.capture.gpu import CHROMIUM_GPU_ARGS, RENDERER_JS, gpu_event, require_nvidia
from pipeline.studio.capture.manifest import (
    CREDIT_MAPBOX_STREETS,
    CaptureError,
    as_int,
    as_number,
    build_manifest,
    event,
    media_path,
    require_kind,
    tool_failure,
)
from pipeline.studio.capture.vite import (
    ANALYTICS_URL_RE,
    PRODUCTION_URL,
    display_awake,
    local_site,
)
from pipeline.utils.geo import is_valid_coordinates

VIEWPORT = (1920, 1080)
DEVICE_SCALE = 2
FPS = 60
HUD_SCALE = 1.3
# videoMode.ts HUD_MIN..HUD_MAX: outside it the page throws and never gets ready.
HUD_RANGE = (0.5, 2.0)
MOVE_S = 0.25
KEY_DELAY_MS = 45
LEAD_S = 0.5
TAIL_S = 0.6
MAX_TAKE_S = 30.0
# Frames per second the screencast must deliver while the cursor moves, or the fast cursor stutters.
MIN_MOTION_FPS = 24.0
READY_TIMEOUT_MS = 120_000
READY_JS = (
    "() => !!(window.__VIDEO && window.__VIDEO.ready && window.__DEMO"
    " && window.__DEMO.isReady && window.__DEMO.isReady())"
)
# Closer on screen, two measure clicks measure nothing a viewer can read.
MIN_MEASURE_GAP_PX = 60.0
ZOOM_WHEEL_PX = 100
ZOOM_STEP_S = 0.05
ZOOM_TIMEOUT_S = 8.0
START_POS = (620.0, 220.0)
CURSOR_JS = Path(__file__).with_name("nerv_cursor.js")
CHROME_ARGS = [
    *CHROMIUM_GPU_ARGS,
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--window-size=1940,1200",
]
CREDITS = [CREDIT_MAPBOX_STREETS]
# Filter panel modes with legend entries (FilterPanel.tsx; "age" is a range slider).
FILTER_BUTTONS = {"country": "Country", "category": "Category", "source": "Source"}
# The Layers panel's base-map toggle (MapLayersPanel.tsx) a take must never click: owner
# correction 2026-09-26, no satellite toggle in globe sections.
SATELLITE_LAYER = "satellite"

# action -> required keys (besides "do")
ACTIONS: dict[str, frozenset[str]] = {
    "pause_rotation": frozenset(),
    "search": frozenset({"q"}),
    "click_result": frozenset({"title"}),
    "fly_wait": frozenset({"s"}),
    "zoom": frozenset({"to"}),
    "open_details": frozenset({"title"}),
    "measure": frozenset({"a", "b"}),
    "toggle_layer": frozenset({"label"}),
    "proximity": frozenset({"at"}),
    "filter": frozenset({"mode", "label"}),
    "wait": frozenset({"s"}),
}


def _point(value: Any, where: str) -> dict[str, float]:
    if not isinstance(value, dict) or set(value) != {"lat", "lng"}:
        raise CaptureError(f"{where} must be {{'lat': .., 'lng': ..}}, got {value!r}")
    lat, lng = as_number(value["lat"], f"{where}.lat"), as_number(value["lng"], f"{where}.lng")
    if not is_valid_coordinates(lat, lng):
        raise CaptureError(f"{where}: ({lat}, {lng}) is not a coordinate")
    return {"lat": lat, "lng": lng}


def validate_actions(actions: Any) -> list[dict[str, Any]]:
    """Check the declarative action list; the planned waits must fit MAX_TAKE_S."""
    if not isinstance(actions, list) or not actions:
        raise CaptureError("a platform take needs a non-empty action list")
    out: list[dict[str, Any]] = []
    waits = 0.0
    for i, action in enumerate(actions):
        where = f"actions[{i}]"
        if not isinstance(action, dict) or action.get("do") not in ACTIONS:
            raise CaptureError(f"{where}: unknown action {action!r} (known: {sorted(ACTIONS)})")
        do = action["do"]
        keys = set(action) - {"do"}
        if keys != ACTIONS[do]:
            raise CaptureError(
                f"{where} ({do}) needs exactly {sorted(ACTIONS[do])}, got {sorted(keys)}"
            )
        clean: dict[str, Any] = {"do": do}
        for key in ("q", "title", "label"):
            if key in keys:
                if not isinstance(action[key], str) or not action[key].strip():
                    raise CaptureError(f"{where}.{key} must be a non-empty string")
                clean[key] = action[key]
        if do == "toggle_layer" and action["label"].strip().casefold() == SATELLITE_LAYER:
            raise CaptureError(
                f"{where}: no satellite toggle in globe sections (owner 2026-09-26): "
                "satellite shows in the details page or a Mapbox take"
            )
        if "s" in keys:
            s = as_number(action["s"], f"{where}.s")
            if not 0 < s <= 10:
                raise CaptureError(f"{where}.s must be in (0, 10], got {s}")
            clean["s"] = s
            waits += s
        if do == "zoom":
            to = as_int(action["to"], f"{where}.to")
            if not 0 <= to <= 100:
                raise CaptureError(f"{where}.to must be a zoom-slider percent 0..100, got {to}")
            clean["to"] = to
        if do == "measure":
            clean["a"] = _point(action["a"], f"{where}.a")
            clean["b"] = _point(action["b"], f"{where}.b")
        if do == "proximity":
            clean["at"] = _point(action["at"], f"{where}.at")
        if do == "filter":
            if action["mode"] not in FILTER_BUTTONS:
                raise CaptureError(
                    f"{where}.mode must be one of {sorted(FILTER_BUTTONS)}, got {action['mode']!r}"
                )
            clean["mode"] = action["mode"]
        out.append(clean)
    if waits > MAX_TAKE_S:
        raise CaptureError(
            f"planned waits of {waits:.1f} s exceed the {MAX_TAKE_S:.0f} s take limit"
        )
    return out


def take_url(base_url: str, hud: float) -> str:
    return f"{base_url.rstrip('/')}/globe.html?{urlencode({'demo': 1, 'video': 1, 'hud': hud})}"


def eased_path(
    start: tuple[float, float], end: tuple[float, float], steps: int
) -> list[tuple[float, float]]:
    """Mouse positions for one move, ease-out cubic; the last point is `end`."""
    if steps < 1:
        raise ValueError("steps must be >= 1")
    (x0, y0), (x1, y1) = start, end
    out = []
    for i in range(1, steps + 1):
        e = 1 - (1 - i / steps) ** 3
        out.append((x0 + (x1 - x0) * e, y0 + (y1 - y0) * e))
    return out


def frame_size(frames_dir: Path) -> tuple[int, int]:
    """Pixel size of the screencast frames. Chrome caps it at the display's pixel size
    (2880x1620 on the workstation, measured 2026-09-26), so it is read, never assumed."""
    from PIL import Image

    with Image.open(frames_dir / "f000000.jpg") as first:
        return first.size


def events_from_marks(
    marks: list[tuple[float, str, dict[str, Any]]], t0: float, scale: float
) -> list[dict[str, Any]]:
    """Manifest events from the driver's marks: seconds since the first frame, x/y in media pixels."""
    return [
        event(max(0.0, t - t0), name, **{k: v * scale for k, v in extra.items()})
        for t, name, extra in marks
    ]


def motion_fps(timestamps: list[float], windows: list[tuple[float, float]]) -> float:
    """Lowest frame rate the screencast delivered during any cursor move (inf without moves)."""
    rates = []
    for start, end in windows:
        frames = sum(1 for ts in timestamps if start <= ts <= end)
        rates.append(frames / (end - start))
    return min(rates, default=float("inf"))


def screen_point_or_fail(
    point: dict[str, Any] | None, name: str, where: dict[str, float]
) -> tuple[float, float]:
    """The page's pixel for a point the take clicks; a hidden or off-screen point fails the take."""
    if point is None:
        raise CaptureError(f"{name} {where} is not on screen in this view")
    return float(point["x"]), float(point["y"])


def measure_gap_ok(a_px: tuple[float, float], b_px: tuple[float, float]) -> bool:
    """Whether two measure clicks lie at least MIN_MEASURE_GAP_PX CSS px apart."""
    return math.dist(a_px, b_px) >= MIN_MEASURE_GAP_PX


def parse_zoom_percent(text: str) -> int:
    """The zoom slider's reading ("66%", ZoomControls.tsx) as an integer percent."""
    m = re.fullmatch(r"\s*(\d{1,3})\s*%\s*", text)
    if not m:
        raise CaptureError(f"the zoom slider reads {text!r}, not a percent")
    return int(m.group(1))


async def wait_ready(page: Any) -> None:
    """Wait until the page may be filmed; a page that never gets there names the likely cause."""
    from playwright.async_api import TimeoutError as PlaywrightTimeout  # local-only dependency

    try:
        await page.wait_for_function(READY_JS, timeout=READY_TIMEOUT_MS)
    except PlaywrightTimeout as exc:
        raise CaptureError(
            f"window.__VIDEO.ready not true within {READY_TIMEOUT_MS // 1000} s (production needs "
            "the ?video=1 frontend deployed; use target local)"
        ) from exc


@dataclass
class Take:
    renderer: str = ""
    timestamps: list[float] = field(default_factory=list)
    marks: list[tuple[float, str, dict[str, Any]]] = field(default_factory=list)
    moves: list[tuple[float, float]] = field(default_factory=list)
    end_ts: float = 0.0


class _Driver:
    """Runs actions on the page with the fast NERV cursor."""

    def __init__(self, page: Any, take: Take) -> None:
        self.page = page
        self.take = take
        self.pos = START_POS

    def mark(self, name: str, **extra: Any) -> None:
        self.take.marks.append((time.time(), name, extra))

    async def move(self, x: float, y: float) -> None:
        """One eased move of MOVE_S: step k waits for its deadline, so slow round trips never add up."""
        steps = max(6, round(MOVE_S * FPS))
        start = time.time()
        for k, (px, py) in enumerate(eased_path(self.pos, (x, y), steps), start=1):
            await self.page.mouse.move(px, py)
            await asyncio.sleep(max(0.0, start + MOVE_S * k / steps - time.time()))
        self.take.moves.append((start, time.time()))
        self.pos = (x, y)

    async def click_at(self, x: float, y: float, name: str | None) -> None:
        """Move there and click; `name` marks the click as a manifest event (None: no event)."""
        if name is not None:
            self.mark(name, x=x, y=y)
        await self.move(x, y)
        await self.page.mouse.click(x, y)

    async def click_locator(self, locator: Any, name: str | None) -> None:
        await locator.wait_for(state="visible", timeout=10_000)
        box = await locator.bounding_box()
        if box is None:
            raise CaptureError(f"{name}: element has no box")
        await self.click_at(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, name)

    async def screen_point(self, name: str, where: dict[str, float]) -> tuple[float, float]:
        point = await self.page.evaluate(
            "([lat, lng]) => window.__DEMO.screenPoint(lat, lng)", [where["lat"], where["lng"]]
        )
        return screen_point_or_fail(point, name, where)

    async def search_tab(self) -> None:
        """Back to the Search tab: Measure and Proximity replace the result list (FilterPanel.tsx)."""
        tab = self.page.locator(".tab-btn", has_text="Search").first
        if "active" not in str(await tab.get_attribute("class")).split():
            await self.click_locator(tab, None)

    def result_item(self, title: str) -> Any:
        title_re = re.compile(rf"^\s*{re.escape(title)}\s*$")
        return self.page.locator(
            ".search-result-item", has=self.page.locator(".search-result-title", has_text=title_re)
        ).first

    def legend_item(self, mode: str, label: str) -> Any:
        """The Filter panel's legend entry named `label` in `mode` (FilterPanel.tsx)."""
        label_re = re.compile(rf"^\s*{re.escape(label)}\s*$")
        if mode == "country":
            # text badges and flag buttons both carry the country as their title
            return self.page.locator(".country-legend-list").get_by_title(label, exact=True).first
        if mode == "category":
            return self.page.locator(".category-legend-item", has_text=label_re).first
        return self.page.locator(
            ".source-legend-item", has=self.page.locator(".source-legend-name", has_text=label_re)
        ).first

    async def zoom_to(self, to: int) -> None:
        """Wheel at the centre of the view (the flown-to site) until the zoom slider reads `to` %."""
        cx, cy = VIEWPORT[0] / 2, VIEWPORT[1] / 2
        self.mark("zoom", x=cx, y=cy)
        await self.move(cx, cy)
        display = self.page.locator(".zoom-slider-top .zoom-percent-display")
        current = parse_zoom_percent(await display.inner_text())
        step = -ZOOM_WHEEL_PX if current < to else ZOOM_WHEEL_PX  # a negative deltaY zooms in
        deadline = time.monotonic() + ZOOM_TIMEOUT_S
        while current < to if step < 0 else current > to:
            if time.monotonic() > deadline:
                raise CaptureError(
                    f"zoom: the slider reads {current} %, not {to} %, after {ZOOM_TIMEOUT_S:.0f} s"
                )
            await self.page.mouse.wheel(0, step)
            await asyncio.sleep(ZOOM_STEP_S)
            current = parse_zoom_percent(await display.inner_text())

    async def run(self, action: dict[str, Any]) -> None:
        do = action["do"]
        page = self.page
        if do == "pause_rotation":
            self.mark(do)
            await page.evaluate("window.__DEMO.setAutoRotate(false)")
        elif do == "search":
            await self.click_locator(page.locator("input.search-input"), do)
            await page.keyboard.type(action["q"], delay=KEY_DELAY_MS)
        elif do == "click_result":
            await self.click_locator(
                self.result_item(action["title"]).locator(".search-result-main"), do
            )
        elif do == "zoom":
            await self.zoom_to(action["to"])
        elif do == "open_details":
            await self.search_tab()
            item = self.result_item(action["title"])
            await item.hover()
            await self.click_locator(item.locator(".search-result-info-btn"), do)
        elif do == "measure":
            await self.click_locator(page.locator(".tab-btn", has_text="Measure"), do)
            a = await self.screen_point("measure point a", action["a"])
            b = await self.screen_point("measure point b", action["b"])
            if not measure_gap_ok(a, b):
                raise CaptureError(
                    f"measure points a and b are {math.dist(a, b):.0f} px apart on screen; "
                    "zoom in first"
                )
            await self.click_at(*a, "measure_a")
            await self.click_at(*b, "measure_b")
        elif do == "toggle_layer":
            expand = page.locator('.layer-toggle-panel .panel-minimize-btn[title="Maximize"]')
            if await expand.count():
                await self.click_locator(expand.first, "expand_layers")
            label_re = re.compile(rf"^\s*{re.escape(action['label'])}\s*$")
            toggle = page.locator(
                ".layer-toggle-panel label.layer-toggle",
                has=page.locator(".layer-label", has_text=label_re),
            ).first
            await self.click_locator(toggle, do)
        elif do == "proximity":
            await self.click_locator(page.locator(".tab-btn", has_text="Proximity"), do)
            await self.click_locator(page.locator(".proximity-btn.set-on-globe"), None)
            x, y = await self.screen_point("proximity centre", action["at"])
            await self.click_at(x, y, "proximity_center")
        elif do == "filter":
            mode_button = page.locator(
                ".toggle-buttons .toggle-btn", has_text=FILTER_BUTTONS[action["mode"]]
            )
            await self.click_locator(mode_button.first, "filter_mode")
            await self.click_locator(self.legend_item(action["mode"], action["label"]), do)
        elif do in ("fly_wait", "wait"):
            self.mark(do)
            await asyncio.sleep(action["s"])
        else:
            raise CaptureError(f"unhandled action {do}")


async def _record(
    base_url: str, hud: float, actions: list[dict[str, Any]], frames_dir: Path
) -> Take:
    from playwright.async_api import async_playwright  # local-only dependency

    take = Take()
    pending: set[asyncio.Future[None]] = set()
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=False, args=CHROME_ARGS)
        context = await browser.new_context(
            viewport={"width": VIEWPORT[0], "height": VIEWPORT[1]}, device_scale_factor=DEVICE_SCALE
        )
        await context.add_init_script(path=str(CURSOR_JS))
        # a take of production must not count as a visit in the site's analytics
        await context.route(ANALYTICS_URL_RE, lambda route: route.abort())
        page = await context.new_page()
        await page.goto(take_url(base_url, hud), wait_until="load", timeout=90_000)
        await wait_ready(page)
        take.renderer = require_nvidia(await page.evaluate(RENDERER_JS), "platform take")
        cdp = await context.new_cdp_session(page)

        async def on_frame(params: dict[str, Any]) -> None:
            index = len(take.timestamps)
            (frames_dir / f"f{index:06d}.jpg").write_bytes(base64.b64decode(params["data"]))
            take.timestamps.append(float(params["metadata"]["timestamp"]))
            await cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})

        def handler(params: dict[str, Any]) -> None:
            task = asyncio.ensure_future(on_frame(params))
            pending.add(task)
            task.add_done_callback(pending.discard)

        cdp.on("Page.screencastFrame", handler)
        driver = _Driver(page, take)
        await page.mouse.move(*START_POS)
        await cdp.send(
            "Page.startScreencast",
            {
                "format": "jpeg",
                "quality": 80,
                "maxWidth": VIEWPORT[0] * DEVICE_SCALE,
                "maxHeight": VIEWPORT[1] * DEVICE_SCALE,
                "everyNthFrame": 1,
            },
        )
        await asyncio.sleep(LEAD_S)
        for action in actions:
            await driver.run(action)
        await asyncio.sleep(TAIL_S)
        take.end_ts = time.time()
        await cdp.send("Page.stopScreencast")
        await asyncio.gather(*pending)
        await browser.close()
    return take


def record_platform(episode_dir: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """Record one platform take into captures/<id>.mp4 and return its manifest."""
    cid = require_kind(spec, "platform")
    if spec.get("target") not in ("local", "production"):
        raise CaptureError(
            f"{cid}: target must be 'local' or 'production', got {spec.get('target')!r}"
        )
    unknown = set(spec) - {"id", "kind", "target", "hud", "actions"}
    if unknown:
        raise CaptureError(f"{cid}: unknown keys {sorted(unknown)}")
    actions = validate_actions(spec.get("actions"))
    hud = as_number(spec.get("hud", HUD_SCALE), f"{cid}: hud")
    if not HUD_RANGE[0] <= hud <= HUD_RANGE[1]:
        raise CaptureError(
            f"{cid}: hud {hud} outside {HUD_RANGE[0]}..{HUD_RANGE[1]} (the page refuses it)"
        )
    if importlib.util.find_spec("playwright") is None:
        raise CaptureError(
            f"{cid}: Playwright is not installed in this venv "
            "(pip install playwright, then playwright install chrome)"
        )
    from playwright.async_api import Error as PlaywrightError  # local-only, after validation

    frames_dir = media_path(episode_dir, cid, ".frames")
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)
    site = (
        local_site(media_path(episode_dir, cid, ".vite.log"))
        if spec["target"] == "local"
        else nullcontext(PRODUCTION_URL)
    )
    with display_awake(), site as base_url:
        try:
            take = asyncio.run(_record(base_url, hud, actions, frames_dir))
        except PlaywrightError as exc:
            raise CaptureError(f"{cid}: {exc}") from exc
    if not take.timestamps:
        raise CaptureError(f"{cid}: the screencast delivered no frames")
    smooth = motion_fps(take.timestamps, take.moves)
    if smooth < MIN_MOTION_FPS:
        raise CaptureError(
            f"{cid}: the screencast delivered {smooth:.1f} frames/s while the cursor moved "
            f"(< {MIN_MOTION_FPS}); the take would stutter"
        )
    width, height = frame_size(frames_dir)
    out = media_path(episode_dir, cid, ".mp4")
    try:
        duration = frames_to_cfr_mp4(frames_dir, take.timestamps, take.end_ts, out, FPS)
    except subprocess.CalledProcessError as exc:
        raise tool_failure(cid, exc) from exc
    shutil.rmtree(frames_dir)
    return build_manifest(
        episode_dir=episode_dir,
        cid=cid,
        kind="platform",
        path=out,
        fps=FPS,
        duration_s=duration,
        width=width,
        height=height,
        events=[
            gpu_event(take.renderer),
            *events_from_marks(take.marks, min(take.timestamps), width / VIEWPORT[0]),
        ],
        credits=CREDITS,
    )
