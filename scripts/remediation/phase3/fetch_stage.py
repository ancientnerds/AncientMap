"""Stage "fetch" of the Phase-3 runner: collect the evidence the finder stage reads.

The pilot (`output/remediation/phase3_pilot/`) ran 76 fetches over 5 sites and measured what
they bought: 2,343 KB delivered for a 200, 19 non-200 answers (403 x8, 404 x3, transport
failure x5, 504 x2, 429 x1 - **one request in four bought nothing**), and two raw OSM bbox
dumps that were 1.0 MB of the 2.34 MB total, fetched only to find one or two named features in
a 2 km box (`COST.md` §3, §7). Decision 12 (`phase3_worklist/FINDER_BRIEF.md`, quoted in
`BATCH_PLAN.md`) turned those measurements into two binding rules, both enforced here:

1. **A 60 KB per-page cap.** `MAX_PAGE_BYTES` states the arithmetic, because the source says
   "60 KB" and never a byte count.
2. **Named features, never a raw geometry dump.** `assert_named_feature` refuses the URL shape
   the pilot measured as the two expensive pages (`api.openstreetmap.org/api/0.6/map?bbox=`)
   and the Overpass spelling of the same thing (`out geom`), and the only Overpass query this
   module builds is a name-filtered one around the site's *stored* point (4.1 KB and 287 bytes
   for the same box that cost 400 KB as a dump).

What a fetch writes, and where the pilot's shape is mirrored:

* **One line per fetch through `ledger.append`**, with the url, the site (through `label`), the
  observed status and the byte count. A non-2xx is *data* - the pilot's 403/404/504/429 all got
  recorded and the run continued - so it is recorded, never raised.
* **One evidence file per fetch**, under `<run_dir>/<batch_id>/evidence/<site_id>%2F<feature>.txt`,
  URL-encoded exactly like the pilot's `evidence/` names (`urllib.parse.quote(label, safe="")`
  in `phase3_pilot/http_get.py`), holding the bytes actually read.

Two deliberate deviations from the pilot's log shape, both named because they are not free:

* The pilot's `fetch_log.jsonl` line carries `final_url`; `phase3.ledger.Entry` (piece 1, frozen
  line shape) has no field for it, and a redirect is followed by the transport anyway. The line
  records the URL that was *asked for*; the final URL is not recorded anywhere. Adding it means
  changing piece 1's ledger contract, which this piece does not do.
* The pilot's `label` was a hand-written site tag ("Satsurblia/wikidata"). Here it is
  `f"{site_id}/{feature}"`, because the batch input carries the `site_id` and no stable short
  name, and a label derived from the mutable `name` column would move between runs.

On "stage 'fetch'": the fetch line is written with `kind="fetch"` (`LedgerKind.FETCH`, the
ledger's own spelling) and `stage` set to the *audit* stage that asked for it
(`Stage.FINDER`/`Stage.REVIEWER`). Writing the string `"fetch"` into the ledger's `stage` field
is not possible without changing `model.Stage`, and it would collapse the dimension the pilot
reports with: `COST.md` §1 splits its 76 fetches into 62 finder + 14 reviewer **by the `stage`
field**, and `ledger.summarise` groups by stage. So the line carries the string "fetch" as its
`kind`, which is what a reader of `LEDGER.jsonl` sees on every fetch row.

What this layer does not do, stated so it is not mistaken for covered: it does not parse the
evidence it stores (that is the finder's job, and the pilot's warning is that reading the two
OSM dumps instead of parsing them would have cost ~3x the plan's token anchor), and it does not
retry. One target is one fetch and one ledger line: the pilot's retried 504 appears as a second
line in its own log, and a retry the ledger cannot see would be exactly the invisible cost this
ledger exists to replace the plan's two 2x-apart anchors with.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from urllib.parse import quote, unquote, urlencode

import httpx

# Dual use: `python -m phase3.fetch_stage` and `python scripts/remediation/phase3/fetch_stage.py`.
# The package is not installed, so the parent directory must be importable first (same shim as
# `run.py`); `census` is the sibling package that solved HTTP fetching for this project already.
if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from census.fetch import USER_AGENT  # noqa: E402  - the project's one User-Agent string

from phase3 import ledger as L  # noqa: E402
from phase3.model import Stage  # noqa: E402
from phase3.run import InputError  # noqa: E402  - one spelling per concept, not a second

#: The binding per-page cap (decision 12; `COST.md` §7 item 1). **The sources say "60 KB" and
#: never a byte count.** 60 x 1024 = **61,440 bytes** is my reading of "60 KB" (binary KB);
#: the decimal reading, 60 x 1000 = 60,000, is not stated anywhere. That is an interpretation,
#: not a measurement, and it is the only number in this module that is read off a phrase
#: rather than off the pilot's log.
MAX_PAGE_BYTES = 60 * 1024

#: Radius of the named-feature Overpass query, in metres. `COST.md` §3 measures the box the two
#: dumps covered as "a 2 km box"; the pilot's own named-feature queries used `around:600` and
#: `around:2000` metres (`fetch_log.jsonl`: `Petroglyph/overpass_stored_features`,
#: `Petroglyph/overpass_beach`). This is the pilot's 2 km, not a new guess.
NAMED_FEATURE_RADIUS_M = 2000

OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
WIKIPEDIA_ENDPOINT = "https://en.wikipedia.org/w/api.php"
WIKIDATA_ENDPOINT = "https://www.wikidata.org/w/api.php"

#: Feature slugs. The first two are the pilot's own label suffixes (`fetch_log.jsonl`:
#: `Satsurblia/enwiki`, `Karpasia/wd_kition_label`); `overpass_named` names the query shape the
#: pilot used for the same job under `overpass_bbox`/`overpass_stored_features`, kept distinct
#: from the dumps those labels also covered.
FEATURE_ENWIKI = "enwiki"
FEATURE_WIKIDATA_SEARCH = "wikidata_search"
FEATURE_OVERPASS_NAMED = "overpass_named"

#: Which features a finding's field buys. Every field named by the finder brief's method §1 is
#: here, so an unknown field is a raise and not a silently unfetched site.
FEATURES_FOR_FIELD: dict[str, tuple[str, ...]] = {
    "lat/lon": (FEATURE_ENWIKI, FEATURE_OVERPASS_NAMED),
    "name": (FEATURE_ENWIKI, FEATURE_WIKIDATA_SEARCH),
    "country": (FEATURE_ENWIKI,),
    "description": (FEATURE_ENWIKI,),
    "card_description": (FEATURE_ENWIKI,),
}

#: Census check families that buy **no** fetch at all (decision 12: "T02 is one human
#: vocabulary decision plus a short exception list, not 117 reviews"; `COST.md` §7 item 5
#: measured the three T02 findings of the pilot: none was a data error). A finder run per T02
#: finding would be money burnt, so no target is built for them - and the tally of that
#: decision is visible in the report as a site with fewer targets than findings.
NO_FETCH_PREFIXES = frozenset({"T02"})

#: URL shapes the pilot measured as raw geometry dumps. `api/0.6/map?bbox=` delivered 598 KB
#: and 400 KB; `out geom` is Overpass's spelling of the same thing. Both are refused.
RAW_GEOMETRY_MARKERS = ("/api/0.6/map?", "out geom", "out:geom")


class TransportFailure(RuntimeError):
    """No response arrived at all (DNS, connect, reset, timeout mid-body).

    Raised, never turned into an empty result: a caller must be able to tell "answered with
    nothing usable" from "could not ask" (`census/fetch.py` makes the same distinction).
    """


class RawGeometryRefused(ValueError):
    """A URL asks for raw geometry. Decision 12 forbids it; see `assert_named_feature`."""


class EvidenceConflict(RuntimeError):
    """An evidence file for this (site, feature) exists and holds *different* bytes."""


@dataclass(frozen=True)
class FetchedPage:
    """One answer from the wire. `body` is what was actually read, capped."""

    status: int
    final_url: str
    body: bytes
    truncated: bool

    @property
    def ok(self) -> bool:
        """2xx. A non-2xx is a measured outcome, not an error: it is recorded as data."""
        return 200 <= self.status < 300


@runtime_checkable
class Fetcher(Protocol):
    """The seam. Anything with this method can stand in for the network."""

    def get(self, url: str) -> FetchedPage:
        """Fetch `url`, or raise `TransportFailure` if no response arrives."""
        ...


def _read_capped(chunks: Iterable[bytes]) -> tuple[bytes, bool]:
    """Read at most `MAX_PAGE_BYTES`, **stopping the stream** at the cap.

    Truncation is a stop, not a slice: the body is never buffered in full and then cut. The
    pilot's two dumps (598 KB, 400 KB) are exactly the pages that must not be pulled over the
    wire to be thrown away, and a test that counts the bytes the transport actually yielded
    fails if this ever becomes read-then-slice.

    A page whose body is exactly `MAX_PAGE_BYTES` is reported `truncated=True`: telling an
    exactly-capped page from a cut one requires reading past the cap, which is the thing the
    cap forbids.
    """
    body = bytearray()
    for chunk in chunks:
        room = MAX_PAGE_BYTES - len(body)
        if len(chunk) > room:
            body.extend(chunk[:room])
            return bytes(body), True
        body.extend(chunk)
        if len(body) == MAX_PAGE_BYTES:
            return bytes(body), True
    return bytes(body), False


class HttpFetcher:
    """The real client: httpx, a descriptive User-Agent, redirects followed, cap enforced.

    `transport` is the injectable seam (`census/fetch.py` takes an `httpx.BaseTransport` the
    same way): tests pass `httpx.MockTransport` or a counting stream and never open a socket.
    """

    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 40.0,
        user_agent: str = USER_AGENT,
    ) -> None:
        self._client = httpx.Client(
            transport=transport,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": user_agent, "Accept": "*/*"},
        )

    def get(self, url: str) -> FetchedPage:
        """GET `url`. Every URL is checked against decision 12 before a socket is opened."""
        assert_named_feature(url)
        try:
            with self._client.stream("GET", url) as response:
                body, truncated = _read_capped(response.iter_bytes())
                return FetchedPage(
                    status=response.status_code,
                    final_url=str(response.url),
                    body=body,
                    truncated=truncated,
                )
        except httpx.HTTPError as exc:
            # No response, or the body died mid-stream: both are "could not ask". A partial
            # body is not a result and is not returned.
            raise TransportFailure(f"GET {url}: {type(exc).__name__}: {exc}") from exc

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpFetcher:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def assert_named_feature(url: str) -> None:
    """Refuse a raw geometry dump (decision 12). Named features, not "give me the bbox".

    The pilot paid 1.0 MB of its 2.34 MB for two such dumps to find one or two named features;
    the same box answered in 287 bytes for a name-filtered Overpass query.

    The URL is unquoted before the check: an Overpass query travels percent-encoded, so
    `out%20geom` is the same request as `out geom`.
    """
    marker = next((m for m in RAW_GEOMETRY_MARKERS if m in unquote(url)), None)
    if marker is not None:
        raise RawGeometryRefused(
            f"{url!r} asks for raw geometry ({marker!r}); decision 12 wants named features "
            "(COST.md §3: two OSM bbox dumps were 1.0 MB of 2.34 MB)"
        )


def wikipedia_extract_url(name: str) -> str:
    """The `enwiki` target: the article's plaintext extract plus its own coordinate claim.

    The same parameters the pilot used (`fetch_log.jsonl`, `Satsurblia/enwiki`).
    """
    return (
        WIKIPEDIA_ENDPOINT
        + "?"
        + urlencode(
            {
                "action": "query",
                "prop": "extracts|coordinates",
                "explaintext": "1",
                "redirects": "1",
                "titles": name,
                "format": "json",
            },
            quote_via=quote,
        )
    )


def wikidata_search_url(name: str) -> str:
    """The `wikidata_search` target: candidate items for a *name*, not for a geometry.

    The worklist findings carry no Q-id (re-verified: no `Q\\d+` in any of the 2,210 findings'
    `note`/`current_value`), so the entity data the pilot fetched by id has to be reached by
    search first. This is the search hop the pilot had to make by hand for Petroglyph's URL.
    """
    return (
        WIKIDATA_ENDPOINT
        + "?"
        + urlencode(
            {
                "action": "wbsearchentities",
                "search": name,
                "language": "en",
                "uselang": "en",
                "limit": "5",
                "format": "json",
            },
            quote_via=quote,
        )
    )


def overpass_named_feature_url(name: str, *, lat: float, lon: float) -> str:
    """The Overpass target: named nodes/ways within `NAMED_FEATURE_RADIUS_M` of the stored point.

    Name-filtered and `around`-based, with `out center tags;` - never `out geom`, never a bbox
    dump. A stored name that cannot be written into an Overpass string literal (a `"` or a
    backslash) raises rather than being silently mangled: a quietly wrong query returns
    "nothing found", which reads as evidence that the name is absent.
    """
    if '"' in name or "\\" in name:
        raise InputError(
            f"name {name!r} cannot be written into an Overpass string literal; "
            "refusing to fetch a mangled query"
        )
    pattern = _overpass_regex(name)
    clauses = "".join(
        f'{element}["name"~"{pattern}",i](around:{NAMED_FEATURE_RADIUS_M},{lat},{lon});'
        for element in ("node", "way")
    )
    query = f"[out:json];({clauses});out center tags;"
    return OVERPASS_ENDPOINT + "?" + urlencode({"data": query}, quote_via=quote)


def _overpass_regex(name: str) -> str:
    """Escape a stored name for Overpass's POSIX-ish regex (`.`, `-`, `(` are all live there)."""
    escaped = name.replace("\\", "")
    for char in ".[]{}()^$*+?|":
        escaped = escaped.replace(char, "\\" + char)
    return escaped


