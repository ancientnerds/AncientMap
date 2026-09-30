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
                 {"do": "toggle_layer", "label": "Coastlines"},
                 {"do": "toggle_layer", "label": "Empire Borders", "empire": "roman"},
                 {"do": "zoom", "to": 90},
                 {"do": "open_details", "title": "Baalbek Stones"},
                 {"do": "measure", "a": {"lat": .., "lng": ..}, "b": {"lat": .., "lng": ..}},
                 {"do": "proximity", "at": {"lat": .., "lng": ..}},
                 {"do": "filter", "mode": "country" | "category" | "source", "label": ".."},
                 {"do": "wait", "s": 1.0}]}

"hud" is optional (default 1.3, 0.5..2 as the page accepts). "zoom" scrolls the mouse
wheel at the centre of the view (the flown-to site) until the zoom slider reads "to"
percent; the app switches to Mapbox on its own. Measure and proximity points are clicked
where the page itself draws them (window.__DEMO.screenPoint), on the globe or on
Mapbox; measure points closer than MIN_MEASURE_GAP_PX on screen refuse the take.
Every click scrolls its target into view first (Playwright's "visible" says nothing about
a scroll container, and the Filter panel's legends and the result list scroll) and lands
only where document.elementFromPoint hits that target, for measure and proximity the
globe's or Mapbox's canvas: anything in the way (a floating window, a label, the edge of
the viewport) fails the take, naming what the click would hit. The globe acts on a
canvas click only 250 ms later (it waits for a double click, and a second click in that
time replaces the first), so each measure point must show in the Measure tab before the
cursor moves on, and point b must add exactly one measurement.
"open_details" returns to the Search tab first (the result list shows only there).
"filter" clicks the Filter panel's mode button, then the legend entry named "label" (a
click toggles it). "toggle_layer" clicks a Layers panel toggle, and the take fails unless
its checkbox flips (a toggle the page disables switches nothing). Every toggle_layer
belongs before the zoom into the Mapbox view: there the Layers panel disables its vector
layers and Labels, and an empire only tints the map, its border far off-screen, so a
toggle_layer in the Mapbox view (MAPBOX_VIEW) fails the take before its click. The view
switches a render or two after a zoom passes the switch point, so it is checked again right
before each click of the toggle (the Empire Borders window's too), when a step of it does not
show, and once the page shows the layer. It never
takes the Satellite base map, in any case (owner correction 2026-09-26: no satellite
toggle in globe sections; satellite shows in the details page or a Mapbox take). The
Historical Layers toggles only open a picker window; their checkbox is on once something
in it is drawn (HistoricalLayersSection.tsx). So "Empire Borders" needs the "empire" to
show (an id of pipeline/historical_boundaries/empire_metadata.py): the take picks it in
that window at its peak extent, the window's "By Period" timeline off first (on, at the
500 BC it loads with, Rome draws Latium only), and fails unless the empire's checkbox and
then the Layers panel's are on. A take shows at most one empire: the window stays open,
and a second click on "Empire Borders" closes it (Globe.tsx). "Geological Layers" and
"Historical Routes" have no picker action. validate_actions refuses a satellite toggle, a
picker without its pick, an empire on any other toggle and a second Empire Borders toggle
before anything starts. Plan D's cross-stream requests 3 and 9 hand this contract to
STUDIO.md and the studio-video skill.
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

