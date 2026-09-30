"""Source and paper page captures (pipeline/studio/capture/sources.py, highlight.js)."""

import asyncio
import importlib.util
import shutil

import pytest

from pipeline.studio.capture import sources
from pipeline.studio.capture.manifest import CaptureError
from pipeline.studio.capture.sources import (
    CONTEXT_PX,
    HIGHLIGHT_JS,
    ascii_host,
    capture_source,
    clip_window,
    image_box,
    require_in_window,
    source_target,
)

NVIDIA = "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Laptop GPU (0x0000249C) Direct3D11 vs_5_0 ps_5_0, D3D11)"
QUOTE_SPEC = {
    "id": "src1",
    "kind": "source",
    "url": "https://x.org/a",
    "quote": "a long enough quote",
}


def test_source_target_for_a_source_and_for_our_paper():
    spec = {
        "id": "s1",
        "kind": "source",
        "url": "https://dainst.org/x",
        "quote": "the block weighs 1,650 tonnes",
    }
    assert source_target(spec) == ("https://dainst.org/x", "quote", "the block weighs 1,650 tonnes")
    paper = {"id": "p1", "kind": "source", "paper": "baalbek-stones", "anchor": "ev-07"}
    assert source_target(paper) == (
        "https://ancientnerds.com/research/baalbek-stones#ev-07",
        "anchor",
        "ev-07",
    )
    # plans A, B and C number evidence ev- plus two or more digits, so ev-100 and beyond exist
    assert source_target({**paper, "anchor": "ev-1234"})[2] == "ev-1234"


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        (
            {"id": "s1", "kind": "source", "url": "ftp://x.org/a", "quote": "a long enough quote"},
            "not an http",
        ),
        ({"id": "s1", "kind": "source", "url": "https://x.org/a", "quote": "short"}, "at least 12"),
        (
            {"id": "p1", "kind": "source", "paper": "Bad Slug", "anchor": "ev-07"},
            "p1: paper 'Bad Slug' is not a slug",
        ),
        ({"id": "p1", "kind": "source", "paper": "ok", "anchor": "ref-3"}, "evidence anchor"),
        # EVIDENCE_ID_RE is applied with fullmatch: a trailing newline is no evidence id
        ({"id": "p1", "kind": "source", "paper": "ok", "anchor": "ev-07\n"}, "evidence anchor"),
        (
            {"id": "x", "kind": "source", "url": "https://x.org/a"},
            "either url \\+ quote or paper \\+ anchor",
        ),
    ],
)
def test_source_target_rejects_bad_specs(spec, message):
    with pytest.raises(CaptureError, match=message):
        source_target(spec)


def test_capture_source_takes_only_source_specs(tmp_path):
    with pytest.raises(CaptureError, match="takes kind 'source'"):
        capture_source(tmp_path, {"id": "p1", "kind": "paper", "paper": "x", "anchor": "ev-01"})


def test_a_venv_without_playwright_is_a_capture_error(tmp_path, monkeypatch):
    find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *args: None if name == "playwright" else find_spec(name, *args),
    )
    with pytest.raises(CaptureError, match="src1: Playwright is not installed in this venv"):
        capture_source(tmp_path, QUOTE_SPEC)
    assert not (tmp_path / "captures").exists()


def test_clip_window_keeps_context_and_stays_on_the_page():
    assert clip_window({"x": 0, "y": 3000, "w": 500, "h": 60}, page_height=10_000) == (
        3000 - CONTEXT_PX,
        60 + 2 * CONTEXT_PX,
    )
    assert clip_window({"x": 0, "y": 100, "w": 500, "h": 60}, page_height=500) == (0.0, 500)


def test_a_window_measured_again_is_no_taller_than_the_viewport_it_is_shot_in():
    # a 100vh hero grew with the 1738 px viewport and moved the quote from y 820 to 1758:
    # the full context would need 1835 px, the viewport (fixed from here) is 1738 px tall
    box = {"x": 0, "y": 1758, "w": 500, "h": 17}
    assert clip_window(box, page_height=5000, max_height=1738) == (1758 - CONTEXT_PX, 1738)
    # a window that fits keeps its full context
    assert clip_window(box, page_height=5000, max_height=2000) == (1758 - CONTEXT_PX, 1817)


def test_image_box_is_in_captured_pixels():
    assert image_box({"x": 100, "y": 1000, "w": 300, "h": 40}, top=100) == [200, 1800, 600, 80]


