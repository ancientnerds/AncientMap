"""Tests for claim-pack integrity in paper handler."""

from unittest.mock import MagicMock

import pytest

from pipeline.lyra.handlers.paper import PaperHandler
from pipeline.lyra.research_state import ResearchAngle
from pipeline.lyra.theo_citations import CitationRegistry


def _make_handler_with_state(angles, all_claims, registry):
    """Build a minimal PaperHandler with just enough state for _collect_claims_for_angles."""
    handler = PaperHandler.__new__(PaperHandler)  # bypass __init__
    handler.state = MagicMock()
    handler.state.angles = angles
    handler.state.registry = registry
    return handler


def test_collect_claims_drops_claims_with_empty_source_ids():
    """Findings with no source_ids and no claim_lookup match must be dropped."""
    registry = CitationRegistry()
    angle = ResearchAngle(
        id="ang1",
        topic="x",
        description="",
        search_queries=[],
        specialist_domains=[],
    )
    angle.findings = [
        {"claim": "supported claim", "source_ids": ["sid1"]},
        {"claim": "unsupported claim", "source_ids": []},
    ]
    # The "supported claim" finding has source_ids but we haven't pre-registered sid1.
    # _collect_claims_for_angles should synthesize a [N] via assign_reference_number.
    handler = _make_handler_with_state([angle], [], registry)
    result = handler._collect_claims_for_angles(["ang1"], [])
    texts = [c["claim"] for c in result]
    assert "supported claim" in texts
    assert "unsupported claim" not in texts


def test_collect_claims_synthesizes_citations_from_source_ids():
    """When a finding has source_ids but no claim_lookup match, build [N] from registry."""
    registry = CitationRegistry()
    sid = registry.register_source("https://a.example/page", "A", "s")
    registry.assign_reference_number(sid)  # -> [1]
    angle = ResearchAngle(
        id="ang1",
        topic="x",
        description="",
        search_queries=[],
        specialist_domains=[],
    )
    angle.findings = [{"claim": "bare claim", "source_ids": [sid]}]
    handler = _make_handler_with_state([angle], [], registry)
    result = handler._collect_claims_for_angles(["ang1"], [])
    assert len(result) == 1
    assert "[1]" in result[0]["citations"]


def test_collect_claims_uses_claim_lookup_when_matched():
    """If the finding matches an enriched claim, use the enriched version."""
    registry = CitationRegistry()
    sid = registry.register_source("https://a.example/page", "A", "s")
    registry.assign_reference_number(sid)
    angle = ResearchAngle(
        id="ang1",
        topic="x",
        description="",
        search_queries=[],
        specialist_domains=[],
    )
    angle.findings = [{"claim": "Matched claim", "source_ids": [sid]}]
    enriched = {"claim": "Matched claim", "citations": "[1]", "confidence": "high"}
    handler = _make_handler_with_state([angle], [enriched], registry)
    result = handler._collect_claims_for_angles(["ang1"], [enriched])
    assert len(result) == 1
    assert result[0]["confidence"] == "high"
    assert "[1]" in result[0]["citations"]


def test_format_claims_skips_empty_citations():
    """A claim with empty citations must not appear in the formatted prompt."""
    claims = [
        {"claim": "cited claim", "citations": "[1]", "confidence": "high"},
        {"claim": "uncited claim", "citations": "", "confidence": "medium"},
    ]
    formatted = PaperHandler._format_claims_for_prompt(claims)
    assert "cited claim" in formatted
    assert "uncited claim" not in formatted


def test_format_claims_skips_whitespace_only_citations():
    """A claim with whitespace-only citations is also skipped."""
    claims = [
        {"claim": "real claim", "citations": "[2]", "confidence": "high"},
        {"claim": "bogus claim", "citations": "   ", "confidence": "medium"},
    ]
    formatted = PaperHandler._format_claims_for_prompt(claims)
    assert "real claim" in formatted
    assert "bogus claim" not in formatted
