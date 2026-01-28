"""
Nomisma.org ingester via SPARQL.

Nomisma.org provides linked open data for numismatics,
connecting mints, rulers, denominations, and coin finds
across multiple databases worldwide.

Data source: http://nomisma.org/
License: Open (varies by dataset)
API Key: Not required
"""

import json
from pathlib import Path
from typing import Iterator, Optional, Dict, Any, List
from datetime import datetime
import time
import urllib.parse

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_json
from pipeline.utils.http import fetch_with_retry


class NomismaIngester(BaseIngester):
    """
    Ingester for Nomisma.org numismatic data via SPARQL.

    Queries the Nomisma SPARQL endpoint to extract:
    - Ancient mints with locations
    - Coin finds with coordinates
    - Hoard data
    - Ruler/mint relationships
    """

    source_id = "coins_nomisma"
    source_name = "Nomisma.org"

    # SPARQL endpoint
    SPARQL_URL = "http://nomisma.org/query"

    # Queries for different data types
    SPARQL_QUERIES = {
        "mints": """
PREFIX nmo: <http://nomisma.org/ontology#>
PREFIX geo: <http://www.w3.org/2003/01/geo/wgs84_pos#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT DISTINCT ?mint ?label ?lat ?lon ?definition ?broader ?startDate ?endDate
WHERE {
    ?mint a nmo:Mint ;
          skos:prefLabel ?label .
    FILTER(lang(?label) = "en" || lang(?label) = "")

    OPTIONAL {
        ?mint geo:location ?loc .
        ?loc geo:lat ?lat ;
             geo:long ?lon .
    }
    OPTIONAL { ?mint skos:definition ?definition . FILTER(lang(?definition) = "en" || lang(?definition) = "") }
    OPTIONAL { ?mint skos:broader ?broader }
    OPTIONAL { ?mint nmo:hasStartDate ?startDate }
    OPTIONAL { ?mint nmo:hasEndDate ?endDate }
}
ORDER BY ?label
LIMIT 10000
""",

        "hoards": """
PREFIX nmo: <http://nomisma.org/ontology#>
PREFIX geo: <http://www.w3.org/2003/01/geo/wgs84_pos#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT DISTINCT ?hoard ?label ?lat ?lon ?closingDate ?discoveryDate ?contents ?findspot
WHERE {
    ?hoard a nmo:Hoard ;
           skos:prefLabel ?label .
    FILTER(lang(?label) = "en" || lang(?label) = "")

    OPTIONAL {
        ?hoard nmo:hasFindspot ?findspot .
        ?findspot geo:lat ?lat ;
                  geo:long ?lon .
    }
    OPTIONAL { ?hoard nmo:hasClosingDate ?closingDate }
    OPTIONAL { ?hoard dcterms:date ?discoveryDate }
    OPTIONAL { ?hoard nmo:hasContents ?contents }
}
ORDER BY ?label
LIMIT 20000
""",

        "finds": """
PREFIX nmo: <http://nomisma.org/ontology#>
PREFIX geo: <http://www.w3.org/2003/01/geo/wgs84_pos#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT DISTINCT ?find ?type ?lat ?lon ?denomination ?material ?authority ?mint ?startDate ?endDate
WHERE {
    ?find nmo:hasFindspot ?findspot .
    ?findspot geo:lat ?lat ;
              geo:long ?lon .

    OPTIONAL { ?find a ?type . FILTER(?type != nmo:Hoard) }
    OPTIONAL { ?find nmo:hasDenomination ?denomination }
    OPTIONAL { ?find nmo:hasMaterial ?material }
    OPTIONAL { ?find nmo:hasAuthority ?authority }
    OPTIONAL { ?find nmo:hasMint ?mint }
    OPTIONAL { ?find nmo:hasStartDate ?startDate }
    OPTIONAL { ?find nmo:hasEndDate ?endDate }
}
LIMIT 50000
""",

        "rulers": """
PREFIX nmo: <http://nomisma.org/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX bio: <http://purl.org/vocab/bio/0.1/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>

SELECT DISTINCT ?ruler ?label ?definition ?birthDate ?deathDate ?reignStart ?reignEnd
WHERE {
    ?ruler a foaf:Person ;
           skos:prefLabel ?label .
    FILTER(lang(?label) = "en" || lang(?label) = "")

    OPTIONAL { ?ruler skos:definition ?definition . FILTER(lang(?definition) = "en") }
    OPTIONAL { ?ruler bio:birth ?birthDate }
    OPTIONAL { ?ruler bio:death ?deathDate }
    OPTIONAL { ?ruler nmo:hasStartDate ?reignStart }
    OPTIONAL { ?ruler nmo:hasEndDate ?reignEnd }
}
ORDER BY ?label
LIMIT 5000
"""
    }

    REQUEST_DELAY = 2.0  # SPARQL queries can be heavy

    def fetch(self) -> Path:
        """
        Fetch numismatic data from Nomisma.org SPARQL endpoint.

        Returns:
            Path to JSON file with numismatic data
        """
        dest_path = self.raw_data_dir / "coins_nomisma.json"

        logger.info("Fetching Nomisma.org data via SPARQL...")
        self.report_progress(0, len(self.SPARQL_QUERIES), "starting...")

        all_data = {
            "mints": [],
            "hoards": [],
            "finds": [],
            "rulers": [],
        }

        headers = {
            "Accept": "application/sparql-results+json",
            "User-Agent": "AncientNerds/1.0 (Research Platform)",
        }

        for i, (query_name, query) in enumerate(self.SPARQL_QUERIES.items()):
            logger.info(f"Running SPARQL query: {query_name}")
            self.report_progress(i, len(self.SPARQL_QUERIES), query_name)

            try:
                # URL encode the query
                params = {
                    "query": query,
                    "format": "json",
                }

                response = fetch_with_retry(
                    self.SPARQL_URL,
                    params=params,
                    headers=headers,
                    timeout=300,  # SPARQL queries can take a while
                )

                data = response.json()
                results = data.get("results", {}).get("bindings", [])

                # Parse results based on query type
                parsed = []
                for result in results:
                    if query_name == "mints":
                        parsed_item = self._parse_mint(result)
                    elif query_name == "hoards":
                        parsed_item = self._parse_hoard(result)
                    elif query_name == "finds":
                        parsed_item = self._parse_find(result)
                    elif query_name == "rulers":
                        parsed_item = self._parse_ruler(result)
                    else:
                        parsed_item = None

                    if parsed_item:
                        parsed.append(parsed_item)

                all_data[query_name] = parsed
                logger.info(f"  {query_name}: {len(parsed):,} records")

                time.sleep(self.REQUEST_DELAY)

            except Exception as e:
                logger.warning(f"Error running {query_name} query: {e}")

        # Count totals
        total = sum(len(v) for v in all_data.values())
        logger.info(f"Total records fetched: {total:,}")
        self.report_progress(len(self.SPARQL_QUERIES), len(self.SPARQL_QUERIES), f"{total:,} records")

        # Save to file
        output = {
            **all_data,
            "metadata": {
                "source": "Nomisma.org",
                "source_url": "http://nomisma.org/",
                "fetched_at": datetime.utcnow().isoformat(),
                "total_mints": len(all_data["mints"]),
                "total_hoards": len(all_data["hoards"]),
                "total_finds": len(all_data["finds"]),
                "total_rulers": len(all_data["rulers"]),
                "data_type": "numismatic_linked_data",
                "license": "Open (varies by dataset)",
            }
        }

        atomic_write_json(dest_path, output)

        logger.info(f"Saved {total:,} records to {dest_path}")
        return dest_path

    def _parse_mint(self, result: Dict) -> Optional[Dict]:
        """Parse a mint result from SPARQL."""
        uri = result.get("mint", {}).get("value", "")
        if not uri:
            return None

        mint_id = uri.split("/")[-1]

        lat = self._parse_coord(result.get("lat", {}).get("value"))
        lon = self._parse_coord(result.get("lon", {}).get("value"))

        return {
            "id": f"nomisma_mint_{mint_id}",
            "uri": uri,
            "name": result.get("label", {}).get("value", mint_id),
            "lat": lat,
            "lon": lon,
            "definition": result.get("definition", {}).get("value", ""),
            "broader": result.get("broader", {}).get("value", ""),
            "start_date": self._parse_date(result.get("startDate", {}).get("value")),
            "end_date": self._parse_date(result.get("endDate", {}).get("value")),
            "type": "mint",
        }

    def _parse_hoard(self, result: Dict) -> Optional[Dict]:
        """Parse a hoard result from SPARQL."""
        uri = result.get("hoard", {}).get("value", "")
        if not uri:
            return None

        hoard_id = uri.split("/")[-1]

        lat = self._parse_coord(result.get("lat", {}).get("value"))
        lon = self._parse_coord(result.get("lon", {}).get("value"))

        return {
            "id": f"nomisma_hoard_{hoard_id}",
            "uri": uri,
            "name": result.get("label", {}).get("value", hoard_id),
            "lat": lat,
            "lon": lon,
            "closing_date": self._parse_date(result.get("closingDate", {}).get("value")),
            "discovery_date": result.get("discoveryDate", {}).get("value", ""),
            "contents": result.get("contents", {}).get("value", ""),
            "findspot_uri": result.get("findspot", {}).get("value", ""),
            "type": "hoard",
        }

    def _parse_find(self, result: Dict) -> Optional[Dict]:
        """Parse a find result from SPARQL."""
        uri = result.get("find", {}).get("value", "")
        if not uri:
            return None

        find_id = uri.split("/")[-1]

        lat = self._parse_coord(result.get("lat", {}).get("value"))
        lon = self._parse_coord(result.get("lon", {}).get("value"))

        if lat is None or lon is None:
            return None

        return {
            "id": f"nomisma_find_{find_id}",
            "uri": uri,
            "lat": lat,
            "lon": lon,
            "type_uri": result.get("type", {}).get("value", ""),
            "denomination_uri": result.get("denomination", {}).get("value", ""),
            "material_uri": result.get("material", {}).get("value", ""),
            "authority_uri": result.get("authority", {}).get("value", ""),
            "mint_uri": result.get("mint", {}).get("value", ""),
            "start_date": self._parse_date(result.get("startDate", {}).get("value")),
            "end_date": self._parse_date(result.get("endDate", {}).get("value")),
            "type": "find",
        }

    def _parse_ruler(self, result: Dict) -> Optional[Dict]:
        """Parse a ruler result from SPARQL."""
        uri = result.get("ruler", {}).get("value", "")
        if not uri:
            return None

        ruler_id = uri.split("/")[-1]

        return {
            "id": f"nomisma_ruler_{ruler_id}",
            "uri": uri,
            "name": result.get("label", {}).get("value", ruler_id),
            "definition": result.get("definition", {}).get("value", ""),
            "birth_date": self._parse_date(result.get("birthDate", {}).get("value")),
            "death_date": self._parse_date(result.get("deathDate", {}).get("value")),
            "reign_start": self._parse_date(result.get("reignStart", {}).get("value")),
            "reign_end": self._parse_date(result.get("reignEnd", {}).get("value")),
            "type": "ruler",
        }

    def _parse_coord(self, value: Optional[str]) -> Optional[float]:
        """Parse a coordinate value."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _parse_date(self, value: Optional[str]) -> Optional[int]:
        """Parse a date string to year integer."""
        if not value:
            return None

        # Try parsing ISO date
        try:
            # Handle negative dates for BCE
            if value.startswith("-"):
                # Format: -0044 for 44 BCE
                return -int(value[1:5])
            elif len(value) >= 4:
                return int(value[:4])
        except (ValueError, IndexError):
            pass

        return None

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """Parse Nomisma data into ParsedSite objects."""
        logger.info(f"Parsing Nomisma data from {raw_data_path}")

        with open(raw_data_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Parse mints as sites
        mints = data.get("mints", [])
        logger.info(f"Processing {len(mints)} mints")
        for mint in mints:
            site = self._mint_to_site(mint)
            if site:
                yield site

        # Parse hoards as sites
        hoards = data.get("hoards", [])
        logger.info(f"Processing {len(hoards)} hoards")
        for hoard in hoards:
            site = self._hoard_to_site(hoard)
            if site:
                yield site

        # Parse finds as sites
        finds = data.get("finds", [])
        logger.info(f"Processing {len(finds)} finds")
        for find in finds:
            site = self._find_to_site(find)
            if site:
                yield site

    def _mint_to_site(self, mint: Dict) -> Optional[ParsedSite]:
        """Convert a mint to a ParsedSite."""
        lat = mint.get("lat")
        lon = mint.get("lon")

        if lat is None or lon is None:
            return None

        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None

        name = mint.get("name", "Unknown Mint")

        desc_parts = []
        if mint.get("definition"):
            desc_parts.append(mint["definition"][:300])

        return ParsedSite(
            source_id=mint["id"],
            name=name,
            lat=lat,
            lon=lon,
            alternative_names=[],
            description="; ".join(desc_parts) if desc_parts else None,
            site_type="mint",
            period_start=mint.get("start_date"),
            period_end=mint.get("end_date"),
            period_name=None,
            precision_meters=100,
            precision_reason="nomisma",
            source_url=mint.get("uri", "http://nomisma.org/"),
            raw_data=mint,
        )

    def _hoard_to_site(self, hoard: Dict) -> Optional[ParsedSite]:
        """Convert a hoard to a ParsedSite."""
        lat = hoard.get("lat")
        lon = hoard.get("lon")

        if lat is None or lon is None:
            return None

        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None

        name = hoard.get("name", "Unknown Hoard")

        desc_parts = []
        if hoard.get("contents"):
            desc_parts.append(f"Contents: {hoard['contents'][:200]}")
        if hoard.get("closing_date"):
            desc_parts.append(f"Closing date: {hoard['closing_date']}")

        return ParsedSite(
            source_id=hoard["id"],
            name=name,
            lat=lat,
            lon=lon,
            alternative_names=[],
            description="; ".join(desc_parts) if desc_parts else None,
            site_type="coin_hoard",
            period_start=None,
            period_end=hoard.get("closing_date"),
            period_name=None,
            precision_meters=500,
            precision_reason="hoard_location",
            source_url=hoard.get("uri", "http://nomisma.org/"),
            raw_data=hoard,
        )

    def _find_to_site(self, find: Dict) -> Optional[ParsedSite]:
        """Convert a find to a ParsedSite."""
        lat = find.get("lat")
        lon = find.get("lon")

        if lat is None or lon is None:
            return None

        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None

        # Extract labels from URIs
        denom = find.get("denomination_uri", "").split("/")[-1] or "coin"
        material = find.get("material_uri", "").split("/")[-1] or ""
        authority = find.get("authority_uri", "").split("/")[-1] or ""

        name_parts = []
        if authority:
            name_parts.append(authority.replace("_", " ").title())
        if denom:
            name_parts.append(denom.replace("_", " "))
        if material:
            name_parts.append(f"({material})")

        name = " ".join(name_parts) if name_parts else f"Coin find {find['id']}"

        return ParsedSite(
            source_id=find["id"],
            name=name,
            lat=lat,
            lon=lon,
            alternative_names=[],
            description=None,
            site_type="coin_find",
            period_start=find.get("start_date"),
            period_end=find.get("end_date"),
            period_name=None,
            precision_meters=100,
            precision_reason="nomisma",
            source_url=find.get("uri", "http://nomisma.org/"),
            raw_data=find,
        )


def ingest_nomisma(session=None, skip_fetch: bool = False) -> dict:
    """Run Nomisma ingestion."""
    with NomismaIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