@dataclass(frozen=True)
class Target:
    """One URL to try, and the finding that asked for it."""

    site_id: str
    feature: str
    url: str
    reason: str  #: "<test_id> <field>" of the finding that bought this target

    @property
    def label(self) -> str:
        """The pilot's `<site>/<feature>` label, with the stable `site_id` as the site part."""
        return f"{self.site_id}/{self.feature}"


def _finding(row: Mapping[str, Any], key: str, what: str) -> Any:
    if key not in row or row[key] in (None, ""):
        raise InputError(f"{what}: finding carries no {key!r}: {dict(row)!r}")
    return row[key]


def _stored_coordinates(site: Mapping[str, Any], site_id: str) -> tuple[float, float]:
    """The site's own stored point, from the finding that flagged it. Never guessed.

    The Overpass target is centred on the coordinate the worklist already carries; a site whose
    findings carry none gets no Overpass target, because a centre I invented would be evidence
    of nothing.
    """
    for finding in site["findings"]:
        if finding.get("field") != "lat/lon":
            continue
        value = finding.get("current_value")
        if (
            isinstance(value, (list, tuple))
            and len(value) == 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)
        ):
            return float(value[0]), float(value[1])
        raise InputError(f"{site_id}: lat/lon finding carries {value!r}, not a coordinate pair")
    raise InputError(f"{site_id}: no lat/lon finding to centre the named-feature query on")


