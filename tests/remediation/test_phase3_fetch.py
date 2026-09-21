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
) -> tuple[F.BatchFetchReport, F.EvidenceStore, L.Ledger]:
    store = F.EvidenceStore(tmp_path / "evidence")
    ledger = L.Ledger(tmp_path / ledger_name)
    with F.HttpFetcher(transport=transport) as fetcher:
        report = F.collect_batch(
            batch=_batch(sites),
            fetcher=fetcher,
            store=store,
            ledger=ledger,
            stage=Stage.FINDER,
        )
    return report, store, ledger


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    site = _site_record(
        findings=[{"test_id": "T03/all-outside", "field": "period_start", "current_value": -500}]
    )
    with pytest.raises(R.InputError, match="no target rule"):
        F.targets_for_site(site)


# ── the fetch itself: measured outcomes ──────────────────────────────────────────────────────


@pytest.mark.parametrize("status", [403, 404, 504, 429])
def test_a_non_2xx_is_recorded_as_data_and_never_raised(tmp_path: Path, status: int) -> None:
    body = f"<html>{status} page</html>".encode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body)

    report, store, ledger = _collect(tmp_path, httpx.MockTransport(handler))

    assert report.fetches == 2  # both targets were attempted, the batch did not stop
    assert [s for _, s in report.non_2xx] == [status, status]
    entries = L.read_entries(ledger.path)
    assert [e["http_status"] for e in entries] == [status, status]
    assert [e["bytes"] for e in entries] == [len(body), len(body)]
    assert store.path_for(SITE_ID, F.FEATURE_ENWIKI).read_bytes() == body


def test_a_transport_failure_raises_and_is_never_an_empty_result(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection reset by peer", request=request)

    with F.HttpFetcher(transport=httpx.MockTransport(handler)) as fetcher:
        with pytest.raises(F.TransportFailure, match="ConnectError"):
            fetcher.get("https://example.invalid/x")

    # Through the stage: the batch stops at the unmeasurable fetch and records nothing for it.
    # An empty result would read as "the source had nothing", which is a different claim.
    store = F.EvidenceStore(tmp_path / "evidence")
    ledger = L.Ledger(tmp_path / "LEDGER.jsonl")
    with F.HttpFetcher(transport=httpx.MockTransport(handler)) as fetcher:
        with pytest.raises(F.TransportFailure):
            F.collect_batch(
                batch=_batch(), fetcher=fetcher, store=store, ledger=ledger, stage=Stage.FINDER
            )
    assert not ledger.path.exists()
    assert list((tmp_path / "evidence").glob("*.txt")) == []


def test_one_ledger_line_per_fetch_carrying_the_site_the_url_the_status_and_the_bytes(
    tmp_path: Path,
) -> None:
    body = b'{"answer": 42}'
    report, store, ledger = _collect(tmp_path, _ok_transport(body))

    assert report.fetches == 2
    entries = L.read_entries(ledger.path)
    assert len(entries) == 2  # exactly one line per fetch, no more and no fewer
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

    # And the ledger's own grouping still works: this is what keeps COST.md's per-stage split
    # (finder 62 / reviewer 14) reportable from the runner's ledger.
    assert L.summarise(ledger.path).by_stage["finder"].fetches == 2

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
    assert len(calls) == 2  # the transport was asked exactly twice in total
    assert len(L.read_entries(ledger.path)) == 2  # no second line for a fetch that did not happen
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
    assert len(fake.urls) == 2
    assert len(L.read_entries(ledger)) == 2
    evidence = sorted(p.name for p in (run_dir / "batch-0001" / "evidence").glob("*.txt"))
    assert len(evidence) == 2
    report = json.loads((run_dir / "batch-0001" / "fetch.json").read_text(encoding="utf-8"))
    assert report["totals"] == {
        "bytes": 28,
        "fetches": 2,
        "non_2xx": 0,
        "skipped_existing": 0,
        "truncated": 0,
    }


def test_the_fetch_command_reports_a_transport_failure_instead_of_a_clean_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = _prepare_run_dir(tmp_path)

    class _DeadFetcher(_FakeFetcher):
        def get(self, url: str) -> F.FetchedPage:
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
            str(tmp_path / "LEDGER.jsonl"),
            "--live",
        ]
    )

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert "ConnectError" in payload["error"]
    assert not (run_dir / "batch-0001" / "fetch.json").exists()
