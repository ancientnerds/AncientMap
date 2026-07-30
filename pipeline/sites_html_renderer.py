"""
HTML rendering for the crawlable site browser (SEO pages).

Renders /sites/ (country index) and /sites/{country} (site listings) as
server-side HTML. These pages are the crawl path connecting search engines
to the ~5,000 curated site detail pages (/site.html?id=...), which serve
their own pre-rendered content to bots via /seo/site/.
"""

from html import escape

from pipeline.article_html_renderer import (
    _SHARED_CSS,
    BASE_URL,
    _footer_html,
    _json_str,
    _nav_html,
    slugify,
)

_SITES_CSS = """
    .country-grid {
        display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
        gap: 12px; margin-top: 24px;
    }
    .country-card {
        background: #0d2229; border: 1px solid #1a3a44; border-radius: 8px;
        padding: 14px 18px; display: flex; justify-content: space-between;
        align-items: center;
    }
    .country-card:hover { border-color: #c02023; }
    .country-card .count { color: #708890; font-size: 13px; }
    .site-row {
        background: #0d2229; border: 1px solid #1a3a44; border-radius: 8px;
        padding: 16px 20px; margin-bottom: 12px;
    }
    .site-row h3 { font-size: 1.15em; margin: 0 0 4px; }
    .site-row .site-meta { color: #708890; font-size: 13px; margin-bottom: 6px; }
    .site-row p { color: #b0b0b0; font-size: 0.95em; margin: 0; }
"""


def country_slug(country: str) -> str:
    """URL slug for a country name."""
    return slugify(country)


def render_sites_index_html(countries: list[dict]) -> str:
    """
    Render the country index page.

    countries: [{name, slug, count}] sorted by name.
    """
    total_sites = sum(c["count"] for c in countries)
    cards = "\n".join(
        f"""        <a class="country-card" href="/sites/{c["slug"]}">
            <span>{escape(c["name"])}</span><span class="count">{c["count"]}</span>
        </a>"""
        for c in countries
    )

    canonical = f"{BASE_URL}/sites/"
    schema = f"""{{
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "Browse Archaeological Sites by Country",
        "description": "Curated archaeological sites in {len(countries)} countries — settlements, temples, tombs, megaliths, and more.",
        "url": "{canonical}",
        "publisher": {{"@type": "Organization", "name": "Ancient Nerds", "url": "{BASE_URL}"}}
    }}"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Browse Archaeological Sites by Country | Ancient Nerds</title>
    <meta name="description" content="Explore {total_sites:,} curated archaeological sites across {len(countries)} countries: settlements, temples, tombs, megaliths, rock art, and more — each with location, description, and sources.">
    <meta name="robots" content="index, follow, max-image-preview:large">
    <link rel="canonical" href="{canonical}">

    <meta property="og:type" content="website">
    <meta property="og:url" content="{canonical}">
    <meta property="og:site_name" content="Ancient Nerds">
    <meta property="og:title" content="Browse Archaeological Sites by Country | Ancient Nerds">
    <meta property="og:description" content="Explore {total_sites:,} curated archaeological sites across {len(countries)} countries.">
    <meta property="og:image" content="{BASE_URL}/landing/og-image.png">

    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Browse Archaeological Sites by Country | Ancient Nerds">
    <meta name="twitter:description" content="Explore {total_sites:,} curated archaeological sites across {len(countries)} countries.">
    <meta name="twitter:image" content="{BASE_URL}/landing/og-image.png">
    <meta name="twitter:site" content="@AncientNerdsDAO">

    <link rel="icon" type="image/svg+xml" href="/favicon.svg">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500;600&family=Orbitron:wght@700&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">

    <script type="application/ld+json">{schema}</script>
    <style>{_SHARED_CSS}{_SITES_CSS}</style>
</head>
<body>
    {_nav_html()}
    <main class="wide-container">
        <h1>Archaeological Sites by Country</h1>
        <p class="meta">{total_sites:,} curated sites from the Ancient Nerds Originals collection.
        For the full index of 750,000+ sites, use the <a href="/search.html">site search</a>
        or the <a href="/globe.html">interactive 3D globe</a>.</p>
        <div class="country-grid">
{cards}
        </div>
    </main>
    {_footer_html()}
</body>
</html>"""


def render_country_sites_html(country: str, slug: str, sites: list[dict]) -> str:
    """
    Render the site listing for one country.

    sites: [{id, name, site_type, period_name, description}] sorted by name.
    """
    e_country = escape(country)
    rows = []
    item_schemas = []
    for s in sites:
        e_name = escape(s["name"])
        site_url = f"/site.html?id={s['id']}"
        meta_bits = " &middot; ".join(
            escape(b) for b in [s.get("site_type") or "", s.get("period_name") or ""] if b
        )
        desc = (s.get("description") or "").strip()
        if len(desc) > 200:
            desc = desc[:200].rsplit(" ", 1)[0] + "…"

        rows.append(f"""
        <div class="site-row">
            <h3><a href="{site_url}">{e_name}</a></h3>
            {f'<div class="site-meta">{meta_bits}</div>' if meta_bits else ""}
            {f"<p>{escape(desc)}</p>" if desc else ""}
        </div>""")
        item_schemas.append(
            f'{{"@type": "ListItem", "name": {_json_str(s["name"])}, '
            f'"url": "{BASE_URL}{site_url}"}}'
        )

    rows_html = "\n".join(rows) if rows else "<p>No curated sites for this country yet.</p>"

    canonical = f"{BASE_URL}/sites/{slug}"
    schema_items = ", ".join(item_schemas[:50])  # Limit schema size
    schema = f"""{{
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "Archaeological Sites in {_json_str(country)[1:-1]}",
        "url": "{canonical}",
        "numberOfItems": {len(sites)},
        "itemListElement": [{schema_items}]
    }}"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Archaeological Sites in {e_country} ({len(sites)}) | Ancient Nerds</title>
    <meta name="description" content="{len(sites)} curated archaeological sites in {e_country}: settlements, temples, tombs, and more — each with location, historical context, and sources.">
    <meta name="robots" content="index, follow, max-image-preview:large">
    <link rel="canonical" href="{canonical}">

    <meta property="og:type" content="website">
    <meta property="og:url" content="{canonical}">
    <meta property="og:site_name" content="Ancient Nerds">
    <meta property="og:title" content="Archaeological Sites in {e_country} | Ancient Nerds">
    <meta property="og:description" content="{len(sites)} curated archaeological sites in {e_country} with locations, descriptions, and sources.">
    <meta property="og:image" content="{BASE_URL}/landing/og-image.png">

    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Archaeological Sites in {e_country} | Ancient Nerds">
    <meta name="twitter:description" content="{len(sites)} curated archaeological sites in {e_country}.">
    <meta name="twitter:image" content="{BASE_URL}/landing/og-image.png">
    <meta name="twitter:site" content="@AncientNerdsDAO">

    <link rel="icon" type="image/svg+xml" href="/favicon.svg">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500;600&family=Orbitron:wght@700&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">

    <script type="application/ld+json">{schema}</script>
    <style>{_SHARED_CSS}{_SITES_CSS}</style>
</head>
<body>
    {_nav_html()}
    <main class="wide-container">
        <h1>Archaeological Sites in {e_country}</h1>
        <p class="meta">{len(sites)} curated sites &middot; <a href="/sites/">All countries</a>
        &middot; <a href="/search.html">Search all 750K+ sites</a>
        &middot; <a href="/globe.html">View on the 3D globe</a></p>
        {rows_html}
    </main>
    {_footer_html()}
</body>
</html>"""
