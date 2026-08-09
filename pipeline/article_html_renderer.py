"""
HTML rendering utilities for SEO-friendly article and news pages.

Converts NewsArticle DB records into full HTML pages with schema markup,
proper meta tags, and styling matching the site's dark theme.
"""

import re
from datetime import datetime
from html import escape

import markdown  # noqa: I001 — third-party, separated intentionally
import nh3

BASE_URL = "https://ancientnerds.com"

# Mirrored in ancient-nerds-map/src/constants/brand.ts — the React pages need
# the same value and cannot import from Python. Until 2026-08-09 this link
# appeared on none of the 7,404 indexed pages, which is where search traffic
# actually lands.
DISCORD_INVITE_URL = "https://discord.gg/8bAjKKCue4"


def _sanitize_html(html: str) -> str:
    """Allowlist-sanitize Markdown output (nh3/ammonia).

    Replaces the old regex blocklist, which was bypassable: it only stripped
    *quoted* event handlers, so `<img src=x onerror=alert(1)>`,
    `<svg onload=...>`, `<details ontoggle=...>` and `javascript:` hrefs all
    passed through into public pages (audit 2026-08-05). Runs BEFORE
    external_links_new_tab so the added target/rel attributes survive.
    """
    return nh3.clean(html)


_A_TAG_RE = re.compile(r"<a\s+[^>]*>")
_EXT_HREF_RE = re.compile(r'href="https?://(?!(?:www\.)?ancientnerds\.com)')


def external_links_new_tab(html: str) -> str:
    """Make external links open in a new tab; internal links stay in-tab."""

    def fix(m: re.Match) -> str:
        tag = m.group(0)
        if not _EXT_HREF_RE.search(tag) or "target=" in tag:
            return tag
        attrs = (
            ' target="_blank"' if "rel=" in tag else ' target="_blank" rel="noopener noreferrer"'
        )
        return tag[:-1] + attrs + ">"

    return _A_TAG_RE.sub(fix, html)