@pytest.mark.parametrize(
    ("box", "message"),
    [
        # a visually hidden copy at left:-9999px, one beyond the 1280 CSS px the window
        # shoots, one across its right edge
        ({"x": -9999, "y": 1000, "w": 293, "h": 17}, "not within the 1280 CSS px"),
        ({"x": 2000, "y": 1000, "w": 293, "h": 17}, "not within the 1280 CSS px"),
        ({"x": 1100, "y": 1000, "w": 293, "h": 17}, "not within the 1280 CSS px"),
        # a copy drawn at font-size 0
        ({"x": 100, "y": 1000, "w": 0, "h": 0}, "has no area"),
        ({"x": 100, "y": 1000, "w": 293, "h": 0.5}, "has no area"),
        # above and below the window
        ({"x": 100, "y": 50, "w": 293, "h": 17}, "left the capture window"),
        ({"x": 100, "y": 1910, "w": 293, "h": 17}, "left the capture window"),
    ],
)
def test_a_highlight_the_window_does_not_show_whole_is_refused(box, message):
    with pytest.raises(CaptureError, match=f"https://x.org/a: the highlight .*{message}"):
        require_in_window("https://x.org/a", box, top=100, height=1817)


def test_a_highlight_inside_the_window_passes():
    require_in_window("https://x.org/a", {"x": 0, "y": 100, "w": 1280, "h": 1817}, 100, 1817)


def test_the_credit_names_the_ascii_host_that_sourceviewer_draws():
    # the same string as video/src/format.ts domainOf: IDNA (ASCII), without "www."
    assert ascii_host("https://www.dainst.org/baalbek?x=1") == "dainst.org"
    assert ascii_host("https://el.wikipedia.org/wiki/Κνωσός") == "el.wikipedia.org"
    assert ascii_host("https://bücher.example/x") == "xn--bcher-kva.example"


PAGE = """<!doctype html><html><head><title>Test source</title></head><body style="margin:0">
<div style="position:fixed;top:0;left:0;right:0;height:80px;background:red" id="overlay">We use cookies</div>
<p style="margin-top:1500px">Intro text.</p>
<p>The block, measuring <em>19.6&nbsp;m</em> in length, is estimated to weigh 1,650 tonnes.</p>
<p id="ev-07">Evidence paragraph.</p>
<p id="ev-02" class="theo-evidence"><span class="theo-evidence-anchor" id="ev-03" style="display:block;height:0"></span>Second evidence paragraph, anchored twice.</p>
</body></html>"""

# 'İ' (U+0130) lower-cases to two UTF-16 units, 'i' and a combining dot above: a Turkish
# menu of place names before the article text must not shift the marks.
TURKISH_PAGE = """<!doctype html><html><head><title>Turkish sites</title></head><body style="margin:0">
<div style="position:fixed;top:0;left:0;right:0;height:40px" id="overlay">Menu</div>
<p>İzmir, İznik, İstanbul, İğdır, İnegöl, İskenderun, İdil, İlgın, İmranlı, İpsala, İscehisar, İvrindi.</p>
<p>At Göbekli Tepe its pillars are carved limestone. More text follows here.</p>
<p>Last line: the enclosures of İstanbul’s hinterland.</p>
</body></html>"""

# Our paper page's shell (ancient-nerds-map/src/styles/index.css and theo.css): html,
# body and #root are 100% tall with overflow hidden, and .theo-page is the 100vh scroller
# with a sticky header, so the document itself does not scroll. Every box is border-box
# (index.css), so .theo-page with its padding fits #root exactly.
PAPER_PAGE = """<!doctype html><html><head><title>Paper</title><style>
* { margin: 0; padding: 0; box-sizing: border-box }
html, body { overflow: hidden; width: 100%; height: 100%; margin: 0 }
#root { width: 100%; height: 100%; overflow: hidden }
.theo-page { height: 100vh; height: 100dvh; overflow-y: auto; padding-bottom: 60px }
.page-header { position: sticky; top: 0; height: 60px; z-index: 10; background: #111 }
</style></head><body><div id="root"><div class="theo-page">
<header class="page-header" id="overlay">Research</header>
<p style="margin-top:1500px">Intro text.</p>
<p id="ev-07" class="theo-evidence">The evidence paragraph of the paper, outlined in the video.</p>
<div style="height:3000px">Later sections.</div>
</div></div></body></html>"""


