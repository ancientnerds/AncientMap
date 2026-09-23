# SPDX-License-Identifier: AGPL-3.0-only
"""The card generator's per-site computation is one pure function, shared with the remediation.

`site_card_stats()` and `content_stats()` were extracted from `_upsert_stats` /
`_get_content_stats` on 2026-09-23 so that the card_stats lane
(scripts/remediation/mechanical/card_stats.py) computes exactly what `generate_stats()` writes,
by calling the same code. These tests pin the three things that makes true: the function is the
old inline computation, the upsert uses it for every column it writes, and the content counts
treat a missing content type as a type of its own, as the ORM loop always did.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.cardgame import generator
from api.cardgame.stats import compute_all_stats
from pipeline.historical_boundaries.tagger import tag_site


def site(**over: object) -> SimpleNamespace:
    base = {
        "id": "00000000-0000-0000-0000-000000000001",
        "site_type": "Temple complex",
        "period_name": "3000 - 1500 BC",
        "period_start": -2500,
        "period_end": None,
        "description": "A temple on a UNESCO World Heritage list.",
        "source_url": "https://en.wikipedia.org/wiki/X",
        "thumbnail_url": "",
        "country": "Malta",
        "lat": 35.869,
        "lon": 14.512,
    }
    base.update(over)
    return SimpleNamespace(**base)


def link(content_type: str | None, content_source: str | None) -> SimpleNamespace:
    return SimpleNamespace(content_type=content_type, content_source=content_source)


def test_content_stats_counts_links_types_and_a_3d_model() -> None:
    assert generator.content_stats([]) == (0, 0, False)
    links = [link("reference", "web"), link("reference", "web"), link(None, "x")]
    assert generator.content_stats(links) == (3, 2, False), "None is a type of its own"
    assert generator.content_stats([link("model", "x")])[2] is True
    assert generator.content_stats([link("video", "sketchfab")])[2] is True


def test_site_card_stats_is_the_old_inline_computation() -> None:
    row = site()
    combos = {(row.site_type, row.period_name): 7}
    got = generator.site_card_stats(
        row, combo_counts=combos, content=(3, 2, True), wiki_image_count=4, engagement=(1, 2)
    )
    expected = compute_all_stats(
        period_start=row.period_start,
        period_end=row.period_end,
        site_type=row.site_type,
        has_description=True,
        has_thumbnail=False,
        content_link_count=3,
        wiki_image_count=4,
        has_source_url=True,
        combo_count=7,
        is_unesco=True,
        like_count=1,
        bookmark_count=2,
        content_type_count=2,
        has_3d_model=True,
        country="Malta",
    )
    empires = tag_site(lat=row.lat, lon=row.lon, period_start=row.period_start)
    assert got == {**expected, "empires": empires, "empire_count": len(empires)}


def test_a_combination_nobody_else_has_counts_as_one() -> None:
    lonely = generator.site_card_stats(
        site(), combo_counts={}, content=(0, 0, False), wiki_image_count=0, engagement=(0, 0)
    )
    once = generator.site_card_stats(
        site(),
        combo_counts={("Temple complex", "3000 - 1500 BC"): 1},
        content=(0, 0, False),
        wiki_image_count=0,
        engagement=(0, 0),
    )
    assert lonely == once


class _Session:
    """The three calls `_upsert_stats` makes on a session once the counts are fetched; anything
    else is refused, so the upsert cannot reach the database some other way unnoticed."""

    def __init__(self, existing: dict[str, object]) -> None:
        self.existing = existing
        self.added: list[object] = []

    def get(self, model: object, key: str) -> object | None:
        assert model is generator.CardStats
        return self.existing.get(key)

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        return None

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"_upsert_stats called session.{name}")


def test_the_upsert_writes_exactly_what_site_card_stats_returns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict] = []

    def fake_stats(row, *, combo_counts, content, wiki_image_count, engagement):  # noqa: ANN001
        seen.append(
            {
                "content": content,
                "images": wiki_image_count,
                "engagement": engagement,
                "combos": combo_counts,
            }
        )
        return {"mystery": 9, "civilization": row.country, "rarity_tier": 3}

    monkeypatch.setattr(generator, "site_card_stats", fake_stats)
    monkeypatch.setattr(generator, "_get_content_stats", lambda s, sid: (5, 2, False))
    monkeypatch.setattr(generator, "_get_wiki_image_count", lambda s, sid: 11)
    monkeypatch.setattr(generator, "_get_engagement", lambda s, sid: (1, 0))
    card = SimpleNamespace(mystery=1, civilization="Pakistan", rarity_tier=2)
    session = _Session({"a": card})
    combos = {("x", "y"): 3}
    created, updated, tiers = generator._upsert_stats(
        session, [site(id="a", country="Afghanistan")], combos, progress=False
    )
    assert (created, updated, dict(tiers)) == (0, 1, {3: 1})
    assert (card.mystery, card.civilization, card.rarity_tier) == (9, "Afghanistan", 3)
    assert seen == [
        {"content": (5, 2, False), "images": 11, "engagement": (1, 0), "combos": combos}
    ]