# Shared CSS for all rendered pages (dark theme matching main site)
_SHARED_CSS = """
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        background: #0a1a1f; color: #d0d0d0;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        line-height: 1.7; font-size: 17px;
    }
    a { color: #c02023; text-decoration: none; }
    a:hover { text-decoration: underline; }

    /* Navigation */
    .nav {
        background: #0d2229; border-bottom: 1px solid #1a3a44;
        padding: 14px 24px; display: flex; align-items: center;
        gap: 24px; flex-wrap: wrap;
    }
    .nav-brand {
        font-family: 'Orbitron', monospace; font-weight: 700;
        font-size: 18px; color: #c02023; letter-spacing: 1px;
    }
    .nav a { color: #a0b0b8; font-size: 14px; }
    .nav a:hover { color: #fff; text-decoration: none; }

    /* Main content area */
    .container { max-width: 800px; margin: 0 auto; padding: 40px 24px 80px; }
    .wide-container { max-width: 1000px; margin: 0 auto; padding: 40px 24px 80px; }

    /* Headings */
    h1, h2, h3, h4 { font-family: 'Cormorant Garamond', Georgia, serif; color: #fff; }
    h1 { font-size: 2.4em; line-height: 1.2; margin-bottom: 16px; }
    h2 { font-size: 1.8em; margin-top: 40px; margin-bottom: 12px; border-bottom: 1px solid #1a3a44; padding-bottom: 8px; }
    h3 { font-size: 1.4em; margin-top: 28px; margin-bottom: 8px; }

    /* Article body */
    .article-body p { margin-bottom: 16px; }
    .article-body ul, .article-body ol { margin: 12px 0 16px 24px; }
    .article-body li { margin-bottom: 6px; }
    .article-body blockquote {
        border-left: 3px solid #c02023; padding: 12px 20px;
        margin: 16px 0; background: #0d2229; border-radius: 0 6px 6px 0;
        font-style: italic; color: #b0b0b0;
    }
    .article-body code { background: #132830; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }
    .article-body strong { color: #e8e8e8; }

    /* Meta info */
    .meta { color: #708890; font-size: 14px; margin-bottom: 32px; }
    .meta time { color: #90a8b0; }

    /* Article cards (listing page) */
    .article-card {
        background: #0d2229; border: 1px solid #1a3a44; border-radius: 8px;
        padding: 24px; margin-bottom: 20px; transition: border-color 0.2s;
    }
    .article-card:hover { border-color: #c02023; }
    .article-card h2 { font-size: 1.5em; margin: 0 0 8px; border: none; padding: 0; }
    .article-card .meta { margin-bottom: 12px; }
    .article-card p { color: #b0b0b0; margin-bottom: 12px; }
    .article-card .read-more { font-weight: 500; }

    /* News archive items */
    .news-date-group { margin-top: 36px; }
    .news-date-group h2 { font-size: 1.3em; color: #90a8b0; }
    .news-item {
        background: #0d2229; border: 1px solid #1a3a44; border-radius: 8px;
        padding: 20px; margin-bottom: 14px;
    }
    .news-item h3 { font-size: 1.15em; margin: 0 0 6px; }
    .news-item .summary { color: #b0b0b0; margin-bottom: 10px; }
    .news-item .facts { margin: 8px 0 10px 18px; font-size: 0.95em; }
    .news-item .facts li { color: #90a8b0; margin-bottom: 4px; }
    .news-item .site-tag {
        display: inline-block; background: #132830; color: #c02023;
        padding: 2px 10px; border-radius: 12px; font-size: 13px; margin-right: 8px;
    }
    .news-item .source-link { font-size: 13px; color: #708890; }

    /* Copy link button */
    .copy-link-btn {
        background: #1a3a44; color: #c02023; border: 1px solid #2a4a54;
        padding: 2px 10px; border-radius: 4px; font-size: 13px;
        cursor: pointer; font-family: inherit; vertical-align: middle;
    }
    .copy-link-btn:hover { background: #2a4a54; }
    .copy-ok { display: none; color: #4a9; font-size: 13px; margin-left: 4px; }

    /* Footer */
    .footer {
        border-top: 1px solid #1a3a44; padding: 24px;
        text-align: center; color: #506870; font-size: 13px; margin-top: 40px;
    }

    /* Pagination */
    .pagination {
        display: flex; justify-content: center; gap: 24px;
        margin-top: 40px; font-size: 15px;
    }
    .pagination .page-info { color: #708890; }

    /* Responsive */
    @media (max-width: 600px) {
        h1 { font-size: 1.8em; }
        .container, .wide-container { padding: 24px 16px 60px; }
    }
"""


def _first_image_url(content_md: str) -> str | None:
    """Extract the first markdown image URL from article content."""
    m = re.search(r"!\[.*?\]\((\S+?)\)", content_md)
    return m.group(1) if m else None


def markdown_to_html(content_md: str, *, toc: bool = True) -> str:
    """
    Markdown -> sanitized HTML with external links opened in a new tab.

    Single definition: article pages, research papers, Medium copies and
    the SEO fragments all render markdown the same way, so a sanitizer
    change cannot apply to some pages and miss others.
    """
    extensions = ["extra", "smarty", "toc"] if toc else ["extra", "smarty"]
    md = markdown.Markdown(extensions=extensions)
    return external_links_new_tab(_sanitize_html(md.convert(content_md)))


def slugify(title: str) -> str:
    """Generate URL-safe slug from article title."""
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = re.sub(r"^-|-$", "", slug)
    return slug[:120]


def story_slug(headline: str, item_id: int) -> str:
    """Stable, unique slug for a news story: headline slug + numeric ID suffix."""
    return f"{slugify(headline)}-{item_id}"


def story_id_from_slug(slug: str) -> int | None:
    """Extract the numeric NewsItem ID from a story slug, or None if malformed."""
    tail = slug.rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() else None


def _nav_html() -> str:
    """Shared navigation header."""
    return """
    <nav class="nav">
        <a href="/" class="nav-brand">ANCIENT NERDS</a>
        <a href="/globe.html">Globe</a>
        <a href="/news.html">News</a>
        <a href="/articles/">Journal</a>
        <a href="/news-archive/">News Archive</a>
        <a href="/research/">Research</a>
        <a href="/sites/">Sites</a>
        <a href="/radar.html">Radar</a>
    </nav>"""


