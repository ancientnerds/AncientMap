"""The owner-case coordinates, wave 2: a third witness from the web, proven from the live page.

The first wave (`classify.weigh`, run stamp `2026-09-23_owner-case-coordinates`, 9 sites, applied)
left 171 cases `review`: one witness only, two that are one (a copy, a rounded copy, one point), two
that disagree, none. Research agents looked for a third, independent statement of where each site is
and wrote `coords3/RESEARCH.jsonl` - one line per site, candidates with a URL, the two numbers and the
page's own words (`coord_text`). **Those claims are untrusted.** This module proves each one from the
page itself or rejects it, and only a proven one becomes a witness.

## `web-verify` (network): one row per candidate in `coords3/WEB_WITNESSES.jsonl`

A candidate is accepted only if every check holds; the first that fails is its reason, and the reason
starts with the check's code (`wiki-host: ...`), so the counts group by it. The three host checks
(`wiki-host`, `refused-host`, `not-public`) run on the URL given and again on the URL a redirect
ends at:

* `malformed` - the candidate is not a URL, two finite numbers and a non-empty `coord_text`;
* `wiki-host` - the page is on Wikipedia, Wikimedia, Wikidata or a mirror of them (`WIKI_HOSTS`,
  matched by host and parent domain): their coordinates are the two witnesses already asked, and a
  mirror is a copy, not a third statement;
* `refused-host` - the project's own site (it publishes the stored point: circular) or a host on
  `pipeline/lyra/blocked_domains.txt` - the search lane's own policy, `search_evidence.excluded_because`;
* `not-public` - a loopback, private or link-local address is never asked (`is_public_http_url`, the
  check the phase-3 fetch stage uses; this workstation carries the production tunnels on localhost).
  The same check runs on every redirect hop, inside the transport (`PublicOnlyTransport`);
* `http` - the page was not served: an HTTP error (403, 404, 429, 503...) or a transport failure,
  recorded with its status. One request per page (`MAX_ATTEMPTS`), the project `USER_AGENT`, the
  census cache under `--cache`/web; a refusal is never asked again another way (CLAUDE.md);
* `not-html` - the answer is not an HTML page (a PDF is not read: no PDF reader is added);
* `bot-wall` - a challenge page served with a 200 (Cloudflare, Anubis, DataDome: `BOT_WALL_MARKERS`);
* `not-on-page` - `coord_text` does not occur in the page's text: `extract_text_from_html` (Lyra's page
  reader) and `html.unescape`, then `normalise` on both sides - NFKC, the prime, quote, degree and
  minus glyph variants unified, zero-width characters dropped, whitespace collapsed - compared
  without case;
* `grid-reference` - `coord_text` is a grid reference (OSGB, UTM, eastings and northings): not read;
* `unparsed` - `coord_text` does not hold exactly two coordinates this parser reads: signed decimal
  degrees (latitude first) or degrees with a hemisphere letter each (decimal, D M or D M S with the
  degree and prime signs or with spaces only, the letter before or after), with nothing else around
  them but labels and separators (`LABEL_WORDS`, the datum "WGS 84");
* `mismatch` - the parsed numbers are not the candidate's `lat`/`lon` within `MATCH_DEGREES` (1e-6):
  the numbers are the page's, not the agent's;
* `identity` - no distinctive word of the stored name (`classify.tokens`, words of at least
  `MIN_TOKEN` letters) and not the whole folded name occurs within `IDENTITY_WINDOW` (1,500)
  characters of the coordinates on the page: a list page's coordinate for another site is not this
  site's.

An accepted row carries the witness: kind `web`, the page's numbers (the parsed values), the URL the
page was read at, `coord_text` as the quote and `classify.grid_of` of the numbers as its step.

## `reweigh` (offline): `coords3/VERDICTS.jsonl` and `coords3/COUNTS.json`

Each of the 171 cases is classified again exactly as `classify.write_all` did - the same cache, the
same `classify_coordinate` - once without web witnesses, which must reproduce the delivered
`coords.jsonl` row (else the cache is not the one the first wave was decided from, and nothing is
written), and once with its accepted web witnesses, under the unchanged rule (`classify.weigh`: two
independent witnesses agree within the tolerance and the stored point lies outside it). A move whose
new point lies in another country than the stored one (`classify.country_after_move`) becomes
`review`: the country is a question for the country lanes, not something a coordinate write may
settle silently. A site of the first wave's plan is never in the second.
"""

from __future__ import annotations

import html
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from census.fetch import Fetcher, FetchError
from phase3.search_evidence import excluded_because
from vlm_pilot.common import write_jsonl

