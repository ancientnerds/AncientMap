"""
Site interaction endpoints: likes (public counter) and bookmarks (private).
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, text

from api.services.jwt_auth import get_current_user, get_optional_user
from pipeline.database import DiscordUser, SiteBookmark, SiteLike, UnifiedSite, get_session

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

        new_achievements = []
        if liked:
            from api.cardgame.achievements import check_achievements
            new_achievements = check_achievements(session, user.id, "site_like")

        session.commit()

    return {"liked": liked, "like_count": like_count, "achievements_unlocked": new_achievements}


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

        new_achievements = []
        if bookmarked:
            from api.cardgame.achievements import check_achievements
            new_achievements = check_achievements(session, user.id, "site_bookmark")

        session.commit()

    return {"bookmarked": bookmarked, "achievements_unlocked": new_achievements}


def _site_summary(site: UnifiedSite) -> dict:
    return {
        "id": str(site.id),
        "name": site.name,
        "country": site.country,
        "site_type": site.site_type,
        "thumbnail_url": site.thumbnail_url,
        "lat": site.lat,
        "lon": site.lon,
    }


@router.get("/me/likes")
def get_my_likes(user: DiscordUser = Depends(get_current_user)):
    """List all sites the current user has liked."""
    with get_session() as session:
        rows = (
            session.query(UnifiedSite, SiteLike.created_at)
            .join(SiteLike, SiteLike.site_id == UnifiedSite.id)
            .filter(SiteLike.user_id == user.id)
            .order_by(SiteLike.created_at.desc())
            .all()
        )
        return [
            {**_site_summary(site), "liked_at": liked_at.isoformat()}
            for site, liked_at in rows
        ]


@router.get("/me/bookmarks")
def get_my_bookmarks(user: DiscordUser = Depends(get_current_user)):
    """List all sites the current user has bookmarked."""
    with get_session() as session:
        rows = (
            session.query(UnifiedSite, SiteBookmark.created_at)
            .join(SiteBookmark, SiteBookmark.site_id == UnifiedSite.id)
            .filter(SiteBookmark.user_id == user.id)
            .order_by(SiteBookmark.created_at.desc())
            .all()
        )
        return [
            {**_site_summary(site), "bookmarked_at": bm_at.isoformat()}
            for site, bm_at in rows
        ]