def founder_medium_script(medium_path: str) -> str:
    """
    JS that injects the "Copy for Medium" link into #mediumSlot — a
    founders-only editorial tool, shown only when /api/auth/me reports
    is_founder for the logged-in user.
    """
    return f"""
    <script>
    (function() {{
        var token = localStorage.getItem("an_auth_token");
        if (!token) return;
        fetch("/api/auth/me", {{ headers: {{ "Authorization": "Bearer " + token }} }})
            .then(function(r) {{ return r.ok ? r.json() : null; }})
            .then(function(user) {{
                if (user && user.is_founder) {{
                    document.getElementById("mediumSlot").innerHTML =
                        ' &middot; <a href="{medium_path}" style="color:#c02023">Copy for Medium</a>';
                }}
            }});
    }})();
    </script>"""


def _footer_html() -> str:
    """Shared footer."""
    return """
    <footer class="footer">
        <p>&copy; 2024-2026 Ancient Nerds &mdash;
        <a href="/">Home</a> &middot;
        <a href="/globe.html">Interactive Globe</a> &middot;
        <a href="/articles/">Journal</a> &middot;
        <a href="/news-archive/">News Archive</a> &middot;
        <a href="/research/">Research Papers</a> &middot;
        <a href="/sites/">Browse Sites</a> &middot;
        <a href="/api.html">API</a></p>
    </footer>"""


# Art. 50(4) EU AI Act: visible disclosure on every AI-generated content page.
# The data attribute doubles as a lightweight machine-readable marker.
AI_NOTICE_HTML = (
    '<p class="ai-notice" data-ai-generated="true" '
    'style="border:1px solid rgba(176,141,87,.45);background:rgba(176,141,87,.1);'
    'padding:8px 12px;border-radius:6px;font-size:.85em;">'
    "AI-generated text: the text on this page was produced automatically by an AI "
    "system. Images are from the original sources, not AI-generated. "
    "Always verify with the original sources.</p>"
)


def render_article_html(
    title: str,
    content_md: str,
    summary: str | None,
    published_at: datetime | None,
    week_start: datetime | None,
    week_end: datetime | None,
    slug: str,
) -> str:
    """Render a single article as a full SEO-optimized HTML page."""
    md = markdown.Markdown(extensions=["extra", "smarty", "toc"])
    body_html = external_links_new_tab(_sanitize_html(md.convert(content_md)))

    meta_desc = (summary or title)[:160]
    pub_date = published_at.strftime("%Y-%m-%d") if published_at else ""
    pub_display = published_at.strftime("%B %d, %Y") if published_at else ""

    date_range = ""
    if week_start and week_end:
        date_range = f"{week_start.strftime('%b %d')} &ndash; {week_end.strftime('%b %d, %Y')}"

    canonical = f"{BASE_URL}/articles/{slug}"
    og_image = escape(_first_image_url(content_md) or f"{BASE_URL}/landing/og-image.png")
    e_title = escape(title)
    e_desc = escape(meta_desc)

    # Article schema (JSON-LD)
    schema = f"""{{
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": {_json_str(title)},
        "description": {_json_str(meta_desc)},
        "datePublished": "{pub_date}",
        "author": {{"@type": "Organization", "name": "Ancient Nerds", "url": "{BASE_URL}"}},
        "publisher": {{"@type": "Organization", "name": "Ancient Nerds", "url": "{BASE_URL}", "logo": {{"@type": "ImageObject", "url": "{BASE_URL}/landing/og-image.png"}}}},
        "image": "{og_image}",
        "mainEntityOfPage": "{canonical}",
        "url": "{canonical}"
    }}"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{e_title} | Ancient Nerds</title>
    <meta name="description" content="{e_desc}">
    <meta name="robots" content="index, follow, max-image-preview:large">
    <link rel="canonical" href="{canonical}">

    <meta property="og:type" content="article">
    <meta property="og:url" content="{canonical}">
    <meta property="og:site_name" content="Ancient Nerds">
    <meta property="og:title" content="{e_title}">
    <meta property="og:description" content="{e_desc}">
    <meta property="og:image" content="{og_image}">
    <meta property="article:published_time" content="{pub_date}">

    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{e_title}">
    <meta name="twitter:description" content="{e_desc}">
    <meta name="twitter:image" content="{og_image}">
    <meta name="twitter:site" content="@AncientNerdsDAO">

    <link rel="icon" type="image/svg+xml" href="/favicon.svg">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500;600&family=Orbitron:wght@700&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">

    <script type="application/ld+json">{schema}</script>
    <style>{_SHARED_CSS}</style>
</head>
<body>
    {_nav_html()}
    <main class="container">
        <article>
            <h1>{e_title}</h1>
            <div class="meta">
                {f'<time datetime="{pub_date}">{pub_display}</time>' if pub_date else ""}
                {f" &middot; Week of {date_range}" if date_range else ""}
                &middot; <a href="/articles/">All Journals</a><span id="mediumSlot"></span>
                &middot; <button onclick="copyLink()" class="copy-link-btn" title="Copy shareable link">Copy Link</button>
                <span class="copy-ok" id="copyOk">Copied!</span>
            </div>
            {AI_NOTICE_HTML}
            <div class="article-body">
                {body_html}
            </div>
        </article>
    </main>
    {_footer_html()}
    <script>
    function copyLink() {{
        navigator.clipboard.writeText("{canonical}").then(function() {{
            var el = document.getElementById("copyOk");
            el.style.display = "inline";
            setTimeout(function() {{ el.style.display = "none"; }}, 2000);
        }});
    }}
    </script>
    {founder_medium_script(f"/articles/{slug}/medium")}
</body>
</html>"""


