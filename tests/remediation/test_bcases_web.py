"""The owner-case coordinates' second wave: a third witness from the web (`bcases/web_witness.py`).

The research behind it is untrusted, so every check a candidate must pass has a test here that goes
red without it - the host (Wikipedia and its mirrors, our own site, a private address, a redirect into
either), the fetch (one request, an HTTP refusal is a rejection with its status, a PDF is not read, a
challenge page is not a page), the text (the quote occurs in the page's text, across the glyphs a
coordinate is typed with), the numbers (they parse, and they are the page's, not the agent's), and
the identity (the site's name stands next to them). Then the classifier's extension (web witnesses
named by their host, last in priority, two agreeing pairs on two points are read), the reweigh (the
unchanged rule, a move into another country is read, the first wave is never touched, the cache must
reproduce the first wave), and the second wave's plan (its own stamp and directory, wave 1 rendering
what is committed). The mutation sweep's "bcases web" set removes the guards one by one.

No test reads the network or production: the scripted fetcher refuses what the real one refuses, the
real fetcher runs on a mock transport, and the psql reader is a fake. The tests on delivered files
skip with their reason while `coords3/RESEARCH.jsonl` is not delivered; the tests that need the
gitignored cache read `BCASES_CACHE` (default: the checkout's own `output/remediation/cache/bcases`).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
import shapely
from shapely.geometry import box

REPO = Path(__file__).resolve().parents[2]
for _path in (REPO, REPO / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import census.fetch as census_fetch  # noqa: E402
from bcases import classify as C  # noqa: E402
from bcases import coord_plan as P  # noqa: E402
from bcases import inputs  # noqa: E402
from bcases import run as RUN  # noqa: E402
from bcases import web_witness as W  # noqa: E402
from census.fetch import USER_AGENT, FetchError  # noqa: E402

OUT = REPO / "output" / "remediation" / "bcases"
CACHE = Path(os.environ.get("BCASES_CACHE", str(inputs.CACHE)))

SITE = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"

NAME = "El Tintal"
URL = "https://www.mayaruins.example/el-tintal"
COORD = "17°34′28″N 89°59′45″W"
LAT, LON = 17 + 34 / 60 + 28 / 3600, -(89 + 59 / 60 + 45 / 3600)


def _html(body: str) -> str:
    return (
        "<html><head><title>Maya ruins</title><script>var tracking = 1;</script></head>"
        f"<body>{body}</body></html>"
    )


PAGE = _html(f"<h1>El Tintal</h1><p>Location: <span>{COORD}</span></p>")


@dataclass
class Page:
    text: str = PAGE
    status: int = 200
    content_type: str | None = "text/html; charset=utf-8"
    final: str | None = None


class ScriptedNet:
    """`census.fetch.Fetcher.get_text` as the real one answers: an error status raises `FetchError`
    (a 404 is returned as a value), a redirect answers with the URL it ended at. A URL that is not
    scripted is a test that reached for the network - it fails."""

    def __init__(self, pages: Mapping[str, Page]) -> None:
        self.pages = dict(pages)
        self.calls: list[str] = []

    def get_text(
        self, url: str, params: dict[str, Any] | None = None, ns: str = "text", force: bool = False
    ) -> dict[str, Any]:
        self.calls.append(url)
        page = self.pages[url]
        final = page.final or url
        if page.status >= 400 and page.status != 404:
            raise FetchError(f"{final}: HTTP {page.status}")
        return {
            "method": "GET",
            "url": final,
            "status": page.status,
            "headers": {} if page.content_type is None else {"content-type": page.content_type},
            "text": page.text if page.status < 400 else "",
            "error": None if page.status < 400 else f"HTTP {page.status}",
            "fetched_at": "2026-09-23T10:00:00+0200",
        }


def _candidate(**kw: Any) -> dict[str, Any]:
    return {
        "url": URL,
        "lat": LAT,
        "lon": LON,
        "coord_text": COORD,
        "source_name": "Maya ruins",
        "agrees_with": "witness",
        "note": "",
        **kw,
    }


def _verify(
    page: Page | None = None, *, name: str = NAME, **kw: Any
) -> tuple[dict[str, Any], ScriptedNet]:
    candidate = _candidate(**kw)
    net = ScriptedNet({candidate["url"]: page or Page()})
    return W.verify_candidate(net, site_id=SITE, name=name, candidate=candidate), net


def _code(row: Mapping[str, Any]) -> str:
    return W.rejection_code(row)


# ── the host ──────────────────────────────────────────────────────────────────────────────────


def test_a_page_that_proves_itself_is_a_web_witness() -> None:
    row, net = _verify()
    assert row["accepted"] is True, row["reason"]
    assert row["reason"].startswith("accepted: ") and "'tintal'" in row["reason"]
    assert row["witness"] == {
        "kind": "web",
        "lat": LAT,
        "lon": LON,
        "url": URL,
        "quote": COORD,
        "step": C.grid_of(LAT, LON),
    }
    assert row["witness"]["step"] == pytest.approx(1 / 3600)
    assert (row["host"], row["final_url"], net.calls) == ("www.mayaruins.example", URL, [URL])


WIKI_URLS = (
    "https://en.wikipedia.org/wiki/El_Tintal",
    "https://en.m.wikipedia.org/wiki/El_Tintal",
    "https://www.wikidata.org/wiki/Q3721023",
    "https://commons.wikimedia.org/wiki/File:X.jpg",
    "https://geohack.toolforge.org/geohack.php?params=17_34_28_N_89_59_45_W",
    "https://www.wikiwand.com/en/El_Tintal",
    "https://dbpedia.org/page/El_Tintal",
    "https://mapcarta.com/12345",
    "https://latitude.to/articles-by-country/gt/guatemala/1/el-tintal",
    "https://alchetron.com/El-Tintal",
    "https://en.everybodywiki.com/El_Tintal",
    "https://kids.kiddle.co/El_Tintal",
    "https://wiki2.org/en/El_Tintal",
    "https://www.wikizero.com/en/El_Tintal",
    "https://justapedia.org/wiki/El_Tintal",
    "https://military-history.fandom.com/wiki/Scordisci",
    "https://wikitia.com/wiki/El_Tintal",
)


def test_a_wiki_host_or_mirror_is_never_a_web_witness() -> None:
    """Their coordinates are the two witnesses already asked, or a copy: never asked for."""
    for url in WIKI_URLS:
        row, net = _verify(url=url)
        assert _code(row) == "wiki-host", (url, row["reason"])
        assert net.calls == [], url


def test_the_named_mirrors_are_in_the_list_and_matched_by_domain_only() -> None:
    assert isinstance(W.WIKI_HOSTS, frozenset)
    named = {
        "wikipedia.org",
        "wikimedia.org",
        "wikidata.org",
        "wikiwand.com",
        "dbpedia.org",
        "toolforge.org",
        "wmflabs.org",
        "mapcarta.com",
        "latitude.to",
        "alchetron.com",
        "everybodywiki.com",
        "kiddle.co",
        "wiki2.org",
        "wikizero.com",
        "justapedia.org",
        "fandom.com",
        "wikitia.com",
    }
    assert named <= W.WIKI_HOSTS, named - W.WIKI_HOSTS
    # a host that merely contains a wiki's name is not the wiki
    for url in ("https://www.notwikipedia.org/x", "https://wikipedia.org.example/x"):
        row, _ = _verify(Page(), url=url)
        assert row["accepted"], (url, row["reason"])


COPY_URLS = (
    "https://en-m-wikipedia-org.translate.goog/wiki/Karnak?_x_tr_sl=en&_x_tr_tl=de",
    "https://www-mayaruins-example.translate.goog/el-tintal?_x_tr_sl=es&_x_tr_tl=en",
    "https://web.archive.org/web/2020/https://en.wikipedia.org/wiki/Karnak",
    "https://web.archive.org/web/2020/https://www.mayaruins.example/el-tintal",
    "https://archive.ph/abcd",
    "https://archive.is/abcd",
    "https://archive.today/abcd",
    "https://archive.li/abcd",
    "https://webcache.googleusercontent.com/search?q=cache:www.mayaruins.example/el-tintal",
)


def test_a_proxy_or_an_archive_copy_is_never_a_web_witness() -> None:
    """A translation proxy or a web archive serves another publisher's page - a Wikipedia article
    (an older revision, another language) as readily as any other: its host is not the page's
    publisher, so the witness would be counted as a publisher of its own ("web:translate.goog",
    "web:archive.org") beside the item and the article it copies. Refused before any request, and
    where a redirect ends."""
    for url in COPY_URLS:
        row, net = _verify(url=url)
        assert _code(row) == "copy-host", (url, row["reason"])
        assert net.calls == [], url
    final = "https://web.archive.org/web/2020/https://www.mayaruins.example/el-tintal"
    row, _ = _verify(Page(final=final))
    assert _code(row) == "copy-host" and f"{URL} redirected to {final}" in row["reason"]
    # a host that merely contains an archive's name is not the archive
    for url in ("https://www.notarchive.org/el-tintal", "https://translate.goog.example/x"):
        row, _ = _verify(url=url)
        assert row["accepted"], (url, row["reason"])


def test_a_redirect_into_wikipedia_is_rejected() -> None:
    row, _ = _verify(Page(final="https://en.wikipedia.org/wiki/El_Tintal"))
    assert _code(row) == "wiki-host" and "redirected to" in row["reason"]
    assert row["final_url"] == "https://en.wikipedia.org/wiki/El_Tintal"


def test_a_redirect_to_our_own_site_a_blocked_host_or_a_private_address_is_refused() -> None:
    """The page read is the one a redirect ends at: every host check runs on it again, not only the
    wiki list - our own site publishes the stored point, and a blocked host is blocked wherever the
    link started."""
    for final, code in (
        ("https://ancientnerds.com/sites/guatemala/el-tintal", "refused-host"),
        ("https://www.ancient-origins.net/x", "refused-host"),
        ("http://127.0.0.1:18000/api/sites", "not-public"),
    ):
        row, _ = _verify(Page(final=final))
        assert _code(row) == code and f"{URL} redirected to {final}" in row["reason"], row["reason"]
        assert row["final_url"] == final


def test_our_own_site_and_a_blocked_host_are_refused() -> None:
    for url in (
        "https://ancientnerds.com/sites/guatemala/el-tintal",
        "https://ancient-origins.net/x",
    ):
        row, net = _verify(url=url)
        assert _code(row) == "refused-host", (url, row["reason"])
        assert net.calls == []


def test_a_private_address_is_never_asked() -> None:
    for url in ("http://127.0.0.1:18000/api/sites", "http://localhost:15432/", "http://10.0.0.7/"):
        row, net = _verify(url=url)
        assert _code(row) == "not-public", (url, row["reason"])
        assert net.calls == []


def _fetcher(
    tmp_path: Path, handler: Any, monkeypatch: pytest.MonkeyPatch
) -> tuple[census_fetch.Fetcher, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    monkeypatch.setattr(census_fetch.time, "sleep", lambda seconds: None)
    return W.open_fetcher(tmp_path / "web", httpx.MockTransport(record)), seen


def test_a_redirect_hop_into_a_private_address_is_refused_inside_the_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://127.0.0.1:18000/api/sites"})

    net, seen = _fetcher(tmp_path, handler, monkeypatch)
    with net:
        row = W.verify_candidate(net, site_id=SITE, name=NAME, candidate=_candidate())
    assert _code(row) == "http" and "not a public http(s) address" in row["reason"]
    assert [str(r.url) for r in seen] == [URL]


# ── the fetch ─────────────────────────────────────────────────────────────────────────────────


def test_an_http_refusal_is_a_rejection_with_its_status_and_one_request() -> None:
    for status in (403, 429, 503):
        row, net = _verify(Page(status=status))
        assert _code(row) == "http" and f"HTTP {status}" in row["reason"], row["reason"]
        assert net.calls == [URL]


def test_a_missing_page_is_a_rejection() -> None:
    row, _ = _verify(Page(status=404))
    assert _code(row) == "http" and "HTTP 404" in row["reason"]


def test_the_real_fetcher_asks_a_refusing_host_once_and_caches_a_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    net, seen = _fetcher(tmp_path, lambda request: httpx.Response(503), monkeypatch)
    with net:
        row = W.verify_candidate(net, site_id=SITE, name=NAME, candidate=_candidate())
    assert _code(row) == "http" and "HTTP 503" in row["reason"]
    assert len(seen) == W.MAX_ATTEMPTS == 1
    assert seen[0].headers["user-agent"] == USER_AGENT

    def page(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text=PAGE)

    net, seen = _fetcher(tmp_path, page, monkeypatch)
    with net:
        first = W.verify_candidate(net, site_id=SITE, name=NAME, candidate=_candidate())
        again = W.verify_candidate(net, site_id=SITE, name=NAME, candidate=_candidate())
    assert first == again and first["accepted"], first["reason"]
    assert len(seen) == 1 and list((tmp_path / "web" / "page").rglob("*.json"))


def test_a_pdf_or_another_document_is_not_read() -> None:
    body = f"%PDF-1.4 El Tintal {COORD}"
    for content_type in ("application/pdf", "application/json", None):
        row, _ = _verify(Page(text=body, content_type=content_type))
        assert _code(row) == "not-html", (content_type, row["reason"])
    row, _ = _verify(Page(content_type="application/xhtml+xml"))
    assert row["accepted"], row["reason"]


CLOUDFLARE = "<html><head><title>Just a moment...</title></head><body>Checking</body></html>"
CHALLENGE = "<html><script>window._cf_chl_opt = {cvId: '3'};</script><body>Enable JS</body></html>"
ANUBIS = (
    "<html><head><title>Making sure you&#39;re not a bot!</title></head>"
    '<body><script id="anubis_challenge" type="application/json">{}</script></body></html>'
)


def test_a_challenge_page_served_with_200_is_a_bot_wall() -> None:
    for markup, what in ((CLOUDFLARE, "Cloudflare"), (CHALLENGE, "Cloudflare"), (ANUBIS, "Anubis")):
        row, _ = _verify(Page(text=markup))
        assert _code(row) == "bot-wall" and what in row["reason"], row["reason"]
    # a page Cloudflare serves normally carries its scripts and is a page
    jsd = '<script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script></head>'
    row, _ = _verify(Page(text=PAGE.replace("</head>", jsd)))
    assert row["accepted"], row["reason"]


# ── the text ──────────────────────────────────────────────────────────────────────────────────


def test_the_quote_must_occur_in_the_page() -> None:
    row, _ = _verify(Page(text=_html("<h1>El Tintal</h1><p>A Maya city in the Peten.</p>")))
    assert _code(row) == "not-on-page", row["reason"]


def test_the_quote_must_stand_whole_in_the_page() -> None:
    """The quote is a substring of the page only where it stands whole: the page's "-17.5744" quoted
    without its sign, its "-89.99583" quoted as "-89.9958", its "117.5744" as "17.5744", or a
    hemisphere letter after the quote would each parse to a number the page does not state."""
    quote, lat, lon = "17.5744, -89.9958", 17.5744, -89.9958
    for shown in (
        "-17.5744, -89.9958",
        "- 17.5744, -89.9958",
        "–17.5744, -89.9958",
        "117.5744, -89.9958",
        "0.17.5744, -89.9958",
        "N17.5744, -89.9958",
        "S 17.5744, -89.9958",
        "17.5744, -89.99583",
        "17.5744, -89.9958.5",
        "17.5744, -89.9958W",
        "17.5744, -89.9958 W",
        "17.5744, -89.9958° W",
    ):
        page = _html(f"<h1>El Tintal</h1><p>GPS {shown} here</p>")
        row, _ = _verify(Page(text=page), coord_text=quote, lat=lat, lon=lon)
        assert _code(row) == "not-on-page" and "whole" in row["reason"], (shown, row["reason"])
    for shown in (
        "GPS (17.5744, -89.9958)",
        "GPS:17.5744, -89.9958.",
        "GPS 17.5744, -89.9958 Elevation 200 m",
        "1. 17.5744, -89.9958",
    ):
        page = _html(f"<h1>El Tintal</h1><p>{shown}</p>")
        row, _ = _verify(Page(text=page), coord_text=quote, lat=lat, lon=lon)
        assert row["accepted"], (shown, row["reason"])
    # a quote that ends on its hemisphere letter or begins with a label is bounded by its own words
    row, _ = _verify(Page(text=_html(f"<h1>El Tintal</h1><p>{COORD}West</p>")))
    assert row["accepted"], row["reason"]


def test_a_dash_before_a_lettered_quote_is_a_separator_not_its_sign() -> None:
    """A quote whose numbers carry their hemisphere letters takes no sign from the page: "El Tintal –
    17°34′28″N 89°59′45″W" is a separator (measured: cestenfrance.fr, 2026-09-23). A sign against its
    first digit, or a digit continuing it, still makes it not the page's number."""
    for shown in (f"El Tintal – {COORD}", f"El Tintal - {COORD}", f"El Tintal, zone E {COORD}"):
        row, _ = _verify(Page(text=_html(f"<p>{shown}</p>")))
        assert row["accepted"], (shown, row["reason"])
    for shown in (f"El Tintal –{COORD}", f"El Tintal 1{COORD}"):
        row, _ = _verify(Page(text=_html(f"<p>{shown}</p>")))
        assert _code(row) == "not-on-page", (shown, row["reason"])


