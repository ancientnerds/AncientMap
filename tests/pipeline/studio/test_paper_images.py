from __future__ import annotations

import json

import pytest

from pipeline.studio import handoff
from pipeline.studio.errors import StudioError
from pipeline.studio.paper import images
from pipeline.studio.paper.numbering import build_paper
from pipeline.studio.paper.workspace import write_json
from tests.pipeline.studio import fixtures as fx

STONE = fx.OPS[0]
POOL_URL = "https://commons.wikimedia.org/wiki/File:Baalbek_stone.jpg"
TEMPLE = "The temple of Jupiter stands on a podium of 800 tons blocks"
STONE_BY_TEMPLE = {
    "id": "op-02",
    "anchor_text": TEMPLE,
    "subject": "The Stone of the Pregnant Woman beside the temple podium",
    "queries": ["Stone of the Pregnant Woman"],
}


def _prepared(tmp_path, ops=None):
    ws = fx.make_workspace(tmp_path)
    write_json(ws.images_dir / "opportunities.json", fx.OPS if ops is None else ops)
    return ws


def test_opportunity_problems_are_all_reported(tmp_path):
    ws = _prepared(tmp_path)
    report = build_paper(ws).markdown
    bad = [
        {
            "id": "op-1",
            "anchor_text": "nowhere in this paper at all, not even once",
            "subject": "two words",
            "queries": [],
        },
        {
            "id": "op-02",
            "anchor_text": "weighs about 1000 tons [S:aaaaaaaaaaa1]. It still lies",
            "subject": "the stone in the quarry",
            "queries": ["Baalbek"],
        },
        {
            "id": "op-03",
            "anchor_text": "In 2014 an excavation team measured a block",
            "subject": "the excavation team at work",
            "queries": ["Baalbek excavation"],
        },
    ]
    problems = images.opportunity_problems(bad, report)
    assert problems == [
        "opportunity 1 (op-1): id must be a unique op-NN",
        "opportunity 1 (op-1): subject needs at least three words",
        "opportunity 1 (op-1): queries must be 1 to 4 non-empty strings",
        "opportunity 1 (op-1): anchor_text matches 0 paragraphs (needs 1)",
        "opportunity 2 (op-02): anchor_text matches 0 paragraphs (needs 1)",
        "opportunity 3 (op-03): images cannot sit in the opening hook; anchor a section paragraph",
    ]


def test_export_gathers_pool_and_search_and_drops_duplicates_and_tiny_images(tmp_path):
    ws = _prepared(tmp_path)
    counts = images.export_images(ws, search=fx.fake_search, download=fx.fake_download)
    rows = handoff.read_jsonl(ws.images_dir / "tasks.jsonl")
    assert counts == {"tasks": 2, "pending": 2, "accepted": 0}
    assert [r["found_by"] for r in rows] == ["dossier pool", "Stone of the Pregnant Woman"]
    report = json.loads((ws.images_dir / "export_report.json").read_text(encoding="utf-8"))
    assert {k: report["op-01"][k] for k in ("subject", "queries", "section")} == {
        "subject": STONE["subject"],
        "queries": STONE["queries"],
        "section": "How Heavy Is Heavy",
    }
    assert report["op-01"]["paragraph"] == rows[0]["paragraph"]
    candidates = report["op-01"]["candidates"]
    results = [r["result"] for r in candidates]
    assert results == [
        "downloaded",
        "downloaded",
        "duplicate picture",
        "narrower than 320 px",
        "metadata gate",
    ]
    assert candidates[-1]["url"] == "https://example.org/cat"
    assert "https://example.org/cat" not in [r["candidate"]["url"] for r in rows]
    assert (ws.root / rows[0]["image_path"]).suffix == ".png"


def test_import_prefers_evidence_and_embeds_it(tmp_path):
    ws = _prepared(tmp_path)
    images.export_images(ws, search=fx.fake_search, download=fx.fake_download)
    rows = handoff.read_jsonl(ws.images_dir / "tasks.jsonl")
    handoff.write_jsonl(
        ws.images_dir / "verdicts.jsonl", fx.image_answers(rows, ["weak", "meaningful"])
    )
    result = images.import_images(ws)
    assert result["selected"] == 1
    selected = json.loads((ws.images_dir / "selected.json").read_text(encoding="utf-8"))
    entry = selected[0]
    assert entry["verified"] is True
    assert entry["source_url"] == "https://example.org/found-1"
    assert entry["file"].startswith("s") and entry["file"].endswith("_Stone_0.jpg")
    assert (ws.images_dir / "selected" / entry["file"]).exists()
    paper = ws.paper.read_text(encoding="utf-8")
    assert f"![Stone 0](/data/research-images/{fx.REQ}/{entry['file']})" in paper