def render_article_listing_html(
    articles: list[dict],
) -> str:
    """
    Render article listing page.

    Each dict in articles: {title, summary, slug, published_at (str), week_start, week_end}
    """
    cards = []
    for a in articles:
        e_title = escape(a["title"])
        e_summary = escape(a.get("summary") or "")
        slug = a["slug"]
        pub = a.get("published_at", "")
        pub_display = ""
        if pub:
            try:
                pub_display = datetime.fromisoformat(pub).strftime("%B %d, %Y")
            except (ValueError, TypeError):
                pub_display = pub

        article_url = f"{BASE_URL}/articles/{slug}"
        cards.append(f"""
        <div class="article-card">
            <h2><a href="/articles/{slug}">{e_title}</a></h2>
            <div class="meta"><time datetime="{pub}">{pub_display}</time></div>
            <p>{e_summary}</p>
            <a href="/articles/{slug}" class="read-more">Read full journal &rarr;</a>
            <div style="margin-top:8px;font-size:13px;color:#506870">
                Share: <code style="background:#132830;padding:2px 8px;border-radius:3px;user-select:all;color:#90a8b0">{article_url}</code>
            </div>
        </div>""")

    cards_html = "\n".join(cards) if cards else "<p>No journals published yet. Check back soon!</p>"

    canonical = f"{BASE_URL}/articles/"
    schema = f"""{{
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "Weekly Archaeology Journal",
        "description": "In-depth weekly journal covering the biggest archaeological discoveries worldwide.",
        "url": "{canonical}",
        "publisher": {{"@type": "Organization", "name": "Ancient Nerds", "url": "{BASE_URL}"}}
    }}"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Weekly Archaeology Journal | Ancient Nerds</title>
    <meta name="description" content="In-depth weekly journal covering the biggest archaeological discoveries. Deep dives into new excavations, lost civilizations, and breakthroughs in ancient history research.">
    <meta name="robots" content="index, follow, max-image-preview:large">
    <link rel="canonical" href="{canonical}">

    <meta property="og:type" content="website">
    <meta property="og:url" content="{canonical}">
    <meta property="og:site_name" content="Ancient Nerds">
    <meta property="og:title" content="Weekly Archaeology Journal | Ancient Nerds">
    <meta property="og:description" content="In-depth weekly journal covering the biggest archaeological discoveries worldwide.">
    <meta property="og:image" content="{BASE_URL}/landing/og-image.png">

    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Weekly Archaeology Articles | Ancient Nerds">
    <meta name="twitter:description" content="In-depth weekly articles covering the biggest archaeological discoveries worldwide.">
    <meta name="twitter:image" content="{BASE_URL}/landing/og-image.png">
    <meta name="twitter:site" content="@AncientNerdsDAO">

    <link rel="icon" type="image/svg+xml" href="/favicon.svg">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500;600&family=Orbitron:wght@700&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">

    <script type="application/ld+json">{schema}</script>
    <style>{_SHARED_CSS}</style>
</head>
<body>
    {_nav_html()}
    <main class="container">
        <h1>Weekly Archaeology Articles</h1>
        <p class="meta">In-depth deep dives into the biggest archaeological discoveries each week. AI-written, sourced, and cited.</p>
        {AI_NOTICE_HTML}
        {cards_html}
    </main>
    {_footer_html()}
</body>
</html>"""


