"""The session-side paper chain: seed, marker sync, evidence and claim answers.

Pinned here because the 24 owner topics are written this way now: research and text
come from the session, and these four scripts turn that into a workspace the ten
studio gates accept. The tests that matter most are the ones that end in the real
importer - `claims.import_claims` refuses any answer whose quote is not verbatim
in the source it names, so a passing `test_the_answers_are_accepted` means the
answer file the chain writes is one the studio will take.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from pipeline.lyra import claim_support
from pipeline.lyra.claim_support import locate_support
from pipeline.studio.errors import StudioError
from pipeline.studio.paper import claims as studio_claims
from pipeline.studio.paper import numbering
from pipeline.studio.paper.workspace import load_dossier
from tests.pipeline.studio import fixtures as fx

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _numbered(root: Path, *, draft: str | None = None):
    ws = fx.make_workspace(root, draft=draft)
    numbering.number(ws)
    return ws


def test_the_marker_gate_is_clean_on_a_workspace_that_passes(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    ws = _numbered(tmp_path)
    markersync = _load("paper24_markersync")
    result = markersync.report(ws)
    assert result["issues"] == 0, [line["detail"] for line in result["lines"]]


def test_markersync_names_the_marker_and_the_missing_values(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    # 4,321 years is in no source: the detail has to name the marker and the value.
    draft = fx.build_draft().replace(
        f"[S:{fx.S1}]", f"[S:{fx.S1}] The quarry froze 4,321 years ago", 1
    )
    ws = _numbered(tmp_path, draft=draft)
    markersync = _load("paper24_markersync")
    result = markersync.report(ws)
    assert result["issues"] >= 1
    line = result["lines"][0]
    assert line["source_id"] == fx.S1
    assert "321" in str(line["detail"])


def test_claimsync_returns_the_window_that_carries_the_claim(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    ws = _numbered(tmp_path)
    dossier = load_dossier(ws)
    claimsync = _load("paper24_claimsync")
    claim = dossier.data["moderated"]["final_claims"][0]
    assert locate_support(claim["claim"], dossier.texts[claim["source_ids"][0]]) is not None
    suggestions = claimsync.suggestions(
        claim["claim"], dossier.texts[claim["source_ids"][0]], limit=1, words=200
    )
    assert suggestions and suggestions[0][0] >= 2
    assert claim["claim"][:40] in suggestions[0][1] or suggestions[0][0] >= 2


def test_evidence_entries_quote_their_source_verbatim(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    ws = _numbered(tmp_path)
    evidence = _load("paper24_evidence")
    out, unlocated = evidence.entries(ws)
    assert out, "no paragraph produced a located quote"
    dossier = load_dossier(ws)
    assert [entry["id"] for entry in out] == [f"ev-{index:02d}" for index in range(1, len(out) + 1)]
    for entry in out:
        assert entry["verdict"] == "supported"
        assert entry["quote"] in dossier.texts[entry["quote_source_id"]]
        assert entry["claim"]
        assert entry["anchor_text"] in " ".join(ws.paper.read_text(encoding="utf-8").split())
    anchors = [entry["anchor_text"] for entry in out]
    assert len(anchors) == len(set(anchors))
    assert unlocated == []


def test_evidence_refuses_a_draft_with_an_unlocated_marker(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    draft = fx.build_draft().replace(
        f"[S:{fx.S1}]", f"[S:{fx.S1}] The quarry froze 4,321 years ago", 1
    )
    ws = _numbered(tmp_path, draft=draft)
    evidence = _load("paper24_evidence")
    out, unlocated = evidence.entries(ws)
    assert out == [] and unlocated, "a wrong marker must be reported, not written"
    assert evidence.main([fx.REQ]) == 1


def _coherence_note(tmp_path) -> list[str]:
    """The argv a real run passes: the coherence answer is this paper's own."""
    note = tmp_path / "coherence.txt"
    note.write_text("no two measurements in this paper contradict each other", encoding="utf-8")
    return ["--coherence-note-file", str(note)]


def test_the_claim_answers_are_accepted_by_the_studio(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    ws = _numbered(tmp_path)
    ws.evidence.write_text(
        json.dumps(fx.EVIDENCE, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    studio_claims.export_claims(ws)
    verdicts = _load("paper24_verdicts")
    assert verdicts.main([fx.REQ, *_coherence_note(tmp_path)]) == 0
    # The importer is the authority: it refuses a quote that is not verbatim.
    assert studio_claims.import_claims(ws) == {
        "accepted": len(
            [
                line
                for line in (ws.claims_dir / "tasks.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        )
    }


def test_the_run_refuses_to_answer_coherence_without_the_papers_own_words(
    monkeypatch, tmp_path, capsys
):
    """The coherence verdict is a judgement about this paper, so no default exists.

    The answer used to sit in the script in the first paper's own words, which
    would have stamped that paper's reasoning onto every paper after it.
    """
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    ws = _numbered(tmp_path)
    studio_claims.export_claims(ws)
    verdicts = _load("paper24_verdicts")
    assert verdicts.main([fx.REQ]) == 2
    assert "coherence-note-file" in capsys.readouterr().err
    assert not (ws.claims_dir / "verdicts.jsonl").exists()


def test_a_fabricated_quote_is_refused(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    ws = _numbered(tmp_path)
    studio_claims.export_claims(ws)
    tasks = [
        json.loads(line)
        for line in (ws.claims_dir / "tasks.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    verdicts = _load("paper24_verdicts")
    verdicts.main([fx.REQ, *_coherence_note(tmp_path)])
    rows = [
        json.loads(line)
        for line in (ws.claims_dir / "verdicts.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for row in rows:
        if row["quote"]:
            row["quote"] = "a sentence no source ever wrote"
            break
    (ws.claims_dir / "verdicts.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8"
    )
    assert tasks
    with pytest.raises(StudioError, match="quote does not occur verbatim"):
        studio_claims.import_claims(ws)


def test_claim_numbers_carry_the_source_unit_spelling():
    """The chain's first measured finding: the unit has to be spelled as the source does."""
    assert claim_support.claim_numbers("20 y") == claim_support.claim_numbers("20 y")
    assert "20 years" not in claim_support.claim_numbers("the source wrote 20 y")
    assert claim_support.claim_numbers("12,870 ± 30 B.P.") == claim_support.claim_numbers(
        "12,870 +/- 30 B.P."
    )
