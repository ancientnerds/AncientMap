"""Does the evidence-fetch stage fetch the right thing, count it, and refuse the rest?

Piece 2 of the runner has no database, and the network is the one thing it *could* touch - so
nothing here opens a socket: the transport is injected (`httpx.MockTransport`, or a counting
stream) and every answer is a fixture.

The guards are the ones decision 12 bought with measurements (`COST.md` §3, §7): a 60 KB per-page
cap that **stops the stream** rather than buffering a 598 KB dump to keep 60 KB of it, named
Overpass queries instead of `api/0.6/map?bbox=` dumps, one ledger line per fetch carrying the
status actually observed (a 403 is data, not an exception), and a re-run that resumes on the
files already on disk instead of paying twice. Each test below is additionally proved able to
fail by mutating the module and restoring it - the mutation evidence is in
`output/remediation/phase3_runner/PIECE2.md`.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
PHASE3_PARENT = REPO / "scripts" / "remediation"
if str(PHASE3_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE3_PARENT))

from phase3 import fetch_stage as F  # noqa: E402
from phase3 import ledger as L  # noqa: E402
from phase3 import run as R  # noqa: E402
from phase3.model import Stage  # noqa: E402

WORKLIST = REPO / "output" / "remediation" / "phase3_worklist" / "WORKLIST.jsonl"

#: The chunk the counting stream hands out. A reader that buffers the page pulls all of them.
CHUNK = 8192

SITE_ID = "31860bc4-476a-49bc-9f97-e25220063d19"
OTHER_SITE_ID = "9f0b0e6d-0000-4000-8000-000000000001"

#: The pilot's own two raw-geometry dumps, byte-identical in shape to `fetch_log.jsonl`
#: (`Petroglyph/osm_bbox`, 400 KB) and the Overpass spelling of the same request.
PILOT_BBOX_DUMP = "https://api.openstreetmap.org/api/0.6/map?bbox=-132.400,56.475,-132.385,56.487"
PILOT_GEOM_QUERY = "https://overpass-api.de/api/interpreter?data=[out:json];way(around:600,56.4,56.4);out%20geom;"


def _site_record(
    *,
    site_id: str = SITE_ID,
    name: str = "Satsurblia Cave",
    findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A worklist record in the shape `WORKLIST.jsonl` really has (verified against it)."""
    if findings is None:
        findings = [
            {
                "test_id": "T01/coords",
                "field": "lat/lon",
                "current_value": [42.37726777374251, 42.60097658321723],
                "severity": "moderate",
            },
            {
                "test_id": "T03/all-outside",
                "field": "card_description",
                "current_value": "period_start=-500",
                "severity": "severe",
            },
        ]
    return {"site_id": site_id, "name": name, "phase3": True, "findings": findings}


def _batch(sites: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"batch_id": "batch-0001", "ordinal": 1, "sites": sites or [_site_record()]}


def _ok_transport(body: bytes = b'{"answer": 42}', calls: list[str] | None = None) -> httpx.BaseTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(str(request.url))
        return httpx.Response(200, content=body)

    return httpx.MockTransport(handler)


class CountingStream(httpx.SyncByteStream):
    """Hands out `total` bytes in `CHUNK` pieces and counts what the reader actually pulled."""

    def __init__(self, total: int, pulled: list[int]) -> None:
        self._total = total
        self._pulled = pulled

    def __iter__(self):  # type: ignore[no-untyped-def]
        sent = 0
        while sent < self._total:
            size = min(CHUNK, self._total - sent)
            sent += size
            self._pulled[0] += size
            yield b"x" * size

    def close(self) -> None:
        return None


def _collect(
    tmp_path: Path,
    transport: httpx.BaseTransport,
    *,
    sites: list[dict[str, Any]] | None = None,
    ledger_name: str = "LEDGER.jsonl",
    pauses: list[float] | None = None,
) -> tuple[F.BatchFetchReport, F.EvidenceStore, L.Ledger]:
    """Run one batch with the transport injected. The retry pause is recorded, never waited."""
    store = F.EvidenceStore(tmp_path / "evidence")
    ledger = L.Ledger(tmp_path / ledger_name)
    with F.HttpFetcher(transport=transport) as fetcher:
        report = F.collect_batch(
            batch=_batch(sites),
            fetcher=fetcher,
            store=store,
            ledger=ledger,
            stage=Stage.FINDER,
            sleep=(pauses if pauses is not None else []).append,
        )
    return report, store, ledger


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _probe_requests(calls: list[str]) -> list[str]:
    """The requests that went to a host's own root: the run's reachability probes (piece 4b)."""
    return [c for c in calls if urlsplit(c).path == "/"]