def test_the_page_and_the_quote_are_compared_across_glyph_variants() -> None:
    """The page types the coordinate with entities, a masculine ordinal and two apostrophes, split
    across tags and non-breaking spaces; the quote with the degree sign, primes and a double prime."""
    typed = "17&deg;34&#8242;28&#8243;N&nbsp;<b>89º59'45''W</b>"
    row, _ = _verify(Page(text=_html(f"<h1>El Tintal</h1><p>{typed}</p>")))
    assert row["accepted"], row["reason"]
    assert W.normalise("89º59'45''W \n x") == "89°59'45\"W x"


def test_a_coordinate_inside_a_script_is_not_page_text() -> None:
    markup = _html(f'<h1>El Tintal</h1><script>var geo = "{COORD}";</script>')
    row, _ = _verify(Page(text=markup))
    assert _code(row) == "not-on-page", row["reason"]


def test_the_glyphs_are_unified_before_nfkc_would_break_them() -> None:
    """NFKC turns a masculine ordinal into "o" and a superscript zero into "0"; unified first they
    are degree signs. A double prime becomes one double quote, a minus sign a hyphen-minus."""
    assert W.normalise("41º53′33″N") == "41°53'33\"N"
    assert W.normalise("45⁰ 30˚") == "45° 30°"
    assert W.normalise("\u221217.5,\u200b \u221289.9") == "-17.5, -89.9"