def render_news_archive_html(
    items_by_date: list[tuple[str, list[dict]]],
    total_count: int,
    page: int = 1,
    total_pages: int = 1,
) -> str:
    """
    Render one page of the news archive listing.

    items_by_date: list of (date_label, [item_dicts]) grouped by date.
    Each item dict: {id, headline, summary, facts, site_name, site_id,
    video_title, youtube_url}
    """
    groups_html = []
    item_schemas = []

    for date_label, items in items_by_date:
        item_cards = []
        for item in items:
            e_headline = escape(item["headline"])
            e_summary = escape(item.get("summary") or "")
            site_name = item.get("site_name") or ""
            site_id = item.get("site_id") or ""
            youtube_url = item.get("youtube_url") or ""
            video_title = escape(item.get("video_title") or "")
            slug = story_slug(item["headline"], item["id"])

            facts_html = ""
            if item.get("facts"):
                facts_li = "".join(f"<li>{escape(f)}</li>" for f in item["facts"][:5])
                facts_html = f'<ul class="facts">{facts_li}</ul>'

            # Internal site link first, external video source second
            site_tag = ""
            if site_name and site_id:
                site_tag = f'<a href="/site.html?id={escape(str(site_id))}" class="site-tag">{escape(site_name)}</a>'
            elif site_name:
                site_tag = f'<span class="site-tag">{escape(site_name)}</span>'
            source = (
                f'<a href="{escape(youtube_url)}" class="source-link" target="_blank" rel="noopener">From: {video_title}</a>'
                if youtube_url
                else ""
            )

            item_cards.append(f"""
            <div class="news-item">
                <h3><a href="/news-archive/{slug}">{e_headline}</a></h3>
                <p class="summary">{e_summary}</p>
                {facts_html}
                <div>{site_tag}{source}
                &middot; <a href="/news-archive/{slug}">Full story &rarr;</a></div>
            </div>""")

            item_schemas.append(
                f'{{"@type": "ListItem", "name": {_json_str(item["headline"])}, '
                f'"url": "{BASE_URL}/news-archive/{slug}"}}'
            )

        groups_html.append(f"""
        <div class="news-date-group">
            <h2>{escape(date_label)}</h2>
            {"".join(item_cards)}
        </div>""")

    body_html = (
        "\n".join(groups_html) if groups_html else "<p>No news items yet. Check back soon!</p>"
    )

    # Pagination nav: page 1 lives at /news-archive/, later pages at /news-archive/page/N
    def _page_url(n: int) -> str:
        return "/news-archive/" if n <= 1 else f"/news-archive/page/{n}"

    pagination_html = ""
    if total_pages > 1:
        newer = f'<a href="{_page_url(page - 1)}">&larr; Newer</a>' if page > 1 else "<span></span>"
        older = (
            f'<a href="{_page_url(page + 1)}">Older &rarr;</a>'
            if page < total_pages
            else "<span></span>"
        )
        pagination_html = f"""
        <nav class="pagination">
            {newer}
            <span class="page-info">Page {page} of {total_pages}</span>
            {older}
        </nav>"""

    canonical = f"{BASE_URL}{_page_url(page)}"
    schema_items = ", ".join(item_schemas[:50])  # Limit schema size
    schema = f"""{{
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "Archaeology News Archive",
        "description": "Latest archaeological discoveries, excavation updates, and ancient history research news.",
        "url": "{canonical}",
        "numberOfItems": {total_count},
        "itemListElement": [{schema_items}]
    }}"""

    page_suffix = f" - Page {page}" if page > 1 else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Archaeology News Archive - Latest Discoveries{page_suffix} | Ancient Nerds</title>
    <meta name="description" content="Archive of {total_count}+ archaeology news items. Excavation updates, ancient civilization discoveries, and research breakthroughs curated from expert YouTube channels.">
    <meta name="robots" content="index, follow, max-image-preview:large">
    <link rel="canonical" href="{canonical}">

    <meta property="og:type" content="website">
    <meta property="og:url" content="{canonical}">
    <meta property="og:site_name" content="Ancient Nerds">
    <meta property="og:title" content="Archaeology News Archive | Ancient Nerds">
    <meta property="og:description" content="Archive of {total_count}+ archaeology news items. Latest discoveries, excavations, and research breakthroughs.">
    <meta property="og:image" content="{BASE_URL}/landing/og-image.png">

    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Archaeology News Archive | Ancient Nerds">
    <meta name="twitter:description" content="Archive of {total_count}+ archaeology news items. Latest discoveries and research breakthroughs.">
    <meta name="twitter:image" content="{BASE_URL}/landing/og-image.png">
    <meta name="twitter:site" content="@AncientNerdsDAO">

    <link rel="icon" type="image/svg+xml" href="/favicon.svg">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500;600&family=Orbitron:wght@700&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">

    <script type="application/ld+json">{schema}</script>
    <style>{_SHARED_CSS}</style>
