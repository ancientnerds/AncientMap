from __future__ import annotations

import json

import pytest

from pipeline.lyra.theo_citations import validate_paper_artifact
from pipeline.studio.errors import StudioError
from pipeline.studio.paper import numbering
from pipeline.studio.paper.workspace import parse_dossier, write_json
from tests.pipeline.studio import fixtures as fx


def _dossier():
    return parse_dossier(fx.dossier_gz_bytes())


def test_numbers_follow_first_citation_order():
    body, registry = numbering.number_draft(
        f"## A\n\nOne [S:{fx.S2}]. Two [S:{fx.S1}] [S:{fx.S2}].\n", _dossier()
    )
    assert body == "## A\n\nOne [1]. Two [2] [1].\n"
    assert registry.reference_numbers == {fx.S2: 1, fx.S1: 2}


def test_draft_problems_are_all_reported():
    draft = (
        "# Title\n\n## References\n\nText [3] [S:eeeeeeeeeee5] [S:xyz] "
        f"[S:{fx.S6}].\n\n![Stone](/data/research-images/x/stone.jpg)\n"
    )
    with pytest.raises(StudioError) as exc:
        numbering.number_draft(draft, _dossier())
    msg = str(exc.value)
    assert "'# ' title line" in msg
    assert "References/Sources heading" in msg
    assert "bare numeric markers ['[3]']" in msg
    assert "malformed source markers ['[S:xyz]']" in msg
    assert "not in the dossier: ['eeeeeeeeeee5']" in msg
    assert f"outside the brief's source list: ['{fx.S6}']" in msg
    assert "draft.md embeds images; images come only through images-import" in msg


def test_number_writes_a_paper_the_artifact_gate_accepts(tmp_path):
    ws = fx.make_workspace(tmp_path)
    built = numbering.number(ws)
    paper = ws.paper.read_text(encoding="utf-8")
    assert paper.startswith("# The Megaliths of the Baalbek Quarry\n\nIn 2014 an excavation team")
    assert (
        "\n## References\n\n[1] Baalbek quarry excavation report — https://www.dainst.org" in paper
    )
    assert "(accessed 2026-09-20) [Academic]" in paper
    audit = validate_paper_artifact(paper)
    assert audit["passed"], audit["issues"]
    rows = json.loads(ws.sources_json.read_text(encoding="utf-8"))
    assert [(r["n"], r["source_id"]) for r in rows] == [(1, fx.S1), (2, fx.S2)]
    assert built.probative_images == []


def _entry(anchor: str, file: str = "s1a2b3c4d_stone.jpg") -> dict:
    return {
        "opportunity_id": "op-01",
        "anchor_text": anchor,
        "file": file,
        "web_path": f"/data/research-images/{fx.REQ}/{file}",
        "image_path": f"/app/public/data/research-images/{fx.REQ}/{file}",
        "title": "Stone of the Pregnant Woman",
        "artist": "Jane Doe",
        "license": "CC BY-SA 4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0",
        "source_url": "https://commons.wikimedia.org/wiki/File:Baalbek_stone.jpg",
        "source_name": "wikimedia",
        "description": "The megalith in the quarry",
        "rationale": "The megalith in the quarry",
        "verified": True,
        "keyword": "stone",
        "search_query": "Baalbek stone",
        "width": 1280,
        "height": 800,
        "sha256": "0" * 64,
    }


def test_images_land_after_their_paragraph_and_keep_the_gate_green(tmp_path):
    ws = fx.make_workspace(tmp_path)
    write_json(
        ws.images_dir / "selected.json",
        [_entry("The Stone of the Pregnant Woman weighs about 1000 tons")],
    )
    built = numbering.number(ws)
    paper = built.markdown
    first_para_end = paper.index("It still lies in the Baalbek quarry [1].")
    assert paper.index("![Stone of the Pregnant Woman]") > first_para_end
    assert built.probative_images[0]["section_heading"] == "How Heavy Is Heavy"
    assert built.probative_images[0]["paragraph_index"] == 2
    assert validate_paper_artifact(paper)["passed"]


def test_an_image_anchor_that_no_longer_matches_is_refused(tmp_path):
    ws = fx.make_workspace(tmp_path)
    write_json(ws.images_dir / "selected.json", [_entry("a sentence that is not in the paper")])
    with pytest.raises(StudioError, match="matches 0 paragraphs of the current draft"):
        numbering.number(ws)


def test_a_draft_edit_after_selection_leaves_images_export_a_build(tmp_path):
    """A claim fix that rewrites an image paragraph's opening makes selected.json stale:
    the published build refuses and names the way out, the build images-export uses
    (with_images=False) still works on the edited draft."""
    ws = fx.make_workspace(tmp_path)
    anchor = "The Stone of the Pregnant Woman weighs about 1000 tons"
    write_json(
        ws.images_dir / "selected.json",
        [
            _entry(anchor),
            {
                **_entry("Jeanine Abdul Massih led the 2014 excavation", "s5e6f7a8b_dig.jpg"),
                "opportunity_id": "op-02",
            },
            {
                **_entry("a sentence that is not in the paper", "s9c0d1e2f_gone.jpg"),
                "opportunity_id": "op-03",
            },
        ],
    )
    draft = ws.draft.read_text(encoding="utf-8")
    edited = "Estimates for the Stone of the Pregnant Woman reach about 1000 tons"
    ws.draft.write_text(draft.replace(anchor, edited), encoding="utf-8")

    with pytest.raises(StudioError) as exc:
        numbering.number(ws)
    msg = str(exc.value)
    assert msg.startswith("images/selected.json no longer fits draft.md: ")
    assert "image s1a2b3c4d_stone.jpg (op-01): its anchor matches 0 paragraphs" in msg
    assert "image s9c0d1e2f_gone.jpg (op-03): its anchor matches 0 paragraphs" in msg
    assert "op-02" not in msg
    assert "run `paper images-export` (it ignores the stale selection)" in msg
    assert not ws.paper.exists()

    built = numbering.build_paper(ws, with_images=False)
    assert edited in built.markdown
    assert "![" not in built.markdown
    assert built.probative_images == []
    assert validate_paper_artifact(built.markdown)["passed"]
