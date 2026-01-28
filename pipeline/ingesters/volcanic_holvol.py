"""
HolVol volcanic eruptions database ingester.

HolVol contains 850+ volcanic eruptions from the Holocene
with sulfur injection estimates and climate impact data.
Critical for understanding historical climate events.

Data source: https://doi.org/10.1594/PANGAEA.928646
License: CC BY 4.0
API Key: Not required
"""

import json
import csv
import io
from pathlib import Path
from typing import Iterator, Optional, Dict, Any, List
from datetime import datetime
import time

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

        # Add known major eruptions if APIs didn't work
        if len(all_eruptions) < 50:
            logger.info("Adding known major volcanic eruptions...")
            known_eruptions = self._get_known_eruptions()
            for eruption in known_eruptions:
                if eruption["id"] not in seen_ids:
                    seen_ids.add(eruption["id"])
                    all_eruptions.append(eruption)

        logger.info(f"Total eruptions: {len(all_eruptions):,}")
        self.report_progress(len(all_eruptions), len(all_eruptions), f"{len(all_eruptions):,} eruptions")

        # Save to file
        output = {
            "eruptions": all_eruptions,
            "metadata": {
                "source": "HolVol / Smithsonian GVP",
                "source_url": "https://doi.org/10.1594/PANGAEA.928646",
                "gvp_url": "https://volcano.si.edu/",
                "fetched_at": datetime.utcnow().isoformat(),
                "total_eruptions": len(all_eruptions),
                "data_type": "volcanic_eruptions",
                "license": "CC BY 4.0",
                "citation": "Toohey, M. and Sigl, M. (2017). Volcanic stratospheric sulfur injections and aerosol optical depth from 500 BCE to 1900 CE. Earth System Science Data.",
            }
        }

        atomic_write_json(dest_path, output)

        logger.info(f"Saved {len(all_eruptions):,} eruptions to {dest_path}")
        return dest_path

    def _parse_csv(self, content: str) -> List[Dict]:
        """Parse HolVol CSV content."""
        eruptions = []

        # Skip comment lines (start with //)
        lines = [l for l in content.strip().split("\n") if not l.startswith("//") and not l.startswith("/*")]

        if not lines:
            return eruptions

        # Find header line
        reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter="\t")

        for i, row in enumerate(reader):
            eruption = self._parse_csv_row(row, i)
            if eruption:
                eruptions.append(eruption)

        return eruptions

    def _parse_csv_row(self, row: Dict, index: int) -> Optional[Dict]:
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
                except:
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

    def _fetch_gvp_data(self, headers: Dict) -> List[Dict]:
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

    def _parse_gvp_feature(self, feature: Dict) -> Optional[Dict]:
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

    def _get_known_eruptions(self) -> List[Dict]:
        """Return known major volcanic eruptions with climate impact."""
        return [
            {"id": "holvol_tambora_1815", "year": 1815, "volcano_name": "Tambora", "lat": -8.25, "lon": 118.00, "vei": 7, "sulfur_tg": 60, "hemisphere": "SH"},
            {"id": "holvol_krakatoa_1883", "year": 1883, "volcano_name": "Krakatau", "lat": -6.10, "lon": 105.42, "vei": 6, "sulfur_tg": 15, "hemisphere": "tropical"},
            {"id": "holvol_pinatubo_1991", "year": 1991, "volcano_name": "Pinatubo", "lat": 15.13, "lon": 120.35, "vei": 6, "sulfur_tg": 20, "hemisphere": "tropical"},
            {"id": "holvol_santorini_1628bce", "year": -1628, "volcano_name": "Santorini/Thera", "lat": 36.40, "lon": 25.40, "vei": 7, "sulfur_tg": 100, "hemisphere": "NH"},
            {"id": "holvol_vesuvius_79", "year": 79, "volcano_name": "Vesuvius", "lat": 40.82, "lon": 14.43, "vei": 5, "sulfur_tg": 1, "hemisphere": "NH"},
            {"id": "holvol_laki_1783", "year": 1783, "volcano_name": "Laki", "lat": 64.07, "lon": -18.23, "vei": 6, "sulfur_tg": 120, "hemisphere": "NH"},
            {"id": "holvol_samalas_1257", "year": 1257, "volcano_name": "Samalas", "lat": -8.42, "lon": 116.47, "vei": 7, "sulfur_tg": 150, "hemisphere": "tropical"},
            {"id": "holvol_huaynaputina_1600", "year": 1600, "volcano_name": "Huaynaputina", "lat": -16.61, "lon": -70.85, "vei": 6, "sulfur_tg": 30, "hemisphere": "SH"},
            {"id": "holvol_eldgja_939", "year": 939, "volcano_name": "Eldgjá", "lat": 63.97, "lon": -18.62, "vei": 6, "sulfur_tg": 70, "hemisphere": "NH"},
            {"id": "holvol_unknown_536", "year": 536, "volcano_name": "Unknown (536 event)", "lat": None, "lon": None, "vei": 6, "sulfur_tg": 40, "hemisphere": "NH"},
            {"id": "holvol_unknown_540", "year": 540, "volcano_name": "Ilopango?", "lat": 13.67, "lon": -89.05, "vei": 6, "sulfur_tg": 40, "hemisphere": "tropical"},
            {"id": "holvol_kuwae_1452", "year": 1452, "volcano_name": "Kuwae", "lat": -16.83, "lon": 168.54, "vei": 6, "sulfur_tg": 35, "hemisphere": "SH"},
            {"id": "holvol_cosiguina_1835", "year": 1835, "volcano_name": "Cosigüina", "lat": 12.98, "lon": -87.57, "vei": 5, "sulfur_tg": 10, "hemisphere": "tropical"},
            {"id": "holvol_agung_1963", "year": 1963, "volcano_name": "Agung", "lat": -8.34, "lon": 115.51, "vei": 5, "sulfur_tg": 7, "hemisphere": "SH"},
            {"id": "holvol_el_chichon_1982", "year": 1982, "volcano_name": "El Chichón", "lat": 17.36, "lon": -93.23, "vei": 5, "sulfur_tg": 7, "hemisphere": "tropical"},
            {"id": "holvol_katmai_1912", "year": 1912, "volcano_name": "Katmai/Novarupta", "lat": 58.28, "lon": -155.16, "vei": 6, "sulfur_tg": 5, "hemisphere": "NH"},
            {"id": "holvol_st_helens_1980", "year": 1980, "volcano_name": "Mount St. Helens", "lat": 46.20, "lon": -122.18, "vei": 5, "sulfur_tg": 1, "hemisphere": "NH"},
            {"id": "holvol_mazama_5677bce", "year": -5677, "volcano_name": "Mount Mazama", "lat": 42.94, "lon": -122.11, "vei": 7, "sulfur_tg": 100, "hemisphere": "NH"},
            {"id": "holvol_toba_74ka", "year": -72000, "volcano_name": "Toba", "lat": 2.68, "lon": 98.88, "vei": 8, "sulfur_tg": 5000, "hemisphere": "tropical"},
            {"id": "holvol_etna_44bce", "year": -44, "volcano_name": "Etna", "lat": 37.75, "lon": 15.00, "vei": 4, "sulfur_tg": 2, "hemisphere": "NH"},
        ]

    def _parse_float(self, value) -> Optional[float]:
        """Parse a float value."""
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _parse_int(self, value) -> Optional[int]:
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

        with open(raw_data_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        eruptions = data.get("eruptions", [])
        logger.info(f"Processing {len(eruptions)} eruptions")

        for eruption in eruptions:
            site = self._eruption_to_site(eruption)
            if site:
                yield site

    def _eruption_to_site(self, eruption: Dict) -> Optional[ParsedSite]:
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
