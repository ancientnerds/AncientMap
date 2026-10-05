"""`scripts/theo_paper_acceptance.py` is the executable form of the goal G1-G6.

It is the only thing that can fail the goal, so its own logic is pinned here:
the baseline numbers it must reproduce on the live corpus are the ones plan A
and plan C were corrected to on 2026-10-04. A future change to the renderer, the
caption format or the report shape moves these numbers, and this test is what
makes that visible instead of silent.

The counts themselves are measured against production from
    docker exec ancient_nerds_api python scripts/theo_paper_acceptance.py
and are not reproduced here: there is no local database, and the corpus lives on
the VPS. What is pinned is the arithmetic on a synthetic paper, which is where
a mistake in the criteria would actually hide.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "theo_paper_acceptance.py"


def _load():
    spec = importlib.util.spec_from_file_location("theo_paper_acceptance", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


acc = _load()


def _img(n: int) -> str:
    return f"![gallery:abc{n:04d}|verified:yes|Subject {n}](/data/research-images/x/p{n}_s.jpg)"


_PAPER = "\n\n".join(
    [
        "# A Title",
        "Hook paragraph.",
        _img(0),
        "## First Section",
        "A paragraph with a number 1650 tons [1].",
        _img(1),
        "## Second Section",
        "A paragraph without any picture.",
        "## Third Section",
        "A paragraph with two pictures.",
        _img(2),
        _img(3),
        "## References",
        "[1] Someone. A title. A venue. DOI: 10.1163/15700593-01502001 (accessed 2026-07-27). "
        "[Academic]",
    ]
)


def test_sections_exclude_the_title_and_the_references():
    assert acc._sections(_PAPER) == ["First Section", "Second Section", "Third Section"]


def test_reference_lines_are_read_from_the_last_references_heading():
    lines = acc._reference_lines(_PAPER)
    assert len(lines) == 1
    assert lines[0].startswith("[1] Someone")


def test_a_doi_only_reference_counts_as_resolvable():
    """83 of the 1052 corpus lines carry no URL. All of them carry a DOI, so they
    resolve: the criterion is 'URL or DOI', and calling them unverifiable was
    the error plan A carried until 2026-10-04."""
    doi_only = "[2] Wouter J. Hanegraaff (2015). How Hermetic was Renaissance Hermetism?. " "Aries. DOI: 10.1163/15700593-01502001"
    assert acc._RESOLVABLE_RE.search(doi_only)
    assert not acc._RESOLVABLE_RE.search("[3] Someone. A title. A venue.")


def test_raw_html_in_a_reference_line_is_found():
    assert acc._RAW_HTML_RE.search("[4] A title with <i>emphasis</i> in it.")
    assert not acc._RAW_HTML_RE.search("[5] A plain reference line.")


def test_the_gallery_marker_is_found_in_a_report():
    assert len(acc._GALLERY_MARKER_RE.findall(_PAPER)) == 4
    assert acc._GALLERY_MARKER_RE.findall("![Baalbek stone](/x.jpg)") == []


def test_evidence_names_the_sections_without_an_image():
    ev = acc._paper_evidence(
        {"slug": "x", "report": _PAPER, "pool": [], "corrections": []}
    )
    assert ev["sections"] == 3
    assert ev["investigations"] == 3
    # four pictures in the report, but the first sits in the hook, which the house
    # format keeps free of images and which is therefore not a section
    assert ev["images"] == 3
    assert ev["sections_without_image"] == ["Second Section"]
    assert ev["sections_below_target"] == ["First Section", "Second Section", "Third Section"]
    assert ev["references"] == 1
    assert ev["references_unresolvable"] == 0
    assert ev["references_with_raw_html"] == 0
    assert ev["gallery_marker_in_report"] == 4


def test_the_floor_is_one_and_the_target_is_four():
    assert acc._MIN_PER_SECTION == 1
    assert acc._TARGET_PER_SECTION == 4


def test_fix_classes_are_parsed_out_of_a_correction_entry():
    """The correction entries are prose only; these are the classes a second
    round would have to repeat, and they can only be counted by parsing them."""
    entry = {
        "date": "2026-10-04",
        "text": (
            "Of 72 verifiable assertions, 44 did not hold up. "
            "8 reattribute, 7 replace claim, 4 delete claim, 2 replace number, "
            "2 replace date were applied. An honest limit: 9 of the 72 assertions "
            "rest on sources that could not be read at all."
        ),
    }
    ev = acc._paper_evidence(
        {"slug": "x", "report": _PAPER, "pool": [], "corrections": [entry]}
    )
    assert ev["fix_classes"] == {
        "reattribute": 8,
        "replace claim": 7,
        "delete claim": 4,
        "replace number": 2,
        "replace date": 2,
    }
    assert ev["unreadable_source_assertions"] == 9
