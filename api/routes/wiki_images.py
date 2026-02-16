"""
Wiki Images API Routes.

Serves Wikipedia/Wikimedia Commons image metadata for sites.
Images are served from Wikimedia's CDN (upload.wikimedia.org).
"""

import logging
import re

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from pipeline.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter()

THUMB_SIZE = 400
FULL_SIZE = 1600


def _wikimedia_thumb_url(original_url: str, width: int) -> str:
    """Convert a Wikimedia original URL to a thumbnail URL at given width.

    Original: .../commons/a/ab/File.jpg
    Thumb:    .../commons/thumb/a/ab/File.jpg/800px-File.jpg
    """
    if not original_url or "upload.wikimedia.org" not in original_url:
        return original_url or ""

    if "/thumb/" not in original_url:
        if "/wikipedia/commons/" in original_url:
            thumb = original_url.replace("/commons/", "/commons/thumb/", 1)
        else:
            thumb = re.sub(
                r"/wikipedia/(\w+)/", r"/wikipedia/\1/thumb/", original_url, count=1
            )
        filename = original_url.rsplit("/", 1)[-1]
        return f"{thumb}/{width}px-{filename}"

    # Already a thumb URL — just swap the width
    return re.sub(r"/\d+px-", f"/{width}px-", original_url)


@router.get("/{site_id}")
async def get_wiki_images(site_id: str, db: Session = Depends(get_db)):
    """Get wiki images for a site. URLs point to Wikimedia CDN."""
    result = db.execute(text("""
        SELECT
            original_url, commons_page_url,
            author, author_url, license, license_url,
            title, is_hero, is_lead, sort_order,
            width, height
        FROM wiki_images
        WHERE site_id = :site_id
        ORDER BY sort_order
    """), {"site_id": site_id})

    images = []
    for row in result:
        images.append({
            "url": _wikimedia_thumb_url(row.original_url, FULL_SIZE),
            "thumb": _wikimedia_thumb_url(row.original_url, THUMB_SIZE),
            "title": row.title,
            "author": row.author,
            "authorUrl": row.author_url,
            "license": row.license,
            "licenseUrl": row.license_url,
            "commonsUrl": row.commons_page_url,
            "isHero": row.is_hero,
            "isLead": row.is_lead,
            "width": row.width,
            "height": row.height,
        })

    return images
