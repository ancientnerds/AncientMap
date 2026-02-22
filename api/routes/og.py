"""
Open Graph Image Generator for Social Media Sharing.

Serves the site's thumbnail image as WebP for OG previews.
Falls back to a branded logo image for sites without thumbnails.
"""

import html
import io
import logging
import os
import re
import tempfile
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse
from PIL import Image
from sqlalchemy import text
from sqlalchemy.orm import Session

from pipeline.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter()

# Logo directory
LOGO_DIR = Path(__file__).parent.parent.parent / "logo"

# OG image dimensions (for fallback)
OG_WIDTH = 600
OG_HEIGHT = 315

# Disk cache for fetched thumbnail images
OG_CACHE_DIR = Path(tempfile.gettempdir()) / "og-cache"
OG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
OG_CACHE_MAX_AGE = 86400  # 24 hours


def _get_cached_image(site_id: str) -> tuple[bytes, str] | None:
    """Return cached (bytes, content_type) if fresh, else None."""
    for ext, ct in [("jpg", "image/jpeg"), ("png", "image/png"), ("webp", "image/webp")]:
        cache_path = OG_CACHE_DIR / f"{site_id}.{ext}"
        if cache_path.exists():
            age = time.time() - cache_path.stat().st_mtime
            if age > OG_CACHE_MAX_AGE:
                cache_path.unlink(missing_ok=True)
                continue
            return cache_path.read_bytes(), ct
    return None


def _save_cached_image(site_id: str, data: bytes, content_type: str) -> None:
    """Save image bytes to disk cache."""
    OG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ext = {"image/png": "png", "image/webp": "webp"}.get(content_type, "jpg")
    cache_path = OG_CACHE_DIR / f"{site_id}.{ext}"
    cache_path.write_bytes(data)


async def _fetch_thumbnail(thumbnail_url: str) -> tuple[bytes, str] | None:
    """Fetch a thumbnail URL. Returns (bytes, content_type) or None."""
    user_agent = os.environ.get("OG_USER_AGENT", "AncientNerdsMap/1.0 (https://ancientnerds.com; contact@ancientnerds.com)")
    try:
        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": user_agent}) as client:
            resp = await client.get(thumbnail_url, follow_redirects=True)
            if resp.status_code != 200:
                return None
            content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
            return resp.content, content_type
    except Exception as e:
        logger.warning(f"Thumbnail fetch failed for {thumbnail_url}: {e}")
        return None


