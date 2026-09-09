"""Payload builders for GET /home (landing-live sections, 2026-09-09).

DB-less: rows are SimpleNamespaces. The field names asserted here are the
contract anRoute.ts::LandingRoute declares.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.gzip import GZipMiddleware

from api.routes import landing_html
from api.routes.landing_html import (
    apply_stats,
    excerpt_html,
    journal_lead,
    journal_teaser,
    lead_window_start,
    paper_lead,
    paper_teaser,
    pick_lead_and_rail,
    reading_minutes,
    sites_compact,
    sites_long,
)
from pipeline.database import get_db

NOW = datetime(2026, 9, 9, 12, 0, 0)
# The three hero markers apply_stats() insists on; a shell without them raises.
_SHELL_MARKERS = (
    '<div data-stat="sites">1.7M+</div><span data-stat="sites-long">1.7 million</span>'
    '<div data-stat="countries">90+</div>'
)


def item(id_, *, sig, hours_ago, category="artifact", site=None, post="One sentence. Two. https://x.y"):
    """A joinedload-ed NewsItem row: every attribute story_payload() touches."""
    video = SimpleNamespace(
        id=f"vid{id_}",
        title=f"Video {id_}",
        published_at=NOW - timedelta(hours=hours_ago),
        channel=SimpleNamespace(name="Inside Archaeology"),
    )
    return SimpleNamespace(
        id=id_,
        headline=f"Headline {id_}",
        summary=f"Summary {id_}",
        facts=[f"Fact {id_}"],
        post_text=post,
        screenshot_url=f"/data/news/screenshots/{id_}.webp",
        news_category=category,
        significance=sig,
        created_at=NOW - timedelta(hours=hours_ago),
        web_sources=[{"url": "a"}, {"url": "b"}],
        timestamp_seconds=None,
        speculative_tag=None,
        site_name_extracted=None,
        video=video,
        site=site,
    )


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


# ── excerpt_html: the lead journal and the lead paper open on the homepage ──
# The window runs the page, so the lead carries real body HTML — cut at a
# block boundary, never mid-tag and never inside a list or a figure.


def test_excerpt_leaves_a_short_body_whole_and_says_so():
    html = "<p>One short paragraph.</p>"
    assert excerpt_html(html, max_chars=2500) == (html, False)


def test_excerpt_cuts_directly_after_the_closing_p_that_crosses_the_budget():
    html = "<p>" + "a" * 40 + "</p><p>second</p><p>third</p>"
    out, cut = excerpt_html(html, max_chars=30)
    assert cut is True
    assert out == "<p>" + "a" * 40 + "</p>"


def test_excerpt_waits_for_the_closing_ul_instead_of_cutting_between_list_items():
    html = "<p>intro</p><ul><li>" + "a" * 40 + "</li><li>second item</li></ul><p>after</p>"
    out, cut = excerpt_html(html, max_chars=20)
    assert cut is True
    assert out.endswith("</ul>")
    assert out.count("<li>") == out.count("</li>") == 2
    assert "after" not in out


def test_excerpt_never_splits_a_nested_list():
    html = "<ul><li>one<ul><li>" + "b" * 60 + "</li></ul></li></ul><p>after</p>"
    out, cut = excerpt_html(html, max_chars=20)
    assert cut is True
    assert out.count("<ul>") == out.count("</ul>") == 2
    assert "after" not in out


def test_excerpt_keeps_a_figure_with_its_image_and_caption_whole():
    html = (
        "<p>" + "a" * 40 + "</p>"
        '<figure class="article-figure"><img src="/x.webp" alt="A"/>'
        "<figcaption>Caption text</figcaption></figure><p>after</p>"
    )
    out, cut = excerpt_html(html, max_chars=45)
    assert cut is True
    assert out.endswith("</figure>")
    assert "<img" in out and "</figcaption>" in out
    assert "after" not in out


def test_excerpt_stops_before_a_heading_instead_of_ending_on_it():
    """A heading is the title of what comes after it. When the heading is the
    block that crosses the budget, the excerpt ends BEFORE it: an excerpt whose
    last line announces a section that was cut away reads as broken."""
    html = "<p>" + "a" * 40 + "</p><h2 id=\"s\">Section</h2><p>body</p>"
    out, cut = excerpt_html(html, max_chars=30)
    assert cut is True
    assert out == "<p>" + "a" * 40 + "</p>"
    # 44 puts the crossing on the heading itself: same end, not "...</h2>".
    out2, cut2 = excerpt_html(html, max_chars=44)
    assert cut2 is True
    assert out2 == "<p>" + "a" * 40 + "</p>"


def test_excerpt_never_cuts_inside_a_wrapper_around_a_block():
    """Depth is tracked for every non-void tag, not only for lists, quotes,
    figures and tables. A <div class="footnote"> around an <ol> used to be
    invisible, so the </ol> looked top-level and the excerpt came back with
    the <div> still open."""
    html = (
        "<p>" + "a" * 40 + "</p>"
        '<div class="footnote"><ol><li>one</li><li>two</li></ol></div>'
        "<p>after</p><p>tail</p>"
    )
    out, cut = excerpt_html(html, max_chars=45)
    assert cut is True
    assert out.count("<div") == out.count("</div>") == 1
    assert out.count("<ol>") == out.count("</ol>") == 1
    assert out.endswith("<p>after</p>")
    assert "tail" not in out


def test_excerpt_output_has_balanced_tags():
    html = (
        "<h2 id=\"a\">Heading</h2><p>" + "word " * 200 + "</p>"
        "<blockquote><p>quoted</p></blockquote><ul><li>x</li></ul><p>tail</p>"
    )
    out, cut = excerpt_html(html, max_chars=100)
    assert cut is True
    for tag in ("p", "h2", "ul", "li", "blockquote"):
        assert out.count(f"<{tag}") == out.count(f"</{tag}>"), tag


def test_excerpt_does_not_claim_a_cut_when_the_last_block_ends_the_document():
    """The flag drives the "continue reading" link — it may not promise text
    that is not there. A body whose final block crosses the budget is still
    complete."""
    html = "<p>" + "a" * 4000 + "</p>"
    assert excerpt_html(html, max_chars=100) == (html, False)


def test_journal_lead_is_the_teaser_plus_the_rendered_opening():
    row = SimpleNamespace(
        id=74,
        title="Week of August 31",
        summary="S",
        content="## A\n\n" + "word " * 900 + "\n\n## B\n\ntail\n",
        week_start=None,
        week_end=None,
        published_at=None,
    )
    lead = journal_lead(row)
    teaser = journal_teaser(row)
    assert {k: lead[k] for k in teaser} == teaser  # the teaser survives untouched
    assert lead["excerpted"] is True
    assert lead["body_html"].startswith("<h2")
    assert "tail" not in lead["body_html"]


def test_paper_lead_adds_author_and_the_report_opening():
    """One row, not two: fetch_paper() selects PAPER_SUMMARY_COLUMNS on top of
    the report, so it already carries everything paper_teaser() reads."""
    row = SimpleNamespace(
        id="a", slug="paper-a", question="Q", published_by=None, published_at=None,
        sites_found=10, title="Paper A", card_description=None, score=None, badge=None,
        word_count=None, hero_src=None,
        published_report="# Paper A\n\n" + "word " * 900 + "\n\n## Tail\n\nlast\n",
        report=None,
    )
    lead = paper_lead(row)
    assert {k: lead[k] for k in paper_teaser(row)} == paper_teaser(row)
    assert lead["author"] is None
    assert lead["excerpted"] is True
    # report_markdown strips the paper's own title heading, like the page does.
    assert "<h1" not in lead["body_html"]
    assert "last" not in lead["body_html"]


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


def test_apply_stats_replaces_every_occurrence_of_a_marker():
    html = _SHELL_MARKERS + '<b data-stat="countries">90+</b>'
    out = apply_stats(html, {"total_sites": 1_759_673, "curated_countries": 98})
    assert out.count(">98<") == 2


def test_apply_stats_raises_when_the_shell_lost_a_marker():
    """A missing marker is a broken shell, not a cosmetic miss — the hero would
    ship the hard-coded "90+" forever. Same standard as render_app_shell()
    refusing a shell without #root."""
    html = '<div data-stat="sites">1.7M+</div><span data-stat="sites-long">1.7 million</span>'
    try:
        apply_stats(html, {"total_sites": 1_759_673, "curated_countries": 98})
    except ValueError as exc:
        assert 'data-stat="countries"' in str(exc)
    else:
        raise AssertionError("apply_stats accepted a shell without the countries marker")


