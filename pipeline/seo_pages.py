"""
Head + body fragments for every server-rendered, indexed page.

These are fragments, not documents: pipeline/app_shell.py splices them
into the real built SPA shell, so each indexed URL is the same page a
visitor gets — same header, same styling, same navigation — just with the
content already present for crawlers and no-JS visitors.

The body markup is deliberately plain and self-contained. React replaces
the whole of #root on mount, so this markup only ever renders for
crawlers, for the instant before hydration, and without JavaScript.
"""

from dataclasses import dataclass
from datetime import datetime
from html import escape

from pipeline.article_html_renderer import (
    AI_NOTICE_HTML,
    BASE_URL,
    _json_str,
    story_slug,
)
from pipeline.sites_html_renderer import (
    _coord_display,
    _period_display,
    country_path,
    encode_path,
    site_path,
)

# Scoped so it cannot leak into the React tree that replaces it.
SSR_CSS = """
/* .an-ssr is the scroll container: #root carries overflow:hidden from
   index.css for the globe, so without this the server-rendered content is
   stuck at the first viewport for crawlers and no-JS visitors. */
.an-ssr{height:100vh;overflow-y:auto;overflow-x:hidden;
  max-width:820px;margin:0 auto;padding:88px 24px 64px;
  font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  color:#e0e0e0;line-height:1.65}
.an-ssr h1{font-family:'Cormorant Garamond',Georgia,serif;color:#fff;
  font-size:2.3em;line-height:1.2;margin:0 0 12px}
.an-ssr h2{font-family:'Cormorant Garamond',Georgia,serif;color:#fff;
  font-size:1.5em;margin:32px 0 10px;border-bottom:1px solid #1a3a44;padding-bottom:6px}
.an-ssr a{color:#4fc3f7;text-decoration:none}
.an-ssr a:hover{text-decoration:underline}
.an-ssr .an-crumb{font-size:13px;color:#708890;margin-bottom:16px}
.an-ssr .an-meta{color:#708890;font-size:14px;margin-bottom:24px}
.an-ssr figure{margin:0 0 24px}
.an-ssr figure img{width:100%;height:auto;border-radius:8px;border:1px solid #1a3a44}
.an-ssr figcaption{color:#708890;font-size:12px;margin-top:6px}
.an-ssr table{width:100%;border-collapse:collapse;margin:8px 0 24px}
.an-ssr th,.an-ssr td{text-align:left;padding:8px 12px;
  border-bottom:1px solid #1a3a44;font-size:.95em;vertical-align:top}
.an-ssr th{color:#708890;font-weight:500;width:34%}
.an-ssr ul{margin:8px 0 24px;padding-left:20px}
.an-ssr li{margin-bottom:6px}
.an-ssr .an-cta{display:inline-block;background:#c02023;color:#fff;
  padding:10px 18px;border-radius:6px;margin:4px 0 24px;font-weight:500}
.an-ssr .an-card{border:1px solid #1a3a44;background:#0d2229;border-radius:8px;
  padding:14px 18px;margin-bottom:12px}
.an-ssr .an-card h3{margin:0 0 4px;font-size:1.1em}
.an-ssr .an-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
"""


@dataclass(frozen=True)
class SeoPage:
    """A server-rendered page ready to be spliced into the app shell."""

    entry: str
    head: str
    body: str
    route: str


