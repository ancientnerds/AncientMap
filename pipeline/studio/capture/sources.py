"""Source page captures for SourceViewer (spec 2026-09-26 section 4.5).

Loads the page in Chrome at 1280 CSS px wide with deviceScaleFactor 2, hides fixed and
sticky layers (cookie bars, banners, sticky headers), highlights the quote (a DOM Range
split into <mark> pieces, highlight.js) and screenshots a window of CONTEXT_PX CSS px
above and below it. The window is shot as the viewport, resized to it and scrolled
there: a full-page screenshot rasterises the whole page, and a 35,000 px Wikipedia
article took 37 s on the GPU, past Playwright's 30 s timeout (2026-09-26). The scroll
only reaches the window when the document scrolls, so highlight.js lets out every
ancestor of the highlight that clips it: our paper page scrolls .theo-page inside a
100%-tall html, body and #root with overflow hidden, and without that the window stayed
the 800 px viewport. Paywalled or login pages do not contain the quote, so the capture
fails with the advice to use a QuoteCard. The same code captures our own paper page
with its #ev-NN paragraph outlined (a second id of a paragraph is an empty span inside
it, plan B; highlight.js outlines the paragraph). The paper slug and the evidence id are
checked with the one definition of each (pipeline.studio.config.check_slug, plan C;
pipeline.lyra.theo_publishing.EVIDENCE_ID_RE, plan A's contract C9). The site's analytics
tracker is blocked (vite.ANALYTICS_URL_RE); a Playwright failure becomes a CaptureError
with its message, and the manifest's size is the size of the PNG Chromium wrote. The
page's own <title> is kept in the "page" event as a record and drawn nowhere (owner
decision 32); of the URL only the ASCII hostname is drawn (ascii_host: SourceViewer's
address bar and the credit "Source page: <host>"), so a Greek or Chinese source page
passes plan C's glyph check of the manifest's drawn strings (its glyphs.py).

Specs (kind "source")::

    {"id": "src-dai", "kind": "source", "url": "https://...", "quote": "verbatim sentence"}
    {"id": "paper-ev07", "kind": "source", "paper": "<paper slug>", "anchor": "ev-07"}

The manifest is a still with three events at t=0: "gpu" (the WebGL renderer that
proved Chrome runs on the NVIDIA, spec 4.11), "page" (url, title) and "highlight"
(box in image pixels, target "quote" or the anchor).
"""

from __future__ import annotations

import asyncio
import importlib.util
import math
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pipeline.lyra.theo_publishing import EVIDENCE_ID_RE
from pipeline.studio.capture.gpu import CHROMIUM_GPU_ARGS, RENDERER_JS, gpu_event, require_nvidia
from pipeline.studio.capture.manifest import (
    CaptureError,
    build_manifest,
    event,
    media_path,
    require_kind,
)
from pipeline.studio.capture.vite import ANALYTICS_URL_RE, PRODUCTION_URL
from pipeline.studio.config import check_slug
from pipeline.studio.errors import StudioError

VIEWPORT = (1280, 800)
DEVICE_SCALE = 2
CONTEXT_PX = 900
SETTLE_MS = 1500
NAV_TIMEOUT_MS = 45_000
MIN_QUOTE_CHARS = 12
HIGHLIGHT_JS = Path(__file__).with_name("highlight.js")
# A desktop Chrome user agent: some sources serve bots a different page.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36"
)


def source_target(spec: dict[str, Any]) -> tuple[str, str, str]:
    """(url, mode, needle) of a source spec; mode is 'quote' (a source) or 'anchor' (our paper)."""
    cid = spec.get("id")
    keys = set(spec) - {"id", "kind"}
    if keys == {"url", "quote"}:
        url = spec["url"]
        parsed = urlparse(url) if isinstance(url, str) else None
        if parsed is None or parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise CaptureError(f"{cid}: url {url!r} is not an http(s) URL")
        quote = spec["quote"]
        if not isinstance(quote, str) or len(quote.strip()) < MIN_QUOTE_CHARS:
            raise CaptureError(
                f"{cid}: quote must be at least {MIN_QUOTE_CHARS} characters of verbatim text"
            )
        return url, "quote", quote
    if keys == {"paper", "anchor"}:
        slug, anchor = spec["paper"], spec["anchor"]
        if not isinstance(slug, str):
            raise CaptureError(f"{cid}: paper {slug!r} is not a slug")
        try:
            check_slug(slug)
        except StudioError as exc:
            raise CaptureError(f"{cid}: paper {exc}") from exc
        if not isinstance(anchor, str) or not EVIDENCE_ID_RE.fullmatch(anchor):
            raise CaptureError(f"{cid}: anchor {anchor!r} is not an evidence anchor like ev-07")
        return f"{PRODUCTION_URL}/research/{slug}#{anchor}", "anchor", anchor
    raise CaptureError(
        f"{cid}: a source capture takes either url + quote or paper + anchor, got {sorted(keys)}"
    )


