"""
HTML rendering for the crawlable site browser (SEO pages).

Renders /sites/ (country index), /sites/{country} (site listings) and
/sites/{country}/{slug} (site detail) as server-side HTML.

The detail pages are the canonical, crawlable form of a site. They serve
identical content to every user agent — unlike the legacy
/site.html?id={uuid} SPA shell, which only revealed its content to
crawlers via a nginx user-agent rewrite to /seo/site/. Google left those
5,000 parameter URLs on "Discovered - currently not indexed" and never
fetched them (verified via URL Inspection, 2026-08-07).
"""

import re
from html import escape
from urllib.parse import quote

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

_SITE_DETAIL_CSS = """
    .breadcrumb { color: #708890; font-size: 13px; margin-bottom: 18px; }
    .breadcrumb a { color: #8fa8b0; }
    .site-hero { margin: 0 0 24px; }
    .site-hero img {
        width: 100%; height: auto; border-radius: 8px; border: 1px solid #1a3a44;
    }
    .site-hero figcaption { color: #708890; font-size: 12px; margin-top: 6px; }
    .fact-table { width: 100%; border-collapse: collapse; margin: 8px 0 24px; }
    .fact-table th, .fact-table td {
        text-align: left; padding: 8px 12px; border-bottom: 1px solid #1a3a44;
        font-size: 0.95em; vertical-align: top;
    }
    .fact-table th { color: #708890; font-weight: 500; width: 34%; }
    .alt-names { color: #b0b0b0; font-size: 0.95em; margin-bottom: 20px; }
    .related-list { list-style: none; margin: 0 0 24px; padding: 0; }
    .related-list li {
        border-bottom: 1px solid #1a3a44; padding: 10px 0;
    }
    .related-list li:last-child { border-bottom: none; }
    .related-list .rel-meta { color: #708890; font-size: 12px; }
    .sibling-links { font-size: 0.95em; line-height: 1.9; }
    .sibling-links a { margin-right: 4px; }
    .map-cta {
        display: inline-block; background: #c02023; color: #fff; padding: 10px 18px;
        border-radius: 6px; margin: 4px 0 24px; font-weight: 500;
    }
    .map-cta:hover { background: #a01b1e; }
"""


def _coord_display(lat: float | None, lon: float | None) -> str:
    """Human-readable coordinate string, or empty when the site has no position."""
    if lat is None or lon is None:
        return ""
    lat_dir = "N" if lat >= 0 else "S"
    lon_dir = "E" if lon >= 0 else "W"
    return f"{abs(lat):.4f}&deg; {lat_dir}, {abs(lon):.4f}&deg; {lon_dir}"


def _year_display(year: int) -> str:
    """Format a signed year as an era-qualified label (-500 -> '500 BC')."""
    return f"{abs(year)} {'BC' if year < 0 else 'AD'}"


def _period_display(site: dict) -> str:
    """Prefer the curated period name, fall back to a start/end year range."""
    if site.get("period_name"):
        return str(site["period_name"])
    start, end = site.get("period_start"), site.get("period_end")
    if start is None:
        return ""
    if end is None:
        return _year_display(start)
    return f"{_year_display(start)} – {_year_display(end)}"