def _meta_head(
    *,
    title: str,
    description: str,
    canonical: str,
    og_type: str = "website",
    image: str | None = None,
    schema: str | None = None,
) -> str:
    """Shared <head> block — one definition instead of six near-copies."""
    e_title = escape(title)
    e_desc = escape(" ".join(description.split())[:300])
    img = escape(image or f"{BASE_URL}/landing/og-image.png")
    schema_tag = f'\n<script type="application/ld+json">{schema}</script>' if schema else ""
    return f"""<title>{e_title} | Ancient Nerds</title>
<meta name="description" content="{e_desc}">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="{escape(canonical)}">
<meta property="og:type" content="{og_type}">
<meta property="og:url" content="{escape(canonical)}">
<meta property="og:site_name" content="Ancient Nerds">
<meta property="og:title" content="{e_title}">
<meta property="og:description" content="{e_desc}">
<meta property="og:image" content="{img}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e_title}">
<meta name="twitter:description" content="{e_desc}">
<meta name="twitter:image" content="{img}">
<meta name="twitter:site" content="@AncientNerdsDAO">
<style>{SSR_CSS}</style>{schema_tag}"""


def _date_parts(value) -> tuple[str, str]:
    """
    (iso date, display date) from a datetime or an ISO string.

    paper_summary_kwargs() hands out published_at as an ISO string while the
    article rows carry real datetimes; both feed these fragments.
    """
    if not value:
        return "", ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value[:10], value[:10]
    return value.strftime("%Y-%m-%d"), value.strftime("%B %d, %Y")


def _route_json(page_type: str, payload: dict) -> str:
    """
    JSON literal for window.__AN_ROUTE__.

    Escapes '<' so a headline containing "</script>" cannot break out of the
    inline script tag — the same guard _json_str applies to JSON-LD.
    """
    import json

    data = json.dumps({"type": page_type, **payload}, ensure_ascii=False)
    return data.replace("<", "\\u003c")


def _crumbs(*parts: tuple[str, str | None]) -> str:
    """Breadcrumb trail; a None href renders as the current page."""
    return " / ".join(
        f'<a href="{escape(href)}">{escape(label)}</a>' if href else escape(label)
        for label, href in parts
    )


def _link_card(href: str, title: str, blurb: str | None = None) -> str:
    """A linked listing card with an optional truncated blurb."""
    body = ""
    if blurb:
        text = " ".join(blurb.split())
        if len(text) > 180:
            text = text[:180].rsplit(" ", 1)[0] + "…"
        body = f"<p>{escape(text)}</p>"
    return f'<div class="an-card"><h3><a href="{escape(href)}">{escape(title)}</a></h3>{body}</div>'


def _story_card(story: dict) -> str:
    return _link_card(
        f"/news-archive/{encode_path(story['slug'])}",
        story["headline"],
        story.get("summary"),
    )


def _breadcrumb_schema(parts: list[tuple[str, str]]) -> str:
    items = ", ".join(
        f'{{"@type": "ListItem", "position": {i}, "name": {_json_str(label)}, "item": "{url}"}}'
        for i, (label, url) in enumerate(parts, start=1)
    )
    return (
        '{"@context": "https://schema.org", "@type": "BreadcrumbList", '
        f'"itemListElement": [{items}]}}'
    )


# --------------------------------------------------------------------------
# Story (/news-archive/{slug})
# --------------------------------------------------------------------------


