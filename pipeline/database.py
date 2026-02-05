"""
Database models for ANCIENT NERDS - Research Platform.

Uses SQLAlchemy 2.0 with GeoAlchemy2 for PostGIS support.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from geoalchemy2 import Geometry
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
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)
from sqlalchemy.sql import func

from pipeline.config import settings

# =============================================================================
# Database Engine and Session
# =============================================================================

engine = create_engine(
    settings.database.url,
    echo=settings.pipeline.log_level == "DEBUG",
    pool_pre_ping=True,
    pool_size=20,           # Increased from 10 for better concurrency
    max_overflow=30,        # Increased from 20
    pool_timeout=30,        # Connection timeout to prevent hanging
    pool_recycle=1800,      # Recycle connections every 30 minutes
    connect_args={
        "connect_timeout": 10,  # Connection timeout in seconds
        "options": "-c statement_timeout=30000"  # 30s query timeout
    }
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Dependency for FastAPI to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_session():
    """Context manager for database sessions."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# =============================================================================
# Base Model
# =============================================================================

class Base(DeclarativeBase):
    """Base class for all models."""
    pass


# =============================================================================
# Site Models (Golden Records)
# =============================================================================

class Site(Base):
    """
    Golden record for a deduplicated archaeological site.

    This represents the merged, canonical record created from one or more
    source records after deduplication.
    """
    __tablename__ = "sites"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Core fields
    canonical_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Location
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    geom: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=True,
    )

    # Spatial indexing (H3)
    h3_index_res5: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    h3_index_res7: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)

    # Confidence scores
    coordinate_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Classification
    site_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # Time period
    period_start: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Year (negative = BCE)
    period_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    period_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Metadata
    source_count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    names: Mapped[list["SiteName"]] = relationship("SiteName", back_populates="site", cascade="all, delete-orphan")
    source_records: Mapped[list["SourceRecord"]] = relationship("SourceRecord", back_populates="site", cascade="all, delete-orphan")

    # Indexes (geom has spatial_index=True so no manual index needed)
    __table_args__ = (
        Index("idx_sites_period", "period_start", "period_end"),
        Index("idx_sites_type_period", "site_type", "period_start"),
    )

    def __repr__(self) -> str:
        return f"<Site {self.canonical_name} ({self.lat}, {self.lon})>"


class SiteName(Base):
    """
    Alternative names for a site.

    A site can have many names: ancient names, modern names, names in different
    languages, transliterations, etc.
    """
    __tablename__ = "site_names"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)

    # Name fields
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(500), nullable=False, index=True)

    # Metadata
    language_code: Mapped[str | None] = mapped_column(String(10), nullable=True)  # ISO 639-1
    script: Mapped[str | None] = mapped_column(String(50), nullable=True)  # latin, greek, arabic, etc.
    name_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # ancient, modern, alternate
    is_canonical: Mapped[bool] = mapped_column(Boolean, default=False)

    # Source tracking
    source_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("source_records.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    site: Mapped["Site"] = relationship("Site", back_populates="names")

    __table_args__ = (
        Index("idx_site_names_site", "site_id"),
    )

    def __repr__(self) -> str:
        return f"<SiteName {self.name} (site={self.site_id})>"


# =============================================================================
# Source Provenance Models
# =============================================================================

class SourceDatabase(Base):
    """
    Metadata about a source database.

    Tracks information about each data source we ingest from.
    """
    __tablename__ = "source_databases"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # e.g., "pleiades", "unesco"
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    api_endpoint: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # License and attribution
    license: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attribution_template: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Sync metadata
    last_sync: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    record_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Priority for canonical value selection (lower = higher priority)
    priority: Mapped[int] = mapped_column(Integer, default=50)

    # Relationships
    records: Mapped[list["SourceRecord"]] = relationship("SourceRecord", back_populates="source_database")

    def __repr__(self) -> str:
        return f"<SourceDatabase {self.id}: {self.name}>"


class SourceRecord(Base):
    """
    Original record from a source database.

    Preserves the complete original data for attribution and provenance.
    """
    __tablename__ = "source_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Link to golden record (if matched)
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Source identification
    source_database_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("source_databases.id"),
        nullable=False,
    )
    source_record_id: Mapped[str] = mapped_column(String(500), nullable=False)  # ID in original database
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Original data
    original_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    original_lon: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Precision metadata
    precision_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    precision_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)  # gps, digitized, protected

    # License and attribution
    license: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attribution: Mapped[str] = mapped_column(Text, nullable=False)

    # Full original record
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Timestamps
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    site: Mapped[Optional["Site"]] = relationship("Site", back_populates="source_records")
    source_database: Mapped["SourceDatabase"] = relationship("SourceDatabase", back_populates="records")

    __table_args__ = (
        UniqueConstraint("source_database_id", "source_record_id", name="uq_source_record"),
        Index("idx_source_records_site", "site_id"),
        Index("idx_source_records_source", "source_database_id", "source_record_id"),
    )

    def __repr__(self) -> str:
        return f"<SourceRecord {self.source_database_id}:{self.source_record_id}>"


