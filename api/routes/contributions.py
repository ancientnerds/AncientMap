"""
User Contributions API - Staging endpoint for site submissions.

All contributions are saved to a JSON file for easy review and editing.
Later, approved contributions can be integrated into the main database.
"""

import json
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from api.services.admin_auth import get_client_ip
from api.services.rate_limiter import RateLimiter
from api.services.turnstile import verify_turnstile as _verify_turnstile_shared
from pipeline.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Lyra Stats & Discoveries Endpoints
# =============================================================================


@router.get("/lyra/stats")
async def get_lyra_stats(db: Session = Depends(get_db)):
    """
    Get Lyra's knowledge stats for the dossier modal.

    Returns:
    - total_discoveries: sites discovered by Lyra (user_contributions with source='lyra')
    - total_sites_known: sites in Lyra's knowledge base (unified_sites)
    - total_name_variants: alternate names Lyra can match (unified_site_names)
    """
    # Sites discovered by Lyra
    discoveries = db.execute(text("""
        SELECT COUNT(*) FROM user_contributions WHERE source = 'lyra'
    """)).scalar() or 0

    # Sites in knowledge base
    sites_known = db.execute(text("""
        SELECT COUNT(*) FROM unified_sites
    """)).scalar() or 0

    # Name variants
    name_variants = db.execute(text("""
        SELECT COUNT(*) FROM unified_site_names
    """)).scalar() or 0

    return {
        "total_discoveries": discoveries,
        "total_sites_known": sites_known,
        "total_name_variants": name_variants,
    }