def story_page(story: dict) -> SeoPage:
    """One news story. 'Story', not 'news': a new video often covers old finds."""
    slug = story_slug(story["headline"], story["id"])
    canonical = f"{BASE_URL}/news-archive/{encode_path(slug)}"
    headline = story["headline"]
    summary = (story.get("summary") or "").strip()
    pub_date, pub_display = _date_parts(story.get("published_at"))

    screenshot = story.get("screenshot_url") or ""
    if screenshot.startswith("/"):
        screenshot = f"{BASE_URL}{screenshot}"

    paragraphs = "\n".join(
        f"<p>{escape(p.strip())}</p>"
        for p in (story.get("post_text") or "").split("\n")
        if p.strip()
    )

    facts_html = ""
    if story.get("facts"):
        items = "".join(f"<li>{escape(f)}</li>" for f in story["facts"])
        facts_html = f"<h2>Key facts</h2><ul>{items}</ul>"

    # The video snapshot: present in the data all along, but previously only
    # used as an og:image — never shown on the page itself.
    video_html = ""
    youtube_url = story.get("youtube_url") or ""
    if screenshot or youtube_url:
        img = (
            f'<img src="{escape(screenshot)}" alt="{escape(story.get("video_title") or headline)}"'
            ' loading="lazy">'
            if screenshot
            else ""
        )
        caption_bits = []
        if story.get("video_title"):
            caption_bits.append(escape(story["video_title"]))
        if story.get("channel_name"):
            caption_bits.append(f"by {escape(story['channel_name'])}")
        caption = " ".join(caption_bits)
        if youtube_url:
            body = img or caption or "Watch the source video"
            video_html = (
                f'<figure><a href="{escape(youtube_url)}" target="_blank" rel="noopener">{body}</a>'
                f"{f'<figcaption>Source: {caption}</figcaption>' if caption and img else ''}</figure>"
            )
        else:
            video_html = f"<figure>{img}<figcaption>{caption}</figcaption></figure>"

    site_html = ""
    if story.get("site_name") and story.get("site_country") and story.get("site_id"):
        url = site_path(story["site_country"], story["site_name"], story["site_id"])
        site_html = f'<p>Related site: <a href="{escape(url)}">{escape(story["site_name"])}</a></p>'
    elif story.get("site_name"):
        site_html = f"<p>Related site: {escape(story['site_name'])}</p>"

    schema = (
        '{"@context": "https://schema.org", "@type": "NewsArticle", '
        f'"headline": {_json_str(headline)}, '
        f'"description": {_json_str(summary[:300])}, '
        f'"datePublished": "{pub_date}", '
        f'"image": "{escape(screenshot or f"{BASE_URL}/landing/og-image.png")}", '
        '"author": {"@type": "Organization", "name": "Ancient Nerds", '
        f'"url": "{BASE_URL}"}}, '
        '"publisher": {"@type": "Organization", "name": "Ancient Nerds", '
        f'"url": "{BASE_URL}"}}, '
        f'"mainEntityOfPage": "{canonical}", "url": "{canonical}"}}'
    )

    head = _meta_head(
        title=headline,
        description=summary or headline,
        canonical=canonical,
        og_type="article",
        image=screenshot or None,
        schema=schema,
    )

    body = f"""<div class="an-ssr">
<nav class="an-crumb">{_crumbs(("Home", "/"), ("Story Archive", "/news-archive/"), (headline, None))}</nav>
<h1>{escape(headline)}</h1>
<div class="an-meta">{f"<time datetime='{pub_date}'>{pub_display}</time>" if pub_date else ""}
{f" &middot; {escape(story['news_category'])}" if story.get("news_category") else ""}</div>
{AI_NOTICE_HTML}
{video_html}
{f"<p><strong>{escape(summary)}</strong></p>" if summary else ""}
{paragraphs}
{facts_html}
{site_html}
<p><a href="/news-archive/">← All stories</a></p>
</div>"""

    # The payload rides along in __AN_ROUTE__ so React renders the real page
    # immediately — no second round trip, no loading flash, and no risk of the
    # interactive view disagreeing with what the crawler was served.
    payload = {
        "id": story["id"],
        "headline": headline,
        "summary": summary,
        "facts": list(story.get("facts") or []),
        "postText": story.get("post_text") or "",
        "screenshotUrl": screenshot,
        "youtubeUrl": youtube_url,
        "videoTitle": story.get("video_title") or "",
        "channelName": story.get("channel_name") or "",
        "publishedAt": pub_date,
        "publishedDisplay": pub_display,
        "category": story.get("news_category") or "",
        "siteName": story.get("site_name") or "",
        "sitePath": (
            site_path(story["site_country"], story["site_name"], story["site_id"])
            if story.get("site_country") and story.get("site_name") and story.get("site_id")
            else ""
        ),
        "siteId": story.get("site_id") or "",
    }
    return SeoPage("story.html", head, body, _route_json("story", payload))


