"""Tests for the deterministic census core (scripts/remediation/census/).

Loaded by file path, not by `import scripts.remediation...`: a dependency installs a
top-level package named `scripts` into site-packages which shadows this repo's
scripts/ directory (the same trap tests/scripts/test_funnel_report.py documents).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CENSUS_PARENT = REPO / "scripts" / "remediation"
if str(CENSUS_PARENT) not in sys.path:
    sys.path.insert(0, str(CENSUS_PARENT))

import httpx  # noqa: E402
from census import fetch as F  # noqa: E402
from census import model as M  # noqa: E402


# --------------------------------------------------------------------- model
class TestFindingContract:
    def test_set_without_value_is_rejected(self):
        """An unfilled proposal invents data - refuse it at construction."""
        with pytest.raises(ValueError, match="needs a proposed_value"):
            M.Finding(
                site_id="s1", test_id="T/x", field="country",
                severity=M.Severity.MODERATE, dimension="D3",
                proposal=M.Proposal.SET,
            )

    def test_review_must_not_carry_a_value(self):
        """REVIEW means 'a human decides'; smuggling a value in would let it be applied."""
        with pytest.raises(ValueError, match="must not carry a value"):
            M.Finding(
                site_id="s1", test_id="T/x", field="country",
                severity=M.Severity.MODERATE, dimension="D3",
                proposal=M.Proposal.REVIEW, proposed_value="Greece",
            )

    def test_clear_is_allowed_without_a_value(self):
        """'An empty field beats a wrong one' - clearing must be expressible."""
        f = M.Finding(
            site_id="s1", test_id="T/x", field="period_start",
            severity=M.Severity.SEVERE, dimension="D1",
            proposal=M.Proposal.CLEAR,
        )
        assert f.proposed_value is None

    def test_unevidenced_finding_is_never_applicable(self):
        f = M.Finding(
            site_id="s1", test_id="T/x", field="country",
            severity=M.Severity.MODERATE, dimension="D3",
            proposal=M.Proposal.SET, proposed_value="Greece",
            confidence=M.Confidence.TWO_SOURCE,
        )
        assert f.applicable is False

    def test_two_sources_from_one_host_count_as_one(self):
        """Anti-pattern 6: two pages of one wiki are not two independent sources."""
        f = M.Finding(
            site_id="s1", test_id="T/x", field="country",
            severity=M.Severity.MODERATE, dimension="D3",
            proposal=M.Proposal.SET, proposed_value="Greece",
            confidence=M.Confidence.TWO_SOURCE,
            evidence=[
                M.Evidence("a", "https://www.wikidata.org/wiki/Q1"),
                M.Evidence("b", "https://wikidata.org/wiki/Q2"),
                M.Evidence("c", "https://pleiades.stoa.org/places/1"),
            ],
        )
        assert f.independent_sources == 2
        assert f.applicable is True

    def test_weak_confidence_is_not_applicable(self):
        f = M.Finding(
            site_id="s1", test_id="T/x", field="country",
            severity=M.Severity.MODERATE, dimension="D3",
            proposal=M.Proposal.SET, proposed_value="Greece",
            confidence=M.Confidence.WEAK,
            evidence=[M.Evidence("a", "https://x.org")],
        )
        assert f.applicable is False

    def test_change_key_is_stable_and_transition_specific(self):
        def mk(cur, new):
            return M.Finding(
                site_id="s1", test_id="T/x", field="country",
                severity=M.Severity.MODERATE, dimension="D3",
                current_value=cur, proposal=M.Proposal.SET, proposed_value=new,
            ).change_key

        assert mk("Turkey", "Türkiye") == mk("Turkey", "Türkiye")
        assert mk("Turkey", "Türkiye") != mk("Turkey", "Greece")
        assert mk("Turkey", "Türkiye") != mk("Anatolia", "Türkiye")

    def test_to_json_roundtrips_enums_and_evidence(self):
        import json

        f = M.Finding(
            site_id="s1", test_id="T/x", field="country",
            severity=M.Severity.MODERATE, dimension="D3",
            current_value="Georgia (country)",
            proposal=M.Proposal.SET, proposed_value="Georgia",
            confidence=M.Confidence.AUTHORITATIVE,
            evidence=[M.Evidence("iso3166", "https://example.org/iso")],
        )
        d = json.loads(f.to_json())
        assert d["severity"] == "moderate"
        assert d["proposal"] == "set"
        assert d["confidence"] == "authoritative"
        assert d["applicable"] is True
        assert d["evidence"][0]["source"] == "iso3166"

    def test_evidence_host_ignores_www(self):
        assert M.Evidence("a", "https://WWW.Example.org/x").host == "example.org"
        assert M.Evidence("plain-label").host == "plain-label"


# --------------------------------------------------------------------- fetch
class TestRetryAfter:
    """Regression cover for a real bug: str.isdigit() is not a float() guard."""

    def test_plain_seconds(self):
        assert F._retry_after_seconds("5") == 5.0

    def test_missing_or_junk_falls_back_to_none(self):
        for junk in (None, "", "Wed, 21 Oct 2026 07:28:00 GMT", "abc", "-1"):
            assert F._retry_after_seconds(junk) is None

    def test_superscript_digit_is_not_a_number(self):
        """'\u00b2'.isdigit() is True while float('\u00b2') raises - the old code crashed here."""
        assert "\u00b2".isdigit() is True
        assert F._retry_after_seconds("\u00b2") is None

    def test_absurd_delay_is_rejected(self):
        assert F._retry_after_seconds("99999") is None


class TestJitter:
    def test_is_bounded_and_reproducible(self):
        a = F._jitter("https://example.org/x", 0)
        assert 0.0 <= a < 1.0
        assert a == F._jitter("https://example.org/x", 0)

    def test_decorrelates_urls_and_attempts(self):
        base = F._jitter("https://example.org/a", 0)
        assert base != F._jitter("https://example.org/b", 0)
        assert base != F._jitter("https://example.org/a", 1)


def _transport(routes: dict[str, tuple[int, str, dict[str, str]]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        key = str(request.url).split("?")[0]
        if key not in routes:
            return httpx.Response(404, text="", request=request)
        status, body, headers = routes[key]
        return httpx.Response(status, text=body, headers=headers, request=request)

    return httpx.MockTransport(handler)


class TestFetcher:
    def test_second_call_is_served_from_cache(self, tmp_path):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, text='{"ok": 1}', request=request)

        with F.Fetcher(root=tmp_path, transport=httpx.MockTransport(handler)) as fet:
            first = fet.get_json("https://example.org/a")
            second = fet.get_json("https://example.org/a")
        assert first["json"] == {"ok": 1}
        assert second["json"] == {"ok": 1}
        assert calls["n"] == 1, "the cache did not absorb the second request"
        assert fet.stats["cache_hits"] == 1

    def test_404_is_returned_not_raised(self, tmp_path):
        """'not found' and 'could not ask' must stay distinguishable."""
        with F.Fetcher(root=tmp_path, transport=_transport({})) as fet:
            p = fet.get_json("https://example.org/missing")
        assert p["status"] == 404
        assert p["json"] is None

    def test_transport_failure_raises_rather_than_reporting_absence(self, tmp_path):
        def boom(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host", request=request)

        with F.Fetcher(root=tmp_path, transport=httpx.MockTransport(boom), max_retries=2) as fet:
            with pytest.raises(F.FetchError):
                fet.get_json("https://example.org/down")

    def test_non_404_error_raises(self, tmp_path):
        with F.Fetcher(root=tmp_path, transport=_transport(
                {"https://example.org/forbidden": (403, "", {})})) as fet:
            with pytest.raises(F.FetchError):
                fet.get_json("https://example.org/forbidden")

    def test_server_error_is_retried_tenaciously(self, tmp_path):
        state = {"n": 0}

        def flaky(request: httpx.Request) -> httpx.Response:
            state["n"] += 1
            if state["n"] < 3:
                return httpx.Response(503, headers={"Retry-After": "0"}, request=request)
            return httpx.Response(200, text='{"ok": true}', request=request)

        with F.Fetcher(root=tmp_path, transport=httpx.MockTransport(flaky), max_retries=4) as fet:
            p = fet.get_json("https://example.org/flaky")
        assert p["json"] == {"ok": True}
        assert state["n"] == 3

    def test_head_falls_back_to_get_on_405(self, tmp_path):
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.method)
            if request.method == "HEAD":
                return httpx.Response(405, request=request)
            return httpx.Response(200, text="x", request=request)

        with F.Fetcher(root=tmp_path, transport=httpx.MockTransport(handler)) as fet:
            p = fet.head("https://example.org/h")
        assert seen == ["HEAD", "GET"]
        assert p["status"] == 200

    def test_head_falls_back_to_get_when_bot_protection_refuses_head(self, tmp_path):
        """A WAF refusing HEAD must not be recorded as a dead link."""
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.method)
            if request.method == "HEAD":
                return httpx.Response(403, request=request)
            return httpx.Response(200, text="portal", request=request)

        with F.Fetcher(root=tmp_path, transport=httpx.MockTransport(handler)) as fet:
            p = fet.head("https://example.org/portal")
        assert seen == ["HEAD", "GET"]
        assert p["status"] == 200

    def test_get_text_raises_on_forbidden(self, tmp_path):
        with F.Fetcher(root=tmp_path, transport=_transport(
                {"https://example.org/denied": (403, "", {})})) as fet:
            with pytest.raises(F.FetchError):
                fet.get_text("https://example.org/denied")

    def test_get_text_passes_404_through_as_a_value(self, tmp_path):
        with F.Fetcher(root=tmp_path, transport=_transport({})) as fet:
            assert fet.get_text("https://example.org/gone")["status"] == 404

    def test_unreadable_cache_entry_is_refetched_not_crashed(self, tmp_path):
        with F.Fetcher(root=tmp_path, transport=_transport(
                {"https://example.org/a": (200, "{}", {})})) as fet:
            fet.get_json("https://example.org/a")
            key = F.Fetcher._key("GET", "https://example.org/a", None)
            (tmp_path / "json" / key[:2] / f"{key}.json").write_text("{not json", encoding="utf-8")
            assert fet.get_json("https://example.org/a")["status"] == 200

    def test_map_preserves_order_and_reports_exceptions(self, tmp_path):
        with F.Fetcher(root=tmp_path, transport=_transport({})) as fet:
            out = fet.map(lambda i: 10 - i, [1, 2, 3], workers=3)
        assert out == [9, 8, 7]

        def half(x):
            if x == 2:
                raise ValueError("boom")
            return x

        with F.Fetcher(root=tmp_path, transport=_transport({})) as fet:
            out = fet.map(half, [1, 2, 3], workers=3)
        assert out[0] == 1 and out[2] == 3
        assert isinstance(out[1], ValueError)


def test_chunked_splits_without_losing_rows():
    assert F.chunked([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
    assert F.chunked([], 3) == []
