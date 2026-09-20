"""Does T08 actually have teeth?

`t08_citation_markers` reports 99 findings over the 5,004 curated sites, and a check that
reports findings is only meaningful if the same code reports nothing on a clean pair and
fires on each defect it claims to find. These tests feed synthetic rows carrying one
defect each - no snapshot, no network - and assert the specific mode fires, with the
proposal shape the census requires.

The grouped/range cases are here because they prove the check goes through the pipeline's
own `normalize_grouped_markers` instead of a second regex: with a naive `\\[(\\d+)\\]`
scan, `[1,2]` is not a marker at all and a perfectly cited description would be filed as
"no markers".
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
CENSUS_PARENT = REPO / "scripts" / "remediation"
if str(CENSUS_PARENT) not in sys.path:
    sys.path.insert(0, str(CENSUS_PARENT))

from census import model as M  # noqa: E402


def _load() -> Any:
    import importlib

    return importlib.import_module("census.tests.t08_citation_markers")


@pytest.fixture(scope="module")
def t08() -> Any:
    return _load()


def _ctx(sites: list[dict]) -> SimpleNamespace:
    """The only part of Context T08 reads: `.sites`."""
    return SimpleNamespace(sites=sites)


def _site(sid: str, description: str | None = None,
          citations: list[dict] | None = None) -> dict[str, Any]:
    raw = {"description_citations": citations} if citations is not None else None
    return {
        "id": sid, "source_id": "ancient_nerds", "name": f"Site {sid}",
        "description": description, "raw_data": raw,
    }


def _entry(n: int, url: str = "https://en.wikipedia.org/wiki/X") -> dict[str, Any]:
    return {"n": n, "url": url, "title": "X", "domain": "en.wikipedia.org", "claim": "c"}


class TestT08CleanRows:
    """Real clean shapes must stay silent, or every finding is noise."""

    def test_matching_markers_and_entries_produce_nothing(self, t08):
        got = t08.run(_ctx([_site("a", "A hill [1] and a ditch [2].", [_entry(1), _entry(2)])]))
        assert got == []

    def test_grouped_markers_are_expanded_not_missed(self, t08):
        """`[1,2]` is two citations - the pipeline's own expander says so."""
        site = _site("a", "A hill [1,2].", [_entry(1), _entry(2)])
        assert t08.applies_to(site, None) is True
        assert t08.run(_ctx([site])) == []

    def test_range_markers_are_expanded_not_missed(self, t08):
        site = _site("a", "A hill [1-3].", [_entry(1), _entry(2), _entry(3)])
        assert t08._marker_sequence(site["description"]) == [1, 2, 3]
        assert t08.run(_ctx([site])) == []

    def test_thousands_numeral_is_not_a_marker(self, t08):
        """`[3,000]` is a number in prose; treating it as a citation invents a defect."""
        site = _site("a", "Occupied for [3,000] years.")
        assert t08._marker_sequence(site["description"]) == []
        assert t08.applies_to(site, None) is False
        assert t08.run(_ctx([site])) == []

    def test_site_with_neither_side_is_not_applicable(self, t08):
        site = _site("a", "A plain description with no citations.")
        assert t08.applies_to(site, None) is False
        assert t08.run(_ctx([site])) == []