def _target_lines(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The ledger lines of *targets*. A probe line carries `host_probe:<host>` as its label."""
    return [e for e in entries if not str(e["label"]).startswith(F.HOST_PROBE_PREFIX)]


def _probe_lines(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in entries if str(e["label"]).startswith(F.HOST_PROBE_PREFIX)]


# ── decision 12, rule 1: the 60 KB cap ───────────────────────────────────────────────────────


def test_the_cap_stops_the_stream_instead_of_buffering_the_page() -> None:
    total = 614_400  # ten capped pages' worth: what the two pilot dumps cost
    pulled = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=CountingStream(total, pulled))

    with F.HttpFetcher(transport=httpx.MockTransport(handler)) as fetcher:
        page = fetcher.get("https://example.invalid/big")

    # The brief and COST.md say "60 KB" and never a byte count: 60 x 1024 = 61,440 is the
    # interpretation this module uses, so it is pinned here rather than left implicit.
    assert F.MAX_PAGE_BYTES == 60 * 1024 == 61_440
    assert page.status == 200
    assert page.truncated is True
    assert len(page.body) == F.MAX_PAGE_BYTES
    assert page.body == b"x" * F.MAX_PAGE_BYTES
    # The proof that it truncates instead of buffering: the transport never yielded the rest.
    assert pulled[0] < total
    assert pulled[0] <= F.MAX_PAGE_BYTES + CHUNK


def test_a_page_below_the_cap_is_kept_whole_and_not_called_truncated() -> None:
    body = b"<html>" + b"y" * 5000 + b"</html>"

    with F.HttpFetcher(transport=_ok_transport(body)) as fetcher:
        page = fetcher.get("https://example.invalid/small")

    assert page.body == body
    assert page.truncated is False


# ── decision 12, rule 2: named features, never raw geometry ──────────────────────────────────


def test_decision_12_refuses_the_two_raw_geometry_shapes_the_pilot_measured() -> None:
    for url in (PILOT_BBOX_DUMP, PILOT_GEOM_QUERY):
        with pytest.raises(F.RawGeometryRefused, match="raw geometry"):
            F.assert_named_feature(url)

    # The guard sits on the fetch path too, so no caller can route around it.
    with pytest.raises(F.RawGeometryRefused):
        with F.HttpFetcher(transport=_ok_transport()) as fetcher:
            fetcher.get(PILOT_BBOX_DUMP)


def test_the_overpass_target_is_a_name_filtered_query_around_the_stored_point() -> None:
    target = next(
        t
        for t in F.targets_for_site(_site_record())
        if t.feature == F.FEATURE_OVERPASS_NAMED
    )
    query = unquote(urlsplit(target.url).query)

    assert '["name"~"Satsurblia Cave",i]' in query
    assert f"(around:{F.NAMED_FEATURE_RADIUS_M}," in query
    assert "42.37726777374251,42.60097658321723" in query
    assert "out center tags;" in query
    assert "out geom" not in query
    assert "bbox" not in query


def test_a_t02_finding_buys_no_fetch_at_all() -> None:
    # Decision 12: T02 is one human vocabulary decision plus a short exception list (COST.md §7
    # item 5: none of the pilot's three T02 findings was a data error).
    site = _site_record(
        findings=[
            {
                "test_id": "T02/outside-polygon",
                "field": "country",
                "current_value": "Ireland",
                "severity": "cosmetic",
            }
        ]
    )
    assert F.targets_for_site(site) == []


def test_every_target_of_every_phase3_worklist_record_is_a_named_feature_query() -> None:
    """The binding rule, checked against the real 1,813-site input instead of a fixture."""
    checked = 0
    for record in R.read_jsonl(WORKLIST):
        if record.get("phase3") is not True:
            continue
        targets = F.targets_for_site(record)
        for target in targets:
            F.assert_named_feature(target.url)
            assert "out geom" not in target.url
            checked += 1
    assert checked > 1_000  # the worklist's findings do buy fetches; a rule table matching none
    # of them would be a silently unfetched run


def test_a_field_no_rule_covers_raises_instead_of_being_skipped() -> None:
    # `scope_status` is T11's field (`census/tests/t11_scope_window.py:146`): whether the record is
    # inside the project's E3 date window. It has no evidence target and never will - the site's own
    # sources cannot settle a project decision - so the rule table must raise rather than quietly
    # buy nothing. (This test used `period_start` until piece 5 gave that field an article+item
    # route, and `period_start` was the only unroutable field it had.)
    site = _site_record(
        findings=[{"test_id": "T11/out_of_window", "field": "scope_status", "current_value": None}]
    )
    with pytest.raises(R.InputError, match="no target rule"):
        F.targets_for_site(site)


# ── the fetch itself: measured outcomes ──────────────────────────────────────────────────────


@pytest.mark.parametrize("status", [400, 403, 404])
def test_a_non_2xx_is_recorded_as_data_and_never_raised(tmp_path: Path, status: int) -> None:
    body = f"<html>{status} page</html>".encode()
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(status, content=body)

    report, store, ledger = _collect(tmp_path, httpx.MockTransport(handler))

    # Both targets were attempted, the batch did not stop - and *neither* bought a page, which is
    # what `fetches` counts: `requests` is the traffic, `fetches` the evidence. The traffic is the
    # two host probes plus the two attempts (piece 4b: the probes are requests like any other).
    assert report.fetches == 0
    assert report.requests == 4
    assert [p.reachable for p in report.probes] == [True, True]  # a 4xx is an answer
    assert [s for _, s in report.non_2xx] == [status, status]
    # A 400/403/404 is an answer the same question gets again unchanged: asked exactly once.
    assert _probe_requests(calls) == ["https://en.wikipedia.org/", "https://overpass-api.de/"]
    assert len(calls) == 4
    entries = _target_lines(L.read_entries(ledger.path))
    assert [e["http_status"] for e in entries] == [status, status]
    assert [e["outcome"] for e in entries] == ["http_error", "http_error"]
    assert [e["attempt"] for e in entries] == [1, 1]
    assert [e["given_up"] for e in entries] == [True, True]
    assert [e["bytes"] for e in entries] == [len(body), len(body)]
    # The failed target's reason is what the judge stage reads back before it refuses to judge.
    assert [o["failure"] for o in json.loads(report.to_json())["sites"][0]["outcomes"]] == [
        f"HTTP {status} (1 request(s) recorded, the last one given up; no evidence on disk)"
    ] * 2
    assert report.failures_by_site() == {
        SITE_ID: {
            F.FEATURE_OVERPASS_NAMED: report.sites[0].outcomes[1].failure,
            F.FEATURE_ENWIKI: report.sites[0].outcomes[0].failure,
        }
    }
    assert not store.path_for(SITE_ID, F.FEATURE_ENWIKI).exists()


def test_a_transport_failure_is_recorded_and_the_next_target_is_still_asked(tmp_path: Path) -> None:
    """The defect the first live batch exposed: one timed-out request ended all 13 Overpass targets.

    A read timeout on target 1 must be target 1's outcome - recorded, with its reason - and target 2
    must still be fetched. Nothing here is swallowed: the failure is in the report *and* the ledger.
    The host's probe answers here (piece 4b), so the failure is the target's own - a host that never
    answers its probe is the other test.
    """
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        if urlsplit(url).path == "/":
            return httpx.Response(200, content=b"<html>the host is there</html>")
        if "wikipedia" in url:
            raise httpx.ReadTimeout("The read operation timed out", request=request)
        return httpx.Response(200, content=b'{"elements": []}')

    report, store, ledger = _collect(tmp_path, httpx.MockTransport(handler))

    assert report.sites[0].outcomes[0].feature == F.FEATURE_ENWIKI
    assert report.sites[0].outcomes[0].failure is not None
    assert "ReadTimeout" in report.sites[0].outcomes[0].failure
    # Target 2 was asked afterwards, and its (valid, empty) answer is on disk.
    assert report.sites[0].outcomes[1].succeeded
    assert store.path_for(SITE_ID, F.FEATURE_OVERPASS_NAMED).read_bytes() == b'{"elements": []}'
    assert report.fetches == 1
    assert [o.requests for o in report.sites[0].outcomes] == [F.MAX_ATTEMPTS, 1]
    assert len(calls) == F.MAX_ATTEMPTS + 1 + 2  # two probes, three lost attempts, one good fetch
    assert report.requests == F.MAX_ATTEMPTS + 1 + 2

    # The fetcher itself still raises: "could not ask" stays distinguishishable from "answered
    # with nothing" at the seam, and the stage is what turns it into recorded data.
    def dead(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection reset by peer", request=request)

    with F.HttpFetcher(transport=httpx.MockTransport(dead)) as fetcher:
        with pytest.raises(F.TransportFailure, match="ConnectError"):
            fetcher.get("https://example.invalid/x")

    rows = _target_lines(L.read_entries(ledger.path))
    assert len(rows) == F.MAX_ATTEMPTS + 1  # one line per attempt, failures included
    assert [r["outcome"] for r in rows] == [
        "transport_failure",
        "transport_failure",
        "transport_failure",
        "ok",
    ]
    assert rows[0]["http_status"] is None
    assert rows[0]["bytes"] == 0
    assert rows[0]["attempt"] == 1
    assert rows[0]["given_up"] is False
    assert rows[F.MAX_ATTEMPTS - 1]["attempt"] == F.MAX_ATTEMPTS
    assert rows[F.MAX_ATTEMPTS - 1]["given_up"] is True
    assert "ReadTimeout" in rows[0]["error"]
    assert rows[-1]["error"] is None
    # The two figures the ledger must be able to answer: how much traffic this batch spent (4
    # attempts) and how much of it bought nothing (3 of them).
    assert L.summarise(ledger.path).total.fetches == F.MAX_ATTEMPTS + 3 == len(rows) + 2
    assert L.summarise(ledger.path).total.fetch_failures == F.MAX_ATTEMPTS


def test_an_empty_result_is_a_success_while_a_failure_is_not(tmp_path: Path) -> None:
    """"I looked and there was nothing" is a result; "I could not look" is not (pilot, 287 bytes)."""
    empty = (
        b'{"version": 0.6, "generator": "Overpass API 0.7.62.11", "elements": []}'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=empty)

    report, store, ledger = _collect(tmp_path, httpx.MockTransport(handler))

    assert report.failed == []
    assert report.fetches == 2
    assert store.path_for(SITE_ID, F.FEATURE_OVERPASS_NAMED).read_bytes() == empty
    entries = _target_lines(L.read_entries(ledger.path))
    assert [e["outcome"] for e in entries] == ["ok", "ok"]
    assert [e["http_status"] for e in entries] == [200, 200]
    assert L.summarise(ledger.path).total.fetch_failures == 0


def test_a_429_is_retried_and_a_400_is_not(tmp_path: Path) -> None:
    """The weather is normal, and two kinds of bad weather are not the same thing.

    `COST.md` §1 measured 429 x1 and 504 x2 in the pilot *and* that the pilot's retries of those
    succeeded; a 400/403/404 is a stable answer, so asking twice would only buy the same one again.
    """
    calls: list[str] = []
    pauses: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        status = 400 if "wikipedia" in url else 429
        return httpx.Response(status, content=b"nope")

    report, _, ledger = _collect(tmp_path, httpx.MockTransport(handler), pauses=pauses)

    enwiki = next(o for o in report.sites[0].outcomes if o.feature == F.FEATURE_ENWIKI)
    overpass = next(o for o in report.sites[0].outcomes if o.feature == F.FEATURE_OVERPASS_NAMED)
    assert enwiki.requests == 1  # 400: asked once, recorded once
    assert overpass.requests == F.MAX_ATTEMPTS  # 429: two retries, then given up with the reason
    assert "HTTP 429" in str(overpass.failure)
    assert f"{F.MAX_ATTEMPTS} request(s) recorded" in str(overpass.failure)
    # The pause before retry 1 and before retry 2, and never a third attempt.
    assert pauses == list(F.RETRY_BACKOFF_SECONDS)
    rows = _target_lines(L.read_entries(ledger.path))
    assert len(rows) == 1 + F.MAX_ATTEMPTS
    assert [r["attempt"] for r in rows if r["http_status"] == 429] == [1, 2, 3]
    assert [r["given_up"] for r in rows if r["http_status"] == 429] == [False, False, True]
    assert len([c for c in calls if "/api/interpreter" in c]) == F.MAX_ATTEMPTS


def test_the_same_url_is_asked_again_and_no_other_host_is_tried(tmp_path: Path) -> None:
    """A retry is a second attempt at one target, not a quiet rotation of endpoints or mirrors."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(504, content=b"too busy")

    report, _, _ = _collect(tmp_path, httpx.MockTransport(handler))

    overpass = [c for c in calls if "/api/interpreter" in c]
    # One URL, three times. The pilot fell back to `overpass.kumi.systems` by hand; that is a
    # decision for the operator, so no other host appears in this runner's own traffic.
    assert len(set(overpass)) == 1
    assert len(overpass) == F.MAX_ATTEMPTS
    assert all(c.startswith(F.OVERPASS_ENDPOINT) for c in overpass)
    # The one other request on that host is the run's probe, and it is the host's own root.
    assert {urlsplit(c).netloc for c in calls} == {"en.wikipedia.org", "overpass-api.de"}
    assert [c for c in calls if c == F.host_probe_url(F.OVERPASS_ENDPOINT)] == [
        "https://overpass-api.de/"
    ]
    assert report.failed and all("HTTP 504" in str(o.failure) for o in report.failed)


def test_every_request_carries_the_projects_identifying_user_agent(tmp_path: Path) -> None:
    """overpass-api.de answers a client it will not serve with 89 bytes of plain text:

        "Please include a meaningful User-Agent string with your requests to avoid rate-limiting."

    (`phase3_pilot/evidence/Didnauri%2Foverpass_shiraki.txt`, which the log shows arrived with HTTP
    429 from a mirror.) The runner sends the project's own string - not httpx's default, and not
    nothing - so the header is asserted here rather than assumed.
    """
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("user-agent", ""))
        return httpx.Response(200, content=b"{}")

    _collect(tmp_path, httpx.MockTransport(handler))

    assert seen == [F.PHASE3_USER_AGENT] * 4  # two probes and two attempts, one string
    assert F.PHASE3_USER_AGENT == F.USER_AGENT
    assert "ancientnerds.com" in F.PHASE3_USER_AGENT
    assert not F.PHASE3_USER_AGENT.lower().startswith("python-httpx")


