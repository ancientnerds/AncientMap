"""
NCEI Tsunami Observations (Runups) database ingester.

NCEI maintains a database of 28,000+ tsunami runup/observation points.
These are locations where tsunamis were observed, distinct from source locations.

Data source: https://www.ncei.noaa.gov/maps/hazards/
API endpoint: https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/tsunamis/runups
License: Public Domain (US Government)
API Key: Not required
"""

import json
from pathlib import Path
from typing import Iterator, Optional, Dict, Any, List
from datetime import datetime

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_json
from pipeline.utils.http import fetch_with_retry


class NCEITsunamiObservationsIngester(BaseIngester):
    """
    Ingester for NCEI Tsunami Runups/Observations database.

    Downloads tsunami observation data including water heights,
    arrival times, and distances from source.
    """

    source_id = "ncei_tsunami_obs"
    source_name = "NCEI Tsunami Observations"

    # NCEI Hazards API endpoint
    API_URL = "https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/tsunamis/runups"

    def fetch(self) -> Path:
        """
        Fetch NCEI tsunami observation data.

        Returns:
            Path to JSON file with observation data
        """
        dest_path = self.raw_data_dir / "ncei_tsunami_observations.json"

        logger.info("Fetching NCEI Tsunami Observations data...")
        self.report_progress(0, None, "starting...")

        all_observations = []

        headers = {
            "Accept": "application/json",
            "User-Agent": "AncientNerds/1.0 (Research Platform; archaeological research)",
        }

        try:
            # Fetch all observations
            logger.info(f"Querying: {self.API_URL}")
            response = fetch_with_retry(
                self.API_URL,
                headers=headers,
                timeout=180,  # Longer timeout for large dataset
            )

            if response.status_code == 200:
                data = response.json()

                # API returns {"items": [...]} or direct array
                if isinstance(data, dict):
                    observations = data.get("items", data.get("runups", data.get("observations", [])))
                else:
                    observations = data

                logger.info(f"Received {len(observations)} observations from API")

                for obs in observations:
                    parsed = self._parse_observation(obs)
                    if parsed:
                        all_observations.append(parsed)

            else:
                logger.warning(f"API returned status {response.status_code}")

        except Exception as e:
            logger.error(f"Failed to fetch NCEI tsunami observations: {e}")

        logger.info(f"Total observations: {len(all_observations):,}")
        self.report_progress(len(all_observations), len(all_observations), f"{len(all_observations):,} observations")

        # Save to file
        output = {
            "observations": all_observations,
            "metadata": {
                "source": "NCEI Tsunami Runups Database",
                "source_url": "https://www.ncei.noaa.gov/maps/hazards/",
                "api_url": self.API_URL,
                "fetched_at": datetime.utcnow().isoformat(),
                "total_observations": len(all_observations),
                "data_type": "tsunami_observations",
                "license": "Public Domain",
                "attribution": "NOAA National Centers for Environmental Information",
            }
        }

        atomic_write_json(dest_path, output)

        logger.info(f"Saved {len(all_observations):,} observations to {dest_path}")
        return dest_path

    def _parse_observation(self, obs: Dict) -> Optional[Dict]:
        """Parse a single tsunami observation record from the API."""
        # Extract coordinates (observation location)
        lat = self._parse_float(obs.get("latitude"))
        lon = self._parse_float(obs.get("longitude"))

        if lat is None or lon is None:
            return None

        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None

        # Extract date from associated event
        year = self._parse_int(obs.get("year"))
        month = self._parse_int(obs.get("month"))
        day = self._parse_int(obs.get("day"))

        # Generate unique ID
        obs_id = obs.get("id", obs.get("runupId"))
        if not obs_id:
            obs_id = f"ncei_obs_{year}_{lat}_{lon}"

        # Extract location info
        location_name = obs.get("locationName", "")
        country = obs.get("country", "")
        region = obs.get("regionCode", "")

        # Wave measurements
        water_height = self._parse_float(obs.get("waterHeight", obs.get("runupHt")))
        horizontal_inundation = self._parse_float(obs.get("horizontalInundation"))
        arrival_time = obs.get("arrivalTime")

        # Distance from source
        distance_from_source = self._parse_float(obs.get("distanceFromSource"))

        # Impact data
        deaths = self._parse_int(obs.get("deaths", obs.get("deathsTotal")))
        injuries = self._parse_int(obs.get("injuries"))
        damage_millions = self._parse_float(obs.get("damageMillionsDollars"))

        # Type flags
        doubtful = obs.get("doubtful", False)

        # Link to parent tsunami event
        tsunami_event_id = obs.get("tsunamiEventId")

        return {
            "id": str(obs_id),
            "year": year,
            "month": month,
            "day": day,
            "lat": lat,
            "lon": lon,
            "location_name": location_name,
            "country": country,
            "region": region,
            "water_height_m": water_height,
            "horizontal_inundation_m": horizontal_inundation,
            "arrival_time": arrival_time,
            "distance_from_source_km": distance_from_source,
            "deaths": deaths,
            "injuries": injuries,
            "damage_millions_usd": damage_millions,
            "doubtful": doubtful,
            "tsunami_event_id": tsunami_event_id,
        }

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
        """Parse NCEI tsunami observation data into ParsedSite objects."""
        logger.info(f"Parsing NCEI tsunami observation data from {raw_data_path}")

        with open(raw_data_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        observations = data.get("observations", [])
        logger.info(f"Processing {len(observations)} observations")

        for obs in observations:
            site = self._observation_to_site(obs)
            if site:
                yield site

    def _observation_to_site(self, obs: Dict) -> Optional[ParsedSite]:
        """Convert an observation record to a ParsedSite."""
        lat = obs.get("lat")
        lon = obs.get("lon")

        if lat is None or lon is None:
            return None

        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None

        # Build name
        year = obs.get("year")
        location = obs.get("location_name", "")
        country = obs.get("country", "")
        water_height = obs.get("water_height_m")

        name_parts = []
        if location:
            name_parts.append(location)
        elif country:
            name_parts.append(country)
        else:
            name_parts.append("Tsunami observation")

        if water_height:
            name_parts.append(f"({water_height:.1f}m)")

        if year:
            if year < 0:
                name_parts.append(f"({abs(year)} BCE)")
            else:
                name_parts.append(f"({year})")

        name = " ".join(name_parts)

        # Build description
        desc_parts = []
        if water_height:
            desc_parts.append(f"Wave height: {water_height:.1f}m")
        if obs.get("horizontal_inundation_m"):
            desc_parts.append(f"Inundation: {obs['horizontal_inundation_m']:.0f}m inland")
        if obs.get("distance_from_source_km"):
            desc_parts.append(f"Distance from source: {obs['distance_from_source_km']:.0f}km")
        if obs.get("arrival_time"):
            desc_parts.append(f"Arrival time: {obs['arrival_time']}")
        if obs.get("deaths"):
            desc_parts.append(f"Deaths: {obs['deaths']:,}")
        if obs.get("injuries"):
            desc_parts.append(f"Injuries: {obs['injuries']:,}")
        if obs.get("doubtful"):
            desc_parts.append("(Doubtful observation)")

        description = "; ".join(desc_parts) if desc_parts else None

        return ParsedSite(
            source_id=obs["id"],
            name=name,
            lat=lat,
            lon=lon,
            alternative_names=[],
            description=description,
            site_type="tsunami_observation",
            period_start=year,
            period_end=year,
            period_name=None,
            precision_meters=1000,  # Observation points are more precise
            precision_reason="coastal_observation",
            source_url=f"https://www.ngdc.noaa.gov/hazel/view/hazards/tsunami/runup-more-info/{obs['id']}",
            raw_data=obs,
        )


def ingest_ncei_tsunami_observations(session=None, skip_fetch: bool = False) -> dict:
    """Run NCEI Tsunami Observations ingestion."""
    with NCEITsunamiObservationsIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