class TestT08FailureModes:
    """One synthetic site per mode the plan names."""

    def test_marker_without_entry_fires(self, t08):
        site = _site("a", "A hill [1] with a ditch [2].", [_entry(1)])
        got = t08.run(_ctx([site]))
        assert [f.test_id for f in got] == ["T08/marker-without-entry"]
        f = got[0]
        assert f.site_id == "a"
        assert f.field == "description"
        assert f.current_value == [1, 2]
        assert "2" in f.note

    def test_entry_never_cited_fires(self, t08):
        site = _site("a", "A hill [1].", [_entry(1), _entry(2)])
        got = t08.run(_ctx([site]))
        assert [f.test_id for f in got] == ["T08/entry-never-cited"]
        assert got[0].field == "raw_data.description_citations"
        assert got[0].current_value == [1, 2]

    def test_array_without_any_marker_fires_once(self, t08):
        site = _site("a", "A hill with a ditch.", [_entry(1), _entry(2)])
        got = t08.run(_ctx([site]))
        assert [f.test_id for f in got] == ["T08/no-markers"], (
            "the stranded array must not also be reported entry by entry"
        )
        assert got[0].current_value == [1, 2]
        assert "stranded" in got[0].note

    def test_numbering_gap_fires(self, t08):
        site = _site("a", "A hill [1] and a ditch [3].", [_entry(1), _entry(3)])
        got = t08.run(_ctx([site]))
        assert [f.test_id for f in got] == ["T08/numbering-gap"]
        assert got[0].current_value == [1, 3]

    def test_numbering_that_starts_above_one_fires(self, t08):
        got = t08.run(_ctx([_site("a", "A hill [2].", [_entry(2)])]))
        assert [f.test_id for f in got] == ["T08/numbering-gap"]

    def test_orphan_and_unreached_together(self, t08):
        """One row can carry three modes; none of them may swallow another."""
        site = _site("a", "A hill [3].", [_entry(1), _entry(2)])
        got = sorted(t08.run(_ctx([site])), key=lambda f: f.test_id)
        assert [f.test_id for f in got] == [
            "T08/entry-never-cited", "T08/marker-without-entry", "T08/numbering-gap",
        ]


class TestT08ProposalShape:
    """The census never writes a value here - that contract is enforced, not hoped for."""

    def test_every_finding_is_review_unverifiable_and_not_applicable(self, t08):
        sites = [
            _site("a", "A hill [1] with a ditch [2].", [_entry(1)]),
            _site("b", "A hill [1].", [_entry(1), _entry(2)]),
            _site("c", "A hill with a ditch.", [_entry(1)]),
            _site("d", "A hill [1] and a ditch [3].", [_entry(1), _entry(3)]),
        ]
        got = t08.run(_ctx(sites))
        assert len(got) == 4
        for f in got:
            assert f.proposal is M.Proposal.REVIEW
            assert f.proposed_value is None, "a corrected description is a judgement call"
            assert f.confidence is M.Confidence.UNVERIFIABLE
            assert f.applicable is False, "REVIEW is never auto-applicable"

    def test_every_finding_carries_evidence_from_both_sides(self, t08):
        got = t08.run(_ctx([_site("a", "A hill [1] with a ditch [2].", [_entry(1)])]))
        assert got, "sanity: the defect must fire"
        sources = {e.source for e in got[0].evidence}
        assert t08.SRC_TEXT in sources
        assert t08.SRC_ARRAY in sources
        assert all(e.quote for e in got[0].evidence), "a quote is what makes it reviewable"

    def test_findings_are_attributed_to_the_right_site(self, t08):
        sites = [
            _site("clean", "A hill [1].", [_entry(1)]),
            _site("broken", "A hill [1] and a ditch [2].", [_entry(1)]),
        ]
        got = t08.run(_ctx(sites))
        assert {f.site_id for f in got} == {"broken"}


class TestT08RefusesToGuess:
    """A malformed array is a hole, not a clean row."""

    def test_array_that_is_not_a_list_raises(self, t08):
        site = _site("a", "A hill [1].")
        site["raw_data"] = {"description_citations": {"n": 1}}
        with pytest.raises(ValueError, match="not a list"):
            t08.run(_ctx([site]))

    def test_entry_without_an_integer_n_raises(self, t08):
        site = _site("a", "A hill [1].", [{"url": "https://x.org"}])
        with pytest.raises(ValueError, match="integer n"):
            t08.run(_ctx([site]))

    def test_raw_data_of_another_shape_is_treated_as_absent(self, t08):
        """2,787 curated rows have `raw_data` NULL - that is a state, not an error."""
        site = _site("a", "A hill [1].")
        site["raw_data"] = None
        got = t08.run(_ctx([site]))
        assert [f.test_id for f in got] == ["T08/marker-without-entry"]

    def test_no_network_and_no_snapshot_access(self, t08):
        """The check is pure over the row: a Context with only `.sites` must be enough."""
        assert not hasattr(t08, "collect"), "T08 is offline; a collector would be dead code"
        assert t08.run(_ctx([_site("a", "A hill [1].", [_entry(1)])])) == []