def _page(body):
    """A test page with a fixed overlay (hideOverlays hides it) above the given body."""
    return (
        '<!doctype html><html><head><title>t</title></head><body style="margin:0">'
        '<div style="position:fixed;top:0;left:0;right:0;height:40px" id="overlay">Menu</div>'
        f"{body}</body></html>"
    )


WEIGHT = "The block is estimated to weigh 1,650 tonnes."
SHOWN = f'<p style="margin-top:1500px">{WEIGHT}</p>'
SPLIT_WEIGHT = "The block is <em>estimated</em> to weigh 1,650 tonnes."
SR_ONLY_SPLIT = (
    '<span id="unseen" style="position:absolute;width:1px;height:1px;overflow:hidden;'
    f'clip:rect(0,0,0,0)">{SPLIT_WEIGHT}</span>'
)
# A CSS-truncated article body (max-height with overflow hidden): the teaser shows, the
# rest is cut off from its readers.
TRUNCATED_PAGE = _page(
    '<div style="max-height:60px;overflow:hidden"><p>The teaser paragraph of the article.</p>'
    f'<p style="margin-top:1500px">{WEIGHT}</p></div><p>After the article.</p>'
)


def _run_highlight(tmp_path, mode, needle, html=PAGE, fragment=""):
    pytest.importorskip("playwright")
    from playwright.async_api import async_playwright

    page_file = tmp_path / "page.html"
    page_file.write_text(html, encoding="utf-8")

    async def go():
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 800})
            await page.goto(page_file.as_uri() + fragment)
            await page.add_script_tag(path=str(HIGHLIGHT_JS))
            await page.evaluate("() => window.__studio.hideOverlays()")
            box = await page.evaluate("([m, n]) => window.__studio.highlight(m, n)", [mode, needle])
            state = await page.evaluate(
                "() => ({marks: [...document.querySelectorAll('mark.__studio-hl')].map(m => m.textContent).join('|'),"
                " overlay: getComputedStyle(document.getElementById('overlay')).display,"
                " scrollHeight: document.documentElement.scrollHeight,"
                " unseen: document.getElementById('unseen') && {"
                "html: document.getElementById('unseen').innerHTML,"
                " nodes: document.getElementById('unseen').childNodes.length},"
                # the text nodes the page made (window.pageNodes) are still its nodes
                " same: window.pageNodes ? (() => {"
                " const now = [...document.getElementById('unseen').childNodes];"
                " return now.length === window.pageNodes.length && now.every("
                "(n, i) => n === window.pageNodes[i] && n.data === window.pageData[i]) })()"
                " : null})"
            )
            await browser.close()
            return box, state

    return asyncio.run(go())


def test_highlight_finds_a_quote_across_inline_elements(tmp_path):
    box, state = _run_highlight(
        tmp_path, "quote", "measuring 19.6 m in length, is estimated to weigh 1,650 TONNES"
    )
    assert box is not None and box["y"] > 1500 and box["w"] > 100
    assert state["marks"] == "measuring |19.6\xa0m| in length, is estimated to weigh 1,650 tonnes"
    assert state["overlay"] == "none"


def test_a_lowercase_that_grows_keeps_the_marks_on_the_quote(tmp_path):
    box, state = _run_highlight(
        tmp_path, "quote", "its pillars are carved limestone", html=TURKISH_PAGE
    )
    assert box is not None
    assert state["marks"] == "its pillars are carved limestone"
    # the quote at the very end of the page, with an 'İ' of its own
    box, state = _run_highlight(
        tmp_path, "quote", "the enclosures of İSTANBUL'S hinterland.", html=TURKISH_PAGE
    )
    assert box is not None
    assert state["marks"] == "the enclosures of İstanbul’s hinterland."


@pytest.mark.parametrize(
    ("mode", "needle"),
    [("anchor", "ev-07"), ("quote", "the evidence paragraph of the paper")],
)
def test_our_paper_page_scrolls_as_a_document(tmp_path, mode, needle):
    # the #ev-07 link scrolls .theo-page; the capture needs the box in document pixels
    box, state = _run_highlight(tmp_path, mode, needle, html=PAPER_PAGE, fragment="#ev-07")
    assert box is not None and box["y"] > 1500
    assert state["scrollHeight"] > 1500 + 3000
    assert state["overlay"] == "none"