# --------------------------------------------------------------------------
# Site (/sites/{country}/{slug})
# --------------------------------------------------------------------------


def site_detail_page(site: dict, related: dict) -> SeoPage:
    """One archaeological site — human-curated, so no AI notice."""
    name = site["name"]
    country = site["country"]
    canonical = f"{BASE_URL}{encode_path(site_path(country, name, site['id']))}"
    site_type = site.get("site_type") or "Archaeological site"
    period = _period_display(site)
    coords = _coord_display(site.get("lat"), site.get("lon"))
    description = (site.get("description") or "").strip()

    paragraphs = "\n".join(
        f"<p>{escape(p.strip())}</p>" for p in description.split("\n") if p.strip()
    )

    image = related.get("image")
    hero_html = ""
    og_image = None
    if image:
        og_image = f"{BASE_URL}{image['url']}"
        credit = " · ".join(escape(b) for b in [image.get("author"), image.get("license")] if b)
        if image.get("commons_url"):
            credit = (
                f'<a href="{escape(image["commons_url"])}" target="_blank" rel="noopener">'
                f"{credit or 'Wikimedia Commons'}</a>"
            )
        hero_html = (
            f'<figure><img src="{escape(image["url"])}" alt="{escape(name)}" loading="lazy">'
            f"{f'<figcaption>{credit}</figcaption>' if credit else ''}</figure>"
        )

    rows = [("Type", escape(site_type))]
    if period:
        rows.append(("Period", escape(period)))
    rows.append(("Country", f'<a href="{escape(country_path(country))}">{escape(country)}</a>'))
    if coords:
        rows.append(("Coordinates", coords))
    if related.get("parent"):
        p = related["parent"]
        rows.append(("Part of", f'<a href="{escape(p["path"])}">{escape(p["name"])}</a>'))
    facts = "\n".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows)

    alt_names = [n for n in related.get("alt_names", []) if n and n != name]
    alt_html = (
        f"<p><strong>Also known as:</strong> {escape(', '.join(alt_names[:12]))}</p>"
        if alt_names
        else ""
    )

    news_html = ""
    if related.get("news"):
        items = "\n".join(
            f'<li><a href="/news-archive/{escape(encode_path(n["slug"]))}">{escape(n["headline"])}</a></li>'
            for n in related["news"][:10]
        )
        news_html = f"<h2>Stories about {escape(name)}</h2><ul>{items}</ul>"

    links_html = ""
    links = [link for link in related.get("links", []) if link.get("url")]
    if links:
        items = "\n".join(
            f'<li><a href="{escape(link["url"])}" target="_blank" rel="noopener">'
            f"{escape(link.get('title') or link['url'])}</a></li>"
            for link in links[:15]
        )
        links_html = f"<h2>Related resources</h2><ul>{items}</ul>"

    siblings_html = ""
    if related.get("siblings"):
        links_ = " &middot; ".join(
            f'<a href="{escape(s["path"])}">{escape(s["name"])}</a>'
            for s in related["siblings"][:24]
        )
        siblings_html = (
            f"<h2>More sites in {escape(country)}</h2><p>{links_}</p>"
            f'<p><a href="{escape(country_path(country))}">All sites in {escape(country)} →</a></p>'
        )

    place = [
        '"@type": "Place"',
        f'"name": {_json_str(name)}',
        f'"url": "{canonical}"',
        f'"address": {{"@type": "PostalAddress", "addressCountry": {_json_str(country)}}}',
    ]
    if description:
        place.append(f'"description": {_json_str(description[:500])}')
    if site.get("lat") is not None and site.get("lon") is not None:
        place.append(
            f'"geo": {{"@type": "GeoCoordinates", "latitude": {site["lat"]}, '
            f'"longitude": {site["lon"]}}}'
        )
    if og_image:
        place.append(f'"image": "{og_image}"')

    crumb_parts = [
        ("Home", f"{BASE_URL}/"),
        ("Sites", f"{BASE_URL}/sites/"),
        (country, f"{BASE_URL}{encode_path(country_path(country))}"),
        (name, canonical),
    ]
    schema = (
        f'[{{"@context": "https://schema.org", {", ".join(place)}}}, '
        f"{_breadcrumb_schema(crumb_parts)}]"
    )

    meta_desc = description or f"{name}: {site_type.lower()} in {country}."
    head = _meta_head(
        title=f"{name} — {country} · {site_type}",
        description=meta_desc,
        canonical=canonical,
        og_type="place",
        image=og_image,
        schema=schema,
    )

    body = f"""<div class="an-ssr">
<nav class="an-crumb">{_crumbs(("Home", "/"), ("Sites", "/sites/"), (country, country_path(country)), (name, None))}</nav>
<h1>{escape(name)}</h1>
<div class="an-meta">{escape(site_type)}{f" &middot; {escape(period)}" if period else ""} &middot; {escape(country)}</div>
{hero_html}
{alt_html}
{paragraphs}
<table>{facts}</table>
<a class="an-cta" href="/globe.html?site={escape(str(site["id"]))}">Show on the interactive globe →</a>
{news_html}
{links_html}
{siblings_html}
</div>"""

    return SeoPage("site.html", head, body, _route_json("site", {"id": str(site["id"])}))


