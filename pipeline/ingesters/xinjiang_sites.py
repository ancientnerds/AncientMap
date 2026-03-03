"""
Xinjiang Paleolithic-Bronze Age archaeological sites ingester.

Li et al. "Spatial distribution data of cultural sites from the
Paleolithic to Bronze Age in Xinjiang, China" (2022), Scientific Data.
DOI: 10.1038/s41597-022-01306-5

Data source: National Tibetan Plateau Data Center (TPDC)
  https://data.tpdc.ac.cn/en/data/bb49a6da-bfd4-4355-9d0c-988eef793ee1/
  DOI: 10.11888/HumanNat.tpdc.271910
License: CC-BY 4.0
Status: UNAVAILABLE - TPDC requires registration/login to download data files
"""

import csv
from collections.abc import Iterator
from pathlib import Path

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite

# Period name -> (start_year, end_year)
PERIOD_DATES: dict[str, tuple[int, int]] = {
    "paleolithic": (-100000, -10000),
    "neolithic": (-5000, -2000),
    "bronze age": (-2000, -800),
    "iron age": (-800, 200),
    "han": (-206, 220),
    # Chinese period names
    "\u65e7\u77f3\u5668": (-100000, -10000),  # Paleolithic
    "\u65b0\u77f3\u5668": (-5000, -2000),  # Neolithic
    "\u9752\u94dc": (-2000, -800),  # Bronze
    "\u94c1\u5668": (-800, 200),  # Iron
    "\u6c49": (-206, 220),  # Han
}

# Type column value -> normalized site_type
TYPE_MAPPING: dict[str, str] = {
    "settlement": "settlement",
    "habitation": "settlement",
    "tomb": "tomb",
    "cemetery": "tomb",
    "burial": "tomb",
    "rock art": "other",
    "petroglyph": "other",
    "fortress": "fortress",
    "fort": "fortress",
}


def _find_column(row: dict[str, str], candidates: list[str]) -> str | None:
    """
    Case-insensitively find a column value from a CSV row.

    Args:
        row: CSV row as dict
        candidates: List of possible column names

    Returns:
        The value if found, or None
    """
    row_lower = {k.lower().strip(): v for k, v in row.items()}
    for candidate in candidates:
        value = row_lower.get(candidate.lower().strip())
        if value is not None:
            return value.strip()
    return None


def _map_site_type(raw_type: str | None) -> str:
    """Map a raw type string to a normalized site_type."""
    if not raw_type:
        return "other"
    type_lower = raw_type.lower()
    for keyword, mapped in TYPE_MAPPING.items():
        if keyword in type_lower:
            return mapped
    return "other"


def _parse_period(
    period_name: str | None,
) -> tuple[int | None, int | None]:
    """
    Parse period dates from a period name string.

    Returns:
        (start_year, end_year) or (None, None)
    """
    if not period_name:
        return None, None
    period_lower = period_name.lower().strip()
    for key, (start, end) in PERIOD_DATES.items():
        if key in period_lower:
            return start, end
    return None, None


class XinjiangSitesIngester(BaseIngester):
    """
    Ingester for Xinjiang archaeological sites dataset (~1.6K sites).

    Covers Paleolithic through Bronze Age sites in the Xinjiang
    Uyghur Autonomous Region of northwestern China.
    """

    source_id = "xinjiang_sites"
    source_name = "Xinjiang Archaeological Sites"

    available = False
    unavailable_reason = (
        "Dataset hosted on National Tibetan Plateau Data Center (TPDC) which requires "
        "registration and login to download. "
        "See https://data.tpdc.ac.cn/en/data/bb49a6da-bfd4-4355-9d0c-988eef793ee1/"
    )

    def fetch(self) -> Path:
        """
        Download the Xinjiang sites CSV.

        Returns:
            Path to the downloaded CSV file

        Raises:
            RuntimeError: Always - TPDC requires registration to download
        """
        raise RuntimeError(
            "Xinjiang sites dataset requires TPDC registration to download. "
            "The original Zenodo URL (record 7830895) was incorrect - that record "
            "is an unrelated Belgian lichens paper. The actual dataset is at "
            "https://data.tpdc.ac.cn/en/data/bb49a6da-bfd4-4355-9d0c-988eef793ee1/ "
            "(DOI: 10.11888/HumanNat.tpdc.271910) which requires login."
        )

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse Xinjiang sites CSV into ParsedSite objects.

        Args:
            raw_data_path: Path to the downloaded CSV file

        Yields:
            ParsedSite objects
        """
        logger.info(f"Parsing Xinjiang sites from {raw_data_path}")

        with open(raw_data_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        logger.info(f"Read {len(rows):,} rows from CSV")
        self.report_progress(0, len(rows), "parsing rows...")

        parsed = 0
        skipped = 0

        for index, row in enumerate(rows):
            site = self._parse_row(row, index)
            if site:
                parsed += 1
                yield site
            else:
                skipped += 1

            if (index + 1) % 500 == 0:
                self.report_progress(
                    index + 1,
                    len(rows),
                    f"{parsed:,} parsed, {skipped:,} skipped",
                )

        logger.info(f"Parsed {parsed:,} sites, skipped {skipped:,} rows")

    def _parse_row(self, row: dict[str, str], index: int) -> ParsedSite | None:
        """
        Parse a single CSV row into a ParsedSite.

        Args:
            row: CSV row as dict
            index: Row index (used as fallback ID)

        Returns:
            ParsedSite or None if row is invalid
        """
        # Extract latitude
        lat_str = _find_column(row, ["Latitude", "Lat", "lat", "Y"])
        lon_str = _find_column(row, ["Longitude", "Lon", "lon", "Long", "X"])

        if not lat_str or not lon_str:
            return None

        try:
            lat = float(lat_str)
            lon = float(lon_str)
        except ValueError:
            return None

        # Skip obvious outliers outside Xinjiang region
        if not (35.0 <= lat <= 50.0 and 73.0 <= lon <= 97.0):
            return None

        # Site ID
        site_id = _find_column(row, ["Site_ID", "ID"]) or str(index)

        # Name
        name = _find_column(row, ["Site_Name", "Name", "site_name"])
        if not name:
            return None

        # Type
        raw_type = _find_column(row, ["Type", "type"])
        site_type = _map_site_type(raw_type)

        # Period
        period_name = _find_column(row, ["Period", "period"])
        period_start, period_end = _parse_period(period_name)

        return ParsedSite(
            source_id=site_id,
            name=name,
            lat=lat,
            lon=lon,
            site_type=site_type,
            period_start=period_start,
            period_end=period_end,
            period_name=period_name,
            source_url="https://data.tpdc.ac.cn/en/data/bb49a6da-bfd4-4355-9d0c-988eef793ee1/",
            raw_data=dict(row),
        )


def ingest_xinjiang_sites(session=None, skip_fetch: bool = False) -> dict:
    """Run Xinjiang Sites ingestion."""
    with XinjiangSitesIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
