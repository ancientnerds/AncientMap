"""
NCEI Tsunami Events database ingester.

Uses the ArcGIS REST endpoint which has 2,500+ tsunami events
with detailed impact data (deaths, damage, runup heights, descriptions).

Data source: https://gis.ngdc.noaa.gov/arcgis/rest/services/web_mercator/hazards/MapServer/0
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


class NCEITsunamisIngester(BaseIngester):
    """
    Ingester for NCEI Tsunami Events database.

    Downloads tsunami event data including location, cause, runup heights,
    and socioeconomic impact (casualties, damage estimates, descriptions).
    """

    source_id = "ncei_tsunamis"
    source_name = "NCEI Tsunami Events"

    # ArcGIS REST endpoint for tsunami events (Layer 0)
    API_URL = "https://gis.ngdc.noaa.gov/arcgis/rest/services/web_mercator/hazards/MapServer/0/query"

    # Max records per request (ArcGIS limit)
    PAGE_SIZE = 1000

    def fetch(self) -> Path:
        """
        Fetch all tsunami events from NCEI ArcGIS API.

        Returns:
            Path to JSON file with tsunami data
        """
        dest_path = self.raw_data_dir / "ncei_tsunamis.json"

        logger.info("Fetching NCEI Tsunami Events data...")
        self.report_progress(0, None, "starting...")

        all_tsunamis = []
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
                    parsed = self._parse_tsunami(feature)
                    if parsed:
                        all_tsunamis.append(parsed)

                logger.info(f"Fetched {len(features)} tsunamis (total: {len(all_tsunamis)})")
                self.report_progress(len(all_tsunamis), None, f"{len(all_tsunamis):,} tsunamis")

                if len(features) < self.PAGE_SIZE:
                    break

                offset += self.PAGE_SIZE

            except Exception as e:
                logger.error(f"Failed to fetch page at offset {offset}: {e}")
                break

        logger.info(f"Total tsunamis: {len(all_tsunamis):,}")

        output = {
            "tsunamis": all_tsunamis,
            "metadata": {
                "source": "NCEI Tsunami Events Database",
                "source_url": "https://gis.ngdc.noaa.gov/arcgis/rest/services/web_mercator/hazards/MapServer/0",
                "fetched_at": datetime.utcnow().isoformat(),
                "total_tsunamis": len(all_tsunamis),
                "license": "Public Domain",
                "attribution": "NOAA NCEI Natural Hazards",
            }
        }

        atomic_write_json(dest_path, output)
        logger.info(f"Saved {len(all_tsunamis):,} tsunamis to {dest_path}")
        return dest_path

    def _parse_tsunami(self, feature: dict) -> dict | None:
        """Parse a single tsunami feature from the ArcGIS response."""
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
            "cause": attrs.get("CAUSE", ""),
            "cause_code": attrs.get("CAUSE_CODE"),
            "event_validity": attrs.get("EVENT_VALIDITY", ""),
            "max_runup_m": attrs.get("MAX_EVENT_RUNUP"),
            "tsunami_intensity": attrs.get("TS_INTENSITY"),
            "eq_magnitude": attrs.get("EQ_MAGNITUDE"),
            "eq_depth_km": attrs.get("EQ_DEPTH"),
            "deaths": attrs.get("DEATHS"),
            "deaths_total": attrs.get("DEATHS_TOTAL"),
            "deaths_description": attrs.get("DEATHS_DESCRIPTION"),
            "injuries": attrs.get("INJURIES"),
            "injuries_total": attrs.get("INJURIES_TOTAL"),
            "missing": attrs.get("MISSING"),
            "damage_millions_usd": attrs.get("DAMAGE_MILLIONS_DOLLARS"),
            "damage_description": attrs.get("DAMAGE_DESCRIPTION"),
            "houses_destroyed": attrs.get("HOUSES_DESTROYED"),
            "houses_destroyed_total": attrs.get("HOUSES_DESTROYED_TOTAL"),
            "comments": attrs.get("COMMENTS"),
            "num_observations": attrs.get("NUM_RUNUP"),
        }

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """Parse NCEI tsunami data into ParsedSite objects."""
        logger.info(f"Parsing NCEI tsunami data from {raw_data_path}")

        with open(raw_data_path, encoding="utf-8") as f:
            data = json.load(f)

        tsunamis = data.get("tsunamis", [])
        logger.info(f"Processing {len(tsunamis)} tsunamis")

        for ts in tsunamis:
            site = self._tsunami_to_site(ts)
            if site:
                yield site

    def _tsunami_to_site(self, ts: dict) -> ParsedSite | None:
        """Convert a tsunami record to a ParsedSite."""
        lat = ts.get("lat")
        lon = ts.get("lon")

        if lat is None or lon is None:
            return None

        # Build name
        location = ts.get("location_name", "")
        year = ts.get("year")
        cause = ts.get("cause", "")

        name_parts = []
        if location:
            name_parts.append(location)
        name_parts.append("Tsunami")
        if cause and cause != "Unknown":
            name_parts.append(f"({cause})")
        if year:
            if year < 0:
                name_parts.append(f"[{abs(year)} BCE]")
            else:
                name_parts.append(f"[{year}]")

        name = " ".join(name_parts)

        # Build description - prefer comments field which has detailed narratives
        desc_parts = []
        if ts.get("comments"):
            desc_parts.append(ts["comments"])
        else:
            if ts.get("deaths_description"):
                desc_parts.append(ts["deaths_description"])
            elif ts.get("deaths_total"):
                desc_parts.append(f"Deaths: {ts['deaths_total']:,}")
            if ts.get("damage_description"):
                desc_parts.append(ts["damage_description"])
            if ts.get("max_runup_m"):
                desc_parts.append(f"Max wave height: {ts['max_runup_m']}m")
            if ts.get("cause"):
                desc_parts.append(f"Cause: {ts['cause']}")

        description = ". ".join(desc_parts) if desc_parts else None
        # Truncate very long descriptions
        if description and len(description) > 2000:
            description = description[:1997] + "..."

        return ParsedSite(
            source_id=ts["id"],
            name=name,
            lat=lat,
            lon=lon,
            alternative_names=[],
            description=description,
            site_type="tsunami",
            period_start=ts.get("year"),
            period_end=ts.get("year"),
            period_name=None,
            precision_meters=10000,
            precision_reason="tsunami_source",
            source_url=f"https://www.ngdc.noaa.gov/hazel/view/hazards/tsunami/event-more-info/{ts['id']}",
            raw_data=ts,
        )


def ingest_ncei_tsunamis(session=None, skip_fetch: bool = False) -> dict:
    """Run NCEI Tsunamis ingestion."""
    with NCEITsunamisIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