def test_whitespace_runs_are_one_space() -> None:
    assert W.normalise("17.5,\n\t  -89.9") == "17.5, -89.9"
    row, _ = _verify(Page(text=_html("<h1>El Tintal</h1><p>17°34′28″N\n\n   89°59′45″W</p>")))
    assert row["accepted"], row["reason"]


# ── the numbers ───────────────────────────────────────────────────────────────────────────────

DMS = (41 + 53 / 60 + 33.9 / 3600, -(8 + 52 / 60 + 11.3 / 3600))
FORMS = {
    "41.8927, -8.8698": (41.8927, -8.8698),
    "41.8927°N 8.8698°W": (41.8927, -8.8698),
    "41.8927 N, 8.8698 W": (41.8927, -8.8698),
    "N 41.8927, W 8.8698": (41.8927, -8.8698),
    "Latitude: 41.8927 Longitude: -8.8698": (41.8927, -8.8698),
    "Coordinates: 41.8927, -8.8698 (WGS 84)": (41.8927, -8.8698),
    "41°53′33.9″N 8°52′11.3″W": DMS,
    "41° 53' 33.9\" N, 8° 52' 11.3\" W": DMS,
    "N41°53'33.9\" W8°52'11.3\"": DMS,
    "41°53'N 8°52'W": (41 + 53 / 60, -(8 + 52 / 60)),
    "N 17° 34.466', W 89° 59.750'": (17 + 34.466 / 60, -(89 + 59.75 / 60)),
    "N17 13 22.008 W89 37 25.008": (17 + 13 / 60 + 22.008 / 3600, -(89 + 37 / 60 + 25.008 / 3600)),
    "17 13 22 N 89 37 25 W": (17 + 13 / 60 + 22 / 3600, -(89 + 37 / 60 + 25 / 3600)),
    "8.8698°W 41.8927°N": (41.8927, -8.8698),
}


def test_the_forms_a_coordinate_is_written_in_parse_to_its_point() -> None:
    for text, point in FORMS.items():
        assert W.parse_coordinates(text) == pytest.approx(point, abs=1e-12), text


def _unparsed(text: str, code: str = "unparsed") -> str:
    with pytest.raises(W.Rejected) as caught:
        W.parse_coordinates(text)
    assert caught.value.code == code, (text, str(caught.value))
    return caught.value.detail


def test_a_grid_reference_is_not_read() -> None:
    for text in ("SU 123 456", "NGR ST 1234 5678", "33T 456789 4567890", "Easting 456789"):
        _unparsed(text, "grid-reference")


def test_a_dms_value_needs_its_hemisphere_letter() -> None:
    assert "hemisphere letter" in _unparsed("41°53'33.9\", -8°52'11.3\"")


def test_a_whole_number_is_not_a_coordinate() -> None:
    assert "whole number" in _unparsed("41, -8")


def test_two_values_in_one_form_and_no_more() -> None:
    for text in ("41.5, 12.3, 13.4", "41.8927", "41 53 33 N 8 52 11", "41.5 N, 12.3"):
        assert "not two in one form" in _unparsed(text), text


def test_words_beside_the_coordinates_are_not_read() -> None:
    """ "West" is a hemisphere this parser does not read, "Tomb 3" another place: neither may pass as
    a label around two signed numbers."""
    for text in ("41.5 North, 12.3 West", "Tomb 3.5, 12.3"):
        assert "stand beside the two coordinates" in _unparsed(text), text


def test_a_sign_or_a_dash_standing_apart_is_not_read() -> None:
    """A sign parted from its number by a space, or a dash the glyph table does not turn into a minus
    (an en dash, a hyphen), would leave the number positive: the text is refused, not read as east
    or north."""
    for text in (
        "17.5744, - 89.9958",
        "17.5744, –89.9958",
        "Lat 17.5744 Long + 89.9958",
        "‐ 17.5744, 89.9958",
        "41.5 N – 12.3 E",
    ):
        assert "stand beside the two coordinates" in _unparsed(text), text
    assert W.parse_coordinates("17.5744,-89.9958") == (17.5744, -89.9958)


def test_two_signed_numbers_are_read_latitude_first_and_a_label_saying_otherwise_is_refused() -> (
    None
):
    """Signed decimals carry no axis of their own: the labels, when there are any, must name the
    latitude first ("Longitude / Latitude -0.3579, 51.754" is a longitude first)."""
    for text in (
        "Longitude / Latitude -0.3579, 51.754",
        "Long: -0.3579, Lat: 51.754",
        "-0.3579 (lon), 51.754 (lat)",
    ):
        assert "names the longitude first" in _unparsed(text), text
    assert W.parse_coordinates("Lat/Long 51.754, -0.3579") == (51.754, -0.3579)
    assert W.parse_coordinates("51.754 (lat), -0.3579 (long)") == (51.754, -0.3579)


def test_a_sign_and_a_letter_together_are_not_read() -> None:
    assert "both a sign and a hemisphere letter" in _unparsed("-41.5 S, 12.3 E")


def test_one_axis_named_twice_is_not_read() -> None:
    assert "names one axis twice" in _unparsed("41.5 N 12.3 N")


def test_a_point_off_the_earth_is_not_read() -> None:
    assert "not a point on Earth" in _unparsed("95.5, 10.5")


