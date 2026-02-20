"""
Patreon webhook handler for credit tier subscriptions.

Endpoint:
- POST /api/patreon/webhook — receives Patreon webhook events

Events handled:
- members:pledge:create  — new patron, grant credits
- members:pledge:update  — tier change, grant credits for new tier
- members:pledge:delete  — patron cancelled (log only, no clawback)
"""

import hashlib
import hmac
import logging
import os
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request

from api.routes.auth import CREDIT_ROLES
from pipeline.database import CreditGrant, DiscordUser, PatreonEvent, get_session

logger = logging.getLogger(__name__)

router = APIRouter()

PATREON_WEBHOOK_SECRET = os.getenv("PATREON_WEBHOOK_SECRET", "")

# Map Patreon tier amount (cents) to Discord role credit config reason
# This lets us grant credits immediately on webhook without waiting for role sync
# Credits per tier: Explorer=2,500, Archaeologist=5,000, Scholar=12,500
_TIER_CENTS_TO_REASON: dict[int, str] = {
    500: "monthly_patron_explorer",      # $5 → 5,000 credits (~40-80 questions)
    1000: "monthly_patron_archaeologist",  # $10 → 15,000 credits (~125-250 questions)
    2500: "monthly_patron_scholar",        # $25 → 50,000 credits (~415-830 questions)
}


def _verify_signature(body: bytes, signature: str) -> bool:
    """Verify Patreon webhook HMAC-MD5 signature."""
    if not PATREON_WEBHOOK_SECRET:
        return False
    expected = hmac.new(
        PATREON_WEBHOOK_SECRET.encode(), body, hashlib.md5,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/webhook")
async def patreon_webhook(request: Request):
    """Handle Patreon webhook events."""
    if not PATREON_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Patreon webhooks not configured")

    # Verify signature
    signature = request.headers.get("X-Patreon-Signature", "")
    body = await request.body()
    if not _verify_signature(body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Parse event
    event_type = request.headers.get("X-Patreon-Event", "")
    payload = await request.json()

    # Extract event ID for idempotency (Patreon doesn't always send one, use a composite)
    data = payload.get("data", {})
    event_id = data.get("id", "")
    if not event_id:
        raise HTTPException(status_code=400, detail="Missing event ID")

    # Make event_id unique per event type
    full_event_id = f"{event_type}:{event_id}"

    # Extract patron info
    included = payload.get("included", [])
    patron_email = None
    discord_id = None
    tier_amount_cents = 0

    # Get pledge amount from data attributes
    attrs = data.get("attributes", {})
    tier_amount_cents = attrs.get("currently_entitled_amount_cents", 0) or attrs.get("amount_cents", 0)

    # Find user and social connections in included resources
    for item in included:
        item_type = item.get("type", "")
        item_attrs = item.get("attributes", {})

        if item_type == "user":
            patron_email = item_attrs.get("email")
            # Check social connections for Discord
            social = item_attrs.get("social_connections", {})
            discord_info = social.get("discord")
            if discord_info and isinstance(discord_info, dict):
                discord_id = discord_info.get("user_id")

    # Idempotency check
    with get_session() as session:
        existing = session.query(PatreonEvent).filter(
            PatreonEvent.event_id == full_event_id,
        ).first()
        if existing:
            return {"ok": True, "message": "Event already processed"}

        # Log the event
        session.add(PatreonEvent(
            event_id=full_event_id,
            event_type=event_type,
            patron_email=patron_email,
            discord_id=discord_id,
            tier_amount_cents=tier_amount_cents,
        ))
        session.commit()

    if event_type == "members:pledge:delete":
        logger.info(f"Patron cancelled: email={patron_email}, discord={discord_id}")
        return {"ok": True, "message": "Pledge deletion logged"}

    if event_type not in ("members:pledge:create", "members:pledge:update"):
        logger.info(f"Ignoring Patreon event: {event_type}")
        return {"ok": True, "message": "Event type not handled"}

    # Try to grant credits immediately if we have a Discord ID
    if not discord_id:
        logger.warning(f"Patreon pledge event but no Discord ID: email={patron_email}")
        return {"ok": True, "message": "No Discord ID — credits will be granted on next login"}

    reason = _TIER_CENTS_TO_REASON.get(tier_amount_cents)
    if not reason:
        logger.warning(f"Unknown tier amount: {tier_amount_cents} cents for discord={discord_id}")
        return {"ok": True, "message": "Unknown tier amount"}

    # Find the CREDIT_ROLES config matching this tier's reason
    role_config = next((cfg for cfg in CREDIT_ROLES.values() if cfg["reason"] == reason), None)
    if not role_config:
        logger.warning(f"No CREDIT_ROLES config for reason={reason}")
        return {"ok": True, "message": "No matching credit config"}

    monthly_amount = role_config["amount"]
    cap_multiplier = role_config.get("cap_multiplier", 3)
    max_balance = monthly_amount * cap_multiplier

    with get_session() as session:
        user = session.query(DiscordUser).filter(
            DiscordUser.discord_id == discord_id,
        ).first()
        if not user:
            logger.info(f"Discord user {discord_id} not in DB yet — credits granted on next login")
            return {"ok": True, "message": "User not registered yet"}

        now = datetime.now(UTC)
        period = f"{now.year:04d}-{now.month:02d}"

        # Reset anchor if this is a new/returning patron (no anchor yet)
        if user.grant_anchor_date is None:
            user.grant_anchor_date = now

        # Idempotency: check if this period + reason was already granted
        existing = session.query(CreditGrant).filter(
            CreditGrant.user_id == user.id,
            CreditGrant.reason == reason,
            CreditGrant.grant_period == period,
        ).first()
        if existing:
            logger.info(f"Credits already granted for {user.username} ({reason}, period={period})")
            return {"ok": True, "message": "Credits already granted for this period"}

        effective = min(monthly_amount, max(0, max_balance - user.credits))
        if effective > 0:
            user.credits += effective
            session.add(CreditGrant(
                user_id=user.id,
                amount=effective,
                reason=reason,
                grant_period=period,
            ))
            logger.info(f"Webhook granted {effective} credits to {user.username} ({reason}, period={period})")
        else:
            logger.info(f"Credit cap reached for {user.username}, no grant ({reason}, period={period})")

        session.commit()

    return {"ok": True, "message": "Credits processed"}
