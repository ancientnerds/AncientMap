"""
Open Graph Image Generator for Social Media Sharing.

Serves the site's thumbnail image as WebP for OG previews.
Falls back to a branded logo image for sites without thumbnails.
"""

import io
import logging
import os
import re
import tempfile
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, Response
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
    user_agent = os.environ.get(
        "OG_USER_AGENT", "AncientNerdsMap/1.0 (https://ancientnerds.com; contact@ancientnerds.com)"
    )
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
    img = Image.new("RGBA", (OG_WIDTH, OG_HEIGHT), (10, 20, 25, 255))

    logo_path = LOGO_DIR / "without background.png"
    if logo_path.exists():
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo_h = int(OG_HEIGHT * 0.6)
            logo_w = int(logo_h * logo.width / logo.height)
            logo = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
            img.paste(logo, ((OG_WIDTH - logo_w) // 2, (OG_HEIGHT - logo_h) // 2), logo)
        except Exception as e:
            logger.warning(f"Failed to load logo: {e}")

    img = img.convert("RGB")
    buffer = io.BytesIO()
    img.save(buffer, format="WEBP", quality=82)
    return buffer.getvalue()


@router.get("/homepage")
async def get_homepage_og_image():
    """Generate Open Graph image for the homepage."""
    img = Image.new("RGBA", (OG_WIDTH, OG_HEIGHT), (10, 20, 25, 255))

    logo_path = LOGO_DIR / "without background.png"
    if logo_path.exists():
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo_h = int(OG_HEIGHT * 0.75)
            logo_w = int(logo_h * logo.width / logo.height)
            logo = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
            img.paste(logo, ((OG_WIDTH - logo_w) // 2, (OG_HEIGHT - logo_h) // 2), logo)
        except Exception as e:
            logger.warning(f"Failed to load logo for homepage: {e}")

    img = img.convert("RGB")
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85, optimize=True)
    buffer.seek(0)

    return Response(
        content=buffer.getvalue(),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=604800"},
    )


def _thumbnail_url(site_id: str, db: Session) -> str | None:
    """The site's thumbnail URL; None when it has none or does not exist."""
    row = db.execute(
        text("SELECT thumbnail_url FROM unified_sites WHERE id::text = :site_id"),
        {"site_id": site_id},
    ).fetchone()
    return row.thumbnail_url if row else None


@router.get("/{site_id}")
async def get_og_image(
    site_id: str,
    refresh: bool = False,
    db: Session = Depends(get_db),
):
    """Serve the site's thumbnail image. Falls back to branded logo."""
    if not re.match(r"^[0-9a-fA-F-]{36}$", site_id):
        return Response(content="Invalid site ID", status_code=400)

    # Check disk cache first
    if not refresh:
        cached = _get_cached_image(site_id)
        if cached:
            data, ct = cached
            return Response(
                content=data, media_type=ct, headers={"Cache-Control": "public, max-age=86400"}
            )

    thumbnail_url = _thumbnail_url(site_id, db)

    # If site has a thumbnail, fetch and serve it as-is
    if thumbnail_url:
        result = await _fetch_thumbnail(thumbnail_url)
        if result:
            data, ct = result
            _save_cached_image(site_id, data, ct)
            return Response(
                content=data, media_type=ct, headers={"Cache-Control": "public, max-age=86400"}
            )

    # Fallback — branded logo image
    img_bytes = _generate_og_fallback()
    _save_cached_image(site_id, img_bytes, "image/webp")
    return Response(
        content=img_bytes,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=86400"},
    )
