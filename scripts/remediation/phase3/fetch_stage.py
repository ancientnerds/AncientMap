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
OSM dumps instead of parsing them would have cost ~3x the plan's token anchor).

**Piece 4 replaced "one target is one fetch and one ledger line" with "one target is up to three
attempts, and every attempt has its own line".** The first live batch (2026-09-21) measured why:
a single `ReadTimeout` on the Overpass target ended the whole batch **and** wrote no ledger line,
so the ledger undercounted exactly what the pilot had counted (19 non-200 of 76 requests; COST.md
§1). Three recorded outcomes now stand apart, because "I could not look" and "I looked and there
was nothing" justify different verdicts:

* **`FetchOutcome.OK`** - a 2xx answer, its bytes on disk. A valid **empty** result (Overpass
  `"elements": []`, the pilot's 287-byte `Petroglyph/overpass.txt`) is an OK attempt.
* **`FetchOutcome.HTTP_ERROR`** - a response with a non-2xx status. Recorded data.
* **`FetchOutcome.TRANSPORT_FAILURE`** - no response at all. Recorded with its reason and no
  status, and **retried** (see `MAX_ATTEMPTS`), because 25 % of the pilot's requests failed this
  way and a design that dies on one of them cannot finish a wave.

A retried target is bounded: `MAX_ATTEMPTS` attempts total, a `RETRY_BACKOFF_SECONDS` pause between
them through an injectable sleeper, and **no** fallback endpoint - which host to ask is a decision
for the operator, not something a retry loop may change silently.

**Piece 4b bounds the retries by host instead of per target.** The first live batch's ledger
measured where its 38 minutes went: 117 of its 121 fetch lines are `overpass-api.de` - 39 targets x
`MAX_ATTEMPTS`, every one of them a TLS reset the runner then slept 20 s over - while the 15 model
calls of the same batch took 39 seconds. So a host is now asked **once per run, before its first
pending target**, through a probe of its own root URL (`host_probe_url`): one request, one ledger
line (`label="host_probe:<host>"`), never retried. Any HTTP answer means the host is reachable and
nothing else about the run changes; only a `TransportFailure` marks it down, and then every pending
target on it is recorded `host_unreachable` - one line each, `attempt=0`, carrying the probe's
reason, and **no request to their URLs** - while the batch continues with the other hosts. A host
whose targets are all already on disk is not probed at all: a re-run costs exactly what it cost
before. No host is substituted and no endpoint is rotated; picking `overpass.osm.ch` because it
answers is a decision for the operator, not for this module.

**Piece 5 adds the `wikidata_entity` target and two fields.** The discover pass asks every site
about its own fields, one call per (site, field), so `period_start` and `site_type` join
`FEATURES_FOR_FIELD`, and the same stored `country`/`description`/`card_description`/year/type are
also asked against the site's **own** Wikidata item - by id, never by search - when the record
carries one. A record without a `wikidata_qid` buys no entity target (the name search answers the
`name` field's question, which is a different one). The id is read from `site_external_ids`
(`kind='wikidata_qid'`, 4,618 rows of the snapshot's 9,237), not from `card_stats.wikidata_qid`:
that column is NULL in **all 5,004** snapshot rows and no code in this repository writes it - the
only writer of a Q-id is `pipeline/lyra/prospector/external_ids.py:55`, into `site_external_ids`
(`phase3/snapshot_plan.py` carries the measurement). A qid that is not a Q-number is refused
rather than written into an `ids=` parameter that would answer with no entities at all.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from urllib.parse import quote, unquote, urlencode, urlsplit

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

#: The User-Agent this client sends, re-exported under this module's own name so the string is
#: visible where the request is built. `census.fetch.USER_AGENT` is the project's one spelling of
#: it: `AncientNerdsSiteAudit/1.0 (https://ancientnerds.com; database audit;
#: ancient.nerds@protonmail.com)` - a named client, a real site and a contact address.
#:
#: Why this is pinned here: overpass-api.de answers a request it will not serve with 89 bytes of
#: plain text (`output/remediation/phase3_pilot/evidence/Didnauri%2Foverpass_shiraki.txt`):
#:
#:     Please include a meaningful User-Agent string with your requests to avoid rate-limiting.
#:
#: The pilot's own client did send one (`http_get.py:UA`, `AncientMap-Phase3-Pilot/1.0
#: (https://github.com/ancientnerds; martin@example.invalid)`) and still got that body - with
#: **HTTP 429** from `overpass.kumi.systems` (`fetch_log.jsonl`, 2026-09-20T22:22:35), i.e. it is
#: this service's rate-limit body, not proof of a missing header. "Meaningful" is the service's
#: word and no source states what satisfies it: whether the runner's own string is accepted is
#: **unverified** - no live request is made from this piece. What *is* pinned is that every request
#: carries this non-default, identifying string instead of httpx's own `python-httpx/x.y`.
PHASE3_USER_AGENT = USER_AGENT

#: How many times one target may be asked in total (so: two retries). **A chosen bound, not a
#: measurement**: no source states an attempt budget. What the sources state is that the weather
#: is bad - `COST.md` §1: 19 non-200 of 76 requests (403 x8, 404 x3, transport x5, 504 x2, 429 x1)
#: - and that the pilot's own retried 504 and 429 succeeded.
MAX_ATTEMPTS = 3

#: The pause before retry 1 and retry 2, in seconds. **A chosen bound**, and the only number here
#: whose source is a log line rather than a phrase: `fetch_log.jsonl` has the failed 504 at
#: 2026-09-20T22:21:01Z (`Pannonian/overpass_stored_point`) and its successful re-ask 20 s later at
#: 22:21:21Z. That 20 s is a request *plus* a pause, so it is read as "the pilot waited on the
#: order of seconds", not as a delay to copy.
RETRY_BACKOFF_SECONDS = (1.0, 3.0)

#: Statuses worth a second attempt: 429 (with the body above) and every 5xx. Everything else -
#: 400, 403, 404 - is an answer the same question gets again unchanged, so it is recorded once and
#: not re-asked.
RETRYABLE_STATUSES = frozenset({408, 429})

#: How long the Overpass target may take, in seconds, versus the client's own `timeout` for the
#: other hosts. **A chosen bound, not a measurement.** What is measured: the first live batch lost
#: the Overpass request to a read timeout at 40 s (`run.py --timeout`), and the enwiki target for
#: the same site answered in the same batch (`LEDGER.jsonl`, `31860bc4.../enwiki`, 4,356 bytes).
#: Wikipedia's `prop=extracts|coordinates` already carries the article's coordinate claim, so
#: Overpass is a **second opinion** here - it is kept, bounded, and must never be the reason a site
#: is unverifiable when the enwiki evidence answered the question.
OVERPASS_TIMEOUT = 20.0

#: The ledger label of a host probe: `host_probe:<host>`. A probe line is a fetch line like any
#: other (the ledger records every request that left the machine), and this prefix is what tells it
#: from a target's attempt when a reader totals a run.
HOST_PROBE_PREFIX = "host_probe:"

#: Feature slugs. The first two are the pilot's own label suffixes (`fetch_log.jsonl`:
#: `Satsurblia/enwiki`, `Karpasia/wd_kition_label`); `overpass_named` names the query shape the
#: pilot used for the same job under `overpass_bbox`/`overpass_stored_features`, kept distinct
#: from the dumps those labels also covered. `wikidata_entity` names the pilot's
#: `Special:EntityData/Q28220554.json` fetch - here as the API query the project already uses for
#: the same data (`scripts/audit_wikidata_batch.py:56`), so one request carries claims, labels and
#: descriptions of the **site's own** item instead of a full JSON dump.
FEATURE_ENWIKI = "enwiki"
FEATURE_WIKIDATA_SEARCH = "wikidata_search"
FEATURE_WIKIDATA_ENTITY = "wikidata_entity"
FEATURE_OVERPASS_NAMED = "overpass_named"

#: The fields the **discover pass** asks about (`phase3/snapshot_plan.py`), and what each buys.
#: `card_description` lives in `card_stats` (see `snapshot_plan.FIELD_STORED_IN`); its evidence is
#: the same article and item as the other four fields'. `period_start` and `site_type` join the
#: table in piece 5: neither buys Overpass - a year and a type are claims about the site, not
#: features around its stored point - and both are asked against the article and, when the record
#: carries one, the Wikidata item.
FEATURES_FOR_FIELD: dict[str, tuple[str, ...]] = {
    "lat/lon": (FEATURE_ENWIKI, FEATURE_OVERPASS_NAMED),
    "name": (FEATURE_ENWIKI, FEATURE_WIKIDATA_SEARCH),
    "country": (FEATURE_ENWIKI, FEATURE_WIKIDATA_ENTITY),
    "description": (FEATURE_ENWIKI, FEATURE_WIKIDATA_ENTITY),
    "card_description": (FEATURE_ENWIKI, FEATURE_WIKIDATA_ENTITY),
    "period_start": (FEATURE_ENWIKI, FEATURE_WIKIDATA_ENTITY),
    "site_type": (FEATURE_ENWIKI, FEATURE_WIKIDATA_ENTITY),
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

#: A Wikidata item id: `Q` followed by digits. The one shape `wikidata_entity_url` accepts; the
#: snapshot's own qids are read against it at plan time (`phase3/snapshot_plan.py`), so the plan
#: refuses the same ids the URL builder would refuse instead of building a URL that answers with
#: no entities.
QID_PATTERN = re.compile(r"Q[1-9][0-9]*")


class TransportFailure(RuntimeError):
    """No response arrived at all (DNS, connect, reset, timeout mid-body).

    Raised, never turned into an empty result: a caller must be able to tell "answered with
    nothing usable" from "could not ask" (`census/fetch.py` makes the same distinction).
    """


class RawGeometryRefused(ValueError):
    """A URL asks for raw geometry. Decision 12 forbids it; see `assert_named_feature`."""


class EvidenceConflict(RuntimeError):
    """An evidence file for this (site, feature) exists and holds *different* bytes."""


def is_retryable_status(status: int | None) -> bool:
    """429/408 or any 5xx. A 400/403/404 is asked once: the next answer would be the same one."""
    if status is None:
        return False
    return status in RETRYABLE_STATUSES or 500 <= status < 600


def host_of(url: str) -> str:
    """The host a URL belongs to, lowercased. The key every per-host decision is taken under."""
    host = urlsplit(url).hostname
    if not host:
        raise InputError(f"{url!r} carries no host; a request needs one to leave the machine")
    return host


def host_probe_url(url: str) -> str:
    """`scheme://host/` for `url`: the one address that belongs to the host and to no target.

    The probe is a request, and the ledger records it as one. Asking the host's own root - the bare
    host URL the brief's `curl` measurements used (`overpass-api.de http=000 time=0.077s`) - keeps
    the probe's ledger line from being read as an attempt on some target: no target is ever asked
    for `/`. The other candidate, reusing the first target's URL as the probe, would make that one
    request both a probe and an attempt, and one of the two would go unrecorded.
    """
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}/"


#: Which hosts get the shorter bound, by host name. Keyed by host rather than by URL so that the
#: run's probe - which asks the host's root, not the endpoint - waits exactly as long as the targets
#: it gates: a host that never answers costs one bounded wait per run, never a longer one than the
#: operator's own `OVERPASS_TIMEOUT`.
SHORT_TIMEOUT_HOSTS: dict[str, float] = {host_of(OVERPASS_ENDPOINT): OVERPASS_TIMEOUT}


def timeout_for(url: str) -> float | None:
    """The per-target bound for this URL's host, or `None` for the client's own default.

    Overpass is the one host this module asks a *second opinion* of, and the one the first live
    batch lost to a read timeout, so it gets the shorter bound (`OVERPASS_TIMEOUT`).
    """
    return SHORT_TIMEOUT_HOSTS.get(host_of(url))


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
        timeout = self._timeout(url)
        try:
            with self._client.stream("GET", url, timeout=timeout) as response:
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

    def _timeout(self, url: str) -> httpx.Timeout | float:
        """`httpx`'s own default for this client, or the target's shorter bound (`timeout_for`)."""
        bound = timeout_for(url)
        return self._client.timeout if bound is None else bound

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpFetcher:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


HOST_MIN_INTERVAL_SECONDS = 0.2
HOST_LOCK_STALE_SECONDS = 30.0
HOST_LOCK_WAIT_SECONDS = 60.0
HOST_LOCK_POLL_SECONDS = 0.05


class PacerTimeout(RuntimeError):
    """A host's lock was held so long that waiting further would only hide a stuck neighbour."""


class HostPacer:
    """One request at a time per host, **across processes**.

    Parallel batches are separate processes, so an in-memory limiter would multiply the rate per
    host by the number of jobs - which is the impoliteness a pacer exists to prevent. The mutex is
    therefore a file beside a per-host stamp: take the lock, measure the time since this host's last
    request, sleep the rest of the interval, rewrite the stamp, release the lock. The **stamp**, not
    the lock, is what sets the interval, so a lock lost to a crash costs at most one early request.

    `clock` and `sleep` are injected, and the lock records its own acquisition time in the file
    rather than relying on the filesystem clock, so tests drive both without mocking `os.stat`.

    Honest about its reach: this is **machine-local**. Two machines running this fleet share no
    per-host state, so the claim it supports is "this machine does not hammer a host", not "a host
    sees at most five requests a second worldwide".
    """

    def __init__(
        self,
        root: Path,
        *,
        min_interval: float = HOST_MIN_INTERVAL_SECONDS,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        stale_after: float = HOST_LOCK_STALE_SECONDS,
        wait_seconds: float = HOST_LOCK_WAIT_SECONDS,
    ) -> None:
        self.root = Path(root)
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._stale_after = stale_after
        self._wait_seconds = wait_seconds

    def stamp_of(self, host: str) -> Path:
        return self.root / f"{host}.stamp"

    def lock_of(self, host: str) -> Path:
        return self.root / f"{host}.lock"

    def wait(self, host: str) -> float:
        """Block until a request to `host` is polite. Returns the seconds slept (0.0 = no wait)."""
        self.root.mkdir(parents=True, exist_ok=True)
        lock = self.lock_of(host)
        deadline = self._clock() + self._wait_seconds
        while True:
            try:
                handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if self._is_stale(lock):
                    # Best effort on purpose: a lock that outlived its process must not wedge the
                    # whole fleet, and the worst case of losing this race is one early request.
                    lock.unlink(missing_ok=True)
                    continue
                if self._clock() > deadline:
                    raise PacerTimeout(
                        f"{lock} was held for {self._wait_seconds:.0f}s - the holder is stuck, "
                        "not busy"
                    ) from None
                self._sleep(HOST_LOCK_POLL_SECONDS)
                continue
            try:
                os.write(handle, f"{self._clock():.6f}".encode())
                return self._hold(host)
            finally:
                os.close(handle)
                lock.unlink(missing_ok=True)

    def _hold(self, host: str) -> float:
        """Inside the lock: sleep the rest of the interval, then claim this request's time."""
        stamp = self.stamp_of(host)
        last = self._read_stamp(stamp)
        wait = 0.0 if last is None else max(0.0, self.min_interval - (self._clock() - last))
        if wait > 0:
            self._sleep(wait)
        stamp.write_text(f"{self._clock():.6f}", encoding="utf-8")
        return wait

    @staticmethod
    def _read_stamp(stamp: Path) -> float | None:
        try:
            return float(stamp.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None

    def _is_stale(self, lock: Path) -> bool:
        try:
            held_since = float(lock.read_text(encoding="utf-8").strip())
        except OSError:
            return False
        except ValueError:
            return True  # a lock that cannot say when it was taken is a leftover
        return self._clock() - held_since > self._stale_after


class PacedFetcher:
    """A `Fetcher` that waits its turn per host before delegating.

    It decorates the seam instead of threading a pacer through `probe_host`, `one_attempt` and
    `collect_batch`: every request in this module goes through `Fetcher.get`, so one decorator paces
    the reachability probe, every retry and every target, and no call site can forget.
    """

    def __init__(self, inner: Fetcher, pacer: HostPacer) -> None:
        self._inner = inner
        self._pacer = pacer

    def get(self, url: str) -> FetchedPage:
        self._pacer.wait(host_of(url))
        return self._inner.get(url)


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


def wikidata_entity_url(qid: str) -> str:
    """The `wikidata_entity` target: one Q-id's claims, labels and descriptions, by id.

    This is the hop the pilot made by hand (`Special:EntityData/Q28220554.json`,
    `phase3_pilot/evidence/`): the item is **known**, so nothing is searched for and nothing is
    guessed. The API query is the project's existing one for the same data
    (`scripts/audit_wikidata_batch.py:56` uses `props=claims|labels`); `descriptions` is added
    because a description is one of the fields the discover pass asks about.

    A qid that is not a Q-number raises instead of being written into the URL: a mangled `ids=`
    value answers `{"entities":{}}`, which reads as "the item says nothing" and would be recorded
    as evidence against the site's value.
    """
    if not QID_PATTERN.fullmatch(qid):
        raise InputError(
            f"wikidata_qid {qid!r} is not a Q-number (Q followed by digits); refusing to build an "
            "entity URL that would answer with no entities"
        )
    return (
        WIKIDATA_ENDPOINT
        + "?"
        + urlencode(
            {
                "action": "wbgetentities",
                "ids": qid,
                "props": "claims|labels|descriptions",
                "languages": "en",
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

    A record that carries no `wikidata_qid` buys no `wikidata_entity` target: there is no id to ask
    about, and the name search (`wikidata_search`) answers a **different** question - it returns
    candidate items for a name, which is what the `name` field needs and not what a stored
    description, year, type, country or card text is judged against. The finding-driven worklist
    records carry no qid at all (`WORKLIST.jsonl`, 1,840 records, re-verified), so their targets
    are unchanged by this rule.
    """
    site_id = str(_finding(site, "site_id", "site record"))
    name = str(_finding(site, "name", f"site {site_id}"))
    findings = site.get("findings")
    if not isinstance(findings, list) or not findings:
        raise InputError(f"{site_id}: a site with no findings buys no evidence... and none came")

    usable = [
        f for f in findings if str(f.get("test_id", "")).partition("/")[0] not in NO_FETCH_PREFIXES
    ]
    qid = site.get("wikidata_qid")
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
            if feature == FEATURE_WIKIDATA_ENTITY and not qid:
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
    if feature == FEATURE_WIKIDATA_ENTITY:
        return wikidata_entity_url(str(_finding(site, "wikidata_qid", f"site {site_id}")))
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


@dataclass(frozen=True)
class FetchAttempt:
    """One HTTP attempt on one target: what happened, and what it bought.

    Exactly the shape of the ledger line written for it, so the report and the ledger cannot
    disagree about a request (the report is for a human, the ledger carries the clock).
    """

    attempt: int  #: 1-based
    outcome: L.FetchOutcome
    http_status: int | None  #: None for a transport failure: no response arrived
    bytes: int  #: 0 when nothing arrived
    error: str | None  #: the reason, for a transport failure only

    @property
    def ok(self) -> bool:
        return self.outcome is L.FetchOutcome.OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt,
            "outcome": self.outcome.value,
            "http_status": self.http_status,
            "bytes": self.bytes,
            "error": self.error,
        }


@dataclass
class TargetOutcome:
    """Every attempt made on one target, and what the target ended with."""

    feature: str
    url: str
    bought_by: str  #: the finding's "<test_id> <field>"
    attempts: list[FetchAttempt] = field(default_factory=list)
    #: Set only by `collect_batch` when the target's host did not answer the run's probe: the
    #: probe's reason, and the fact that **no attempt was made** - `attempts` stays empty and no
    #: request went to `url`. Kept apart from a failed attempt on purpose: "the host never
    #: answered, so this was not tried" and "this was tried and failed" are different sentences,
    #: and the judge reads them back as the reason a site has no evidence.
    not_attempted: str | None = None
    #: Set only by `one_attempt`: the page this target bought is on disk, and whether it was cut
    #: at `MAX_PAGE_BYTES`.
    stored: bool = False
    truncated: bool = False

    @property
    def requests(self) -> int:
        """HTTP requests made for this target. Zero for one that was never attempted."""
        return len(self.attempts)

    @property
    def final(self) -> FetchAttempt:
        if not self.attempts:  # pragma: no cover - `failure` handles a not-attempted target first
            raise RuntimeError(f"{self.feature}: no attempt was recorded")
        return self.attempts[-1]

    @property
    def succeeded(self) -> bool:
        return bool(self.attempts) and self.final.ok

    @property
    def failure(self) -> str | None:
        """Why this target has no evidence, or `None` when it does have some.

        This is the sentence the judge stage reads back out of the report before it decides
        whether a missing evidence file is an explained failure or a hole in the record. It says
        which of the two facts it is: a target nobody asked because its host did not answer, or a
        target that was asked and failed.
        """
        if self.succeeded:
            return None
        if self.not_attempted is not None:
            return (
                f"not attempted: this target's host did not answer the run's host probe "
                f"({self.not_attempted}); 0 request(s) recorded, no evidence on disk"
            )
        final = self.final
        if final.outcome is L.FetchOutcome.TRANSPORT_FAILURE:
            what = f"no response: {final.error}"
        else:
            what = f"HTTP {final.http_status}"
        return (
            f"{what} ({self.requests} request(s) recorded, the last one given up; "
            "no evidence on disk)"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempts": [a.to_dict() for a in self.attempts],
            "bought_by": self.bought_by,
            "feature": self.feature,
            "failure": self.failure,
            "not_attempted": self.not_attempted,
            "requests": self.requests,
            "url": self.url,
        }


@dataclass
class SiteEvidence:
    """What the fetch stage did for one site. Counts, not prose."""

    site_id: str
    targets: list[Target] = field(default_factory=list)
    fetched: int = 0  #: targets that produced an evidence file
    skipped_existing: int = 0
    truncated: int = 0
    bytes: int = 0
    non_2xx: list[tuple[str, int]] = field(default_factory=list)
    #: One record per attempted target, in attempt order. A failed target is here too - that is
    #: the whole point of piece 4: a request that bought nothing must be visible in the report.
    outcomes: list[TargetOutcome] = field(default_factory=list)

    @property
    def requests(self) -> int:
        """HTTP attempts made for this site (every one of them has its own ledger line)."""
        return sum(o.requests for o in self.outcomes)

    @property
    def failed(self) -> list[TargetOutcome]:
        return [o for o in self.outcomes if not o.succeeded]

    @property
    def not_attempted(self) -> list[TargetOutcome]:
        """Targets recorded as `host_unreachable`: their host never answered, so nothing was asked."""
        return [o for o in self.outcomes if o.not_attempted is not None]

    def failures(self) -> dict[str, str]:
        """`feature -> why it has no evidence`, for the targets that have none."""
        return {o.feature: str(o.failure) for o in self.failed}

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "targets": [
                {"feature": t.feature, "reason": t.reason, "url": t.url} for t in self.targets
            ],
            "outcomes": [o.to_dict() for o in self.outcomes],
            "fetched": self.fetched,
            "not_attempted": len(self.not_attempted),
            "skipped_existing": self.skipped_existing,
            "truncated": self.truncated,
            "bytes": self.bytes,
            "non_2xx": [{"url": url, "http_status": status} for url, status in self.non_2xx],
        }


@dataclass(frozen=True)
class HostProbe:
    """One host's reachability decision for this run, and the single request that bought it.

    `reachable` is decided by *any* HTTP answer: a 400, a 404, a 429 and a 500 all mean the host
    answered, so only a `TransportFailure` marks a host down (the brief's measurement: the same
    `curl` gets a reset from `overpass-api.de` and a 400 from `overpass.osm.ch`, and only the reset
    means "not there"). `reason` carries what was observed, so the report and the prompt can say
    which of the two facts is on the table.
    """

    host: str
    url: str  #: the probe URL (the host's root), not any target's
    reachable: bool
    outcome: L.FetchOutcome
    http_status: int | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "url": self.url,
            "reachable": self.reachable,
            "outcome": self.outcome.value,
            "http_status": self.http_status,
            "reason": self.reason,
        }


@dataclass
class BatchFetchReport:
    """The batch's fetch outcome. Deterministic: no timestamp (the ledger carries the clock)."""

    batch_id: str
    stage: Stage
    sites: list[SiteEvidence] = field(default_factory=list)
    #: One record per host this run actually asked, in the order the batch reached them. Empty when
    #: every target was already on disk: then no host was asked at all.
    probes: list[HostProbe] = field(default_factory=list)

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

    @property
    def requests(self) -> int:
        """Every HTTP request the batch made: one probe per host asked, plus every target attempt.

        A target recorded `host_unreachable` contributes 0 - no request went to its URL - while the
        probe that decided that contributes 1. Both have a ledger line, so this figure and the
        ledger's `fetches` for the batch stay the same number.
        """
        return sum(s.requests for s in self.sites) + len(self.probes)

    @property
    def probe_requests(self) -> int:
        return len(self.probes)

    @property
    def not_attempted(self) -> list[TargetOutcome]:
        """Targets no request was made for: their host did not answer the run's probe."""
        return [o for s in self.sites for o in s.not_attempted]

    @property
    def failed(self) -> list[TargetOutcome]:
        return [o for s in self.sites for o in s.failed]

    def failures_by_site(self) -> dict[str, dict[str, str]]:
        """The record the judge stage reads: `site_id -> {feature: why it has no evidence}`.

        A target that was never attempted is in here too, with the sentence that says so: the
        judge must be told which of the two facts it is holding.
        """
        return {s.site_id: s.failures() for s in self.sites if s.failed}

    def to_json(self) -> str:
        payload = {
            "batch_id": self.batch_id,
            "stage": self.stage.value,
            "probes": [p.to_dict() for p in self.probes],
            "sites": [s.to_dict() for s in self.sites],
            "totals": {
                "fetches": self.fetches,
                "requests": self.requests,
                "probes": self.probe_requests,
                "failed": len(self.failed),
                "not_attempted": len(self.not_attempted),
                "skipped_existing": self.skipped_existing,
                "truncated": self.truncated,
                "bytes": self.bytes,
                "non_2xx": len(self.non_2xx),
            },
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def probe_host(
    *,
    host: str,
    url: str,
    fetcher: Fetcher,
    ledger: L.Ledger,
    batch_id: str,
    stage: Stage,
) -> HostProbe:
    """Ask a host once, before its first pending target, and record that one request.

    The probe is **not** retried, and that is the whole point: `MAX_ATTEMPTS` copies of the same
    wait is what the first live batch measured as 38 minutes (117 lines on one host, every one of
    them a nested wait over a host that answered nothing). One bounded request per host per run
    turns that into one; when the host answers, the run proceeds exactly as it did before.

    Its line is an ordinary fetch line, written *before* the decision is applied (piece 2's rule:
    a request that left the machine is visible even if the next byte of code does not run), and it
    carries `given_up=False` even when the host is down: `given_up` records that a *target's* last
    attempt ended without evidence, and no target was attempted here.
    """
    try:
        page = fetcher.get(url)
    except TransportFailure as exc:
        reason = str(exc)
        probe = HostProbe(
            host=host,
            url=url,
            reachable=False,
            outcome=L.FetchOutcome.TRANSPORT_FAILURE,
            http_status=None,
            reason=reason,
        )
        status: int | None = None
        size = 0
        error: str | None = reason
    else:
        # **Any** HTTP answer means reachable - 400, 404, 429, 500 included. A host that says "no"
        # is a host that is there; only silence is absence (the brief's curl: a reset from
        # `overpass-api.de`, a 400 from `overpass.osm.ch`).
        status = page.status
        size = len(page.body)
        error = None
        probe = HostProbe(
            host=host,
            url=url,
            reachable=True,
            outcome=L.FetchOutcome.OK if page.ok else L.FetchOutcome.HTTP_ERROR,
            http_status=status,
            reason=f"HTTP {status}",
        )
    ledger.append(
        L.Entry(
            kind=L.LedgerKind.FETCH,
            stage=stage,
            batch_id=batch_id,
            label=f"{HOST_PROBE_PREFIX}{host}",
            url=url,
            http_status=status,
            bytes=size,
            outcome=probe.outcome,
            attempt=1,
            error=error,
            given_up=False,
        )
    )
    return probe


def one_attempt(
    *,
    target: Target,
    fetcher: Fetcher,
    store: EvidenceStore,
    ledger: L.Ledger,
    batch_id: str,
    stage: Stage,
    sleep: Callable[[float], None],
) -> TargetOutcome:
    """Ask one target, up to `MAX_ATTEMPTS` times, and record every attempt exactly once.

    The order inside an attempt is the ledger's rule from piece 2 and it does not change: the
    **line goes down first**, because the request happened and a crash after it must leave a
    visible measurement rather than an invisible one; the page is stored second.

    What is retried is decided by `is_retryable_status` plus a transport failure, and what is
    *not*: a fallback host. `HttpFetcher` keeps asking the same URL, because which endpoint to ask
    is a decision for the operator (and `overpass.kumi.systems` - the third-party mirror the pilot
    fell back to by hand - is a different service with different terms).
    """
    outcome = TargetOutcome(feature=target.feature, url=target.url, bought_by=target.reason)
    for number in range(1, MAX_ATTEMPTS + 1):
        attempt, page = _ask(target=target, fetcher=fetcher, number=number)
        retryable = attempt.outcome is L.FetchOutcome.TRANSPORT_FAILURE or is_retryable_status(
            attempt.http_status
        )
        last = not retryable or number == MAX_ATTEMPTS
        ledger.append(
            L.Entry(
                kind=L.LedgerKind.FETCH,
                stage=stage,
                batch_id=batch_id,
                label=target.label,
                url=target.url,
                http_status=attempt.http_status,
                bytes=attempt.bytes,
                outcome=attempt.outcome,
                attempt=number,
                error=attempt.error,
                given_up=last and not attempt.ok,
            )
        )
        if page is not None and page.ok:
            # A valid *empty* answer (Overpass `"elements": []`) is an OK attempt like any other:
            # the file is the record that the question was asked *and answered with nothing*.
            store.write(site_id=target.site_id, feature=target.feature, body=page.body)
            outcome.stored = True
            outcome.truncated = page.truncated
        outcome.attempts.append(attempt)
        if last:
            return outcome
        sleep(RETRY_BACKOFF_SECONDS[number - 1])
    raise AssertionError("unreachable: the loop returns on its last attempt")  # pragma: no cover


def _ask(
    *, target: Target, fetcher: Fetcher, number: int
) -> tuple[FetchAttempt, FetchedPage | None]:
    """One request. A transport failure is turned into a recorded attempt, never into a stop.

    Nothing else is caught: an exception the fetcher was not asked to raise (a `ValueError`, a
    `RawGeometryRefused`) is a bug in the caller, not weather, and propagates.
    """
    try:
        page = fetcher.get(target.url)
    except TransportFailure as exc:
        return (
            FetchAttempt(
                attempt=number,
                outcome=L.FetchOutcome.TRANSPORT_FAILURE,
                http_status=None,
                bytes=0,
                error=str(exc),
            ),
            None,
        )
    return (
        FetchAttempt(
            attempt=number,
            outcome=L.FetchOutcome.OK if page.ok else L.FetchOutcome.HTTP_ERROR,
            http_status=page.status,
            bytes=len(page.body),
            error=None,
        ),
        page,
    )


def collect_batch(
    *,
    batch: Mapping[str, Any],
    fetcher: Fetcher,
    store: EvidenceStore,
    ledger: L.Ledger,
    stage: Stage = Stage.FINDER,
    sleep: Callable[[float], None] = time.sleep,
) -> BatchFetchReport:
    """Fetch every target the batch's sites buy, writing one ledger line per *attempt*.

    No failure of one target stops the batch. A transport failure is recorded as that target's
    outcome with its reason and the next target is asked; a 429/5xx is retried up to
    `MAX_ATTEMPTS` times; anything else is recorded once. Nothing is caught into an empty result,
    and nothing is retried without a ledger line - an unrecorded retry is the invisible charge
    this ledger exists to prevent.

    Each host is probed **once per run, immediately before its first pending target**
    (`probe_host`), and only then: a host whose targets are all already on disk is not asked at
    all, so a re-run costs exactly what it cost before. A host that does not answer the probe
    leaves every pending target on it recorded as `host_unreachable` - one line each, `attempt=0`,
    the probe's reason, and **no request to their URLs** - while the targets of the other hosts are
    fetched normally. No other host is tried in its place.

    `sleep` is the retry pause, injected so a test never waits on a real clock.
    """
    batch_id = str(_finding(batch, "batch_id", "batch"))
    sites = batch.get("sites")
    if not isinstance(sites, list) or not sites:
        raise InputError(f"{batch_id}: batch carries no sites")
    report = BatchFetchReport(batch_id=batch_id, stage=stage)
    probes: dict[str, HostProbe] = {}
    for site in sites:
        result = SiteEvidence(site_id=str(_finding(site, "site_id", "site record")))
        result.targets = targets_for_site(site)
        report.sites.append(result)
        for target in result.targets:
            if store.exists(target.site_id, target.feature):
                result.skipped_existing += 1
                continue
            host = host_of(target.url)
            probe = probes.get(host)
            if probe is None:
                probe = probe_host(
                    host=host,
                    url=host_probe_url(target.url),
                    fetcher=fetcher,
                    ledger=ledger,
                    batch_id=batch_id,
                    stage=stage,
                )
                probes[host] = probe
            if not probe.reachable:
                # One line, and no request to this target's URL: nothing was asked, so there is no
                # attempt to number (`attempt=0`) and the reason is the probe's own.
                ledger.append(
                    L.Entry(
                        kind=L.LedgerKind.FETCH,
                        stage=stage,
                        batch_id=batch_id,
                        label=target.label,
                        url=target.url,
                        http_status=None,
                        bytes=0,
                        outcome=L.FetchOutcome.HOST_UNREACHABLE,
                        attempt=0,
                        error=probe.reason,
                        given_up=False,
                    )
                )
                result.outcomes.append(
                    TargetOutcome(
                        feature=target.feature,
                        url=target.url,
                        bought_by=target.reason,
                        not_attempted=probe.reason,
                    )
                )
                continue
            outcome = one_attempt(
                target=target,
                fetcher=fetcher,
                store=store,
                ledger=ledger,
                batch_id=batch_id,
                stage=stage,
                sleep=sleep,
            )
            result.outcomes.append(outcome)
            if outcome.stored:
                result.fetched += 1
                result.bytes += outcome.final.bytes
                result.truncated += int(outcome.truncated)
            for attempt in outcome.attempts:
                if not attempt.ok and attempt.http_status is not None:
                    # Data, not an exception: the pilot recorded 403/404/504/429 and continued.
                    result.non_2xx.append((target.url, attempt.http_status))
    report.probes = list(probes.values())
    return report


def write_report(path: Path, report: BatchFetchReport) -> None:
    """Write the batch's fetch report: sorted keys, LF, no timestamp (a re-run is identical)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.to_json() + "\n", encoding="utf-8", newline="\n")
