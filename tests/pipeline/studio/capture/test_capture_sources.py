"""Source and paper page captures (pipeline/studio/capture/sources.py, highlight.js)."""

import asyncio
import importlib.util

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


def test_image_box_is_in_captured_pixels():
    assert image_box({"x": 100, "y": 1000, "w": 300, "h": 40}, top=100) == [200, 1800, 600, 80]


def test_the_credit_names_the_ascii_host_that_sourceviewer_draws():
    # the same string as video/src/format.ts domainOf: IDNA (ASCII), without "www."
    assert ascii_host("https://www.dainst.org/baalbek?x=1") == "dainst.org"
    assert ascii_host("https://el.wikipedia.org/wiki/Κνωσός") == "el.wikipedia.org"
    assert ascii_host("https://bücher.example/x") == "xn--bcher-kva.example"


PAGE = """<!doctype html><html><head><title>Test source</title></head><body style="margin:0">
<div style="position:fixed;top:0;left:0;right:0;height:80px;background:red" id="cookie">We use cookies</div>
<p style="margin-top:1500px">Intro text.</p>
<p>The block, measuring <em>19.6&nbsp;m</em> in length, is estimated to weigh 1,650 tonnes.</p>
<p id="ev-07">Evidence paragraph.</p>
<p id="ev-02" class="theo-evidence"><span class="theo-evidence-anchor" id="ev-03" style="display:block;height:0"></span>Second evidence paragraph, anchored twice.</p>
</body></html>"""


def _run_highlight(tmp_path, mode, needle):
    pytest.importorskip("playwright")
    from playwright.async_api import async_playwright

    page_file = tmp_path / "page.html"
    page_file.write_text(PAGE, encoding="utf-8")

    async def go():
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 800})
            await page.goto(page_file.as_uri())
            await page.add_script_tag(path=str(HIGHLIGHT_JS))
            await page.evaluate("() => window.__studio.hideOverlays()")
            box = await page.evaluate("([m, n]) => window.__studio.highlight(m, n)", [mode, needle])
            state = await page.evaluate(
                "() => ({marks: [...document.querySelectorAll('mark.__studio-hl')].map(m => m.textContent).join('|'),"
                " cookie: getComputedStyle(document.getElementById('cookie')).display})"
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
    assert state["cookie"] == "none"


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