def test_minutes_and_seconds_stay_below_sixty() -> None:
    assert "is not below 60" in _unparsed("41°61'N 8°52'W")
    assert "is not below 60" in _unparsed("41°53'60\"N 8°52'11\"W")


def test_the_numbers_are_the_pages_not_the_agents() -> None:
    row, _ = _verify(lat=LAT + 2e-6)
    assert _code(row) == "mismatch", row["reason"]
    row, _ = _verify(lat=LAT + 5e-7, lon=LON - 5e-7)
    assert row["accepted"], row["reason"]
    # the witness carries what the page says, never the agent's rounding of it
    assert (row["witness"]["lat"], row["witness"]["lon"]) == (LAT, LON)


def test_a_malformed_candidate_is_rejected_and_nothing_is_asked() -> None:
    for broken in (
        {"lat": "17.5"},
        {"lat": True},
        {"lon": float("nan")},
        {"url": None},
        {"url": "ftp://files.example/x"},
        {"coord_text": " \u200b "},
    ):
        candidate = _candidate(**broken)
        net = ScriptedNet({})
        row = W.verify_candidate(net, site_id=SITE, name=NAME, candidate=candidate)
        assert _code(row) == "malformed", (broken, row["reason"])
        assert net.calls == []
    row = W.verify_candidate(ScriptedNet({}), site_id=SITE, name=NAME, candidate=["a list"])
    assert _code(row) == "malformed" and row["url"] is None


# ── the identity ──────────────────────────────────────────────────────────────────────────────


def test_a_list_pages_coordinate_far_from_the_name_is_not_the_sites() -> None:
    far = _html(f"<p>{COORD}</p><p>{'x ' * 800}</p><p>El Tintal</p>")
    row, _ = _verify(Page(text=far))
    assert _code(row) == "identity" and "'tintal'" in row["reason"], row["reason"]
    near = _html(f"<p>{COORD}</p><p>{'x ' * 700}</p><p>El Tintal</p>")
    row, _ = _verify(Page(text=near))
    assert row["accepted"], row["reason"]
    before = _html(f"<p>El Tintal</p><p>{'x ' * 700}</p><p>{COORD}</p>")
    assert _verify(Page(text=before))[0]["accepted"]


def test_generic_and_short_words_of_the_name_do_not_identify_it() -> None:
    """ "Ban Chiang Archaeological Site": "ban" is too short and "site" generic - only "chiang" names
    the place."""
    name = "Ban Chiang Archaeological Site"
    assert W.distinctive_words(name) == ["chiang"]
    other = _html(f"<p>Ban Na archaeological site: {COORD}</p>")
    row, _ = _verify(Page(text=other), name=name)
    assert _code(row) == "identity", row["reason"]
    own = _html(f"<p>Ban Chiang: {COORD}</p>")
    assert _verify(Page(text=own), name=name)[0]["accepted"]


def _named(name: str, markup: str, coord_text: str, lat: float, lon: float) -> dict[str, Any]:
    candidate = _candidate(coord_text=coord_text, lat=lat, lon=lon)
    net = ScriptedNet({URL: Page(text=_html(markup))})
    return W.verify_candidate(net, site_id=SITE, name=name, candidate=candidate)


def test_a_type_word_of_the_name_does_not_identify_it() -> None:
    """ "Great", "dolmen", "temple", "grave", "field" say what kind of place a name is, not which: a
    page about another place uses them beside its own coordinates as readily - the Sassnitz town
    hall's "great view" next to the Great Dolmen of Dwasieden's P625, Luxor Temple for Karnak Temple
    Complex. Only the name's own words identify it."""
    assert W.distinctive_words("Great Dolmen of Dwasieden") == ["dwasieden"]
    assert W.distinctive_words("Karnak Temple Complex") == ["karnak"]
    assert W.distinctive_words("Jordbro Grave Field") == ["jordbro"]
    assert W.distinctive_words("Petroglyph Beach State Historic Park") == []
    assert {"tomb", "gate", "forum", "cave", "caves", "tower", "arch", "rock", "shelter"} <= (
        W.TYPE_WORDS
    )
    assert {"museum", "villa", "roman", "river", "menir"} <= W.TYPE_WORDS
    dwasieden = ("Great Dolmen of Dwasieden", "54.51500, 13.64100", 54.515, 13.641)
    sassnitz = (
        "<h1>Sassnitz town hall</h1><p>A great view over the harbour.</p><p>Coordinates: {}</p>"
    )
    row = _named(dwasieden[0], sassnitz.format(dwasieden[1]), *dwasieden[1:])
    assert _code(row) == "identity" and "['dwasieden']" in row["reason"], row["reason"]
    own = "<h1>The dolmen of Dwasieden</h1><p>Coordinates: {}</p>"
    assert _named(dwasieden[0], own.format(dwasieden[1]), *dwasieden[1:])["accepted"]
    karnak = ("Karnak Temple Complex", "25.69950, 32.63910", 25.6995, 32.6391)
    luxor = "<h1>Luxor Temple</h1> Coordinates: {}"
    row = _named(karnak[0], luxor.format(karnak[1]), *karnak[1:])
    assert _code(row) == "identity" and "['karnak']" in row["reason"], row["reason"]
    assert _named(karnak[0], f"<h1>Karnak</h1> {karnak[1]}", *karnak[1:])["accepted"]


def test_a_name_of_type_words_only_is_matched_whole() -> None:
    """ "Petroglyph Beach State Historic Park" has no word of its own: the whole name must stand
    beside the coordinates, not one of its words."""
    park = ("Petroglyph Beach State Historic Park", "56.47500, -132.37000", 56.475, -132.37)
    other = "<h1>Sandy Beach</h1><p>A state park with a historic cabin.</p><p>{}</p>"
    row = _named(park[0], other.format(park[1]), *park[1:])
    assert _code(row) == "identity" and "[]" in row["reason"], row["reason"]
    own = "<h1>Petroglyph Beach State Historic Park</h1><p>{}</p>"
    row = _named(park[0], own.format(park[1]), *park[1:])
    assert row["accepted"] and "'petroglyph beach state historic park'" in row["reason"]


def test_a_name_without_a_distinctive_word_is_matched_whole() -> None:
    """ "Ur" has no word of four letters: the whole folded name must stand there as a word, and
    "urban" is not "Ur"."""
    assert W.distinctive_words("Ur") == []
    urban = _html(f"<p>The urban centre: {COORD}</p>")
    assert _code(_verify(Page(text=urban), name="Ur")[0]) == "identity"
    ur = _html(f"<p>Ur: {COORD}</p>")
    assert _verify(Page(text=ur), name="Ur")[0]["accepted"]


def test_a_name_in_parentheses_on_the_page_identifies_the_site() -> None:
    page = _html(f"<p>Mirador Basin site 4 (El Tintal): {COORD}</p>")
    row, _ = _verify(Page(text=page))
    assert row["accepted"], row["reason"]


# ── the research and the file ────────────────────────────────────────────────────────────────


def _research_line(sid: str = SITE, candidates: list[Any] | None = None) -> dict[str, Any]:
    return {
        "site_id": sid,
        "candidates": [_candidate()] if candidates is None else candidates,
        "none_reason": None,
        "queries": ["El Tintal coordinates"],
    }


def _jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_the_research_file_is_refused_when_it_is_not_one_line_per_case(tmp_path: Path) -> None:
    known = {SITE: NAME}
    path = tmp_path / "RESEARCH.jsonl"
    _jsonl(path, [_research_line(OTHER)])
    with pytest.raises(inputs.InputError, match="is not one of the review cases"):
        W.read_research(path, known)
    _jsonl(path, [_research_line(), _research_line()])
    with pytest.raises(inputs.InputError, match="has a second line"):
        W.read_research(path, known)
    _jsonl(path, [{**_research_line(), "candidates": "none"}])
    with pytest.raises(inputs.InputError, match="is not a list"):
        W.read_research(path, known)


