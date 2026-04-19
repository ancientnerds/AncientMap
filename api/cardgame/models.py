"""Card game SQLAlchemy models.

All models import Base from pipeline.database so create_all_tables() picks
them up automatically.  No modifications to pipeline/database.py needed.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from pipeline.database import Base


class CardStats(Base):
    """Precomputed stats per site (1:1 with unified_sites)."""

    __tablename__ = "card_stats"

    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("unified_sites.id", ondelete="CASCADE"),
        primary_key=True,
    )
    antiquity: Mapped[int] = mapped_column(Integer, nullable=False)
    fortification: Mapped[int] = mapped_column(Integer, nullable=False)
    cultural_influence: Mapped[int] = mapped_column(Integer, nullable=False)
    mystery: Mapped[int] = mapped_column(Integer, nullable=False)
    legacy: Mapped[int] = mapped_column(Integer, nullable=False)
    total_power: Mapped[int] = mapped_column(Integer, nullable=False)
    rarity_score: Mapped[int] = mapped_column(Integer, nullable=False)
    rarity_tier: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    category_group: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    civilization: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    empires: Mapped[list | None] = mapped_column(JSONB, default=list, server_default="[]")
    empire_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    card_description: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Enrichment metadata (populated by site enrichment pipeline)
    wikidata_qid: Mapped[str | None] = mapped_column(String(20), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    heritage_designation: Mapped[str | None] = mapped_column(Text, nullable=True)
    inception_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    best_wiki_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    commons_image: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Audit tracking
    last_enriched: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    site: Mapped["UnifiedSite"] = relationship("UnifiedSite", lazy="joined")

    __table_args__ = (Index("idx_card_stats_rarity", "rarity_tier", "rarity_score"),)


class CardCollection(Base):
    """Cards owned by a user."""

    __tablename__ = "card_collections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discord_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("unified_sites.id", ondelete="CASCADE"),
        nullable=False,
    )
    acquired_via: Mapped[str] = mapped_column(String(50), nullable=False)
    # Phase E: Card Evolution
    star_level: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    card_xp: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "site_id", name="uq_card_collection"),
        Index("idx_card_collections_user", "user_id"),
    )


class CardDeck(Base):
    """Saved deck configuration (max 3 per user, 10 cards each)."""

    __tablename__ = "card_decks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discord_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    card_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    commander_empire_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (Index("idx_card_decks_user", "user_id"),)


class CardBattle(Base):
    """Battle history between two players."""

    __tablename__ = "card_battles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    challenger_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discord_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    defender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discord_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
    )
    winner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discord_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    challenger_wins: Mapped[int] = mapped_column(Integer, default=0)
    defender_wins: Mapped[int] = mapped_column(Integer, default=0)
    rounds: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    stake_credits: Mapped[int] = mapped_column(Integer, default=0)
    # Phase B: Snap mechanic
    snap_multiplier: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    snapped_by: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_card_battles_challenger", "challenger_id"),
        Index("idx_card_battles_defender", "defender_id"),
        Index("idx_card_battles_status", "status"),
    )


class CardPlayerStats(Base):
    """Denormalized player stats for quick lookups."""

    __tablename__ = "card_player_stats"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discord_users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    total_cards: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    draws: Mapped[int] = mapped_column(Integer, default=0)
    win_streak: Mapped[int] = mapped_column(Integer, default=0)
    best_streak: Mapped[int] = mapped_column(Integer, default=0)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    daily_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_daily: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    packs_opened: Mapped[int] = mapped_column(Integer, default=0)
    feature_flags: Mapped[dict | None] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CardPackLog(Base):
    """Audit trail for pack openings."""

    __tablename__ = "card_pack_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discord_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    pack_type: Mapped[str] = mapped_column(String(20), nullable=False)
    credits_spent: Mapped[int] = mapped_column(Integer, nullable=False)
    cards_received: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("idx_card_pack_log_user", "user_id"),)


class QuizSession(Base):
    """A single quiz session (Phase C)."""

    __tablename__ = "quiz_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discord_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    questions: Mapped[list] = mapped_column(JSONB, nullable=False)
    answers_key: Mapped[list] = mapped_column(JSONB, nullable=False)
    explanations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("idx_quiz_sessions_user", "user_id"),)


class ExpeditionProgress(Base):
    """Per-user expedition progress (Phase D)."""

    __tablename__ = "expedition_progress"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discord_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    expedition_id: Mapped[str] = mapped_column(String(50), nullable=False)
    current_stage: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_stage_played_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "expedition_id", name="uq_expedition_progress"),
        Index("idx_expedition_progress_user", "user_id"),
    )


class EmpireCard(Base):
    """Static empire card definitions — one row per empire."""

    __tablename__ = "empire_cards"

    empire_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    region: Mapped[str] = mapped_column(String(100), nullable=False)
    start_year: Mapped[int] = mapped_column(Integer, nullable=False)
    end_year: Mapped[int] = mapped_column(Integer, nullable=False)
    peak_area: Mapped[int] = mapped_column(Integer, default=0)
    thematic_stat: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    color: Mapped[int] = mapped_column(Integer, default=0x888888)


class EmpireCollection(Base):
    """Empire cards owned by a user."""

    __tablename__ = "empire_collections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discord_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    empire_id: Mapped[str] = mapped_column(String(50), nullable=False)
    acquired_via: Mapped[str] = mapped_column(String(50), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "empire_id", name="uq_empire_collection"),
        Index("idx_empire_collections_user", "user_id"),
    )


class Achievement(Base):
    """Static achievement definitions, seeded on startup."""

    __tablename__ = "achievements"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[str] = mapped_column(String(10), nullable=False)
    reward_credits: Mapped[int] = mapped_column(Integer, default=0)
    reward_xp: Mapped[int] = mapped_column(Integer, default=0)
    reward_card_tier: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reward_card_count: Mapped[int] = mapped_column(Integer, default=0)
    icon: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class UserAchievement(Base):
    """Per-user achievement unlock records."""

    __tablename__ = "user_achievements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discord_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    achievement_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("achievements.id", ondelete="CASCADE"),
        nullable=False,
    )
    unlocked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    claimed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "achievement_id", name="uq_user_achievement"),
        Index("idx_user_achievements_user", "user_id"),
    )


class LyraBattle(Base):
    """Tracks a player's duel against Lyra at a specific difficulty tier."""

    __tablename__ = "lyra_battles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discord_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    lyra_tier: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-4
    result: Mapped[str | None] = mapped_column(String, nullable=True)  # "win", "loss"
    player_score: Mapped[int] = mapped_column(Integer, default=0)
    lyra_score: Mapped[int] = mapped_column(Integer, default=0)
    credits_earned: Mapped[int] = mapped_column(Integer, default=0)
    xp_earned: Mapped[int] = mapped_column(Integer, default=0)
    pack_reward: Mapped[str | None] = mapped_column(String, nullable=True)  # "rare", "epic"
    played_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_lyra_battles_user_tier", "user_id", "lyra_tier"),
        Index("idx_lyra_battles_played_at", "played_at"),
    )


# Late import to avoid circular — only used for type hints in relationship()
from pipeline.database import UnifiedSite  # noqa: E402, F811
