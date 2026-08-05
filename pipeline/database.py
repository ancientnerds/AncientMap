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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
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
    pool_size=20,  # Increased from 10 for better concurrency
    max_overflow=30,  # Increased from 20
    pool_timeout=30,  # Connection timeout to prevent hanging
    pool_recycle=1800,  # Recycle connections every 30 minutes
    connect_args={
        "connect_timeout": 10,  # Connection timeout in seconds
        "options": "-c statement_timeout=300000",  # 5min query timeout
    },
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
    period_start: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # Year (negative = BCE)
    period_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    period_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Metadata
    source_count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    names: Mapped[list["SiteName"]] = relationship(
        "SiteName", back_populates="site", cascade="all, delete-orphan"
    )
    source_records: Mapped[list["SourceRecord"]] = relationship(
        "SourceRecord", back_populates="site", cascade="all, delete-orphan"
    )

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
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False
    )

    # Name fields
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(500), nullable=False, index=True)

    # Metadata
    language_code: Mapped[str | None] = mapped_column(String(10), nullable=True)  # ISO 639-1
    script: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # latin, greek, arabic, etc.
    name_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # ancient, modern, alternate
    is_canonical: Mapped[bool] = mapped_column(Boolean, default=False)

    # Source tracking
    source_record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_records.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    site: Mapped["Site"] = relationship("Site", back_populates="names")

    __table_args__ = (Index("idx_site_names_site", "site_id"),)

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
    records: Mapped[list["SourceRecord"]] = relationship(
        "SourceRecord", back_populates="source_database"
    )

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
    source_record_id: Mapped[str] = mapped_column(
        String(500), nullable=False
    )  # ID in original database
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Original data
    original_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    original_lon: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Precision metadata
    precision_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    precision_reason: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # gps, digitized, protected

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
    source_database: Mapped["SourceDatabase"] = relationship(
        "SourceDatabase", back_populates="records"
    )

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
    decision: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # auto_match, auto_reject, human_match, human_reject, pending

    # Who/what made the decision
    decided_by: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # algorithm_v1, user:xyz
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Feature vector used for decision
    features: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("idx_match_decisions_site", "site_id"),)


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
    status: Mapped[str] = mapped_column(
        String(50), default="pending"
    )  # pending, in_review, completed, skipped
    assigned_to: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (Index("idx_review_queue_status", "status", "priority"),)


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

    # Edit tracking
    edited_by: Mapped[str] = mapped_column(String(20), server_default="initial", nullable=False)

    # Full original data
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Hierarchy (e.g. Great Sphinx → Giza Necropolis)
    parent_site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("unified_sites.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Audit tracking
    last_audited: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    parent_site: Mapped["UnifiedSite | None"] = relationship(
        "UnifiedSite",
        remote_side="UnifiedSite.id",
        foreign_keys=[parent_site_id],
    )
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


class UnifiedSiteName(Base):
    """Alternate names for unified sites — powers site matching and search."""

    __tablename__ = "unified_site_names"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("unified_sites.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    language_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    name_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # label, alias

    __table_args__ = (
        Index("idx_usn_site", "site_id"),
        UniqueConstraint("site_id", "name_normalized", name="uq_usn"),
    )

    def __repr__(self) -> str:
        return f"<UnifiedSiteName {self.name} for site {self.site_id}>"


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
    content_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # text, map, inscription, artwork, model
    content_source: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # topostext, david_rumsey, edh, sketchfab
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


class WikiImage(Base):
    """
    Locally cached Wikipedia/Wikimedia Commons image for a site.

    Stores downloaded image metadata and attribution for self-hosted serving.
    """

    __tablename__ = "wiki_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("unified_sites.id", ondelete="CASCADE"),
        nullable=False,
    )

    # File storage
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    commons_page_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Thumbnail dimensions
    thumb_width: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Attribution
    author: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    license: Mapped[str | None] = mapped_column(String(50), nullable=True)
    license_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Display flags
    is_hero: Mapped[bool] = mapped_column(Boolean, default=False)
    is_lead: Mapped[bool] = mapped_column(Boolean, default=False)
    is_excluded: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Source tracking
    source_type: Mapped[str] = mapped_column(String(20), default="wikimedia")

    # File metadata
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    site: Mapped["UnifiedSite"] = relationship("UnifiedSite", backref="wiki_images")

    __table_args__ = (
        UniqueConstraint("site_id", "original_url", name="uq_wiki_image_site_url"),
        Index("idx_wiki_images_site", "site_id"),
    )

    def __repr__(self) -> str:
        return f"<WikiImage {self.filename} for site {self.site_id}>"


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
    category: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # global, europe, americas, etc.

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
    tier: Mapped[str] = mapped_column(
        String(50), default="free"
    )  # anonymous, free, pro, enterprise
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
    # AI-corrected name (e.g. "Seab Birch" -> "Sayburç")
    corrected_name: Mapped[str | None] = mapped_column(String(500), nullable=True)

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

    # Lyra enrichment fields
    enrichment_status: Mapped[str | None] = mapped_column(
        String(20), default="pending", nullable=True
    )
    wikidata_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    wikipedia_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    period_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    period_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    period_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_facts_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enrichment_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    promoted_site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("unified_sites.id", ondelete="SET NULL"), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_contributions_status", "status"),
        Index("idx_contributions_created", "created_at"),
        Index("idx_contributions_enrichment", "source", "enrichment_status"),
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
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    duration_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    last_attempted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Cached YouTube storyboard info for screenshot extraction.
    # None = not fetched; {} = fetched, no storyboard available; populated dict = ready to use.
    storyboard_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

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
        UUID(as_uuid=True),
        ForeignKey("unified_sites.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    site_name_extracted: Mapped[str | None] = mapped_column(String(500), nullable=True)
    site_match_tried: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    significance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    news_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    speculative_tag: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Pipeline efficiency tracking
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    screenshot_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # RAG enrichment fields
    transcript_segment: Mapped[str | None] = mapped_column(Text, nullable=True)
    entities: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Web verification sources (populated during rescore web-check)
    web_sources: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Editorial judgment from the significance scorer (why this score?)
    score_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

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
    active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    quality_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<NewsArticle {self.id}: {self.title[:40]}>"


# =============================================================================
# Library Sources (Deduplicated Web Citations)
# =============================================================================


class LibrarySource(Base):
    """Aggregated citation/web source from across all content types."""

    __tablename__ = "library_sources"

    id: Mapped[str] = mapped_column(String(12), primary_key=True)  # sha256(url)[:12]
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    reliability_tier: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    period_tags: Mapped[list | None] = mapped_column(ARRAY(String(100)), nullable=True)
    source_types: Mapped[list | None] = mapped_column(ARRAY(String(20)), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    citation_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    parent_refs: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_library_sources_citation_count", "citation_count"),
        Index("idx_library_sources_period_tags", "period_tags", postgresql_using="gin"),
        Index("idx_library_sources_source_types", "source_types", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<LibrarySource {self.id}: {self.domain}>"


# =============================================================================
# Database Snapshots (Version Control for Audit Edits)
# =============================================================================


class DbSnapshot(Base):
    """Snapshot of site rows before a batch edit or upload."""

    __tablename__ = "db_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "audit", "upload", "admin"
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    snapshot_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "edit" | "upload" | "manual"
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_id: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # which database this snapshot belongs to

    rows: Mapped[list["SnapshotRow"]] = relationship(
        "SnapshotRow",
        back_populates="snapshot",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<DbSnapshot {self.id} ({self.snapshot_type}, {self.row_count} rows)>"


class SnapshotRow(Base):
    """Single row captured in a snapshot — stores pre-change state."""

    __tablename__ = "snapshot_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("db_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    old_data: Mapped[dict] = mapped_column(JSONB, nullable=False)

    snapshot: Mapped["DbSnapshot"] = relationship("DbSnapshot", back_populates="rows")

    __table_args__ = (
        Index("idx_snapshot_rows_snapshot", "snapshot_id"),
        Index("idx_snapshot_rows_site", "site_id"),
    )

    def __repr__(self) -> str:
        return f"<SnapshotRow snapshot={self.snapshot_id} site={self.site_id}>"


# =============================================================================
# Source Version Pins (Per-Source Snapshot Pinning for Public Globe)
# =============================================================================


class SourceVersionPin(Base):
    """Pin a specific snapshot version as the publicly served data for a source."""

    __tablename__ = "source_version_pins"

    source_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    snapshot_date: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )  # null = serve live DB
    pinned_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    pinned_by: Mapped[str] = mapped_column(String(50), nullable=False)

    def __repr__(self) -> str:
        return f"<SourceVersionPin {self.source_id} → {self.snapshot_date}>"


# =============================================================================
# Discord Auth & Credits
# =============================================================================


class DiscordUser(Base):
    """Discord-authenticated user with Lyra credits."""

    __tablename__ = "discord_users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    discord_id: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    avatar_hash: Mapped[str | None] = mapped_column(String(100), nullable=True)
    roles: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reserved_credits: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_unlimited: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    grant_anchor_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    credit_grants: Mapped[list["CreditGrant"]] = relationship("CreditGrant", back_populates="user")
    token_usage_logs: Mapped[list["TokenUsageLog"]] = relationship(
        "TokenUsageLog", back_populates="user"
    )

    def __repr__(self) -> str:
        return f"<DiscordUser {self.username} ({self.discord_id})>"


class PatreonEvent(Base):
    """Patreon webhook events for idempotent processing."""

    __tablename__ = "patreon_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    event_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    patron_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    discord_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    tier_amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<PatreonEvent {self.event_id} ({self.event_type})>"


class CreditGrant(Base):
    """Log of credit grants (OG Nerd role, future Patreon tiers, etc.)."""

    __tablename__ = "credit_grants"

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
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(100), nullable=False)
    grant_period: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )  # "2026-02" for monthly, "one_time" for one-time grants
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["DiscordUser"] = relationship("DiscordUser", back_populates="credit_grants")

    __table_args__ = (
        Index("idx_credit_grants_user_reason", "user_id", "reason"),
        UniqueConstraint(
            "user_id", "reason", "grant_period", name="uq_credit_grants_user_reason_period"
        ),
    )

    def __repr__(self) -> str:
        return f"<CreditGrant {self.amount} to {self.user_id} ({self.reason})>"


class TokenUsageLog(Base):
    """Per-request token usage for Lyra chat."""

    __tablename__ = "token_usage_logs"

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
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    voyage_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    web_search_requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    credits_used: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["DiscordUser"] = relationship("DiscordUser", back_populates="token_usage_logs")

    __table_args__ = (Index("idx_token_usage_user_date", "user_id", "created_at"),)

    def __repr__(self) -> str:
        return f"<TokenUsageLog {self.credits_used} credits by {self.user_id}>"


# =============================================================================
# Site Interactions (Likes & Bookmarks)
# =============================================================================


class SiteLike(Base):
    """A user's like on an archaeological site (public, with count)."""

    __tablename__ = "site_likes"

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
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("unified_sites.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "site_id", name="uq_site_like"),
        Index("idx_site_likes_site", "site_id"),
    )


class SiteBookmark(Base):
    """A user's private bookmark on an archaeological site."""

    __tablename__ = "site_bookmarks"

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
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("unified_sites.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "site_id", name="uq_site_bookmark"),
        Index("idx_site_bookmarks_user", "user_id"),
    )


# =============================================================================
# Vector Sync State
# =============================================================================


class VectorSyncState(Base):
    """Persistent state for Qdrant vector reindex operations."""

    __tablename__ = "vector_sync_state"

    collection: Mapped[str] = mapped_column(String(50), primary_key=True)
    last_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_result: Mapped[str | None] = mapped_column(String(200), nullable=True)

    def __repr__(self) -> str:
        return f"<VectorSyncState {self.collection} @ {self.last_completed_at}>"


# =============================================================================
# Helper Functions
# =============================================================================


# =============================================================================
# Theo Research Requests
# =============================================================================


class ResearchRequest(Base):
    """Async research request processed by Theodore Furcade."""

    __tablename__ = "research_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    effort: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    pipeline_trace: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    sites_found: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    tools_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    specialist_options: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    slug: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_research_requests_user_created", "user_id", "created_at"),
        Index("idx_research_requests_status", "status"),
        Index("idx_research_requests_public", "is_public", "published_at"),
    )

    def __repr__(self) -> str:
        return f"<ResearchRequest {self.id} ({self.status})>"


