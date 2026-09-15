# SPDX-License-Identifier: AGPL-3.0-only
"""Every library parent ref carries the canonical page path of the citing item.

DB-less: _register() only fills the in-memory `pending` rows. The frontend
(LibraryDetailCard) links exactly this path; until 2026-09-15 it built
/site.html?id= and /research.html?id= from the bare id — redirecting legacy
URLs on a page Google renders (render audit 2026-09-15).
"""

from pipeline.library_aggregator import LibraryAggregator


def _register(agg: LibraryAggregator, **overrides) -> None:
    kwargs = {
        "url": "https://example.org/paper",
        "title": "A source",
        "snippet": "",
        "source_type": "site",
        "period_name": None,
        "parent_type": "site",
        "parent_id": "5281654c-0000-4000-8000-000000000000",
        "parent_title": "Borremose",
        "parent_path": "/sites/denmark/borremose-5281654c",
    }
    kwargs.update(overrides)
    agg._register(**kwargs)


def test_parent_ref_carries_the_canonical_path():
    agg = LibraryAggregator()
    _register(agg)
    (row,) = agg.pending.values()
    assert row["parent_refs"] == [
        {
            "type": "site",
            "id": "5281654c-0000-4000-8000-000000000000",
            "title": "Borremose",
            "path": "/sites/denmark/borremose-5281654c",
        }
    ]


def test_withdrawn_story_has_no_path_but_stays_a_ref():
    agg = LibraryAggregator()
    _register(
        agg,
        source_type="story",
        parent_type="story",
        parent_id="4711",
        parent_title="Rejected story",
        parent_path=None,
    )
    (row,) = agg.pending.values()
    assert row["parent_refs"][0]["path"] is None
    assert row["parent_refs"][0]["title"] == "Rejected story"


def test_merge_keeps_one_ref_per_parent_and_its_path():
    agg = LibraryAggregator()
    _register(agg)
    _register(agg, snippet="longer snippet text")  # same URL, same parent → merged
    _register(
        agg,
        source_type="research",
        parent_type="research",
        parent_id="42",
        parent_title="A paper",
        parent_path="/research/a-paper",
    )
    (row,) = agg.pending.values()
    assert row["citation_count"] == 3
    assert [(r["type"], r["path"]) for r in row["parent_refs"]] == [
        ("site", "/sites/denmark/borremose-5281654c"),
        ("research", "/research/a-paper"),
    ]
