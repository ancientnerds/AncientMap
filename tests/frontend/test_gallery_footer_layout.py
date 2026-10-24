"""The site popup's gallery footer in a real Chrome (D62, wording B).

The gallery warning's text grew from 31 to 58 characters with the beta exit. The footer
holds it beside the connector status (`.gallery-footer` in `src/styles/index.css`); jsdom has
no layout, so only a real browser shows whether the two still share the row. The page here
is the footer's markup from `SitePopup.tsx` and `ConnectorStatus.tsx` inside the popup's own
wrappers, styled by the shipped stylesheets and the self-hosted JetBrains Mono.

Like the studio's page captures, the test needs Playwright and an installed Chrome; it skips
without Playwright (CI has none, see CLAUDE.md "Local only").
"""

import asyncio
import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "ancient-nerds-map"
SITE_POPUP = FRONTEND / "src" / "components" / "SitePopup" / "SitePopup.tsx"
ORIGIN = "http://footer.test"

# The narrow cases: the standalone site page on phone widths (the popup spans the
# viewport) and the windowed popup resized to its MIN_WIDTH (usePopupWindow.ts).
NARROW = [
    pytest.param("standalone", 360, None, id="site-page-360"),
    pytest.param("standalone", 390, None, id="site-page-390"),
    pytest.param("standalone", 430, None, id="site-page-430"),
    pytest.param("windowed", 1280, 400, id="windowed-min-width-400"),
]
# The desktop cases, where the warning stays on one line as before.
WIDE = [
    pytest.param("windowed", 1280, None, id="windowed-default"),
    pytest.param("windowed", 1280, 700, id="windowed-700"),
    pytest.param("standalone", 1280, None, id="site-page-1280"),
]


def warning_text() -> str:
    """The warning sentence exactly as SitePopup.tsx ships it."""
    source = SITE_POPUP.read_text(encoding="utf-8")
    match = re.search(r'className="gallery-dev-warning">.*?<span>(.*?)</span>', source, re.DOTALL)
    assert match, "SitePopup.tsx has no .gallery-dev-warning span"
    return match.group(1)


def harness(mode: str, popup_width: int | None) -> str:
    footer = (
        '<div class="gallery-footer">'
        '<div class="connector-status">'
        '<button class="connector-status-header" aria-expanded="false">'
        '<svg class="connector-status-chevron" width="12" height="12" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/>'
        "</svg>"
        '<span class="connector-status-summary">14 sources returned results'
        '<span class="connector-status-failed"> (2 failed)</span>'
        '<span class="connector-status-time"> - 1.2s</span></span>'
        "</button></div>"
        '<div class="gallery-dev-warning">'
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
        ' stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0'
        ' 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/>'
        '<line x1="12" y1="17" x2="12.01" y2="17"/></svg>'
        f"<span>{warning_text()}</span>"
        "</div></div>"
    )
    gallery = f'<div class="popup-gallery-section">{footer}</div>'
    if mode == "standalone":
        body = (
            '<div class="site-page">'
            f'<div class="site-popup site-popup-large standalone">{gallery}</div></div>'
        )
    else:
        size = f"width:{popup_width}px;height:600px;" if popup_width else ""
        body = (
            '<div class="site-popup site-popup-large windowed"'
            f' style="position:fixed;left:0;top:0;{size}z-index:1000">{gallery}</div>'
        )
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<link rel="stylesheet" href="/fonts/fonts.css">'
        '<link rel="stylesheet" href="/src/styles/index.css">'
        '<link rel="stylesheet" href="/src/styles/site-page.css">'
        f"</head><body>{body}</body></html>"
    )


MEASURE = """() => {
  const footer = document.querySelector('.gallery-footer');
  const status = footer.querySelector('.connector-status');
  const warning = footer.querySelector('.gallery-dev-warning');
  const text = warning.querySelector('span');
  const box = el => el.getBoundingClientRect();
  // the span is a flex item (blockified), so its own client rects are one box: count the
  // line boxes of its text instead
  const lines = document.createRange();
  lines.selectNodeContents(text);
  return {
    font: [...document.fonts].some(f => f.family.includes('JetBrains Mono') && f.status === 'loaded'),
    warningFont: getComputedStyle(warning).fontFamily,
    footerWidth: box(footer).width,
    footerRight: box(footer).right,
    footerScroll: footer.scrollWidth,
    footerClient: footer.clientWidth,
    statusWidth: box(status).width,
    warningRight: box(warning).right,
    textRight: box(text).right,
    textLines: new Set([...lines.getClientRects()].map(r => Math.round(r.top))).size,
    iconWidth: box(warning.querySelector('svg')).width,
  };
}"""


def measure(mode: str, viewport: int, popup_width: int | None) -> dict:
    pytest.importorskip("playwright")
    from playwright.async_api import async_playwright

    page_html = harness(mode, popup_width)

    # The page needs the stylesheets (index.css @imports its partials) and the fonts; any
    # other request (a background image a rule names) answers 404 as a missing file would.
    types = {".css": "text/css", ".woff2": "font/woff2"}

    async def serve(route):
        path = route.request.url[len(ORIGIN) :].split("?")[0]
        if path == "/":
            await route.fulfill(body=page_html, content_type="text/html")
            return
        root = FRONTEND / "public" if path.startswith("/fonts/") else FRONTEND
        file = root / path.lstrip("/")
        if file.suffix in types and file.is_file():
            await route.fulfill(body=file.read_bytes(), content_type=types[file.suffix])
        else:
            await route.fulfill(status=404, body="")

    async def go():
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page(viewport={"width": viewport, "height": 800})
            await page.route(f"{ORIGIN}/**", serve)
            await page.goto(f"{ORIGIN}/")
            await page.evaluate("() => document.fonts.ready")
            result = await page.evaluate(MEASURE)
            await browser.close()
            return result

    return asyncio.run(go())


def assert_measured_in_the_brand_font(m: dict) -> None:
    assert m["warningFont"].startswith('"JetBrains Mono"'), m["warningFont"]
    assert m["font"], "JetBrains Mono did not load, the widths would be a fallback font's"


def assert_the_row_holds(m: dict) -> None:
    # nothing spills out of the footer, which .popup-gallery-section would clip
    assert m["footerScroll"] <= m["footerClient"], m
    assert m["warningRight"] <= m["footerRight"] + 0.5, m
    assert m["textRight"] <= m["warningRight"] + 0.5, m
    assert m["iconWidth"] == 12, m


@pytest.mark.parametrize(("mode", "viewport", "popup_width"), NARROW)
def test_a_narrow_footer_keeps_the_status_and_the_whole_warning(mode, viewport, popup_width):
    m = measure(mode, viewport, popup_width)
    assert_measured_in_the_brand_font(m)
    assert_the_row_holds(m)
    # the clickable status summary keeps a real share of the row (the old 31-character
    # warning left it 35 % to 41 % on these widths)
    assert m["statusWidth"] >= 0.35 * m["footerWidth"], m
    # the warning wraps instead of pushing the status out
    assert m["textLines"] >= 2, m


@pytest.mark.parametrize(("mode", "viewport", "popup_width"), WIDE)
def test_a_desktop_footer_shows_the_warning_on_one_line(mode, viewport, popup_width):
    m = measure(mode, viewport, popup_width)
    assert_measured_in_the_brand_font(m)
    assert_the_row_holds(m)
    assert m["textLines"] == 1, m
