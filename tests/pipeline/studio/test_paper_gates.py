from __future__ import annotations

import json

from pipeline.lyra import theo_publishing
from pipeline.lyra.quality_gate import recompute_quality_passed
from pipeline.studio.paper import gates, numbering
from pipeline.studio.paper.workspace import parse_dossier, write_json
from tests.pipeline.studio import fixtures as fx


def _report(draft: str, title: str = fx.META["title"]) -> str:
    body, registry = numbering.number_draft(draft, parse_dossier(fx.dossier_gz_bytes()))
    markdown, _placed = numbering.compose(title, body, registry, [])
    return markdown


def _gate(result, name):
    return next(g for g in result["gates"] if g["name"] == name)


def test_complete_workspace_passes_every_gate(tmp_path):
    ws = fx.complete_workspace(tmp_path)
    result = gates.run_check(ws)
    failing = [g["name"] for g in result["gates"] if not g["passed"]]
    assert failing == []
    assert result["passed"] is True
    score = result["quality_score"]
    assert score["badge"] == "Claim-checked"
    assert score["audit_gate_failures"]["hallucination_final"] == 0
    assert recompute_quality_passed(score, result["audit"]) is True
    assert score["meta"]["images_verified"] == 1
    assert result["hero_image"]["src"].startswith(f"/data/research-images/{fx.REQ}/s")
    stored = json.loads(ws.check_report.read_text(encoding="utf-8"))
    assert stored["paper_sha256"] == gates.sha256_text(ws.paper.read_text(encoding="utf-8"))
    assert stored["evidence_sha256"] == gates.sha256_text(ws.evidence.read_text(encoding="utf-8"))
    assert stored["meta_sha256"] == gates.sha256_text(ws.meta.read_text(encoding="utf-8"))


def test_quality_score_reads_a_legacy_export(tmp_path):
    ws = fx.complete_workspace(tmp_path, dossier=fx.legacy_dossier_dict())
    result = gates.run_check(ws)
    assert result["passed"] is True
    metrics = result["quality_score"]["metrics"]
    # 2 angles -> 4, 2 final claims -> 0, 2 debate rounds -> 2, full-text share 2/4 -> 2
    assert metrics["research_depth"] == 8


def test_without_claim_answers_the_claims_gate_fails(tmp_path):
    ws = fx.make_workspace(tmp_path)
    result = gates.run_check(ws)
    assert result["passed"] is False
    claims_gate = _gate(result, "claims")
    assert claims_gate["details"]["status"]["missing"]
    assert _gate(result, "hero")["passed"] is False
    assert result["quality_score"]["badge"] == "Unverified"


def test_structure_gate_names_every_problem():
    draft = fx.build_draft(filler=1).replace("## The Other Side\n\n", "## The Other Side\n")
    gate = gates.gate_structure(_report(draft))
    problems = gate.details["problems"]
    assert "heading '## The Other Side' is not followed by a blank line" in problems
    assert any("prose words; the house range is 5000-7500" in p for p in problems)
    swapped = fx.build_draft().replace("## The Other Side", "## Other Views")
    problems = gates.gate_structure(_report(swapped)).details["problems"]
    assert problems[0].startswith("the last three sections must be")


def test_structure_gate_counts_investigation_sections():
    draft = (
        fx.build_draft()
        .replace("## How Heavy Is Heavy\n\n", "")
        .replace("## Who Cut the Blocks\n\n", "")
    )
    problems = gates.gate_structure(_report(draft)).details["problems"]
    assert "need 2 to 4 investigation sections, got 0" in problems


def test_structure_gate_needs_one_or_two_hook_paragraphs():
    no_hook = fx.build_draft().replace(fx.HOOK + "\n\n", "", 1)
    no_hook = no_hook.replace(fx.filler_paragraph() + "\n\n", "", 1)
    problems = gates.gate_structure(_report(no_hook)).details["problems"]
    assert (
        "the paper opens with 0 hook paragraphs before the first ## heading (needs 1 to 2)"
        in problems
    )
    gate = gates.gate_structure(_report(fx.build_draft()))
    assert gate.passed, gate.details
    assert (gate.details["hook_paragraphs"], gate.details["investigations"]) == (2, 2)


def test_meta_gate():
    ok = gates.gate_meta(fx.META, "How were the Baalbek megaliths moved?")
    assert ok.passed, ok.details
    bad = gates.gate_meta(
        {
            "title": "What if: aliens?",
            "card_description": "See [1]. One is here. Two is here. Three.",
        },
        "q",
    )
    problems = bad.details["problems"]
    assert "title has 3 words (needs 4-12)" in problems
    assert "title must not contain ? : dashes or quotes" in problems
    assert "title starts with a question stem" in problems
    assert "card_description has more than three sentences" in problems
    assert "card_description must be plain text (no citations, no markdown)" in problems


def test_references_gate_catches_numbers_without_a_source():
    report = _report(fx.build_draft())
    rows = [{"n": 1, "source_id": fx.S1}]
    gate = gates.gate_references(report, rows, parse_dossier(fx.dossier_gz_bytes()))
    assert gate.details == {"unresolved_numbers": [2], "unknown_source_ids": []}


