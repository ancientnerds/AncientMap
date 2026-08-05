"""Claims-per-node shaping (spec §7 Focus-Card)."""

from types import SimpleNamespace

from api.routes.public_v1 import (
    _claim_items,
    _knowledge_limiter,
    _limiter,
    knowledge_rate_limit_dependency,
    rate_limit_dependency,
)


def test_claim_items_shape():
    rows = [
        SimpleNamespace(
            text="The dating is contested",
            status="contested",
            confidence=0.6,
            external_source_count=1,
            paper_ids=["abc"],
        )
    ]
    items = _claim_items(rows)
    assert items[0]["status"] == "contested"
    assert items[0]["confidence"] == 0.6
    assert items[0]["paper_ids"] == ["abc"]


def test_knowledge_rate_limiter_uses_dedicated_namespace():
    """The knowledge read endpoints (/graph, /knowledge/activity,
    /knowledge/claims) must not share a budget with the general 10/min
    public API limiter — a distinct namespace, distinct dependency."""
    assert _knowledge_limiter.namespace != _limiter.namespace
    assert _knowledge_limiter.namespace == "public_v1_knowledge"
    assert _knowledge_limiter.max_requests == 60
    assert knowledge_rate_limit_dependency is not rate_limit_dependency
