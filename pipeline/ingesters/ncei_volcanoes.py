"""
NCEI Significant Volcanic Eruptions database ingester.

Uses the NCEI Hazel API which has 900+ significant volcanic eruptions
with detailed impact data (deaths, damage, descriptions).

Data source: https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/volcanoes
License: Public Domain (US Government)
API Key: Not required
"""

import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_json
from pipeline.utils.http import fetch_with_retry


class NCEIVolcanoesIngester(BaseIngester):
    """
    Ingester for NCEI Significant Volcanic Eruptions database.

    Downloads significant volcanic eruption events including location, VEI,
    and socioeconomic impact (casualties, damage estimates, descriptions).
    """

    source_id = "ncei_volcanoes"
    source_name = "NCEI Significant Volcanic Eruptions"

    # NCEI Hazel API endpoint for volcanic eruptions
    LIST_API_URL = "https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/volcanoes"
    DETAIL_API_URL = "https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/volcanoes/{id}"

    # Page size (API default is 200)
    PAGE_SIZE = 200

    def fetch(self) -> Path:
        """
        Fetch all significant volcanic eruptions from NCEI Hazel API.

        Returns:
            Path to JSON file with volcano data
        """
        dest_path = self.raw_data_dir / "ncei_volcanoes.json"

        logger.info("Fetching NCEI Significant Volcanic Eruptions data...")
        self.report_progress(0, None, "starting...")

        headers = {
            "Accept": "application/json",
            "User-Agent": "AncientNerds/1.0 (Research Platform; archaeological research)",
        }

        # First, get all eruptions from list endpoint (paginated)
        all_eruptions = []
        page = 1
        total_pages = None

        while True:
            url = f"{self.LIST_API_URL}?page={page}"
            logger.info(f"Fetching page {page}...")

            try:
                response = fetch_with_retry(url, headers=headers, timeout=60)

                if response.status_code != 200:
                    logger.warning(f"API returned status {response.status_code}")
                    break

                data = response.json()
                items = data.get("items", [])
                total_pages = data.get("totalPages", 1)
                total_items = data.get("totalItems", 0)

                if not items:
                    break

                all_eruptions.extend(items)
                logger.info(f"Fetched {len(items)} eruptions (total: {len(all_eruptions)}/{total_items})")
                self.report_progress(len(all_eruptions), total_items, f"{len(all_eruptions):,} eruptions")

                if page >= total_pages:
                    break

                page += 1

            except Exception as e:
                logger.error(f"Failed to fetch page {page}: {e}")
                break

        logger.info(f"Fetched {len(all_eruptions)} eruptions from list. Fetching details...")

        # Now fetch details for each eruption to get the comments field
        def fetch_detail(eruption):
            eruption_id = eruption.get("id")
            if not eruption_id:
                return eruption

            try:
                url = self.DETAIL_API_URL.format(id=eruption_id)
                response = fetch_with_retry(url, headers=headers, timeout=30)
                if response.status_code == 200:
                    detail = response.json()
                    # Merge detail data into eruption
                    eruption["comments"] = detail.get("comments")
                    return eruption
            except Exception as e:
                logger.debug(f"Failed to fetch detail for {eruption_id}: {e}")
            return eruption

        # Fetch details in parallel (limit concurrency to be respectful)
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_detail, e): e for e in all_eruptions}
            completed = 0
            for _future in as_completed(futures):
                completed += 1
                if completed % 100 == 0:
                    logger.info(f"Fetched details for {completed}/{len(all_eruptions)} eruptions")
                    self.report_progress(completed, len(all_eruptions), f"details: {completed:,}/{len(all_eruptions):,}")

        # Parse eruptions
        parsed_eruptions = []
        for eruption in all_eruptions:
            parsed = self._parse_eruption(eruption)
            if parsed:
                parsed_eruptions.append(parsed)

        logger.info(f"Total eruptions: {len(parsed_eruptions):,}")
        self.report_progress(len(parsed_eruptions), len(parsed_eruptions), f"{len(parsed_eruptions):,} eruptions")

        output = {
            "volcanoes": parsed_eruptions,
            "metadata": {
                "source": "NCEI Significant Volcanic Eruptions Database",
                "source_url": "https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/volcanoes",
                "fetched_at": datetime.utcnow().isoformat(),
                "total_eruptions": len(parsed_eruptions),
                "data_type": "volcanic_eruptions",
                "license": "Public Domain",
                "attribution": "NOAA NCEI Natural Hazards",
            }
        }

        atomic_write_json(dest_path, output)
        logger.info(f"Saved {len(parsed_eruptions):,} eruptions to {dest_path}")
        return dest_path

    def _parse_eruption(self, eruption: dict) -> dict | None:
        """Parse a single eruption from the API response."""
        lat = eruption.get("latitude")
        lon = eruption.get("longitude")

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
            "id": str(eruption.get("id")),
            "year": eruption.get("year"),
            "month": eruption.get("month"),
            "day": eruption.get("day"),
            "lat": lat,
            "lon": lon,
            "name": eruption.get("name", ""),
            "location_name": eruption.get("location", ""),
            "country": eruption.get("country", ""),
            "vei": eruption.get("vei"),
            "morphology": eruption.get("morphology", ""),
            "elevation_m": eruption.get("elevation"),
            "status": eruption.get("status", ""),
            "time_erupt": eruption.get("timeErupt", ""),
            "agent": eruption.get("agent", ""),
            "deaths": eruption.get("deaths"),
            "deaths_total": eruption.get("deathsTotal"),
            "damage_amount_order_total": eruption.get("damageAmountOrderTotal"),
            "deaths_amount_order_total": eruption.get("deathsAmountOrderTotal"),
            "comments": eruption.get("comments"),
        }

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """Parse NCEI volcano data into ParsedSite objects."""
        logger.info(f"Parsing NCEI volcanic eruption data from {raw_data_path}")

        with open(raw_data_path, encoding="utf-8") as f:
            data = json.load(f)

        eruptions = data.get("volcanoes", [])
        logger.info(f"Processing {len(eruptions)} eruptions")

        for eruption in eruptions:
            site = self._eruption_to_site(eruption)
            if site:
                yield site

    def _eruption_to_site(self, eruption: dict) -> ParsedSite | None:
        """Convert an eruption record to a ParsedSite."""
        lat = eruption.get("lat")
        lon = eruption.get("lon")

        if lat is None or lon is None:
            return None

        # Build name
        name = eruption.get("name", "")
        year = eruption.get("year")

        name_parts = [name] if name else ["Volcanic Eruption"]
        if year:
            if year < 0:
                name_parts.append(f"({abs(year)} BCE)")
            else:
                name_parts.append(f"({year})")

        site_name = " ".join(name_parts)

        # Use comments as description if available, otherwise build from fields
        description = eruption.get("comments")
        if not description:
            desc_parts = []
            if eruption.get("morphology"):
                desc_parts.append(eruption["morphology"])
            if eruption.get("vei"):
                desc_parts.append(f"VEI: {eruption['vei']}")
            if eruption.get("deaths_total"):
                desc_parts.append(f"Deaths: {eruption['deaths_total']:,}")
            if eruption.get("agent"):
                agent_map = {"P": "Pyroclastic flow", "T": "Tsunami", "M": "Mudflow/Lahar", "L": "Lava"}
                agent_desc = agent_map.get(eruption["agent"], eruption["agent"])
                desc_parts.append(f"Agent: {agent_desc}")
            description = ". ".join(desc_parts) if desc_parts else None

        # Truncate very long descriptions
        if description and len(description) > 2000:
            description = description[:1997] + "..."

        return ParsedSite(
            source_id=eruption["id"],
            name=site_name,
            lat=lat,
            lon=lon,
            alternative_names=[],
            description=description,
            site_type="volcano",
            period_start=eruption.get("year"),
            period_end=eruption.get("year"),
            period_name=None,
            precision_meters=10000,
            precision_reason="volcanic_eruption",
            source_url=f"https://www.ngdc.noaa.gov/hazel/view/hazards/volcano/event-more-info/{eruption['id']}",
            raw_data=eruption,
        )


def ingest_ncei_volcanoes(session=None, skip_fetch: bool = False) -> dict:
    """Run NCEI Volcanoes ingestion."""
    with NCEIVolcanoesIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