def render_site_detail_html(site: dict, related: dict) -> str:
    """
    Render one archaeological site as a full, crawlable HTML page.

    site: {id, name, country, site_type, period_name, period_start, period_end,
           description, lat, lon, source_url}
    related: {alt_names: [str], image: {url, author, license, commons_url}|None,
              news: [{slug, headline}], links: [{title, url, content_type}],
              siblings: [{name, slug}], parent: {name, slug}|None}
    """
    name = site["name"]
    country = site.get("country") or ""
    if not country:
        # The canonical URL is /sites/{country}/{slug}; without a country it
        # would silently become /sites//{slug}. Callers select on
        # "country IS NOT NULL AND country != ''", so this is unreachable —
        # fail loudly rather than publish a broken canonical.
        raise ValueError(f"site {site['id']} has no country; cannot build a canonical URL")
    c_slug = country_slug(country)
    canonical = f"{BASE_URL}{encode_path(site_path(country, name, site['id']))}"

    e_name = escape(name)
    e_country = escape(country)
    site_type = site.get("site_type") or "Archaeological site"
    period = _period_display(site)
    coords = _coord_display(site.get("lat"), site.get("lon"))
    description = (site.get("description") or "").strip()

    # Title carries the two strongest query terms after the name.
    page_title = f"{name} — {country} · {site_type}"

    # Meta description: real prose beats a boilerplate template. Must be a
    # single line — the description text carries newlines, and a raw newline
    # inside the content attribute garbles the search snippet.
    if description:
        meta_desc = re.sub(r"\s+", " ", description).strip()
        if len(meta_desc) > 160:
            meta_desc = meta_desc[:157].rsplit(" ", 1)[0] + "…"
    else:
        meta_desc = f"{name}: {site_type.lower()} in {country}."

    paragraphs = "\n            ".join(
        f"<p>{escape(p.strip())}</p>" for p in description.split("\n") if p.strip()
    )

    # --- Hero image (Wikimedia, with the attribution its licence requires) ---
    hero_html = ""
    og_image = f"{BASE_URL}/landing/og-image.png"
    image = related.get("image")
    if image:
        og_image = f"{BASE_URL}{image['url']}"
        credit_bits = []
        if image.get("author"):
            credit_bits.append(escape(image["author"]))
        if image.get("license"):
            credit_bits.append(escape(image["license"]))
        credit = " · ".join(credit_bits)
        if image.get("commons_url"):
            credit = f'<a href="{escape(image["commons_url"])}" target="_blank" rel="noopener">{credit or "Wikimedia Commons"}</a>'
        hero_html = f"""<figure class="site-hero">
            <img src="{escape(image["url"])}" alt="{e_name}" loading="lazy">
            {f"<figcaption>{credit}</figcaption>" if credit else ""}
        </figure>"""

    # --- Facts table ---
    fact_rows = [("Type", escape(site_type))]
    if period:
        fact_rows.append(("Period", escape(period)))
    fact_rows.append(("Country", f'<a href="/sites/{c_slug}">{e_country}</a>'))
    if coords:
        fact_rows.append(("Coordinates", coords))
    parent = related.get("parent")
    if parent:
        fact_rows.append(
            ("Part of", f'<a href="/sites/{c_slug}/{parent["slug"]}">{escape(parent["name"])}</a>')
        )
    facts_html = "\n".join(
        f"                <tr><th>{label}</th><td>{value}</td></tr>" for label, value in fact_rows
    )

    # --- Alternate names ---
    alt_names = [n for n in related.get("alt_names", []) if n and n != name]
    alt_html = ""
    if alt_names:
        alt_html = (
            f'<p class="alt-names"><strong>Also known as:</strong> '
            f"{escape(', '.join(alt_names[:12]))}</p>"
        )

    # --- Related news stories (internal links into the indexed news archive) ---
    news_html = ""
    news = related.get("news", [])
    if news:
        items = "\n".join(
            f'                <li><a href="/news-archive/{escape(n["slug"])}">'
            f"{escape(n['headline'])}</a></li>"
            for n in news[:10]
        )
        news_html = f"""<h2>Archaeology news about {e_name}</h2>
            <ul class="related-list">
{items}
            </ul>"""

    # --- External resources (texts, maps, inscriptions, 3D models) ---
    links_html = ""
    links = [link for link in related.get("links", []) if link.get("url")]
    if links:
        link_items = []
        for link in links[:15]:
            url = escape(link["url"])
            label = escape(link.get("title") or link["url"])
            kind = link.get("content_type")
            kind_html = f' <span class="rel-meta">{escape(kind)}</span>' if kind else ""
            link_items.append(
                f'                <li><a href="{url}" target="_blank" rel="noopener">'
                f"{label}</a>{kind_html}</li>"
            )
        items = "\n".join(link_items)
        links_html = f"""<h2>Related resources</h2>
            <ul class="related-list">
{items}
            </ul>"""

    # --- Sibling sites: gives every detail page outbound internal links ---
    siblings_html = ""
    siblings = related.get("siblings", [])
    if siblings:
        sib_links = " &middot; ".join(
            f'<a href="/sites/{c_slug}/{s["slug"]}">{escape(s["name"])}</a>' for s in siblings[:24]
        )
        siblings_html = f"""<h2>More archaeological sites in {e_country}</h2>
            <p class="sibling-links">{sib_links}</p>
            <p><a href="/sites/{c_slug}">See all sites in {e_country} →</a></p>"""

    source_html = ""
    if site.get("source_url"):
        source_html = (
            f'<p class="meta">Source: <a href="{escape(site["source_url"])}" '
            f'target="_blank" rel="noopener">reference</a></p>'
        )

    # --- Structured data ---
    place_schema: list[str] = [
        '"@type": "Place"',
        f'"name": {_json_str(name)}',
        f'"url": "{canonical}"',
    ]
    if description:
        place_schema.append(f'"description": {_json_str(description[:500])}')
    if site.get("lat") is not None and site.get("lon") is not None:
        place_schema.append(
            f'"geo": {{"@type": "GeoCoordinates", "latitude": {site["lat"]}, '
            f'"longitude": {site["lon"]}}}'
        )
    place_schema.append(
        f'"address": {{"@type": "PostalAddress", "addressCountry": {_json_str(country)}}}'
    )
    if image:
        place_schema.append(f'"image": "{og_image}"')

    crumbs = [
        ("Home", f"{BASE_URL}/"),
        ("Sites", f"{BASE_URL}/sites/"),
        (country, f"{BASE_URL}{encode_path(country_path(country))}"),
        (name, canonical),
    ]
    crumb_items = ", ".join(
        f'{{"@type": "ListItem", "position": {i}, "name": {_json_str(label)}, "item": "{url}"}}'
        for i, (label, url) in enumerate(crumbs, start=1)
    )

    schema = f"""[
    {{
        "@context": "https://schema.org",
        {", ".join(place_schema)}
    }},
    {{
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [{crumb_items}]
    }}
    ]"""

    breadcrumb_html = " / ".join(
        [
            '<a href="/">Home</a>',
            '<a href="/sites/">Sites</a>',
            f'<a href="/sites/{c_slug}">{e_country}</a>',
            e_name,
        ]
    )

    e_title = escape(page_title)
    e_meta_desc = escape(meta_desc)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{e_title} | Ancient Nerds</title>
    <meta name="description" content="{e_meta_desc}">
    <meta name="robots" content="index, follow, max-image-preview:large">
    <link rel="canonical" href="{canonical}">

    <meta property="og:type" content="place">
    <meta property="og:url" content="{canonical}">
    <meta property="og:site_name" content="Ancient Nerds">
    <meta property="og:title" content="{e_title}">
    <meta property="og:description" content="{e_meta_desc}">
    <meta property="og:image" content="{escape(og_image)}">

    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{e_title}">
    <meta name="twitter:description" content="{e_meta_desc}">
    <meta name="twitter:image" content="{escape(og_image)}">
    <meta name="twitter:site" content="@AncientNerdsDAO">

    <link rel="icon" type="image/svg+xml" href="/favicon.svg">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500;600&family=Orbitron:wght@700&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">

    <script type="application/ld+json">{schema}</script>
    <style>{_SHARED_CSS}{_SITES_CSS}{_SITE_DETAIL_CSS}</style>