# --------------------------------------------------------------------------
# Research paper (/research/{slug}) and journal (/articles/{slug})
# --------------------------------------------------------------------------


def research_page(paper: dict, body_html: str) -> SeoPage:
    """One research paper. Body HTML is already rendered from markdown."""
    canonical = f"{BASE_URL}/research/{encode_path(paper['slug'])}"
    title = paper["title"]
    summary = (paper.get("summary") or "").strip()
    author = paper.get("author") or "Theo"
    pub_date, _ = _date_parts(paper.get("published_at"))

    # Theo is a pipeline, not a person — keep it an Organization in JSON-LD.
    author_schema = (
        '{"@type": "Organization", "name": "Ancient Nerds", "description": "AI research pipeline"}'
        if author == "Theo"
        else f'{{"@type": "Person", "name": {_json_str(author)}}}'
    )
    schema = (
        '{"@context": "https://schema.org", "@type": "ScholarlyArticle", '
        f'"headline": {_json_str(title)}, "description": {_json_str(summary[:300])}, '
        f'"datePublished": "{pub_date}", "author": {author_schema}, '
        '"license": "https://creativecommons.org/licenses/by/4.0/", '
        f'"mainEntityOfPage": "{canonical}", "url": "{canonical}"}}'
    )

    head = _meta_head(
        title=title,
        description=summary or title,
        canonical=canonical,
        og_type="article",
        image=paper.get("hero_image_url") or None,
        schema=schema,
    )

    body = f"""<div class="an-ssr">
<nav class="an-crumb">{_crumbs(("Home", "/"), ("Research", "/research/"), (title, None))}</nav>
<h1>{escape(title)}</h1>
<div class="an-meta">{escape(author)}{f" &middot; {pub_date}" if pub_date else ""} &middot; CC BY 4.0</div>
{AI_NOTICE_HTML}
{f"<p><strong>{escape(summary)}</strong></p>" if summary else ""}
{body_html}
<p><a href="/research/">← All research papers</a></p>
</div>"""

    return SeoPage("research.html", head, body, _route_json("research", {"slug": paper["slug"]}))


def research_index_page(papers: list[dict]) -> SeoPage:
    """The open-access research library listing."""
    canonical = f"{BASE_URL}/research/"
    cards = "\n".join(
        _link_card(f"/research/{encode_path(p['slug'])}", p["title"], p.get("summary"))
        for p in papers
    )
    head = _meta_head(
        title="Research Library",
        description=(
            f"{len(papers)} open-access archaeological research papers with full citations, "
            "published under CC BY 4.0."
        ),
        canonical=canonical,
    )
    body = f"""<div class="an-ssr">
<nav class="an-crumb">{_crumbs(("Home", "/"), ("Research", None))}</nav>
<h1>Research Library</h1>
<div class="an-meta">{len(papers)} open-access papers &middot; CC BY 4.0</div>
{AI_NOTICE_HTML}
{cards}
</div>"""
    return SeoPage("research.html", head, body, _route_json("researchIndex", {}))