def test_import_skips_images_without_attribution(tmp_path):
    ws = _prepared(tmp_path)
    images.export_images(ws, search=fx.fake_search, download=fx.fake_download)
    rows = handoff.read_jsonl(ws.images_dir / "tasks.jsonl")
    rows[1]["candidate"]["artist"] = rows[1]["candidate"]["source"] = ""
    handoff.write_jsonl(ws.images_dir / "tasks.jsonl", rows)
    handoff.write_jsonl(
        ws.images_dir / "verdicts.jsonl", fx.image_answers(rows, ["weak", "meaningful"])
    )
    images.import_images(ws)
    selected = json.loads((ws.images_dir / "selected.json").read_text(encoding="utf-8"))
    assert [e["source_url"] for e in selected] == [rows[0]["candidate"]["url"]]
    assert selected[0]["verified"] is False


def test_import_tries_every_illustration_until_one_has_a_licence(tmp_path):
    """The first-ranked weak image lacks a licence: the second weak one is taken."""
    ws = _prepared(tmp_path)
    images.export_images(ws, search=fx.fake_search, download=fx.fake_download)
    rows = handoff.read_jsonl(ws.images_dir / "tasks.jsonl")
    rows[0]["candidate"]["license"] = ""
    handoff.write_jsonl(ws.images_dir / "tasks.jsonl", rows)
    handoff.write_jsonl(ws.images_dir / "verdicts.jsonl", fx.image_answers(rows, ["weak", "weak"]))
    result = images.import_images(ws)
    assert result["selected"] == 1
    selected = json.loads((ws.images_dir / "selected.json").read_text(encoding="utf-8"))
    assert [(e["source_url"], e["verified"]) for e in selected] == [
        ("https://example.org/found-1", False)
    ]


def test_a_picture_placed_for_one_opportunity_gives_way_to_the_next_illustration(tmp_path):
    """Two opportunities share the dossier pool's top image: the second one falls back to
    its next weak candidate instead of losing every illustration."""
    ws = _prepared(tmp_path, [STONE, STONE_BY_TEMPLE])
    images.export_images(ws, search=fx.fake_search, download=fx.fake_download)
    rows = handoff.read_jsonl(ws.images_dir / "tasks.jsonl")
    assert [(r["opportunity_id"], r["candidate"]["url"]) for r in rows] == [
        ("op-01", POOL_URL),
        ("op-01", "https://example.org/found-1"),
        ("op-02", POOL_URL),
        ("op-02", "https://example.org/found-1"),
    ]
    handoff.write_jsonl(ws.images_dir / "verdicts.jsonl", fx.image_answers(rows, ["weak"] * 4))
    result = images.import_images(ws)
    selected = json.loads((ws.images_dir / "selected.json").read_text(encoding="utf-8"))
    assert result["selected"] == 2
    assert [(e["opportunity_id"], e["source_url"]) for e in selected] == [
        ("op-01", POOL_URL),
        ("op-02", "https://example.org/found-1"),
    ]


