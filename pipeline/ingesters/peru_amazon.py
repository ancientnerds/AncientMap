"""
Pre-Columbian Amazon earthwork sites ingester.

Based on data from Peripato et al. (2023) "More than 10,000 pre-Columbian
earthworks are still hidden throughout Amazonia" in Science, which compiled
earthwork locations from multiple databases (Amazon Arch, PAST, CNSA,
INRAP & DAC, TREES/INPE).

Originally used de Souza et al. (2018) Figshare dataset, but that was
deleted from Figshare (DOI 10.6084/m9.figshare.5898512 returns 404).

Data source: https://github.com/Vperipato/ade2541 (tag v1.0.0)
Zenodo archive: https://doi.org/10.5281/zenodo.10214943
License: CC-BY-4.0
API Key: Not required
"""

from collections.abc import Iterator
from pathlib import Path

import pyreadr
from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_bytes
from pipeline.utils.http import fetch_with_retry

# Database names from the Peripato dataset mapped to readable labels
DATABASE_LABELS = {
    "Amazon Arch": "AmazonArch",
    "PAST": "PAST",
    "CNSA": "CNSA",
    "INRAP & DAC": "INRAP/DAC",
    "TREES/INPE": "TREES/INPE",
}


class PeruAmazonIngester(BaseIngester):
    """
    Ingester for Pre-Columbian Amazon earthwork sites.

    Contains ~960 earthwork sites compiled from multiple archaeological
    databases covering the Amazon basin (Brazil, Peru, Bolivia, etc.).
    """

    source_id = "peru_amazon"
    source_name = "Pre-Columbian Amazon Sites"

    # Earthworks.rds from Peripato et al. 2023, pinned to tagged release v1.0.0
    DOWNLOAD_URL = "https://github.com/Vperipato/ade2541/raw/v1.0.0/Database/Earthworks.rds"

    def fetch(self) -> Path:
        """
        Fetch earthwork site data from GitHub (Peripato et al. 2023).

        Returns:
            Path to downloaded RDS file
        """
        dest_path = self.raw_data_dir / "peru_amazon_raw.rds"

        logger.info("Fetching Pre-Columbian Amazon data from GitHub...")
        self.report_progress(0, None, "downloading from GitHub...")

        response = fetch_with_retry(self.DOWNLOAD_URL, timeout=120)

        atomic_write_bytes(dest_path, response.content)

        logger.info(f"Saved {len(response.content):,} bytes to {dest_path}")
        return dest_path

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse RDS data into ParsedSite objects.

        The Earthworks.rds file contains columns: Longitude, Latitude, Database.
        Site names are generated from index + database since the dataset
        only has coordinates and source database.

        Args:
            raw_data_path: Path to the downloaded RDS file

        Yields:
            ParsedSite objects for valid earthwork sites
        """
        logger.info(f"Parsing Pre-Columbian Amazon data from {raw_data_path}")

        result = pyreadr.read_r(str(raw_data_path))
        df = list(result.values())[0]

        logger.info(f"Loaded {len(df)} rows with columns: {list(df.columns)}")

        parsed_count = 0
        skipped_count = 0

        for index, row in df.iterrows():
            site = self._parse_row(row, index)
            if site:
                parsed_count += 1
                yield site
            else:
                skipped_count += 1

        logger.info(f"Parsed {parsed_count:,} sites, skipped {skipped_count:,} rows")

    def _parse_row(self, row, index: int) -> ParsedSite | None:
        """
        Parse a single dataframe row into a ParsedSite.

        Args:
            row: pandas Series from iterrows()
            index: Row index

        Returns:
            ParsedSite or None if row is invalid
        """
        lat = row.get("Latitude")
        lon = row.get("Longitude")
        database = row.get("Database", "")

        if lat is None or lon is None:
            return None

        lat = float(lat)
        lon = float(lon)

        # Validate coordinates are roughly in the Amazon basin
        # Lat: -20 to 10, Lon: -80 to -45
        if not (-20 <= lat <= 10) or not (-80 <= lon <= -45):
            logger.debug(f"Row {index}: coordinates ({lat}, {lon}) outside Amazon bounds, skipping")
            return None

        # Clean up multi-source database labels
        db_label = database.strip()
        if db_label.startswith("Multiple:"):
            # e.g. "Multiple: (Amazon Arch | CNSA)" -> use first source
            inner = db_label.replace("Multiple:", "").strip().strip("()")
            first_source = inner.split("|")[0].strip()
            db_label = DATABASE_LABELS.get(first_source, first_source)
        else:
            db_label = DATABASE_LABELS.get(db_label, db_label)

        site_id = str(index)
        name = f"Earthwork {index} ({db_label})"
        description = f"Source database: {database}; Region: Amazon basin"

        raw_data = {
            "Latitude": lat,
            "Longitude": lon,
            "Database": database,
        }

        return ParsedSite(
            source_id=site_id,
            name=name,
            lat=lat,
            lon=lon,
            description=description,
            site_type="monument",
            period_start=-1000,
            period_end=1500,
            period_name="Pre-Columbian",
            precision_meters=500,
            precision_reason="compiled_database",
            source_url="https://doi.org/10.1126/science.ade2541",
            raw_data=raw_data,
        )


def ingest_peru_amazon(session=None, skip_fetch: bool = False) -> dict:
    """Run Pre-Columbian Amazon ingestion."""
    with PeruAmazonIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
