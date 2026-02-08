"""YouTube channel management for the Lyra news pipeline.

Channel list lives in channels.json at the repo root.
To suggest a new channel, add a {"id": "...", "name": "..."} entry and open a PR.
"""

import json
import logging
from pathlib import Path

from pipeline.database import NewsChannel, get_session

logger = logging.getLogger(__name__)

CHANNELS_JSON = Path(__file__).resolve().parent / "channels.json"


def _load_seed_channels() -> list[dict]:
    """Load the channel list from channels.json."""
    with open(CHANNELS_JSON, encoding="utf-8") as f:
        return json.load(f)


def seed_channels() -> None:
    """Insert seed channels into the database if they don't already exist."""
    channels = _load_seed_channels()
    with get_session() as session:
        existing = {c.id for c in session.query(NewsChannel.id).all()}
        added = 0
        for ch in channels:
            if ch["id"] not in existing:
                session.add(NewsChannel(
                    id=ch["id"],
                    name=ch["name"],
                ))
                added += 1
        if added:
            logger.info(f"Seeded {added} new channels")
        else:
            logger.info("All channels already present")


def get_enabled_channels() -> list[NewsChannel]:
    """Return all enabled channels from the database."""
    with get_session() as session:
        channels = session.query(NewsChannel).filter(NewsChannel.enabled.is_(True)).all()
        # Detach from session so they can be used after session closes
        session.expunge_all()
        return channels
