"""The strict MiniMax coding-plan helpers and their legacy wrappers, over `httpx.MockTransport`.

`minimax_search` and `minimax_vlm` turned every failure into an empty result until 2026-09-22, so a dead
key, a spent budget and "nothing found" were the same value. `minimax_search_strict` /
`minimax_vlm_strict` raise a typed error for each of them instead, and the old names stay as thin
wrappers that keep their callers' empty-on-failure contract. Every branch below is driven through a
real `httpx.Client` with a mock transport - a `MagicMock` client would accept calls the real one
refuses (a `MagicMock` response has a `.content` of any length and a `.json()` of any shape).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from pipeline.lyra import minimax_shared as S
from pipeline.lyra.minimax_limiter import QuotaExhaustedError

KEY = "sk-cp-test-SECRET-never-logged"


def _client(handler: Any) -> httpx.Client:
    return httpx.Client(
        base_url="https://api.minimax.io",
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        transport=httpx.MockTransport(handler),
    )


def _answer(status: int, body: Any, *, raw: bytes | None = None) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        if raw is not None:
            return httpx.Response(status, content=raw)
        return httpx.Response(status, json=body)

    return handler


ORGANIC = [
    {"title": "Byllis", "link": "https://en.wikipedia.org/wiki/Byllis", "snippet": "An ancient city.", "date": "2021"},
    {"title": "No page", "link": "", "snippet": "x"},
    {"title": "Second", "link": "https://example.org/b", "snippet": "s2"},
]  # fmt: skip


def test_a_successful_search_keeps_every_entry_and_ranks_the_ones_that_name_a_page() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json={"base_resp": {"status_code": 0, "status_msg": "success"}, "organic": ORGANIC}
        )

    response = S.minimax_search_strict(_client(handler), '"Byllis" Albania')
    assert seen[0].url.path == S.MINIMAX_SEARCH_PATH
    assert json.loads(seen[0].content) == {"q": '"Byllis" Albania'}
    assert seen[0].headers["authorization"] == f"Bearer {KEY}"
    assert [item.url for item in response.items] == [
        "https://en.wikipedia.org/wiki/Byllis",
        "",
        "https://example.org/b",
    ]
    assert [(hit.rank, hit.result.url) for hit in response.hits] == [
        (1, "https://en.wikipedia.org/wiki/Byllis"),
        (3, "https://example.org/b"),
    ]
    assert response.linkless == 1
    assert response.http_status == 200
    assert response.body_bytes > 0


def test_the_legacy_wrapper_returns_exactly_the_old_objects_linkless_entries_included() -> None:
    body = {"base_resp": {"status_code": 0}, "organic": ORGANIC}
    got = S.minimax_search(_client(_answer(200, body)), "q")
    old = [
        S.WebSearchResult(
            title=item.get("title", ""),
            url=item.get("link", ""),
            snippet=item.get("snippet", ""),
            date=item.get("date", ""),
        )
        for item in ORGANIC
    ]
    assert got == old


def test_an_empty_organic_list_is_a_real_no_hits_and_not_an_error() -> None:
    response = S.minimax_search_strict(
        _client(_answer(200, {"base_resp": {"status_code": 0}, "organic": []})), "q"
    )
    assert response.items == ()
    assert response.hits == ()
    assert response.linkless == 0


def test_a_body_without_organic_is_not_no_hits() -> None:
    client = _client(_answer(200, {"base_resp": {"status_code": 0}}))
    with pytest.raises(S.CodingPlanResponseError, match="no `organic`"):
        S.minimax_search_strict(client, "q")
    assert S.minimax_search(client, "q") == []


@pytest.mark.parametrize(
    ("status", "body", "error", "family"),
    [
        (401, "unauthorized", S.CodingPlanAuthError, S.MiniMaxAuthError),
        (403, "forbidden", S.CodingPlanAuthError, S.MiniMaxAuthError),
        (429, "Token Plan usage limit reached (2056)", S.CodingPlanQuotaError, QuotaExhaustedError),
        (429, "token plan rate limit reached (2062)", S.CodingPlanThrottleError, S.CodingPlanError),
        (429, "too many requests", S.CodingPlanHTTPError, S.MiniMaxTerminalError),
        (500, "internal error", S.CodingPlanHTTPError, S.MiniMaxTerminalError),
        (400, "invalid api key", S.CodingPlanAuthError, S.MiniMaxAuthError),
    ],
)
def test_every_non_2xx_raises_its_own_type_and_the_wrapper_still_returns_empty(
    status: int, body: str, error: type[Exception], family: type[Exception]
) -> None:
    client = _client(_answer(status, None, raw=body.encode()))
    with pytest.raises(error) as caught:
        S.minimax_search_strict(client, "q")
    assert isinstance(caught.value, family)
    assert caught.value.http_status == status
    assert caught.value.body_bytes == len(body)
    assert KEY not in str(caught.value)
    assert S.minimax_search(client, "q") == []


@pytest.mark.parametrize(
    ("code", "error"),
    [
        (1004, S.CodingPlanAuthError),
        (2038, S.CodingPlanAuthError),
        (2056, S.CodingPlanQuotaError),
        (2062, S.CodingPlanThrottleError),
        (1000, S.CodingPlanResponseError),
    ],
)
def test_a_2xx_whose_base_resp_reports_an_error_raises_and_is_never_read_as_hits(
    code: int, error: type[Exception]
) -> None:
    body = {"base_resp": {"status_code": code, "status_msg": "nope"}, "organic": ORGANIC}
    client = _client(_answer(200, body))
    with pytest.raises(error, match=str(code)) as caught:
        S.minimax_search_strict(client, "q")
    assert caught.value.http_status == 200
    assert S.minimax_search(client, "q") == []


def test_a_base_resp_that_signals_nothing_is_accepted() -> None:
    """`base_resp: {}` carries no code, so it reports no error; the results are read."""
    response = S.minimax_search_strict(
        _client(_answer(200, {"base_resp": {}, "organic": ORGANIC})), "q"
    )
    assert len(response.items) == 3


def test_a_body_that_is_not_json_raises_and_the_wrapper_returns_empty() -> None:
    client = _client(_answer(200, None, raw=b"<html>gateway</html>"))
    with pytest.raises(S.CodingPlanResponseError, match="not JSON"):
        S.minimax_search_strict(client, "q")
    assert S.minimax_search(client, "q") == []


def test_no_response_at_all_is_a_transport_error_with_no_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection reset", request=request)

    client = _client(handler)
    with pytest.raises(S.CodingPlanTransportError) as caught:
        S.minimax_search_strict(client, "q")
    assert caught.value.http_status is None
    assert caught.value.body_bytes == 0
    assert S.minimax_search(client, "q") == []


@pytest.mark.parametrize(
    "body",
    [
        [1, 2],
        {"organic": "nope"},
        {"organic": [["not", "an", "object"]]},
    ],
)
def test_a_contract_break_raises_from_both_the_strict_call_and_the_wrapper(body: Any) -> None:
    """The old loop raised AttributeError/TypeError on these bodies too; a contract break stays loud."""
    client = _client(_answer(200, body))
    with pytest.raises(S.CodingPlanShapeError):
        S.minimax_search_strict(client, "q")
    with pytest.raises(S.CodingPlanShapeError):
        S.minimax_search(client, "q")


@pytest.mark.parametrize(
    "base_resp",
    [
        "broken",
        {"status_code": "0"},
        # `False == 0` in Python: without the bool exclusion this would read as success.
        {"status_code": False},
        {"status_code": True},
    ],
)
def test_a_malformed_base_resp_is_a_new_raise_where_the_old_wrapper_returned_the_hits(
    base_resp: Any,
) -> None:
    """A deliberate change for web_research, tweet_verifier and theo_sources: the old code never read
    `base_resp` and returned the results beside it. A body that breaks the documented contract is not
    a set of hits, so both the strict call and the wrapper now raise instead."""
    client = _client(_answer(200, {"base_resp": base_resp, "organic": ORGANIC}))
    with pytest.raises(S.CodingPlanShapeError, match="base_resp"):
        S.minimax_search_strict(client, "q")
    with pytest.raises(S.CodingPlanShapeError, match="base_resp"):
        S.minimax_search(client, "q")


def test_a_body_that_names_both_the_budget_and_the_rate_cap_is_the_budget() -> None:
    """`minimax_limiter.is_plan_rate_throttle`'s own rule: check the budget first (conservative)."""
    body = {"error": "token plan rate limit reached (2062); usage limit reached (2056)"}
    with pytest.raises(S.CodingPlanQuotaError):
        S.minimax_search_strict(_client(_answer(429, body)), "q")
    both = {"base_resp": {"status_code": 2062, "status_msg": "usage limit reached"}, "organic": []}
    with pytest.raises(S.CodingPlanQuotaError):
        S.minimax_search_strict(_client(_answer(200, both)), "q")


