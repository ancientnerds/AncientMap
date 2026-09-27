"""Dossier export (contract C3): manifest dossiers, legacy runs, texts, list, CLI."""

from __future__ import annotations

import gzip
import io
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from pipeline.lyra import theo_dossier as td
from tests.fake_sql import FakeResult, RecordingSession

REQ = "11111111-2222-3333-4444-555555555555"
S_CORE, S_FINDING, S_FAR, S_TDM, S_NONE = (
    "aaaaaaaaaaa1",
    "aaaaaaaaaaa2",
    "aaaaaaaaaaa3",
    "aaaaaaaaaaa4",
    "aaaaaaaaaaa5",
)

MODERATED = {
    "final_claims": [{"claim": "c", "source_ids": [S_CORE, S_TDM]}],
    "revised_claims": [],
    "speculative_claims": [],
    "dropped_claims": [],
}
ANGLE = {
    "id": "ang1",
    "topic": "Quarry",
    "description": "d",
    "findings": [
        {"claim": "f1", "source_ids": [S_CORE, S_FINDING]},
        {"claim": "f2", "source_ids": [S_FAR]},
    ],
    "search_queries": ["q"],
}
STALE_ANGLE = {**ANGLE, "id": "old1", "topic": "From a deferred first attempt"}


def _source(sid: str) -> dict:
    return {
        "id": sid,
        "url": f"https://x.example/{sid}",
        "title": sid,
        "domain": "x.example",
        "reliability_tier": 1,
        "doi": "",
        "authors": [],
        "venue": "",
        "date": "2014",
        "license": "",
        "source_api": "openalex",
        "snippet_chars": 10,
        "access_timestamp": "",
        "search_query": "",
        "citation_count": 0,
        "self_source": False,
    }


REGISTRY = {
    "sources": [_source(s) for s in (S_CORE, S_FINDING, S_FAR, S_TDM, S_NONE)],
    "claims": [],
    "reference_numbers": {},
}
POOL = {"ang1": [{"url": "https://commons.example/File:A.jpg"}]}
MANIFEST = {"version": 1, "request_id": REQ, "angle_ids": ["ang1"], "counts": {"final_claims": 1}}


def _art(kind, payload, ref=""):
    return SimpleNamespace(kind=kind, ref=ref, payload=payload)


def _archive(sid, content_type="text/html", chars=100, tdm=False, text=None):
    return SimpleNamespace(
        source_id=sid,
        url=f"https://x.example/{sid}",
        content_type=content_type,
        text_chars=chars,
        fetched_at=datetime(2026, 9, 28, tzinfo=UTC),
        tdm_opt_out=tdm,
        full_text=text,
    )


REQUEST_ROW = SimpleNamespace(
    id=REQ,
    question="Who cut the Baalbek monoliths?",
    status="researched",
    is_batch=True,
    user_id="442000112756064260",
    created_at=datetime(2026, 9, 27, 20, 0),
    completed_at=datetime(2026, 9, 28, 9, 15),
    llm_calls=399,
    total_tokens=12345678,
    duration_ms=39_600_000,
)
ARCHIVE_ROWS = [
    _archive(S_CORE, text="core text"),
    _archive(S_FINDING, text="finding text"),
    _archive(S_FAR, text="far text"),
    _archive(S_TDM, chars=0, tdm=True),
]


class _ArchiveSession(RecordingSession):
    """Answers theo_source_archive reads for the requested ids only, as the database does."""

    def execute(self, stmt, params=None):
        result = super().execute(stmt, params)
        if "FROM theo_source_archive" in stmt.text:
            return FakeResult([row for row in ARCHIVE_ROWS if row.source_id in params["ids"]])
        return result


def _session(artifacts) -> RecordingSession:
    return _ArchiveSession(
        {"FROM research_requests": [REQUEST_ROW], "FROM research_artifacts": artifacts}
    )


DOSSIER_ARTIFACTS = [
    _art("dossier", MANIFEST),
    _art("moderated", MODERATED),
    _art("synthesis", {"synthesis": {}, "cross_angle_connections": []}),
    _art("debate", {"rounds": 4}),
    _art("angle_findings", ANGLE, "ang1"),
    _art("angle_findings", STALE_ANGLE, "old1"),
    _art("citation_registry", REGISTRY),
    _art("image_candidate_pool", POOL),
]