def _out(tmp_path: Path, candidates: list[Any]) -> Path:
    out = tmp_path / "out"
    _jsonl(out / "coords3" / "RESEARCH_INPUT.jsonl", [{"site_id": SITE, "name": NAME}])
    _jsonl(out / "coords3" / "RESEARCH.jsonl", [_research_line(candidates=candidates)])
    return out


def test_web_verify_writes_one_row_per_candidate(tmp_path: Path) -> None:
    other = "https://heritage.example/tintal"
    out = _out(tmp_path, [_candidate(), _candidate(url=other), "junk"])
    net = ScriptedNet({URL: Page(), other: Page(status=403)})
    counts = W.web_verify(net, out)
    rows = inputs.read_jsonl(out / "coords3" / "WEB_WITNESSES.jsonl")
    assert [(r["url"], _code(r)) for r in rows] == [
        (URL, "accepted"),
        (other, "http"),
        (None, "malformed"),
    ]
    assert counts == {
        "research_lines": 1,
        "candidates": 3,
        "outcome": {"accepted": 1, "http": 1, "malformed": 1},
    }
    assert {k for r in rows for k in r} == {
        "site_id",
        "url",
        "host",
        "final_url",
        "accepted",
        "reason",
        "witness",
    }


# ── the classifier's third kind ───────────────────────────────────────────────────────────────

WD_POINT = (17.574441, -89.995833)
EN_FAR = (17.61, -89.95)  # 6 km off the item's point: the two disagree
WEB_POINT = (17.57712, -89.99321)  # 400 m from the item's point, on no grid of it
STORED = (17.65691605256732, -89.92638063638016)


def _wd(point: tuple[float, float] = WD_POINT, **kw: Any) -> C.Witness:
    return C.Witness(
        "wikidata", *point, "https://www.wikidata.org/wiki/Q1", "P625", step=C.grid_of(*point), **kw
    )


def _en(point: tuple[float, float]) -> C.Witness:
    return C.Witness(
        "enwiki", *point, "https://en.wikipedia.org/wiki/El_Tintal", "en", step=C.grid_of(*point)
    )


def _web(host: str, point: tuple[float, float] = WEB_POINT) -> C.Witness:
    return C.Witness("web", *point, f"https://{host}/page", "quote", step=C.grid_of(*point))


def test_a_web_witness_is_named_by_its_host_and_one_host_is_one_witness() -> None:
    assert _web("www.maya.example").label == "web:maya.example" == _web("maya.example").label
    assert _wd().label == "wikidata"
    near = (WEB_POINT[0] + 0.002, WEB_POINT[1])  # 222 m: two points, one host
    assert not C.independent(_web("maya.example"), _web("www.maya.example", near))
    assert C.independent(_web("maya.example"), _web("heritage.example", near))


def test_the_subdomains_of_one_publisher_are_one_witness() -> None:
    """A witness is named by its host's registered domain: "whc.unesco.org" and "en.unesco.org" are
    one publisher, and under a country's shared second level ("co.uk", "gov.pk") the label before
    it is the publisher."""
    near = (WEB_POINT[0] + 0.002, WEB_POINT[1])  # 222 m: two points
    assert _web("whc.unesco.org").label == _web("en.unesco.org").label == "web:unesco.org"
    assert not C.independent(_web("whc.unesco.org"), _web("en.unesco.org", near))
    assert _web("www.megalithic.co.uk").label == "web:megalithic.co.uk"
    assert _web("antiquities.sindhculture.gov.pk").label == "web:sindhculture.gov.pk"
    assert _web("doam.gov.pk").label == "web:doam.gov.pk"
    assert C.independent(_web("doam.gov.pk"), _web("antiquities.sindhculture.gov.pk", near))
    assert _web("archaeology.sac.or.th").label == "web:sac.or.th"
    assert _web("kids.kiddle.co").label == "web:kiddle.co"


def test_two_witnesses_of_one_label_cannot_be_weighed_together() -> None:
    with pytest.raises(ValueError, match="share one label"):
        C.weigh(STORED, [_web("maya.example"), _web("maya.example", WD_POINT)])


def test_a_web_page_that_confirms_the_item_moves_the_site_to_the_items_point() -> None:
    verdict = C.weigh(STORED, [_web("maya.example"), _wd()])
    assert verdict["verdict"] == "move", verdict["reason"]
    assert verdict["to"].kind == "wikidata"
    assert verdict["agreeing"] == ["wikidata", "web:maya.example"]
    assert set(verdict["stored_to_witness_m"]) == {"wikidata", "web:maya.example"}


def test_the_article_outranks_a_web_page() -> None:
    en = (WD_POINT[0] - 0.003, WD_POINT[1] + 0.001)
    verdict = C.weigh(STORED, [_web("maya.example", (en[0] + 0.004, en[1])), _en(en)])
    assert verdict["verdict"] == "move" and verdict["to"].kind == "enwiki"


def test_a_third_witness_decides_between_two_that_disagree() -> None:
    en_near_web = (WEB_POINT[0] + 0.004, WEB_POINT[1])  # 445 m from the web page
    ws = [_wd(EN_FAR), _en(en_near_web), _web("maya.example")]
    verdict = C.weigh(STORED, ws)
    assert verdict["verdict"] == "move", verdict["reason"]
    assert verdict["agreeing"] == ["enwiki", "web:maya.example"]


def test_two_web_pages_of_two_hosts_pair_for_a_site_without_an_item() -> None:
    site = {
        "id": SITE,
        "name": NAME,
        "lat": STORED[0],
        "lon": STORED[1],
        "lat_text": repr(STORED[0]),
        "lon_text": repr(STORED[1]),
        "geom_text": "0101000020E6100000AAAA",
        "country": "Guatemala",
        "qid": None,
    }
    kw = {"origin": "T01/coords", "claims": {}, "labels": {}, "names": {}, "enwiki": {}}
    alone = C.classify_coordinate(site, None, shared={}, **kw)
    assert alone["reason"] == "no Wikidata item: no witness to ask"
    pair = [_web("maya.example"), _web("heritage.example", WD_POINT)]
    row = C.classify_coordinate(site, None, shared={}, web=pair, **kw)
    assert row["verdict"] == "move", row["reason"]
    assert row["new"]["from"] == "web:maya.example"
    assert {w["label"] for w in row["witnesses"]} == {"web:maya.example", "web:heritage.example"}


def test_a_web_page_that_copies_the_item_rounded_is_not_a_second_witness() -> None:
    rounded = (round(WD_POINT[0], 4), round(WD_POINT[1], 4))
    verdict = C.weigh(STORED, [_wd(), _web("maya.example", rounded)])
    assert verdict["verdict"] == "review"
    assert verdict["reason"] == ("the two witnesses are one: web is wikidata rounded to 4 decimals")


def test_two_witnesses_that_are_each_one_with_a_third_do_not_pair() -> None:
    """Two web pages 20 m either side of the item's point are each the item's point (one within an
    arcsecond of it), 40 m apart from each other - not one pairwise, but both one with the item:
    pairing them would count one statement three times. "Are one" is followed through the chain."""
    north = (round(WD_POINT[0] + 0.00018, 6), WD_POINT[1])
    south = (round(WD_POINT[0] - 0.00018, 6), WD_POINT[1])
    wd, a, b = _wd(), _web("maya.example", north), _web("heritage.example", south)
    assert not C.independent(wd, a) and not C.independent(wd, b) and C.independent(a, b)
    assert C.copy_groups([wd, a, b]) == [0, 0, 0]
    verdict = C.weigh(STORED, [wd, a, b])
    assert verdict["verdict"] == "review", verdict["reason"]
    assert (
        "web:maya.example and web:heritage.example are one: both are one with wikidata"
        in (verdict["reason"])
    )
    # a witness outside the chain still pairs with it
    en = _en((WD_POINT[0] + 0.004, WD_POINT[1]))  # 445 m away: independent of all three
    verdict = C.weigh(STORED, [wd, a, b, en])
    assert verdict["verdict"] == "move" and verdict["agreeing"] == ["wikidata", "enwiki"]


