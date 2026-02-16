"""
Wiki Images API Routes.

Serves locally cached Wikipedia/Wikimedia Commons image metadata for sites.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from pipeline.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{site_id}")
async def get_wiki_images(site_id: str, db: Session = Depends(get_db)):
    """Get locally cached wiki images for a site."""
    result = db.execute(text("""
        SELECT
            filename, original_url, commons_page_url,
            author, author_url, license, license_url,
            title, is_hero, is_lead, sort_order,
            source_type, width, height, site_id
        FROM wiki_images
        WHERE site_id = :site_id
        ORDER BY sort_order
    """), {"site_id": site_id})

    images = []
    for row in result:
        site_id_short = str(row.site_id).replace("-", "")[:8]
        images.append({
            "url": f"/data/images/wiki/{site_id_short}/{row.filename}",
            "thumb": f"/data/images/wiki/{site_id_short}/{row.filename}",
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