# =============================================================================
# Deduplication Models
# =============================================================================

class MatchDecision(Base):
    """
    Record of match decisions made during deduplication.

    Provides audit trail and training data for improving the matching model.
    """
    __tablename__ = "match_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # The merged site (if matched)
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="SET NULL"),
        nullable=True,
    )

    # The two records being compared
    source_record_id_1: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_record_id_2: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_records.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Match result
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    decision: Mapped[str] = mapped_column(String(50), nullable=False)  # auto_match, auto_reject, human_match, human_reject, pending

    # Who/what made the decision
    decided_by: Mapped[str | None] = mapped_column(String(100), nullable=True)  # algorithm_v1, user:xyz
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Feature vector used for decision
    features: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_match_decisions_site", "site_id"),
    )


class ReviewQueue(Base):
    """
    Queue of potential matches requiring human review.
    """
    __tablename__ = "review_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # The two records to review
    source_record_id_1: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_record_id_2: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_records.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Match details
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    features: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Queue management
    priority: Mapped[int] = mapped_column(Integer, default=0)  # Higher = review first
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, in_review, completed, skipped
    assigned_to: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_review_queue_status", "status", "priority"),
    )


# =============================================================================
# Unified Site Models (for Static Export)
# =============================================================================

class UnifiedSite(Base):
    """
    Unified, denormalized site record for fast queries and static export.

    This is a simplified table that holds ALL sites from all sources,
    optimized for bulk export to static JSON files.
    """
    __tablename__ = "unified_sites"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Source identification
    source_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_record_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Core fields
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    name_normalized: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)

    # Location
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    geom: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=True,
    )
    h3_index: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)

    # Classification
    site_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # Time period
    period_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    period_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    period_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Additional info
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Full original data
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    content_links: Mapped[list["SiteContentLink"]] = relationship(
        "SiteContentLink", back_populates="site", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("source_id", "source_record_id", name="uq_unified_site"),
        # geom has spatial_index=True so no manual index needed
        Index("idx_unified_sites_period", "period_start", "period_end"),
        Index("idx_unified_sites_type", "site_type"),
    )

    def __repr__(self) -> str:
        return f"<UnifiedSite {self.source_id}:{self.source_record_id} - {self.name}>"


class SiteContentLink(Base):
    """
    Pre-computed links between sites and related content.

    Links sites to texts (ToposText), maps (David Rumsey),
    inscriptions (EDH), artworks, 3D models, etc.
    """
    __tablename__ = "site_content_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Link to unified site
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("unified_sites.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Content identification
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)  # text, map, inscription, artwork, model
    content_source: Mapped[str] = mapped_column(String(50), nullable=False)  # topostext, david_rumsey, edh, sketchfab
    content_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Content preview data (embedded for fast export)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relevance
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-1

    # Additional metadata
    link_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    site: Mapped["UnifiedSite"] = relationship("UnifiedSite", back_populates="content_links")

    __table_args__ = (
        UniqueConstraint("site_id", "content_source", "content_id", name="uq_content_link"),
        Index("idx_content_links_site", "site_id"),
        Index("idx_content_links_type", "content_type"),
        Index("idx_content_links_source", "content_source"),
    )

    def __repr__(self) -> str:
        return f"<SiteContentLink {self.content_type}:{self.content_source}:{self.content_id}>"


class SourceMeta(Base):
    """
    Metadata about each data source for the frontend.

    Includes display info like colors and icons.
    """
    __tablename__ = "source_meta"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # e.g., "pleiades"
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Display
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)  # Hex color
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)  # global, europe, americas, etc.

    # Stats
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Primary source flag - Ancient Nerds original is the primary source
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    # Whether this source is enabled by default (primary sources are, others aren't)
    enabled_by_default: Mapped[bool] = mapped_column(Boolean, default=False)

    # Priority for display order (lower = higher priority, 0 = primary)
    priority: Mapped[int] = mapped_column(Integer, default=50)

    # License
    license: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attribution: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    last_loaded: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<SourceMeta {self.id}: {self.name}>"