def test_a_p625_that_cites_the_web_pages_publisher_is_one_with_it() -> None:
    """Measured on the live run: Pusilha's P625 was imported from the Cebuano Wikipedia, whose
    geographic articles were generated from GeoNames, and its web witness is geonames.org; Mersinaki's
    P625 cites phrc.it by URL, and its web witness is phrc.it. Each pair is one source, however far
    GeoNames has drifted since - never a move."""
    assert C.cited_publishers({"P143": ["Q837615"]}) == ("geonames.org",)
    assert C.cited_publishers({"P248": ["Q830106"]}) == ("geonames.org",)
    assert C.cited_publishers({"P854": ["http://phrc.it/index.php?module=content"]}) == ("phrc.it",)
    assert C.cited_publishers({"P143": ["Q328"], "P4656": ["https://en.wikipedia.org/x"]}) == ()
    near = (WD_POINT[0] + 0.0006, WD_POINT[1])  # 67 m: two points, not one by distance
    wd, web = _wd(cites=("geonames.org",)), _web("www.geonames.org", near)
    assert not C.independent(wd, web) and not C.independent(web, wd)
    assert C.independent(_wd(), web)
    verdict = C.weigh(STORED, [wd, web])
    assert verdict["verdict"] == "review", verdict["reason"]
    assert verdict["reason"] == (
        "the two witnesses are one: P625 cites geonames.org, the web page's publisher"
    )
    # read from the cache as `witnesses` reads it
    claim = _claim(WD_POINT)
    claim["p625"]["references"] = {"P143": ["Q837615"]}
    ws, _ = C.witnesses("Q1", claims={"Q1": claim}, enwiki={})
    assert ws[0].cites == ("geonames.org",)
    row = _reweigh([_web("www.geonames.org", near)], claims={"Q1": claim})
    assert row["verdict"] == "review" and "P625 cites geonames.org" in row["reason"]


def test_two_agreeing_pairs_on_two_points_are_read_not_moved() -> None:
    far = (WD_POINT[0] + 0.03, WD_POINT[1])  # 3.3 km north
    ws = [_wd(), _web("maya.example"), _en(far), _web("heritage.example", (far[0] + 0.004, far[1]))]
    verdict = C.weigh(STORED, ws)
    assert verdict["verdict"] == "review", verdict["reason"]
    assert "but so do enwiki and web:heritage.example" in verdict["reason"]


def test_the_reason_names_every_pair_when_three_witnesses_do_not_agree() -> None:
    ws = [_wd(), _en(EN_FAR), _web("maya.example", (WD_POINT[0] - 0.05, WD_POINT[1]))]
    verdict = C.weigh(STORED, ws)
    assert verdict["verdict"] == "review"
    assert verdict["reason"].startswith("no two of the 3 witnesses are independent and agree: ")
    for pair in ("wikidata and enwiki disagree", "wikidata and web:maya.example disagree"):
        assert pair in verdict["reason"], verdict["reason"]


# ── reweigh ───────────────────────────────────────────────────────────────────────────────────


def _site(point: tuple[float, float] = STORED, **kw: Any) -> dict[str, Any]:
    return {
        "id": SITE,
        "name": NAME,
        "lat": point[0],
        "lon": point[1],
        "lat_text": repr(point[0]),
        "lon_text": repr(point[1]),
        "geom_text": "0101000020E6100000AAAA",
        "qid": "Q1",
        "enwiki": None,
        "country": "Guatemala",
        **kw,
    }


def _claim(point: tuple[float, float], **kw: Any) -> dict[str, Any]:
    return {
        "missing": False,
        "en_label": kw.get("label"),
        "p625": {
            "lat": point[0],
            "lon": point[1],
            "precision": 1e-06,
            "globe": "Q2",
            "rank": "normal",
            "references": {},
            "statements": 1,
        },
        "p31": ["Q839954"],
        "p189": kw.get("p189", []),
        "p195": kw.get("p195", []),
        "p276": [],
        "enwiki": None,
    }


LABELS = {"Q839954": "archaeological site"}
NAMES = {"Q1": {"labels": {"en": NAME}}}


def _atlas(country: str = "Guatemala") -> tuple[list[str], list[Any], shapely.STRtree]:
    geoms = [box(-92.3, 13.7, -88.2, 17.8)]
    return [country], geoms, shapely.STRtree(geoms)


def _delivered(site: Mapping[str, Any], claims: Mapping[str, Any]) -> dict[str, Any]:
    row = C.classify_coordinate(
        site,
        site["qid"],
        origin="T01/coords",
        claims=claims,
        labels=LABELS,
        names=NAMES,
        enwiki={},
        shared=C.shared_counts({SITE: site}),
    )
    return json.loads(json.dumps({**row, "k_class": "K5-over-10km", "coords_only": True}))


def _reweigh(
    web: list[C.Witness] | None = None, *, atlas: Any = None, wave1: set[str] | None = None, **kw
) -> dict[str, Any]:
    site = kw.pop("site", _site())
    claims = kw.pop("claims", {"Q1": _claim(WD_POINT)})
    delivered = kw.pop("delivered", None) or _delivered(site, claims)
    rows = W.reweigh_rows(
        [delivered],
        sites={SITE: site},
        claims=claims,
        labels=LABELS,
        names=NAMES,
        enwiki={},
        web={SITE: web or []},
        web_notes={},
        wave1=wave1 or set(),
        atlas=atlas or _atlas(),
    )
    return rows[0]


def test_reweigh_moves_a_case_a_web_page_confirms() -> None:
    row = _reweigh()
    assert (row["verdict"], row["reason"]) == ("review", "one witness only (wikidata)")
    row = _reweigh([_web("maya.example")])
    assert row["verdict"] == "move", row["reason"]
    assert (row["new"]["lat"], row["new"]["lon"]) == WD_POINT
    assert row["first_wave_reason"] == "one witness only (wikidata)"
    assert row["country_after_move"]["agrees"] and row["k_class"] == "K5-over-10km"


def test_a_move_into_another_country_is_held_for_review() -> None:
    row = _reweigh([_web("maya.example")], atlas=_atlas("Mexico"))
    assert row["verdict"] == "review" and "new" not in row
    assert "lies in ['Mexico'], not in the stored country 'Guatemala'" in row["reason"]
    assert (row["blocked_move"]["lat"], row["blocked_move"]["lon"]) == WD_POINT


def test_a_first_wave_site_is_never_reweighed() -> None:
    with pytest.raises(inputs.InputError, match="in the first wave's plan"):
        _reweigh([_web("maya.example")], wave1={SITE})


def test_only_a_review_case_is_reweighed() -> None:
    site, claims = _site(), {"Q1": _claim(WD_POINT)}
    moved = {**_delivered(site, claims), "verdict": "move"}
    with pytest.raises(inputs.InputError, match="is not a review case"):
        _reweigh(site=site, claims=claims, delivered=moved)


def test_reweigh_refuses_a_cache_that_does_not_reproduce_the_first_wave() -> None:
    site, claims = _site(), {"Q1": _claim(WD_POINT)}
    stale = {**_delivered(site, claims), "reason": "the two witnesses disagree: 3.00 km apart"}
    with pytest.raises(inputs.InputError, match="does not reproduce the first wave's verdict"):
        _reweigh(site=site, claims=claims, delivered=stale)


MUSEUM = (48.8611, 2.3358)
FIND = (27.629712, 38.549421)


def test_a_museum_object_keeps_the_first_waves_rule() -> None:
    """Its web witnesses join the find-spot's; it moves only when stored at the museum."""
    claims = {
        "Q1": _claim(MUSEUM, p189=["Q2"], p195=["Q3"]),
        "Q2": _claim(FIND),
        "Q3": _claim(MUSEUM),
    }
    web = [_web("museum.example", (FIND[0] + 0.003, FIND[1]))]
    atlas = ([NAME], [box(30, 20, 45, 35)], shapely.STRtree([box(30, 20, 45, 35)]))
    at_museum = _site(MUSEUM, country=NAME)
    row = _reweigh(web, site=at_museum, claims=claims, atlas=atlas)
    assert (row["verdict"], row["rule"]) == ("move", "museum-find-spot"), row["reason"]
    assert (row["new"]["lat"], row["new"]["lon"]) == FIND
    elsewhere = _site((30.0, 30.0), country=NAME)
    row = _reweigh(web, site=elsewhere, claims=claims, atlas=atlas)
    assert row["verdict"] == "review" and "not at its holding museum" in row["reason"]


