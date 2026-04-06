"""Wiki images API — hero management and local image cache."""

import logging
from io import BytesIO
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException
from PIL import Image
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.services.jwt_auth import require_founder
from pipeline.database import DiscordUser, get_db

logger = logging.getLogger(__name__)
router = APIRouter()

IMAGE_DIR = Path("/app/public/data/images/wiki")
HERO_WIDTH = 800
WEBP_QUALITY = 82


class SetHeroRequest(BaseModel):
    image_url: str
    attribution_url: str


@router.get("/hero-status")
async def get_hero_status(db: Session = Depends(get_db)):
    """Return hero image info for all sites that have one."""
    result = db.execute(
        text("""
        SELECT DISTINCT ON (site_id) site_id::text, original_url, commons_page_url
        FROM wiki_images
        WHERE is_hero = true
        ORDER BY site_id, created_at DESC
    """)
    )
    out = {}
    for row in result:
        sid_short = row[0].replace("-", "")[:8]
        out[row[0]] = {
            "path": f"/data/images/wiki/{sid_short}/hero.webp",
            "original_url": row[1] or "",
            "attribution_url": row[2] or "",
        }
    return out


@router.post("/{site_id}/set-hero")
async def set_hero(
    site_id: str,
    body: SetHeroRequest,
    db: Session = Depends(get_db),
    _user: DiscordUser = Depends(require_founder),
):
    """Download an image and set it as hero for a site."""
    import traceback

    try:
        # Validate site exists
        site_row = db.execute(
            text("SELECT id FROM unified_sites WHERE id = :id"),
            {"id": site_id},
        ).fetchone()
        if not site_row:
            raise HTTPException(status_code=404, detail="Site not found")

        # Load the image: local path or remote URL
        print(f"[set-hero] Loading image: {body.image_url}", flush=True)
        if body.image_url.startswith("/data/"):
            local_path = Path("/app/public") / body.image_url.lstrip("/")
            print(f"[set-hero] Resolved local path: {local_path} (exists={local_path.exists()})", flush=True)
            if not local_path.exists():
                raise HTTPException(status_code=400, detail=f"Local image not found: {local_path}")
            image_bytes = local_path.read_bytes()
        else:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(body.image_url)
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=400, detail=f"Failed to download image: HTTP {resp.status_code}"
                )
            image_bytes = resp.content

        print(f"[set-hero] Loaded {len(image_bytes)} bytes", flush=True)

        # Process with PIL: resize + convert to WebP
        img = Image.open(BytesIO(image_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        if img.width > HERO_WIDTH:
            ratio = HERO_WIDTH / img.width
            img = img.resize((HERO_WIDTH, int(img.height * ratio)), Image.LANCZOS)

        final_width, final_height = img.size
        print(f"[set-hero] Processed image: {final_width}x{final_height}", flush=True)

        # Save to disk
        site_id_short = site_id.replace("-", "")[:8]
        site_dir = IMAGE_DIR / site_id_short
        site_dir.mkdir(parents=True, exist_ok=True)
        hero_path = site_dir / "hero.webp"

        buf = BytesIO()
        img.save(buf, format="WEBP", quality=WEBP_QUALITY, method=4)
        hero_path.write_bytes(buf.getvalue())
        print(f"[set-hero] Saved hero to {hero_path}", flush=True)

        thumb_path = f"/data/images/wiki/{site_id_short}/hero.webp"

        # Clear existing hero flags for this site
        db.execute(
            text("UPDATE wiki_images SET is_hero = false WHERE site_id = :sid AND is_hero = true"),
            {"sid": site_id},
        )

        # Upsert wiki_images row
        db.execute(
            text("""
            INSERT INTO wiki_images (site_id, filename, original_url, commons_page_url, is_hero, source_type, width, height)
            VALUES (:sid, 'hero.webp', :orig, :attr, true, 'manual', :w, :h)
            ON CONFLICT (site_id, original_url)
            DO UPDATE SET
                filename = 'hero.webp',
                commons_page_url = :attr,
                is_hero = true,
                source_type = 'manual',
                width = :w,
                height = :h
        """),
            {
                "sid": site_id,
                "orig": body.image_url,
                "attr": body.attribution_url,
                "w": final_width,
                "h": final_height,
            },
        )

        # Update thumbnail_url on unified_sites
        db.execute(
            text("UPDATE unified_sites SET thumbnail_url = :thumb WHERE id = :sid"),
            {"thumb": thumb_path, "sid": site_id},
        )

        db.commit()
        print(f"[set-hero] Success! thumbnail_url={thumb_path}", flush=True)
        return {"success": True, "path": thumb_path}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        tb = traceback.format_exc()
        print(f"[set-hero] FAILED: {e}\n{tb}", flush=True)
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}") from None


@router.get("/{site_id}")
async def get_wiki_images(site_id: str, db: Session = Depends(get_db)):
    """Get locally cached wiki images for a site."""
    result = db.execute(
        text("""
        SELECT
            filename, original_url, commons_page_url,
            author, author_url, license, license_url,
            title, is_hero, is_lead, sort_order,
            source_type, width, height, site_id
        FROM wiki_images
        WHERE site_id = :site_id
        ORDER BY is_hero DESC, is_lead DESC, sort_order
    """),
        {"site_id": site_id},
    )

    images = []
    for row in result:
        site_id_short = str(row.site_id).replace("-", "")[:8]
        images.append(
            {
                "url": f"/data/images/wiki/{site_id_short}/{row.filename}",
                "thumb": f"/data/images/wiki/{site_id_short}/{row.filename}",
                "title": row.title,
                "author": row.author,
                "authorUrl": row.author_url,
                "license": row.license,
                "licenseUrl": row.license_url,
                "commonsUrl": row.commons_page_url,
                "originalUrl": row.original_url,
                "isHero": row.is_hero,
                "isLead": row.is_lead,
                "width": row.width,
                "height": row.height,
            }
        )

    return images
