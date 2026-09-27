from __future__ import annotations

import gzip

import pytest

from pipeline.studio.errors import StudioError
from pipeline.studio.paper import workspace
from tests.pipeline.studio import fixtures as fx


def test_parse_dossier_reads_version_one():
    d = workspace.parse_dossier(fx.dossier_gz_bytes())
    assert d.request_id == fx.REQ
    assert d.question.startswith("How were")
    assert set(d.sources) == {fx.S1, fx.S2, fx.S3, fx.S4, fx.S5, fx.S6}
    assert d.data["texts_mode"] == "cited"  # stream A's eleventh key is tolerated


def test_parse_dossier_refuses_other_versions_and_missing_keys():
    data = fx.dossier_dict()
    data["version"] = 2
    with pytest.raises(StudioError, match="this studio reads version 1"):
        workspace.parse_dossier(fx.dossier_gz_bytes(data))
    data = fx.dossier_dict()
    del data["texts"]
    with pytest.raises(StudioError, match=r"lacks \['texts'\]"):
        workspace.parse_dossier(fx.dossier_gz_bytes(data))
    with pytest.raises(StudioError, match="not gzip'd JSON"):
        workspace.parse_dossier(b"plain")
    with pytest.raises(StudioError, match="not a JSON object"):
        workspace.parse_dossier(gzip.compress(b"[1, 2]"))


def test_text_status_distinguishes_the_four_archive_states():
    d = workspace.parse_dossier(fx.dossier_gz_bytes())
    assert [d.text_status(s) for s in (fx.S1, fx.S3, fx.S4, fx.S6)] == [
        "full_text",
        "abstract_only",
        "tdm_reserved",
        "missing",
    ]
    data = fx.dossier_dict()
    del data["texts"][fx.S2]
    assert workspace.parse_dossier(fx.dossier_gz_bytes(data)).text_status(fx.S2) == "missing"


def test_cited_source_carries_the_registry_fields():
    d = workspace.parse_dossier(fx.dossier_gz_bytes())
    src = d.cited_source(fx.S1)
    assert (src.id, src.reliability_tier, src.access_timestamp[:10]) == (fx.S1, 1, "2026-09-20")
    with pytest.raises(StudioError, match="is not in the dossier"):
        d.cited_source("eeeeeeeeeee5")


def test_a_source_without_title_cannot_be_cited():
    data = fx.dossier_dict()
    data["sources"][0]["title"] = "  "
    with pytest.raises(StudioError, match="has no title"):
        workspace.parse_dossier(fx.dossier_gz_bytes(data)).cited_source(fx.S1)


def test_load_dossier_checks_the_request_id(tmp_path):
    ws = fx.make_workspace(tmp_path)
    assert workspace.load_dossier(ws).request_id == fx.REQ
    other = workspace.PaperWorkspace(ws.root, "11111111-2222-3333-4444-555555555555")
    with pytest.raises(StudioError, match="belongs to"):
        workspace.load_dossier(other)


def test_a_rewrite_workspace_holds_the_fresh_runs_dossier(tmp_path):
    target = workspace.PaperWorkspace(tmp_path / "t", "11111111-2222-3333-4444-555555555555")
    target.root.mkdir()
    target.dossier_gz.write_bytes(fx.dossier_gz_bytes())
    assert workspace.dossier_request_id(target) == target.request_id
    with pytest.raises(StudioError, match="belongs to"):
        workspace.load_dossier(target)
    workspace.write_json(target.dossier_from, {"request_id": fx.REQ})
    assert workspace.dossier_request_id(target) == fx.REQ
    assert workspace.load_dossier(target).request_id == fx.REQ
    workspace.write_json(target.dossier_from, {"request_id": fx.REQ, "note": "x"})
    with pytest.raises(StudioError, match="dossier_from.json must be exactly"):
        workspace.dossier_request_id(target)