def _accepted(url: str, point: tuple[float, float], sid: str = SITE) -> dict[str, Any]:
    return {
        "site_id": sid,
        "url": url,
        "host": W._host(url),
        "final_url": url,
        "accepted": True,
        "reason": "accepted: ...",
        "witness": {
            "kind": "web",
            "lat": point[0],
            "lon": point[1],
            "url": url,
            "quote": "q",
            "step": C.grid_of(*point),
        },
    }


def test_one_host_is_one_witness_and_a_host_with_two_points_gives_none() -> None:
    same = [
        _accepted("https://maya.example/a", WEB_POINT),
        _accepted("https://www.maya.example/b", WEB_POINT),
    ]
    web, notes = W.web_witnesses(same)
    assert [w.url for w in web[SITE]] == ["https://maya.example/a"]
    assert notes[SITE] == ["web:maya.example: 2 pages, one point"]
    two = [same[0], _accepted("https://maya.example/c", WD_POINT)]
    web, notes = W.web_witnesses(two)
    assert SITE not in web
    assert notes[SITE] == ["web:maya.example: 2 pages give 2 points - no witness from it"]


def test_an_accepted_row_verify_candidate_did_not_write_is_refused() -> None:
    row = _accepted("https://maya.example/a", WEB_POINT)
    wiki = _accepted("https://en.wikipedia.org/wiki/El_Tintal", WEB_POINT)
    with pytest.raises(inputs.InputError, match="witness is on en.wikipedia.org"):
        W.web_witnesses([wiki])
    archived = _accepted("https://web.archive.org/web/2020/https://maya.example/a", WEB_POINT)
    with pytest.raises(inputs.InputError, match="witness is on web.archive.org"):
        W.web_witnesses([archived])
    moved = {**row, "final_url": "https://other.example/"}
    with pytest.raises(inputs.InputError, match="is not the page read"):
        W.web_witnesses([moved])
    coarse = {**row, "witness": {**row["witness"], "step": 1.0}}
    with pytest.raises(inputs.InputError, match="step is not its numbers' grid"):
        W.web_witnesses([coarse])


def test_the_web_witnesses_must_be_the_verification_of_the_research() -> None:
    research = [_research_line(candidates=[_candidate(), "junk"])]
    rows = [{"site_id": SITE, "url": URL}, {"site_id": SITE, "url": None}]
    W.check_verified(research, rows)
    with pytest.raises(inputs.InputError, match="run `web-verify` again"):
        W.check_verified(research, rows[:1])
    with pytest.raises(inputs.InputError, match="run `web-verify` again"):
        W.check_verified(research, rows[::-1])


# ── the chain: research -> web-verify -> reweigh -> plan --wave 2 -> check/verify ───────────


def _cache(tmp_path: Path, site: Mapping[str, Any]) -> Path:
    cache = tmp_path / "cache"
    meta = {"fetched_at": "2026-09-23"}
    inputs.write_cache(cache / inputs.EXPORT_FILE, {SITE: site}, meta)
    inputs.write_cache(cache / inputs.CLAIMS_FILE, {"Q1": _claim(WD_POINT)}, meta)
    inputs.write_cache(cache / inputs.P31_FILE, LABELS, meta)
    inputs.write_cache(cache / inputs.NAMES_FILE, NAMES, meta)
    inputs.write_cache(cache / inputs.ENWIKI_FILE, {}, meta)
    return cache


WEB_URL = "https://www.mayaruins.example/el-tintal"
WEB_COORD = "17.57712, -89.99321"


def _chain(tmp_path: Path) -> tuple[Path, Path]:
    """A second wave of one site from the research to its plan, every step on disk."""
    site = _site()
    cache = _cache(tmp_path, site)
    out = _out(
        tmp_path,
        [_candidate(url=WEB_URL, lat=WEB_POINT[0], lon=WEB_POINT[1], coord_text=WEB_COORD)],
    )
    delivered = _delivered(site, {"Q1": _claim(WD_POINT)})
    _jsonl(out / "coords.jsonl", [delivered])
    _jsonl(out / "coords_plan" / "PLAN.jsonl", [{"site_id": OTHER}])
    page = _html(f"<h1>El Tintal</h1><p>GPS: {WEB_COORD}</p>")
    W.web_verify(ScriptedNet({WEB_URL: Page(text=page)}), out)
    return cache, out


def test_reweigh_writes_the_verdicts_and_the_counts_it_returns(tmp_path: Path) -> None:
    cache, out = _chain(tmp_path)
    counts = W.reweigh(cache, out, atlas=_atlas())
    assert counts == json.loads((out / "coords3" / "COUNTS.json").read_text(encoding="utf-8"))
    assert counts["verdict"] == {"move": 1}
    assert counts["candidate_outcome"] == {"accepted": 1}
    assert counts["cases_by_web_witnesses"] == {"1": 1}
    assert counts["reason"]["move"] == {
        "wikidata and web agree within N m (independent), the stored point is N km away": 1
    }
    rows = inputs.read_jsonl(out / "coords3" / "VERDICTS.jsonl")
    assert [r["verdict"] for r in rows] == ["move"]


def test_the_counted_reason_drops_the_publisher_and_the_numbers_only() -> None:
    """COUNTS.json groups reasons with their publishers and numbers taken out - and nothing more: a
    bracket closing after a publisher stays (measured: "one witness only (web" in the first count)."""
    assert W._reason_class("one witness only (web:maya.example)") == "one witness only (web)"
    assert (
        W._reason_class(
            "wikidata and web:topostext.org agree within 89 m (independent), the stored point is "
            "4.15 km away"
        )
        == "wikidata and web agree within N m (independent), the stored point is N km away"
    )
    assert W._reason_class("lies in ['Netherlands'], not") == "lies in [...], not"


def test_reweigh_refuses_a_research_input_that_is_not_the_review_cases(tmp_path: Path) -> None:
    cache, out = _chain(tmp_path)
    _jsonl(out / "coords3" / "RESEARCH_INPUT.jsonl", [{"site_id": OTHER, "name": "X"}])
    with pytest.raises(inputs.InputError, match="does not name the review cases"):
        W.reweigh(cache, out, atlas=_atlas())


class FakeDatabase:
    """A psql reader over the planned columns: it answers only the ids the SQL names, and the
    journal only for the stamp it expects."""

    def __init__(self, rows: list[P.Change], *, state: str, stamp: str) -> None:
        self.rows, self.state, self.stamp = rows, state, stamp

    def __call__(self, sql: str) -> list[dict[str, Any]]:
        if "FROM remediation_change_log" in sql:
            assert f"run_stamp = '{self.stamp}'" in sql, sql
            return [{"change_key": r.change_key} for r in self.rows]
        out = []
        for sid in re.findall(r"'([0-9a-f-]{36})'::uuid", sql):
            mine = {r.column: r for r in self.rows if r.site_id == sid}
            pick = "old_value" if self.state == "old" else "new_value"
            out.append(
                {
                    "site_id": sid,
                    "lat": getattr(mine["lat"], pick),
                    "lon": getattr(mine["lon"], pick),
                    "geom": getattr(mine["geom"], pick),
                    "geom_is_point": True,
                }
            )
        return out