def article_index_page(articles: list[dict]) -> SeoPage:
    """The weekly journal listing."""
    canonical = f"{BASE_URL}/articles/"
    cards = "\n".join(
        _link_card(f"/articles/{encode_path(a['slug'])}", a["title"], a.get("summary"))
        for a in articles
    )
    head = _meta_head(
        title="Weekly Archaeology Journal",
        description=(
            f"{len(articles)} weekly journals covering the biggest archaeological "
            "discoveries, each sourced and cited."
        ),
        canonical=canonical,
    )
    body = f"""<div class="an-ssr">
<nav class="an-crumb">{_crumbs(("Home", "/"), ("Journal", None))}</nav>
<h1>Weekly Archaeology Journal</h1>
<div class="an-meta">{len(articles)} issues</div>
{AI_NOTICE_HTML}
{cards}
</div>"""
    return SeoPage("articles.html", head, body, _route_json("articleIndex", {}))


def story_archive_page(stories: list[dict], page: int, total_pages: int, total: int) -> SeoPage:
    """
    The Story Archive listing.

    Named "stories", not "news": a video published this week routinely
    covers a find from decades ago, so dating them as news is wrong.
    """
    suffix = f" — page {page}" if page > 1 else ""
    canonical = f"{BASE_URL}/news-archive/" if page == 1 else f"{BASE_URL}/news-archive/page/{page}"

    cards = "\n".join(_story_card(s) for s in stories)

    nav_bits = []
    if page > 1:
        prev = "/news-archive/" if page == 2 else f"/news-archive/page/{page - 1}"
        nav_bits.append(f'<a href="{prev}">← Previous</a>')
    if page < total_pages:
        nav_bits.append(f'<a href="/news-archive/page/{page + 1}">Next →</a>')
    pager = f"<p>{' &middot; '.join(nav_bits)}</p>" if nav_bits else ""

    head = _meta_head(
        title=f"Story Archive{suffix}",
        description=(
            f"{total:,} archaeology stories from the Ancient Nerds video digest — "
            "excavations, dating results, and reinterpretations, each with its source."
        ),
        canonical=canonical,
    )
    body = f"""<div class="an-ssr">
<nav class="an-crumb">{_crumbs(("Home", "/"), ("Story Archive", None))}</nav>
<h1>Story Archive</h1>
<div class="an-meta">{total:,} stories{f" &middot; page {page} of {total_pages}" if total_pages > 1 else ""}</div>
{AI_NOTICE_HTML}
{cards}
{pager}
</div>"""
    return SeoPage(
        "story.html",
        head,
        body,
        _route_json(
            "storyArchive",
            {
                "page": page,
                "totalPages": total_pages,
                "total": total,
                "stories": [
                    {
                        "slug": s["slug"],
                        "headline": s["headline"],
                        "summary": (s.get("summary") or "")[:300],
                    }
                    for s in stories
                ],
            },
        ),
    )