</head>
<body>
    {_nav_html()}
    <main class="container">
        <article>
            <nav class="breadcrumb">{breadcrumb_html}</nav>
            <h1>{e_name}</h1>
            <div class="meta">{escape(site_type)}{f" &middot; {escape(period)}" if period else ""} &middot; {e_country}</div>
            {hero_html}
            {alt_html}
            <div class="article-body">
            {paragraphs}
            </div>
            <table class="fact-table">
{facts_html}
            </table>
            <a class="map-cta" href="/site.html?id={escape(str(site["id"]))}">View on the interactive 3D globe →</a>
            {source_html}
            {news_html}
            {links_html}
            {siblings_html}
        </article>
    </main>
    {_footer_html()}
</body>
</html>"""


def country_slug(country: str) -> str:
    """URL slug for a country name."""
    return slugify(country)


def site_id_short(site_id: str) -> str:
    """First 8 hex chars of a site UUID — the on-disk image dir and slug suffix."""
    return str(site_id).replace("-", "")[:8]


def site_slug(name: str, site_id: str) -> str:
    """
    Stable, unique slug for a site: name slug + short ID suffix.

    The ID suffix is required, not decorative: 16 curated sites share a name
    with another site. It also makes the URL self-healing — a renamed site
    still resolves via the suffix and redirects to its new canonical slug.
    """
    stem = slugify(name)
    suffix = site_id_short(site_id)
    return f"{stem}-{suffix}" if stem else suffix


def site_id_prefix_from_slug(slug: str) -> str | None:
    """Extract the 8-hex-char site ID prefix from a site slug, or None if malformed."""
    tail = slug.rsplit("-", 1)[-1].lower()
    return tail if re.fullmatch(r"[0-9a-f]{8}", tail) else None


def site_path(country: str, name: str, site_id: str) -> str:
    """Canonical path for a site detail page, unencoded (see encode_path)."""
    return f"/sites/{country_slug(country)}/{site_slug(name, site_id)}"


def country_path(country: str) -> str:
    """Canonical path for a country listing page, unencoded (see encode_path)."""
    return f"/sites/{country_slug(country)}"


def encode_path(path: str) -> str:
    """
    Percent-encode a site-relative path for use in a sitemap <loc> or a
    rel=canonical URL.

    478 of the 5,012 curated site names carry non-ASCII characters
    (Ayşepınar, Aguada Fénix, …), one country does too (Türkiye), and so do
    ~100 news/article slugs. The sitemap protocol requires escaped URLs.

    Takes an UNENCODED path — passing an already-encoded one would
    double-escape every '%'. In-page href attributes do not need this;
    browsers encode them, and the readable form is nicer to look at.
    """
    return quote(path)


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
        site_url = f"/sites/{slug}/{site_slug(s['name'], s['id'])}"
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
