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
    md = "Prose [1, 2].\n\n## References\n\n[1] A, B — https://a.example\n"
    text, n = normalize_grouped_markers(md)
    assert n == 1
    assert "[1] [2]" in text
    assert "[1] A, B — https://a.example" in text  # refs untouched
