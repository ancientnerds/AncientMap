"""Artifact-level citation integrity: validate_paper_artifact + repair_artifact.

Golden fixtures mirror the real defect classes found 2026-07-28 in the
Kybalion and DMT papers (stray [N#] tokens, markers beyond the rendered
list, grouped [9, 7, 1] brackets, orphaned rendered refs, stale rendered
list vs registry).
"""

from pipeline.lyra.theo_citations import (
    _collect_non_numeric_markers,
    normalize_grouped_markers,
    split_artifact,
    validate_paper_artifact,
)


def test_split_artifact_splits_single_heading():
    md = "# T\n\nProse [1].\n\n## References\n\n[1] A — https://a.example (accessed 2026-01-01)\n"
    prose, heading, body = split_artifact(md)
    assert "Prose [1]." in prose
    assert "References" not in prose
    assert heading.startswith("## References")
    assert "[1] A — https://a.example" in body


def test_split_artifact_no_heading_returns_all_prose():
    prose, heading, body = split_artifact("just prose, no refs")
    assert prose == "just prose, no refs"
    assert heading == ""
    assert body == ""


def test_split_artifact_handles_h3_and_sources():
    for h in ("### References", "## Sources"):
        prose, heading, body = split_artifact(f"P\n\n{h}\n\n[1] A — https://a.example\n")
        assert heading.startswith(h)


def test_collect_non_numeric_markers_finds_debug_and_grouped_tokens():
    prose = (
        "Claim [N1]. Another [N2]. Grouped [9, 7, 1]. Fine [3]. "
        "A [link](https://x.example) and a footnote [^1] are ignored."
    )
    tokens = _collect_non_numeric_markers(prose)
    assert "N1" in tokens
    assert "N2" in tokens
    assert "9, 7, 1" in tokens
    assert "3" not in tokens
    assert "link" not in tokens
    assert "^1" not in tokens


def test_split_artifact_empty_string():
    assert split_artifact("") == ("", "", "")


def test_split_artifact_heading_at_eof_without_newline():
    prose, heading, body = split_artifact("P\n\n## References")
    assert prose == "P\n\n"
    assert heading == "## References"
    assert body == ""


def test_split_artifact_multiple_headings_splits_on_last():
    md = "P\n\n## References\n\nfake block\n\nmore prose\n\n## References\n\n[1] Real — https://r.example\n"
    prose, heading, body = split_artifact(md)
    assert "fake block" in prose
    assert "more prose" in prose
    assert "[1] Real" in body


def test_normalize_grouped_markers_splits_groups():
    text, n = normalize_grouped_markers("Intro claim [9, 7, 1]. Next [2,3].")
    assert text == "Intro claim [9] [7] [1]. Next [2] [3]."
    assert n == 2


def test_normalize_grouped_markers_noop_without_groups():
    text, n = normalize_grouped_markers("Plain [1] and [2].")
    assert text == "Plain [1] and [2]."
    assert n == 0


def test_normalize_grouped_markers_leaves_refs_section_alone():
    md = "Prose [1, 2].\n\n## References\n\n[1, 2] Combined ref — https://a.example\n"
    text, n = normalize_grouped_markers(md)
    assert n == 1  # only the prose group counted
    assert "[1] [2]" in text.split("## References")[0]
    assert "[1, 2] Combined ref — https://a.example" in text  # refs body untouched


CLEAN_PAPER = """# Clean Paper

## Findings

The site dates to 9600 BC based on radiocarbon samples [1]. Excavations
revealed T-shaped pillars with animal reliefs carved in relief [2].

## References

[1] Radiocarbon dating at Gobekli Tepe — https://a.example/dating (accessed 2026-07-01) [Academic]
[2] T-shaped pillars survey — https://a.example/pillars (accessed 2026-07-01)
"""

# Kybalion-class defects: [N#] writer artifacts + markers beyond the rendered
# list + a rendered ref never cited.
KYBALION_CLASS = """# Hermeticism Paper

## Findings

The Corpus Hermeticum dates to late antiquity [N1], and the famous axiom is
a nineteenth-century paraphrase [N2] first printed in 1908 [1].

The Kybalion presents seven principles attributed to Hermes Trismegistus [2].

*Kybalion first edition, 1908 [4] [5]*

Atkinson published under several pseudonyms during his career [6].

## References

[1] Corpus Hermeticum dating — https://a.example/corpus (accessed 2026-07-01) [Academic]
[2] The Kybalion 1908 — https://a.example/kybalion (accessed 2026-07-01)
[3] Hermetic tradition overview — https://a.example/tradition (accessed 2026-07-01)
"""


