"""Does T07 have teeth, and does it keep the one distinction it exists for?

Two things are checked here, both against synthetic data and a mocked transport - no
snapshot, no network:

* the classification: a 404/410 must fire, a 2xx must not;
* the line between "dead" and "we could not ask": a 403 (WAF), a 5xx, a DNS/connect
  failure must never be reported as a dead link, and must never be silently swallowed
  either - a site whose links could not be verified is *flagged*, not `pass`.

`collect()` is exercised through the real Fetcher with an `httpx.MockTransport`, so the
resumability claim (a second collect refetches nothing) is measured by counting the
requests that actually reach the transport, not asserted about the store.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
CENSUS_PARENT = REPO / "scripts" / "remediation"
if str(CENSUS_PARENT) not in sys.path:
    sys.path.insert(0, str(CENSUS_PARENT))

from census import model as M  # noqa: E402
from census.fetch import Fetcher, FetchError  # noqa: E402

T07 = importlib.import_module("census.tests.t07_link_sweep")

GONE = "https://gone.example/one"
CITED = "https://gone.example/cited"


# --------------------------------------------------------------------- fixtures
class _Snap:
    """The two snapshot accessors T07 reads, over a hand-written link table."""

    def __init__(self, links: list[dict[str, Any]]) -> None:
        self._links = links

    def rows(self, table: str) -> list[dict[str, Any]]:
        assert table == "site_content_links", table
        return self._links

    def by(self, table: str, key: str | None = None) -> dict[str, list[dict[str, Any]]]:
        assert (table, key) == ("site_content_links", "site_id"), (table, key)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in self._links:
            grouped.setdefault(str(row["site_id"]), []).append(row)
        return grouped


def _site(sid: str, description: str = "", citations: list[dict[str, Any]] | None = None,
          raw_data: Any = None) -> dict[str, Any]:
    site: dict[str, Any] = {
        "id": sid, "source_id": "ancient_nerds", "name": f"Site {sid}", "description": description,
    }
    if citations is not None:
        site["raw_data"] = {"description_citations": citations}
    if raw_data is not None:
        site["raw_data"] = raw_data
    return site


def _link(link_id: int, sid: str, url: str | None) -> dict[str, Any]:
    return {
        "id": link_id, "site_id": sid, "content_type": "reference",
        "content_source": "web_discovery", "content_url": url, "title": "A source",
        "link_metadata": {"domain": "gone.example", "link_type": "article"},
    }


def _routes(
    mapping: dict[str, tuple[int, str | None]],
) -> tuple[httpx.MockTransport, list[str]]:
    """A transport that answers `mapping[url]` and records every request it saw."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url}")
        status, location = mapping.get(str(request.url), (418, None))
        headers = {"location": location} if location else {}
        return httpx.Response(status, headers=headers)

    return httpx.MockTransport(handler), calls