</head>
<body>
    {_nav_html()}
    <main class="wide-container">
        <h1>Archaeology News Archive</h1>
        {AI_NOTICE_HTML}
        <p class="meta">{total_count} news items curated from expert archaeology YouTube channels.
        For the interactive experience, visit the <a href="/news.html">live news feed</a>.</p>
        {body_html}
        {pagination_html}
    </main>
    {_footer_html()}
</body>
</html>"""


def render_story_html(story: dict) -> str:
    """
    Render a single news story as a full SEO-optimized HTML page.

    story: {id, headline, summary, facts, post_text, site_name, site_id,
    screenshot_url, youtube_url, video_title, channel_name, published_at
    (datetime|None), news_category}
    """
    slug = story_slug(story["headline"], story["id"])
    canonical = f"{BASE_URL}/news-archive/{slug}"
    e_headline = escape(story["headline"])
    e_summary = escape(story.get("summary") or "")
    meta_desc = escape((story.get("summary") or story["headline"])[:160])

    published_at = story.get("published_at")
    pub_date = published_at.strftime("%Y-%m-%d") if published_at else ""
    pub_display = published_at.strftime("%B %d, %Y") if published_at else ""

    screenshot = story.get("screenshot_url") or ""
    if screenshot.startswith("/"):
        screenshot = f"{BASE_URL}{screenshot}"
    og_image = escape(screenshot or f"{BASE_URL}/landing/og-image.png")

    # Body text: post_text is plain text — render as escaped paragraphs
    post_text = story.get("post_text") or ""
    paragraphs = "\n".join(
        f"<p>{escape(p.strip())}</p>" for p in post_text.split("\n") if p.strip()
    )

    facts_html = ""
    if story.get("facts"):
        facts_li = "".join(f"<li>{escape(f)}</li>" for f in story["facts"])
        facts_html = f'<h2>Key Facts</h2><ul class="facts">{facts_li}</ul>'

    site_html = ""
    if story.get("site_name") and story.get("site_id"):
        site_url = f"/site.html?id={escape(str(story['site_id']))}"
        site_html = (
            f'<p>Related site: <a href="{site_url}" class="site-tag">'
            f"{escape(story['site_name'])}</a> &mdash; view location, images, and "
            f'history on the <a href="{site_url}">Ancient Nerds map</a>.</p>'
        )

    source_html = ""
    if story.get("youtube_url"):
        channel = escape(story.get("channel_name") or "")
        video_title = escape(story.get("video_title") or "the source video")
        by_channel = f" by {channel}" if channel else ""
        source_html = (
            f'<p class="source-link">Source: <a href="{escape(story["youtube_url"])}" '
            f'target="_blank" rel="noopener">{video_title}</a>{by_channel}</p>'
        )

    category = story.get("news_category") or ""
    category_html = f'<span class="site-tag">{escape(category)}</span> ' if category else ""

    schema = f"""{{
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": {_json_str(story["headline"])},
        "description": {_json_str((story.get("summary") or "")[:300])},
        "datePublished": "{pub_date}",
        "image": "{og_image}",
        "author": {{"@type": "Organization", "name": "Ancient Nerds", "url": "{BASE_URL}"}},
        "publisher": {{"@type": "Organization", "name": "Ancient Nerds", "url": "{BASE_URL}", "logo": {{"@type": "ImageObject", "url": "{BASE_URL}/landing/og-image.png"}}}},
        "mainEntityOfPage": "{canonical}",
        "url": "{canonical}"
    }}"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{e_headline} | Ancient Nerds</title>
    <meta name="description" content="{meta_desc}">
    <meta name="robots" content="index, follow, max-image-preview:large">
    <link rel="canonical" href="{canonical}">

    <meta property="og:type" content="article">
    <meta property="og:url" content="{canonical}">
    <meta property="og:site_name" content="Ancient Nerds">
    <meta property="og:title" content="{e_headline}">
    <meta property="og:description" content="{meta_desc}">
    <meta property="og:image" content="{og_image}">
    <meta property="article:published_time" content="{pub_date}">

    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{e_headline}">
    <meta name="twitter:description" content="{meta_desc}">
    <meta name="twitter:image" content="{og_image}">
    <meta name="twitter:site" content="@AncientNerdsDAO">

    <link rel="icon" type="image/svg+xml" href="/favicon.svg">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500;600&family=Orbitron:wght@700&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">

    <script type="application/ld+json">{schema}</script>
    <style>{_SHARED_CSS}</style>