def test_highlight_outlines_an_evidence_anchor_and_misses_absent_text(tmp_path):
    box, _ = _run_highlight(tmp_path, "anchor", "ev-07")
    assert box is not None and box["y"] > 1500
    missing, _ = _run_highlight(tmp_path, "quote", "text that is not on the page")
    assert missing is None


def test_a_second_evidence_id_outlines_its_whole_paragraph(tmp_path):
    # plan B puts the second and later ids of a paragraph on an empty, zero-height span
    span, _ = _run_highlight(tmp_path, "anchor", "ev-03")
    paragraph, _ = _run_highlight(tmp_path, "anchor", "ev-02")
    assert span is not None and span["h"] > 10 and span["w"] > 0
    assert span == paragraph


@pytest.mark.parametrize(
    "unseen",
    [
        f'<div style="display:none">{WEIGHT}</div>',
        f'<script type="application/ld+json">{{"articleBody": "{WEIGHT}"}}</script>',
        f'<p style="visibility:hidden">{WEIGHT}</p>',
        # copies the search reads but a clipping box cuts off: a screen-reader-only span,
        # a closed accordion, a teaser clipped with an ellipsis
        '<span style="position:absolute;width:1px;height:1px;overflow:hidden;'
        f'clip:rect(0,0,0,0)">{WEIGHT}</span>',
        f'<div style="max-height:0;overflow:hidden"><p>{WEIGHT}</p></div>',
        '<p style="width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
        f"{WEIGHT}</p>",
        # a copy the search reads that no box of the page draws
        f"<textarea>{WEIGHT}</textarea>",
        # copies placed off the page the capture reaches (a visually hidden span, left or
        # above the document's origin) or drawn at no size
        f'<span style="position:absolute;left:-9999px">{WEIGHT}</span>',
        f'<span style="position:absolute;top:-9999px">{WEIGHT}</span>',
        f'<p style="font-size:0">{WEIGHT}</p>',
        f'<p style="transform:scale(0)">{WEIGHT}</p>',
        # a screen-reader-only copy split across inline elements: its three marks are
        # unmarked, the split text nodes joined again, and the search maps the page again
        SR_ONLY_SPLIT,
    ],
    ids=[
        "display-none",
        "json-ld",
        "visibility-hidden",
        "sr-only",
        "closed-accordion",
        "ellipsis",
        "textarea",
        "offscreen-left",
        "offscreen-top",
        "font-size-0",
        "scale-0",
        "sr-only-split",
    ],
)
def test_a_copy_the_reader_does_not_see_is_passed_over(tmp_path, unseen):
    # the first copy in the DOM is hidden, cut off or off the page; the one the reader sees
    # (at x 0, y 1500) is highlighted
    box, state = _run_highlight(tmp_path, "quote", WEIGHT, html=_page(unseen + SHOWN))
    assert box is not None and box["y"] >= 1500 and box["w"] > 100
    assert 0 <= box["x"] and box["x"] + box["w"] <= 1280
    assert state["marks"] == WEIGHT


def test_a_passed_over_copy_gets_its_text_nodes_back(tmp_path):
    # unmark put the three marked pieces back and joined the text nodes markText split:
    # the span holds its text, the <em> and its text again, as the page wrote them
    _, state = _run_highlight(tmp_path, "quote", WEIGHT, html=_page(SR_ONLY_SPLIT + SHOWN))
    assert state["marks"] == WEIGHT
    assert state["unseen"] == {"html": SPLIT_WEIGHT, "nodes": 3}


# A screen-reader-only copy whose text is two adjacent text nodes the page made itself, as
# a client-rendered React page writes `text {value}`; the quote starts at offset 0 of the
# first, so its split leaves an empty text node there.
REACT_TEXT_NODES = (
    '<span id="unseen" style="position:absolute;width:1px;height:1px;overflow:hidden;'
    'clip:rect(0,0,0,0)"></span><script>(() => {'
    " const span = document.getElementById('unseen');"
    " span.append('The block is estimated ', 'to weigh 1,650 tonnes.');"
    " window.pageNodes = [...span.childNodes];"
    " window.pageData = window.pageNodes.map((n) => n.data) })()</script>"
)