def _failing_transport(raises: type[Exception]) -> tuple[httpx.MockTransport, list[str]]:
    """A transport that fails every request the way a dead route does."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url}")
        raise raises(f"cannot reach {request.url}")

    return httpx.MockTransport(handler), calls


def _ctx(tmp_path: Path, sites: list[dict[str, Any]], links: list[dict[str, Any]],
         transport: httpx.BaseTransport | None = None) -> Any:
    fetcher = Fetcher(tmp_path / "cache", max_retries=1, transport=transport)
    return SimpleNamespace(
        sites=sites, snap=_Snap(links), cache=tmp_path / "cache", out=tmp_path,
        fetch=fetcher, net=lambda: fetcher,
    )


def _actionable(ctx: Any) -> list[M.Finding]:
    t07 = T07
    t07.collect(ctx)
    return t07.run(ctx)


# --------------------------------------------------------------------- dead links
class TestT07DeadLinks:
    """The defect the check exists to find: a reference URL that no longer answers."""

    def test_a_404_is_reported_and_cleared(self, tmp_path):
        sid = "site-a"
        transport, calls = _routes({GONE: (404, None)})
        ctx = _ctx(tmp_path, [_site(sid)], [_link(7, sid, GONE)], transport)

        got = _actionable(ctx)

        assert len(got) == 1
        f = got[0]
        assert f.site_id == sid
        assert f.test_id == "T07/gone"
        assert f.severity is M.Severity.COSMETIC, "a dead favicon button is not read aloud"
        assert f.proposal is M.Proposal.CLEAR
        assert f.proposed_value is None, "CLEAR carries no value"
        assert f.current_value == GONE
        assert f.field == "site_content_links.content_url"
        assert f.confidence is M.Confidence.AUTHORITATIVE, "the host's own 404 is the source"
        assert f.applicable, "no [N] marker cites it, so the dead row can go"
        assert "site_content_links.id=7" in f.note
        assert f.evidence and f.evidence[0].host == "gone.example"
        assert calls == [f"HEAD {GONE}"], "a 404 is an answer; no GET retry"

    def test_a_410_is_gone_permanently(self, tmp_path):
        sid = "site-a"
        url = "https://gone.example/permanent"
        transport, _ = _routes({url: (410, None)})
        ctx = _ctx(tmp_path, [_site(sid)], [_link(1, sid, url)], transport)

        got = _actionable(ctx)

        assert [f.test_id for f in got] == ["T07/gone-permanent"]
        assert got[0].proposal is M.Proposal.CLEAR

    def test_a_cited_404_goes_to_review_and_is_never_cleared(self, tmp_path):
        """Clearing the link row would not touch the published footnote that cites it."""
        sid = "site-a"
        site = _site(sid, description="The fort was built in 500 BC [1].",
                     citations=[{"n": 1, "url": CITED, "title": "Source",
                                 "domain": "gone.example", "claim": "built 500 BC"}])
        transport, _ = _routes({CITED: (404, None)})
        ctx = _ctx(tmp_path, [site], [_link(3, sid, CITED)], transport)

        got = _actionable(ctx)

        assert len(got) == 1
        f = got[0]
        assert f.test_id == "T07/gone"
        assert f.severity is M.Severity.MODERATE
        assert f.proposal is M.Proposal.REVIEW
        assert f.proposed_value is None, "REVIEW must not carry a value"
        assert not f.applicable
        assert len(f.evidence) == 2, "the marker that cites the URL is part of the claim"
        assert "description_citations" in f.evidence[1].source
        assert "replacing the source" in f.note

    def test_a_citation_without_a_marker_does_not_make_a_link_cited(self, tmp_path):
        """The array alone is not a citation: the text has to point at it (T08 owns that)."""
        sid = "site-a"
        site = _site(sid, description="The fort was built in 500 BC.",
                     citations=[{"n": 1, "url": CITED, "title": "Source",
                                 "domain": "gone.example", "claim": "built 500 BC"}])
        transport, _ = _routes({CITED: (404, None)})
        ctx = _ctx(tmp_path, [site], [_link(3, sid, CITED)], transport)

        got = _actionable(ctx)

        assert got[0].proposal is M.Proposal.CLEAR

    def test_a_redirect_chain_is_followed_and_the_last_answer_is_the_finding(self, tmp_path):
        sid = "site-a"
        old = "http://old.example/x"
        new = "https://new.example/y"
        transport, calls = _routes({old: (301, new), new: (404, None)})
        ctx = _ctx(tmp_path, [_site(sid)], [_link(1, sid, old)], transport)

        got = _actionable(ctx)

        assert len(calls) == 2, "the redirect must be followed"
        assert got[0].current_value == old, "the row holds the original URL"
        assert new in got[0].note, "the final URL has to be recorded"
        assert new in got[0].evidence[0].quote

    def test_a_reachable_link_produces_nothing(self, tmp_path):
        sid = "site-a"
        transport, _ = _routes({GONE: (200, None)})
        ctx = _ctx(tmp_path, [_site(sid)], [_link(1, sid, GONE)], transport)

        assert _actionable(ctx) == []


# --------------------------------------------------------------------- not dead
class TestT07NeverCallsAnUnverifiedLinkDead:
    """403/5xx/unreachable are open questions. Neither "dead" nor "clean" is honest."""

    def test_a_403_is_refused_not_dead(self, tmp_path):
        sid = "site-a"
        transport, calls = _routes({GONE: (403, None)})
        ctx = _ctx(tmp_path, [_site(sid)], [_link(1, sid, GONE)], transport)

        got = _actionable(ctx)

        assert len(got) == 1
        f = got[0]
        assert f.test_id == "T07/refused"
        assert f.proposal is M.Proposal.REVIEW
        assert f.proposed_value is None
        assert f.confidence is M.Confidence.UNVERIFIABLE
        assert f.severity is M.Severity.COSMETIC, "no defect is known, only a question"
        assert not f.applicable
        assert "not a dead link" in f.note
        assert calls == [f"HEAD {GONE}", f"GET {GONE}"], "the client retries a refused HEAD"

    def test_a_5xx_is_a_server_error_not_a_dead_link(self, tmp_path):
        sid = "site-a"
        transport, _ = _routes({GONE: (503, None)})
        ctx = _ctx(tmp_path, [_site(sid)], [_link(1, sid, GONE)], transport)

        got = _actionable(ctx)

        assert [f.test_id for f in got] == ["T07/server-error"]
        assert got[0].proposal is M.Proposal.REVIEW
        assert got[0].confidence is M.Confidence.UNVERIFIABLE

    def test_a_transport_failure_is_unreachable_not_dead(self, tmp_path):
        sid = "site-a"
        transport, _ = _failing_transport(httpx.ConnectError)
        ctx = _ctx(tmp_path, [_site(sid)], [_link(1, sid, GONE)], transport)

        got = _actionable(ctx)

        assert [f.test_id for f in got] == ["T07/unreachable"]
        f = got[0]
        assert f.proposal is M.Proposal.REVIEW
        assert f.confidence is M.Confidence.UNVERIFIABLE
        assert "not evidence that the link is dead" in f.note
        assert "failed after 1 attempts" in f.evidence[0].quote, "the reason has to be kept"

    def test_an_unknown_status_is_unclassified_not_dead(self, tmp_path):
        sid = "site-a"
        transport, _ = _routes({GONE: (451, None)})
        ctx = _ctx(tmp_path, [_site(sid)], [_link(1, sid, GONE)], transport)

        got = _actionable(ctx)

        assert [f.test_id for f in got] == ["T07/unclassified"]
        assert "451" in got[0].note
        assert got[0].confidence is M.Confidence.UNVERIFIABLE

    def test_a_refused_citation_is_reported_as_unverified_citation(self, tmp_path):
        sid = "site-a"
        site = _site(sid, description="A claim [1].",
                     citations=[{"n": 1, "url": CITED, "title": "S", "domain": "d",
                                 "claim": "c"}])
        transport, _ = _routes({CITED: (403, None)})
        ctx = _ctx(tmp_path, [site], [_link(1, sid, CITED)], transport)

        got = _actionable(ctx)

        assert got[0].test_id == "T07/refused"
        assert "citation is unverified" in got[0].note
        assert len(got[0].evidence) == 2


# --------------------------------------------------------------------- collector
class TestT07Collector:
    """The collector is the only network part, so its contract is measured, not asserted."""

    def test_collect_probes_every_distinct_url_once_and_is_resumable(self, tmp_path):
        sid_a, sid_b = "site-a", "site-b"
        links = [
            _link(1, sid_a, GONE),
            _link(2, sid_b, GONE),                 # same URL on another site
            _link(3, sid_a, "https://ok.example/"),
        ]
        transport, calls = _routes({GONE: (404, None), "https://ok.example/": (200, None)})
        ctx = _ctx(tmp_path, [_site(sid_a), _site(sid_b)], links, transport)

        T07.collect(ctx)
        assert sorted(calls) == [f"HEAD {GONE}", "HEAD https://ok.example/"]

        calls.clear()
        T07.collect(ctx)
        assert calls == [], "a second collect must be offline: the store holds every answer"

        rec = T07.read_probe(ctx, GONE)
        assert rec is not None
        assert rec["status"] == 404, "the store covers what the Fetcher cache does not"

    def test_a_transport_failure_is_retried_by_the_next_collect(self, tmp_path):
        """A record without an HTTP status is about the route, not the link."""
        sid = "site-a"
        transport, calls = _failing_transport(httpx.ConnectError)
        ctx = _ctx(tmp_path, [_site(sid)], [_link(1, sid, GONE)], transport)

        T07.collect(ctx)
        rec = T07.read_probe(ctx, GONE)
        assert rec is not None and rec["status"] is None
        assert not T07._is_final(rec)

        probed = len(calls)
        T07.collect(ctx)
        assert len(calls) > probed, "a failure with no HTTP status must be probed again"

    def test_a_wholesale_network_failure_is_never_recorded_as_link_rot(self, tmp_path):
        n = T07.MIN_SWEEP + 10
        sites = [_site(f"site-{i}") for i in range(n)]
        links = [_link(i, f"site-{i}", f"https://host-{i}.example/x") for i in range(n)]
        transport, _ = _failing_transport(httpx.ConnectError)
        ctx = _ctx(tmp_path, sites, links, transport)

        with pytest.raises(FetchError, match=f"not one of the {n} probes"):
            T07.collect(ctx)

    def test_run_refuses_to_decide_a_link_the_collector_never_probed(self, tmp_path):
        sid = "site-a"
        ctx = _ctx(tmp_path, [_site(sid)], [_link(1, sid, GONE)])

        with pytest.raises(RuntimeError, match="no probe record"):
            T07.run(ctx)

    def test_a_site_without_reference_links_is_not_applicable(self, tmp_path):
        ctx = _ctx(tmp_path, [_site("site-a")], [])

        assert T07.applies_to(ctx.sites[0], ctx) is False
        assert T07.run(ctx) == []

    def test_a_missing_content_url_is_not_a_link(self, tmp_path):
        sid = "site-a"
        ctx = _ctx(tmp_path, [_site(sid)], [_link(1, sid, None), _link(2, sid, "  ")])

        assert T07._distinct_urls(ctx) == []
        assert T07.applies_to(ctx.sites[0], ctx) is False
        assert T07.run(ctx) == [], "applies_to() and run() must agree on the same site"

    def test_classify_covers_every_status_family(self):
        cases = {None: "unreachable", 200: "reachable", 302: "reachable", 404: "gone",
                 410: "gone-permanent", 401: "refused", 403: "refused", 429: "refused",
                 400: "refused", 501: "refused", 500: "server-error", 503: "server-error",
                 451: "unclassified"}
        for status, expected in cases.items():
            assert T07.classify({"status": status}) == expected, status

    def test_a_raw_data_that_is_not_an_object_fails_loudly(self, tmp_path):
        """A snapshot shape change must stop the run, not silently drop every citation."""
        sid = "site-a"
        site = _site(sid, description="A claim [1].", raw_data="{\"description_citations\": []}")
        transport, _ = _routes({GONE: (200, None)})
        ctx = _ctx(tmp_path, [site], [_link(1, sid, GONE)], transport)

        T07.collect(ctx)
        with pytest.raises(ValueError, match="raw_data is str"):
            T07.run(ctx)