# =============================================================================
# API Models
# =============================================================================

class APIKey(Base):
    """
    API key for rate limiting and access control.
    """
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Key identification
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Owner information
    owner_email: Mapped[str] = mapped_column(String(320), nullable=False)
    owner_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Tier and limits
    tier: Mapped[str] = mapped_column(String(50), default="free")  # anonymous, free, pro, enterprise
    rate_limit_override: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Custom limit

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Usage tracking
    usage_logs: Mapped[list["UsageLog"]] = relationship("UsageLog", back_populates="api_key")

    def __repr__(self) -> str:
        return f"<APIKey {self.name} ({self.tier})>"


class UsageLog(Base):
    """
    API usage logging for analytics and billing.
    """
    __tablename__ = "usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # API key (null for anonymous)
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Request details
    endpoint: Mapped[str] = mapped_column(String(200), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)

    # Response details
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Client info
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv6 max length
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    api_key: Mapped[Optional["APIKey"]] = relationship("APIKey", back_populates="usage_logs")

    __table_args__ = (
        Index("idx_usage_logs_api_key_date", "api_key_id", "created_at"),
        Index("idx_usage_logs_date", "created_at"),
    )


# =============================================================================
# User Contributions (Staging Table for Community Submissions)
# =============================================================================


class UserContribution(Base):
    """
    User-submitted site contributions for admin review.

    All submissions go to this staging table before being
    approved and moved to unified_sites.
    """
    __tablename__ = "user_contributions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Required fields
    name: Mapped[str] = mapped_column(String(500), nullable=False)

    # Optional location (can be entered manually or via map click)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Optional metadata
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    site_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Submission metadata
    submitter_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    turnstile_token: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Source: 'user' (manual submission) or 'lyra' (pipeline-extracted)
    source: Mapped[str] = mapped_column(String(20), default="user", nullable=False, index=True)
    # How many videos mention this site (incremented by pipeline, always 1 for user contributions)
    mention_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Review status: pending, approved, rejected
    status: Mapped[str] = mapped_column(String(50), default="pending")
    reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_contributions_status", "status"),
        Index("idx_contributions_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<UserContribution {self.name} ({self.status})>"


# =============================================================================
# Lyra News Pipeline Models
# =============================================================================


class NewsChannel(Base):
    """YouTube channel tracked by the Lyra news pipeline."""
    __tablename__ = "news_channels"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # YouTube channel ID
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    videos: Mapped[list["NewsVideo"]] = relationship("NewsVideo", back_populates="channel")

    def __repr__(self) -> str:
        return f"<NewsChannel {self.name}>"


class NewsVideo(Base):
    """YouTube video processed by the Lyra pipeline."""
    __tablename__ = "news_videos"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)  # YouTube video ID
    channel_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("news_channels.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    duration_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)

    channel: Mapped["NewsChannel"] = relationship("NewsChannel", back_populates="videos")
    items: Mapped[list["NewsItem"]] = relationship("NewsItem", back_populates="video")

    def __repr__(self) -> str:
        return f"<NewsVideo {self.id}: {self.title[:40]}>"


class NewsItem(Base):
    """Individual news item (one key topic extracted from a video)."""
    __tablename__ = "news_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("news_videos.id"), nullable=False, index=True
    )
    headline: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    facts: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    timestamp_range: Mapped[str | None] = mapped_column(String(50), nullable=True)
    timestamp_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    post_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    screenshot_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    # Link to archaeological site on the globe
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("unified_sites.id"), nullable=True, index=True
    )
    site_name_extracted: Mapped[str | None] = mapped_column(String(500), nullable=True)

    video: Mapped["NewsVideo"] = relationship("NewsVideo", back_populates="items")
    site: Mapped[Optional["UnifiedSite"]] = relationship("UnifiedSite", lazy="joined")

    def __repr__(self) -> str:
        return f"<NewsItem {self.id}: {self.headline[:40]}>"


class NewsArticle(Base):
    """Weekly digest article generated from video summaries."""
    __tablename__ = "news_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    week_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    week_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    video_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<NewsArticle {self.id}: {self.title[:40]}>"


# =============================================================================
# Helper Functions
# =============================================================================

def create_all_tables():
    """Create all database tables."""
    Base.metadata.create_all(bind=engine)


def drop_all_tables():
    """Drop all database tables. USE WITH CAUTION!"""
    Base.metadata.drop_all(bind=engine)
