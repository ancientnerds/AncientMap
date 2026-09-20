"""T06 - the shape of every URL in the snapshot, offline.

A URL column can be wrong in ways that need no request to be seen: a missing scheme, a
value that is not a URL at all, a fragment where a page was meant, an HTML escape that
leaked out of an attribute, two URLs glued together by a newline, a Wikipedia page URL
inside an `<img src>`, a percent-escape cut in half, an upload whose hash directory is
not the hash of its own filename. Those are T06's business. Whether a URL still *answers*
is T07's (`t07_link_sweep`); this module opens no socket, so the two concerns stay
separable and a network wobble can never change T06's flag list.

**The field list is enumerated from the snapshot, not from the task's shortlist.** Every
column of the six snapshot tables was walked; every URL-bearing one is in `FIELDS`, with
what reads it and how many rows it has:

| field | what reads it | rows |
|---|---|---|
| `unified_sites.source_url` | the site's reference link (`docs/.../SITES_DB_REMEDIATION_2026-09.md:105`) | 5,004 |
| `unified_sites.thumbnail_url` | card hero `<img src>` (`GameCard.tsx:196`) | 5,004 |
| `card_stats.best_wiki_url` | card enrichment - **NULL on all rows** (plan 3.3) | 5,004 |
| `card_stats.commons_image` | card enrichment - **NULL on all rows** (plan 3.3) | 5,004 |
| `wiki_images.original_url` | image (re)fetch (`api/routes/public_v1.py:1723`) | 49,691 |
| `wiki_images.commons_page_url` | attribution, Phase-2 original re-fetch | 49,691 |
| `wiki_images.author_url` | attribution link (plan 11 legal exposure) | 49,691 |
| `wiki_images.license_url` | licence deed link (plan 11) | 49,691 |
| `site_content_links.content_url` | the site's reference links (`api/routes/sites.py:1243`) | 16,029 |
| `site_content_links.thumbnail_url` | nothing selects it (`api/routes/sites.py:1245`) | 16,029 |
| `raw_data.description_citations[].url` | the sources behind each description | 3,009 |

Columns that are NULL on **every** row (`card_stats.best_wiki_url`, `card_stats.commons_image`,
`site_content_links.thumbnail_url`, 26,037 values) carry no presence rule: they are
unpopulated enrichment columns that Phase 2/6 own, and a rule there would report the same
known gap 26,037 times instead of a URL defect.

**Root causes, not just symptoms.** Two producers explain most real defects, and they are
named here because a database fix is only durable if the producer agrees:
`pipeline/wiki_image_downloader.py::parse_attribution` takes `href="..."` out of the raw
HTML attribute without unescaping it (hence `&amp;` inside 8,218 stored URLs), and
`scripts/reindex_wiki_images.py:97` writes a *filesystem path* into `original_url`.

**Accepted shapes** - two things look wrong and are not, so they are code, not prose:
* `/data/images/wiki/<8 hex>/<file>`: written by `pipeline/static_exporter.py:363` and
  `api/routes/sites_html.py:132` for `thumbnail_url` (the 8 hex digits are checked against
  the site's own id), and by `scripts/reindex_wiki_images.py:97` for
  `wiki_images.original_url`, where `api/routes/wiki_images.py:177` handles the shape on
  purpose. The remote original of those 673 rows is not reconstructible offline: the file
  extension was normalised to `.webp`, so the Commons filename is gone.
* a fragment that is *not* empty (`.../wiki/Paphos_Archaeological_Park#Odeon`, and Google's
  `#:~:text=` text fragments) deep-links inside a real page. 9 `source_url` values carry one;
  only the 2 with an empty fragment (`...Kvitvy#`) are reported.

**Confidence ladder** - never inflated to make a finding apply:
* `SET` + `AUTHORITATIVE`: the target value is what a project module already writes for that
  exact shape (`wiki_image_downloader.py:439-441` for protocol-relative URLs, `:612-613` for
  the md5 directory layout, `:459-461` for `commons_page_url_for`), or the scheme is settled
  by our own data (an https URL for the same host already stored in the snapshot).
* `SET` + `WEAK`: a mechanically obvious repair whose correctness still needs one request
  (percent-escape repair, collapsing `//`, decoding `&amp;`, adding a scheme that no stored
  URL corroborates). Proposed, not auto-applicable.
* `REVIEW` + `UNVERIFIABLE`, no value: the replacement exists but nowhere in the snapshot -
  a truncated tail, the 42 sites with neither a source link nor a Wikidata anchor, a
  `license_url` holding a Commons file page. "Could not decide" is reported as such, never
  guessed.

One finding per row and column, most specific class first; the note names every class found
on that value. Severity follows the model's own definition - URL shape is `cosmetic` ("real
but invisible to a visitor") except a missing `source_url` and a `javascript:` value, which
are `moderate`. Classes: missing, not-a-url, javascript-scheme, fragment-only,
non-http-scheme, wrong-field, page-as-image, protocol-relative, control-characters,
html-entities, no-host, wikimedia-path, http-scheme, missing-scheme, double-slash,
bad-percent-encoding, truncated, truncated-tail, local-path-mismatch.
"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, unquote, urlsplit

from census.model import Confidence, Evidence, Finding, Proposal, Severity

if TYPE_CHECKING:
    from census.run import Context

TEST_ID = "T06"
NAME = "URL shapes"
DIMENSION = "URL"

# ---------------------------------------------------------------- shape patterns

SCHEME_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*):")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
#: an HTML character reference is never part of a URL
ENTITY_RE = re.compile(r"&(?:amp|lt|gt|quot|apos|nbsp|#\d+);")
BAD_PERCENT_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")
#: scheme-relative site path: pipeline/static_exporter.py:363, api/routes/sites_html.py:132
LOCAL_IMAGE_RE = re.compile(r"^/data/images/wiki/(?P<hex8>[0-9a-f]{8})/(?P<file>[^/]+)$")
#: a host with an optional path but no scheme - "www.historyhit.com/locations/dougga/"
BARE_HOST_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]*\.[a-z]{2,}(?::\d+)?(?:[/?#].*)?$", re.I)
#: a MediaWiki *page* URL (en.wikipedia.org/wiki/X), as opposed to a file URL
WIKI_PAGE_RE = re.compile(
    r"^https?://(?:[a-z-]+\.)?(?:wikipedia|wikimedia|wiktionary)\.org/wiki/", re.I
)
#: an original upload path: /wikipedia/<wiki>/<md5[0]>/<md5[:2]>/<filename>
UPLOAD_PATH_RE = re.compile(
    r"^/wikipedia/(?P<wiki>[^/]+)/(?P<h1>[0-9a-f])/(?P<h2>[0-9a-f]{2})/(?P<name>[^/]+)$"
)
#: the last character promises more ("...?id=", "...?src=", ".../foo/")
DANGLING_RE = re.compile(r"[=&?;]$")
TRAILING_SEPARATOR_RE = re.compile(r"[-_]$")
#: a "//" that is not an embedded URL's own separator (web.archive.org, CDN filter paths)
INNER_DOUBLE_SLASH_RE = re.compile(r"(?<!:)//")

UPLOAD_HOST = "upload.wikimedia.org"
COMMONS_HOST = "commons.wikimedia.org"
COMMONS_PAGE_PREFIX = f"https://{COMMONS_HOST}/wiki/"
CITATION_FIELD = "raw_data.description_citations[].url"

#: the two kinds that legitimately carry a site-relative /data/... path
_RELATIVE_OK_KINDS = ("image", "wiki-original")

#: class priority - the first class present on a value supplies the proposal
_PRIORITY = (
    "empty",
    "not-a-url",
    "javascript-scheme",
    "fragment-only",
    "non-http-scheme",
    "wrong-field",
    "page-as-image",
    "protocol-relative",
    "control-characters",
    "html-entities",
    "no-host",
    "wikimedia-path",
    "http-scheme",
    "missing-scheme",
    "double-slash",
    "bad-percent-encoding",
    "truncated",
    "truncated-tail",
    "local-path-mismatch",
)
_RANK = {name: i for i, name in enumerate(_PRIORITY)}


@dataclass(frozen=True)
class _Field:
    """One URL-bearing column: where it lives, what it feeds, how loud a defect is."""

    table: str
    column: str
    key: str
    kind: str  # link | image | wiki-original | wiki-page | attribution | licence | citations
    severity: Severity
    required: bool = False
    why: str = ""  #: what reads the field - quoted back in the evidence of a finding


FIELDS: tuple[_Field, ...] = (
    _Field(
        "unified_sites",
        "source_url",
        "id",
        "link",
        Severity.MODERATE,
        required=True,
        why="the site's own reference link (SITES_DB_REMEDIATION_2026-09.md:105)",
    ),
    _Field(
        "unified_sites",
        "thumbnail_url",
        "id",
        "image",
        Severity.COSMETIC,
        why="card hero <img src> (ancient-nerds-map/src/components/cards/GameCard.tsx:196)",
    ),
    _Field(
        "card_stats",
        "best_wiki_url",
        "site_id",
        "link",
        Severity.COSMETIC,
        why="card enrichment column, NULL on all 5,004 rows (plan 3.3)",
    ),
    _Field(
        "card_stats",
        "commons_image",
        "site_id",
        "link",
        Severity.COSMETIC,
        why="card enrichment column, NULL on all 5,004 rows (plan 3.3)",
    ),
    _Field(
        "wiki_images",
        "original_url",
        "site_id",
        "wiki-original",
        Severity.COSMETIC,
        required=True,
        why="original file address, used to (re)fetch the image (api/routes/public_v1.py:1723)",
    ),
    _Field(
        "wiki_images",
        "commons_page_url",
        "site_id",
        "wiki-page",
        Severity.COSMETIC,
        why="Commons file page for attribution and for Phase-2 original fetches",
    ),
    _Field(
        "wiki_images",
        "author_url",
        "site_id",
        "attribution",
        Severity.COSMETIC,
        why="attribution link; missing attribution is a plan-11 legal exposure",
    ),
    _Field(
        "wiki_images",
        "license_url",
        "site_id",
        "licence",
        Severity.COSMETIC,
        why="licence deed link (plan 11)",
    ),
    _Field(
        "site_content_links",
        "content_url",
        "site_id",
        "link",
        Severity.COSMETIC,
        required=True,
        why="the reference links shown on the site page (api/routes/sites.py:1243)",
    ),
    _Field(
        "site_content_links",
        "thumbnail_url",
        "site_id",
        "image",
        Severity.COSMETIC,
        why="never selected by a consumer (api/routes/sites.py:1245, pipeline/static_exporter.py:419)",
    ),
    _Field(
        "unified_sites",
        "raw_data",
        "id",
        "citations",
        Severity.COSMETIC,
        why="the sources cited behind the description (plan Phase 4)",
    ),
)


@dataclass(frozen=True)
class _Issue:
    klass: str
    severity: Severity
    proposal: Proposal
    confidence: Confidence
    note: str
    evidence: list[Evidence]
    proposed_value: Any = None


# ---------------------------------------------------------------- pure helpers


def _quote(text: str, limit: int = 300) -> str:
    return text if len(text) <= limit else text[:limit] + "..."


def _md5_dirs(name: str) -> tuple[str, str]:
    """Wikimedia's upload layout: `md5(filename)[0]` and `md5(filename)[0:2]`.

    `pipeline/wiki_image_downloader.py:612-613` computes exactly this, which is why a
    mismatch is repairable rather than merely reportable.

    MD5 IS LOAD-BEARING HERE - do not "upgrade" it. It is not a security hash, it is the
    directory-naming scheme in Wikimedia's own URLs, so any other digest breaks the
    comparison instead of strengthening it. Measured over 49,017 real `original_url` values
    from the snapshot:

        md5    -> matches the URL's /d1/d2/ directories in 49,016 cases (100.0%)
        sha256 -> matches in 178 cases (0.4%, i.e. coincidence)

    So sha256 would manufacture ~48,838 false URL mismatches. `usedforsecurity=False` is set
    because this is a filename layout, never an integrity claim; consequently no
    weak-hash rule applies (`.semgrep/` has none), and the `sast` gate is unaffected.
    """
    digest = hashlib.md5(unquote(name).encode("utf-8"), usedforsecurity=False).hexdigest()
    return digest[0], digest[:2]


def _as_absolute(value: str) -> str | None:
    """ "//host/x" -> "https://host/x"; None when the value has no usable scheme."""
    if value.startswith("//"):
        return "https:" + value
    return value if SCHEME_RE.match(value) else None


def _looks_like_host(value: str) -> bool:
    return bool(BARE_HOST_RE.match(value))


def _upload_name(value: str) -> str | None:
    """Filename of a well-formed `upload.wikimedia.org` original, else None."""
    split = urlsplit(value)
    if split.netloc != UPLOAD_HOST or "/thumb/" in split.path:
        return None
    match = UPLOAD_PATH_RE.match(split.path)
    return match.group("name") if match else None


def _derive_commons_page(original: str) -> str | None:
    """`https://commons.wikimedia.org/wiki/File:<name>`, quoted as the project quotes it.

    Same output as `pipeline/wiki_image_downloader.py:459-461::commons_page_url_for`.
    """
    name = _upload_name(original)
    if not name:
        return None
    return COMMONS_PAGE_PREFIX + quote("File:" + unquote(name), safe="")


def _strip_thumb(url: str) -> str:
    """`.../commons/thumb/a/ab/Name/300px-Name` -> `.../commons/a/ab/Name`."""
    split = urlsplit(url)
    parts = split.path.strip("/").split("/")
    if "thumb" not in parts:
        return url
    head, rest = parts[: parts.index("thumb")], parts[parts.index("thumb") + 1 :]
    if len(rest) > 3 and re.match(r"^\d+px-", rest[-1]):
        rest = rest[:-1]
    return f"{split.scheme}://{split.netloc}/" + "/".join(head + rest)


def _upload_dir_fix(value: str) -> str | None:
    """The same `upload.wikimedia.org` URL with md5-derived directories, if they differ.

    Works for originals and for thumb URLs (whose directories are the original's).
    """
    split = urlsplit(value)
    parts = split.path.strip("/").split("/")
    if len(parts) < 5 or parts[0] != "wikipedia":
        return None
    head, rest = parts[:2], parts[2:]
    thumb = rest[:1] == ["thumb"]
    if thumb:
        rest = rest[1:]
    if len(rest) < 3 or (rest[0], rest[1]) == _md5_dirs(rest[2]):
        return None
    h1, h2 = _md5_dirs(rest[2])
    path = "/" + "/".join(head + (["thumb"] if thumb else []) + [h1, h2] + rest[2:])
    return f"{split.scheme}://{split.netloc}{path}"


def _https_pool(ctx: Context) -> dict[str, tuple[str, str]]:
    """`host -> (an https URL already stored for it, the field holding it)`.

    "Does this host serve https?" cannot be answered offline - but it can be answered from
    the snapshot: if our own data already stores an https URL for the host, the host serves
    https. That is the whole evidence base for a scheme upgrade; no world knowledge and no
    request are involved.
    """
    pool: dict[str, tuple[str, str]] = {}
    for fld in FIELDS:
        label = CITATION_FIELD if fld.kind == "citations" else f"{fld.table}.{fld.column}"
        for row in ctx.snap.rows(fld.table):
            for value in _field_values(fld, row):
                if isinstance(value, str) and value.startswith("https://"):
                    pool.setdefault(urlsplit(value).netloc.lower(), (value, label))
    return pool


def _citation_urls(row: dict[str, Any]) -> list[str]:
    raw = row.get("raw_data")
    if not isinstance(raw, dict):
        return []
    out: list[str] = []
    for citation in raw.get("description_citations") or []:
        if isinstance(citation, dict) and isinstance(citation.get("url"), str) and citation["url"]:
            out.append(citation["url"])
    return out


def _field_values(fld: _Field, row: dict[str, Any]) -> list[Any]:
    """The one value of a plain column, or the several citation URLs of `raw_data`."""
    if fld.kind == "citations":
        return list(_citation_urls(row))
    return [row.get(fld.column)]


def _presence_required(fld: _Field, row: dict[str, Any]) -> bool:
    """Is an empty value a defect *for this row*?

    `commons_page_url` is required only where a remote original exists to point at; the 650
    disk-indexed rows whose `original_url` is a `/data/...` path cannot be reconstructed
    (the `.webp` normalisation dropped the original extension), so their empty page URL is
    not a shape defect this check can repair.
    """
    if fld.kind == "wiki-page":
        return _upload_name(row.get("original_url") or "") is not None
    return fld.required


# ---------------------------------------------------------------- generic checks


def _tail_issues(fld: _Field, value: str, stripped: str) -> list[_Issue]:
    """Does the value stop mid-expression? (`...&site=`, `.../researchgate-slug-`)"""
    if DANGLING_RE.search(stripped):
        return [
            _Issue(
                "truncated",
                fld.severity,
                Proposal.REVIEW,
                Confidence.UNVERIFIABLE,
                "ends mid-expression (dangling = & ? ;); the missing tail is not in the snapshot",
                [Evidence(source=f"snapshot:{fld.table}.{fld.column}", quote=_quote(value))],
            )
        ]
    if TRAILING_SEPARATOR_RE.search(stripped):
        return [
            _Issue(
                "truncated-tail",
                fld.severity,
                Proposal.REVIEW,
                Confidence.UNVERIFIABLE,
                "ends with - or _, which some publishers do on purpose; t07_link_sweep decides",
                [Evidence(source=f"snapshot:{fld.table}.{fld.column}", quote=_quote(value))],
            )
        ]
    return []


def _value_issues(fld: _Field, value: str, pool: dict[str, tuple[str, str]]) -> list[_Issue]:
    """Everything decidable from the value's own text: encoding, scheme, query, tail."""
    out: list[_Issue] = []
    stripped = value.strip()
    out.extend(_tail_issues(fld, value, stripped))

    if CONTROL_RE.search(value):
        out.append(
            _Issue(
                "control-characters",
                fld.severity,
                Proposal.REVIEW,
                Confidence.UNVERIFIABLE,
                "embedded control character(s) - the value holds more than one URL and the "
                "snapshot cannot say which was meant",
                [Evidence(source=f"snapshot:{fld.table}.{fld.column}", quote=_quote(value))],
            )
        )
    elif stripped != value:
        out.append(
            _Issue(
                "control-characters",
                fld.severity,
                Proposal.SET,
                Confidence.WEAK,
                "leading/trailing whitespace around an otherwise intact URL",
                [Evidence(source=f"snapshot:{fld.table}.{fld.column}", quote=_quote(value))],
                proposed_value=stripped,
            )
        )

    if ENTITY_RE.search(value):
        out.append(
            _Issue(
                "html-entities",
                fld.severity,
                Proposal.SET,
                Confidence.WEAK,
                "an HTML escape is stored inside the URL (parse_attribution takes href= verbatim); "
                "decoding is lossless but changes which query the server sees",
                [
                    Evidence(source=f"snapshot:{fld.table}.{fld.column}", quote=_quote(value)),
                    Evidence(
                        source="pipeline/wiki_image_downloader.py:435-438",
                        quote='href_match = re.search(r\'href="([^"]+)"\', author_raw) / '
                        "author_url = href_match.group(1)  # verbatim, never unescaped",
                    ),
                    Evidence(
                        source="pipeline/unified_loader.py:29-30",
                        quote="# Decode HTML entities like &#39; &amp; etc / text = html.unescape(text)",
                    ),
                ],
                proposed_value=html.unescape(value),
            )
        )

    match = SCHEME_RE.match(stripped)
    if match is None:
        if stripped.startswith("#"):
            out.append(
                _Issue(
                    "fragment-only",
                    fld.severity,
                    Proposal.CLEAR,
                    Confidence.AUTHORITATIVE,
                    "a bare fragment is not a locator: it resolves against the current page, "
                    "which for a stored link is nothing",
                    [
                        Evidence(source=f"snapshot:{fld.table}.{fld.column}", quote=_quote(value)),
                        Evidence(
                            source="docs/procedures/SITES_DB_REMEDIATION_2026-09.md:681",
                            quote="6. URL shapes: 7 non-http, 9 fragment URLs, 42 missing.",
                        ),
                    ],
                )
            )
        elif stripped.startswith("//"):
            out.append(
                _Issue(
                    "protocol-relative",
                    fld.severity,
                    Proposal.SET,
                    Confidence.AUTHORITATIVE,
                    "protocol-relative URL; the project restores the scheme for exactly this shape",
                    [
                        Evidence(source=f"snapshot:{fld.table}.{fld.column}", quote=_quote(value)),
                        Evidence(
                            source="pipeline/wiki_image_downloader.py:439-440",
                            quote='if author_url.startswith("//"): author_url = "https:" + author_url',
                        ),
                    ],
                    proposed_value="https:" + stripped,
                )
            )
        elif LOCAL_IMAGE_RE.match(stripped) and fld.kind in _RELATIVE_OK_KINDS:
            pass  # the site-relative image shape the project itself writes
        elif _looks_like_host(stripped):
            host = stripped.split("/", 1)[0].lower()
            known = pool.get(host)
            out.append(
                _Issue(
                    "missing-scheme",
                    fld.severity,
                    Proposal.SET,
                    Confidence.AUTHORITATIVE if known else Confidence.WEAK,
                    (
                        f"absolute URL without its scheme; {host} is already stored over https "
                        f"in {known[1]}"
                    )
                    if known
                    else "absolute URL without its scheme; https is the only scheme the project writes",
                    [
                        Evidence(source=f"snapshot:{fld.table}.{fld.column}", quote=_quote(value)),
                        Evidence(
                            source=(
                                f"snapshot:{known[1]} (same host over https)"
                                if known
                                else "pipeline/wiki_image_downloader.py:459-461 (project URLs are https)"
                            ),
                            url=known[0] if known else None,
                            quote=_quote(known[0]) if known else "https://<host>/...",
                        ),
                    ],
                    proposed_value="https://" + stripped,
                )
            )
        else:
            out.append(
                _Issue(
                    "not-a-url",
                    fld.severity,
                    Proposal.CLEAR,
                    Confidence.AUTHORITATIVE,
                    "not a locator at all (no scheme, no host); an empty field beats a wrong one",
                    [
                        Evidence(source=f"snapshot:{fld.table}.{fld.column}", quote=_quote(value)),
                        Evidence(
                            source="census/model.py (Finding docstring)",
                            quote='"clear the field" is an explicit, allowed proposal',
                        ),
                    ],
                )
            )
        return out  # a value without a scheme has no path or query left to check

    scheme = match.group(1).lower()
    if scheme == "javascript":
        out.append(
            _Issue(
                "javascript-scheme",
                Severity.MODERATE,
                Proposal.CLEAR,
                Confidence.AUTHORITATIVE,
                "javascript: where a locator belongs; this field is rendered into href/src",
                [
                    Evidence(source=f"snapshot:{fld.table}.{fld.column}", quote=_quote(value)),
                    Evidence(
                        source="docs/procedures/SITES_DB_REMEDIATION_2026-09.md:681",
                        quote="6. URL shapes: 7 non-http, 9 fragment URLs, 42 missing.",
                    ),
                ],
            )
        )
        return out
    if scheme not in ("http", "https"):
        out.append(
            _Issue(
                "non-http-scheme",
                fld.severity,
                Proposal.REVIEW,
                Confidence.UNVERIFIABLE,
                f"{scheme}: - not resolvable by the site's consumers and no replacement is "
                "decidable offline",
                [Evidence(source=f"snapshot:{fld.table}.{fld.column}", quote=_quote(value))],
            )
        )
        return out

    split = urlsplit(stripped)
    if not split.netloc:
        out.append(
            _Issue(
                "no-host",
                fld.severity,
                Proposal.REVIEW,
                Confidence.UNVERIFIABLE,
                "has a scheme but no host; the intended host is not recoverable offline",
                [Evidence(source=f"snapshot:{fld.table}.{fld.column}", quote=_quote(value))],
            )
        )
        return out

    body = split.path + (f"?{split.query}" if split.query else "")
    if INNER_DOUBLE_SLASH_RE.search(body):
        out.append(
            _Issue(
                "double-slash",
                fld.severity,
                Proposal.SET,
                Confidence.WEAK,
                "double slash inside the path; collapsing it is mechanical but a request must "
                "confirm the server agrees",
                [Evidence(source=f"snapshot:{fld.table}.{fld.column}", quote=_quote(value))],
                proposed_value=INNER_DOUBLE_SLASH_RE.sub("/", value),
            )
        )

    if BAD_PERCENT_RE.search(value):
        out.append(
            _Issue(
                "bad-percent-encoding",
                fld.severity,
                Proposal.SET,
                Confidence.WEAK,
                "a % not followed by two hex digits; a literal percent must be written %25",
                [Evidence(source=f"snapshot:{fld.table}.{fld.column}", quote=_quote(value))],
                proposed_value=BAD_PERCENT_RE.sub("%25", value),
            )
        )

    if scheme == "http":
        host = split.netloc.lower()
        known = pool.get(host)
        if known:
            out.append(
                _Issue(
                    "http-scheme",
                    fld.severity,
                    Proposal.SET,
                    Confidence.AUTHORITATIVE,
                    f"http where {host} already serves https in the snapshot ({known[1]})",
                    [
                        Evidence(source=f"snapshot:{fld.table}.{fld.column}", quote=_quote(value)),
                        Evidence(
                            source=f"snapshot:{known[1]} (same host over https)",
                            url=known[0],
                            quote=_quote(known[0]),
                        ),
                    ],
                    proposed_value="https://" + stripped[len("http://") :],
                )
            )
        else:
            out.append(
                _Issue(
                    "http-scheme",
                    fld.severity,
                    Proposal.REVIEW,
                    Confidence.UNVERIFIABLE,
                    "http, and no https URL for this host exists anywhere in the snapshot; "
                    "t07_link_sweep must confirm before a scheme change",
                    [Evidence(source=f"snapshot:{fld.table}.{fld.column}", quote=_quote(value))],
                )
            )
    return out


def _field_issues(fld: _Field, value: str, site_id: str) -> list[_Issue]:
    """Checks that only mean something for one kind of field."""
    local = LOCAL_IMAGE_RE.match(value.strip())
    if local is not None and fld.kind in _RELATIVE_OK_KINDS:
        # The project's own site-relative image path (`static_exporter.py:363`): its eight
        # hex digits are the site id, otherwise the row points at another site's file.
        if site_id.startswith(local.group("hex8")):
            return []
        return [
            _Issue(
                "local-path-mismatch",
                fld.severity,
                Proposal.REVIEW,
                Confidence.UNVERIFIABLE,
                f"site-relative image path of another site ({local.group('hex8')} is not "
                f"{site_id[:8]})",
                [
                    Evidence(source=f"snapshot:{fld.table}.{fld.column}", quote=_quote(value)),
                    Evidence(
                        source="pipeline/static_exporter.py:363",
                        quote='site["im"] = f"/data/images/wiki/{sid_short}/{row.hero_filename}"',
                    ),
                ],
            )
        ]

    absolute = _as_absolute(value)
    if absolute is None:
        return []
    split = urlsplit(absolute)
    host = split.netloc.lower()

    if fld.kind == "image" and WIKI_PAGE_RE.match(absolute):
        return [
            _Issue(
                "page-as-image",
                fld.severity,
                Proposal.REVIEW,
                Confidence.UNVERIFIABLE,
                "a wiki *page* URL where an image is expected; it renders nothing in <img src>",
                [
                    Evidence(source=f"snapshot:{fld.table}.{fld.column}", quote=_quote(value)),
                    Evidence(
                        source="ancient-nerds-map/src/components/cards/GameCard.tsx:196-197",
                        quote='<img src={card.thumbnail_url} alt={card.name} loading="lazy" />',
                    ),
                ],
            )
        ]

    if fld.kind == "licence" and host == COMMONS_HOST:
        return [
            _Issue(
                "wrong-field",
                fld.severity,
                Proposal.REVIEW,
                Confidence.UNVERIFIABLE,
                "license_url holds a Commons *file page*, not a licence deed; the deed URL is "
                "not derivable from the snapshot",
                [
                    Evidence(source=f"snapshot:{fld.table}.{fld.column}", quote=_quote(value)),
                    Evidence(
                        source="pipeline/connectors/protocols/mediawiki.py:196",
                        quote='"license_url": self._extract_metadata(extmetadata, "LicenseUrl")',
                    ),
                ],
            )
        ]

    if fld.kind == "wiki-page" and not absolute.startswith(COMMONS_PAGE_PREFIX + "File"):
        return [
            _Issue(
                "wrong-field",
                fld.severity,
                Proposal.REVIEW,
                Confidence.UNVERIFIABLE,
                "not a Commons file page; commons_page_url_for() writes "
                "https://commons.wikimedia.org/wiki/File%3A<name>, and no page is derivable "
                "for an image that does not live on Commons",
                [
                    Evidence(source=f"snapshot:{fld.table}.{fld.column}", quote=_quote(value)),
                    Evidence(
                        source="pipeline/wiki_image_downloader.py:459-461",
                        quote="return f\"https://commons.wikimedia.org/wiki/{urllib.parse.quote(file_title, safe='')}\"",
                    ),
                ],
            )
        ]

    if fld.kind not in ("image", "wiki-original"):
        return []

    if fld.kind == "wiki-original" and "/thumb/" in split.path:
        stripped = _strip_thumb(absolute)
        return [
            _Issue(
                "wikimedia-path",
                fld.severity,
                Proposal.SET,
                Confidence.AUTHORITATIVE,
                "a thumbnail URL stored as the original; the original is the same path without "
                "the /thumb/ segment and the size prefix",
                [
                    Evidence(source=f"snapshot:{fld.table}.{fld.column}", quote=_quote(value)),
                    Evidence(
                        source="pipeline/wiki_image_downloader.py:140-151 (thumb_to_original)",
                        quote='url = url.replace("/thumb/", "/") / url = url[:url.rfind("/")]',
                    ),
                ],
                proposed_value=_upload_dir_fix(stripped) or stripped,
            )
        ]

    if host != UPLOAD_HOST:
        if fld.kind == "wiki-original":
            return [
                _Issue(
                    "wrong-field",
                    fld.severity,
                    Proposal.REVIEW,
                    Confidence.UNVERIFIABLE,
                    f"image whose original sits on {host!r}; the intended file address is not "
                    "decidable offline",
                    [Evidence(source=f"snapshot:{fld.table}.{fld.column}", quote=_quote(value))],
                )
            ]
        return []

    fixed = _upload_dir_fix(absolute)
    if fixed is None:
        return []
    return [
        _Issue(
            "wikimedia-path",
            fld.severity,
            Proposal.SET,
            Confidence.AUTHORITATIVE,
            "directory is not md5(filename), which is the layout every Wikimedia upload lives in",
            [
                Evidence(source=f"snapshot:{fld.table}.{fld.column}", quote=_quote(value)),
                Evidence(
                    source="pipeline/wiki_image_downloader.py:611-613",
                    quote="md5 = hashlib.md5(encoded_name.encode()).hexdigest() / "
                    "original_url = f'https://upload.wikimedia.org/wikipedia/commons/"
                    "{md5[0]}/{md5[:2]}/{urllib.parse.quote(encoded_name)}'",
                ),
            ],
            proposed_value=fixed,
        )
    ]


def _empty_repair(fld: _Field, row: dict[str, Any]) -> _Issue | None:
    """The one empty value whose replacement the project itself computes."""
    if fld.kind != "wiki-page":
        return None
    original = row.get("original_url") or ""
    derived = _derive_commons_page(original)
    if derived is None:
        return None
    return _Issue(
        "empty",
        fld.severity,
        Proposal.SET,
        Confidence.AUTHORITATIVE,
        "no Commons page for an image that was fetched from Commons",
        [
            Evidence(source=f"snapshot:{fld.table}.original_url", quote=_quote(original)),
            Evidence(
                source="pipeline/wiki_image_downloader.py:459-461",
                quote="return f\"https://commons.wikimedia.org/wiki/{urllib.parse.quote(file_title, safe='')}\"",
            ),
        ],
        proposed_value=derived,
    )


def _findings(
    fld: _Field, row: dict[str, Any], value: Any, site_id: str, pool: dict[str, tuple[str, str]]
) -> list[Finding]:
    """The single finding for one (row, column, value), most specific class first."""
    if value is None or (isinstance(value, str) and not value.strip()):
        if not _presence_required(fld, row):
            return []
        repair = _empty_repair(fld, row)
        if repair is not None:
            issues = [repair]
        else:
            issues = [
                _Issue(
                    "empty",
                    fld.severity,
                    Proposal.REVIEW,
                    Confidence.UNVERIFIABLE,
                    f"empty and required: {fld.why}",
                    [
                        Evidence(source=f"snapshot:{fld.table}.{fld.column}", quote="(empty)"),
                        Evidence(
                            source="SITES_DB_REMEDIATION_2026-09.md:105",
                            quote="`source_url` | 42 missing",
                        ),
                    ],
                )
            ]
    elif not isinstance(value, str):
        issues = [
            _Issue(
                "not-a-url",
                fld.severity,
                Proposal.REVIEW,
                Confidence.UNVERIFIABLE,
                f"not text at all ({type(value).__name__})",
                [Evidence(source=f"snapshot:{fld.table}.{fld.column}", quote=str(value))],
            )
        ]
    else:
        issues = _value_issues(fld, value, pool) + _field_issues(fld, value, site_id)

    if not issues:
        return []
    issues.sort(key=lambda issue: _RANK[issue.klass])
    primary = issues[0]
    note = primary.note
    also = [issue.klass for issue in issues[1:]]
    if also:
        note = f"{note}; also: {', '.join(also)}"
    return [
        Finding(
            site_id=site_id,
            test_id=f"{TEST_ID}/{primary.klass}",
            field=CITATION_FIELD if fld.kind == "citations" else f"{fld.table}.{fld.column}",
            severity=primary.severity,
            dimension=DIMENSION,
            current_value=value,
            proposed_value=primary.proposed_value,
            proposal=primary.proposal,
            confidence=primary.confidence,
            evidence=primary.evidence,
            note=note,
        )
    ]


def run(ctx: Context) -> list[Finding]:
    """Every URL-bearing column of the snapshot, shape-checked. No network, no cache."""
    pool = _https_pool(ctx)
    findings: list[Finding] = []
    for fld in FIELDS:
        for row in ctx.snap.rows(fld.table):
            site_id = str(row[fld.key])
            for value in _field_values(fld, row):
                findings.extend(_findings(fld, row, value, site_id, pool))
    return findings
