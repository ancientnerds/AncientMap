"""FastAPI router — all /api/cards/* endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func

from api.cardgame.constants import (
    EMPIRE_DESCRIPTIONS,
    EMPIRE_DISPLAY_NAMES,
    EMPIRE_PERIODS,
    EMPIRE_THEMATIC_STATS,
    PACK_PRICES,
    RARITY_NAMES,
    get_level,
)
from api.cardgame.models import (
    CardBattle,
    CardCollection,
    CardDeck,
    CardPlayerStats,
    CardStats,
)
from api.services.jwt_auth import get_current_user, get_optional_user
from api.services.rate_limiter import RateLimiter
from pipeline.database import DiscordUser, UnifiedSite, get_session
from pipeline.historical_boundaries.empire_metadata import EMPIRE_METADATA
from pipeline.utils.country_lookup import normalize_country

router = APIRouter()

_pack_limiter = RateLimiter(max_requests=10, window_seconds=60, namespace="card_packs")
_quiz_limiter = RateLimiter(max_requests=10, window_seconds=60, namespace="card_quiz")
_daily_limiter = RateLimiter(max_requests=5, window_seconds=60, namespace="card_daily")
_starter_limiter = RateLimiter(max_requests=3, window_seconds=60, namespace="card_starter")
_expedition_limiter = RateLimiter(max_requests=10, window_seconds=60, namespace="card_expedition")


# ---------------------------------------------------------------------------
# Request/response schemas
# ---------------------------------------------------------------------------

class PackOpenRequest(BaseModel):
    pack_type: str = Field(max_length=20)


class DeckCreateRequest(BaseModel):
    name: str = Field(max_length=100)
    card_ids: list[str] = Field(max_length=10)


class QuizAnswerRequest(BaseModel):
    session_id: str = Field(max_length=50)
    answers: list[str] = Field(max_length=20)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _card_stats_to_dict(card: CardStats, site: UnifiedSite | None = None) -> dict:
    """Serialize a CardStats row to a response dict."""
    d = {
        "site_id": str(card.site_id),
        "antiquity": card.antiquity,
        "fortification": card.fortification,
        "cultural_influence": card.cultural_influence,
        "mystery": card.mystery,
        "legacy": card.legacy,
        "total_power": card.total_power,
        "rarity_tier": card.rarity_tier,
        "rarity_name": RARITY_NAMES.get(card.rarity_tier, "Common"),
        "category_group": card.category_group,
        "civilization": card.civilization,
    }
    if site:
        d.update({
            "name": site.name,
            "country": site.country,
            "country_code": normalize_country(site.country) if site.country else None,
            "period_name": site.period_name,
            "period_start": site.period_start,
            "thumbnail_url": site.thumbnail_url,
            "site_type": site.site_type,
            "lat": site.lat,
            "lon": site.lon,
        })
    return d


def _get_client_ip(request: Request) -> str:
    """Extract client IP. Only trust X-Forwarded-For from loopback (nginx proxy)."""
    if request.client and request.client.host in ("127.0.0.1", "::1"):
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------

@router.get("/random")
def get_random_cards(count: int = Query(100, ge=1, le=200)):
    """Get random site cards (public, no auth)."""
    with get_session() as session:
        rows = (
            session.query(CardStats, UnifiedSite)
            .join(UnifiedSite, CardStats.site_id == UnifiedSite.id)
            .order_by(func.random())
            .limit(count)
            .all()
        )
        cards = []
        for card, site in rows:
            d = _card_stats_to_dict(card, site)
            d["star_level"] = 0
            d["card_xp"] = 0
            cards.append(d)
        return {"cards": cards}


@router.get("/empires/all")
def get_all_empires():
    """Get all empire cards (public, no auth)."""
    empires = []
    for empire_id, name in EMPIRE_DISPLAY_NAMES.items():
        meta = EMPIRE_METADATA.get(empire_id, {})
        empires.append({
            "id": empire_id,
            "name": name,
            "region": meta.get("region", ""),
            "thematic_stat": EMPIRE_THEMATIC_STATS.get(empire_id, "mystery"),
            "period": EMPIRE_PERIODS.get(empire_id, ""),
            "description": EMPIRE_DESCRIPTIONS.get(empire_id, ""),
        })
    return {"empires": empires}


@router.get("/stats/{site_id}")
def get_card_stats(site_id: str):
    """Get card stats for any site (public)."""
    try:
        sid = uuid.UUID(site_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid site ID") from e

    with get_session() as session:
        card = session.get(CardStats, sid)
        if not card:
            raise HTTPException(status_code=404, detail="Card not found")

        site = session.get(UnifiedSite, sid)
        return _card_stats_to_dict(card, site)


@router.get("/leaderboard")
def get_leaderboard(
    sort: str = Query("wins", regex="^(wins|cards|power|streak)$"),
    limit: int = Query(20, ge=1, le=100),
):
    """Top players leaderboard (public)."""
    with get_session() as session:
        query = (
            session.query(CardPlayerStats, DiscordUser)
            .join(DiscordUser, CardPlayerStats.user_id == DiscordUser.id)
        )

        if sort == "wins":
            query = query.order_by(CardPlayerStats.wins.desc())
        elif sort == "cards":
            query = query.order_by(CardPlayerStats.total_cards.desc())
        elif sort == "power":
            query = query.order_by(CardPlayerStats.xp.desc())
        elif sort == "streak":
            query = query.order_by(CardPlayerStats.best_streak.desc())

        rows = query.limit(limit).all()

        result = []
        for ps, user in rows:
            result.append({
                "username": user.username if user else "Unknown",
                "avatar_hash": user.avatar_hash if user else None,
                "wins": ps.wins,
                "losses": ps.losses,
                "draws": ps.draws,
                "total_cards": ps.total_cards,
                "xp": ps.xp,
                "best_streak": ps.best_streak,
                "daily_streak": ps.daily_streak,
            })

        return {"leaderboard": result}


# ---------------------------------------------------------------------------
# Authenticated endpoints
# ---------------------------------------------------------------------------

@router.get("/collection")
def get_collection(
    user: DiscordUser = Depends(get_current_user),
    rarity: int | None = Query(None, ge=1, le=5),
    group: str | None = Query(None),
    civilization: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """Get user's card collection (paginated, filterable)."""
    with get_session() as session:
        query = (
            session.query(CardCollection, CardStats, UnifiedSite)
            .join(CardStats, CardCollection.site_id == CardStats.site_id)
            .join(UnifiedSite, CardCollection.site_id == UnifiedSite.id)
            .filter(CardCollection.user_id == user.id)
        )

        if rarity is not None:
            query = query.filter(CardStats.rarity_tier == rarity)
        if group:
            query = query.filter(CardStats.category_group == group)
        if civilization:
            query = query.filter(CardStats.civilization.ilike(f"%{civilization}%"))

        total = query.count()
        rows = (
            query
            .order_by(CardStats.rarity_tier.desc(), CardStats.total_power.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        cards = []
        for coll, card, site in rows:
            d = _card_stats_to_dict(card, site)
            d["acquired_via"] = coll.acquired_via
            d["acquired_at"] = coll.created_at.isoformat() if coll.created_at else None
            d["star_level"] = coll.star_level
            d["card_xp"] = coll.card_xp
            cards.append(d)

        return {
            "cards": cards,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        }


@router.post("/pack/open")
def open_pack_endpoint(
    body: PackOpenRequest,
    request: Request,
    user: DiscordUser = Depends(get_current_user),
):
    """Open a card pack."""
    if not _pack_limiter.check(_get_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many pack openings, slow down")

    from api.cardgame.packs import (
        InsufficientCreditsError,
        InvalidPackTypeError,
        open_pack,
    )

    with get_session() as session:
        # Re-fetch user inside session
        db_user = session.query(DiscordUser).filter(DiscordUser.id == user.id).first()
        if not db_user:
            raise HTTPException(status_code=401, detail="User not found")

        try:
            cards = open_pack(session, db_user, body.pack_type)
        except InvalidPackTypeError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        except InsufficientCreditsError as e:
            raise HTTPException(status_code=402, detail=str(e)) from None

        from api.cardgame.achievements import check_achievements
        new_achievements = check_achievements(session, db_user.id, "pack_open")

        return {
            "cards": cards,
            "credits_remaining": db_user.credits,
            "pack_type": body.pack_type,
            "achievements_unlocked": new_achievements,
        }


@router.get("/decks")
def get_decks(user: DiscordUser = Depends(get_current_user)):
    """List user's decks."""
    with get_session() as session:
        decks = (
            session.query(CardDeck)
            .filter(CardDeck.user_id == user.id)
            .order_by(CardDeck.created_at)
            .all()
        )
        return {
            "decks": [
                {
                    "id": str(d.id),
                    "name": d.name,
                    "is_active": d.is_active,
                    "card_ids": d.card_ids,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                }
                for d in decks
            ]
        }


@router.post("/decks")
def create_or_update_deck(
    body: DeckCreateRequest,
    user: DiscordUser = Depends(get_current_user),
):
    """Create or update a deck (max 3 per user, max 10 cards)."""
    card_ids = list(dict.fromkeys(body.card_ids))  # deduplicate preserving order
    if len(card_ids) > 10:
        raise HTTPException(status_code=400, detail="Deck can have at most 10 cards")

    with get_session() as session:
        # Verify all cards are owned by user
        owned = {
            str(r[0]) for r in
            session.query(CardCollection.site_id)
            .filter(CardCollection.user_id == user.id)
            .all()
        }
        for cid in card_ids:
            if cid not in owned:
                raise HTTPException(status_code=400, detail=f"You don't own card {cid}")

        # Check deck count
        deck_count = (
            session.query(CardDeck)
            .filter(CardDeck.user_id == user.id)
            .count()
        )
        if deck_count >= 3:
            raise HTTPException(status_code=400, detail="Maximum 3 decks allowed")

        deck = CardDeck(
            user_id=user.id,
            name=body.name,
            card_ids=card_ids,
        )
        session.add(deck)
        session.flush()

        return {
            "id": str(deck.id),
            "name": deck.name,
            "card_ids": deck.card_ids,
        }


@router.put("/decks/{deck_id}")
def update_deck(
    deck_id: str,
    body: DeckCreateRequest,
    user: DiscordUser = Depends(get_current_user),
):
    """Update an existing deck's name and cards."""
    card_ids = list(dict.fromkeys(body.card_ids))  # deduplicate preserving order
    if len(card_ids) > 10:
        raise HTTPException(status_code=400, detail="Deck can have at most 10 cards")

    try:
        did = uuid.UUID(deck_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid deck ID") from e

    with get_session() as session:
        deck = session.get(CardDeck, did)
        if not deck or deck.user_id != user.id:
            raise HTTPException(status_code=404, detail="Deck not found")

        # Verify all cards are owned by user
        owned = {
            str(r[0]) for r in
            session.query(CardCollection.site_id)
            .filter(CardCollection.user_id == user.id)
            .all()
        }
        for cid in card_ids:
            if cid not in owned:
                raise HTTPException(status_code=400, detail=f"You don't own card {cid}")

        deck.name = body.name
        deck.card_ids = card_ids

        return {
            "id": str(deck.id),
            "name": deck.name,
            "card_ids": deck.card_ids,
        }


@router.delete("/decks/{deck_id}")
def delete_deck(
    deck_id: str,
    user: DiscordUser = Depends(get_current_user),
):
    """Delete a deck."""
    try:
        did = uuid.UUID(deck_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid deck ID") from e

    with get_session() as session:
        deck = session.get(CardDeck, did)
        if not deck or deck.user_id != user.id:
            raise HTTPException(status_code=404, detail="Deck not found")

        session.delete(deck)
        return {"deleted": True}


@router.put("/decks/{deck_id}/activate")
def activate_deck(
    deck_id: str,
    user: DiscordUser = Depends(get_current_user),
):
    """Set a deck as the active deck."""
    try:
        did = uuid.UUID(deck_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid deck ID") from e

    with get_session() as session:
        deck = session.get(CardDeck, did)
        if not deck or deck.user_id != user.id:
            raise HTTPException(status_code=404, detail="Deck not found")

        # Deactivate all other decks
        session.query(CardDeck).filter(
            CardDeck.user_id == user.id,
            CardDeck.id != did,
        ).update({"is_active": False})

        deck.is_active = True

        return {"id": str(deck.id), "is_active": True}


@router.get("/player-stats")
def get_player_stats(user: DiscordUser = Depends(get_current_user)):
    """Get current user's player stats."""
    with get_session() as session:
        ps = session.get(CardPlayerStats, user.id)
        if not ps:
            level, xp_progress, xp_to_next = get_level(0)
            return {
                "total_cards": 0, "wins": 0, "losses": 0, "draws": 0,
                "win_streak": 0, "best_streak": 0, "xp": 0,
                "daily_streak": 0, "packs_opened": 0,
                "level": level, "xp_progress": xp_progress, "xp_to_next": xp_to_next,
            }
        level, xp_progress, xp_to_next = get_level(ps.xp)
        return {
            "total_cards": ps.total_cards,
            "wins": ps.wins,
            "losses": ps.losses,
            "draws": ps.draws,
            "win_streak": ps.win_streak,
            "best_streak": ps.best_streak,
            "xp": ps.xp,
            "daily_streak": ps.daily_streak,
            "packs_opened": ps.packs_opened,
            "level": level,
            "xp_progress": xp_progress,
            "xp_to_next": xp_to_next,
        }


@router.post("/starter")
def claim_starter(request: Request, user: DiscordUser = Depends(get_current_user)):
    """Claim starter deck (once per user)."""
    if not _starter_limiter.check(_get_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many requests, slow down")
    from api.cardgame.rewards import AlreadyHasStarterError, claim_starter_deck

    with get_session() as session:
        db_user = session.query(DiscordUser).filter(DiscordUser.id == user.id).first()
        if not db_user:
            raise HTTPException(status_code=401, detail="User not found")

        try:
            cards = claim_starter_deck(session, db_user)
        except AlreadyHasStarterError as e:
            raise HTTPException(status_code=409, detail=str(e)) from None

        from api.cardgame.achievements import check_achievements
        new_achievements = check_achievements(session, db_user.id, "starter_claim")

        return {"cards": cards, "count": len(cards), "achievements_unlocked": new_achievements}


@router.post("/daily")
def claim_daily_endpoint(request: Request, user: DiscordUser = Depends(get_current_user)):
    """Claim daily reward."""
    if not _daily_limiter.check(_get_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many requests, slow down")
    from api.cardgame.rewards import AlreadyClaimedError, claim_daily

    with get_session() as session:
        db_user = session.query(DiscordUser).filter(DiscordUser.id == user.id).first()
        if not db_user:
            raise HTTPException(status_code=401, detail="User not found")

        try:
            result = claim_daily(session, db_user)
        except AlreadyClaimedError as e:
            raise HTTPException(status_code=409, detail=str(e)) from None

        from api.cardgame.achievements import check_achievements
        new_achievements = check_achievements(session, db_user.id, "daily_claim")
        result["achievements_unlocked"] = new_achievements

        return result


@router.get("/packs")
def get_pack_info():
    """Get available pack types and prices (public)."""
    return {
        "packs": {
            name: {
                "cost": p["cost"],
                "cards": p["cards"],
                "guarantees": [
                    RARITY_NAMES.get(t, "Common") for t in p["guarantees"]
                ],
            }
            for name, p in PACK_PRICES.items()
        }
    }


# ---------------------------------------------------------------------------
# Synergy preview (Phase A)
# ---------------------------------------------------------------------------

@router.post("/deck-synergies")
def preview_deck_synergies(
    body: DeckCreateRequest,
    user: DiscordUser = Depends(get_current_user),
):
    """Preview synergies for a set of card_ids (deck builder helper)."""
    from api.cardgame.synergies import compute_synergies, describe_synergies

    with get_session() as session:
        cards = []
        for cid in body.card_ids:
            try:
                card = session.get(CardStats, uuid.UUID(cid))
            except ValueError:
                continue
            if card:
                cards.append(card)

        if not cards:
            return {"synergies": [], "bonuses": {}}

        bonuses = compute_synergies(cards)
        descriptions = describe_synergies(cards)

        return {
            "synergies": descriptions,
            "bonuses": bonuses,
        }


# ---------------------------------------------------------------------------
# Quiz endpoints (Phase C)
# ---------------------------------------------------------------------------

@router.post("/quiz/start")
def start_quiz(
    request: Request,
    user: DiscordUser = Depends(get_current_user),
):
    """Start a new quiz session."""
    if not _quiz_limiter.check(_get_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many quiz requests, slow down")

    from api.cardgame.quiz import QuizLimitReachedError, generate_quiz

    with get_session() as session:
        db_user = session.query(DiscordUser).filter(DiscordUser.id == user.id).first()
        if not db_user:
            raise HTTPException(status_code=401, detail="User not found")

        try:
            quiz_data = generate_quiz(session, db_user.id)
        except QuizLimitReachedError as e:
            raise HTTPException(status_code=429, detail=str(e)) from None

        return quiz_data


@router.post("/quiz/submit")
def submit_quiz(
    body: QuizAnswerRequest,
    user: DiscordUser = Depends(get_current_user),
):
    """Submit quiz answers and get results + rewards."""
    from api.cardgame.quiz import QuizAlreadySubmittedError, submit_quiz_answers

    with get_session() as session:
        db_user = session.query(DiscordUser).filter(DiscordUser.id == user.id).first()
        if not db_user:
            raise HTTPException(status_code=401, detail="User not found")

        try:
            result = submit_quiz_answers(session, db_user, body.session_id, body.answers)
        except QuizAlreadySubmittedError as e:
            raise HTTPException(status_code=409, detail=str(e)) from None
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None

        from api.cardgame.achievements import check_achievements
        new_achievements = check_achievements(session, db_user.id, "quiz_submit")
        result["achievements_unlocked"] = new_achievements

        return result


# ---------------------------------------------------------------------------
# Expedition endpoints (Phase D)
# ---------------------------------------------------------------------------

@router.get("/expeditions")
def list_expeditions(
    user: DiscordUser = Depends(get_optional_user),
):
    """List all expeditions with optional user progress."""
    from api.cardgame.expedition import get_available_expeditions, get_expedition_progress

    expeditions = get_available_expeditions()

    if user:
        with get_session() as session:
            progress = get_expedition_progress(session, user.id)
        # Merge progress into expedition list
        progress_map = {p["expedition_id"]: p for p in progress}
        for exp in expeditions:
            p = progress_map.get(exp["id"], {})
            exp["current_stage"] = p.get("current_stage", 0)
            exp["completed"] = p.get("completed", False)

    return {"expeditions": expeditions}


@router.post("/expeditions/{expedition_id}/play")
def play_expedition(
    expedition_id: str,
    request: Request,
    user: DiscordUser = Depends(get_current_user),
):
    """Play the next stage of an expedition."""
    if not _expedition_limiter.check(_get_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many requests, slow down")
    from api.cardgame.expedition import play_expedition_stage

    with get_session() as session:
        db_user = session.query(DiscordUser).filter(DiscordUser.id == user.id).first()
        if not db_user:
            raise HTTPException(status_code=401, detail="User not found")

        try:
            result = play_expedition_stage(session, db_user, expedition_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None

        from api.cardgame.achievements import check_achievements
        new_achievements = check_achievements(session, db_user.id, "expedition_stage")
        result["achievements_unlocked"] = new_achievements

        return result


# ---------------------------------------------------------------------------
# Achievement endpoints
# ---------------------------------------------------------------------------

_achievement_limiter = RateLimiter(max_requests=10, window_seconds=60, namespace="achievements")
_achievement_event_limiter = RateLimiter(max_requests=30, window_seconds=60, namespace="achievement_events")


class AchievementEventRequest(BaseModel):
    event_type: str = Field(max_length=50)
    layer_count: int | None = None


@router.get("/achievements")
def get_achievements(
    user: DiscordUser | None = Depends(get_optional_user),
):
    """Full achievement list with user unlock/claim status.

    If authenticated, runs a retroactive full check to auto-unlock
    achievements the user already qualifies for.
    """
    from api.cardgame.achievements import ACHIEVEMENTS, check_achievements
    from api.cardgame.models import UserAchievement

    unlocked_map: dict[str, dict] = {}

    if user:
        with get_session() as session:
            # Retroactive check — unlocks anything the user already qualifies for
            check_achievements(session, user.id, "full_check")

            rows = (
                session.query(UserAchievement)
                .filter(UserAchievement.user_id == user.id)
                .all()
            )
            for ua in rows:
                unlocked_map[ua.achievement_id] = {
                    "unlocked_at": ua.unlocked_at.isoformat() if ua.unlocked_at else None,
                    "claimed": ua.claimed,
                    "claimed_at": ua.claimed_at.isoformat() if ua.claimed_at else None,
                }

    achievements = []
    for aid, a in ACHIEVEMENTS.items():
        entry = {
            "id": aid,
            "category": a["category"],
            "name": a["name"],
            "description": a["description"],
            "tier": a["tier"],
            "reward_credits": a["reward_credits"],
            "reward_xp": a["reward_xp"],
            "reward_card_tier": a["reward_card_tier"],
            "reward_card_count": a["reward_card_count"],
            "icon": a["icon"],
            "sort_order": a["sort_order"],
            "hidden": a["hidden"],
        }
        u = unlocked_map.get(aid)
        if u:
            entry["unlocked"] = True
            entry["unlocked_at"] = u["unlocked_at"]
            entry["claimed"] = u["claimed"]
            entry["claimed_at"] = u["claimed_at"]
        else:
            entry["unlocked"] = False
            entry["claimed"] = False
        achievements.append(entry)

    return {"achievements": achievements, "total": len(achievements)}


@router.post("/achievements/{achievement_id}/claim")
def claim_achievement(
    achievement_id: str,
    request: Request,
    user: DiscordUser = Depends(get_current_user),
):
    """Claim rewards for an unlocked achievement."""
    if not _achievement_limiter.check(_get_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many requests, slow down")

    from api.cardgame.achievements import claim_achievement_reward

    with get_session() as session:
        db_user = session.query(DiscordUser).filter(DiscordUser.id == user.id).first()
        if not db_user:
            raise HTTPException(status_code=401, detail="User not found")

        try:
            result = claim_achievement_reward(session, db_user, achievement_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None

        result["credits_remaining"] = db_user.credits
        return result


@router.get("/achievements/summary")
def get_achievements_summary(
    user: DiscordUser = Depends(get_current_user),
):
    """Quick counts: total unlocked, total available, unclaimed count."""
    from api.cardgame.achievements import ACHIEVEMENTS
    from api.cardgame.models import UserAchievement

    with get_session() as session:
        total_unlocked = (
            session.query(UserAchievement)
            .filter(UserAchievement.user_id == user.id)
            .count()
        )
        unclaimed = (
            session.query(UserAchievement)
            .filter(
                UserAchievement.user_id == user.id,
                UserAchievement.claimed.is_(False),
            )
            .count()
        )

    return {
        "total_available": len(ACHIEVEMENTS),
        "total_unlocked": total_unlocked,
        "unclaimed": unclaimed,
    }


@router.post("/achievements/event")
def report_achievement_event(
    body: AchievementEventRequest,
    request: Request,
    user: DiscordUser = Depends(get_current_user),
):
    """Frontend-triggered events for Cartographer/Explorer achievements."""
    if not _achievement_event_limiter.check(_get_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many requests")

    from api.cardgame.achievements import check_achievements
    from api.cardgame.models import CardPlayerStats

    context = {"event_type": body.event_type}
    if body.layer_count is not None:
        context["layer_count"] = body.layer_count

    with get_session() as session:
        # Persist the event in feature_flags for retroactive checks
        ps = session.get(CardPlayerStats, user.id)
        if not ps:
            ps = CardPlayerStats(user_id=user.id)
            session.add(ps)
            session.flush()

        flags = dict(ps.feature_flags or {})
        flags[body.event_type] = True
        if body.layer_count is not None:
            flags["max_layers"] = max(flags.get("max_layers", 0), body.layer_count)
        ps.feature_flags = flags

        new_achievements = check_achievements(session, user.id, "frontend_event", context)

    return {"achievements_unlocked": new_achievements}