def test_the_overpass_target_gets_the_shorter_timeout_and_the_others_do_not(
    tmp_path: Path,
) -> None:
    """Overpass is the second opinion, so it is bounded (it is the host the first batch lost)."""
    bounds: list[tuple[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bounds.append((str(request.url), request.extensions["timeout"]["read"]))
        return httpx.Response(200, content=b"{}")

    _collect(tmp_path, httpx.MockTransport(handler))

    assert F.OVERPASS_TIMEOUT < 40.0  # the client default (`run.py --timeout`, HttpFetcher)
    by_url = dict(bounds)
    assert len(by_url) == 4  # two probes and two attempts
    # The bound belongs to the *host*, so the probe of `overpass-api.de` waits exactly as long as
    # that host's targets do: it asks the host's root, which no endpoint prefix covers.
    assert by_url[F.host_probe_url(F.OVERPASS_ENDPOINT)] == F.OVERPASS_TIMEOUT
    assert by_url[F.host_probe_url(F.WIKIPEDIA_ENDPOINT)] != F.OVERPASS_TIMEOUT
    for url, bound in by_url.items():
        overpass = urlsplit(url).hostname == "overpass-api.de"
        assert bound == (F.OVERPASS_TIMEOUT if overpass else 40.0)
        assert F.timeout_for(url) == (F.OVERPASS_TIMEOUT if overpass else None)
    assert F.timeout_for(F.OVERPASS_ENDPOINT + "?data=x") == F.OVERPASS_TIMEOUT
    assert F.timeout_for(F.host_probe_url(F.OVERPASS_ENDPOINT)) == F.OVERPASS_TIMEOUT
    assert F.timeout_for(F.WIKIPEDIA_ENDPOINT) is None


def test_one_ledger_line_per_fetch_carrying_the_site_the_url_the_status_and_the_bytes(
    tmp_path: Path,
) -> None:
    body = b'{"answer": 42}'
    report, store, ledger = _collect(tmp_path, _ok_transport(body))

    assert report.fetches == 2
    entries = _target_lines(L.read_entries(ledger.path))
    assert len(entries) == 2  # exactly one line per attempt, no more and no fewer
    assert {e["label"] for e in entries} == {
        f"{SITE_ID}/{F.FEATURE_ENWIKI}",
        f"{SITE_ID}/{F.FEATURE_OVERPASS_NAMED}",
    }
    for entry in entries:
        assert entry["kind"] == "fetch"
        assert entry["stage"] == "finder"
        assert entry["batch_id"] == "batch-0001"
        assert entry["url"].startswith("https://")
        assert entry["http_status"] == 200
        assert entry["bytes"] == len(body)
        assert entry["at"].endswith("+00:00")
        assert entry["outcome"] == "ok"
        assert entry["attempt"] == 1
        assert entry["given_up"] is False
        assert entry["error"] is None

    # And the ledger's own grouping still works: this is what keeps COST.md's per-stage split
    # (finder 62 / reviewer 14) reportable from the runner's ledger. The two probe lines are fetch
    # lines in the same stage - every request that left the machine has one.
    assert len(_probe_lines(L.read_entries(ledger.path))) == 2
    assert L.summarise(ledger.path).by_stage["finder"].fetches == 4

    # The evidence file's name is the URL-encoded label, exactly like the pilot's evidence/.
    slug = F.EvidenceStore.slug(SITE_ID, F.FEATURE_ENWIKI)
    assert slug.startswith(SITE_ID)
    assert "%2F" in slug
    assert store.path_for(SITE_ID, F.FEATURE_ENWIKI).read_bytes() == body


def test_a_site_with_no_lat_lon_finding_never_gets_an_invented_overpass_centre() -> None:
    site = _site_record(
        name="Karpasia - Town",
        findings=[{"test_id": "T05/disambiguated", "field": "country", "current_value": "Cyprus"}],
    )
    assert [t.feature for t in F.targets_for_site(site)] == [F.FEATURE_ENWIKI]


# ── the re-run: no silent second copy ────────────────────────────────────────────────────────


def test_a_second_run_skips_what_is_already_on_disk_and_duplicates_nothing(tmp_path: Path) -> None:
    calls: list[str] = []
    store = F.EvidenceStore(tmp_path / "evidence")
    ledger = L.Ledger(tmp_path / "LEDGER.jsonl")

    with F.HttpFetcher(transport=_ok_transport(calls=calls)) as fetcher:
        first = F.collect_batch(
            batch=_batch(), fetcher=fetcher, store=store, ledger=ledger, stage=Stage.FINDER
        )
        after_first = {
            path.name: _hash(path) for path in sorted((tmp_path / "evidence").glob("*.txt"))
        }
        # The second run gets a *fresh* fetcher, so nothing is served from a client's memory.
        second = F.collect_batch(
            batch=_batch(), fetcher=fetcher, store=store, ledger=ledger, stage=Stage.FINDER
        )

    assert first.fetches == 2
    assert second.fetches == 0
    assert second.skipped_existing == 2  # reported, not silent
    # Two probes and two fetches on the first run; **nothing** on the second - a host whose targets
    # are all already on disk is not probed, so the re-run costs what it cost before.
    assert len(calls) == 4
    assert len(_probe_requests(calls)) == 2
    assert second.probes == []
    assert len(L.read_entries(ledger.path)) == 4  # no second line for a request that did not happen
    after_second = {
        path.name: _hash(path) for path in sorted((tmp_path / "evidence").glob("*.txt"))
    }
    assert len(after_second) == 2
    assert after_second == after_first


def test_receiving_different_bytes_for_a_recorded_target_raises_instead_of_overwriting(
    tmp_path: Path,
) -> None:
    store = F.EvidenceStore(tmp_path / "evidence")
    store.write(site_id=SITE_ID, feature=F.FEATURE_ENWIKI, body=b"first answer")
    with pytest.raises(F.EvidenceConflict, match="different bytes"):
        store.write(site_id=SITE_ID, feature=F.FEATURE_ENWIKI, body=b"second answer")
    with pytest.raises(F.EvidenceConflict, match="different bytes"):
        store.write(site_id=SITE_ID, feature=F.FEATURE_ENWIKI, body=b"third answer")


# ── piece 4b: one reachability probe per host per run ────────────────────────────────────────
#
# The first live batch's ledger measured where its 38 minutes went: 117 of its 121 fetch lines sat
# on one host that answers nothing from this workstation (a TLS reset at 0.077 s), each line three
# 20-second waits - while the model calls of the same 15 sites took 39 seconds. The fix is one
# bounded request per host per run. The tests below pin it, including that a host which answers
# changes nothing at all.


class _CountingFetcher:
    """The seam with a counter: every URL it is asked for is recorded. No socket, no httpx.

    A host in `down_hosts` raises `TransportFailure` - the measured weather, where
    `overpass-api.de` resets after 0.077 s; every other host answers, with `statuses` overriding
    the 200 for a named host.
    """

    def __init__(
        self, *, down_hosts: set[str] | None = None, statuses: dict[str, int] | None = None
    ) -> None:
        self.urls: list[str] = []
        self._down = down_hosts or set()
        self._statuses = statuses or {}

    def get(self, url: str) -> F.FetchedPage:
        self.urls.append(url)
        host = urlsplit(url).hostname or ""
        if host in self._down:
            raise F.TransportFailure(f"GET {url}: ConnectError: connection reset by peer")
        return F.FetchedPage(
            status=self._statuses.get(host, 200),
            final_url=url,
            body=b'{"query": {}}',
            truncated=False,
        )


def _two_sites() -> list[dict[str, Any]]:
    """Two sites, each buying an `enwiki` and an `overpass_named` target."""
    return [_site_record(), _site_record(site_id=OTHER_SITE_ID, name="Other Cave")]


def _collect_with(
    tmp_path: Path, fetcher: F.Fetcher, sites: list[dict[str, Any]] | None = None
) -> tuple[F.BatchFetchReport, F.EvidenceStore, L.Ledger, list[float]]:
    """Collect a batch with an injected fetcher, recording (never sleeping through) the pauses."""
    store = F.EvidenceStore(tmp_path / "evidence")
    ledger = L.Ledger(tmp_path / "LEDGER.jsonl")
    pauses: list[float] = []
    report = F.collect_batch(
        batch=_batch(sites if sites is not None else _two_sites()),
        fetcher=fetcher,
        store=store,
        ledger=ledger,
        stage=Stage.FINDER,
        sleep=pauses.append,
    )
    return report, store, ledger, pauses


def test_a_host_that_does_not_answer_is_probed_once_and_its_targets_are_not_attempted(
    tmp_path: Path,
) -> None:
    """The measured defect: 39 targets x 3 attempts x 20 s against a host that answers nothing."""
    dead = "GET https://overpass-api.de/: ConnectError: connection reset by peer"
    fetcher = _CountingFetcher(down_hosts={"overpass-api.de"})

    report, store, ledger, pauses = _collect_with(tmp_path, fetcher)

    # The probe: exactly one request to the dead host, and it is the host's own root...
    assert [u for u in fetcher.urls if urlsplit(u).hostname == "overpass-api.de"] == [
        "https://overpass-api.de/"
    ]
    # ...so not one request went to any of its targets, which the report still names.
    overpass_targets = {
        t.url for s in report.sites for t in s.targets if t.feature == F.FEATURE_OVERPASS_NAMED
    }
    assert len(overpass_targets) == 2
    assert overpass_targets.isdisjoint(fetcher.urls)
    # And nothing waited: the dead host costs one request, not `MAX_ATTEMPTS` waits per target.
    assert pauses == []
    assert report.requests == 4  # two probes + the two enwiki targets, and nothing else
    assert report.fetches == 2  # the other host was fetched normally, in the same run
    assert all(store.exists(s.site_id, F.FEATURE_ENWIKI) for s in report.sites)

    # Each pending target on the dead host: exactly one ledger line, `attempt=0`, the probe's reason.
    rows = L.read_entries(ledger.path)
    not_attempted = [r for r in _target_lines(rows) if r["outcome"] == "host_unreachable"]
    assert len(not_attempted) == 2
    assert {r["label"] for r in not_attempted} == {
        f"{SITE_ID}/{F.FEATURE_OVERPASS_NAMED}",
        f"{OTHER_SITE_ID}/{F.FEATURE_OVERPASS_NAMED}",
    }
    for row in not_attempted:
        assert row["attempt"] == 0
        assert row["http_status"] is None
        assert row["bytes"] == 0
        assert row["given_up"] is False
        assert row["error"] == dead
    # Three lines bought nothing: the probe that found the host down, and the two targets it spared
    # from `MAX_ATTEMPTS` waits each. `fetches` counts all six lines; `fetch_failures` puts a
    # host-unreachable target in the same bucket as a transport failure.
    assert L.summarise(ledger.path).total.fetch_failures == 3
    assert L.summarise(ledger.path).total.fetches == 6
    assert [r["url"] for r in _probe_lines(rows)] == [
        "https://en.wikipedia.org/",
        "https://overpass-api.de/",
    ]

    # fetch.json carries the probe decision per host, and the two facts stay apart.
    payload = json.loads(report.to_json())
    assert payload["probes"] == [
        {
            "host": "en.wikipedia.org",
            "url": "https://en.wikipedia.org/",
            "reachable": True,
            "outcome": "ok",
            "http_status": 200,
            "reason": "HTTP 200",
        },
        {
            "host": "overpass-api.de",
            "url": "https://overpass-api.de/",
            "reachable": False,
            "outcome": "transport_failure",
            "http_status": None,
            "reason": dead,
        },
    ]
    assert payload["totals"]["not_attempted"] == 2
    assert payload["totals"]["probes"] == 2
    assert [s["not_attempted"] for s in payload["sites"]] == [1, 1]
    outcome = payload["sites"][0]["outcomes"][1]
    assert outcome["attempts"] == []
    assert outcome["requests"] == 0
    assert outcome["not_attempted"] == dead
    assert outcome["failure"] == (
        f"not attempted: this target's host did not answer the run's host probe ({dead}); "
        "0 request(s) recorded, no evidence on disk"
    )
    # The same site's *other* target is evidence that arrived: one sentence each, never blurred.
    assert payload["sites"][0]["outcomes"][0]["failure"] is None


def test_a_reachable_host_is_probed_exactly_once_for_all_of_its_targets(tmp_path: Path) -> None:
    """When the host answers, nothing about the run changes - except the two probe requests."""
    fetcher = _CountingFetcher()

    report, _, ledger, _ = _collect_with(tmp_path, fetcher)

    # One probe per host, and the same probe serves both sites' targets of that host.
    assert _probe_requests(fetcher.urls) == [
        "https://en.wikipedia.org/",
        "https://overpass-api.de/",
    ]
    assert len([u for u in fetcher.urls if "/w/api.php" in u]) == 2
    assert len([u for u in fetcher.urls if "/api/interpreter" in u]) == 2
    assert report.probe_requests == 2
    assert [(p.host, p.reachable, p.reason) for p in report.probes] == [
        ("en.wikipedia.org", True, "HTTP 200"),
        ("overpass-api.de", True, "HTTP 200"),
    ]
    # Every target was fetched, exactly as it was before the probe existed.
    assert report.requests == 6
    assert report.fetches == 4
    assert report.not_attempted == []
    assert report.failed == []
    assert len(_probe_lines(L.read_entries(ledger.path))) == 2


def test_the_probe_writes_its_own_ledger_line_and_any_http_answer_means_reachable(
    tmp_path: Path,
) -> None:
    """Brief item 3: a 404 is an answer, so it is not "down". Only silence is absence."""
    fetcher = _CountingFetcher(statuses={"en.wikipedia.org": 404})

    report, _, ledger, _ = _collect_with(tmp_path, fetcher)

    probe_lines = _probe_lines(L.read_entries(ledger.path))
    assert len(probe_lines) == 2  # one request, one line, per host per run
    assert {r["label"] for r in probe_lines} == {
        f"{F.HOST_PROBE_PREFIX}en.wikipedia.org",
        f"{F.HOST_PROBE_PREFIX}overpass-api.de",
    }
    line = next(r for r in probe_lines if r["label"].endswith("en.wikipedia.org"))
    assert line["kind"] == "fetch"  # an ordinary fetch line: every request has one
    assert line["stage"] == "finder"
    assert line["batch_id"] == "batch-0001"
    assert line["url"] == "https://en.wikipedia.org/"  # the host's root, never a target's URL
    assert line["http_status"] == 404
    assert line["outcome"] == "http_error"
    assert line["attempt"] == 1
    assert line["given_up"] is False
    assert line["error"] is None  # a response that arrived is recorded by its status
    assert line["bytes"] == len(b'{"query": {}}')
    # The 404 gated nothing: the host answered, so its targets were asked as before.
    assert next(p for p in report.probes if p.host == "en.wikipedia.org").reason == "HTTP 404"
    assert report.not_attempted == []
    assert len([u for u in fetcher.urls if "/w/api.php" in u]) == 2
    # A probe URL belongs to no target of the batch, so its line can never be read as an attempt.
    target_urls = {t.url for s in report.sites for t in s.targets}
    assert {r["url"] for r in probe_lines}.isdisjoint(target_urls)


# ── the CLI: offline unless told otherwise ───────────────────────────────────────────────────


def _prepare_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "runs"
    target = run_dir / "batch-0001" / "input.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(_batch(), ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return run_dir


class _FakeFetcher:
    """Stands in for `HttpFetcher` so the CLI's `--live` path needs no socket."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def get(self, url: str) -> F.FetchedPage:
        F.assert_named_feature(url)
        self.urls.append(url)
        return F.FetchedPage(status=200, final_url=url, body=b'{"answer": 42}', truncated=False)

    def close(self) -> None:
        return None


def test_the_fetch_command_without_live_lists_the_targets_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = _prepare_run_dir(tmp_path)
    ledger = tmp_path / "LEDGER.jsonl"

    code = R.main(
        ["fetch", "--batch-id", "batch-0001", "--run-dir", str(run_dir), "--ledger", str(ledger)]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["live"] is False
    assert payload["sites"] == 1
    assert [t["feature"] for t in payload["targets"]] == [
        F.FEATURE_ENWIKI,
        F.FEATURE_OVERPASS_NAMED,
    ]
    assert not ledger.exists()
    assert not (run_dir / "batch-0001" / "evidence").exists()
    assert not (run_dir / "batch-0001" / "fetch.json").exists()


def test_the_fetch_command_with_live_writes_ledger_lines_evidence_and_a_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = _prepare_run_dir(tmp_path)
    ledger = tmp_path / "LEDGER.jsonl"
    fake = _FakeFetcher()
    monkeypatch.setattr(F, "HttpFetcher", lambda timeout: fake)

    code = R.main(
        [
            "fetch",
            "--batch-id",
            "batch-0001",
            "--run-dir",
            str(run_dir),
            "--ledger",
            str(ledger),
            "--live",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["totals"]["fetches"] == 2
    assert payload["totals"]["requests"] == 4  # two host probes + two fetches
    assert payload["totals"]["probes"] == 2
    assert payload["totals"]["not_attempted"] == 0
    assert payload["totals"]["failed"] == 0
    assert len(fake.urls) == 4
    assert sorted(_probe_requests(fake.urls)) == [
        "https://en.wikipedia.org/",
        "https://overpass-api.de/",
    ]
    assert len(L.read_entries(ledger)) == 4
    evidence = sorted(p.name for p in (run_dir / "batch-0001" / "evidence").glob("*.txt"))
    assert len(evidence) == 2
    report = json.loads((run_dir / "batch-0001" / "fetch.json").read_text(encoding="utf-8"))
    assert report["totals"] == {
        "bytes": 28,
        "failed": 0,
        "fetches": 2,
        "non_2xx": 0,
        "not_attempted": 0,
        "probes": 2,
        "requests": 4,
        "skipped_existing": 0,
        "truncated": 0,
    }
    assert {p["host"] for p in report["probes"]} == {"en.wikipedia.org", "overpass-api.de"}
    assert all(p["reachable"] is True and p["reason"] == "HTTP 200" for p in report["probes"])


def test_the_fetch_command_records_a_transport_failure_and_writes_its_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Piece 4, at the CLI: a dead *target* is data, not a reason to exit 2 and lose the batch.

    The host's probe answers here (piece 4b), so these two targets are the ones that fail: a host
    that answers nothing at all is the other case - one probe line and two not-attempted records.
    """
    run_dir = _prepare_run_dir(tmp_path)
    ledger = tmp_path / "LEDGER.jsonl"

    class _DeadFetcher(_FakeFetcher):
        def get(self, url: str) -> F.FetchedPage:
            F.assert_named_feature(url)
            self.urls.append(url)
            if urlsplit(url).path == "/":
                return F.FetchedPage(status=200, final_url=url, body=b"root", truncated=False)
            raise F.TransportFailure(f"GET {url}: ConnectError: connection reset by peer")

    monkeypatch.setattr(F, "HttpFetcher", lambda timeout: _DeadFetcher())
    code = R.main(
        [
            "fetch",
            "--batch-id",
            "batch-0001",
            "--run-dir",
            str(run_dir),
            "--ledger",
            str(ledger),
            "--live",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["totals"]["failed"] == 2
    assert payload["totals"]["not_attempted"] == 0
    assert payload["totals"]["requests"] == 2 * F.MAX_ATTEMPTS + 2  # every attempt, plus two probes
    report = json.loads((run_dir / "batch-0001" / "fetch.json").read_text(encoding="utf-8"))
    assert report["totals"]["fetches"] == 0
    assert [o["requests"] for o in report["sites"][0]["outcomes"]] == [F.MAX_ATTEMPTS] * 2
    assert all("ConnectError" in o["failure"] for o in report["sites"][0]["outcomes"])
    rows = _target_lines(L.read_entries(ledger))
    assert len(rows) == 2 * F.MAX_ATTEMPTS
    assert {r["outcome"] for r in rows} == {"transport_failure"}
    assert [r["given_up"] for r in rows] == [False, False, True, False, False, True]
    assert (run_dir / "batch-0001" / "fetch.json").exists()
