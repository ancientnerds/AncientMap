"""
HolVol volcanic eruptions database ingester.

HolVol contains 850+ volcanic eruptions from the Holocene
with sulfur injection estimates and climate impact data.
Critical for understanding historical climate events.

Data source: https://doi.org/10.1594/PANGAEA.928646
License: CC BY 4.0
API Key: Not required
"""

import csv
import io
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_json
from pipeline.utils.http import fetch_with_retry


class HolVolIngester(BaseIngester):
    """
    Ingester for HolVol volcanic eruptions database.

    Downloads volcanic eruption data from PANGAEA including
    dates, sulfur emissions, and climate impacts.
    """

    source_id = "volcanic_holvol"
    source_name = "HolVol Volcanic Database"

    # PANGAEA data download
    PANGAEA_URL = "https://doi.pangaea.de/10.1594/PANGAEA.928646"
    PANGAEA_DATA_URL = "https://doi.pangaea.de/10.1594/PANGAEA.928646?format=textfile"

    # Alternative direct download
    DATA_URLS = [
        "https://hs.pangaea.de/Maps/VICS/HolVol_v1.0.csv",
        "https://store.pangaea.de/Publications/TooheyM-etal_2021/HolVol_v1.0.csv",
    ]

    # Smithsonian GVP for volcano locations
    GVP_URL = "https://volcano.si.edu/database/search_eruption_results.cfm"
    GVP_API = "https://webservices.volcano.si.edu/geoserver/GVP-VOTW/ows"

    def fetch(self) -> Path:
        """
        Fetch HolVol volcanic eruption data.

        Returns:
            Path to JSON file with eruption data
        """
        dest_path = self.raw_data_dir / "volcanic_holvol.json"

        logger.info("Fetching HolVol volcanic eruption data...")
        self.report_progress(0, None, "starting...")

        all_eruptions = []
        seen_ids = set()

        headers = {
            "Accept": "text/csv, application/json",
            "User-Agent": "AncientNerds/1.0 (Research Platform; climate research)",
        }

        # Try to download HolVol data
        csv_content = None

        for url in self.DATA_URLS:
            logger.info(f"Trying: {url}")
            try:
                response = fetch_with_retry(url, headers=headers, timeout=120)

                if response.status_code == 200:
                    csv_content = response.text
                    logger.info(f"Downloaded {len(csv_content):,} bytes from {url}")
                    break

            except Exception as e:
                logger.debug(f"Failed to fetch {url}: {e}")

        # Try PANGAEA API
        if not csv_content:
            logger.info("Trying PANGAEA API...")
            try:
                response = fetch_with_retry(
                    self.PANGAEA_DATA_URL,
                    headers=headers,
                    timeout=120,
                )

                if response.status_code == 200:
                    csv_content = response.text

            except Exception as e:
                logger.debug(f"PANGAEA API failed: {e}")

        # Parse CSV content
        if csv_content:
            all_eruptions = self._parse_csv(csv_content)
            logger.info(f"Parsed {len(all_eruptions)} eruptions from CSV")

        # Try Smithsonian GVP for additional volcano data
        if len(all_eruptions) < 100:
            logger.info("Fetching Smithsonian GVP data...")
            gvp_eruptions = self._fetch_gvp_data(headers)
            for eruption in gvp_eruptions:
                if eruption["id"] not in seen_ids:
                    seen_ids.add(eruption["id"])
                    all_eruptions.append(eruption)

        # If all API sources failed, mark unavailable rather than using hardcoded data
        if len(all_eruptions) < 50:
            if len(all_eruptions) == 0:
                self.available = False
                self.unavailable_reason = (
                    "Both PANGAEA and Smithsonian GVP APIs returned no data. "
                    "Check endpoint availability."
                )
            else:
                logger.warning(f"Only {len(all_eruptions)} eruptions fetched (below 50 threshold)")

        logger.info(f"Total eruptions: {len(all_eruptions):,}")
        self.report_progress(
            len(all_eruptions), len(all_eruptions), f"{len(all_eruptions):,} eruptions"
        )

        # Save to file
        output = {
            "eruptions": all_eruptions,
            "metadata": {
                "source": "HolVol / Smithsonian GVP",
                "source_url": "https://doi.org/10.1594/PANGAEA.928646",
                "gvp_url": "https://volcano.si.edu/",
                "fetched_at": datetime.now(UTC).isoformat(),
                "total_eruptions": len(all_eruptions),
                "data_type": "volcanic_eruptions",
                "license": "CC BY 4.0",
                "citation": "Toohey, M. and Sigl, M. (2017). Volcanic stratospheric sulfur injections and aerosol optical depth from 500 BCE to 1900 CE. Earth System Science Data.",
            },
        }

        atomic_write_json(dest_path, output)

        logger.info(f"Saved {len(all_eruptions):,} eruptions to {dest_path}")
        return dest_path

    def _parse_csv(self, content: str) -> list[dict]:
        """Parse HolVol CSV content."""
        eruptions = []

        # Skip comment lines (start with //)
        lines = [
            l
            for l in content.strip().split("\n")
            if not l.startswith("//") and not l.startswith("/*")
        ]

        if not lines:
            return eruptions

        # Find header line
        reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter="\t")

        for i, row in enumerate(reader):
            eruption = self._parse_csv_row(row, i)
            if eruption:
                eruptions.append(eruption)

        return eruptions

    def _parse_csv_row(self, row: dict, index: int) -> dict | None:
        """Parse a single CSV row."""
        # Get year - might be in different columns
        year = None
        for col in ["Year", "year", "Date", "Age", "Age [ka BP]", "Year CE"]:
            if col in row and row[col]:
                try:
                    val = float(row[col])
                    # Convert ka BP to CE if needed
                    if "ka" in col.lower() or "bp" in col.lower():
                        year = int(1950 - val * 1000)
                    else:
                        year = int(val)
                    break
                except (ValueError, TypeError, OverflowError):
                    pass

        if year is None:
            return None

        eruption_id = f"holvol_{abs(year)}_{index}"

        # Get volcano name and location
        volcano = ""
        lat, lon = None, None

        for col in ["Volcano", "volcano", "Name", "Source"]:
            if col in row and row[col]:
                volcano = row[col]
                break

        for col in ["Lat", "lat", "Latitude"]:
            if col in row:
                lat = self._parse_float(row[col])
                break

        for col in ["Lon", "lon", "Long", "Longitude"]:
            if col in row:
                lon = self._parse_float(row[col])
                break

        # Get sulfur injection
        sulfur = None
        for col in ["SO2", "Sulfur", "SAOD", "Total SO2 [Tg]", "Sulfur [Tg]"]:
            if col in row:
                sulfur = self._parse_float(row[col])
                break

        # Get VEI
        vei = None
        for col in ["VEI", "vei", "Magnitude"]:
            if col in row:
                vei = self._parse_int(row[col])
                break

        return {
            "id": eruption_id,
            "year": year,
            "volcano_name": volcano,
            "lat": lat,
            "lon": lon,
            "sulfur_tg": sulfur,
            "vei": vei,
            "hemisphere": row.get("Hemisphere", row.get("hemisphere", "")),
            "ice_core_signal": row.get("Ice Core", row.get("ice_core", "")),
            "uncertainty_years": self._parse_int(row.get("Uncertainty", row.get("Error", ""))),
        }

    def _fetch_gvp_data(self, headers: dict) -> list[dict]:
        """Fetch data from Smithsonian Global Volcanism Program."""
        eruptions = []

        try:
            # Query GVP WFS for Holocene volcanoes
            params = {
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeName": "GVP-VOTW:Smithsonian_VOTW_Holocene_Volcanoes",
                "outputFormat": "application/json",
                "count": 1500,
            }

            response = fetch_with_retry(
                self.GVP_API,
                params=params,
                headers=headers,
                timeout=120,
            )

            if response.status_code == 200:
                data = response.json()
                features = data.get("features", [])

                for feature in features:
                    eruption = self._parse_gvp_feature(feature)
                    if eruption:
                        eruptions.append(eruption)

        except Exception as e:
            logger.debug(f"GVP WFS query failed: {e}")

        return eruptions

    def _parse_gvp_feature(self, feature: dict) -> dict | None:
        """Parse a GVP volcano feature."""
        if not feature:
            return None

        props = feature.get("properties", {})
        geom = feature.get("geometry", {})

        lat, lon = None, None
        if geom.get("type") == "Point":
            coords = geom.get("coordinates", [])
            if len(coords) >= 2:
                lon, lat = coords[0], coords[1]

        volcano_num = props.get("Volcano_Number", props.get("vnum", ""))
        if not volcano_num:
            return None

        # Get last eruption year
        last_eruption = props.get("Last_Eruption_Year", props.get("last_eruption", ""))
        year = self._parse_int(last_eruption)

        return {
            "id": f"gvp_{volcano_num}",
            "year": year,
            "volcano_name": props.get("Volcano_Name", props.get("name", "")),
            "lat": lat,
            "lon": lon,
            "vei": self._parse_int(props.get("VEI", "")),
            "volcano_type": props.get("Primary_Volcano_Type", props.get("type", "")),
            "country": props.get("Country", ""),
            "region": props.get("Region", ""),
            "elevation_m": self._parse_int(props.get("Elevation", "")),
        }

    def _parse_float(self, value) -> float | None:
        """Parse a float value."""
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _parse_int(self, value) -> int | None:
        """Parse an integer value."""
        if value is None or value == "":
            return None
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """Parse HolVol data into ParsedSite objects."""
        logger.info(f"Parsing HolVol data from {raw_data_path}")

        with open(raw_data_path, encoding="utf-8") as f:
            data = json.load(f)

        eruptions = data.get("eruptions", [])
        logger.info(f"Processing {len(eruptions)} eruptions")

        for eruption in eruptions:
            site = self._eruption_to_site(eruption)
            if site:
                yield site

    def _eruption_to_site(self, eruption: dict) -> ParsedSite | None:
        """Convert an eruption to a ParsedSite."""
        lat = eruption.get("lat")
        lon = eruption.get("lon")

        # Some eruptions have unknown locations
        if lat is None or lon is None:
            return None

        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None

        name = eruption.get("volcano_name", "")
        year = eruption.get("year")

        if not name and year:
            name = f"Eruption {year}"
        elif not name:
            name = f"Unknown eruption {eruption['id']}"

        if year:
            if year < 0:
                name += f" ({abs(year)} BCE)"
            else:
                name += f" ({year} CE)"

        # Build description
        desc_parts = []
        if eruption.get("vei"):
            desc_parts.append(f"VEI: {eruption['vei']}")
        if eruption.get("sulfur_tg"):
            desc_parts.append(f"Sulfur: {eruption['sulfur_tg']} Tg")
        if eruption.get("hemisphere"):
            desc_parts.append(f"Hemisphere: {eruption['hemisphere']}")

        return ParsedSite(
            source_id=eruption["id"],
            name=name,
            lat=lat,
            lon=lon,
            alternative_names=[],
            description="; ".join(desc_parts) if desc_parts else None,
            site_type="volcanic_eruption",
            period_start=year,
            period_end=year,
            period_name=None,
            precision_meters=10000,  # Volcanic events affect large areas
            precision_reason="volcano",
            source_url="https://doi.org/10.1594/PANGAEA.928646",
            raw_data=eruption,
        )


def ingest_holvol(session=None, skip_fetch: bool = False) -> dict:
    """Run HolVol ingestion."""
    with HolVolIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
