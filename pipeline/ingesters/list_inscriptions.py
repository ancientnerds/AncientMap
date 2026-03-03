"""
LIST Latin Inscriptions ingester.

Downloads the LIST (Linked Inscriptions Search Tool) dataset containing
~525K Latin inscriptions with geographic coordinates from across the Roman world.

Data source: https://zenodo.org/records/10473706
License: CC-BY 4.0
API Key: Not required
"""

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite
from pipeline.utils.http import DEFAULT_HEADERS


class LISTInscriptionsIngester(BaseIngester):
    """
    Ingester for LIST Latin Inscriptions.

    LIST contains ~525K Latin inscriptions from the Roman world,
    sourced from the Epigraphic Database Heidelberg and EDCS.
    Downloaded as a GeoJSON FeatureCollection from Zenodo.
    """

    source_id = "list_inscriptions"
    source_name = "LIST Latin Inscriptions"

    DOWNLOAD_URL = "https://zenodo.org/records/10473706/files/LIST_v1-2.geojson?download=1"

    def fetch(self) -> Path:
        """
        Download the LIST GeoJSON from Zenodo.

        Uses streaming download because the file is ~1.2 GB.

        Returns:
            Path to the downloaded GeoJSON file.
        """
        dest_path = self.raw_data_dir / "list_inscriptions.geojson"

        logger.info(f"Downloading LIST inscriptions from {self.DOWNLOAD_URL}...")
        self.report_progress(0, None, "downloading ~1.2 GB GeoJSON from Zenodo...")

        # Stream the download -- too large for in-memory fetch_with_retry
        with httpx.Client(
            timeout=httpx.Timeout(connect=30, read=120, write=30, pool=30),
            follow_redirects=True,
        ) as client:
            with client.stream("GET", self.DOWNLOAD_URL, headers=DEFAULT_HEADERS) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0))
                downloaded = 0
                with open(dest_path, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=8 * 1024 * 1024):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = int(downloaded * 100 / total)
                            self.report_progress(
                                pct,
                                100,
                                f"downloaded {downloaded // (1024 * 1024)} MB / {total // (1024 * 1024)} MB",
                            )

        logger.info(f"Downloaded LIST inscriptions to {dest_path} ({downloaded:,} bytes)")
        return dest_path

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

        # Source ID: v1-2 uses "LIST-ID" (integer), with separate "EDH-ID" and "EDCS-ID"
        list_id = str(properties.get("LIST-ID", "")) or str(idx)

        # Name: prefer ancient findspot, then modern, then fallback
        # v1-2 uses "NULL" string instead of null for missing values
        ancient = properties.get("findspot_ancient_clean")
        modern = properties.get("findspot_modern_clean")
        if ancient and ancient != "NULL":
            name = ancient
        elif modern and modern != "NULL":
            name = modern
        else:
            name = f"Inscription {list_id}"

        # Period parsing
        period_start = self._parse_year(properties.get("not_before"))
        period_end = self._parse_year(properties.get("not_after"))

        # Filter: only include inscriptions with period_end <= 1500 (or no period_end)
        if period_end is not None and period_end > 1500:
            return None

        # Source URL: link to EDH if available, else EDCS
        edh_id = properties.get("EDH-ID")
        edcs_id = properties.get("EDCS-ID")
        source_url = None
        if edh_id:
            source_url = f"https://edh.ub.uni-heidelberg.de/edh/inschrift/{edh_id}"
        elif edcs_id:
            source_url = f"http://db.edcs.eu/epigr/epi_ergebnis.php?s_text={edcs_id}"

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
        text = properties.get("clean_text_conservative", "")
        inscription_type = properties.get("type_of_inscription_clean", "")
        material = properties.get("material_clean", "")
        province = properties.get("province_label_clean") or properties.get("province", "")

        parts = []
        if inscription_type and inscription_type != "NULL":
            parts.append(f"Type: {inscription_type}")
        if material and material != "NULL":
            parts.append(f"Material: {material}")
        if province and province != "NULL":
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