class TtsRequest(Base):
    """FIFO queue for TTS audio generation requests on research papers."""

    __tablename__ = "tts_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    audio_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    chars_generated: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_tts_requests_status_requested", "status", "requested_at"),
        Index("idx_tts_requests_paper_user", "paper_id", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<TtsRequest {self.id} ({self.status})>"


class ResearchNode(Base):
    """A node in the research knowledge graph (2026-07-26 design).

    The graph doubles as the permanent researcher's topic queue: `frontier`
    nodes are candidate research topics, the feeder promotes the best one to
    `researching`, and a completed paper marks it `explored`. See
    docs/superpowers/specs/2026-07-26-permanent-researcher-design.md.

    kind:   topic | paper | site | entity | connection | hypothesis
    status: reference | frontier | researching | explored
    created_from: rabbit_hole | story | journal | site | manual | backfill | paper | curator
    question: stored research question for curator-created frontier nodes (2026-08-04)
    outcome:  confirmed | refuted | inconclusive — hypothesis nodes only
    """

    __tablename__ = "research_nodes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    label: Mapped[str] = mapped_column(String(500), nullable=False)
    norm_label: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="frontier", index=True)
    created_from: Mapped[str] = mapped_column(String(20), nullable=False)
    # Accumulated interest signal from source injectors (story mentions etc.).
    source_signal: Mapped[float] = mapped_column(Float, default=0.0)
    paper_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_requests.id", ondelete="SET NULL"),
        nullable=True,
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("unified_sites.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Curator-written research question for connection/hypothesis frontier
    # nodes (2026-08-04) — question_for_node() prefers this over templates.
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    # confirmed | refuted | inconclusive — hypothesis nodes only (2026-08-04).
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("kind", "norm_label", name="uq_research_node_kind_label"),)

    def __repr__(self) -> str:
        return f"<ResearchNode {self.kind}:{self.label[:40]} ({self.status})>"


