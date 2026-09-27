"""The dossier's shape: cited sources, the manifest, the result_json summary."""

from datetime import UTC, datetime, timedelta

from pipeline.lyra.dossier_manifest import (
    DOSSIER_KINDS,
    build_manifest,
    cited_source_ids,
    manifest_summary,
    moderated_source_ids,
)
from pipeline.lyra.research_state import ResearchAngle, ResearchState

MODERATED = {
    "final_claims": [{"claim": "f1", "source_ids": ["s1", "s2"]}],
    "revised_claims": [{"original": "o", "revised": "r", "source_ids": ["s2", "s3"]}],
    "speculative_claims": [{"claim": "sp", "source_ids": ["s4"]}],
    "dropped_claims": [{"claim": "d", "source_ids": ["s9"]}],
}

ARCHIVE = {
    "cited_sources": 4,
    "full_text": 3,
    "abstract_only": 1,
    "missing": 0,
    "tdm_reserved": 0,
    "failures": [],
    "duration_s": 1.0,
    "timed_out": False,
}


def test_moderated_sources_in_first_seen_order_without_dropped_claims():
    assert moderated_source_ids(MODERATED) == ["s1", "s2", "s3", "s4"]


def test_cited_sources_add_findings_that_share_a_source():
    angles = [
        {"id": "a1", "findings": [{"source_ids": ["s1", "s7"]}, {"source_ids": ["s8"]}]},
        {"id": "a2", "findings": [{"source_ids": ["s4", "s5"]}]},
    ]
    assert cited_source_ids(MODERATED, angles) == ["s1", "s2", "s3", "s4", "s7", "s5"]


def _state() -> ResearchState:
    state = ResearchState(question="Who cut the Baalbek monoliths?", request_id="req-1")
    state.started_at = datetime(2026, 9, 26, 0, 0, tzinfo=UTC)
    state.registry.register_source(url="https://a.example/1", title="A", snippet="x")
    state.registry.register_source(url="https://a.example/2", title="B", snippet="y")
    state.angles = [
        ResearchAngle(
            id="a1", topic="Quarry", description="d", findings=[{"claim": "c"}, {"claim": "d"}]
        )
    ]
    state.moderated_result = MODERATED
    state.image_candidate_pool = {"a1": [{"url": "u1"}, {"url": "u2"}]}
    state.llm_call_count = 10
    state.total_tokens = 500
    return state


def test_manifest_counts_everything_the_writer_gets():
    created = datetime(2026, 9, 26, 1, 0, tzinfo=UTC)
    manifest = build_manifest(_state(), ARCHIVE, created_at=created)
    assert manifest == {
        "version": 1,
        "request_id": "req-1",
        "question": "Who cut the Baalbek monoliths?",
        "created_at": "2026-09-26T01:00:00+00:00",
        "angle_ids": ["a1"],
        "counts": {
            "angles": 1,
            "findings": 2,
            "sources": 2,
            "final_claims": 1,
            "revised_claims": 1,
            "speculative_claims": 1,
            "images": 2,
        },
        "kinds": list(DOSSIER_KINDS),
        "archive": ARCHIVE,
        "research": {"llm_calls": 10, "total_tokens": 500, "duration_s": 3600.0},
    }


def test_summary_is_what_result_json_carries():
    manifest = build_manifest(_state(), ARCHIVE, created_at=datetime.now(UTC) + timedelta(hours=1))
    summary = manifest_summary(manifest, 8812)
    assert summary["artifact_id"] == 8812
    assert summary["version"] == 1
    assert summary["counts"] == manifest["counts"]
    assert summary["archive"] == {
        "cited_sources": 4,
        "full_text": 3,
        "abstract_only": 1,
        "missing": 0,
        "tdm_reserved": 0,
    }