def test_validate_passes_clean_paper():
    report = validate_paper_artifact(CLEAN_PAPER)
    assert report["passed"] is True
    assert report["total_references"] == 2
    assert report["issues"] == []


def test_validate_flags_kybalion_class_defects():
    report = validate_paper_artifact(KYBALION_CLASS)
    assert report["passed"] is False
    assert "N1" in report["non_numeric_markers"]
    assert "N2" in report["non_numeric_markers"]
    assert report["invalid_markers"] == [4, 5, 6]
    assert report["orphaned_refs"] == [3]
    # total_references counts the RENDERED list — the 50-vs-45 bug class.
    assert report["total_references"] == 3


def test_validate_flags_grouped_markers_as_non_numeric():
    md = CLEAN_PAPER.replace("samples [1]", "samples [1, 2]")
    report = validate_paper_artifact(md)
    assert report["passed"] is False
    assert "1, 2" in report["non_numeric_markers"]


def test_validate_flags_missing_references_section():
    report = validate_paper_artifact("# T\n\nProse with [1].\n")
    assert report["passed"] is False
    assert report["references_sections"] == 0
    assert any("no References section" in i for i in report["issues"])


def test_validate_flags_duplicate_references_sections():
    md = CLEAN_PAPER + "\n## References\n\n[9] Ghost — https://g.example\n"
    report = validate_paper_artifact(md)
    assert report["passed"] is False
    assert report["references_sections"] == 2


def test_validate_flags_unparseable_ref_line():
    md = CLEAN_PAPER.replace(
        "[2] T-shaped pillars survey — https://a.example/pillars (accessed 2026-07-01)",
        "Smith, J. (1998). Pillars. Antiquity.",
    )
    report = validate_paper_artifact(md)
    assert report["passed"] is False
    assert len(report["unparseable_ref_lines"]) == 1


def test_validate_flags_duplicate_and_noncontiguous_numbers():
    md = """# T

## Findings

Alpha claim about dating with plenty of detail attached [1]. Beta claim about
architecture with plenty of detail attached [4].

## References

[1] A — https://a.example (accessed 2026-07-01)
[1] B — https://b.example (accessed 2026-07-01)
[4] D — https://d.example (accessed 2026-07-01)
"""
    report = validate_paper_artifact(md)
    assert report["passed"] is False
    assert report["duplicate_ref_nums"] == [1]
    assert report["non_contiguous"] is True


def test_validate_flags_empty_references_section():
    report = validate_paper_artifact("# T\n\n## References\n")
    assert report["passed"] is False
    assert any("no parseable entries" in i for i in report["issues"])


def test_validate_heading_requires_exact_line():
    # `## References:` is not a refs heading to the frontend renderer.
    report = validate_paper_artifact(
        "# T\n\nProse [1].\n\n## References:\n\n[1] A — https://a.example (accessed 2026-07-01)\n"
    )
    assert report["references_sections"] == 0
    assert report["passed"] is False


def test_validate_sources_of_evidence_is_not_a_refs_heading():
    md = CLEAN_PAPER.replace("## Findings", "## Sources of Evidence")
    report = validate_paper_artifact(md)
    assert report["references_sections"] == 1
    assert report["passed"] is True


def test_validate_crlf_input_still_checks_uncited_paragraphs():
    md = """# T

## Findings

Alpha claim about dating with plenty of factual detail attached here for
length testing purposes [1].

Beta claim about architecture with plenty of factual detail attached here
for length testing purposes.

## References

[1] A — https://a.example (accessed 2026-07-01)
"""
    crlf = md.replace("\n", "\r\n")
    report = validate_paper_artifact(crlf)
    assert report["uncited_paragraphs"] >= 1


from pipeline.lyra.theo_citations import (
    repair_artifact,
    replace_references_section,
    validate_or_repair,
)