def targets_for_site(site: Mapping[str, Any]) -> list[Target]:
    """The targets this site's findings buy, in finding order, deduplicated by feature.

    Driven by the findings: the census check family decides *whether* to fetch at all (T02 buys
    none), the field decides *what*, and the record supplies the name and the stored point.
    """
    site_id = str(_finding(site, "site_id", "site record"))
    name = str(_finding(site, "name", f"site {site_id}"))
    findings = site.get("findings")
    if not isinstance(findings, list) or not findings:
        raise InputError(f"{site_id}: a site with no findings buys no evidence... and none came")

    usable = [
        f for f in findings if str(f.get("test_id", "")).partition("/")[0] not in NO_FETCH_PREFIXES
    ]
    targets: dict[str, Target] = {}
    for finding in usable:
        test_id = str(_finding(finding, "test_id", f"site {site_id}"))
        field_name = str(_finding(finding, "field", f"site {site_id}"))
        if field_name not in FEATURES_FOR_FIELD:
            raise InputError(
                f"{site_id}: {test_id} is filed on field {field_name!r}, which no target rule "
                f"covers (known fields: {sorted(FEATURES_FOR_FIELD)})"
            )
        reason = f"{test_id} {field_name}"
        for feature in FEATURES_FOR_FIELD[field_name]:
            if feature in targets:
                continue
            targets[feature] = Target(
                site_id=site_id,
                feature=feature,
                url=_url_for(feature, site, site_id, name),
                reason=reason,
            )
    return list(targets.values())