from bcases import classify as C
from bcases import inputs
from pipeline.lyra.blocked_domains import listed_domain_of
from pipeline.utils.http import is_public_http_url
from pipeline.utils.text import extract_text_from_html

#: Where the second wave's inputs and deliverables live, under `--out`.
COORDS3 = "coords3"
RESEARCH_INPUT = "RESEARCH_INPUT.jsonl"
RESEARCH = "RESEARCH.jsonl"
WEB_WITNESSES = "WEB_WITNESSES.jsonl"
VERDICTS = "VERDICTS.jsonl"
COUNTS = "COUNTS.json"
#: The first wave's plan: a site in it is never in the second.
WAVE1_PLAN = Path("coords_plan") / "PLAN.jsonl"

#: Wikipedia, Wikimedia and Wikidata, their tools, and the sites that republish them. Their
#: coordinates are the item's and the article's - the two witnesses already asked - or a copy of one:
#: never a third statement. Matched by host and parent domain (`listed_domain_of`).
WIKI_HOSTS = frozenset(
    {
        # Wikimedia's own projects
        "wikipedia.org",
        "wikimedia.org",
        "wikidata.org",
        "wikivoyage.org",
        "wiktionary.org",
        "wikisource.org",
        "wikibooks.org",
        "wikiquote.org",
        "wikinews.org",
        "wikiversity.org",
        "mediawiki.org",
        "wikimediafoundation.org",
        # Wikimedia's tool hosts: GeoHack prints the article's own coordinates
        "toolforge.org",
        "wmflabs.org",
        "wmcloud.org",
        # mirrors and republishers of Wikipedia and Wikidata
        "wikiwand.com",
        "dbpedia.org",
        "mapcarta.com",
        "latitude.to",
        "alchetron.com",
        "everybodywiki.com",
        "kiddle.co",
        "wiki2.org",
        "wikizero.com",
        "justapedia.org",
        "wikimili.com",
        "infogalactic.com",
        "unionpedia.org",
        "wikibrief.org",
        "dewiki.de",
        "zxc.wiki",
        "second.wiki",
        "howlingpixel.com",
        "wikiless.org",
        "wikipedia-on-ipfs.org",
        "thefreedictionary.com",
        "academic.ru",
        "en-academic.com",
        "trek.zone",
        "wiki.kidzsearch.com",
        "wiki.alquds.edu",
    }
)

#: A challenge page served with a 200 - the page asked for is not in it. Lower case; each marker is
#: specific to the challenge (a Cloudflare-served page carries `/cdn-cgi/` scripts normally, so that
#: path is no marker).
BOT_WALL_MARKERS = (
    ("<title>just a moment...</title>", "a Cloudflare challenge page"),
    ("_cf_chl_opt", "a Cloudflare challenge page"),
    ("attention required! | cloudflare", "a Cloudflare block page"),
    ('id="anubis_challenge"', "an Anubis challenge page"),
    ("making sure you&#39;re not a bot!", "an Anubis challenge page"),
    ("making sure you're not a bot!", "an Anubis challenge page"),
    ("captcha-delivery.com", "a DataDome challenge page"),
)
#: The media types read as a page. Anything else - a PDF above all - is rejected with its type.
HTML_TYPES = frozenset({"text/html", "application/xhtml+xml"})
#: One request per page: a refusal is the page's answer, not a reason to ask again.
MAX_ATTEMPTS = 1
#: How close the parsed numbers must be to the candidate's (degrees): the page's digits, not the
#: agent's rounding of them.
MATCH_DEGREES = 1e-6
#: How far from the coordinates (characters of the normalised page text, both sides) the site's name
#: must stand, and how long a word of the name must be to count as distinctive.
IDENTITY_WINDOW = 1500
MIN_TOKEN = 4

