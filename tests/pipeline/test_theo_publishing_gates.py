"""Publish gates: slug, shape, snapshot, artifact, quality, evidence, images, status, page."""

from __future__ import annotations

import copy

import pytest

from pipeline.lyra import theo_publishing as tp
from pipeline.lyra.theo_citations import validate_paper_artifact
from tests.fake_sql import RecordingSession
from tests.pipeline.theo_publish_fixtures import (
    EVIDENCE,
    IMG,
    IMG_NAME,
    OTHER_REQ,
    QUALITY,
    REPORT,
    REQ,
    SOURCE_A,
    TITLE,
    WRITER,
    images_tree,
    make_result,
)

# --- slug -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "slug"),
    [
        ("The Baalbek Trilithon", "the-baalbek-trilithon"),
        ("  Göbekli Tepe: Pillars & Pits  ", "gbekli-tepe-pillars-pits"),
        ("Sumer -- the -- Anunnaki", "sumer-the-anunnaki"),
    ],
)
def test_make_slug_keeps_the_route_rule(title, slug):
    assert tp.make_slug(title) == slug


def test_pick_slug_appends_the_id_on_collision():
    free = RecordingSession({})
    assert tp.pick_slug(free, "The Baalbek Trilithon", REQ) == "the-baalbek-trilithon"
    sql, params = free.log[0]
    assert "slug = :slug AND id != :id" in sql
    assert params == {"slug": "the-baalbek-trilithon", "id": REQ}
    taken = RecordingSession({"SELECT 1 FROM research_requests WHERE slug": [object()]})
    assert tp.pick_slug(taken, "The Baalbek Trilithon", REQ) == "the-baalbek-trilithon-11111111"


# --- writer, shape and snapshot ------------------------------------------------------


def test_the_writer_record_is_what_the_disclosure_line_knows():
    assert tp.check_writer(WRITER) == []
    assert tp.check_writer({**WRITER, "published": "auto"}) == [
        "writer.published must be 'automatic' or 'manual'"
    ]
    assert tp.check_writer({**WRITER, "published": "manual"}) == []
    assert tp.check_writer({**WRITER, "extra": 1}) == ["writer has unknown keys: ['extra']"]


def test_a_complete_bundle_passes_shape_and_snapshot():
    result = make_result()
    assert tp.check_publish_shape(result, WRITER) == {"passed": True, "issues": []}
    assert tp.check_snapshot(result) == {"passed": True, "issues": []}


def test_shape_names_every_problem():
    result = make_result(corrections=[{"date": "2026-10-01", "text": "x"}], extra="nope")
    del result["card_description"]
    gate = tp.check_publish_shape(result, {**WRITER, "human_review": "no"})
    assert gate["passed"] is False
    assert "writer.human_review must be true or false" in gate["issues"]
    assert "result.card_description must be a str" in gate["issues"]
    assert "result has unknown keys: ['extra']" in gate["issues"]


def test_shape_rejects_first_publish_corrections_and_a_foreign_writer():
    gate = tp.check_publish_shape(
        make_result(
            corrections=[{"date": "2026-10-01", "text": "x"}], writer={**WRITER, "model": "x"}
        ),
        WRITER,
    )
    assert (
        "result.corrections must be [] at first publish (use --correct afterwards)"
        in gate["issues"]
    )
    assert "result.writer differs from the bundle's writer" in gate["issues"]


def test_shape_needs_evidence_and_the_audit_gate_summary():
    quality = copy.deepcopy(QUALITY)
    del quality["audit_gate_failures"]
    gate = tp.check_publish_shape(make_result(evidence=[], quality_score=quality), WRITER)
    assert "result.evidence is empty: every paper carries evidence entries" in gate["issues"]
    assert "result.quality_score.audit_gate_failures missing" in gate["issues"]


def test_snapshot_requires_one_text_and_one_hero():
    result = make_result(published_report=REPORT + "\nextra", published_hero_image=None)
    gate = tp.check_snapshot(result)
    assert gate["passed"] is False
    assert len(gate["issues"]) == 2


# --- artifact and quality ---------------------------------------------------------


def test_artifact_gate_returns_the_audit():
    gate, audit = tp.check_artifact(REPORT)
    assert gate == {"passed": True, "issues": []}
    assert audit["passed"] is True
    broken_gate, _ = tp.check_artifact(REPORT.replace("podium [2].", "podium [7]."))
    assert broken_gate["passed"] is False


