"""
NCEI Significant Earthquakes database ingester.

Uses the ArcGIS REST endpoint which has 6,500+ significant earthquakes
with detailed impact data (deaths, damage, descriptions).

Data source: https://gis.ngdc.noaa.gov/arcgis/rest/services/web_mercator/hazards/MapServer/5
License: Public Domain (US Government)
API Key: Not required
"""

import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_json
from pipeline.utils.http import fetch_with_retry


class NCEIEarthquakesIngester(BaseIngester):
    """
    Ingester for NCEI Significant Earthquakes database.

    Downloads significant earthquake data including location, magnitude,
    and socioeconomic impact (casualties, damage estimates, descriptions).
    """

    source_id = "ncei_earthquakes"
    source_name = "NCEI Significant Earthquakes"

    # ArcGIS REST endpoint for significant earthquakes (Layer 5)
    API_URL = "https://gis.ngdc.noaa.gov/arcgis/rest/services/web_mercator/hazards/MapServer/5/query"

    # Max records per request (ArcGIS limit)
    PAGE_SIZE = 1000

    def fetch(self) -> Path:
        """
        Fetch all significant earthquakes from NCEI ArcGIS API.

        Returns:
            Path to JSON file with earthquake data
        """
        dest_path = self.raw_data_dir / "ncei_earthquakes.json"

        logger.info("Fetching NCEI Significant Earthquakes data...")
        self.report_progress(0, None, "starting...")

        all_earthquakes = []
        offset = 0

        headers = {
            "Accept": "application/json",
            "User-Agent": "AncientNerds/1.0 (Research Platform; archaeological research)",
        }

        while True:
            params = {
                "where": "1=1",
                "outFields": "*",
                "f": "json",
                "resultOffset": str(offset),
                "resultRecordCount": str(self.PAGE_SIZE),
            }
            query_string = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{self.API_URL}?{query_string}"

            logger.info(f"Fetching page at offset {offset}...")

            try:
                response = fetch_with_retry(url, headers=headers, timeout=120)

                if response.status_code != 200:
                    logger.warning(f"API returned status {response.status_code}")
                    break

                data = response.json()
                features = data.get("features", [])

                if not features:
                    logger.info("No more features, pagination complete")
                    break

                for feature in features:
                    parsed = self._parse_earthquake(feature)
                    if parsed:
                        all_earthquakes.append(parsed)

                logger.info(f"Fetched {len(features)} earthquakes (total: {len(all_earthquakes)})")
                self.report_progress(len(all_earthquakes), None, f"{len(all_earthquakes):,} earthquakes")

                if len(features) < self.PAGE_SIZE:
                    break

                offset += self.PAGE_SIZE

            except Exception as e:
                logger.error(f"Failed to fetch page at offset {offset}: {e}")
                break

        logger.info(f"Total earthquakes: {len(all_earthquakes):,}")

        output = {
            "earthquakes": all_earthquakes,
            "metadata": {
                "source": "NCEI Significant Earthquakes Database",
                "source_url": "https://gis.ngdc.noaa.gov/arcgis/rest/services/web_mercator/hazards/MapServer/5",
                "fetched_at": datetime.utcnow().isoformat(),
                "total_earthquakes": len(all_earthquakes),
                "license": "Public Domain",
                "attribution": "NOAA NCEI Natural Hazards",
            }
        }

        atomic_write_json(dest_path, output)
        logger.info(f"Saved {len(all_earthquakes):,} earthquakes to {dest_path}")
        return dest_path

    def _parse_earthquake(self, feature: dict) -> dict | None:
        """Parse a single earthquake feature from the ArcGIS response."""
        attrs = feature.get("attributes", {})

        lat = attrs.get("LATITUDE")
        lon = attrs.get("LONGITUDE")

        if lat is None or lon is None:
            return None

        try:
            lat = float(lat)
            lon = float(lon)
        except (ValueError, TypeError):
            return None

        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None

        return {
            "id": str(attrs.get("ID") or attrs.get("OBJECTID")),
            "year": attrs.get("YEAR"),
            "month": attrs.get("MONTH"),
            "day": attrs.get("DAY"),
            "lat": lat,
            "lon": lon,
            "location_name": attrs.get("LOCATION_NAME", ""),
            "country": attrs.get("COUNTRY", ""),
            "region": attrs.get("REGION", ""),
            "magnitude": attrs.get("EQ_MAGNITUDE"),
            "depth_km": attrs.get("EQ_DEPTH"),
            "intensity": attrs.get("INTENSITY"),
            "deaths": attrs.get("DEATHS"),
            "deaths_total": attrs.get("DEATHS_TOTAL"),
            "deaths_description": attrs.get("DEATHS_DESCRIPTION"),
            "injuries": attrs.get("INJURIES"),
            "injuries_total": attrs.get("INJURIES_TOTAL"),
            "missing": attrs.get("MISSING"),
            "damage_millions_usd": attrs.get("DAMAGE_MILLIONS_DOLLARS"),
            "damage_description": attrs.get("DAMAGE_DESCRIPTION"),
            "houses_destroyed": attrs.get("HOUSES_DESTROYED"),
            "houses_damaged": attrs.get("HOUSES_DAMAGED"),
        }

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """Parse NCEI earthquake data into ParsedSite objects."""
        logger.info(f"Parsing NCEI earthquake data from {raw_data_path}")

        with open(raw_data_path, encoding="utf-8") as f:
            data = json.load(f)

        earthquakes = data.get("earthquakes", [])
        logger.info(f"Processing {len(earthquakes)} earthquakes")

        for eq in earthquakes:
            site = self._earthquake_to_site(eq)
            if site:
                yield site

    def _earthquake_to_site(self, eq: dict) -> ParsedSite | None:
        """Convert an earthquake record to a ParsedSite."""
        lat = eq.get("lat")
        lon = eq.get("lon")

        if lat is None or lon is None:
            return None

        # Build name
        location = eq.get("location_name", "")
        year = eq.get("year")
        mag = eq.get("magnitude")

        name_parts = [location] if location else ["Earthquake"]
        if mag:
            name_parts.append(f"M{mag:.1f}")
        if year:
            if year < 0:
                name_parts.append(f"({abs(year)} BCE)")
            else:
                name_parts.append(f"({year})")

        name = " ".join(name_parts)

        # Build description from available fields
        desc_parts = []
        if eq.get("deaths_description"):
            desc_parts.append(eq["deaths_description"])
        elif eq.get("deaths_total"):
            desc_parts.append(f"Deaths: {eq['deaths_total']:,}")
        if eq.get("damage_description"):
            desc_parts.append(eq["damage_description"])
        if eq.get("magnitude"):
            desc_parts.append(f"Magnitude: {eq['magnitude']}")
        if eq.get("depth_km"):
            desc_parts.append(f"Depth: {eq['depth_km']} km")

        description = ". ".join(desc_parts) if desc_parts else None

        return ParsedSite(
            source_id=eq["id"],
            name=name,
            lat=lat,
            lon=lon,
            alternative_names=[],
            description=description,
            site_type="earthquake",
            period_start=eq.get("year"),
            period_end=eq.get("year"),
            period_name=None,
            precision_meters=10000,
            precision_reason="earthquake_epicenter",
            source_url=f"https://www.ngdc.noaa.gov/hazel/view/hazards/earthquake/event-more-info/{eq['id']}",
            raw_data=eq,
        )


def ingest_ncei_earthquakes(session=None, skip_fetch: bool = False) -> dict:
    """Run NCEI Earthquakes ingestion."""
    with NCEIEarthquakesIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
