# SPDX-License-Identifier: AGPL-3.0-only
"""api/services/search_console.py and api/services/crux.py: the shapes the
dashboard draws, from fake API answers in the form the live APIs gave on
2026-10-09."""

from __future__ import annotations

import asyncio
from datetime import date

import httpx
import pytest

from api.services import crux
from api.services import search_console as sc


def row(day, clicks, impressions, position=9.0):
    return {
        "keys": [day],
        "clicks": clicks,
        "impressions": impressions,
        "ctr": 0.01,
        "position": position,
    }


def test_the_daily_series_fills_the_days_search_console_left_out():
    days = sc.daily_series([row("2026-10-01", 3, 100), row("2026-10-04", 5, 200)])
    assert [d["day"] for d in days] == ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]
    assert days[1] == {"day": "2026-10-02", "clicks": 0, "impressions": 0, "position": None}
    assert days[3]["impressions"] == 200


def test_an_empty_property_has_no_series():
    assert sc.daily_series([]) == []


class FakeSession:
    """Answers each query by its dimensions, and records the windows asked for."""

    def __init__(self, by_dimension):
        self.by_dimension = by_dimension
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append(json)
        rows = self.by_dimension[tuple(json["dimensions"])]
        return FakeResponse({"rows": rows} if rows else {})


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


def test_the_overview_compares_the_last_finished_28_days_with_the_28_before(monkeypatch):
    session = FakeSession(
        {
            ("date",): [row("2026-09-01", 1, 10), row("2026-10-06", 57, 3389)],
            (): [{"clicks": 1056, "impressions": 76977, "ctr": 0.0137, "position": 8.9}],
            ("query",): [{"keys": ["ancient nerds"], "clicks": 38, "impressions": 49, "ctr": 0.7, "position": 1.0}],
            ("page",): [
                {"keys": ["https://ancientnerds.com/"], "clicks": 56, "impressions": 900, "ctr": 0.06, "position": 3.0},
                {"keys": ["https://ancientnerds.com/globe.html"], "clicks": 17, "impressions": 80, "ctr": 0.2, "position": 2.0},
            ],
        }
    )  # fmt: skip
    monkeypatch.setattr(sc, "_session", lambda: session)
    out = sc.search_overview(date(2026, 10, 9))
    # The windows hang off the last day Search Console has, not off today.
    assert out["current"]["start"] == "2026-09-09" and out["current"]["end"] == "2026-10-06"
    assert out["previous"]["start"] == "2026-08-12" and out["previous"]["end"] == "2026-09-08"
    assert out["current"]["clicks"] == 1056
    assert out["queries"] == [
        {"query": "ancient nerds", "clicks": 38, "impressions": 49, "position": 1.0}
    ]
    assert [p["path"] for p in out["pages"]] == ["/", "/globe.html"]
    assert out["pages_shown"] == {"current": 2, "previous": 2}
    assert len(out["days"]) == 36
    assert len(session.calls) == 6


def test_an_empty_window_is_zero_clicks_and_no_position(monkeypatch):
    session = FakeSession(
        {("date",): [row("2026-10-06", 0, 1)], (): [], ("query",): [], ("page",): []}
    )
    monkeypatch.setattr(sc, "_session", lambda: session)
    out = sc.search_overview(date(2026, 10, 9))
    assert out["previous"]["clicks"] == 0 and out["previous"]["position"] is None


def test_without_the_key_the_panel_says_why(monkeypatch):
    monkeypatch.delenv("GSC_SERVICE_ACCOUNT_JSON", raising=False)
    with pytest.raises(RuntimeError, match="GSC_SERVICE_ACCOUNT_JSON"):
        sc._session()


def _crux_record(form_factor):
    return {
        "record": {
            "key": {"origin": "https://ancientnerds.com", "formFactor": form_factor},
            "collectionPeriods": [
                {"firstDate": {"year": 2026, "month": 8, "day": 31}, "lastDate": {"year": 2026, "month": 9, "day": 27}},
                {"firstDate": {"year": 2026, "month": 9, "day": 7}, "lastDate": {"year": 2026, "month": 10, "day": 3}},
            ],
            "metrics": {
                "largest_contentful_paint": {"percentilesTimeseries": {"p75s": [2797, 2765]}},
                "interaction_to_next_paint": {"percentilesTimeseries": {"p75s": [436, None]}},
                "cumulative_layout_shift": {"percentilesTimeseries": {"p75s": ["0.04", "0.03"]}},
            },
        }
    }  # fmt: skip


def test_field_vitals_turn_the_history_into_weeks_and_numbers(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        import json

        return httpx.Response(200, json=_crux_record(json.loads(request.content)["formFactor"]))

    real_client = httpx.AsyncClient
    monkeypatch.setenv("CRUX_API_KEY", "k")
    monkeypatch.setattr(
        crux.httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    out = asyncio.run(crux.field_vitals())
    assert out["phone"] == {
        "weeks": ["2026-09-27", "2026-10-03"],
        "lcp": [2797.0, 2765.0],
        "inp": [436.0, None],
        "cls": [0.04, 0.03],
    }
    assert set(out) == {"phone", "desktop"}


def test_field_vitals_without_the_key_say_why(monkeypatch):
    monkeypatch.delenv("CRUX_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="CRUX_API_KEY"):
        asyncio.run(crux.field_vitals())
