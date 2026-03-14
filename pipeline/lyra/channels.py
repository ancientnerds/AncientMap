"""YouTube channel management for the Lyra news pipeline.

Channel list lives in channels.json at the repo root.
To suggest a new channel, add a {"id": "...", "name": "..."} entry and open a PR.
"""

import json
import logging
from pathlib import Path

from pipeline.database import NewsChannel, NewsItem, NewsVideo, get_session

logger = logging.getLogger(__name__)

CHANNELS_JSON = Path(__file__).resolve().parent / "channels.json"


def _load_seed_channels() -> list[dict]:
    """Load the channel list from channels.json."""
    with open(CHANNELS_JSON, encoding="utf-8") as f:
        return json.load(f)


def seed_channels() -> None:
    """Sync database channels with channels.json.

    Adds new channels and removes channels (plus their videos and news items)
    that are no longer in channels.json.
    """
    channels = _load_seed_channels()
    wanted_ids = {ch["id"] for ch in channels}
    with get_session() as session:
        existing = {c.id for c in session.query(NewsChannel.id).all()}

        # Add new channels
        added = 0
        for ch in channels:
            if ch["id"] not in existing:
                session.add(
                    NewsChannel(
                        id=ch["id"],
                        name=ch["name"],
                    )
                )
                added += 1

        # Remove channels no longer in channels.json
        stale_ids = existing - wanted_ids
        removed = 0
        for channel_id in stale_ids:
            channel = session.query(NewsChannel).get(channel_id)
            if channel:
                # Delete news_items for this channel's videos
                video_ids = [
                    v.id
                    for v in session.query(NewsVideo.id)
                    .filter(NewsVideo.channel_id == channel_id)
                    .all()
                ]
                if video_ids:
                    session.query(NewsItem).filter(
                        NewsItem.video_id.in_(video_ids)
                    ).delete(synchronize_session=False)
                # Delete videos
                session.query(NewsVideo).filter(
                    NewsVideo.channel_id == channel_id
                ).delete(synchronize_session=False)
                # Delete channel
                session.delete(channel)
                removed += 1
                logger.info(f"Removed channel: {channel.name} ({channel_id})")

        if added:
            logger.info(f"Seeded {added} new channels")
        if removed:
            logger.info(f"Removed {removed} stale channels")
        if not added and not removed:
            logger.info("All channels already in sync")


def get_enabled_channels() -> list[NewsChannel]:
    """Return all enabled channels from the database."""
    with get_session() as session:
        channels = session.query(NewsChannel).filter(NewsChannel.enabled.is_(True)).all()
        # Detach from session so they can be used after session closes
        session.expunge_all()
        return channels