def test_quality_needs_the_stored_verdict_and_the_recomputation():
    audit = validate_paper_artifact(REPORT)
    assert tp.check_quality(QUALITY, audit, require_stored_passed=True)["passed"] is True
    held = tp.check_quality({**QUALITY, "passed": False}, audit, require_stored_passed=True)
    assert held["passed"] is False
    assert held["issues"] == ["quality_score.passed is not true"]
    # Corrections recompute only: the stored flag predates the corrected text.
    assert (
        tp.check_quality({**QUALITY, "passed": False}, audit, require_stored_passed=False)["passed"]
        is True
    )
    no_summary = {k: v for k, v in QUALITY.items() if k != "audit_gate_failures"}
    assert (
        tp.check_quality(no_summary, audit, require_stored_passed=False)["recomputed_passed"]
        is False
    )


# --- evidence -----------------------------------------------------------------------


def test_published_evidence_resolves():
    gate = tp.check_evidence(REPORT, TITLE, copy.deepcopy(EVIDENCE))
    assert gate == {"passed": True, "issues": [], "resolved": {"ev-01": 1, "ev-02": 4}}


def test_only_supported_well_formed_evidence_is_published():
    bad = copy.deepcopy(EVIDENCE)
    bad[0]["verdict"] = "partly"
    bad[1]["quote_source_id"] = SOURCE_A
    bad.append({**EVIDENCE[0], "id": "ev-1"})
    bad.append({**EVIDENCE[1]})
    bad.append(
        {
            **EVIDENCE[0],
            "id": "ev-05",
            "source_ids": [SOURCE_A + "\n"],
            "quote_source_id": SOURCE_A + "\n",
        }
    )
    gate = tp.check_evidence(REPORT, TITLE, bad)
    assert gate["passed"] is False
    assert gate["resolved"] == {}
    assert "ev-01: verdict is 'partly'; only 'supported' may be published" in gate["issues"]
    assert "ev-02: quote_source_id is not one of source_ids" in gate["issues"]
    assert "ev-1: id must look like ev-NN" in gate["issues"]
    assert "ev-02: duplicate id" in gate["issues"]
    assert "ev-05: source_ids must be a non-empty list of 12-hex source ids" in gate["issues"]


def test_evidence_with_missing_keys_is_reported_not_crashed():
    gate = tp.check_evidence(REPORT, TITLE, [{"id": "ev-01"}, "not an object"])
    assert gate["passed"] is False
    assert gate["issues"][0].startswith("ev-01: missing [")
    assert gate["issues"][1] == "evidence[1]: must be an object"


def test_the_shape_issues_are_what_check_evidence_reports_first():
    # Stream C's local check takes check_evidence's issues unchanged and runs its
    # dossier-bound checks only when every issue check_evidence reports starts
    # with `paper page: ` (shape and markdown anchors clean, C9).
    assert tp.evidence_shape_issues(copy.deepcopy(EVIDENCE)) == []
    noted = [{**EVIDENCE[0], "note": "x"}]
    assert tp.evidence_shape_issues(noted) == ["ev-01: unknown keys ['note']"]
    assert tp.check_evidence(REPORT, TITLE, noted)["issues"] == tp.evidence_shape_issues(noted)
    # A shape-clean entry whose anchor fails reports only the anchor issue.
    unanchored = [{**EVIDENCE[0], "anchor_text": "No paragraph opens with these words"}]
    assert tp.evidence_shape_issues(unanchored) == []
    assert tp.check_evidence(REPORT, TITLE, unanchored)["issues"] == [
        "ev-01: anchor_text matches 0 paragraphs (needs exactly 1)"
    ]


# A References line is no prose paragraph for report_paragraphs, but the page
# serves it as a <p>: a prose paragraph that opens with a reference's title
# resolves once in the markdown and twice on the page, where the page would
# raise (an HTTP 500 on the live paper). The gate must see what the page sees.
PAGE_ONLY_CLASH = REPORT.replace(
    "## The Quarry Blocks\n",
    "## The Quarry Blocks\n\nBaalbek quarry survey results were published in 2014 by the institute [1].\n",
)


def test_an_anchor_must_also_resolve_on_the_served_page():
    evidence = [
        *copy.deepcopy(EVIDENCE),
        {**EVIDENCE[0], "id": "ev-03", "anchor_text": "Baalbek quarry survey"},
    ]
    resolved, issues = tp.check_evidence_anchors(PAGE_ONLY_CLASH, TITLE, evidence)
    assert resolved == {"ev-01": 2, "ev-02": 5, "ev-03": 1}
    assert len(issues) == 1
    assert issues[0].startswith("paper page: ")
    assert "ev-03" in issues[0]
    gate = tp.check_evidence(PAGE_ONLY_CLASH, TITLE, evidence)
    assert gate["passed"] is False
    assert gate["issues"] == issues