from pipeline.historical_boundaries.empire_metadata import EMPIRE_METADATA
from pipeline.studio.capture.encode import frame_size, frames_to_cfr_mp4
from pipeline.studio.capture.gpu import CHROMIUM_GPU_ARGS, RENDERER_JS, gpu_event, require_nvidia
from pipeline.studio.capture.manifest import (
    CREDIT_MAPBOX_STREETS,
    CaptureError,
    as_coordinates,
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
# The maps a measure or proximity click must land on: the Three.js globe's canvas
# (sceneInit.ts appends it to .globe-container) and Mapbox's, on top in mapbox-primary-mode
# (styles/index.css); the one not in front takes no pointer events.
MAP_CANVAS = ".globe-container > canvas, .mapbox-globe-container canvas.mapboxgl-canvas"
# Given a locator's elements: null when the topmost element at (x, y) is one of them or
# inside one, else what is hit ("nothing" off the viewport). elementFromPoint skips
# pointer-events:none, so the NERV cursor never counts.
HIT_JS = r"""(targets, [x, y]) => {
  const hit = document.elementFromPoint(x, y)
  if (hit !== null && targets.some((el) => el.contains(hit))) return null
  if (hit === null) return 'nothing'
  const classes = (hit.getAttribute('class') || '').trim().split(/\s+/).filter(Boolean)
  return [hit.tagName.toLowerCase(), ...classes].join('.')
}"""
# The globe acts on a canvas click only 250 ms later, waiting for a double click, and a
# click inside that time replaces the pending one (createClickHandler in
# ancient-nerds-map/src/components/Globe/rendering/eventHandlers.ts; Mapbox acts at once).
# So a measure point counts once the Measure tab (FilterPanel.tsx) shows it: point a as
# the end-point hint, point b as one more measurement in the tab's count.
REGISTER_TIMEOUT_MS = 2_000
MEASURE_HINT = ".proximity-tab-content .radius-label"
MEASURE_HINT_TEXT = "Click to set end point..."
MEASURE_COUNT = ".proximity-tab-content .search-results-header > span"
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
# The Historical Layers toggles (HistoricalLayersSection.tsx) only open a picker window;
# their checkbox is on once something in it is drawn (Empire Borders: visibleEmpires.size >
# 0). A take picks an empire (EmpireBordersPanel.tsx), nothing picks a geological layer or
# a route. Compared case-folded, like SATELLITE_LAYER.
EMPIRE_LAYER = "empire borders"
PICKER_LAYERS = frozenset({"geological layers", "historical routes"})
EMPIRE_WINDOW = ".empire-borders-window"
CHECKBOX = 'input[type="checkbox"]'
# The page's mark of the Mapbox view (MapboxGlobeService.enablePrimaryMode, once the zoom
# slider passes the switch point). There no toggle_layer films anything: the Layers panel
# disables its vector layers and Labels (MapLayersPanel.tsx), and an empire's fill only tints
# the map while its border lies hundreds of km off-screen (take platform-02p, 2026-09-30).
MAPBOX_VIEW = "body.mapbox-primary-mode"

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
# action -> keys it may carry besides the required ones
OPTIONAL: dict[str, frozenset[str]] = {"toggle_layer": frozenset({"empire"})}


def exact_text(text: str) -> re.Pattern[str]:
    """Matches an element whose whole text is `text` (surrounding whitespace aside)."""
    return re.compile(rf"^\s*{re.escape(text)}\s*$")


def _toggle_layer(action: dict[str, Any], where: str) -> dict[str, Any]:
    """The toggle_layer rules: no satellite, no picker window without its pick."""
    layer = action["label"].strip().casefold()
    if layer == SATELLITE_LAYER:
        raise CaptureError(
            f"{where}: no satellite toggle in globe sections (owner 2026-09-26): "
            "satellite shows in the details page or a Mapbox take"
        )
    if layer in PICKER_LAYERS:
        raise CaptureError(
            f"{where}: {action['label']!r} only opens its picker window and no action picks "
            "from it, so its checkbox would switch nothing on"
        )
    if layer != EMPIRE_LAYER:
        if "empire" in action:
            raise CaptureError(
                f"{where}: only 'Empire Borders' takes an empire, not {action['label']!r}"
            )
        return {}
    if "empire" not in action:
        raise CaptureError(
            f"{where}: 'Empire Borders' only opens its window; name the empire to show "
            '("empire": an id of pipeline/historical_boundaries/empire_metadata.py)'
        )
    empire = action["empire"]
    if not isinstance(empire, str) or empire not in EMPIRE_METADATA:
        raise CaptureError(
            f"{where}.empire must be an empire id of "
            f"pipeline/historical_boundaries/empire_metadata.py, got {empire!r}"
        )
    return {"empire": empire}


def _point(value: Any, where: str) -> dict[str, float]:
    if not isinstance(value, dict) or set(value) != {"lat", "lng"}:
        raise CaptureError(f"{where} must be {{'lat': .., 'lng': ..}}, got {value!r}")
    lat, lng = as_coordinates(value, where)
    return {"lat": lat, "lng": lng}


def validate_actions(actions: Any) -> list[dict[str, Any]]:
    """Check the declarative action list; the planned waits must fit MAX_TAKE_S."""
    if not isinstance(actions, list) or not actions:
        raise CaptureError("a platform take needs a non-empty action list")
    out: list[dict[str, Any]] = []
    waits = 0.0
    empire_at: str | None = None
    for i, action in enumerate(actions):
        where = f"actions[{i}]"
        if not isinstance(action, dict) or action.get("do") not in ACTIONS:
            raise CaptureError(f"{where}: unknown action {action!r} (known: {sorted(ACTIONS)})")
        do = action["do"]
        keys = set(action) - {"do"}
        optional = OPTIONAL.get(do, frozenset())
        if not ACTIONS[do] <= keys <= ACTIONS[do] | optional:
            may = f" (optional {sorted(optional)})" if optional else ""
            raise CaptureError(
                f"{where} ({do}) needs exactly {sorted(ACTIONS[do])}{may}, got {sorted(keys)}"
            )
        clean: dict[str, Any] = {"do": do}
        for key in ("q", "title", "label"):
            if key in keys:
                if not isinstance(action[key], str) or not action[key].strip():
                    raise CaptureError(f"{where}.{key} must be a non-empty string")
                clean[key] = action[key]
        if do == "toggle_layer":
            clean.update(_toggle_layer(action, where))
            if "empire" in clean:
                if empire_at is not None:
                    raise CaptureError(
                        f"{where}: a take shows at most one empire: 'Empire Borders' at "
                        f"{empire_at} opened its window, and a second click closes it"
                    )
                empire_at = where
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


def measurement_label(count: int) -> str:
    """The Measure tab's count as FilterPanel.tsx writes it ("1 measurement", "2 measurements")."""
    return f"{count} measurement{'' if count == 1 else 's'}"


def parse_measurement_count(text: str) -> int:
    """The Measure tab's count ("1 measurement", "3 measurements") as an integer."""
    m = re.fullmatch(r"\s*(\d+) measurements?\s*", text)
    if not m:
        raise CaptureError(f"the Measure tab reads {text!r}, not a measurement count")
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
        # The toggle_layer running now (its `what`): the view is checked right before each of
        # its clicks and when the page does not show one of its steps (on_the_globe).
        self.toggling: str | None = None

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

    async def click_at(
        self, x: float, y: float, name: str, target: Any, *, event: bool = True
    ) -> None:
        """Move there and click, once the point hits `target` (a locator); a click named
        `name` fails the take when anything else is in the way, and a click of a
        toggle_layer when the view switched to Mapbox meanwhile. `event` marks the click
        as a manifest event."""
        if event:
            self.mark(name, x=x, y=y)
        await self.move(x, y)
        hit = await target.evaluate_all(HIT_JS, [x, y])
        if hit is not None:
            raise CaptureError(
                f"{name}: the click at ({x:.0f}, {y:.0f}) would hit {hit}, not its target"
            )
        if self.toggling is not None:
            await self.on_the_globe(self.toggling)
        await self.page.mouse.click(x, y)

    async def click_locator(self, locator: Any, name: str, *, event: bool = True) -> None:
        """Click the centre of `locator`, scrolled into view first: Playwright's "visible"
        does not mean inside its scroll container (the legends and the result list scroll)."""
        await locator.wait_for(state="visible", timeout=10_000)
        await locator.scroll_into_view_if_needed(timeout=10_000)
        box = await locator.bounding_box()
        if box is None:
            raise CaptureError(f"{name}: element has no box")
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        await self.click_at(x, y, name, locator, event=event)

    async def measurement_count(self) -> int:
        """Measurements on the page; the Measure tab shows the count once there is one."""
        label = self.page.locator(MEASURE_COUNT)
        if not await label.count():
            return 0
        return parse_measurement_count(await label.inner_text())

    async def registered(self, state: Any, what: str, missing: str) -> None:
        """Wait until the page shows `state` (a locator) after the click `what`, or fail
        with `missing` (what the page does not show). During a toggle_layer a switch to the
        Mapbox view is named as the reason instead: it disables the checkboxes."""
        from playwright.async_api import TimeoutError as PlaywrightTimeout  # local-only dependency

        try:
            await state.wait_for(state="visible", timeout=REGISTER_TIMEOUT_MS)
        except PlaywrightTimeout as exc:
            if self.toggling is not None:
                await self.on_the_globe(self.toggling)
            raise CaptureError(
                f"{what}: {missing} within {REGISTER_TIMEOUT_MS / 1000:g} s, "
                "so the page did not take the click"
            ) from exc

    async def switched(self, toggle: Any, on: bool, what: str) -> None:
        """Wait until the checkbox in `toggle` (a label locator) is `on` after the click
        `what`, or fail: a click that switches nothing films a moment that never happened."""
        box = toggle.locator(f"{CHECKBOX}{':checked' if on else ':not(:checked)'}")
        await self.registered(box, what, f"its checkbox does not turn {'on' if on else 'off'}")

    async def on_the_globe(self, what: str) -> None:
        """Fail the toggle `what` when the page shows the Mapbox view (MAPBOX_VIEW)."""
        if await self.page.locator(MAPBOX_VIEW).count():
            raise CaptureError(
                f"{what} in the Mapbox view: the Layers panel's toggles are disabled there and "
                "an empire only tints the map; put toggle_layer before the zoom"
            )

    async def show_empire(self, empire: str) -> None:
        """Pick `empire` in the open Empire Borders window (EmpireBordersPanel.tsx) at its peak
        extent: its "By Period" timeline goes off first (on, at the 500 BC it loads with, the
        empire takes that year's borders, Rome Latium only, or none), and the empire's region
        opens if it is closed."""
        page = self.page
        name, region_name = EMPIRE_METADATA[empire]["name"], EMPIRE_METADATA[empire]["region"]
        window = page.locator(EMPIRE_WINDOW)
        await self.registered(
            window,
            "toggle_layer 'Empire Borders'",
            "the page does not show the Empire Borders window",
        )
        period = window.locator(
            "label.layer-toggle", has=page.locator(".layer-label", has_text=exact_text("By Period"))
        )
        if await period.locator(CHECKBOX).is_checked(timeout=10_000):
            await self.click_locator(period, "empire_timeline")
            await self.switched(period, False, "the Empire Borders window's 'By Period'")
        header = page.locator(
            ".region-header-compact > span:not(.region-chevron)", has_text=exact_text(region_name)
        )
        region = window.locator(".empire-region-compact", has=header)
        row = region.locator(
            "label.empire-row-inline",
            has=page.locator(".empire-name-truncated", has_text=exact_text(name)),
        )
        if not await row.count():
            await self.click_locator(region.locator(".region-header-compact"), "empire_region")
        await self.click_locator(row, "empire")
        await self.switched(row, True, f"empire {name!r}")

    async def toggle_layer(self, action: dict[str, Any]) -> None:
        """Click the Layers panel toggle `action["label"]` and wait until the page shows it:
        its checkbox flips, or for Empire Borders the named empire is drawn (show_empire)
        and the panel's checkbox is on."""
        page = self.page
        what = f"toggle_layer {action['label']!r}"
        expand = page.locator('.layer-toggle-panel .panel-minimize-btn[title="Maximize"]')
        if await expand.count():
            await self.click_locator(expand.first, "expand_layers")
        toggle = page.locator(
            ".layer-toggle-panel label.layer-toggle",
            has=page.locator(".layer-label", has_text=exact_text(action["label"])),
        ).first
        if "empire" in action:
            # the click opens the window; the checkbox turns on with the empire drawn
            await self.click_locator(toggle, "toggle_layer")
            await self.show_empire(action["empire"])
            await self.switched(toggle, True, f"{what} in the Layers panel")
        else:
            on = await toggle.locator(CHECKBOX).is_checked(timeout=10_000)
            await self.click_locator(toggle, "toggle_layer")
            await self.switched(toggle, not on, what)

    async def screen_point(self, name: str, where: dict[str, float]) -> tuple[float, float]:
        point = await self.page.evaluate(
            "([lat, lng]) => window.__DEMO.screenPoint(lat, lng)", [where["lat"], where["lng"]]
        )
        return screen_point_or_fail(point, name, where)

    async def search_tab(self) -> None:
        """Back to the Search tab: Measure and Proximity replace the result list (FilterPanel.tsx)."""
        tab = self.page.locator(".tab-btn", has_text="Search").first
        if "active" not in str(await tab.get_attribute("class")).split():
            await self.click_locator(tab, "search_tab", event=False)

    def result_item(self, title: str) -> Any:
        return self.page.locator(
            ".search-result-item",
            has=self.page.locator(".search-result-title", has_text=exact_text(title)),
        ).first

    def legend_item(self, mode: str, label: str) -> Any:
        """The Filter panel's legend entry named `label` in `mode` (FilterPanel.tsx)."""
        label_re = exact_text(label)
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
            # the info button always shows (styles/index.css), so no hover first: Playwright's
            # hover would jump the cursor in one step and leave self.pos behind
            info = self.result_item(action["title"]).locator(".search-result-info-btn")
            await self.click_locator(info, do)
        elif do == "measure":
            await self.click_locator(page.locator(".tab-btn", has_text="Measure"), do)
            a = await self.screen_point("measure point a", action["a"])
            b = await self.screen_point("measure point b", action["b"])
            if not measure_gap_ok(a, b):
                raise CaptureError(
                    f"measure points a and b are {math.dist(a, b):.0f} px apart on screen; "
                    "zoom in first"
                )
            before = await self.measurement_count()
            await self.click_at(*a, "measure_a", page.locator(MAP_CANVAS))
            hint = page.locator(MEASURE_HINT, has_text=MEASURE_HINT_TEXT)
            await self.registered(
                hint, "measure point a", f"the Measure tab does not show {MEASURE_HINT_TEXT!r}"
            )
            await self.click_at(*b, "measure_b", page.locator(MAP_CANVAS))
            label = measurement_label(before + 1)
            count = page.locator(MEASURE_COUNT, has_text=exact_text(label))
            await self.registered(
                count, "measure point b", f"the Measure tab does not show {label!r}"
            )
        elif do == "toggle_layer":
            what = f"toggle_layer {action['label']!r}"
            await self.on_the_globe(what)  # before the cursor moves
            # The view switches a render or two after the zoom slider passes the switch point,
            # so right after such a zoom it can arrive at any step of the toggle: the view is
            # checked right before each click (click_at), when a step does not show
            # (registered) and once the page shows the layer.
            self.toggling = what
            try:
                await self.toggle_layer(action)
                await self.on_the_globe(what)
            finally:
                self.toggling = None
        elif do == "proximity":
            await self.click_locator(page.locator(".tab-btn", has_text="Proximity"), do)
            await self.click_locator(
                page.locator(".proximity-btn.set-on-globe"), "proximity_set_on_globe", event=False
            )
            x, y = await self.screen_point("proximity centre", action["at"])
            await self.click_at(x, y, "proximity_center", page.locator(MAP_CANVAS))
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


class _Screencast:
    """The page's CDP screencast: each frame lands in `frames_dir`, its timestamp in `take`.

    Every frame task is kept until the take ends: stop() fails the take when one of them
    did not land (Chrome sends the next frame only after the ack), and abandon() settles
    them when an action failed, before the browser closes under them."""

    def __init__(self, cdp: Any, take: Take, frames_dir: Path) -> None:
        self.cdp = cdp
        self.take = take
        self.frames_dir = frames_dir
        self.tasks: list[asyncio.Future[None]] = []
        cdp.on("Page.screencastFrame", self._handler)

    async def _on_frame(self, params: dict[str, Any]) -> None:
        index = len(self.take.timestamps)
        (self.frames_dir / f"f{index:06d}.jpg").write_bytes(base64.b64decode(params["data"]))
        self.take.timestamps.append(float(params["metadata"]["timestamp"]))
        await self.cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})

    def _handler(self, params: dict[str, Any]) -> None:
        self.tasks.append(asyncio.ensure_future(self._on_frame(params)))

    async def start(self) -> None:
        await self.cdp.send(
            "Page.startScreencast",
            {
                "format": "jpeg",
                "quality": 80,
                "maxWidth": VIEWPORT[0] * DEVICE_SCALE,
                "maxHeight": VIEWPORT[1] * DEVICE_SCALE,
                "everyNthFrame": 1,
            },
        )

    async def stop(self) -> None:
        """Stop and end the take. The take keeps the frames that arrived before the stop's
        response: Chrome can still send one it encoded while the stop was on its way
        (measured 2026-09-29: 4 of 25 stops), and that one would land while the browser
        closes, where its ack fails. The end comes last, once every kept frame has landed,
        because a frame can arrive with the stop's response and a take that ends before its
        last frame fails the encode (encode.concat_script). A frame that did not land (its
        file or its ack failed) fails the take."""
        await self.cdp.send("Page.stopScreencast")
        self.cdp.remove_listener("Page.screencastFrame", self._handler)
        results = await asyncio.gather(*self.tasks, return_exceptions=True)
        failed = [r for r in results if isinstance(r, BaseException)]
        if failed:
            raise CaptureError(
                f"{len(failed)} screencast frame(s) did not land: {failed[0]!r}"
            ) from failed[0]
        self.take.end_ts = time.time()

    async def abandon(self) -> None:
        """An action failed the take: no more frames, and every frame task is settled before
        the browser closes. The frames are not used, so their own failures do not matter;
        the action's error is the take's."""
        self.cdp.remove_listener("Page.screencastFrame", self._handler)
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)


async def _record(
    base_url: str, hud: float, actions: list[dict[str, Any]], frames_dir: Path
) -> Take:
    from playwright.async_api import async_playwright  # local-only dependency

    take = Take()
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
        screencast = _Screencast(await context.new_cdp_session(page), take, frames_dir)
        driver = _Driver(page, take)
        await page.mouse.move(*START_POS)
        await screencast.start()
        try:
            await asyncio.sleep(LEAD_S)
            for action in actions:
                await driver.run(action)
            await asyncio.sleep(TAIL_S)
        except BaseException:
            await screencast.abandon()
            raise
        await screencast.stop()
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