def sites_index_page(countries: list[dict]) -> SeoPage:
    """Country index of curated sites."""
    total = sum(c["count"] for c in countries)
    canonical = f"{BASE_URL}/sites/"
    cards = "\n".join(
        f'<a class="an-card" href="{escape(country_path(c["name"]))}">'
        f"{escape(c['name'])} ({c['count']})</a>"
        for c in countries
    )
    head = _meta_head(
        title="Archaeological Sites by Country",
        description=(
            f"{total:,} curated archaeological sites across {len(countries)} countries: "
            "settlements, temples, tombs, megaliths and rock art, each with location and sources."
        ),
        canonical=canonical,
    )
    body = f"""<div class="an-ssr">
<nav class="an-crumb">{_crumbs(("Home", "/"), ("Sites", None))}</nav>
<h1>Archaeological Sites by Country</h1>
<div class="an-meta">{total:,} curated sites in {len(countries)} countries</div>
<div class="an-grid">{cards}</div>
</div>"""
    return SeoPage(
        "site.html",
        head,
        body,
        _route_json(
            "sitesIndex",
            {
                "countries": [
                    {"name": c["name"], "count": c["count"], "path": country_path(c["name"])}
                    for c in countries
                ]
            },
        ),
    )


def country_sites_page(country: str, sites: list[dict]) -> SeoPage:
    """All curated sites of one country."""
    canonical = f"{BASE_URL}{encode_path(country_path(country))}"
    rows = "\n".join(_link_card(s["path"], s["name"], s.get("description")) for s in sites)
    items = ", ".join(
        f'{{"@type": "ListItem", "position": {i}, "name": {_json_str(s["name"])}, '
        f'"url": "{BASE_URL}{encode_path(s["path"])}"}}'
        for i, s in enumerate(sites[:50], start=1)
    )
    schema = (
        '{"@context": "https://schema.org", "@type": "ItemList", '
        f'"name": {_json_str(f"Archaeological Sites in {country}")}, '
        f'"numberOfItems": {len(sites)}, "itemListElement": [{items}]}}'
    )
    head = _meta_head(
        title=f"Archaeological Sites in {country} ({len(sites)})",
        description=(
            f"{len(sites)} curated archaeological sites in {country}: settlements, temples, "
            "tombs and more — each with location, historical context and sources."
        ),
        canonical=canonical,
        schema=schema,
    )
    body = f"""<div class="an-ssr">
<nav class="an-crumb">{_crumbs(("Home", "/"), ("Sites", "/sites/"), (country, None))}</nav>
<h1>Archaeological Sites in {escape(country)}</h1>
<div class="an-meta">{len(sites)} curated sites</div>
{rows}
</div>"""
    return SeoPage(
        "site.html",
        head,
        body,
        _route_json(
            "country",
            {
                "country": country,
                "sites": [
                    {
                        "name": x["name"],
                        "path": x["path"],
                        "summary": (x.get("description") or "")[:200],
                    }
                    for x in sites
                ],
            },
        ),
    )


def article_page(article: dict, body_html: str) -> SeoPage:
    """One weekly journal issue."""
    canonical = f"{BASE_URL}/articles/{encode_path(article['slug'])}"
    title = article["title"]
    summary = (article.get("summary") or "").strip()
    pub_date, _ = _date_parts(article.get("published_at"))

    schema = (
        '{"@context": "https://schema.org", "@type": "Article", '
        f'"headline": {_json_str(title)}, "description": {_json_str(summary[:300])}, '
        f'"datePublished": "{pub_date}", '
        '"author": {"@type": "Organization", "name": "Ancient Nerds"}, '
        f'"mainEntityOfPage": "{canonical}", "url": "{canonical}"}}'
    )

    head = _meta_head(
        title=title,
        description=summary or title,
        canonical=canonical,
        og_type="article",
        image=article.get("hero_image_url") or None,
        schema=schema,
    )

    body = f"""<div class="an-ssr">
<nav class="an-crumb">{_crumbs(("Home", "/"), ("Journal", "/articles/"), (title, None))}</nav>
<h1>{escape(title)}</h1>
<div class="an-meta">{pub_date}</div>
{AI_NOTICE_HTML}
{f"<p><strong>{escape(summary)}</strong></p>" if summary else ""}
{body_html}
<p><a href="/articles/">← All journals</a></p>
</div>"""

    return SeoPage("articles.html", head, body, _route_json("article", {"slug": article["slug"]}))
