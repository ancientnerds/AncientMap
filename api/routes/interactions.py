"""
Site interaction endpoints: likes (public counter) and bookmarks (private).
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, text

from api.services.jwt_auth import get_current_user, get_optional_user
from pipeline.database import DiscordUser, SiteBookmark, SiteLike, get_session

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/sites/{site_id}/status")
def get_site_interaction_status(
    site_id: UUID,
    user: DiscordUser | None = Depends(get_optional_user),
):
    """Get like count and current user's like/bookmark status for a site."""
    with get_session() as session:
        like_count = session.query(func.count(SiteLike.id)).filter(
            SiteLike.site_id == site_id,
        ).scalar()

        liked = False
        bookmarked = False
        if user:
            liked = session.query(
                session.query(SiteLike).filter(
                    SiteLike.user_id == user.id,
                    SiteLike.site_id == site_id,
                ).exists()
            ).scalar()
            bookmarked = session.query(
                session.query(SiteBookmark).filter(
                    SiteBookmark.user_id == user.id,
                    SiteBookmark.site_id == site_id,
                ).exists()
            ).scalar()

    return {"like_count": like_count, "liked": liked, "bookmarked": bookmarked}


@router.post("/sites/{site_id}/like")
def toggle_like(
    site_id: UUID,
    user: DiscordUser = Depends(get_current_user),
):
    """Toggle the current user's like on a site. Returns new state + count."""
    with get_session() as session:
        existing = session.query(SiteLike).filter(
            SiteLike.user_id == user.id,
            SiteLike.site_id == site_id,
        ).first()

        if existing:
            session.delete(existing)
            liked = False
        else:
            session.add(SiteLike(user_id=user.id, site_id=site_id))
            liked = True

        session.flush()
        like_count = session.query(func.count(SiteLike.id)).filter(
            SiteLike.site_id == site_id,
        ).scalar()
        session.commit()

    return {"liked": liked, "like_count": like_count}


@router.post("/sites/{site_id}/bookmark")
def toggle_bookmark(
    site_id: UUID,
    user: DiscordUser = Depends(get_current_user),
):
    """Toggle the current user's bookmark on a site."""
    with get_session() as session:
        existing = session.query(SiteBookmark).filter(
            SiteBookmark.user_id == user.id,
            SiteBookmark.site_id == site_id,
        ).first()

        if existing:
            session.delete(existing)
            bookmarked = False
        else:
            session.add(SiteBookmark(user_id=user.id, site_id=site_id))
            bookmarked = True

        session.commit()

    return {"bookmarked": bookmarked}
