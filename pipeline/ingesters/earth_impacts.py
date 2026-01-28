"""
Earth Impact Craters database ingester.

Contains ~200 confirmed impact craters on Earth from the
Planetary and Space Science Centre (PASSC) Earth Impact Database.

Data source: http://www.passc.net/EarthImpactDatabase/
License: Public data for research
"""

import json
from pathlib import Path
from typing import Iterator, Optional

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite


class EarthImpactsIngester(BaseIngester):
    """
    Ingester for Earth Impact Craters database.

    Uses pre-downloaded GeoJSON from PASSC Earth Impact Database.
    """

    source_id = "earth_impacts"
    source_name = "Earth Impact Craters"

    def fetch(self) -> Path:
        """
        Return path to existing GeoJSON file.
        Data is pre-downloaded from PASSC.
        """
        # Look for existing geojson
        geojson_path = Path("data/raw/earth_impacts/earth_impacts.geojson")

        if not geojson_path.exists():
            raise FileNotFoundError(
                f"Earth impacts GeoJSON not found at {geojson_path}. "
                "Please download from http://www.passc.net/EarthImpactDatabase/"
            )

        logger.info(f"Using existing earth impacts data: {geojson_path}")
        return geojson_path

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """Parse Earth Impact Craters GeoJSON into ParsedSite objects."""
        logger.info(f"Parsing earth impacts from {raw_data_path}")

        with open(raw_data_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        features = data.get("features", [])
        logger.info(f"Processing {len(features)} impact craters")

        for i, feature in enumerate(features):
            site = self._feature_to_site(feature, i)
            if site:
                yield site

    def _feature_to_site(self, feature: dict, index: int) -> Optional[ParsedSite]:
        """Convert a GeoJSON feature to a ParsedSite."""
        props = feature.get("properties", {})
        geom = feature.get("geometry", {})

        # Get coordinates
        if geom.get("type") != "Point":
            return None

        coords = geom.get("coordinates", [])
        if len(coords) < 2:
            return None

        lon, lat = coords[0], coords[1]

        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None

        # Get crater name
        name = props.get("crater_name", f"Impact Crater {index}")

        # Get location info
        country = props.get("country", "")
        state = props.get("state", "")
        location = ", ".join(filter(None, [state, country]))

        # Get diameter
        diameter_km = props.get("diameter_km")

        # Parse age (in millions of years ago)
        age_str = props.get("age_millions_years_ago", "")
        period_start = self._parse_age(age_str)

        # Build description
        desc_parts = []
        if diameter_km:
            desc_parts.append(f"Diameter: {diameter_km} km")
        if age_str:
            desc_parts.append(f"Age: {age_str} million years ago")
        if props.get("target_rock"):
            desc_parts.append(f"Target rock: {props['target_rock']}")
        if props.get("bolid_type"):
            desc_parts.append(f"Bolide type: {props['bolid_type']}")
        if props.get("exposed"):
            desc_parts.append("Exposed: Yes" if props["exposed"] else "Buried")

        # Generate unique ID
        crater_id = name.lower().replace(" ", "_").replace("'", "")
        source_id = f"impact_{crater_id}_{index}"

        # Add country to description if available
        if location:
            desc_parts.append(f"Location: {location}")

        return ParsedSite(
            source_id=source_id,
            name=f"{name} Impact Crater",
            lat=lat,
            lon=lon,
            alternative_names=[name] if name != f"Impact Crater {index}" else [],
            description="; ".join(desc_parts) if desc_parts else None,
            site_type="impact_crater",
            period_start=period_start,
            period_end=period_start,
            period_name=self._get_period_name(period_start),
            precision_meters=int((diameter_km or 1) * 500),  # Precision based on crater size
            precision_reason="crater_size",
            source_url=props.get("url", "http://www.passc.net/EarthImpactDatabase/"),
            raw_data=props,
        )

    def _parse_age(self, age_str: str) -> Optional[int]:
        """
        Parse age string (in millions of years ago) to a year.
        Returns negative year for ancient dates.
        """
        if not age_str or age_str == "-":
            return None

        try:
            # Handle ranges like "290 ± 20" or "1640 - 600"
            age_str = age_str.replace("~", "").replace("<", "").replace(">", "")

            if "±" in age_str:
                age_str = age_str.split("±")[0].strip()
            elif " - " in age_str:
                # Take midpoint of range
                parts = age_str.split(" - ")
                age_str = str((float(parts[0]) + float(parts[1])) / 2)

            # Parse the number (millions of years ago)
            mya = float(age_str)

            # Convert to year (negative = BCE)
            # 1 million years ago = year -1,000,000
            year = int(-mya * 1_000_000)

            # Cap at reasonable ancient limit
            if year < -100_000_000:
                year = -100_000_000

            return year

        except (ValueError, TypeError):
            return None

    def _get_period_name(self, year: Optional[int]) -> Optional[str]:
        """Get geological period name from year."""
        if year is None:
            return None

        mya = abs(year) / 1_000_000

        if mya < 0.01:  # Less than 10,000 years
            return "Holocene"
        elif mya < 2.6:
            return "Pleistocene"
        elif mya < 5.3:
            return "Pliocene"
        elif mya < 23:
            return "Miocene"
        elif mya < 34:
            return "Oligocene"
        elif mya < 56:
            return "Eocene"
        elif mya < 66:
            return "Paleocene"
        elif mya < 145:
            return "Cretaceous"
        elif mya < 201:
            return "Jurassic"
        elif mya < 252:
            return "Triassic"
        elif mya < 299:
            return "Permian"
        elif mya < 359:
            return "Carboniferous"
        elif mya < 419:
            return "Devonian"
        elif mya < 444:
            return "Silurian"
        elif mya < 485:
            return "Ordovician"
        elif mya < 541:
            return "Cambrian"
        else:
            return "Precambrian"


def ingest_earth_impacts(session=None, skip_fetch: bool = False) -> dict:
    """Run Earth Impacts ingestion."""
    with EarthImpactsIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