@router.get("/lyra/list")
async def get_lyra_contributions(
    page: int = 1,
    page_size: int = 20,
    min_mentions: int = 1,
    db: Session = Depends(get_db),
):
    """
    Get paginated list of sites discovered by Lyra.

    Sorted by mention_count DESC (most mentioned first).
    """
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    offset = (page - 1) * page_size

    # Get total count
    total = db.execute(text("""
        SELECT COUNT(*) FROM user_contributions
        WHERE source = 'lyra' AND mention_count >= :min_mentions
    """), {"min_mentions": min_mentions}).scalar() or 0

    # Get paginated items
    rows = db.execute(text("""
        SELECT id, name, description, country, site_type, source_url, mention_count, created_at
        FROM user_contributions
        WHERE source = 'lyra' AND mention_count >= :min_mentions
        ORDER BY mention_count DESC, created_at DESC
        LIMIT :limit OFFSET :offset
    """), {"min_mentions": min_mentions, "limit": page_size, "offset": offset}).fetchall()

    items = [
        {
            "id": str(row.id),
            "name": row.name,
            "description": row.description,
            "country": row.country,
            "site_type": row.site_type,
            "source_url": row.source_url,
            "mention_count": row.mention_count,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]

    return {
        "items": items,
        "total_count": total,
        "page": page,
        "page_size": page_size,
        "has_more": offset + len(items) < total,
    }

# Contributions JSON file path
CONTRIBUTIONS_FILE = Path(__file__).parent.parent.parent / "data" / "contributions.json"

_rate_limiter = RateLimiter(max_requests=25, window_seconds=3600)


def load_contributions() -> list[dict]:
    """Load contributions from JSON file."""
    if not CONTRIBUTIONS_FILE.exists():
        return []
    try:
        with open(CONTRIBUTIONS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []


def save_contribution(contribution: dict) -> None:
    """Append a contribution to the JSON file."""
    # Ensure data directory exists
    CONTRIBUTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Load existing, append, and save
    contributions = load_contributions()
    contributions.append(contribution)

    with open(CONTRIBUTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(contributions, f, indent=2, ensure_ascii=False)


class ContributionCreate(BaseModel):
    """Pydantic model for contribution submission."""
    name: str = Field(..., min_length=1, max_length=500, description="Site name (required)")
    lat: float | None = Field(None, ge=-90, le=90, description="Latitude")
    lon: float | None = Field(None, ge=-180, le=180, description="Longitude")
    description: str | None = Field(None, max_length=5000, description="Site description")
    country: str | None = Field(None, max_length=100, description="Country")
    site_type: str | None = Field(None, max_length=100, description="Site type/category")
    source_url: str | None = Field(None, max_length=2000, description="Source URL")
    turnstile_token: str = Field(..., description="Cloudflare Turnstile token")

    @field_validator('source_url')
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        """Validate that source_url is a proper HTTP/HTTPS URL."""
        if v is None or v.strip() == '':
            return None
        v = v.strip()
        # Only allow http/https URLs
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?'  # domain
            r'(\.[a-zA-Z]{2,})+'  # TLD
            r'(:\d+)?'  # optional port
            r'(/[^\s]*)?$',  # path
            re.IGNORECASE
        )
        if not url_pattern.match(v):
            raise ValueError('Invalid URL format. Must be a valid http:// or https:// URL.')
        return v

    @field_validator('country')
    @classmethod
    def validate_country(cls, v: str | None) -> str | None:
        """Validate country contains only allowed characters."""
        if v is None or v.strip() == '':
            return None
        v = v.strip()
        # Only allow letters, spaces, hyphens, and apostrophes
        if not re.match(r"^[a-zA-Z\s\-']+$", v):
            raise ValueError('Country must contain only letters, spaces, hyphens, and apostrophes.')
        return v


async def verify_turnstile(token: str, ip: str) -> bool:
    """Verify Cloudflare Turnstile token (delegates to shared service)."""
    return await _verify_turnstile_shared(token, ip)


@router.post("/")
async def create_contribution(
    contribution: ContributionCreate,
    request: Request,
):
    """
    Submit a new site contribution.

    Requires Cloudflare Turnstile verification.
    All submissions are saved to a JSON file for admin review.
    """
    client_ip = get_client_ip(request)

    # Rate limiting check (before Turnstile to save API calls)
    if client_ip and not _rate_limiter.check(client_ip):
        raise HTTPException(status_code=429, detail="Too many submissions. Please try again later.")

    # Verify Turnstile token
    is_valid = await verify_turnstile(contribution.turnstile_token, client_ip or "")
    if not is_valid:
        raise HTTPException(status_code=400, detail="Bot verification failed. Please try again.")

    # Create contribution record
    contribution_id = str(uuid.uuid4())
    contribution_data = {
        "id": contribution_id,
        "name": contribution.name.strip(),
        "lat": contribution.lat,
        "lon": contribution.lon,
        "description": contribution.description.strip() if contribution.description else None,
        "country": contribution.country.strip() if contribution.country else None,
        "site_type": contribution.site_type,
        "source_url": contribution.source_url.strip() if contribution.source_url else None,
        "status": "pending",  # pending, approved, rejected
        "submitted_at": datetime.now(UTC).isoformat(),
        "submitter_ip": client_ip,
    }

    # Save to JSON file
    save_contribution(contribution_data)

    logger.info(f"New submission: {contribution_data['name']} (ID: {contribution_id})")

    return {
        "success": True,
        "id": contribution_id,
        "message": "Thank you! Your contribution has been submitted for review.",
    }


@router.get("/site-types")
async def get_site_types(db: Session = Depends(get_db)):
    """
    Get list of existing site types for the dropdown.

    Returns the distinct site types from the unified_sites table.
    """
    try:
        result = db.execute(text("""
            SELECT DISTINCT site_type
            FROM unified_sites
            WHERE site_type IS NOT NULL AND site_type != ''
            ORDER BY site_type
            LIMIT 100
        """))

        types = [row.site_type for row in result if row.site_type]
        return {"site_types": types}
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching site types: {e}")
        raise HTTPException(status_code=500, detail="Database error fetching site types") from e


@router.get("/countries")
async def get_countries(db: Session = Depends(get_db)):
    """
    Get list of countries from existing sites.

    Returns distinct countries for autocomplete suggestions.
    """
    try:
        result = db.execute(text("""
            SELECT DISTINCT country
            FROM unified_sites
            WHERE country IS NOT NULL AND country != ''
            ORDER BY country
            LIMIT 200
        """))

        countries = [row.country for row in result if row.country]
        return {"countries": countries}
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching countries: {e}")
        return {"countries": []}
