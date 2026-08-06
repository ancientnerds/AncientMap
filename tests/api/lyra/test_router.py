# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for Lyra model router — RequestContext routing."""

import os

import pytest

# Ensure env vars are set before importing
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from api.services.lyra_router import (
    RequestContext,
    route_request,
)

# ---------------------------------------------------------------------------
# route_request — always routes to Anthropic cloud
# ---------------------------------------------------------------------------


class TestRouteRequest:
    """Test the full route_request() function."""

    def test_returns_anthropic_context(self):
        ctx = route_request("anthropic", "What is Pompeii?")
        assert ctx.backend_type == "anthropic"
        assert ctx.model_tier == "premium"
        assert ctx.embedding_backend == "voyage"
        assert ctx.supports_tools is True

    def test_backend_arg_ignored(self):
        # backend arg is unused — always routes to anthropic
        ctx = route_request("anything", "hello")
        assert ctx.backend_type == "anthropic"

    def test_message_arg_ignored(self):
        # message arg is unused — tier is always premium
        ctx1 = route_request("anthropic", "hi")
        ctx2 = route_request("anthropic", "What sites are on Crete?")
        assert ctx1.model_tier == ctx2.model_tier == "premium"

    def test_request_context_is_frozen(self):
        ctx = route_request("anthropic", "hello")
        with pytest.raises(AttributeError):
            ctx.model_tier = "heavy"  # type: ignore[misc]

    def test_returns_request_context_instance(self):
        ctx = route_request("anthropic", "test")
        assert isinstance(ctx, RequestContext)