def test_export_of_a_dossier_ships_the_cited_texts_only():
    bundle = td.build_export(_session(DOSSIER_ARTIFACTS), REQ, texts="cited")
    assert bundle["version"] == 1
    assert bundle["texts_mode"] == "cited"
    assert bundle["manifest"] == MANIFEST
    assert bundle["request"]["status"] == "researched"
    assert bundle["request"]["completed_at"] == "2026-09-28T09:15:00"
    assert [angle["id"] for angle in bundle["angles"]] == ["ang1"]
    assert set(bundle["angles"][0]) == {"id", "topic", "description", "findings"}
    assert bundle["texts"] == {S_CORE: "core text", S_FINDING: "finding text"}
    sources = {source["id"]: source for source in bundle["sources"]}
    assert len(sources) == 5
    assert sources[S_TDM]["archive"]["tdm_opt_out"] is True
    assert sources[S_NONE]["archive"] is None
    assert "snippet_chars" not in sources[S_CORE]
    assert bundle["images"] == POOL


def test_all_texts_on_request():
    bundle = td.build_export(_session(DOSSIER_ARTIFACTS), REQ, texts="all")
    assert set(bundle["texts"]) == {S_CORE, S_FINDING, S_FAR}


def test_a_legacy_run_exports_with_a_computed_manifest():
    legacy = [
        _art("moderated", MODERATED),
        _art("synthesis", {"synthesis": {}, "cross_angle_connections": []}),
        _art("debate", {"rounds": 4}),
        _art("angle_findings", ANGLE, "ang1"),
        _art("citation_registry", REGISTRY),
        _art("paper_final", {"image_candidate_pool": POOL, "title": "Old paper"}),
    ]
    bundle = td.build_export(_session(legacy), REQ, texts="cited")
    manifest = bundle["manifest"]
    assert manifest["legacy"] is True
    assert manifest["angle_ids"] == ["ang1"]
    assert manifest["archive"]["cited_sources"] == 2
    assert manifest["archive"]["full_text"] == 1
    assert manifest["archive"]["tdm_reserved"] == 1
    assert manifest["research"] == {
        "llm_calls": 399,
        "total_tokens": 12345678,
        "duration_s": 39600.0,
    }
    assert bundle["images"] == POOL


def test_an_incomplete_dossier_is_refused():
    broken = [artifact for artifact in DOSSIER_ARTIFACTS if artifact.kind != "citation_registry"]
    with pytest.raises(td.DossierExportError, match="citation_registry"):
        td.build_export(_session(broken), REQ, texts="cited")


def test_an_unknown_request_is_refused():
    session = RecordingSession({})
    with pytest.raises(td.DossierExportError, match="does not exist"):
        td.build_export(session, REQ, texts="cited")


def test_list_shows_researched_rows_with_their_summary():
    row = SimpleNamespace(
        id=REQ,
        question="q",
        status="researched",
        is_batch=True,
        created_at=datetime(2026, 9, 27, 20, 0),
        completed_at=datetime(2026, 9, 28, 9, 15),
        result_json=json.dumps({"dossier": {"artifact_id": 8}, "title": None}),
    )
    session = RecordingSession({"FROM research_requests": [row]})
    assert td.list_researched(session) == [
        {
            "id": REQ,
            "question": "q",
            "status": "researched",
            "is_batch": True,
            "created_at": "2026-09-27T20:00:00",
            "completed_at": "2026-09-28T09:15:00",
            "dossier": {"artifact_id": 8},
        }
    ]
    assert "WHERE status = 'researched'" in session.statements()[0]


def test_the_cli_writes_gzip_json(monkeypatch):
    monkeypatch.setattr(td, "get_session", lambda: _session(DOSSIER_ARTIFACTS))
    buffer = io.BytesIO()
    assert td.main(["export", REQ], stdout_bytes=buffer) == 0
    bundle = json.loads(gzip.decompress(buffer.getvalue()).decode("utf-8"))
    assert bundle["request"]["id"] == REQ


def test_the_cli_rejects_a_bad_id_and_reports_a_missing_dossier(monkeypatch):
    assert td.main(["export", "nope"], stdout_bytes=io.BytesIO()) == 2
    monkeypatch.setattr(td, "get_session", lambda: RecordingSession({}))
    assert td.main(["export", REQ], stdout_bytes=io.BytesIO()) == 1


def test_the_cli_exports_any_uuid_spelling_under_the_canonical_id(monkeypatch):
    # research_artifacts.request_id is TEXT: only the canonical lowercase id finds the rows.
    session = _session(DOSSIER_ARTIFACTS)
    monkeypatch.setattr(td, "get_session", lambda: session)
    buffer = io.BytesIO()
    # REQ has no hex letters (.upper() would not change it): the hyphen-less spelling is the other form.
    assert td.main(["export", REQ.replace("-", "")], stdout_bytes=buffer) == 0
    assert json.loads(gzip.decompress(buffer.getvalue()).decode("utf-8"))["request"]["id"] == REQ
    assert {params["id"] for _sql, params in session.log if "id" in params} == {REQ}
