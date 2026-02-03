"""
Base ingester class for data sources.

All source-specific ingesters should inherit from BaseIngester and implement
the required abstract methods.
"""

import json
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from pipeline.config import DATA_SOURCES, settings
from pipeline.database import SessionLocal, SourceDatabase, SourceRecord


def atomic_write_bytes(dest_path: Path, content: bytes) -> Path:
    """
    Write bytes to file atomically.

    Args:
        dest_path: Final destination path
        content: Bytes to write

    Returns:
        Path to written file
    """
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = dest_path.with_suffix(dest_path.suffix + ".tmp")

    try:
        temp_path.write_bytes(content)

        if dest_path.exists():
            dest_path.unlink()
        temp_path.rename(dest_path)

        return dest_path
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def atomic_write_json(dest_path: Path, data: Any, indent: int = None) -> Path:
    """
    Write JSON data atomically - only replaces target file on success.

    1. Writes to temp file in same directory
    2. Validates JSON is readable
    3. Renames temp to final (atomic on same filesystem)

    Args:
        dest_path: Final destination path
        data: Data to serialize as JSON
        indent: JSON indent (None for compact)

    Returns:
        Path to written file
    """
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file in same directory (for atomic rename)
    temp_path = dest_path.with_suffix(dest_path.suffix + ".tmp")

    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, default=str, ensure_ascii=False, indent=indent)

        # Verify file is valid JSON
        with open(temp_path, encoding="utf-8") as f:
            json.load(f)

        # Atomic rename (overwrites existing)
        if dest_path.exists():
            dest_path.unlink()
        temp_path.rename(dest_path)

        return dest_path

    except Exception:
        # Clean up temp file on failure
        if temp_path.exists():
            temp_path.unlink()
        raise


@dataclass
class ParsedSite:
    """
    Standardized representation of a site parsed from a source.

    This is the common format all ingesters should produce.
    """
    # Required fields
    source_id: str              # ID in the source database
    name: str                   # Primary name
    lat: float                  # Latitude (WGS84)
    lon: float                  # Longitude (WGS84)

    # Optional fields
    alternative_names: list[str] = field(default_factory=list)
    description: str | None = None
    site_type: str | None = None
    period_start: int | None = None  # Year (negative = BCE)
    period_end: int | None = None
    period_name: str | None = None

    # Precision metadata
    precision_meters: float | None = None
    precision_reason: str | None = None

    # Source URL for direct linking
    source_url: str | None = None

    # Full original record for provenance
    raw_data: dict[str, Any] | None = None


