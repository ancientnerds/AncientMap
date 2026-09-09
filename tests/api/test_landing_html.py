"""Payload builders for GET /home (landing-live sections, 2026-09-09).

DB-less: rows are SimpleNamespaces. The field names asserted here are the
contract anRoute.ts::LandingRoute declares.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from api.routes.landing_html import (
    apply_stats,
    first_sentence,
    journal_teaser,
    paper_teaser,
    pick_lead_and_rail,
    reading_minutes,
    sites_compact,
    sites_long,
    story_teaser,
)

NOW = datetime(2026, 9, 9, 12, 0, 0)


def item(id_, *, sig, hours_ago, category="artifact", site=None, post="One sentence. Two. https://x.y"):
    video = SimpleNamespace(channel=SimpleNamespace(name="Inside Archaeology"))
    return SimpleNamespace(
        id=id_,
        headline=f"Headline {id_}",
        post_text=post,
        screenshot_url=f"/data/news/screenshots/{id_}.webp",
        news_category=category,
        significance=sig,
        created_at=NOW - timedelta(hours=hours_ago),
        web_sources=[{"url": "a"}, {"url": "b"}],
        video=video,
        site=site,
    )


def test_first_sentence_drops_trailing_links_and_caps_length():
    assert first_sentence("One sentence. Two. https://x.y") == "One sentence."
    assert first_sentence("No period https://x.y") == "No period"
    assert first_sentence(None) == ""
    long = "word " * 50 + "end."
    out = first_sentence(long)
    assert len(out) <= 181 and out.endswith("…")


def test_story_teaser_maps_row_and_site():
    site = SimpleNamespace(
        id="da3ff939-2402-4bf8-a476-e7725c81c8d5", name="Stirling Castle", country="United Kingdom"
    )
    t = story_teaser(item(7, sig=6, hours_ago=3, site=site))
    assert t == {
        "id": 7,
        "headline": "Headline 7",
        "summary": "One sentence.",
        "screenshot_url": "/data/news/screenshots/7.webp",
        "category": "artifact",
        "significance": 6,
        "created_at": (NOW - timedelta(hours=3)).isoformat(),
        "channel": "Inside Archaeology",
        "sources": 2,
        "path": "/news-archive/headline-7-7",
        "site": {"name": "Stirling Castle", "country": "United Kingdom"},
    }
    assert story_teaser(item(8, sig=None, hours_ago=1))["site"] is None
    no_country = SimpleNamespace(id="x", name="Etowah", country=None)
    assert story_teaser(item(9, sig=2, hours_ago=1, site=no_country))["site"] is None


def test_pick_lead_prefers_the_48h_window_and_never_duplicates():
    recent = [item(i, sig=3, hours_ago=i) for i in range(1, 8)]  # ids 1..7, newest first
    lead_48h = item(5, sig=9, hours_ago=5)
    lead, rail = pick_lead_and_rail(recent, lead_48h)
    assert lead.id == 5
    assert [r.id for r in rail] == [1, 2, 3, 4, 6, 7]


def test_pick_lead_falls_back_to_the_best_of_the_recent_seven():
    recent = [item(1, sig=2, hours_ago=60), item(2, sig=8, hours_ago=61), item(3, sig=8, hours_ago=62)]
    lead, rail = pick_lead_and_rail(recent, None)
    assert lead.id == 2  # tie on 8 → the newer one
    assert [r.id for r in rail] == [1, 3]


def test_pick_lead_keeps_six_rows_when_the_lead_is_outside_the_seven():
    recent = [item(i, sig=3, hours_ago=i) for i in range(1, 8)]
    lead, rail = pick_lead_and_rail(recent, item(99, sig=9, hours_ago=40))
    assert lead.id == 99
    assert len(rail) == 6 and [r.id for r in rail] == [1, 2, 3, 4, 5, 6]


def test_reading_minutes_rounds_up_at_238_wpm():
    assert reading_minutes(2762) == 12
    assert reading_minutes(238) == 1
    assert reading_minutes(0) == 0


def test_journal_teaser_counts_words_sections_sources_and_first_image():
    content = (
        "# Title\n\nIntro text here.\n\n## Artifact Discoveries\n\nText with a [link](https://a.b) "
        "and ![img](/data/news/screenshots/nMxEoIrMwX8_367.webp).\n\n## In Brief\n\nmore\n\n"
        "## Sources\n\n1. https://c.d\n\n## Videos\n\nV1. https://youtu.be/x\n"
    )
    row = SimpleNamespace(
        id=74,
        title="Week of August 31: Wooden Structure, and More",
        summary="Summary.",
        content=content,
        week_start=datetime(2026, 8, 31),
        week_end=datetime(2026, 9, 6, 23, 59, 59),
        published_at=datetime(2026, 9, 7, 4, 20, 43),
    )
    t = journal_teaser(row)
    assert t["sections"] == ["Artifact Discoveries", "In Brief"]
    assert t["sources"] == 3
    assert t["image_url"] == "/data/news/screenshots/nMxEoIrMwX8_367.webp"
    assert t["path"] == "/articles/week-of-august-31-wooden-structure-and-more"
    assert t["words"] == len(content.split()) and t["minutes"] == reading_minutes(t["words"])
    assert t["week_start"] == "2026-08-31T00:00:00" and t["published_at"] == "2026-09-07T04:20:43"


def test_paper_teaser_uses_the_public_api_mapping():
    row = SimpleNamespace(
        id="4bf8", slug="the-egyptian-hard-stone-precision-debate", question="Q?", published_by=None,
        published_at=datetime(2026, 8, 31, 22, 7, 6), sites_found=2748,
        title="The Egyptian Hard-Stone Precision Debate", card_description="Summary.",
        score="98", badge="Unverified", word_count="6466", hero_src="/data/research-images/x.jpg",
    )
    t = paper_teaser(row)
    assert t == {
        "slug": "the-egyptian-hard-stone-precision-debate",
        "title": "The Egyptian Hard-Stone Precision Debate",
        "summary": "Summary.",
        "published_at": "2026-08-31T22:07:06",
        "words": 6466,
        "minutes": 28,
        "sources_analyzed": 2748,
        "quality_score": 98,
        "hero_image_url": "https://ancientnerds.com/data/research-images/x.jpg",
        "path": "/research/the-egyptian-hard-stone-precision-debate",
    }


def test_number_formats():
    assert sites_compact(1_759_673) == "1.76M"
    assert sites_compact(999_999) == "999K"
    assert sites_long(1_759_673) == "1.7 million"


def test_apply_stats_replaces_only_marked_values():
    html = (
        '<div class="hero-stat-value" data-stat="sites">1.7M+</div>'
        '<span data-stat="sites-long">1.7 million</span>'
        '<div class="hero-stat-value" data-stat="countries">90+</div>'
        '<div class="hero-stat-value">30+</div>'
    )
    out = apply_stats(html, {"total_sites": 1_759_673, "curated_countries": 98})
    assert 'data-stat="sites">1.76M<' in out
    assert 'data-stat="sites-long">1.7 million<' in out
    assert 'data-stat="countries">98<' in out
    assert '<div class="hero-stat-value">30+</div>' in out