def test_a_passed_over_copy_keeps_the_text_nodes_its_page_made(tmp_path):
    """Review of Task 29: unmark normalized the parent, which merges every adjacent text
    node under it (the page's own too) and drops the empty one a split at offset 0 leaves,
    so React would update or remove a text node that is no longer in the page."""
    _, state = _run_highlight(tmp_path, "quote", WEIGHT, html=_page(REACT_TEXT_NODES + SHOWN))
    assert state["marks"] == WEIGHT
    assert state["unseen"]["nodes"] == 2 and state["same"] is True


def test_of_two_copies_the_reader_sees_the_first_is_highlighted(tmp_path):
    html = _page(SHOWN + f'<p style="margin-top:1500px">{WEIGHT}</p>')
    box, state = _run_highlight(tmp_path, "quote", WEIGHT, html=html)
    # the first paragraph starts at y 1500, the second 1500 px below its end
    assert box is not None and 1500 <= box["y"] < 1600
    assert state["marks"] == WEIGHT


def test_text_in_a_display_contents_element_is_read(tmp_path):
    # display:contents has no box of its own; its text is laid out in the paragraph
    html = _page(f'<p style="margin-top:1500px"><span style="display:contents">{WEIGHT}</span></p>')
    box, state = _run_highlight(tmp_path, "quote", WEIGHT, html=html)
    assert box is not None and box["y"] >= 1500
    assert state["marks"] == WEIGHT


@pytest.mark.parametrize(
    "body",
    [
        # a teaser the reader sees, its continuation kept in the DOM behind the paywall
        # (the line break between them is page text: it joins the two into the quote)
        '<p style="margin-top:1500px">The block is estimated</p>\n'
        '<p style="display:none">to weigh 1,650 tonnes.</p>',
        # a closed accordion
        f'<div style="max-height:0;overflow:hidden"><p>{WEIGHT}</p></div>',
        # the text of a form field is read by the search but drawn by no box of the page
        f"<textarea>{WEIGHT}</textarea>",
        # the page's content in a fixed scroller, which hideOverlays hides with the banners
        f'<div style="position:fixed;inset:0;overflow-y:auto">{SHOWN}</div>',
        # a page wider than the 1280 CSS px the capture shoots: the only copy lies beyond
        # that width, or runs past its right edge
        f'<p style="margin:1500px 0 0 2000px;width:600px">{WEIGHT}</p>',
        f'<p style="margin:1500px 0 0 1000px;white-space:nowrap">{WEIGHT}</p>',
    ],
    ids=[
        "hidden-continuation",
        "closed-accordion",
        "textarea",
        "fixed-scroller",
        "beyond-1280",
        "across-1280",
    ],
)
def test_a_quote_the_reader_cannot_see_whole_is_not_found(tmp_path, body):
    # sources.py turns None into the advice to use a QuoteCard
    box, _ = _run_highlight(tmp_path, "quote", WEIGHT, html=_page(body))
    assert box is None


def test_a_truncated_body_shows_its_teaser_and_keeps_the_rest_hidden(tmp_path):
    teaser, state = _run_highlight(
        tmp_path, "quote", "the teaser paragraph of the article", html=TRUNCATED_PAGE
    )
    assert teaser is not None
    assert state["marks"] == "The teaser paragraph of the article"
    # the quote lies in the part the page cuts off: letting it out would show readers'
    # hidden text as if it were on the page
    hidden, _ = _run_highlight(tmp_path, "quote", WEIGHT, html=TRUNCATED_PAGE)
    assert hidden is None


def test_an_evidence_paragraph_cut_off_by_its_box_is_not_visible(tmp_path):
    html = _page(
        '<div style="max-height:0;overflow:hidden">'
        '<p id="ev-09" class="theo-evidence">Collapsed evidence.</p></div>'
    )
    box, _ = _run_highlight(tmp_path, "anchor", "ev-09", html=html)
    assert box is None


@pytest.mark.skipif(shutil.which("nvidia-smi") is None, reason="no NVIDIA driver on this machine")
def test_the_capture_window_on_our_paper_page_keeps_its_context(tmp_path):
    pytest.importorskip("playwright")
    from PIL import Image

    page_file = tmp_path / "paper.html"
    page_file.write_text(PAPER_PAGE, encoding="utf-8")
    out = tmp_path / "paper.png"
    shot = asyncio.run(sources._capture(page_file.as_uri() + "#ev-07", "anchor", "ev-07", out))
    box = shot["box"]
    # CONTEXT_PX above and below the paragraph, not the 800 px viewport it was loaded in
    assert shot["top"] == pytest.approx(box["y"] - CONTEXT_PX, abs=1)
    assert shot["height"] == pytest.approx(box["h"] + 2 * CONTEXT_PX, abs=1)
    with Image.open(out) as img:
        assert img.size[1] == pytest.approx(shot["height"] * sources.DEVICE_SCALE, abs=2)


