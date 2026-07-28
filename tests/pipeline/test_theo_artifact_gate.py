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