def test_specifics_gate_fails_on_a_date_the_cited_source_lacks():
    draft = fx.build_draft().replace(
        "Jeanine Abdul Massih led the 2014 excavation [S:aaaaaaaaaaa1].",
        "Jeanine Abdul Massih led the 1998 excavation [S:aaaaaaaaaaa1].",
    )
    dossier = parse_dossier(fx.dossier_gz_bytes())
    report = _report(draft)
    rows = numbering.sources_table(numbering.number_draft(draft, dossier)[1])
    gate = gates.gate_specifics(report, rows, dossier, dossier.texts)
    assert not gate.passed
    assert gate.details["unmatched_in_cited_paragraphs"] == 1
    assert gate.details["failing"][0]["unmatched"] == ["date: 1998"]


def test_specifics_of_a_tdm_reserved_source_are_found_in_its_live_text():
    draft = fx.build_draft().replace(
        "Jeanine Abdul Massih led the 2014 excavation [S:aaaaaaaaaaa1]. "
        "The block was quarried in the Roman period [S:aaaaaaaaaaa1].",
        f"Jeanine Abdul Massih led the 2014 excavation [S:{fx.S4}]. "
        f"The block was quarried in the Roman period [S:{fx.S4}].",
    )
    dossier = parse_dossier(fx.dossier_gz_bytes())
    report = _report(draft)
    rows = numbering.sources_table(numbering.number_draft(draft, dossier)[1])
    assert not gates.gate_specifics(report, rows, dossier, dossier.texts).passed
    live = {**dossier.texts, fx.S4: "Jeanine Abdul Massih led the 2014 excavation."}
    gate = gates.gate_specifics(report, rows, dossier, live)
    assert gate.passed, gate.details


def test_coherence_gate_needs_title_terms_in_the_body():
    title = "The Lost Obelisk of Baalbek"
    report = _report(fx.build_draft(), title)
    assert report.startswith(f"# {title}\n")
    gate = gates.gate_coherence(title, report, None)
    assert gate.details["undefined_title_terms"] == ["Lost Obelisk"]
    assert "numeric coherence not checked (claim check incomplete)" in gate.details["problems"]


def test_run_check_fails_a_title_term_only_the_title_line_carries(tmp_path):
    ws = fx.complete_workspace(tmp_path)
    write_json(ws.meta, dict(fx.META, title="The Lost Obelisk of Baalbek Revisited"))
    result = gates.run_check(ws)
    assert ws.paper.read_text(encoding="utf-8").startswith(
        "# The Lost Obelisk of Baalbek Revisited\n"
    )
    failing = [g["name"] for g in result["gates"] if not g["passed"]]
    assert failing == ["coherence", "quality"]
    assert _gate(result, "coherence")["details"]["undefined_title_terms"] == [
        "Lost Obelisk",
        "Baalbek Revisited",
    ]
    score = result["quality_score"]
    assert score["audit_gate_failures"]["undefined_title_terms"] == 2
    assert score["badge"] == "Unverified"
    assert recompute_quality_passed(score, result["audit"]) is False


def test_pick_hero_offers_only_wide_images_when_any_exist():
    narrow = {
        "web_path": "/data/research-images/x/a.jpg",
        "width": 400,
        "verified": True,
        "title": "Baalbek quarry stone",
        "source_url": "u",
        "source_name": "wikimedia",
    }
    wide = {
        "web_path": "/data/research-images/x/b.jpg",
        "width": 1200,
        "verified": False,
        "title": "A view",
        "source_url": "u",
        "source_name": "wikimedia",
    }
    assert gates.pick_hero("Baalbek Quarry", [narrow, wide])["src"].endswith("b.jpg")
    assert gates.pick_hero("Baalbek Quarry", [narrow])["src"].endswith("a.jpg")
    assert gates.pick_hero("Baalbek Quarry", []) is None


def test_images_gate_needs_the_file_the_licence_and_the_attribution(tmp_path):
    ws = fx.make_workspace(tmp_path)
    entry = {
        "file": "s00000000_x.jpg",
        "license": "",
        "source_url": "u",
        "artist": "",
        "source_name": " ",
        "description": "c",
        "verified": True,
    }
    gate = gates.gate_images(ws, "", [entry])
    assert gate.details["problems"] == [
        "s00000000_x.jpg: file missing from images/selected/",
        "s00000000_x.jpg: licence or source URL missing",
        "s00000000_x.jpg: attribution missing",
        "report embeds 0 images, images-import selected 1",
    ]


def test_run_check_reports_invalid_evidence_without_crashing(tmp_path):
    ws = fx.make_workspace(tmp_path)
    write_json(
        ws.evidence, [dict(fx.EVIDENCE[0], anchor_text="nowhere in the paper at all, really")]
    )
    result = gates.run_check(ws)
    assert _gate(result, "evidence")["passed"] is False
    assert _gate(result, "page_anchors")["details"] == {"problems": ["evidence.json invalid"]}
    assert _gate(result, "claims")["details"] == {"problems": ["evidence.json invalid"]}


def test_the_page_half_of_the_acceptance_is_the_page_anchors_gate(tmp_path, monkeypatch):
    ws = fx.make_workspace(tmp_path)
    calls = []

    def acceptance(report, title, entries):
        calls.append(title)
        return {"ev-01": 1, "ev-02": 2}, ["paper page: ev-02 matches 2 paragraphs"]

    monkeypatch.setattr(theo_publishing, "check_evidence_anchors", acceptance)
    result = gates.run_check(ws)
    assert calls[0] == fx.META["title"]
    assert _gate(result, "evidence")["passed"] is True
    assert _gate(result, "page_anchors")["details"] == {
        "problems": ["paper page: ev-02 matches 2 paragraphs"]
    }