def clip_window(box: dict[str, float], page_height: float) -> tuple[float, float]:
    """(top, height) in CSS px of the screenshot window around the highlight."""
    top = max(0.0, box["y"] - CONTEXT_PX)
    bottom = min(page_height, box["y"] + box["h"] + CONTEXT_PX)
    if bottom <= top:
        raise CaptureError(f"empty capture window for box {box} on a {page_height}px page")
    return top, bottom - top


def ascii_host(url: str) -> str:
    """The hostname the video draws for a source page: ASCII (IDNA) without "www.", the
    same string as SourceViewer's address bar (video/src/format.ts domainOf)."""
    host = urlparse(url).hostname or ""
    return host.encode("idna").decode("ascii").removeprefix("www.")


def image_box(box: dict[str, float], top: float) -> list[float]:
    """Highlight box in pixels of the captured image."""
    return [
        box["x"] * DEVICE_SCALE,
        (box["y"] - top) * DEVICE_SCALE,
        box["w"] * DEVICE_SCALE,
        box["h"] * DEVICE_SCALE,
    ]


async def _capture(url: str, mode: str, needle: str, out: Path) -> dict[str, Any]:
    from playwright.async_api import async_playwright  # local-only dependency

    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True, args=CHROMIUM_GPU_ARGS)
        context = await browser.new_context(
            viewport={"width": VIEWPORT[0], "height": VIEWPORT[1]},
            device_scale_factor=DEVICE_SCALE,
            user_agent=USER_AGENT,
        )
        # our own paper page must not count as a visit in the site's analytics
        await context.route(ANALYTICS_URL_RE, lambda route: route.abort())
        page = await context.new_page()
        renderer = require_nvidia(await page.evaluate(RENDERER_JS), "source capture")
        await page.goto(url, wait_until="load", timeout=NAV_TIMEOUT_MS)
        await page.wait_for_timeout(SETTLE_MS)
        await page.add_script_tag(path=str(HIGHLIGHT_JS))
        await page.evaluate("() => window.__studio.hideOverlays()")
        box = await page.evaluate(
            "([mode, needle]) => window.__studio.highlight(mode, needle)", [mode, needle]
        )
        if box is None and mode == "quote":
            raise CaptureError(
                f"quote not found on {url}; paywalled or login pages cannot be captured, use a QuoteCard"
            )
        if box is None:
            raise CaptureError(f"#{needle} has no visible paragraph on {url}")
        page_height = await page.evaluate("() => document.documentElement.scrollHeight")
        top, height = clip_window(box, page_height)
        await page.set_viewport_size({"width": VIEWPORT[0], "height": math.ceil(height)})
        await page.evaluate("(y) => window.scrollTo(0, y)", top)
        await page.wait_for_timeout(SETTLE_MS)
        scrolled = await page.evaluate("() => window.scrollY")
        box = await page.evaluate("() => window.__studio.box()")
        if not (scrolled <= box["y"] and box["y"] + box["h"] <= scrolled + height):
            raise CaptureError(f"{url}: the highlight left the capture window after scrolling")
        await page.screenshot(
            path=str(out),
            type="png",
            clip={"x": 0, "y": 0, "width": VIEWPORT[0], "height": height},
        )
        title = await page.title()
        await browser.close()
    return {"box": box, "top": scrolled, "height": height, "title": title, "renderer": renderer}


def capture_source(episode_dir: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """Capture one source page (or our paper page) into captures/<id>.png and return its manifest."""
    cid = require_kind(spec, "source")
    url, mode, needle = source_target(spec)
    if importlib.util.find_spec("playwright") is None:
        raise CaptureError(
            f"{cid}: Playwright is not installed in this venv "
            "(pip install playwright, then playwright install chrome)"
        )
    from PIL import Image
    from playwright.async_api import Error as PlaywrightError  # local-only, after validation

    out = media_path(episode_dir, cid, ".png")
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        shot = asyncio.run(_capture(url, mode, needle, out))
    except PlaywrightError as exc:
        raise CaptureError(f"{cid}: {exc}") from exc
    # Chromium rounds the fractional CSS window to whole pixels its own way: measure the PNG.
    with Image.open(out) as img:
        width, height = img.size
    title = shot["title"].strip()
    # Our own paper page needs no credit. A source is credited by its ASCII host only: the
    # page's own <title> (often Greek, Hebrew, Chinese) stays a record in the page event.
    credits = [f"Source page: {ascii_host(url)}"] if mode == "quote" else []
    return build_manifest(
        episode_dir=episode_dir,
        cid=cid,
        kind="source",
        path=out,
        fps=None,
        duration_s=None,
        width=width,
        height=height,
        events=[
            gpu_event(shot["renderer"]),
            event(0, "page", url=url, title=title),
            event(
                0,
                "highlight",
                box=image_box(shot["box"], shot["top"]),
                target="quote" if mode == "quote" else needle,
            ),
        ],
        credits=credits,
    )