</head>
<body>
    {_nav_html()}
    <main class="container">
        <article>
            <h1>{e_headline}</h1>
            <div class="meta">
                {category_html}{f'<time datetime="{pub_date}">{pub_display}</time>' if pub_date else ""}
                &middot; <a href="/news-archive/">News Archive</a>
                &middot; <a href="/news.html">Live Feed</a>
            </div>
            {AI_NOTICE_HTML}
            <div class="article-body">
                <p><strong>{e_summary}</strong></p>
                {paragraphs}
                {facts_html}
                {site_html}
                {source_html}
            </div>
        </article>
    </main>
    {_footer_html()}
</body>
</html>"""


def render_medium_copy_html(
    title: str,
    content_md: str,
    canonical_url: str,
    extra_footer_html: str = "",
) -> str:
    """Render a clean, light-themed page for copying into Medium's editor."""
    md = markdown.Markdown(extensions=["extra", "smarty"])
    body_html = external_links_new_tab(_sanitize_html(md.convert(content_md)))
    canonical = canonical_url
    e_title = escape(title)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Copy for Medium: {e_title}</title>
    <meta name="robots" content="noindex">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ background: #f8f8f8; color: #333; font-family: Georgia, serif; line-height: 1.8; font-size: 18px; }}
        .toolbar {{
            position: sticky; top: 0; z-index: 10;
            background: #1a1a2e; color: #fff; padding: 14px 24px;
            display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
        }}
        .toolbar h2 {{ font-size: 15px; font-family: sans-serif; font-weight: 400; opacity: 0.7; }}
        .toolbar button {{
            background: #c02023; color: #fff; border: none; padding: 8px 20px;
            border-radius: 4px; font-size: 14px; cursor: pointer; font-family: sans-serif;
        }}
        .toolbar button:hover {{ background: #e02525; }}
        .toolbar .canonical {{
            font-family: monospace; font-size: 13px; background: #2a2a4a;
            padding: 6px 12px; border-radius: 4px; user-select: all; color: #8f8;
        }}
        .toolbar .status {{ font-size: 13px; font-family: sans-serif; color: #8f8; display: none; }}
        #article {{ max-width: 720px; margin: 40px auto; padding: 0 24px 80px; }}
        #article h1 {{ font-size: 2.2em; margin-bottom: 12px; color: #111; }}
        #article h2 {{ font-size: 1.6em; margin-top: 36px; margin-bottom: 10px; color: #222; }}
        #article h3 {{ font-size: 1.3em; margin-top: 28px; margin-bottom: 8px; color: #333; }}
        #article p {{ margin-bottom: 16px; }}
        #article ul, #article ol {{ margin: 12px 0 16px 28px; }}
        #article li {{ margin-bottom: 6px; }}
        #article blockquote {{
            border-left: 3px solid #c02023; padding: 12px 20px;
            margin: 16px 0; background: #f0f0f0; font-style: italic; color: #555;
        }}
        #article strong {{ color: #111; }}
        #article a {{ color: #c02023; }}
        #article hr {{ border: none; border-top: 1px solid #ddd; margin: 32px 0; }}
        .note {{
            max-width: 720px; margin: 0 auto 20px; padding: 0 24px;
            font-family: sans-serif; font-size: 13px; color: #888;
        }}
    </style>
</head>
<body>
    <div class="toolbar">
        <h2>Copy for Medium</h2>
        <button onclick="selectAndCopy()">Select All &amp; Copy</button>
        <span class="canonical">{canonical}</span>
        <span class="status" id="status">Copied!</span>
    </div>
    <p class="note">
        1. Click "Select All &amp; Copy" above &nbsp; 2. Open Medium &rarr; New Story &nbsp;
        3. Paste (Ctrl+V) &nbsp; 4. After publishing, set canonical URL to the green URL above
    </p>
    <div id="article">
        <h1>{e_title}</h1>
        {body_html}
        <hr>
        <p><em>Originally published on <a href="{canonical}">Ancient Nerds</a>
        &mdash; explore 750,000+ archaeological sites on our
        <a href="{BASE_URL}/globe.html">interactive 3D globe</a>.</em></p>
        {extra_footer_html}
    </div>
    <script>
    function selectAndCopy() {{
        const el = document.getElementById('article');
        const range = document.createRange();
        range.selectNodeContents(el);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
        document.execCommand('copy');
        const status = document.getElementById('status');
        status.style.display = 'inline';
        setTimeout(() => status.style.display = 'none', 2000);
    }}
    </script>
</body>
</html>"""


def render_404_html(what: str = "Page") -> str:
    """Render a styled 404 page."""
    what = escape(what)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{what} Not Found | Ancient Nerds</title>
    <meta name="robots" content="noindex">
    <link rel="icon" type="image/svg+xml" href="/favicon.svg">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600&family=Orbitron:wght@700&family=Inter:wght@400;500&display=swap" rel="stylesheet">
    <style>{_SHARED_CSS}</style>
</head>
<body>
    {_nav_html()}
    <main class="container" style="text-align:center; padding-top: 80px;">
        <h1 style="font-size: 3em; color: #c02023;">404</h1>
        <p style="font-size: 1.2em; margin: 20px 0;">{what} not found.</p>
        <p><a href="/articles/">Browse all articles</a> &middot; <a href="/news-archive/">News archive</a> &middot; <a href="/">Home</a></p>
    </main>
    {_footer_html()}
</body>
</html>"""


def _json_str(s: str) -> str:
    """Escape a string for safe JSON embedding inside a <script> tag.

    json.dumps alone does not escape "<" — an LLM-derived title containing
    "</script><script>" would break out of the JSON-LD block (audit
    2026-08-05).
    """
    import json

    return json.dumps(s, ensure_ascii=False).replace("<", "\\u003c")