def test_lead_window_start_is_48h_before_the_given_now():
    assert lead_window_start(NOW) == datetime(2026, 9, 7, 12, 0, 0)


def _landing_data():
    site = SimpleNamespace(
        id="16147718-a70b-486e-aaba-9cf71316602c",
        name="Roman grave",
        country="Austria",
        site_type="Battlefield",
        period_name="Roman",
        period_start=100,
        source_id="ancient_nerds",
    )
    recent = [item(i, sig=3, hours_ago=i) for i in range(1, 8)]
    return {
        "recent": recent,
        "lead_48h": item(9, sig=9, hours_ago=2, category="bioarchaeology", site=site),
        "categories": ["artifact", "bioarchaeology"],
        "journals": [
            SimpleNamespace(id=74, title="Week of August 31", summary="S", content="## A\n\ntext", week_start=None, week_end=None, published_at=None),
            SimpleNamespace(id=73, title="Week of August 24", summary=None, content="text", week_start=None, week_end=None, published_at=None),
        ],
        "journal_total": 23,
        "papers": [
            SimpleNamespace(id="a", slug="paper-a", question="Q", published_by=None, published_at=None, sites_found=10, title="Paper A", card_description=None, score=None, badge=None, word_count=None, hero_src=None),
            SimpleNamespace(id="b", slug="paper-b", question="Q", published_by=None, published_at=None, sites_found=20, title="Paper B", card_description=None, score=None, badge=None, word_count=None, hero_src=None),
        ],
        # research_html.fetch_paper()'s row for the lead paper: the summary
        # columns AND the report, which is why that one row builds the lead.
        "paper_full": SimpleNamespace(
            id="a", slug="paper-a", question="Q", published_by=None, published_at=None,
            sites_found=10, title="Paper A", card_description=None, score=None, badge=None,
            word_count=None, hero_src=None,
            published_report="## Findings\n\nreport text", report=None,
        ),
        "paper_total": 24,
        "news_stats": {"total_items": 3189, "total_articles": 23},
    }