@dataclass
class IngesterResult:
    """Result of an ingestion run."""
    source_id: str
    success: bool
    records_fetched: int = 0
    records_parsed: int = 0
    records_saved: int = 0
    records_failed: int = 0
    errors: list[str] = field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def duration_seconds(self) -> float | None:
        """Calculate duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class BaseIngester(ABC):
    """
    Abstract base class for data source ingesters.

    Subclasses must implement:
    - fetch(): Download raw data from the source
    - parse(): Parse raw data into ParsedSite objects
    """

    # Class attributes to be set by subclasses
    source_id: str = None           # e.g., "pleiades"
    source_name: str = None         # e.g., "Pleiades"

    def __init__(self, session=None, progress_callback=None):
        """
        Initialize the ingester.

        Args:
            session: SQLAlchemy session (optional, will create if not provided)
            progress_callback: Optional callback for progress updates
                              Signature: callback(current, total, status_text)
        """
        if self.source_id is None:
            raise ValueError("source_id must be set in subclass")

        self.session = session or SessionLocal()
        self._owns_session = session is None
        self.progress_callback = progress_callback

        # Load source info from config
        self.source_info = DATA_SOURCES.get(self.source_id, {})
        self.source_name = self.source_name or self.source_info.get("name", self.source_id)

        # Paths for data storage
        self.raw_data_dir = settings.pipeline.data_raw_dir / self.source_id
        self.raw_data_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initialized {self.source_name} ingester")

    def report_progress(self, current: int, total: int = None, status: str = None):
        """Report progress to callback if set."""
        if self.progress_callback:
            self.progress_callback(current, total, status)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._owns_session:
            self.session.close()

    @abstractmethod
    def fetch(self) -> Path:
        """
        Fetch raw data from the source.

        Returns:
            Path to the downloaded raw data file.
        """
        pass

    @abstractmethod
    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse raw data into standardized ParsedSite objects.

        Args:
            raw_data_path: Path to the raw data file

        Yields:
            ParsedSite objects
        """
        pass

    def validate_site(self, site: ParsedSite) -> list[str]:
        """
        Validate a parsed site.

        Args:
            site: ParsedSite to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Required fields
        if not site.source_id:
            errors.append("Missing source_id")
        if not site.name:
            errors.append("Missing name")

        # Coordinate validation
        if site.lat is None or site.lon is None:
            errors.append("Missing coordinates")
        elif not (-90 <= site.lat <= 90):
            errors.append(f"Invalid latitude: {site.lat}")
        elif not (-180 <= site.lon <= 180):
            errors.append(f"Invalid longitude: {site.lon}")

        # Period validation
        if site.period_start is not None and site.period_end is not None:
            if site.period_start > site.period_end:
                errors.append(f"period_start ({site.period_start}) > period_end ({site.period_end})")

        return errors

    def save_source_record(self, site: ParsedSite) -> SourceRecord | None:
        """
        Save a parsed site as a source record.

        Args:
            site: ParsedSite to save

        Returns:
            Created SourceRecord or None if failed
        """
        # Check if record already exists
        existing = self.session.query(SourceRecord).filter_by(
            source_database_id=self.source_id,
            source_record_id=site.source_id,
        ).first()

        if existing:
            logger.debug(f"Record already exists: {self.source_id}:{site.source_id}")
            # Update existing record
            existing.original_name = site.name
            existing.original_lat = site.lat
            existing.original_lon = site.lon
            existing.precision_meters = site.precision_meters
            existing.precision_reason = site.precision_reason
            existing.source_url = site.source_url
            existing.raw_data = site.raw_data
            existing.retrieved_at = datetime.utcnow()
            return existing

        # Create new record
        record = SourceRecord(
            source_database_id=self.source_id,
            source_record_id=site.source_id,
            original_name=site.name,
            original_lat=site.lat,
            original_lon=site.lon,
            precision_meters=site.precision_meters,
            precision_reason=site.precision_reason,
            source_url=site.source_url,
            license=self.source_info.get("license"),
            attribution=self.source_info.get("attribution", f"Data from {self.source_name}"),
            raw_data=site.raw_data,
            retrieved_at=datetime.utcnow(),
        )

        self.session.add(record)
        return record

    def ensure_source_database(self):
        """Ensure the source database record exists."""
        existing = self.session.query(SourceDatabase).filter_by(id=self.source_id).first()
        if not existing:
            source_db = SourceDatabase(
                id=self.source_id,
                name=self.source_name,
                description=self.source_info.get("description"),
                url=self.source_info.get("url"),
                api_endpoint=self.source_info.get("api_url") or self.source_info.get("download_url"),
                license=self.source_info.get("license"),
                attribution_template=self.source_info.get("attribution"),
            )
            self.session.add(source_db)
            self.session.commit()

    def run(self, skip_fetch: bool = False, batch_size: int = None) -> IngesterResult:
        """
        Run the full ingestion pipeline.

        Args:
            skip_fetch: Skip fetching and use existing raw data
            batch_size: Number of records to commit at once

        Returns:
            IngesterResult with statistics
        """
        batch_size = batch_size or settings.pipeline.batch_size
        result = IngesterResult(
            source_id=self.source_id,
            success=False,
            started_at=datetime.utcnow(),
        )

        try:
            # Ensure source database exists
            self.ensure_source_database()

            # Fetch data
            if not skip_fetch:
                logger.info(f"Fetching data from {self.source_name}...")
                raw_data_path = self.fetch()
            else:
                # Find most recent raw data file
                raw_files = list(self.raw_data_dir.glob("*"))
                if not raw_files:
                    raise FileNotFoundError(f"No raw data files found in {self.raw_data_dir}")
                raw_data_path = max(raw_files, key=lambda p: p.stat().st_mtime)
                logger.info(f"Using existing raw data: {raw_data_path}")

            # Parse and save
            logger.info(f"Parsing data from {raw_data_path}...")
            batch = []

            for site in self.parse(raw_data_path):
                result.records_fetched += 1

                # Validate
                errors = self.validate_site(site)
                if errors:
                    result.records_failed += 1
                    result.errors.append(f"{site.source_id}: {', '.join(errors)}")
                    continue

                result.records_parsed += 1

                # Save
                try:
                    record = self.save_source_record(site)
                    if record:
                        batch.append(record)
                        result.records_saved += 1
                except Exception as e:
                    result.records_failed += 1
                    result.errors.append(f"{site.source_id}: {str(e)}")
                    continue

                # Commit batch
                if len(batch) >= batch_size:
                    self.session.commit()
                    logger.info(f"Committed batch of {len(batch)} records (total: {result.records_saved})")
                    batch = []

            # Commit remaining
            if batch:
                self.session.commit()
                logger.info(f"Committed final batch of {len(batch)} records")

            # Update source database metadata
            source_db = self.session.query(SourceDatabase).filter_by(id=self.source_id).first()
            if source_db:
                source_db.last_sync = datetime.utcnow()
                source_db.record_count = result.records_saved
                self.session.commit()

            result.success = True

        except Exception as e:
            logger.error(f"Ingestion failed: {e}")
            result.errors.append(str(e))
            self.session.rollback()
            raise

        finally:
            result.completed_at = datetime.utcnow()
            logger.info(
                f"Ingestion complete: {result.records_saved} saved, "
                f"{result.records_failed} failed, "
                f"{result.duration_seconds:.1f}s"
            )

        return result