# DMT-class defects: grouped marker + orphan high marker + rendered refs
# never cited (repair must drop them and renumber prose + list atomically).
DMT_CLASS = """# DMT Paper

## Findings

Strassman ran DEA-approved injections at UNM between 1990 and 1995 with
sixty volunteers enrolled [2, 1]. Later EEG work replicated the surge under
psilocybin in controlled settings [3]. A speculative claim cites nothing
real [6].

## References

[1] Strassman UNM study — https://a.example/strassman (accessed 2026-07-01) [Academic]
[2] DMT and the pineal — https://a.example/pineal (accessed 2026-07-01)
[3] EEG replication — https://a.example/eeg (accessed 2026-07-01) [Academic]
[4] Never cited A — https://a.example/na (accessed 2026-07-01)
[5] Never cited B — https://a.example/nb (accessed 2026-07-01)
"""


def test_repair_fixes_dmt_class_defects():
    repaired, report = repair_artifact(DMT_CLASS)
    assert report["passed"] is True
    # Grouped marker split, order preserved: [2, 1] -> [2] [1] -> renumbered [1] [2]
    assert "enrolled [1] [2]." in repaired
    # [3] keeps citing the EEG line, renumbered to [3] (first-use order 2,1,3)
    assert "settings [3]." in repaired
    # Orphan [6] stripped; never-cited refs [4] [5] dropped; list is 1..3
    assert "[6]" not in repaired
    assert "Never cited" not in repaired
    assert report["total_references"] == 3
    # Titles preserved verbatim on renumbered lines
    assert "[1] DMT and the pineal — https://a.example/pineal" in repaired
    assert "[2] Strassman UNM study — https://a.example/strassman" in repaired


def test_repair_strips_tokens_but_holds_kybalion_class():
    # [N1]/[N2] and [4][5][6] are stripped, ref [3] dropped — but stripping
    # [6] leaves the Atkinson paragraph uncited, so the repair must NOT
    # reach passed: the paper HOLDS for manual review instead of publishing
    # with an uncited factual claim.
    repaired, report = repair_artifact(KYBALION_CLASS)
    assert "[N1]" not in repaired
    assert "[N2]" not in repaired
    prose_part = repaired.split("## References")[0]
    assert "[4]" not in prose_part
    assert "[6]" not in prose_part
    assert report["passed"] is False
    assert report["uncited_paragraphs"] >= 1


def test_repair_is_idempotent():
    once, _ = repair_artifact(DMT_CLASS)
    twice, report = repair_artifact(once)
    assert twice == once
    assert report["passed"] is True


def test_repair_bails_on_unparseable_ref_line():
    md = DMT_CLASS.replace(
        "[4] Never cited A — https://a.example/na (accessed 2026-07-01)",
        "Some stray sentence in the references block.",
    )
    repaired, report = repair_artifact(md)
    assert report["passed"] is False
    # Original refs body untouched — no guessing against a broken list.
    assert "Some stray sentence" in repaired


def test_repair_holds_when_strip_creates_uncited_paragraph():
    md = """# T

## Findings

This entire factual paragraph about ancient metallurgy rests on one marker
that resolves to nothing at all [9].

## References

[1] Real ref — https://a.example/r (accessed 2026-07-01)
"""
    _repaired, report = repair_artifact(md)
    # [9] is stripped, [1] becomes orphaned -> dropped, paragraph now uncited.
    assert report["passed"] is False
    assert report["uncited_paragraphs"] >= 1


def test_validate_or_repair_returns_original_when_clean():
    text, report = validate_or_repair(CLEAN_PAPER)
    assert text == CLEAN_PAPER
    assert report["passed"] is True


def test_validate_or_repair_repairs_dirty_text():
    text, report = validate_or_repair(DMT_CLASS)
    assert report["passed"] is True
    assert "enrolled [1] [2]." in text


def test_replace_references_section_replaces_stale_block():
    stale = CLEAN_PAPER
    new_md = replace_references_section(
        stale, "[1] Only ref — https://o.example (accessed 2026-07-02)"
    )
    assert "Only ref" in new_md
    assert "Radiocarbon dating" not in new_md
    assert new_md.count("## References") == 1


def test_replace_references_section_appends_when_missing():
    new_md = replace_references_section("# T\n\nProse [1].\n", "[1] R — https://r.example")
    assert "## References" in new_md
    assert "[1] R — https://r.example" in new_md