#: The glyphs a coordinate is typed with, unified before NFKC (which would turn a masculine ordinal
#: into "o", a superscript zero into "0" and a double prime into two primes) and again after it.
_GLYPHS = str.maketrans(
    {
        "\u00ba": "\u00b0",  # masculine ordinal indicator -> degree sign
        "\u02da": "\u00b0",  # ring above
        "\u2070": "\u00b0",  # superscript zero
        "\u2032": "'",  # prime
        "\u02b9": "'",  # modifier letter prime
        "\u2019": "'",  # right single quotation mark
        "\u2018": "'",  # left single quotation mark
        "\u201b": "'",  # single high-reversed-9 quotation mark
        "\u00b4": "'",  # acute accent
        "\u0060": "'",  # grave accent
        "\u02bc": "'",  # modifier letter apostrophe
        "\u2035": "'",  # reversed prime
        "\uff07": "'",  # fullwidth apostrophe
        "\u2033": '"',  # double prime
        "\u02ba": '"',  # modifier letter double prime
        "\u201c": '"',  # left double quotation mark
        "\u201d": '"',  # right double quotation mark
        "\u201e": '"',  # double low-9 quotation mark
        "\u201f": '"',  # double high-reversed-9 quotation mark
        "\u2036": '"',  # reversed double prime
        "\uff02": '"',  # fullwidth quotation mark
        "\u2212": "-",  # minus sign
        "\ufe63": "-",  # small hyphen-minus
        "\uff0d": "-",  # fullwidth hyphen-minus
        "\u200b": "",  # zero-width space
        "\u200c": "",  # zero-width non-joiner
        "\u200d": "",  # zero-width joiner
        "\u2060": "",  # word joiner
        "\ufeff": "",  # zero-width no-break space
        "\u00ad": "",  # soft hyphen
    }
)

#: Words that may stand around the two coordinates in `coord_text`: labels, nothing that could be a
#: hemisphere, a number or another place.
LABEL_WORDS = frozenset(
    """lat latitude lon long lng longitude coordinates coordinate coords coord gps location position
    wgs wgs84 decimal degrees dd dms and""".split()
)

# One coordinate: degrees (decimal, or whole with minutes and seconds after a degree sign) with a
# sign, or a hemisphere letter after it (`_SUFFIX`) or before it (`_PREFIX`).
_NUMBER = r"""
    (?P<sign>[+-])?
    (?<![\d.])(?P<deg>\d{1,3}(?:\.\d+)?)(?!\d)
    (?:\s*(?P<dg>°)
        (?:\s*(?P<min>\d{1,2}(?:\.\d+)?)(?!\d)\s*'
            (?:\s*(?P<sec>\d{1,2}(?:\.\d+)?)(?!\d)\s*")?
        )?
    )?
"""
_SUFFIX = re.compile(_NUMBER + r"(?:\s*(?P<post>[NSEW])(?![A-Za-z]))?", re.VERBOSE)
_PREFIX = re.compile(r"(?:(?<![A-Za-z])(?P<pre>[NSEW])\s*)?" + _NUMBER, re.VERBOSE)
# Degrees, minutes and seconds written with spaces only ("N17 13 22.0 W89 37 25.0"): read only with a
# hemisphere letter, which is what makes three numbers one coordinate.
_SPACED = (
    r"(?<![\d.])(?P<deg>\d{1,3})\s(?P<min>\d{1,2}(?:\.\d+)?)(?:\s(?P<sec>\d{1,2}(?:\.\d+)?))?"
    r"(?![\d.])"
)
_SPACED_SUFFIX = re.compile(_SPACED + r"\s?(?P<post>[NSEW])(?![A-Za-z])")
_SPACED_PREFIX = re.compile(r"(?<![A-Za-z])(?P<pre>[NSEW])\s?" + _SPACED)
#: The forms whose two coordinates carry a hemisphere letter each, tried in this order.
_LETTERED = (_SUFFIX, _PREFIX, _SPACED_SUFFIX, _SPACED_PREFIX)
#: A grid reference: its words, an OSGB square with its digits, a UTM zone with an easting, or a
#: projected metre value (five or more whole digits).
_GRID_WORDS = re.compile(
    r"\b(?:UTM|MGRS|NGR|OSGB|OSGR|easting|northing|grid\s+ref(?:erence)?)\b", re.IGNORECASE
)
_GRID_FORMS = re.compile(
    r"(?<![A-Za-z])[HNOST][A-HJ-Z]\s?\d{2,5}\s?\d{2,5}(?!\d)"
    r"|\b\d{1,2}\s?[C-HJ-NP-X]\s+\d{5,}"
    r"|(?<![\d.])\d{5,}(?!\d)"
)
_WGS84 = re.compile(r"\bwgs\s?84\b", re.IGNORECASE)