def test_markdown_indices_are_what_the_evidence_gate_reports():
    assert tp.check_evidence_anchors(REPORT, TITLE, copy.deepcopy(EVIDENCE)) == (
        {"ev-01": 1, "ev-02": 4},
        [],
    )


# --- images -------------------------------------------------------------------------


def test_images_must_exist_in_this_papers_folder(tmp_path):
    folder = tmp_path / REQ
    folder.mkdir()
    (folder / IMG_NAME).write_bytes(b"jpeg")
    result = make_result()
    gate = tp.check_images(
        REQ, REPORT, result["probative_images"], result["hero_image"], images_root=tmp_path
    )
    assert gate == {"passed": True, "issues": [], "checked": 1, "missing": [], "foreign": []}


def test_missing_foreign_and_unsafe_images_fail(tmp_path):
    foreign = f"/data/research-images/{OTHER_REQ}/p2.jpg"
    hero = {"src": f"/data/research-images/{REQ}/../etc.jpg"}
    gate = tp.check_images(
        REQ, REPORT, [{"web_path": foreign}, {"title": "no path"}], hero, images_root=tmp_path
    )
    assert gate["passed"] is False
    assert gate["missing"] == [IMG]
    assert gate["foreign"] == [foreign]
    assert "probative_images[1] has no web_path" in gate["issues"]
    assert f"not a research-images path: /data/research-images/{REQ}/../etc.jpg" in gate["issues"]
    trailing = tp.check_images(REQ, "", [{"web_path": IMG + "\n"}], None, images_root=tmp_path)
    assert trailing["issues"] == [f"not a research-images path: {IMG}\n"]


# --- pictures (report class G, rule 6) ----------------------------------------------


def test_a_verified_no_marker_never_ships(tmp_path):
    """Rule 6 in the report's own words: `verified:no` must mean "nobody has looked".

    52 of the 511 image references in the 31-paper corpus carried it, and every one of
    those papers passed every gate that existed.
    """
    report = REPORT.replace(f"![Quarry block with a person for scale]({IMG})", f"![gallery:aa11bb22|verified:no|Quarry block with a person for scale]({IMG})")
    images_root, served = images_tree(tmp_path, IMG_NAME)
    gate = tp.check_pictures(
        REQ, report, make_result()["probative_images"], served_root=served
    )
    assert gate["passed"] is False
    assert gate["rules"] == ["unverified"]
    assert "verified:no" in gate["issues"][0]
    assert images_root.is_dir()


def test_a_picture_the_site_cannot_serve_fails(tmp_path):
    """7 of the 511 references in the corpus answered 404, all in one paper.

    The file check (`check_images`) asks whether the picture is in the paper's
    folder; this asks whether the site can answer the URL the paper prints, which
    is a different question and the one a reader hits.
    """
    images_root, served = images_tree(tmp_path)
    report = REPORT.replace(IMG, f"/data/research-images/{REQ}/p9_never_uploaded.jpg")
    gate = tp.check_pictures(
        REQ, report, make_result()["probative_images"], served_root=served
    )
    assert gate["passed"] is False
    assert gate["rules"] == ["not_served"]
    assert "p9_never_uploaded.jpg" in gate["issues"][0]


def test_a_credited_licensed_picture_in_the_right_folder_passes(tmp_path):
    images_root, served = images_tree(tmp_path, IMG_NAME)
    gate = tp.check_pictures(
        REQ, REPORT, make_result()["probative_images"], served_root=served
    )
    assert gate == {"passed": True, "issues": [], "figures": 1, "rules": []}


# --- status -------------------------------------------------------------------------


def test_status_gate_for_publish():
    assert tp.check_publish_status("researched", False, dry_run=False)["passed"] is True
    assert tp.check_publish_status("completed", False, dry_run=False)["passed"] is True
    assert tp.check_publish_status("running", False, dry_run=True)["passed"] is False
    public_dry = tp.check_publish_status("completed", True, dry_run=True)
    assert public_dry["passed"] is True
    assert public_dry["apply_allowed"] is False
    assert tp.check_publish_status("completed", True, dry_run=False)["passed"] is False


# --- page -----------------------------------------------------------------------------


def test_the_page_gate_runs_the_pages_own_validators():
    stored = {**make_result(), "writer": WRITER}
    assert tp.check_page(REQ, stored) == {"passed": True, "issues": []}
    gate = tp.check_page(REQ, {**stored, "writer": {**WRITER, "published": "semi"}})
    assert gate["passed"] is False
    assert len(gate["issues"]) == 1
    assert "writer.published" in gate["issues"][0]
    # A legacy M3 paper has none of the extras and renders as before.
    assert tp.check_page(REQ, {"title": "Old", "report": REPORT})["passed"] is True