@pytest.mark.skipif(shutil.which("nvidia-smi") is None, reason="no NVIDIA driver on this machine")
@pytest.mark.parametrize(
    "unseen",
    [
        f'<span style="position:absolute;left:-9999px">{WEIGHT}</span>',
        f'<span style="position:absolute;top:-9999px">{WEIGHT}</span>',
        f'<p style="font-size:0">{WEIGHT}</p>',
    ],
    ids=["offscreen-left", "offscreen-top", "font-size-0"],
)
def test_the_highlight_box_lies_in_the_captured_png(tmp_path, unseen):
    # a copy off the page or at no size comes first; the manifest's box is the shown copy's
    pytest.importorskip("playwright")
    from PIL import Image

    page_file = tmp_path / "page.html"
    page_file.write_text(_page(unseen + SHOWN), encoding="utf-8")
    out = tmp_path / "page.png"
    shot = asyncio.run(sources._capture(page_file.as_uri(), "quote", WEIGHT, out))
    x, y, w, h = image_box(shot["box"], shot["top"])
    with Image.open(out) as img:
        width, height = img.size
    assert w > 100 and h > 10
    assert 0 <= x and x + w <= width
    assert 0 <= y and y + h <= height + 1  # Chromium rounds the window to whole pixels


@pytest.mark.skipif(shutil.which("nvidia-smi") is None, reason="no NVIDIA driver on this machine")
def test_a_viewport_tall_hero_above_the_quote_keeps_it_in_the_window(tmp_path):
    # the header is 100vh: when the viewport grows to the window's height it grows too and
    # moves the quote down, out of the window measured in the 800 px viewport
    pytest.importorskip("playwright")
    from PIL import Image

    hero = _page(
        '<header style="height:100vh">Hero</header>'
        f'<p style="margin:20px 0">{WEIGHT}</p><div style="height:3000px">Later sections.</div>'
    )
    page_file = tmp_path / "hero.html"
    page_file.write_text(hero, encoding="utf-8")
    out = tmp_path / "hero.png"
    shot = asyncio.run(sources._capture(page_file.as_uri(), "quote", WEIGHT, out))
    box = shot["box"]
    assert box["y"] > sources.VIEWPORT[1] + CONTEXT_PX  # below the grown hero
    assert shot["top"] <= box["y"] and box["y"] + box["h"] <= shot["top"] + shot["height"]
    with Image.open(out) as img:
        assert img.size[1] == pytest.approx(shot["height"] * sources.DEVICE_SCALE, abs=2)


def test_the_manifest_size_is_the_size_of_the_written_png(tmp_path, monkeypatch):
    pytest.importorskip("playwright")
    from PIL import Image

    async def shot(url, mode, needle, out):
        # 906.3 CSS px at scale 2 is 1812.6; Chromium wrote a 1812 px tall PNG
        Image.new("RGB", (2560, 1812), "white").save(out)
        box = {"x": 100, "y": 1000, "w": 300, "h": 40}
        title = "Κνωσός - Βικιπαίδεια"
        return {"box": box, "top": 100, "height": 906.3, "title": title, "renderer": NVIDIA}

    monkeypatch.setattr(sources, "_capture", shot)
    manifest = capture_source(tmp_path, QUOTE_SPEC)
    assert (manifest["width"], manifest["height"]) == (2560, 1812)
    # the page's own <title> is a record in the page event; the drawn credit is the ASCII host
    assert manifest["credits"] == ["Source page: x.org"]
    assert manifest["events"][1]["title"] == "Κνωσός - Βικιπαίδεια"


def test_a_browser_failure_is_a_capture_error_with_its_cause(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.async_api")

    async def timeout(url, mode, needle, out):
        raise playwright.TimeoutError("Timeout 45000ms exceeded.")

    monkeypatch.setattr(sources, "_capture", timeout)
    with pytest.raises(CaptureError, match="src1: Timeout 45000ms exceeded.") as err:
        capture_source(tmp_path, QUOTE_SPEC)
    assert isinstance(err.value.__cause__, playwright.TimeoutError)
