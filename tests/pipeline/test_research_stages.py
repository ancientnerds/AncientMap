"""Tests for research_stages.py -- shared research module."""

import json

from pipeline.lyra import research_stages
from pipeline.lyra.config import LyraSettings
from pipeline.lyra.research_stages import ClusterResult, _stage_audit
from pipeline.lyra.theo_citations import CitationRegistry


class TestClusterResult:
    def test_default_error_empty(self):
        r = ClusterResult(prose="test", sources=[], video_sources=[], score=0, passed=False)
        assert r.error == ""

    def test_has_expected_fields(self):
        r = ClusterResult(
            prose="body", sources=[{"citation": 1}], video_sources=[], score=85, passed=True
        )
        assert r.prose == "body"
        assert r.score == 85
        assert r.passed is True

    def test_error_field_set(self):
        r = ClusterResult(
            prose="", sources=[], video_sources=[], score=0, passed=False, error="No sources found."
        )
        assert r.error == "No sources found."

    def test_sources_list(self):
        sources = [
            {"citation": 1, "url": "https://example.com", "label": "Example", "type": "news"},
            {"citation": 2, "url": "https://arxiv.org/123", "label": "Paper", "type": "academic"},
        ]
        r = ClusterResult(prose="text", sources=sources, video_sources=[], score=72, passed=True)
        assert len(r.sources) == 2
        assert r.sources[0]["type"] == "news"
        assert r.sources[1]["type"] == "academic"


class TestStageAuditSelfSourceGuard:
    """Follow-up-Ticket 5: the journal audit's unconditional
    `source.reliability_tier = tier_val` clobbered a self-source's
    authoritative tier 4 down to whatever tier the LLM guessed — the audit
    prompt only ever scores tiers 1-3."""

    def test_audited_self_source_keeps_tier_4(self, monkeypatch):
        registry = CitationRegistry()
        self_sid = registry.register_source(
            url="https://ancientnerds.com/theo/public/prior-paper",
            title="[self] Prior Paper",
            snippet="own prior research",
            self_source=True,
        )
        external_sid = registry.register_source(
            url="https://example.edu/paper",
            title="External Paper",
            snippet="external research",
        )
        assert registry.sources[self_sid].reliability_tier == 4  # sanity: forced at registration

        def _fake_chat(system, user_msg, max_tokens, settings=None):
            # The LLM audit scores every source it sees, including the
            # self-source one — it has no concept of tier 4.
            sid = self_sid if self_sid in user_msg else external_sid
            return json.dumps(
                {"scored_sources": [{"id": sid, "reliability_tier": 2}], "rejected_sources": []}
            )

        monkeypatch.setattr(research_stages, "minimax_chat_anthropic", _fake_chat)
        monkeypatch.setattr(research_stages, "_load_prompt", lambda name: "system prompt")

        _stage_audit("test question", registry, LyraSettings())

        assert registry.sources[self_sid].reliability_tier == 4  # untouched
        assert registry.sources[external_sid].reliability_tier == 2  # normal audit still applies