@pytest.mark.parametrize(
    ("exported", "current", "edit", "stale"),
    [
        (
            [STONE],
            [{**STONE, "anchor_text": TEMPLE, "subject": "The temple podium of Jupiter"}],
            None,
            "op-01",
        ),
        ([STONE], [STONE, STONE_BY_TEMPLE], None, "op-02"),
        ([STONE, STONE_BY_TEMPLE], [STONE], None, "op-02"),
        ([STONE], [{**STONE, "queries": ["Baalbek quarry megalith"]}], None, "op-01"),
        ([STONE], [STONE], ("It still lies in the", "It has rested in the"), "op-01"),
    ],
    ids=["re-anchored", "added", "removed", "new-queries", "paragraph-edited"],
)
def test_import_refuses_tasks_exported_for_other_opportunities_or_another_draft(
    tmp_path, exported, current, edit, stale
):
    """An answer vouches only for the task it answered: opportunities.json or draft.md
    changed since images-export, so the import refuses instead of embedding an image that
    was judged for another paragraph or subject (or reporting a never-searched op as empty)."""
    ws = _prepared(tmp_path, exported)
    images.export_images(ws, search=fx.fake_search, download=fx.fake_download)
    rows = handoff.read_jsonl(ws.images_dir / "tasks.jsonl")
    verdicts = ["weak", "meaningful"] * (len(rows) // 2)
    handoff.write_jsonl(ws.images_dir / "verdicts.jsonl", fx.image_answers(rows, verdicts))
    write_json(ws.images_dir / "opportunities.json", current)
    if edit is not None:
        draft = ws.draft.read_text(encoding="utf-8")
        assert draft.count(edit[0]) == 1
        ws.draft.write_text(draft.replace(*edit), encoding="utf-8")
    with pytest.raises(StudioError) as refused:
        images.import_images(ws)
    message = str(refused.value)
    assert f"exported for other opportunities or another draft: ['{stale}']" in message
    assert "Run `paper images-export` again" in message
    assert not (ws.images_dir / "selected.json").exists()


def test_a_refused_import_keeps_the_answers_of_unchanged_tasks(tmp_path):
    ws = _prepared(tmp_path)
    images.export_images(ws, search=fx.fake_search, download=fx.fake_download)
    rows = handoff.read_jsonl(ws.images_dir / "tasks.jsonl")
    handoff.write_jsonl(
        ws.images_dir / "verdicts.jsonl", fx.image_answers(rows, ["weak", "meaningful"])
    )
    write_json(ws.images_dir / "opportunities.json", [STONE, STONE_BY_TEMPLE])
    with pytest.raises(StudioError, match="another draft"):
        images.import_images(ws)
    counts = images.export_images(ws, search=fx.fake_search, download=fx.fake_download)
    assert counts == {"tasks": 4, "pending": 2, "accepted": 2}


def test_import_refuses_bad_boxes_and_unanswered_tasks(tmp_path):
    ws = _prepared(tmp_path)
    images.export_images(ws, search=fx.fake_search, download=fx.fake_download)
    rows = handoff.read_jsonl(ws.images_dir / "tasks.jsonl")
    answers = fx.image_answers(rows, ["meaningful", "off_topic"])
    answers[0]["subject_box"] = [0.8, 0.1, 0.5, 0.5]
    handoff.write_jsonl(ws.images_dir / "verdicts.jsonl", answers)
    with pytest.raises(handoff.HandoffError, match="subject_box must be null"):
        images.import_images(ws)
    handoff.write_jsonl(
        ws.images_dir / "verdicts.jsonl", fx.image_answers(rows[:1], ["meaningful"])
    )
    with pytest.raises(StudioError, match="1 image tasks have no accepted answer"):
        images.import_images(ws)


def test_export_ignores_a_selection_a_draft_edit_made_stale(tmp_path):
    """A draft edit that rewrites the image paragraph's opening makes selected.json stale:
    images-export still builds the paper (without that selection) for the new anchor."""
    ws = _prepared(tmp_path)
    images.export_images(ws, search=fx.fake_search, download=fx.fake_download)
    rows = handoff.read_jsonl(ws.images_dir / "tasks.jsonl")
    handoff.write_jsonl(
        ws.images_dir / "verdicts.jsonl", fx.image_answers(rows, ["weak", "meaningful"])
    )
    images.import_images(ws)
    old = "The Stone of the Pregnant Woman weighs about 1000 tons"
    new = "By most measures the Stone of the Pregnant Woman weighs about 1000 tons"
    ws.draft.write_text(ws.draft.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
    with pytest.raises(StudioError, match="no longer fits draft.md"):
        build_paper(ws)
    write_json(ws.images_dir / "opportunities.json", [{**fx.OPS[0], "anchor_text": new}])
    counts = images.export_images(ws, search=fx.fake_search, download=fx.fake_download)
    assert counts["tasks"] == 2
    rows = handoff.read_jsonl(ws.images_dir / "tasks.jsonl")
    assert all(r["paragraph"].startswith(new) for r in rows)
