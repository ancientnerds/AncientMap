"""Quota errors must propagate out of the structured-call stack (2026-07-19).

Born from the 07-08..07-12 batch standstill: 17 decomposition failures in a
row because a MiniMax 429/2056 (weekly Token Plan wall) died inside
structured_llm_call's blanket except and came back as {} — which the
decomposition handler read as "no research angles" and the worker marked
'failed' (permanent) instead of 'deferred' (retry when the window resets).

Two type-killers are covered:
1. call_api wrapped QuotaExhaustedError into LyraAPIError (type lost).
2. structured_llm_call swallowed the typed error from the fallback path.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pipeline.lyra import config as cfg
from pipeline.lyra import minimax_shared as ms
from pipeline.lyra.minimax_limiter import InsufficientQuotaError, QuotaExhaustedError

SCHEMA = {"type": "object", "properties": {"angles": {"type": "array"}}}


def _structured_call():
    # settings is only forwarded to the fallback path — a bare namespace keeps
    # the test independent of env configuration.
    return ms.structured_llm_call(
        "system", "user", SCHEMA, 1000, SimpleNamespace(), temperature=0.2
    )


def test_structured_call_reraises_quota_from_primary_path(monkeypatch):
    """A quota death in call_api must NOT degrade into {} via the fallback."""

    def quota_dead(**_kwargs):
        raise QuotaExhaustedError("MiniMax quota exhausted during LLM call: 429 (2056)")

    monkeypatch.setattr("pipeline.lyra.config.call_api", quota_dead)
    with pytest.raises(QuotaExhaustedError):
        _structured_call()


def test_structured_call_reraises_quota_from_fallback_path(monkeypatch):
    """A transient primary failure followed by a quota death in the fallback
    must surface the quota error, not return {}."""

    def transient(**_kwargs):
        raise RuntimeError("Minimax API error: 503 upstream hiccup")

    def quota_dead(*_args, **_kwargs):
        raise QuotaExhaustedError("MiniMax quota exhausted during M3 call: 429 (2056)")

    monkeypatch.setattr("pipeline.lyra.config.call_api", transient)
    monkeypatch.setattr(ms, "minimax_chat_anthropic", quota_dead)
    with pytest.raises(QuotaExhaustedError):
        _structured_call()


@pytest.mark.parametrize("exc_type", [QuotaExhaustedError, InsufficientQuotaError])
def test_call_api_does_not_wrap_quota_errors(monkeypatch, exc_type):
    """call_api wraps unknown errors into LyraAPIError — but the typed quota
    errors are the worker's routing signal for 'deferred' and must pass
    through unwrapped."""
    monkeypatch.setattr(cfg, "_get_settings", lambda: SimpleNamespace(llm_backend="minimax"))

    def quota_dead(_settings, **_kwargs):
        raise exc_type("quota dead")

    monkeypatch.setattr(cfg, "_call_anthropic_api", quota_dead)
    with pytest.raises(exc_type):
        cfg.call_api(system="s", messages=[], max_tokens=10)
