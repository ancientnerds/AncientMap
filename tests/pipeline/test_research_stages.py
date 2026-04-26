"""Tests for research_stages.py -- shared research module."""

from pipeline.lyra.research_stages import ClusterResult


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