def test_home_route_hands_the_landing_payload_and_substitutes_hero_counts():
    landing_html._cache.clear()
    # render_app_shell is mocked, so the "injected" body is part of the fake shell
    shell = (
        '<html><div class="hero-stat-value" data-stat="sites">1.7M+</div>'
        '<span data-stat="sites-long">1.7 million</span>'
        '<div class="hero-stat-value" data-stat="countries">90+</div>'
        '<div id="root"><p>live</p></div></html>'
    )
    with (
        patch.object(landing_html, "fetch_landing_data", return_value=_landing_data()),
        patch.object(landing_html, "get_site_stats", return_value={"total_sites": 1_759_673, "curated_countries": 98}),
        patch.object(landing_html, "get_current_research", new=AsyncMock(return_value={"running": {"question": "Osiris", "started_at": "2026-09-09T06:00:00", "sites_found": 12}})),
        patch("api.seo_shell.render_page", return_value=("<title>x</title>", "<p>live</p>")) as render,
        patch("api.seo_shell.render_app_shell", return_value=shell),
    ):
        resp = asyncio.run(landing_html.home(db=object()))

    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "public, max-age=300"
    body = resp.body.decode()
    assert 'data-stat="sites">1.76M<' in body and "<p>live</p>" in body
    assert 'data-stat="countries">98<' in body

    route = render.call_args[0][0]
    assert route["type"] == "landing"
    assert route["stats"] == {"sites": 1_759_673, "stories": 3189, "journals": 23, "papers": 24}
    lead = route["stories"]["lead"]
    assert lead["id"] == 9 and len(route["stories"]["rail"]) == 6
    # The window runs the story page, so the payload is the story page's own —
    # full body, video and site, minus the route discriminator.
    assert lead["headline"] == "Headline 9"
    assert lead["post_text"] == "One sentence. Two. https://x.y"
    assert lead["youtube_url"] == "https://www.youtube.com/watch?v=vid9"
    assert lead["site_curated"] is True
    # related=[]: a "read next" list inside the window would be a dead end.
    assert lead["related"] == []
    assert all(r["related"] == [] for r in route["stories"]["rail"])
    # "type" belongs to the route, not to a story inside it.
    assert "type" not in lead and all("type" not in r for r in route["stories"]["rail"])
    assert route["stories"]["categories"] == ["artifact", "bioarchaeology"]
    # The journal and the paper window run their pages, so their leads carry
    # body HTML; the rail rows are links and stay teasers.
    journals = route["journals"]
    assert journals["lead"]["id"] == 74 and journals["total"] == 23
    assert '<h2 id="a">A</h2>' in journals["lead"]["body_html"]
    assert "<p>text</p>" in journals["lead"]["body_html"]
    assert journals["lead"]["excerpted"] is False
    assert all("body_html" not in j for j in journals["rail"])
    papers = route["papers"]
    assert papers["lead"]["slug"] == "paper-a" and papers["total"] == 24
    assert papers["lead"]["author"] is None
    assert "report text" in papers["lead"]["body_html"]
    assert papers["lead"]["excerpted"] is False
    assert all("body_html" not in p for p in papers["rail"])
    assert route["papers"]["theo"] == {"question": "Osiris", "started_at": "2026-09-09T06:00:00", "sites_found": 12}