class Rejected(Exception):
    """A candidate that fails a check: `code` is the check, `detail` what it found."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


class NonPublicAddress(RuntimeError):
    """A request - the first or a redirect hop - to an address that is not public."""


class PublicOnlyTransport(httpx.BaseTransport):
    """An `httpx` transport that sends a request only to a public http(s) address.

    `httpx` hands every request to the transport, each redirect hop included, so a public page that
    redirects to `localhost` is refused here before a socket is opened (the phase-3 fetch stage does
    the same with a request hook; `census.fetch.Fetcher` takes a transport).
    """

    def __init__(self, inner: httpx.BaseTransport) -> None:
        self.inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if not is_public_http_url(url):
            raise NonPublicAddress(f"{url!r} is not a public http(s) address: never asked")
        return self.inner.handle_request(request)

    def close(self) -> None:
        self.inner.close()


def open_fetcher(root: Path, inner: httpx.BaseTransport) -> Fetcher:
    """The census fetcher the pages are read with: the project `USER_AGENT`, its cache under `root`,
    one request per page, every hop through `PublicOnlyTransport`."""
    return Fetcher(
        root=root, workers=1, max_retries=MAX_ATTEMPTS, transport=PublicOnlyTransport(inner)
    )


# ------------------------------------------------------------------------------------ the text
def normalise(text: str) -> str:
    """The form a page and a `coord_text` are compared in: glyph variants unified, NFKC,
    zero-width characters dropped, whitespace collapsed (case is kept; the comparison folds it)."""
    unified = unicodedata.normalize("NFKC", text.translate(_GLYPHS)).translate(_GLYPHS)
    return " ".join(unified.replace("''", '"').split())


def page_text(markup: str) -> str:
    """The page's text as a reader sees it: Lyra's reader, entities undone, `normalise`d."""
    return normalise(html.unescape(extract_text_from_html(markup)))


def bot_wall(markup: str) -> str | None:
    """Which challenge page `markup` is, or None."""
    low = markup.lower()
    return next((what for marker, what in BOT_WALL_MARKERS if marker in low), None)


# --------------------------------------------------------------------------------- the numbers
def _components(pattern: re.Pattern[str], text: str) -> list[re.Match[str]]:
    return list(pattern.finditer(text))


def _letter(match: re.Match[str]) -> str | None:
    groups = match.groupdict()
    return groups.get("pre") or groups.get("post")


def _degrees(match: re.Match[str]) -> float:
    """One component's value in degrees, signed; `Rejected` for a form this parser does not read."""
    groups = match.groupdict()
    deg, minutes, seconds = groups["deg"], groups["min"], groups["sec"]
    letter, sign = _letter(match), groups.get("sign")
    text = match.group(0).strip()
    if sign and letter:
        raise Rejected("unparsed", f"{text!r} has both a sign and a hemisphere letter")
    if minutes is not None and letter is None:
        raise Rejected("unparsed", f"{text!r}: a D M S value needs its hemisphere letter")
    if letter is None and "." not in deg and groups.get("dg") is None:
        raise Rejected("unparsed", f"{text!r} is a whole number, not a coordinate")
    if minutes is not None and "." in deg:
        raise Rejected("unparsed", f"{text!r} has decimal degrees and minutes")
    if seconds is not None and "." in minutes:
        raise Rejected("unparsed", f"{text!r} has decimal minutes and seconds")
    value = float(deg)
    for part, scale in ((minutes, 60.0), (seconds, 3600.0)):
        if part is not None:
            if float(part) >= 60.0:
                raise Rejected("unparsed", f"{text!r}: {part} is not below 60")
            value += float(part) / scale
    negative = sign == "-" or letter in ("S", "W")
    return -value if negative else value


def _leftover(text: str, matches: Sequence[re.Match[str]]) -> str:
    """`text` without the two coordinates: what may only be labels and separators."""
    out, last = [], 0
    for match in matches:
        out.append(text[last : match.start()])
        last = match.end()
    out.append(text[last:])
    return " ".join(out)


def parse_coordinates(coord_text: str) -> tuple[float, float]:
    """(lat, lon) from a normalised `coord_text`, or `Rejected` (`grid-reference`, `unparsed`). The
    datum's name ("WGS 84") is a label, not a number."""
    text = _WGS84.sub(" ", normalise(coord_text))
    grid = _GRID_WORDS.search(text) or _GRID_FORMS.search(text)
    if grid is not None:
        raise Rejected(
            "grid-reference",
            f"{grid.group(0)!r} in {text!r}: a grid reference (OSGB, UTM) is not read",
        )
    chosen: list[re.Match[str]] | None = None
    for pattern in _LETTERED:
        found = _components(pattern, text)
        if len(found) == 2 and all(_letter(m) for m in found):
            chosen = found
            break
    if chosen is None:
        found = _components(_SUFFIX, text)
        if len(found) == 2 and not any(_letter(m) for m in found):
            chosen = found
    if chosen is None:
        raise Rejected(
            "unparsed",
            f"{text!r} holds {len(found)} coordinate value(s), not two in one form "
            "(signed decimals, or degrees with a hemisphere letter each)",
        )
    rest = _leftover(text, chosen)
    stray = [w for w in re.findall(r"[^\W_]+", rest) if w.casefold() not in LABEL_WORDS]
    if stray:
        raise Rejected("unparsed", f"{text!r}: {stray} stand beside the two coordinates")
    values = [_degrees(m) for m in chosen]
    letters = [_letter(m) for m in chosen]
    if letters[0] is None:
        lat, lon = values
    else:
        axis = {
            ("N" if letter in ("N", "S") else "E"): v
            for letter, v in zip(letters, values, strict=True)
        }
        if len(axis) != 2:
            raise Rejected("unparsed", f"{text!r} names one axis twice: {letters}")
        lat, lon = axis["N"], axis["E"]
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise Rejected("unparsed", f"{text!r} is {lat}, {lon}: not a point on Earth")
    return lat, lon


