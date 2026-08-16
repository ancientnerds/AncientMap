"""Generate the Python reference heads for the meta.ts port (react-ssr plan, Task 5).

Writes, per indexed page type (plus branch variants), two files into
ancient-nerds-map/src/seo/__tests__/pyref/:

    {name}.html        the exact head fragment pipeline/seo_pages.py renders
    {name}.route.json  the route payload the TS meta function receives

The Vitest comparison test (src/seo/__tests__/meta.test.ts) renders the
route payload through renderHead() and diffs against the head byte for
byte. The only tolerated difference is the <style>{SSR_CSS}</style> block,
which meta.ts deliberately does not embed — after the cutover the CSS
comes from the built Vite bundle, not from the head fragment.

For story/storyArchive/sitesIndex/country the payload is taken verbatim
from SeoPage.route, i.e. exactly what production injects into
window.__AN_ROUTE__ today. site/research/article and the two index types
still carry stub payloads in production ({"id"}, {"slug"}, {}), so for
those the script builds the post-cutover payload shape (react-ssr plan,
Tasks 11-14) from the same fixture values that fed the Python renderer —
head and payload cannot drift apart because both come from one fixture.

Reproducible:  python scripts/gen_meta_reference.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from pipeline.seo_pages import (  # noqa: E402
    SeoPage,
    _date_parts,
    article_index_page,
    article_page,
    country_sites_page,
    research_index_page,
    research_page,
    site_detail_page,
    sites_index_page,
    story_archive_page,
    story_page,
)
from pipeline.sites_html_renderer import _period_display  # noqa: E402

OUT = REPO / "ancient-nerds-map" / "src" / "seo" / "__tests__" / "pyref"

# ---------------------------------------------------------------------------
# Fixtures. Deliberately awkward data: non-ASCII (Türkiye, Göbekli),
# HTML-escapables (&, ", ', <) and a >150-char post_text so every escape
# branch of _meta_head() and every description branch is exercised.
# ---------------------------------------------------------------------------

STORY = {
    "id": 4711,
    "headline": 'Bronze Age "Sun Chariot" & a second fragment found at Trundholm',
    "summary": (
        "Conservators at the National Museum confirm a second fragment "
        "of the Trundholm Sun Chariot."
    ),
    "post_text": (
        "Archaeologists re-examined spoil heaps from the 1902 Trundholm excavation "
        "and recovered a second bronze fragment <matching> the Sun Chariot's spiral "
        "ornament.\n"
        "The piece confirms the chariot was cast in at least two moulds, and traces "
        "of gold leaf survive on one edge.\n"
        "Museum conservators date the casting to roughly 1400 BC."
    ),
    "facts": ["Second fragment found in the 1902 spoil heaps"],
    "published_at": datetime(2026, 3, 14, 9, 30),
    "screenshot_url": "/data/news/screenshots/4711.jpg",
    "youtube_url": "https://www.youtube.com/watch?v=abc123",
    "timestamp_seconds": 754,
    "video_title": "Sun Chariot's Lost Twin?",
    "channel_name": "Ancient Architects",
    "news_category": "Excavation",
    "site_name": "Trundholm Mose",
    "site_id": "1b2c3d4e-0000-4000-8000-000000000000",
    "site_country": "Denmark",
    "site_curated": True,
    "speculative_tag": "",
    "web_sources": [
        {
            "url": "https://en.natmus.dk/sun-chariot/",
            "title": "The Sun Chariot — National Museum of Denmark",
            "snippet": "The Sun Chariot was found in 1902 in the Trundholm bog.",
        }
    ],
    "related": [
        {
            "slug": "trundholm-bog-survey-planned-4600",
            "headline": "Trundholm bog survey planned",
            "kind": "site",
        }
    ],
}

# Under 150 collapsed chars of post_text: since b4690a3 the description /
# og:description / twitter:description tags must be omitted entirely.
# The </script> in the headline drives the JSON-LD escape path: _json_str /
# jsonStr must mask the < to \\u003c or the schema breaks out of its
# <script> tag; the <title> path must escape it to &lt;/script&gt;.
STORY_SHORT = {
    **STORY,
    "id": 4712,
    "headline": "Short dig note from Trundholm </script>",
    "summary": "A one-line update from the bog.",
    "post_text": "A one-line update.",
    "screenshot_url": "",
    "youtube_url": "",
    "timestamp_seconds": None,
    "web_sources": [],
    "related": [],
}

ARCHIVE_STORIES = [
    {
        "slug": "bronze-age-sun-chariot-a-second-fragment-found-at-trundholm-4711",
        "headline": STORY["headline"],
        "summary": STORY["summary"],
        "published_at": STORY["published_at"],
        "news_category": "Excavation",
        "site_name": "Trundholm Mose",
        "channel_name": "Ancient Architects",
        "speculative_tag": "",
        "screenshot_url": "/data/news/screenshots/4711.jpg",
    },
    {
        "slug": "karahan-tepe-carvings-reinterpreted-4650",
        "headline": "Karahan Tepe carvings reinterpreted",
        "summary": "A new reading of the Karahan Tepe reliefs links them to seasonal feasting.",
        "published_at": datetime(2026, 3, 2, 18, 0),
        "news_category": "Interpretation",
        "site_name": "Karahan Tepe",
        "channel_name": "Stefan Milo",
        "speculative_tag": "speculative",
        "screenshot_url": "",
    },
]

SITE = {
    "id": "9c8b7a65-4321-4cba-8000-111122223333",
    "name": "Göbekli Tepe",
    "country": "Türkiye",
    "site_type": "Temple complex",
    "period_name": "< 4500 BC",
    "period_start": -9600,
    "period_end": None,
    "lat": 37.2231,
    "lon": 38.9224,
    "description": (
        "The world's first known temple complex, raised by hunter-gatherers "
        "around 9600 BC — millennia before pottery or the wheel.\n"
        "Its T-shaped pillars carry reliefs of foxes, snakes and vultures."
    ),
}

SITE_RELATED = {
    "alt_names": ["Göbekli Tepe", "Portasar", "Potbelly Hill"],
    "image": {
        "url": "/data/images/wiki/9c8b7a65/hero.webp",
        "author": "Teomancimit",
        "license": "CC BY-SA 3.0",
        "commons_url": "https://commons.wikimedia.org/wiki/File:G%C3%B6bekli_Tepe.jpg",
    },
    "news": [{"slug": "gobekli-tepe-dig-resumes-991", "headline": "Göbekli Tepe dig resumes"}],
    "links": [
        {
            "title": "UNESCO World Heritage listing",
            "url": "https://whc.unesco.org/en/list/1572/",
            "content_type": "reference",
        }
    ],
    "parent": None,
    "siblings": [{"name": "Karahan Tepe", "path": "/sites/türkiye/karahan-tepe-1a2b3c4d"}],
}

COUNTRY_SITES = [
    {
        "name": "Göbekli Tepe",
        "path": "/sites/türkiye/göbekli-tepe-9c8b7a65",
        "description": SITE["description"],
        "site_type": "Temple complex",
        "period_name": "< 4500 BC",
        "period_start": -9600,
        "thumbnail_url": "/data/images/wiki/9c8b7a65/hero.webp",
    },
    {
        "name": "Karahan Tepe",
        "path": "/sites/türkiye/karahan-tepe-1a2b3c4d",
        "description": (
            "Sister site of Göbekli Tepe with more than 250 T-shaped pillars "
            "still embedded in the bedrock."
        ),
        "site_type": "Temple complex",
        "period_name": "< 4500 BC",
        "period_start": -8800,
        "thumbnail_url": "",
    },
    {
        "name": "Aspendos Theatre",
        "path": "/sites/türkiye/aspendos-theatre-5e6f7a8b",
        "description": (
            "The best-preserved Roman theatre of the ancient world, built under Marcus Aurelius."
        ),
        "site_type": "Theatre",
        "period_name": "1 – 500 AD",
        "period_start": 155,
        "thumbnail_url": "",
    },
]

COUNTRIES = [
    {"name": "Türkiye", "count": 218},
    {"name": "Denmark", "count": 42},
    {"name": "Peru", "count": 4752},
]

PAPER = {
    "slug": "obsidian-trade-networks-anatolia",
    "title": "Obsidian Trade Networks in Neolithic Anatolia",
    "summary": (
        "Sourcing analyses of 1,200 obsidian artefacts reveal two distinct "
        "exchange spheres centred on the Cappadocian and Lake Van sources."
    ),
    "author": "Theo",
    "published_at": "2026-07-02T04:15:00",
    "hero_image_url": "https://ancientnerds.com/data/research/obsidian/hero.webp",
}

PAPER_PERSON = {
    **PAPER,
    "slug": "gobekli-tepe-water-management",
    "title": "Water Management at Göbekli Tepe",
    "summary": "Cistern volumes suggest the enclosures hosted gatherings of several hundred people.",
    "author": "Dr. Jane Doe",
    "hero_image_url": None,
}

PAPERS_INDEX = [
    {"slug": p["slug"], "title": p["title"], "summary": p["summary"]} for p in (PAPER, PAPER_PERSON)
]

ARTICLE = {
    "slug": "week-31-hoards-and-harbours",
    "title": "Week 31: Hoards & Harbours",
    "summary": "A Viking silver hoard on Gotland and a submerged Bronze Age harbour off Crete.",
    "published_at": datetime(2026, 8, 3),
    "hero_image_url": None,
}

ARTICLES_INDEX = [
    {"slug": ARTICLE["slug"], "title": ARTICLE["title"], "summary": ARTICLE["summary"]},
    {
        "slug": "week-30-mummies-and-mosaics",
        "title": "Week 30: Mummies & Mosaics",
        "summary": "New Saqqara burials and a four-season mosaic under an Antakya hotel.",
    },
]


# ---------------------------------------------------------------------------
# Post-cutover payloads for the types whose production payload is still a
# stub. Shapes per react-ssr plan Tasks 11-14; values from the fixtures
# above, derived exactly the way the Python renderer derives them.
# ---------------------------------------------------------------------------


def _site_route() -> dict:
    return {
        "type": "site",
        "id": SITE["id"],
        "name": SITE["name"],
        "country": SITE["country"],
        "siteType": SITE["site_type"] or "Archaeological site",
        "period": _period_display(SITE),
        "description": SITE["description"],
        "coords": {"lat": SITE["lat"], "lon": SITE["lon"]},
        "image": {
            "url": SITE_RELATED["image"]["url"],
            "author": SITE_RELATED["image"]["author"],
            "license": SITE_RELATED["image"]["license"],
            "commonsUrl": SITE_RELATED["image"]["commons_url"],
        },
        "altNames": SITE_RELATED["alt_names"],
        "news": SITE_RELATED["news"],
        "links": [
            {"title": link["title"], "url": link["url"], "contentType": link["content_type"]}
            for link in SITE_RELATED["links"]
        ],
        "parent": SITE_RELATED["parent"],
        "siblings": SITE_RELATED["siblings"],
    }


def _paper_route(paper: dict) -> dict:
    return {
        "type": "research",
        "slug": paper["slug"],
        "title": paper["title"],
        "summary": (paper.get("summary") or "").strip(),
        "author": paper.get("author") or "Theo",
        "publishedAt": _date_parts(paper.get("published_at"))[0],
        "heroImageUrl": paper.get("hero_image_url") or "",
    }


def _article_route(article: dict) -> dict:
    return {
        "type": "article",
        "slug": article["slug"],
        "title": article["title"],
        "summary": (article.get("summary") or "").strip(),
        "publishedAt": _date_parts(article.get("published_at"))[0],
        "heroImageUrl": article.get("hero_image_url") or "",
    }


def cases() -> list[tuple[str, SeoPage, dict | None]]:
    """(name, rendered page, payload override). None = use SeoPage.route."""
    return [
        ("story", story_page(STORY), None),
        ("story_short", story_page(STORY_SHORT), None),
        ("storyArchive", story_archive_page(ARCHIVE_STORIES, 1, 94, 2248), None),
        ("storyArchive_page2", story_archive_page(ARCHIVE_STORIES, 2, 94, 2248), None),
        ("site", site_detail_page(SITE, SITE_RELATED), _site_route()),
        ("sitesIndex", sites_index_page(COUNTRIES), None),
        ("country", country_sites_page("Türkiye", COUNTRY_SITES), None),
        ("research", research_page(PAPER, "<p>body</p>"), _paper_route(PAPER)),
        ("research_person", research_page(PAPER_PERSON, "<p>body</p>"), _paper_route(PAPER_PERSON)),
        (
            "researchIndex",
            research_index_page(PAPERS_INDEX),
            {"type": "researchIndex", "papers": PAPERS_INDEX},
        ),
        ("article", article_page(ARTICLE, "<p>body</p>"), _article_route(ARTICLE)),
        (
            "articleIndex",
            article_index_page(ARTICLES_INDEX),
            {"type": "articleIndex", "articles": ARTICLES_INDEX},
        ),
    ]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, page, route_override in cases():
        route = route_override if route_override is not None else json.loads(page.route)
        with open(OUT / f"{name}.html", "w", encoding="utf-8", newline="\n") as fh:
            fh.write(page.head)
        with open(OUT / f"{name}.route.json", "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(route, ensure_ascii=False, indent=2) + "\n")
        print(f"wrote {name}.html + {name}.route.json")


if __name__ == "__main__":
    main()