def _generate_og_fallback() -> bytes:
    """Generate a branded fallback OG image (logo on dark background)."""
    img = Image.new('RGBA', (OG_WIDTH, OG_HEIGHT), (10, 20, 25, 255))

    logo_path = LOGO_DIR / "without background.png"
    if logo_path.exists():
        try:
            logo = Image.open(logo_path).convert('RGBA')
            logo_h = int(OG_HEIGHT * 0.6)
            logo_w = int(logo_h * logo.width / logo.height)
            logo = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
            img.paste(logo, ((OG_WIDTH - logo_w) // 2, (OG_HEIGHT - logo_h) // 2), logo)
        except Exception as e:
            logger.warning(f"Failed to load logo: {e}")

    img = img.convert('RGB')
    buffer = io.BytesIO()
    img.save(buffer, format='WEBP', quality=82)
    return buffer.getvalue()


@router.get("/homepage")
async def get_homepage_og_image():
    """Generate Open Graph image for the homepage."""
    img = Image.new('RGBA', (OG_WIDTH, OG_HEIGHT), (10, 20, 25, 255))

    logo_path = LOGO_DIR / "without background.png"
    if logo_path.exists():
        try:
            logo = Image.open(logo_path).convert('RGBA')
            logo_h = int(OG_HEIGHT * 0.75)
            logo_w = int(logo_h * logo.width / logo.height)
            logo = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
            img.paste(logo, ((OG_WIDTH - logo_w) // 2, (OG_HEIGHT - logo_h) // 2), logo)
        except Exception as e:
            logger.warning(f"Failed to load logo for homepage: {e}")

    img = img.convert('RGB')
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=85, optimize=True)
    buffer.seek(0)

    return Response(
        content=buffer.getvalue(),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=604800"},
    )


def get_site_data(site_id: str, db: Session) -> dict:
    """Look up site metadata from the database."""
    query = text("""
        SELECT name, lat, lon, country, description, site_type,
               period_start, period_end, thumbnail_url
        FROM unified_sites
        WHERE id::text = :site_id
    """)
    result = db.execute(query, {"site_id": site_id})
    row = result.fetchone()

    if not row:
        return {
            "found": False,
            "name": "Site Not Found",
            "description": "This archaeological site could not be found.",
            "country": "",
            "site_type": None,
            "period": None,
            "lat": None,
            "lon": None,
            "thumbnail_url": None,
        }

    description = row.description or ""
    if len(description) > 200:
        description = description[:197] + "..."

    # Build period string
    period = None
    if row.period_start is not None:
        ps = row.period_start
        pe = row.period_end
        suffix_s = "BC" if ps < 0 else "AD"
        suffix_e = "BC" if (pe or ps) < 0 else "AD"
        period = f"{abs(ps)} {suffix_s}" if pe is None else f"{abs(ps)} {suffix_s} - {abs(pe)} {suffix_e}"

    return {
        "found": True,
        "name": row.name or "Unknown Site",
        "description": description,
        "country": row.country or "",
        "site_type": row.site_type,
        "period": period,
        "lat": row.lat,
        "lon": row.lon,
        "thumbnail_url": row.thumbnail_url,
    }


@router.get("/share/{site_id}")
async def get_share_page(
    site_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Serve HTML page with OG meta tags for social media sharing."""
    if not re.match(r'^[0-9a-fA-F-]{36}$', site_id):
        return HTMLResponse(content="Invalid site ID", status_code=400)

    base_url = str(request.base_url).rstrip('/')
    base_url = base_url.replace("http://", "https://")
    site = get_site_data(site_id, db)

    og_image_url = f"{base_url}/api/og/{site_id}"
    app_url = html.escape(f"/site.html?id={site_id}")
    canonical_url = html.escape(f"{base_url}/site.html?id={site_id}")

    # Title: "Site Name | Country · Category"
    title_parts: list[str] = []
    if site["country"]:
        title_parts.append(site["country"])
    if site["site_type"]:
        title_parts.append(site["site_type"])
    title = site["name"]
    if title_parts:
        title += " | " + " · ".join(title_parts)

    # Description: just the site description text
    og_desc = site["description"] or "Archaeological site on Ancient Nerds"

    title_escaped = html.escape(title)
    og_desc_escaped = html.escape(og_desc)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title_escaped} - Ancient Nerds</title>

    <!-- Open Graph / Facebook -->
    <meta property="og:type" content="website">
    <meta property="og:url" content="{canonical_url}">
    <meta property="og:title" content="{title_escaped}">
    <meta property="og:description" content="{og_desc_escaped}">
    <meta property="og:image" content="{og_image_url}">
    <meta property="og:site_name" content="ANCIENT NERDS">

    <!-- Twitter -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{title_escaped}">
    <meta name="twitter:description" content="{og_desc_escaped}">
    <meta name="twitter:image" content="{og_image_url}">
    <meta name="twitter:site" content="@AncientNerdsDAO">

    <!-- Redirect to app -->
    <meta http-equiv="refresh" content="0;url={app_url}">

    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a1a1f;
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
        }}
        .loading {{ text-align: center; }}
        .spinner {{
            width: 40px; height: 40px;
            border: 3px solid #333;
            border-top-color: #ffd700;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    </style>
</head>
<body>
    <div class="loading">
        <div class="spinner"></div>
        <p>Loading {title_escaped}...</p>
    </div>
    <script>window.location.href = "{app_url}";</script>
</body>
</html>"""

    return HTMLResponse(content=html_content)


@router.get("/{site_id}")
async def get_og_image(
    site_id: str,
    refresh: bool = False,
    db: Session = Depends(get_db),
):
    """Serve the site's thumbnail image. Falls back to branded logo."""
    # Check disk cache first
    if not refresh:
        cached = _get_cached_image(site_id)
        if cached:
            data, ct = cached
            return Response(content=data, media_type=ct, headers={"Cache-Control": "public, max-age=86400"})

    site = get_site_data(site_id, db)

    # If site has a thumbnail, fetch and serve it as-is
    if site.get("thumbnail_url"):
        result = await _fetch_thumbnail(site["thumbnail_url"])
        if result:
            data, ct = result
            _save_cached_image(site_id, data, ct)
            return Response(content=data, media_type=ct, headers={"Cache-Control": "public, max-age=86400"})

    # Fallback — branded logo image
    img_bytes = _generate_og_fallback()
    _save_cached_image(site_id, img_bytes, "image/webp")
    return Response(content=img_bytes, media_type="image/webp", headers={"Cache-Control": "public, max-age=86400"})