# ----------------------------------------------------------------------------------- identity
def distinctive_words(name: str) -> list[str]:
    """The words of the stored name that say which place it is: `classify.tokens` (the generic words
    gone) of at least `MIN_TOKEN` letters."""
    return sorted(t for t in C.tokens(name) if len(t) >= MIN_TOKEN)


def named_near(hay: str, needle: str, name: str) -> str | None:
    """The word of `name` (or the whole folded name) that stands within `IDENTITY_WINDOW` characters
    of an occurrence of `needle` in `hay`, or None. Both are the case-folded normalised texts."""
    words, whole = distinctive_words(name), C.fold(name)
    start = hay.find(needle)
    while start >= 0:
        window = hay[max(0, start - IDENTITY_WINDOW) : start + len(needle) + IDENTITY_WINDOW]
        folded = C.fold(window, keep_parentheses=True)
        present = set(folded.split())
        for word in words:
            if word in present:
                return word
        if whole and f" {whole} " in f" {folded} ":
            return whole
        start = hay.find(needle, start + 1)
    return None


# ---------------------------------------------------------------------------------- one candidate
def _host(url: str) -> str | None:
    """The lower-case host of an http(s) URL, or None when it names none (the candidate is then
    `malformed`)."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    return parts.hostname.rstrip(".")


def _refuse_host(url: str, *, asked: str | None = None) -> None:
    """The host checks that need no request: a wiki or a mirror, our own site or a blocked host, an
    address that is not public. `asked` is the URL the request was sent to when `url` is the one a
    redirect ended at: the same checks hold for the page read, and the reason names both."""
    how = "" if asked is None else f"{asked} redirected to {url}: "
    host = _host(url)
    if host is None:
        raise Rejected("malformed", f"{how}{url!r} is not an http(s) URL with a host")
    wiki = listed_domain_of(host, WIKI_HOSTS)
    if wiki is not None:
        raise Rejected(
            "wiki-host", f"{how}{host} is {wiki}: Wikipedia, Wikidata or a mirror of them"
        )
    refused = excluded_because(url)
    if refused is not None:
        raise Rejected("refused-host", f"{how}{refused}")
    if not is_public_http_url(url):
        raise Rejected("not-public", f"{how}{url!r} is not a public http(s) address: never asked")


def candidate_url(candidate: Any) -> str | None:
    """The URL a candidate names, as its row records it (None when it names none)."""
    url = candidate.get("url") if isinstance(candidate, Mapping) else None
    return url if isinstance(url, str) else None


def _candidate_fields(candidate: Any) -> tuple[str, float, float, str]:
    if not isinstance(candidate, Mapping):
        raise Rejected("malformed", f"a candidate is a {type(candidate).__name__}, not an object")
    url, text = candidate.get("url"), candidate.get("coord_text")
    if not isinstance(url, str) or not url:
        raise Rejected("malformed", f"url {url!r} is not a URL")
    if not isinstance(text, str) or not normalise(text):
        raise Rejected("malformed", f"coord_text {text!r} is empty")
    numbers = []
    for key in ("lat", "lon"):
        value = candidate.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
        ):
            raise Rejected("malformed", f"{key} {value!r} is not a number")
        numbers.append(float(value))
    return url, numbers[0], numbers[1], text


def _read_page(net: Any, url: str, row: dict[str, Any]) -> tuple[str, str]:
    """(the URL the page was read at, its markup), or `Rejected` (`http`, a host check failing on the
    URL a redirect ended at, `not-html`, `bot-wall`); an answered request records its URL in `row`
    either way. `net` is
    `census.fetch.Fetcher` (`open_fetcher`): `get_text` raises `FetchError` on every error status
    but 404, which it returns as a value."""
    try:
        payload = net.get_text(url, ns="page")
    except FetchError as exc:
        raise Rejected("http", str(exc)) from None
    final = str(payload["url"])
    row["final_url"] = final
    if payload["error"]:
        raise Rejected("http", f"{final}: {payload['error']}")
    if final != url:
        _refuse_host(final, asked=url)
    headers = {str(k).lower(): str(v) for k, v in payload["headers"].items()}
    media = headers.get("content-type", "").split(";")[0].strip().lower()
    if media not in HTML_TYPES:
        raise Rejected("not-html", f"{final} answered {media or 'no content type'!r}, not HTML")
    markup = str(payload["text"])
    wall = bot_wall(markup)
    if wall is not None:
        raise Rejected("bot-wall", f"{final} answered {wall} (HTTP {payload['status']})")
    return final, markup


def _prove(net: Any, name: str, candidate: Any, row: dict[str, Any]) -> dict[str, Any]:
    """The witness a candidate proves, or `Rejected` at the first check that fails."""
    url, lat, lon, coord_text = _candidate_fields(candidate)
    _refuse_host(url)
    final, markup = _read_page(net, url, row)
    hay, needle = page_text(markup).casefold(), normalise(coord_text).casefold()
    if needle not in hay:
        raise Rejected("not-on-page", f"{coord_text!r} does not occur in the text of {final}")
    got_lat, got_lon = parse_coordinates(coord_text)
    if abs(got_lat - lat) > MATCH_DEGREES or abs(got_lon - lon) > MATCH_DEGREES:
        raise Rejected(
            "mismatch",
            f"{coord_text!r} reads {got_lat}, {got_lon}; the candidate says {lat}, {lon}",
        )
    word = named_near(hay, needle, name)
    if word is None:
        raise Rejected(
            "identity",
            f"no word of {name!r} {distinctive_words(name)} within {IDENTITY_WINDOW} characters "
            f"of {coord_text!r}",
        )
    row["reason"] = f"accepted: the page reads {got_lat}, {got_lon} and names the site ({word!r})"
    return {
        "kind": "web",
        "lat": got_lat,
        "lon": got_lon,
        "url": final,
        "quote": coord_text,
        "step": C.grid_of(got_lat, got_lon),
    }


def verify_candidate(net: Any, *, site_id: str, name: str, candidate: Any) -> dict[str, Any]:
    """One row of `WEB_WITNESSES.jsonl`: the candidate accepted with its witness, or its reason."""
    url = candidate_url(candidate)
    row: dict[str, Any] = {
        "site_id": site_id,
        "url": url,
        "host": _host(url) if url is not None else None,
        "final_url": None,
        "accepted": False,
        "reason": None,
        "witness": None,
    }
    try:
        witness = _prove(net, name, candidate, row)
    except Rejected as exc:
        row["reason"] = str(exc)
        return row
    row.update(accepted=True, witness=witness)
    return row


# ---------------------------------------------------------------------------------- the research
def read_research(path: Path, known: Mapping[str, str]) -> list[dict[str, Any]]:
    """`RESEARCH.jsonl`, one line per site of `known` (`{site_id: name}`) at most. A line for a site
    that is not a case, a second line for one site, or a line without its candidate list is refused:
    the file is someone else's answer, and a mistake in it is theirs to fix, not ours to guess."""
    lines = inputs.read_jsonl(path)
    seen: set[str] = set()
    for number, line in enumerate(lines, start=1):
        sid = line.get("site_id")
        if sid not in known:
            raise inputs.InputError(f"{path}:{number}: {sid!r} is not one of the review cases")
        if sid in seen:
            raise inputs.InputError(f"{path}:{number}: {sid} has a second line")
        seen.add(sid)
        if not isinstance(line.get("candidates"), list):
            raise inputs.InputError(f"{path}:{number}: `candidates` is not a list")
    return lines


