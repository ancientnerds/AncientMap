"""429 flavor split: plan RATE throttle (2062) vs plan BUDGET exhaustion (2056).

Born from the 2026-07-29 quantum-consciousness run death: a single 429 (2062)
"Token Plan rate limit reached" killed a 15h run at FactCheckComplete while
the watchdog probe showed 5h=71% / weekly=27% remaining. 2062 is MiniMax's
short-window rate cap — the SDK's sub-second retries land in the same minute
window, and `is_quota_error` classified it as budget exhaustion (typed raise,
no retry). Run stats: 619 requests, 2 rate-limited — one spike, 15h lost.

Expected behavior after the fix:
- (2062) rate throttle  -> backoff long enough to clear the minute window,
  retry; only when it persists through all backoffs raise QuotaExhaustedError
  (defer — persisting throttle means a genuine trough, the 06-29 case).
- (2056) budget         -> unchanged: freeze + immediate typed raise.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from pipeline.lyra import config as cfg
from pipeline.lyra import minimax_shared as ms
from pipeline.lyra.minimax_limiter import (
    QuotaExhaustedError,
    is_plan_rate_throttle,
    is_quota_error,
)

RATE_429 = (
    "Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', "
    "'message': 'Token Plan rate limit reached: Upgrade your Token Plan or "
    "switch to pay-as-you-go API usage. (2062)'}}"
)
USAGE_429 = (
    "Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', "
    "'message': 'Token Plan usage limit reached: Upgrade your Token Plan or "
    "purchase Credits for more usage. (2056)'}}"
)


# --- classification ---------------------------------------------------------


def test_2062_is_throttle_not_quota():
    assert is_plan_rate_throttle(RATE_429) is True
    assert is_quota_error(RATE_429) is False


def test_2056_is_quota_not_throttle():
    assert is_quota_error(USAGE_429) is True
    assert is_plan_rate_throttle(USAGE_429) is False


def test_wrapped_quota_text_still_recognized():
    # The event bus recognizes our own wrapped QuotaExhaustedError copies via
    # the "quota exhausted" marker — must survive the marker split.
    wrapped = "Minimax API error: MiniMax quota exhausted — calls frozen for 300s"
    assert is_quota_error(wrapped) is True
    assert is_plan_rate_throttle(wrapped) is False


# --- shared fakes ------------------------------------------------------------


class _FakeSlot:
    def __init__(self, log: list[str]):
        self._log = log

    def report_success(self) -> None:
        self._log.append("success")

    def report_rate_limit(self) -> None:
        self._log.append("rate_limit")

    def report_quota_exhausted(self) -> None:
        self._log.append("quota_exhausted")


class _FakeLimiter:
    def __init__(self):
        self.calls: list[str] = []

    @contextmanager
    def request(self):
        yield _FakeSlot(self.calls)


class _FlakyClient:
    """Raises `exc_msg` for the first `failures` create() calls, then succeeds."""

    def __init__(self, failures: int, exc_msg: str, text: str = "recovered"):
        self.attempts = 0
        self._failures = failures
        self._exc_msg = exc_msg
        self._text = text
        self.messages = self

    def create(self, **_kwargs):
        self.attempts += 1
        if self.attempts <= self._failures:
            raise RuntimeError(self._exc_msg)
        return SimpleNamespace(
            content=[SimpleNamespace(text=self._text, type="text", citations=None)],
            stop_reason="end_turn",
            model="m3",
            usage=None,
        )


@pytest.fixture
def sleeps(monkeypatch):
    recorded: list[float] = []
    monkeypatch.setattr(time, "sleep", recorded.append)
    return recorded


@pytest.fixture
def fake_limiter(monkeypatch):
    limiter = _FakeLimiter()
    monkeypatch.setattr("pipeline.lyra.minimax_limiter.limiter", limiter)
    return limiter


_SETTINGS = SimpleNamespace(minimax_top_p=None, minimax_service_tier=None)


def _m3_call(monkeypatch, client):
    monkeypatch.setattr(cfg, "_get_minimax_anthropic_client", lambda _s: client)
    return ms.minimax_chat_anthropic(
        "system",
        "user",
        500,
        _SETTINGS,
        temperature=0.2,
        thinking={"type": "disabled"},
    )


# --- minimax_chat_anthropic (the path that killed 80c629b4) ------------------


def test_m3_survives_transient_rate_throttle(monkeypatch, sleeps, fake_limiter):
    client = _FlakyClient(failures=2, exc_msg=RATE_429)
    assert _m3_call(monkeypatch, client) == "recovered"
    assert client.attempts == 3
    # Backoff must clear the per-minute window — sub-minute retries just land
    # in the same bucket (the SDK already burned two sub-second retries).
    assert sleeps == [60, 120]
    assert fake_limiter.calls.count("rate_limit") == 2
    assert "quota_exhausted" not in fake_limiter.calls


def test_m3_raises_quota_after_persistent_throttle(monkeypatch, sleeps, fake_limiter):
    client = _FlakyClient(failures=99, exc_msg=RATE_429)
    with pytest.raises(QuotaExhaustedError):
        _m3_call(monkeypatch, client)
    assert client.attempts == 3
    assert sleeps == [60, 120]
    # A throttle persisting through ~3min of backoff is a genuine trough —
    # freeze the limiter (the 2026-06-29 case) before the typed raise.
    assert "quota_exhausted" in fake_limiter.calls


def test_m3_budget_exhaustion_fails_fast(monkeypatch, sleeps, fake_limiter):
    client = _FlakyClient(failures=99, exc_msg=USAGE_429)
    with pytest.raises(QuotaExhaustedError):
        _m3_call(monkeypatch, client)
    assert client.attempts == 1
    assert sleeps == []
    assert "quota_exhausted" in fake_limiter.calls


# --- _call_anthropic_api (config.py, same branch shape) ----------------------

_CFG_SETTINGS = SimpleNamespace(
    llm_backend="minimax",
    model_summarize="m",
    max_tokens=100,
    temperature_min=0.0,
    minimax_top_p=None,
    minimax_service_tier=None,
)


def _cfg_call(monkeypatch, client):
    monkeypatch.setattr(cfg, "_get_client", lambda _s: client)
    return cfg._call_anthropic_api(
        _CFG_SETTINGS,
        system="s",
        messages=[{"role": "user", "content": "u"}],
        max_tokens=50,
        thinking={"type": "disabled"},
    )


def test_call_api_path_retries_throttle_then_raises(monkeypatch, sleeps, fake_limiter):
    client = _FlakyClient(failures=99, exc_msg=RATE_429)
    with pytest.raises(QuotaExhaustedError):
        _cfg_call(monkeypatch, client)
    # _max_attempts=2 in this path: one window-clearing backoff, then raise.
    assert client.attempts == 2
    assert sleeps == [60]
    assert "quota_exhausted" in fake_limiter.calls


def test_call_api_path_survives_single_throttle(monkeypatch, sleeps, fake_limiter):
    client = _FlakyClient(failures=1, exc_msg=RATE_429)
    response = _cfg_call(monkeypatch, client)
    assert client.attempts == 2
    assert sleeps == [60]
    assert response.content and response.content[0].text == "recovered"
    assert "quota_exhausted" not in fake_limiter.calls


def test_call_api_path_budget_fails_fast(monkeypatch, sleeps, fake_limiter):
    client = _FlakyClient(failures=99, exc_msg=USAGE_429)
    with pytest.raises(QuotaExhaustedError):
        _cfg_call(monkeypatch, client)
    assert client.attempts == 1
    assert sleeps == []