def test_home_route_omits_sections_without_rows_and_serves_from_cache():
    landing_html._cache.clear()
    data = _landing_data()
    data.update(recent=[], lead_48h=None, journals=[], papers=[])
    with (
        patch.object(landing_html, "fetch_landing_data", return_value=data) as fetch,
        patch.object(landing_html, "get_site_stats", return_value={"total_sites": 5, "curated_countries": 1}),
        patch.object(landing_html, "get_current_research", new=AsyncMock(return_value={"running": None})),
        patch("api.seo_shell.render_page", return_value=("<title>x</title>", "")) as render,
        patch("api.seo_shell.render_app_shell", return_value=_SHELL_MARKERS + '<div id="root"></div>'),
    ):
        asyncio.run(landing_html.home(db=object()))
        asyncio.run(landing_html.home(db=object()))

    route = render.call_args[0][0]
    assert route["stories"] is None and route["journals"] is None and route["papers"] is None
    assert fetch.call_count == 1  # second call came from the 300 s cache


def test_home_stays_decodable_when_the_client_accepts_gzip():
    """Two gzip-negotiated hits must decode identically.

    Caching the Response object breaks that: GZipMiddleware sets
    Content-Encoding on the very `raw_headers` list the Response carries, so
    the cached object came back on hit two already labelled gzip — and the
    middleware then passed the uncompressed body through untouched
    (`content_encoding_set`), which is ERR_CONTENT_DECODING_FAILED in the
    browser. The cache holds bytes for exactly this reason.
    """
    landing_html._cache.clear()
    shell = "<html>" + _SHELL_MARKERS + '<div id="root">' + "<p>live</p>" * 60 + "</div></html>"
    app = FastAPI()
    app.add_middleware(GZipMiddleware, minimum_size=500)
    app.include_router(landing_html.router)
    app.dependency_overrides[get_db] = lambda: object()
    with (
        patch.object(landing_html, "fetch_landing_data", return_value=_landing_data()) as fetch,
        patch.object(
            landing_html,
            "get_site_stats",
            return_value={"total_sites": 1_759_673, "curated_countries": 98},
        ),
        patch.object(
            landing_html, "get_current_research", new=AsyncMock(return_value={"running": None})
        ),
        patch("api.seo_shell.render_page", return_value=("<title>x</title>", "<p>live</p>")),
        patch("api.seo_shell.render_app_shell", return_value=shell),
        TestClient(app) as client,
    ):
        first = client.get("/home", headers={"Accept-Encoding": "gzip"})
        second = client.get("/home", headers={"Accept-Encoding": "gzip"})

    assert first.status_code == 200 and second.status_code == 200
    assert fetch.call_count == 1  # hit two really is the cached document
    assert first.text == second.text
    assert '<div id="root">' in second.text and "<p>live</p>" in second.text


def test_home_answers_head_from_the_cache_without_a_body():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from pipeline.database import get_db

    landing_html._cache.clear()
    landing_html._cache["home"] = (time.monotonic() + 300, b"<html>cached</html>")
    app = FastAPI()
    app.include_router(landing_html.router)
    app.dependency_overrides[get_db] = lambda: object()
    client = TestClient(app)

    head = client.head("/home")
    assert head.status_code == 200 and head.content == b""
    assert head.headers["cache-control"] == "public, max-age=300"
    assert client.get("/home").text == "<html>cached</html>"