def research_cases(out: Path) -> dict[str, str]:
    """`{site_id: name}` of the cases the research was given (`RESEARCH_INPUT.jsonl`)."""
    rows = inputs.read_jsonl(out / COORDS3 / RESEARCH_INPUT)
    return {str(r["site_id"]): str(r["name"]) for r in rows}


def verify_all(
    net: Any, research: Sequence[Mapping[str, Any]], cases: Mapping[str, str]
) -> list[dict[str, Any]]:
    """Every candidate of every research line, in file order."""
    return [
        verify_candidate(net, site_id=line["site_id"], name=cases[line["site_id"]], candidate=c)
        for line in research
        for c in line["candidates"]
    ]


def rejection_code(row: Mapping[str, Any]) -> str:
    return str(row["reason"]).split(":", 1)[0]


def web_verify(net: Any, out: Path) -> dict[str, Any]:
    """`web-verify`: read `RESEARCH.jsonl`, prove every candidate, write `WEB_WITNESSES.jsonl`."""
    cases = research_cases(out)
    research = read_research(out / COORDS3 / RESEARCH, cases)
    rows = verify_all(net, research, cases)
    write_jsonl(out / COORDS3 / WEB_WITNESSES, rows)
    return {
        "research_lines": len(research),
        "candidates": len(rows),
        "outcome": dict(sorted(Counter(rejection_code(r) for r in rows).items())),
    }


