# SPDX-License-Identifier: AGPL-3.0-only
"""Die Related-Stories-Rangfolge (api/services/story_related.py), DB-los.

Reihenfolge der Gründe: gleiche Site, gleicher Ort, gleiches Land, gemeinsame
Themenwörter, eine spezifische Kategorie nur zum Auffüllen bis drei.
"""

from __future__ import annotations

from datetime import datetime

from api.services.story_related import (
    RELATED_LIMIT,
    RELATED_MIN,
    StoryRow,
    related_stories,
    terms,
)


def _row(id_: int, headline: str, **kw) -> StoryRow:
    fields = {
        "tags": (),
        "site_id": "",
        "place": "",
        "country": "",
        "significance": 3,
        "created_at": datetime(2026, 10, 1),
        "news_category": "general",
    }
    fields.update(kw)
    return StoryRow(id=id_, headline=headline, **fields)


#: Filler: 300 stories that share nothing with the test stories, so the
#: document frequencies look like a real corpus (2,317 index stories, 2026-10-20).
_FILLER = [_row(10_000 + i, f"Temple number {i} restored") for i in range(300)]


def _picks(story: StoryRow, others: list[StoryRow]) -> list[tuple[int, str]]:
    return [(r.id, kind) for r, kind in related_stories(story, [story, *others, *_FILLER])]


def test_terms_drop_function_words_and_fold_plurals():
    row = _row(1, "Elongated skulls of the Chinook, speaker claims", tags=("cranial_modification",))
    assert terms(row) == frozenset({"elongated", "skull", "chinook", "cranial", "modification"})


def test_the_tiers_come_in_order_site_place_country_topic():
    story = _row(1, "Elongated skulls at Paracas", site_id="s1", place="Paracas", country="Peru")
    others = [
        _row(2, "Elongated skulls in Peru", country="Peru"),
        _row(3, "Elongated skull burials", place="Coffin Rock"),
        _row(4, "Survey at the necropolis", site_id="s1", place="Paracas", country="Peru"),
        _row(5, "Textiles from the peninsula", place="paracas "),
        _row(6, "Unrelated temple", country="Peru"),
    ]
    assert _picks(story, others) == [
        (4, "site"),
        (5, "place"),  # place names compare case- and space-insensitively
        (2, "country"),  # within a tier the stronger topic overlap first
        (6, "country"),
        (3, "topic"),
    ]


def test_one_shared_word_is_not_a_topic():
    story = _row(1, "Elongated skulls of the Pacific Northwest")
    assert _picks(story, [_row(2, "Elongated tower in Rome")]) == []


def test_the_block_holds_at_most_the_limit_and_skips_the_story_itself():
    story = _row(1, "Elongated skulls of the Pacific Northwest")
    others = [_row(i, f"Elongated skulls on the Pacific coast {i}") for i in range(2, 12)]
    picks = _picks(story, others)
    assert len(picks) == RELATED_LIMIT
    assert 1 not in [p[0] for p in picks]


def test_ties_break_by_significance_then_recency_then_id():
    story = _row(1, "Elongated skulls of the Pacific Northwest")
    others = [
        _row(2, "Elongated skulls A", significance=2, created_at=datetime(2026, 10, 9)),
        _row(3, "Elongated skulls B", significance=5, created_at=datetime(2026, 1, 1)),
        _row(4, "Elongated skulls C", significance=2, created_at=datetime(2026, 10, 9)),
        _row(5, "Elongated skulls D", significance=2, created_at=datetime(2026, 10, 10)),
    ]
    assert [p[0] for p in _picks(story, others)] == [3, 5, 4, 2]


def test_a_specific_category_fills_a_short_block_up_to_the_minimum_only():
    story = _row(1, "Bronze mirror conserved", news_category="conservation")
    others = [_row(i, f"Fresco {i} cleaned", news_category="conservation") for i in range(2, 9)]
    assert _picks(story, others) == [(8, "category"), (7, "category"), (6, "category")]
    assert len(_picks(story, others)) == RELATED_MIN


def test_general_is_too_broad_to_relate_stories():
    story = _row(1, "Bronze mirror conserved")
    assert _picks(story, [_row(2, "Fresco cleaned")]) == []


def test_the_category_does_not_pad_a_block_that_has_three_picks():
    story = _row(1, "Elongated skulls of the Pacific Northwest", news_category="bioarchaeology")
    others = [
        *[_row(i, f"Elongated skulls report {i}") for i in range(2, 5)],
        _row(9, "Fresco cleaned", news_category="bioarchaeology"),
    ]
    assert [k for _, k in _picks(story, others)] == ["topic", "topic", "topic"]
