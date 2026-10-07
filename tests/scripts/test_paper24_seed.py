"""`scripts/paper24_seed.py` builds a workspace from research done in this session.

Pinned here because the whole 24-paper chain now runs through it: a research file
that is accepted but unusable would fail later, in a gate, with an error that
names the paper and not the cause. So the refusals are the tests.

1. A seeded workspace is one the studio reads: the gzip parses as a version-1
   dossier, the texts are on disk and the brief is rendered - the three files
   `paper pull` writes, so every later step is unchanged.
2. Every id and text is validated before a byte is written (12 lowercase hex,
   no duplicate, a real text, claims citing only sources the file carries).
3. The manifest counts what the file carries and records the provenance
   truthfully: 0 LLM calls, 0 tokens, 0 debate rounds, the researcher named.
4. Nothing is repaired and nothing is overwritten: a bad file writes nothing, and
   an existing dossier or a published paper stops the seed.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from pipeline.studio.errors import StudioError
from pipeline.studio.paper.workspace import load_dossier, workspace

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "paper24_seed.py"
REQUEST = "6e51cdfc-2571-43d3-bdec-b8eb5831bbf6"
_TEXT = (
    "The Younger Dryas cooling began about 12,900 years ago, and the Younger Dryas "
    "impact hypothesis proposes that a comet struck the Laurentide Ice Sheet. "
    "Naniscaura crater in southern Quebec has been dated to about 12,900 years ago, "
    "and microtektites from the field are reported in sediments of that age. "
) * 3


def _load():
    spec = importlib.util.spec_from_file_location("paper24_seed", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _research(**overrides) -> dict:
    data = {
        "question": "What caused the Younger Dryas cooling?",
        "status": "researched",
        "researcher": "MiniMax-M3.1-Flash-Preview",
        "research_seconds": 12.5,
        "angles": [
            {
                "id": "chronology",
                "topic": "The chronology",
                "description": "When the cooling started and how fast it came.",
                "findings": [
                    {
                        "claim": "The Younger Dryas cooling began about 12,900 years ago.",
                        "confidence": "high",
                        "source_ids": ["abc123def456"],
                    }
                ],
            }
        ],
        "claims": [
            {
                "claim": "The Younger Dryas cooling began about 12,900 years ago.",
                "confidence": "high",
                "source_ids": ["abc123def456"],
                "notes": "",
            }
        ],
        "sources": [
            {
                "id": "abc123def456",
                "url": "https://en.wikipedia.org/wiki/Younger_Dryas",
                "title": "Younger Dryas",
                "domain": "en.wikipedia.org",
                "reliability_tier": 3,
                "doi": "",
                "authors": ["Wikipedia contributors"],
                "venue": "Wikipedia",
                "date": "2026-01-01",
                "license": "CC BY-SA 4.0",
                "source_api": "web",
                "content_type": "text/html",
                "fetched_at": "2026-10-05T14:00:00+00:00",
                "text": _TEXT,
            }
        ],
    }
    data.update(overrides)
    return data


def test_seeded_workspace_is_one_the_studio_reads(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    seed = _load()
    summary = seed.seed(workspace(REQUEST), _research())
    ws = workspace(REQUEST)
    assert ws.dossier_gz.exists() and ws.brief.exists()
    assert ws.text_path("abc123def456").read_text(encoding="utf-8") == _TEXT
    dossier = load_dossier(ws)
    assert dossier.request_id == REQUEST
    assert dossier.citable_ids == ["abc123def456"]
    assert summary["sources"] == 1 and summary["citable"] == 1
    assert "{{" not in ws.brief.read_text(encoding="utf-8")
    assert "[S:abc123def456]" in ws.brief.read_text(encoding="utf-8")


def test_manifest_counts_the_file_and_names_the_provenance(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    seed = _load()
    bundle = seed.build_dossier(_research(), REQUEST)
    manifest = bundle["manifest"]
    assert manifest["counts"] == {
        "angles": 1,
        "findings": 1,
        "sources": 1,
        "final_claims": 1,
        "revised_claims": 0,
        "speculative_claims": 0,
        "images": 0,
    }
    assert manifest["archive"]["cited_sources"] == 1
    assert manifest["archive"]["full_text"] == 1
    assert manifest["research"] == {
        "llm_calls": 0,
        "total_tokens": 0,
        "duration_s": 12.5,
        "researcher": "MiniMax-M3.1-Flash-Preview",
        "stage": "mini_max_code_session",
    }
    assert bundle["debate"]["rounds"] == 0
    assert bundle["texts_mode"] == "all"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda r: r["sources"][0].update(id="ABC"), "12 lowercase hex"),
        (lambda r: r["sources"][0].update(id="abc123"), "12 lowercase hex"),
        (lambda r: r["sources"].append(dict(r["sources"][0])), "repeats the source id"),
        (lambda r: r["sources"][0].update(text="too short"), "too short"),
        (lambda r: r["sources"][0].update(title=""), "title"),
        (lambda r: r["claims"][0].update(source_ids=["0123456789ab"]), "does not carry"),
        (lambda r: r["claims"][0].update(source_ids=[]), "non-empty list"),
        (lambda r: r["angles"][0].update(findings=[]), "carries no finding"),
        (lambda r: r.update(sources=[]), "carries no sources"),
        (lambda r: r.update(claims=[]), "carries no claim"),
        (lambda r: r.update(angles=[]), "carries no angle"),
        (lambda r: r.update(researcher=""), "researcher"),
        (lambda r: r.update(researcher="   "), "researcher"),
        (lambda r: r.pop("researcher"), "researcher"),
    ],
)
def test_a_bad_research_file_writes_nothing(monkeypatch, tmp_path, mutate, message):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    seed = _load()
    research = copy.deepcopy(_research())
    mutate(research)
    ws = workspace(REQUEST)
    with pytest.raises(StudioError, match=message):
        seed.seed(ws, research)
    assert not ws.dossier_gz.exists()
    assert not ws.brief.exists()
    assert not ws.texts_dir.exists()


def test_an_existing_dossier_needs_force(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    seed = _load()
    ws = workspace(REQUEST)
    seed.seed(ws, _research())
    with pytest.raises(StudioError, match="--force"):
        seed.seed(ws, _research())
    assert seed.seed(ws, _research(), force=True)["claims"] == 1


def test_a_published_paper_is_never_reseeded(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    seed = _load()
    ws = workspace(REQUEST)
    ws.root.mkdir(parents=True, exist_ok=True)
    ws.published_bundle.write_text("{}", encoding="utf-8")
    with pytest.raises(StudioError, match="paper correct"):
        seed.seed(ws, _research())
    assert not ws.dossier_gz.exists()


def test_main_reports_the_workspace(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    seed = _load()
    research_file = tmp_path / "research.json"
    research_file.write_text(json.dumps(_research()), encoding="utf-8")
    assert seed.main([REQUEST, str(research_file)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["request_id"] == REQUEST and out["angles"] == 1
    assert seed.main([REQUEST, str(tmp_path / "missing.json")]) == 2
