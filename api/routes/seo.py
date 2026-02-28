"""
SEO pre-rendered pages for search engine crawlers.

Serves full HTML with OG tags, structured data, and visible content.
Nginx detects crawler user agents on /site.html?id={uuid} and rewrites
to /seo/site/{uuid} which is handled here.
"""

import html
import json
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from api.routes.og import get_site_data
from pipeline.database import get_db

router = APIRouter()


@router.get("/seo/site/{site_id}")
async def seo_site_page(
    site_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Serve pre-rendered HTML for crawlers hitting /?site={uuid}."""
    if not re.match(r"^[0-9a-fA-F-]{36}$", site_id):
        return HTMLResponse(content="Invalid site ID", status_code=400)

    site = get_site_data(site_id, db)
    if not site["found"]:
        return HTMLResponse(content="Site not found", status_code=404)

    # Nginx proxies over HTTP internally; force https for public URLs
    base_url = str(request.base_url).rstrip("/").replace("http://", "https://")
    country_escaped = html.escape(site["country"])
    site_type_escaped = html.escape(site["site_type"] or "Archaeological site")
    og_image_url = f"{base_url}/api/og/{site_id}"
    canonical_url = html.escape(f"{base_url}/site.html?id={site_id}")

    # Title: "Site Name | Country · Category"
    title_parts: list[str] = []
    if site["country"]:
        title_parts.append(site["country"])
    if site["site_type"]:
        title_parts.append(site["site_type"])
    og_title = site["name"]
    if title_parts:
        og_title += " | " + " · ".join(title_parts)
    title_escaped = html.escape(og_title)

    # Description: just the site description text
    desc_escaped = html.escape(site["description"] or "Archaeological site on Ancient Nerds")

    # JSON-LD structured data for Google rich results
    ld_json = {
        "@context": "https://schema.org",
        "@type": "Place",
        "name": site["name"],
        "description": site["description"],
        "url": f"{base_url}/site.html?id={site_id}",
        "image": f"{base_url}/api/og/{site_id}",
    }
    if site["lat"] is not None and site["lon"] is not None:
        ld_json["geo"] = {
            "@type": "GeoCoordinates",
            "latitude": site["lat"],
            "longitude": site["lon"],
        }
    if site["country"]:
        ld_json["address"] = {
            "@type": "PostalAddress",
            "addressCountry": site["country"],
        }
    # json.dumps with ensure_ascii=True prevents any HTML injection via </script>
    ld_json_str = json.dumps(ld_json, ensure_ascii=True)

    # Build coordinate string for display
    coord_str = ""
    if site["lat"] is not None and site["lon"] is not None:
        lat, lon = site["lat"], site["lon"]
        lat_dir = "N" if lat >= 0 else "S"
        lon_dir = "E" if lon >= 0 else "W"
        coord_str = f"{abs(lat):.4f}&deg; {lat_dir}, {abs(lon):.4f}&deg; {lon_dir}"

    page_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title_escaped} - Ancient Nerds</title>
    <meta name="description" content="{desc_escaped}">
    <link rel="canonical" href="{canonical_url}">

    <!-- Open Graph / Facebook -->
    <meta property="og:type" content="website">
    <meta property="og:url" content="{canonical_url}">
    <meta property="og:title" content="{title_escaped}">
    <meta property="og:description" content="{desc_escaped}">
    <meta property="og:image" content="{og_image_url}">
    <meta property="og:site_name" content="ANCIENT NERDS">

    <!-- Twitter -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{title_escaped}">
    <meta name="twitter:description" content="{desc_escaped}">
    <meta name="twitter:image" content="{og_image_url}">
    <meta name="twitter:site" content="@AncientNerdsDAO">

    <script type="application/ld+json">{ld_json_str}</script>

    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a1a1f; color: #e0e0e0;
            max-width: 720px; margin: 40px auto; padding: 0 20px;
        }}
        h1 {{ color: #ffd700; margin-bottom: 8px; }}
        .meta {{ color: #999; font-size: 14px; margin-bottom: 16px; }}
        .description {{ line-height: 1.6; margin-bottom: 24px; }}
        a {{ color: #4fc3f7; }}
    </style>
</head>
<body>
    <h1>{title_escaped}</h1>
    <p class="meta">{site_type_escaped}{" &mdash; " + country_escaped if site["country"] else ""}{" &mdash; " + coord_str if coord_str else ""}</p>
    <p class="description">{desc_escaped}</p>
    <p><a href="/site.html?id={html.escape(site_id)}">View on Ancient Nerds Map</a></p>
</body>
</html>"""

    return HTMLResponse(
        content=page_html,
        headers={"Cache-Control": "public, max-age=86400"},
    )
