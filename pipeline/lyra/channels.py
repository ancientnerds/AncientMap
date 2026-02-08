"""YouTube channel management for the Lyra news pipeline."""

import logging

from pipeline.database import NewsChannel, get_session

logger = logging.getLogger(__name__)

# Seed channels from the original Lyra channels.json
SEED_CHANNELS = [
    {"id": "UCscI4NOggNSN-Si5QgErNCw", "name": "Ancient Architects"},
    {"id": "UCxq9PsBVarBK9BpG9SYQF7w", "name": "Curious Being"},
    {"id": "UCodgvia5IT5wiV0II9swBLw", "name": "DeDunking"},
    {"id": "UCsIlJ9eYylZQcyfMOPNUz9w", "name": "Bright Insight"},
    {"id": "UCDWboBDVnIsGdYSK3KUO0hQ", "name": "History for GRANITE"},
    {"id": "UCmhg8Hd2vOHwH3Pi3_9fYag", "name": "Wandering Wolf"},
    {"id": "UCqMVaZM-USi0G54pu5318dQ", "name": "MegalithomaniaUK"},
    {"id": "UCN2Z_nuG5XtVnE998unA3PA", "name": "Funny Olde World"},
    {"id": "UCOnnmKlDZltHAqJLz-XIpGA", "name": "Universe Inside You"},
    {"id": "UC8QWOIcinxsrvMGlWox7bXg", "name": "Dark5 Ancient Mysteries"},
    {"id": "UC2Stn8atEra7SMdPWyQoSLA", "name": "UnchartedX"},
    {"id": "UCMwDeEoupy8QQpKKc8pzU_Q", "name": "History with Kayleigh"},
    {"id": "UCLclaVGVpaNIbdQaRs1wC5Q", "name": "One-eyed giant building walls"},
    {"id": "UC452QHC05BAbQZZlYDUaoAA", "name": "Institute for Natural Philosophy"},
    {"id": "UCgMfHNvlc4Zvr8FJHopDnvA", "name": "History, Myths & Legends"},
    {"id": "UCFestibN7lYXvEj_BMEh29w", "name": "Luke Caverns"},
    {"id": "UC65XXzhHyH3BKZ72Q1eKF8Q", "name": "Matthew LaCroix"},
    {"id": "UC9qJWqnmPhDLnZNllSQ8uQA", "name": "Nikkiana Jones"},
    {"id": "UCRDZ_t_-uHLsz_Otq6iOgyg", "name": "Michael Button"},
    {"id": "UCAPciy143ZBXBrFpCVPnWDg", "name": "The Randall Carlson"},
    {"id": "UCQoVoWXj6jyibI3gs3J4rbg", "name": "SPIRIT in STONE"},
]


def seed_channels() -> None:
    """Insert seed channels into the database if they don't already exist."""
    with get_session() as session:
        existing = {c.id for c in session.query(NewsChannel.id).all()}
        added = 0
        for ch in SEED_CHANNELS:
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