def test_repair_leaves_legitimate_bracketed_prose_and_holds():
    md = CLEAN_PAPER.replace("samples [1]", 'samples "as [the king] decreed" [sic] [1]')
    repaired, report = repair_artifact(md)
    assert "[the king]" in repaired
    assert "[sic]" in repaired
    assert report["passed"] is False


def test_validate_or_repair_holds_original_on_legit_brackets():
    md = CLEAN_PAPER.replace("samples [1]", "samples [sic] [1]")
    text, report = validate_or_repair(md)
    assert text == md
    assert report["passed"] is False


def test_normalize_expands_dash_ranges():
    text, n = normalize_grouped_markers("Claim [2-4]. Another [7–8].")
    assert text == "Claim [2] [3] [4]. Another [7] [8]."
    assert n == 2


def test_normalize_leaves_thousands_numerals_alone():
    text, n = normalize_grouped_markers("Population reached [3,000] by then.")
    assert text == "Population reached [3,000] by then."
    assert n == 0


def test_normalize_leaves_oversized_ranges_alone():
    text, n = normalize_grouped_markers("See [1-45].")
    assert text == "See [1-45]."
    assert n == 0


def test_repair_expands_range_and_keeps_cited_refs():
    md = DMT_CLASS.replace("settings [3]", "settings [3-5]")
    repaired, report = repair_artifact(md)
    assert report["passed"] is True
    assert report["total_references"] == 5
    assert "Never cited A" in repaired
    assert "Never cited B" in repaired


def test_repair_bails_on_paren_adjacent_numeric_marker():
    md = DMT_CLASS.replace("real [6].", "real [6]. Compare [1](see appendix).")
    repaired, report = repair_artifact(md)
    assert report["passed"] is False
    assert "[1](see appendix)" in repaired


def test_repair_preserves_image_with_bracketed_alt():
    md = DMT_CLASS.replace(
        "## References",
        "![Temple ruins [1]](https://img.example/t.jpg)\n\n## References",
    )
    repaired, report = repair_artifact(md)
    assert "![Temple ruins [1]](https://img.example/t.jpg)" in repaired
    assert report["passed"] is False


def test_repair_preserves_list_indentation():
    md = DMT_CLASS.replace(
        "A speculative claim cites nothing\nreal [6].",
        "A speculative claim cites nothing real [6].\n\n- Top point [3]\n  - Nested point [1]",
    )
    repaired, _report = repair_artifact(md)
    assert "  - Nested point" in repaired


def test_repair_normalizes_crlf():
    crlf = DMT_CLASS.replace("\n", "\r\n")
    repaired, report = repair_artifact(crlf)
    assert "\r\n" not in repaired
    assert report["passed"] is True


def test_repair_leaves_hex_like_english_words_and_holds():
    md = CLEAN_PAPER.replace("samples [1]", "samples near the [facade] within a [decade] [1]")
    repaired, report = repair_artifact(md)
    assert "[facade]" in repaired
    assert "[decade]" in repaired
    assert report["passed"] is False


def test_repair_strips_real_hex_debug_token():
    md = CLEAN_PAPER.replace("samples [1]", "samples [5620e1fb87f7] [1]")
    repaired, report = repair_artifact(md)
    assert "5620e1fb87f7" not in repaired
    assert report["passed"] is True


def test_repair_strips_leaked_self_provenance_marker():
    # [self] is reference-map metadata (theo_sources.py PublicResearchAdapter
    # prefixes own-paper titles with it); a writer LLM copying it into prose
    # must not HOLD the paper -- it's an allowlisted strippable artifact.
    md = CLEAN_PAPER.replace("samples [1]", "samples [self] [1]")
    repaired, report = repair_artifact(md)
    assert "[self]" not in repaired
    assert report["passed"] is True


def test_validate_or_repair_repairs_leaked_self_marker():
    md = CLEAN_PAPER.replace("samples [1]", "samples [self] [1]")
    text, report = validate_or_repair(md)
    assert report["passed"] is True
    assert "[self]" not in text


def test_normalize_leaves_year_ranges_alone():
    text, n = normalize_grouped_markers("Seasons [1990-1995] produced stratigraphy.")
    assert text == "Seasons [1990-1995] produced stratigraphy."
    assert n == 0


def test_normalize_leaves_leading_zero_ranges_alone():
    text, n = normalize_grouped_markers("The dig ran through [07-08].")
    assert text == "The dig ran through [07-08]."
    assert n == 0