def test_wave_two_renders_under_its_own_stamp_and_directory(tmp_path: Path) -> None:
    cache, out = _chain(tmp_path)
    W.reweigh(cache, out, atlas=_atlas())
    rows = P.write_files(out, P.WAVE2)
    directory = out / "coords_plan_wave2"
    assert P.WAVE2.plan_dir == "coords_plan_wave2" and directory.is_dir()
    assert not (out / "coords_plan" / "APPLY.sql").exists()
    apply_sql = (directory / "APPLY.sql").read_text(encoding="utf-8")
    undo = (directory / "ROLLBACK.sql").read_text(encoding="utf-8")
    stamp = "2026-09-23_owner-case-coordinates-wave2"
    assert P.WAVE2.run_stamp == stamp
    assert f"'{P.TEST_ID}', '{stamp}', r.change_key, 'two_source'" in apply_sql
    assert f"l.run_stamp = '{stamp}'" in apply_sql and f"'{P.RUN_STAMP}'" not in apply_sql
    assert f"'{stamp}-rollback'" in undo
    assert (directory / "REHEARSAL.sql").exists()
    # the evidence names the web page the move rests on
    evidence = {e["source"]: e for e in rows[0].evidence}
    assert evidence["witness:web:mayaruins.example"]["url"] == WEB_URL
    assert evidence["witness:web:mayaruins.example"]["quote"] == WEB_COORD
    plan_md = (directory / "PLAN.md").read_text(encoding="utf-8")
    assert f"[web:mayaruins.example]({WEB_URL}) {WEB_COORD}" in plan_md
    assert "run.py plan --wave 2" in plan_md and "run.py verify --wave 2" in plan_md
    assert "output/remediation/bcases/coords_plan_wave2/APPLY.sql" in plan_md
    assert plan_md.startswith(P.WAVE2.title)


def test_wave_two_check_and_verify_read_their_own_rows_and_stamp(tmp_path: Path) -> None:
    cache, out = _chain(tmp_path)
    W.reweigh(cache, out, atlas=_atlas())
    rows = P.write_files(out, P.WAVE2)
    stamp = P.WAVE2.run_stamp
    old = FakeDatabase(rows, state="old", stamp=stamp)
    assert P.run_readonly("check", out, reader=old, wave=P.WAVE2) == 0
    new = FakeDatabase(rows, state="new", stamp=stamp)
    assert P.run_readonly("verify", out, reader=new, wave=P.WAVE2) == 0
    assert P.run_readonly("verify", out, reader=old, wave=P.WAVE2) == 1


def test_wave_two_refuses_a_site_of_wave_one(tmp_path: Path) -> None:
    cache, out = _chain(tmp_path)
    W.reweigh(cache, out, atlas=_atlas())
    _jsonl(out / "coords_plan" / "PLAN.jsonl", [{"site_id": SITE}])
    with pytest.raises(P.PlanError, match="already planned"):
        P.write_files(out, P.WAVE2)
    assert P.WAVE2.earlier == (P.PLAN_DIR,)


def test_a_wave_without_a_move_has_nothing_to_plan(tmp_path: Path) -> None:
    _jsonl(tmp_path / "coords3" / "VERDICTS.jsonl", [{"site_id": SITE, "verdict": "review"}])
    _jsonl(tmp_path / "coords_plan" / "PLAN.jsonl", [{"site_id": OTHER}])
    with pytest.raises(P.PlanError, match="has nothing to plan"):
        P.write_files(tmp_path, P.WAVE2)


def test_the_command_line_plans_the_second_wave(tmp_path: Path) -> None:
    cache, out = _chain(tmp_path)
    W.reweigh(cache, out, atlas=_atlas())
    assert RUN.main(["plan", "--wave", "2", "--out", str(out)]) == 0
    assert (out / "coords_plan_wave2" / "APPLY.sql").exists()


def test_the_wave_belongs_to_the_plan_commands_alone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--wave` given to a command that has no wave is an error, not an option silently dropped."""
    for command in ("classify", "research", "web-verify", "reweigh"):
        with pytest.raises(SystemExit) as stopped:
            RUN.main([command, "--wave", "2", "--out", str(tmp_path)])
        assert stopped.value.code == 2, command
        assert "--wave belongs to plan, check and verify" in capsys.readouterr().err, command


def test_wave_one_still_renders_what_is_committed(tmp_path: Path) -> None:
    """Wave 1 is applied: its plan, statements and PLAN.md render as committed, byte for byte (the
    working copy's line endings aside - PLAN.md and PLAN.jsonl are not pinned to LF)."""
    shutil.copy(OUT / "coords.jsonl", tmp_path / "coords.jsonl")
    P.write_files(tmp_path)
    for name in ("APPLY.sql", "ROLLBACK.sql", "PLAN.jsonl", "PLAN.md"):
        rendered = (tmp_path / "coords_plan" / name).read_bytes()
        committed = (OUT / "coords_plan" / name).read_bytes().replace(b"\r\n", b"\n")
        assert rendered == committed, name
    assert P.WAVES[1] is P.WAVE1 and P.WAVE1.run_stamp == P.RUN_STAMP
    assert P.WAVE1.plan_dir == P.PLAN_DIR and P.WAVE1.flag == ""


# ── the delivered files ───────────────────────────────────────────────────────────────────────

WEB_FILE = OUT / "coords3" / "WEB_WITNESSES.jsonl"
delivered_web = pytest.mark.skipif(
    not WEB_FILE.exists(),
    reason=f"{WEB_FILE} is not delivered yet: `run.py web-verify` runs once the research "
    "(coords3/RESEARCH.jsonl) is in",
)


@delivered_web
def test_every_delivered_web_witness_holds_its_own_rules() -> None:
    rows = inputs.read_jsonl(WEB_FILE)
    research = W.read_research(OUT / "coords3" / "RESEARCH.jsonl", W.research_cases(OUT))
    W.check_verified(research, rows)
    for row in rows:
        if not row["accepted"]:
            continue
        w = row["witness"]
        assert W.listed_domain_of(W._host(w["url"]), W.WIKI_HOSTS) is None, w["url"]
        assert W.parse_coordinates(w["quote"]) == (w["lat"], w["lon"]), w
        assert w["step"] == C.grid_of(w["lat"], w["lon"])


needs_cache = pytest.mark.skipif(
    not (CACHE / inputs.NAMES_FILE).exists(),
    reason=f"the gitignored bcases cache is not at {CACHE}; set BCASES_CACHE to the main "
    "checkout's output/remediation/cache/bcases",
)


@needs_cache
def test_without_a_web_witness_the_second_wave_is_the_first(tmp_path: Path) -> None:
    """The 171 review cases, weighed with the real cache and no web witness, are the first wave's
    verdicts exactly - the reweigh's own reproduction check passes for every one of them."""
    out = tmp_path / "out"
    (out / "coords3").mkdir(parents=True)
    shutil.copy(OUT / "coords.jsonl", out / "coords.jsonl")
    shutil.copy(OUT / "coords3" / "RESEARCH_INPUT.jsonl", out / "coords3" / "RESEARCH_INPUT.jsonl")
    (out / "coords_plan").mkdir()
    shutil.copy(OUT / "coords_plan" / "PLAN.jsonl", out / "coords_plan" / "PLAN.jsonl")
    cases = W.research_cases(out)
    _jsonl(
        out / "coords3" / "RESEARCH.jsonl",
        [{"site_id": s, "candidates": [], "none_reason": "x", "queries": []} for s in cases],
    )
    (out / "coords3" / "WEB_WITNESSES.jsonl").write_text("", encoding="utf-8")
    counts = W.reweigh(CACHE, out, atlas=C.CC.load_countries())
    assert counts["cases"] == 171 and counts["verdict"] == {"review": 171}
    first = {r["site_id"]: r for r in inputs.read_jsonl(OUT / "coords.jsonl")}
    for row in inputs.read_jsonl(out / "coords3" / "VERDICTS.jsonl"):
        assert row["reason"] == first[row["site_id"]]["reason"] == row["first_wave_reason"]


@delivered_web
@needs_cache
def test_the_delivered_second_wave_is_reproduced(tmp_path: Path) -> None:
    out = tmp_path / "out"
    shutil.copytree(OUT, out)
    counts = W.reweigh(CACHE, out, atlas=C.CC.load_countries())
    assert counts == json.loads((OUT / "coords3" / "COUNTS.json").read_text(encoding="utf-8"))
    assert inputs.read_jsonl(out / "coords3" / "VERDICTS.jsonl") == inputs.read_jsonl(
        OUT / "coords3" / "VERDICTS.jsonl"
    )
