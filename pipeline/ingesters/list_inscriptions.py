"""
LIST Latin Inscriptions ingester.

Downloads the LIST (Linked Inscriptions Search Tool) dataset containing
~512K Latin inscriptions with geographic coordinates from across the Roman world.

Data source: https://zenodo.org/records/8117658
License: CC-BY 4.0
API Key: Not required
"""

import json
from collections.abc import Iterator
from pathlib import Path

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite
from pipeline.utils.http import download_file


class LISTInscriptionsIngester(BaseIngester):
    """
    Ingester for LIST Latin Inscriptions.

    LIST contains ~512K Latin inscriptions from the Roman world,
    sourced from the Epigraphic Database Heidelberg and other corpora.
    Downloaded as a GeoJSON FeatureCollection from Zenodo.
    """

    source_id = "list_inscriptions"
    source_name = "LIST Latin Inscriptions"

    DOWNLOAD_URL = "https://zenodo.org/records/8117658/files/LIST_Open_Full.geojson?download=1"

    def fetch(self) -> Path:
        """
        Download the LIST GeoJSON from Zenodo.

        Returns:
            Path to the downloaded GeoJSON file.
        """
        dest_path = self.raw_data_dir / "list_inscriptions.geojson"

        logger.info(f"Downloading LIST inscriptions from {self.DOWNLOAD_URL}...")
        self.report_progress(0, None, "downloading GeoJSON from Zenodo...")

        path = download_file(url=self.DOWNLOAD_URL, dest_path=dest_path, force=True)

        logger.info(f"Downloaded LIST inscriptions to {path}")
        return path

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse LIST GeoJSON into ParsedSite objects.

        Yields:
            ParsedSite objects for inscriptions with valid coordinates.
        """
        logger.info(f"Parsing LIST inscriptions from {raw_data_path}")

        with open(raw_data_path, encoding="utf-8") as f:
            data = json.load(f)

        features = data.get("features", [])
        logger.info(f"Processing {len(features):,} inscription features")

        for idx, feature in enumerate(features):
            site = self._parse_feature(feature, idx)
            if site:
                yield site

    def _parse_feature(self, feature: dict, idx: int) -> ParsedSite | None:
        """
        Parse a single GeoJSON feature into a ParsedSite.

        Args:
            feature: GeoJSON feature dict
            idx: Index in the feature list (fallback ID)

        Returns:
            ParsedSite or None if invalid/filtered out.
        """
        geometry = feature.get("geometry", {})
        properties = feature.get("properties", {})

        # Only Point geometries
        if geometry.get("type") != "Point":
            return None

        coords = geometry.get("coordinates", [])
        if len(coords) < 2:
            return None

        lon, lat = coords[0], coords[1]

        # Validate coordinates
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None
        if lat == 0 and lon == 0:
            return None

        # Source ID
        list_id = str(properties.get("list_id", "")) or str(idx)

        # Name: prefer ancient findspot, then modern, then fallback
        name = (
            properties.get("findspot_ancient")
            or properties.get("findspot_modern")
            or f"Inscription {list_id}"
        )

        # Period parsing
        period_start = self._parse_year(properties.get("not_before"))
        period_end = self._parse_year(properties.get("not_after"))

        # Filter: only include inscriptions with period_end <= 1500 (or no period_end)
        if period_end is not None and period_end > 1500:
            return None

        # Source URL: link to EDCS if list_id starts with "HD"
        source_url = None
        if list_id.startswith("HD"):
            source_url = f"https://db.edcs.eu/epigr/epi.php?s_hd_nr={list_id}"

        # Description
        description = self._build_description(properties)

        return ParsedSite(
            source_id=list_id,
            name=name,
            lat=lat,
            lon=lon,
            site_type="inscription",
            period_start=period_start,
            period_end=period_end,
            source_url=source_url,
            description=description,
            raw_data=properties,
        )

    def _parse_year(self, value) -> int | None:
        """
        Parse a year value from the dataset.

        Values are integer strings like "-100", "200".
        Negative values = BCE.

        Returns:
            Integer year or None if not parseable.
        """
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def _build_description(self, properties: dict) -> str | None:
        """Build a description string from available properties."""
        text = properties.get("text_cleaned", "")
        inscription_type = properties.get("type_of_inscription", "")
        material = properties.get("material", "")
        province = properties.get("province", "")

        parts = []
        if inscription_type:
            parts.append(f"Type: {inscription_type}")
        if material:
            parts.append(f"Material: {material}")
        if province:
            parts.append(f"Province: {province}")
        if text:
            # Truncate inscription text to keep description reasonable
            truncated = text[:200] + ("..." if len(text) > 200 else "")
            parts.append(truncated)

        if not parts:
            return None

        description = "; ".join(parts)
        return description[:500]


def ingest_list_inscriptions(session=None, skip_fetch: bool = False) -> dict:
    """Run LIST Latin Inscriptions ingestion."""
    with LISTInscriptionsIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