def _url_for(feature: str, site: Mapping[str, Any], site_id: str, name: str) -> str:
    if feature == FEATURE_ENWIKI:
        return wikipedia_extract_url(name)
    if feature == FEATURE_WIKIDATA_SEARCH:
        return wikidata_search_url(name)
    if feature == FEATURE_OVERPASS_NAMED:
        lat, lon = _stored_coordinates(site, site_id)
        return overpass_named_feature_url(name, lat=lat, lon=lon)
    raise InputError(f"{site_id}: no URL builder for feature {feature!r}")


@dataclass(frozen=True)
class EvidenceFile:
    """One written evidence file. `wrote=False` means an identical file was already there."""

    site_id: str
    feature: str
    path: Path
    wrote: bool


class EvidenceStore:
    """`evidence/<site_id>%2F<feature>.txt`, the pilot's layout, one file per fetch.

    Existence is the record: a target whose file is already on disk is not fetched again, so a
    re-run costs nothing and cannot silently pile up a second copy of the same page. Deleting a
    file is how a human asks for that one page again. The file is written to a `.tmp` and
    replaced, so a kill leaves no half page behind (the census cache's convention).
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    @staticmethod
    def slug(site_id: str, feature: str) -> str:
        """The pilot's URL-encoded label: `quote("Satsurblia/wikidata", safe="")`."""
        return quote(f"{site_id}/{feature}", safe="")

    def path_for(self, site_id: str, feature: str) -> Path:
        return self.root / f"{self.slug(site_id, feature)}.txt"

    def exists(self, site_id: str, feature: str) -> bool:
        return self.path_for(site_id, feature).exists()

    def write(self, *, site_id: str, feature: str, body: bytes) -> EvidenceFile:
        path = self.path_for(site_id, feature)
        if path.exists():
            if path.read_bytes() != body:
                raise EvidenceConflict(
                    f"{path} holds different bytes than the answer just received; refusing to "
                    "overwrite a recorded fetch (delete the file to refetch this one target)"
                )
            return EvidenceFile(site_id=site_id, feature=feature, path=path, wrote=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(body)
        tmp.replace(path)
        return EvidenceFile(site_id=site_id, feature=feature, path=path, wrote=True)


@dataclass
class SiteEvidence:
    """What the fetch stage did for one site. Counts, not prose."""

    site_id: str
    targets: list[Target] = field(default_factory=list)
    fetched: int = 0
    skipped_existing: int = 0
    truncated: int = 0
    bytes: int = 0
    non_2xx: list[tuple[str, int]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "targets": [
                {"feature": t.feature, "reason": t.reason, "url": t.url} for t in self.targets
            ],
            "fetched": self.fetched,
            "skipped_existing": self.skipped_existing,
            "truncated": self.truncated,
            "bytes": self.bytes,
            "non_2xx": [{"url": url, "http_status": status} for url, status in self.non_2xx],
        }


@dataclass
class BatchFetchReport:
    """The batch's fetch outcome. Deterministic: no timestamp (the ledger carries the clock)."""

    batch_id: str
    stage: Stage
    sites: list[SiteEvidence] = field(default_factory=list)

    @property
    def fetches(self) -> int:
        return sum(s.fetched for s in self.sites)

    @property
    def skipped_existing(self) -> int:
        return sum(s.skipped_existing for s in self.sites)

    @property
    def truncated(self) -> int:
        return sum(s.truncated for s in self.sites)

    @property
    def bytes(self) -> int:
        return sum(s.bytes for s in self.sites)

    @property
    def non_2xx(self) -> list[tuple[str, int]]:
        return [row for s in self.sites for row in s.non_2xx]

    def to_json(self) -> str:
        payload = {
            "batch_id": self.batch_id,
            "stage": self.stage.value,
            "sites": [s.to_dict() for s in self.sites],
            "totals": {
                "fetches": self.fetches,
                "skipped_existing": self.skipped_existing,
                "truncated": self.truncated,
                "bytes": self.bytes,
                "non_2xx": len(self.non_2xx),
            },
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def collect_batch(
    *,
    batch: Mapping[str, Any],
    fetcher: Fetcher,
    store: EvidenceStore,
    ledger: L.Ledger,
    stage: Stage = Stage.FINDER,
) -> BatchFetchReport:
    """Fetch every target the batch's sites buy, writing one ledger line and one file each.

    A `TransportFailure` propagates: the batch stops with the fetch that could not be measured,
    and the pages already stored stay on disk, so a re-run resumes on the remaining targets
    instead of paying for them twice. Nothing is caught into an empty result.
    """
    batch_id = str(_finding(batch, "batch_id", "batch"))
    sites = batch.get("sites")
    if not isinstance(sites, list) or not sites:
        raise InputError(f"{batch_id}: batch carries no sites")
    report = BatchFetchReport(batch_id=batch_id, stage=stage)
    for site in sites:
        result = SiteEvidence(site_id=str(_finding(site, "site_id", "site record")))
        result.targets = targets_for_site(site)
        report.sites.append(result)
        for target in result.targets:
            if store.exists(target.site_id, target.feature):
                result.skipped_existing += 1
                continue
            page = fetcher.get(target.url)
            # The line goes first, and it is fsynced: the fetch *happened*, and a crash after
            # this point must leave a visible measurement rather than an invisible one. The
            # other order would record a page nobody could account for.
            ledger.append(
                L.Entry(
                    kind=L.LedgerKind.FETCH,
                    stage=stage,
                    batch_id=batch_id,
                    label=target.label,
                    url=target.url,
                    http_status=page.status,
                    bytes=len(page.body),
                )
            )
            store.write(site_id=target.site_id, feature=target.feature, body=page.body)
            result.fetched += 1
            result.bytes += len(page.body)
            if page.truncated:
                result.truncated += 1
            if not page.ok:
                # Data, not an exception: the pilot recorded 403/404/504/429 and continued.
                result.non_2xx.append((target.url, page.status))
    return report


def write_report(path: Path, report: BatchFetchReport) -> None:
    """Write the batch's fetch report: sorted keys, LF, no timestamp (a re-run is identical)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.to_json() + "\n", encoding="utf-8", newline="\n")