# ── the VLM endpoint ──────────────────────────────────────────────────────────────────────────────


def test_the_vlm_posts_a_data_uri_and_returns_the_content() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"content": '{"verdict":"accept"}', "base_resp": {}})

    client = _client(handler)
    assert S.minimax_vlm_strict(client, b"\xff\xd8jpeg", "is it?") == '{"verdict":"accept"}'
    assert S.minimax_vlm(client, b"\xff\xd8jpeg", "is it?") == '{"verdict":"accept"}'
    payload = json.loads(seen[0].content)
    assert seen[0].url.path == S.MINIMAX_VLM_PATH
    assert payload["prompt"] == "is it?"
    assert payload["image_url"].startswith("data:image/jpeg;base64,")


@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (200, {"base_resp": {"status_code": 0}}, S.CodingPlanResponseError),
        (200, {"content": ""}, S.CodingPlanResponseError),
        (200, {"content": None}, S.CodingPlanResponseError),
        (200, {"content": ["x"]}, S.CodingPlanShapeError),
        (201, {"content": "x"}, S.CodingPlanResponseError),
        (200, {"content": "x", "base_resp": {"status_code": 2056}}, S.CodingPlanQuotaError),
        (429, {"error": "rate limited"}, S.CodingPlanHTTPError),
        (401, {"error": "no"}, S.CodingPlanAuthError),
    ],
)
def test_every_vlm_failure_raises_strictly_and_reads_as_a_reject_through_the_wrapper(
    status: int, body: Any, error: type[Exception]
) -> None:
    client = _client(_answer(status, body))
    with pytest.raises(error):
        S.minimax_vlm_strict(client, b"img", "p")
    assert S.minimax_vlm(client, b"img", "p") == ""


def test_a_vlm_body_that_is_not_json_is_a_reject_through_the_wrapper() -> None:
    client = _client(_answer(200, None, raw=b"not json"))
    with pytest.raises(S.CodingPlanResponseError):
        S.minimax_vlm_strict(client, b"img", "p")
    assert S.minimax_vlm(client, b"img", "p") == ""


# ── the weekly reset, now shared with the phase-3 search stage ─────────────────────────────────────


def test_the_weekly_reset_is_monday_midnight_utc() -> None:
    assert S.hours_until_weekly_reset(datetime(2026, 8, 7, 0, 0, tzinfo=UTC)) == 72.0
    assert S.hours_until_weekly_reset(datetime(2026, 8, 10, 0, 0, tzinfo=UTC)) == 168.0
    assert 167 < S.hours_until_weekly_reset(datetime(2026, 8, 3, 0, 1, tzinfo=UTC)) < 168


def test_theo_reads_the_same_function_rather_than_a_copy_of_it() -> None:
    from api.services import theo_worker

    assert theo_worker._hours_until_weekly_reset is S.hours_until_weekly_reset