class ResearchEdge(Base):
    """A directed edge between research nodes.

    kind: leads_to (paper -> open rabbit hole) | cites | contradicts |
    about_site | related. CASCADE is allowed here (graph-owned data, not
    site-owned) — deleting a node removes its edges.
    """

    __tablename__ = "research_edges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    src: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_nodes.id", ondelete="CASCADE"), index=True
    )
    dst: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_nodes.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("src", "dst", "kind", name="uq_research_edge"),)

    def __repr__(self) -> str:
        return f"<ResearchEdge {self.kind} {self.src}->{self.dst}>"


class KnowledgeClaim(Base):
    """One claim in the permanent researcher's world model (2026-08-04 design).

    status: established | contested | refuted | open
    `refuted` is terminal — the curator never reopens a refuted claim; a
    refuted thesis must not re-enter the frontier as an open question.
    """

    __tablename__ = "knowledge_claims"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    norm_text: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    # Provenance: which papers assert this, how many EXTERNAL tier-1/2
    # sources back it (self-citations never count — spec §5).
    paper_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    external_source_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # UNIQUE enforces the refuted-is-terminal invariant at the DB level:
    # duplicate norm_text rows would let the curator's LIMIT-1 lookup pick
    # the non-refuted twin and silently reopen a refuted claim.
    __table_args__ = (UniqueConstraint("norm_text", name="uq_knowledge_claim_norm_text"),)

    def __repr__(self) -> str:
        return f"<KnowledgeClaim {self.status} {self.text[:40]!r}>"


class ThinkingLogEntry(Base):
    """One event in the thinking-layer activity feed (spec §7).

    kind: curator | miner | run_event
    Powers GET /api/v1/knowledge/activity — the Knowledge page timeline.
    """

    __tablename__ = "thinking_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self) -> str:
        return f"<ThinkingLogEntry {self.kind} {self.summary[:40]!r}>"


# =============================================================================
# Helper Functions
# =============================================================================


def create_all_tables():
    """Create all database tables."""
    Base.metadata.create_all(bind=engine)


def drop_all_tables():
    """Drop all database tables. USE WITH CAUTION!"""
    Base.metadata.drop_all(bind=engine)