# ------------------------------------------------------------------------------------- reweigh
def check_verified(
    research: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]]
) -> None:
    """Refuse a `WEB_WITNESSES.jsonl` that is not the verification of this `RESEARCH.jsonl`: one row
    per candidate, in file order, naming the candidate's site and URL."""
    asked = [(line["site_id"], candidate_url(c)) for line in research for c in line["candidates"]]
    answered = [(row["site_id"], row["url"]) for row in rows]
    if asked != answered:
        raise inputs.InputError(
            f"{WEB_WITNESSES} holds {len(answered)} rows for the {len(asked)} candidates of "
            f"{RESEARCH}, or not in their order: run `web-verify` again"
        )


def web_witnesses(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, list[C.Witness]], dict[str, list[str]]]:
    """The accepted rows as witnesses, per site and ordered by label, and the notes on those left out.

    One host is one witness (`Witness.label`): pages of one host that give one point count once, and
    pages of one host that give two points give none - which of its two is meant is not ours to pick.
    An accepted row whose witness is not the page it read, sits on a wiki host or carries a step that
    is not its numbers' grid was not written by `verify_candidate`, and is refused.
    """
    by_label: dict[str, dict[str, list[C.Witness]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row["accepted"] is not True:
            continue
        sid, w = str(row["site_id"]), row["witness"]
        host = _host(str(w["url"]))
        if w["kind"] != "web" or w["url"] != row["final_url"] or host is None:
            raise inputs.InputError(f"{WEB_WITNESSES}: {sid}'s witness is not the page read: {w}")
        if listed_domain_of(host, WIKI_HOSTS) is not None:
            raise inputs.InputError(f"{WEB_WITNESSES}: {sid}'s witness is on {host}")
        if w["step"] != C.grid_of(w["lat"], w["lon"]):
            raise inputs.InputError(f"{WEB_WITNESSES}: {sid}'s step is not its numbers' grid")
        witness = C.Witness(
            "web", float(w["lat"]), float(w["lon"]), str(w["url"]), str(w["quote"]), step=w["step"]
        )
        by_label[sid][witness.label].append(witness)
    out: dict[str, list[C.Witness]] = {}
    notes: dict[str, list[str]] = {}
    for sid, by_host in sorted(by_label.items()):
        for label, ws in sorted(by_host.items()):
            points = {(w.lat, w.lon) for w in ws}
            if len(points) == 1:
                out.setdefault(sid, []).append(min(ws, key=lambda w: w.url))
                if len(ws) > 1:
                    notes.setdefault(sid, []).append(f"{label}: {len(ws)} pages, one point")
            else:
                notes.setdefault(sid, []).append(
                    f"{label}: {len(ws)} pages give {len(points)} points - no witness from it"
                )
    return out, notes


def reweigh_rows(
    delivered: Sequence[Mapping[str, Any]],
    *,
    sites: Mapping[str, Mapping[str, Any]],
    claims: Mapping[str, Any],
    labels: Mapping[str, Any],
    names: Mapping[str, Any],
    enwiki: Mapping[str, Any],
    web: Mapping[str, Sequence[C.Witness]],
    web_notes: Mapping[str, Sequence[str]],
    wave1: set[str],
    atlas: tuple[Any, Any, Any],
) -> list[dict[str, Any]]:
    """The second wave's verdict on each of the first wave's review cases (`delivered`)."""
    shared = C.shared_counts(sites)
    rows: list[dict[str, Any]] = []
    for old in delivered:
        sid = str(old["site_id"])
        if old["verdict"] != "review":
            raise inputs.InputError(f"{sid} ({old['name']}) is not a review case: {old['verdict']}")
        if sid in wave1:
            raise inputs.InputError(f"{sid} ({old['name']}) is in the first wave's plan")
        site = sites[sid]
        common: dict[str, Any] = {
            "origin": old["origin"],
            "claims": claims,
            "labels": labels,
            "names": names,
            "enwiki": enwiki,
            "shared": shared,
        }
        again = C.classify_coordinate(site, site.get("qid"), **common)
        first = {k: v for k, v in old.items() if k not in ("k_class", "coords_only")}
        if json.loads(json.dumps(again)) != first:
            raise inputs.InputError(
                f"{sid} ({old['name']}): the cache does not reproduce the first wave's verdict - "
                "it is not the cache coords.jsonl was classified from"
            )
        row = C.classify_coordinate(site, site.get("qid"), web=web.get(sid, ()), **common)
        row.update({k: old[k] for k in ("k_class", "coords_only") if k in old})
        row["first_wave_reason"] = old["reason"]
        row["web_notes"] = list(web_notes.get(sid, ()))
        if row["verdict"] == "move":
            country = C.country_after_move(
                str(row["country"]), row["new"]["lat"], row["new"]["lon"], atlas
            )
            row["country_after_move"] = country
            if not country["agrees"]:
                blocked = {**row.pop("new"), "km": row.pop("moved_km")}
                row.update(
                    verdict="review",
                    blocked_move=blocked,
                    reason=f"{row['reason']}; but the new point lies in {country['polygon']}, not "
                    f"in the stored country {country['stored']!r} - a country question first",
                )
        rows.append(row)
    return rows


def _reason_class(reason: str) -> str:
    """A reason with its numbers, lists and web hosts taken out, for counting."""
    reason = re.sub(r"web:[^\s,;]+", "web", reason)
    reason = re.sub(r"\[[^\]]*\]", "[...]", reason)
    return re.sub(r"[\d.]+ (k?m)\b", r"N \1", reason)


def summarise(
    rows: Sequence[Mapping[str, Any]],
    web_rows: Sequence[Mapping[str, Any]],
    research: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """`coords3/COUNTS.json`: every key a JSON key, so what `reweigh` returns is what it writes."""
    with_web = Counter(sum(1 for w in r.get("witnesses", ()) if w["kind"] == "web") for r in rows)
    return {
        "cases": len(rows),
        "research_lines": len(research),
        "research_none_reason": sum(1 for line in research if line.get("none_reason")),
        "candidates": len(web_rows),
        "candidate_outcome": dict(sorted(Counter(rejection_code(r) for r in web_rows).items())),
        "cases_by_web_witnesses": {str(n): with_web[n] for n in sorted(with_web)},
        "verdict": dict(sorted(Counter(str(r["verdict"]) for r in rows).items())),
        "reason": {
            verdict: dict(
                sorted(
                    Counter(
                        _reason_class(r["reason"]) for r in rows if r["verdict"] == verdict
                    ).items()
                )
            )
            for verdict in sorted({str(r["verdict"]) for r in rows})
        },
        "moves_held_for_country": sum(1 for r in rows if "blocked_move" in r),
    }


def reweigh(cache: Path, out: Path, *, atlas: tuple[Any, Any, Any]) -> dict[str, Any]:
    """`reweigh`: write `coords3/VERDICTS.jsonl` and `coords3/COUNTS.json`; return the counts."""
    cases = research_cases(out)
    delivered = [r for r in inputs.read_jsonl(out / "coords.jsonl") if r["verdict"] == "review"]
    if {str(r["site_id"]) for r in delivered} != set(cases):
        raise inputs.InputError(
            f"{RESEARCH_INPUT} does not name the review cases of coords.jsonl: they are not one set"
        )
    research = read_research(out / COORDS3 / RESEARCH, cases)
    web_rows = inputs.read_jsonl(out / COORDS3 / WEB_WITNESSES)
    check_verified(research, web_rows)
    web, notes = web_witnesses(web_rows)
    wave1 = {str(r["site_id"]) for r in inputs.read_jsonl(out / WAVE1_PLAN)}
    rows = reweigh_rows(
        delivered,
        sites=inputs.load_sites(cache),
        claims=inputs.read_cache(cache / inputs.CLAIMS_FILE),
        labels=inputs.read_cache(cache / inputs.P31_FILE),
        names=inputs.read_cache(cache / inputs.NAMES_FILE),
        enwiki=inputs.read_cache(cache / inputs.ENWIKI_FILE),
        web=web,
        web_notes=notes,
        wave1=wave1,
        atlas=atlas,
    )
    counts = summarise(rows, web_rows, research)
    write_jsonl(out / COORDS3 / VERDICTS, rows)
    (out / COORDS3 / COUNTS).write_text(
        json.dumps(counts, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    return counts
