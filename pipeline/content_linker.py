"""
Content Linker for Ancient Nerds Map.

Pre-computes relationships between sites and related content:
- Text references (ToposText)
- Historical maps (David Rumsey)
- Inscriptions (EDH)
- 3D models (Sketchfab)
- Artworks (Europeana)

Usage:
    python -m pipeline.content_linker
    python -m pipeline.content_linker --type texts
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Iterator
from datetime import datetime

from loguru import logger
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from pipeline.database import get_session, SiteContentLink
from pipeline.utils import haversine_distance, normalize_name


# Content source configurations
CONTENT_SOURCES = {
    "topostext": {
        "type": "text",
        "description": "Ancient Greek and Latin text references",
        "file": "data/raw/topostext/topostext.json",
        "data_key": "places",
    },
    "david_rumsey": {
        "type": "map",
        "description": "Historical maps",
        "file": "data/raw/david_rumsey/david_rumsey.json",
        "data_key": "maps",
    },
    "inscriptions_edh": {
        "type": "inscription",
        "description": "Latin inscriptions",
        "file": "data/raw/inscriptions_edh/inscriptions_edh.json",
        "data_key": "inscriptions",
    },
    "models_sketchfab": {
        "type": "model",
        "description": "3D archaeological models",
        "file": "data/raw/models_sketchfab/models_sketchfab.json",
        "data_key": "models",
    },
    "europeana": {
        "type": "artwork",
        "description": "European cultural heritage items",
        "file": "data/raw/europeana/europeana.json",
        "data_key": "items",
    },
}

# Link distance thresholds (in km)
DISTANCE_THRESHOLDS = {
    "text": 10,        # Text references within 10km
    "inscription": 5,  # Inscriptions within 5km (more precise)
    "map": 100,        # Maps can cover large areas
    "model": 10,       # 3D models within 10km
    "artwork": 20,     # Artworks within 20km
}


def normalize_for_matching(name: str) -> str:
    """Normalize name for fuzzy matching with prefix removal."""
    import re

    # Use shared normalize_name utility
    normalized = normalize_name(name)

    if not normalized:
        return ""

    # Remove common prefixes/suffixes specific to archaeological sites
    prefixes = ["tel ", "tell ", "temple of ", "sanctuary of ", "ancient ", "old "]
    for prefix in prefixes:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]

    return normalized.strip()


def name_similarity(name1: str, name2: str) -> float:
    """Calculate similarity between two names (0-1)."""
    n1 = normalize_for_matching(name1)
    n2 = normalize_for_matching(name2)

    if not n1 or not n2:
        return 0.0

    # Exact match
    if n1 == n2:
        return 1.0

    # One contains the other
    if n1 in n2 or n2 in n1:
        shorter = min(len(n1), len(n2))
        longer = max(len(n1), len(n2))
        return shorter / longer

    # Simple character-based similarity (Jaccard on character trigrams)
    def trigrams(s):
        return set(s[i:i+3] for i in range(len(s)-2)) if len(s) >= 3 else {s}

    t1, t2 = trigrams(n1), trigrams(n2)
    if not t1 or not t2:
        return 0.0

    intersection = len(t1 & t2)
    union = len(t1 | t2)

    return intersection / union if union > 0 else 0.0


class ContentLinker:
    """Links sites to related content from various sources."""

    def __init__(self):
        self.stats = {}

    def link_all(self, content_type: Optional[str] = None):
        """Link all content types or a specific type."""
        sources_to_link = []

        for source_id, config in CONTENT_SOURCES.items():
            if content_type is None or config["type"] == content_type:
                sources_to_link.append((source_id, config))

        if not sources_to_link:
            logger.warning(f"No content sources found for type: {content_type}")
            return

        with get_session() as session:
            for source_id, config in sources_to_link:
                logger.info(f"\n{'='*60}")
                logger.info(f"Linking {config['description']} ({source_id})")
                logger.info(f"{'='*60}")

                try:
                    count = self._link_source(session, source_id, config)
                    self.stats[source_id] = {"success": True, "count": count}
                    logger.info(f"Created {count:,} links for {source_id}")
                except Exception as e:
                    logger.error(f"Failed to link {source_id}: {e}")
                    self.stats[source_id] = {"success": False, "error": str(e)}
                    session.rollback()

        self._print_summary()

    def _link_source(self, session, source_id: str, config: Dict) -> int:
        """Link a single content source to sites."""
        file_path = Path(config["file"])
        if not file_path.exists():
            logger.warning(f"Content file not found: {file_path}")
            return 0

        # Load content data
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        content_items = data.get(config["data_key"], [])
        if not content_items:
            # Try other common keys
            for key in ["places", "sites", "records", "items", "results", "features"]:
                if key in data:
                    content_items = data[key]
                    break

        if not content_items and isinstance(data, list):
            content_items = data

        logger.info(f"Loaded {len(content_items):,} content items")

        # Delete existing links for this source
        session.execute(
            text("DELETE FROM site_content_links WHERE content_source = :source"),
            {"source": source_id}
        )

        # Get linker function based on content type
        content_type = config["type"]
        linker = getattr(self, f"_link_{content_type}", self._link_generic)

        # Process and link
        links_created = 0
        batch = []
        batch_size = 1000

        for item in content_items:
            for link in linker(session, source_id, item, content_type):
                batch.append(link)

                if len(batch) >= batch_size:
                    self._insert_links(session, batch)
                    links_created += len(batch)
                    batch = []

                    if links_created % 10000 == 0:
                        logger.info(f"  Created {links_created:,} links...")

        # Insert remaining
        if batch:
            self._insert_links(session, batch)
            links_created += len(batch)

        session.commit()
        return links_created

    def _insert_links(self, session, links: List[Dict]):
        """Bulk insert links."""
        if not links:
            return

        stmt = insert(SiteContentLink).values(links)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["site_id", "content_source", "content_id"]
        )
        session.execute(stmt)

    def _link_text(self, session, source_id: str, item: Dict, content_type: str) -> Iterator[Dict]:
        """Link ToposText places to sites."""
        # Get item location
        lat = item.get("lat")
        lon = item.get("lon")

        if lat is None or lon is None:
            geom = item.get("geometry", {})
            coords = geom.get("coordinates", [])
            if coords and len(coords) >= 2:
                lon, lat = coords[0], coords[1]

        if lat is None or lon is None:
            return

        try:
            lat = float(lat)
            lon = float(lon)
        except (ValueError, TypeError):
            return

        item_name = item.get("name", "")
        content_id = item.get("ToposText", "").split("/")[-1] if item.get("ToposText") else str(item.get("id", ""))

        if not content_id:
            return

        # Find nearby sites
        threshold = DISTANCE_THRESHOLDS.get(content_type, 10)

        # Use PostGIS for spatial query (approximate bounding box first)
        lat_delta = threshold / 111  # ~111km per degree latitude
        lon_delta = threshold / (111 * math.cos(math.radians(lat)))

        result = session.execute(
            text("""
                SELECT id, name, lat, lon FROM unified_sites
                WHERE lat BETWEEN :min_lat AND :max_lat
                AND lon BETWEEN :min_lon AND :max_lon
            """),
            {
                "min_lat": lat - lat_delta,
                "max_lat": lat + lat_delta,
                "min_lon": lon - lon_delta,
                "max_lon": lon + lon_delta,
            }
        )

        for row in result:
            site_id, site_name, site_lat, site_lon = row

            # Calculate precise distance
            distance = haversine_distance(lat, lon, site_lat, site_lon)
            if distance > threshold:
                continue

            # Calculate relevance score
            name_sim = name_similarity(item_name, site_name)
            distance_score = 1 - (distance / threshold)
            relevance = (name_sim * 0.6) + (distance_score * 0.4)

            # Only link if reasonable relevance
            if relevance < 0.2 and distance > threshold / 2:
                continue

            yield {
                "site_id": site_id,
                "content_type": content_type,
                "content_source": source_id,
                "content_id": content_id,
                "title": item_name[:500],
                "content_url": item.get("ToposText", f"https://topostext.org/place/{content_id}"),
                "relevance_score": round(relevance, 3),
                "metadata": {
                    "references": item.get("references", ""),
                    "description": item.get("description", "")[:500],
                    "greek": item.get("Greek", ""),
                    "pleiades": item.get("Pleiades", ""),
                    "wikidata": item.get("Wikidata", ""),
                },
            }

    def _link_inscription(self, session, source_id: str, item: Dict, content_type: str) -> Iterator[Dict]:
        """Link EDH inscriptions to sites."""
        lat = item.get("lat")
        lon = item.get("lon")

        if lat is None or lon is None:
            return

        try:
            lat = float(lat)
            lon = float(lon)
        except (ValueError, TypeError):
            return

        content_id = item.get("edh_id", item.get("id", ""))
        if not content_id:
            return

        threshold = DISTANCE_THRESHOLDS.get(content_type, 5)
        lat_delta = threshold / 111
        lon_delta = threshold / (111 * max(0.1, math.cos(math.radians(lat))))

        result = session.execute(
            text("""
                SELECT id, name, lat, lon FROM unified_sites
                WHERE lat BETWEEN :min_lat AND :max_lat
                AND lon BETWEEN :min_lon AND :max_lon
            """),
            {
                "min_lat": lat - lat_delta,
                "max_lat": lat + lat_delta,
                "min_lon": lon - lon_delta,
                "max_lon": lon + lon_delta,
            }
        )

        item_name = item.get("ancient_place") or item.get("modern_place") or ""

        for row in result:
            site_id, site_name, site_lat, site_lon = row

            distance = haversine_distance(lat, lon, site_lat, site_lon)
            if distance > threshold:
                continue

            name_sim = name_similarity(item_name, site_name)
            distance_score = 1 - (distance / threshold)
            relevance = (name_sim * 0.4) + (distance_score * 0.6)

            if relevance < 0.1:
                continue

            yield {
                "site_id": site_id,
                "content_type": content_type,
                "content_source": source_id,
                "content_id": content_id,
                "title": f"Inscription {content_id}"[:500],
                "content_url": item.get("source_url", f"https://edh.ub.uni-heidelberg.de/edh/inschrift/{content_id}"),
                "relevance_score": round(relevance, 3),
                "metadata": {
                    "inscription_type": item.get("inscription_type", ""),
                    "material": item.get("material", ""),
                    "object_type": item.get("object_type", ""),
                    "date_start": item.get("date_start"),
                    "date_end": item.get("date_end"),
                    "find_spot": item.get("find_spot", ""),
                },
            }

    def _link_map(self, session, source_id: str, item: Dict, content_type: str) -> Iterator[Dict]:
        """Link David Rumsey historical maps to sites.

        Maps are linked based on:
        1. Bounding box overlap (if georeferenced)
        2. Title matching with site names
        """
        content_id = item.get("id", "")
        if not content_id:
            return

        title = item.get("title", "")
        bbox_str = item.get("bbox", "")

        # Try to parse bbox if available
        if bbox_str and item.get("georeferenced"):
            try:
                # bbox format: "minLon,minLat,maxLon,maxLat"
                parts = [float(x) for x in bbox_str.split(",")]
                if len(parts) == 4:
                    min_lon, min_lat, max_lon, max_lat = parts

                    # Find sites within map bounds
                    result = session.execute(
                        text("""
                            SELECT id, name FROM unified_sites
                            WHERE lat BETWEEN :min_lat AND :max_lat
                            AND lon BETWEEN :min_lon AND :max_lon
                            LIMIT 1000
                        """),
                        {
                            "min_lat": min_lat,
                            "max_lat": max_lat,
                            "min_lon": min_lon,
                            "max_lon": max_lon,
                        }
                    )

                    for row in result:
                        site_id, site_name = row

                        # Calculate relevance based on name match
                        name_sim = name_similarity(title, site_name)
                        relevance = max(0.3, name_sim)  # At least 0.3 for bbox match

                        yield {
                            "site_id": site_id,
                            "content_type": content_type,
                            "content_source": source_id,
                            "content_id": content_id,
                            "title": title[:500],
                            "thumbnail_url": item.get("thumbnail", ""),
                            "content_url": item.get("iiif_manifest", ""),
                            "relevance_score": round(relevance, 3),
                            "metadata": {
                                "date": item.get("date", ""),
                                "author": item.get("author", ""),
                                "publisher": item.get("publisher", ""),
                                "full_image": item.get("full_image", ""),
                            },
                        }
                    return
            except (ValueError, TypeError):
                pass

        # No bbox - try title matching with ancient site names
        # Extract potential place names from title
        title_words = set(normalize_for_matching(title).split())

        if not title_words:
            return

        # Search for sites with matching names
        result = session.execute(
            text("""
                SELECT id, name FROM unified_sites
                WHERE name_normalized LIKE ANY(:patterns)
                LIMIT 100
            """),
            {"patterns": [f"%{word}%" for word in title_words if len(word) > 3]}
        )

        for row in result:
            site_id, site_name = row
            name_sim = name_similarity(title, site_name)

            if name_sim < 0.3:
                continue

            yield {
                "site_id": site_id,
                "content_type": content_type,
                "content_source": source_id,
                "content_id": content_id,
                "title": title[:500],
                "thumbnail_url": item.get("thumbnail", ""),
                "content_url": item.get("iiif_manifest", ""),
                "relevance_score": round(name_sim, 3),
                "metadata": {
                    "date": item.get("date", ""),
                    "author": item.get("author", ""),
                    "publisher": item.get("publisher", ""),
                },
            }

    def _link_model(self, session, source_id: str, item: Dict, content_type: str) -> Iterator[Dict]:
        """Link Sketchfab 3D models to sites."""
        lat = item.get("lat")
        lon = item.get("lon")

        content_id = str(item.get("uid", item.get("id", "")))
        if not content_id:
            return

        title = item.get("name", item.get("title", ""))

        # If model has coordinates, use proximity matching
        if lat is not None and lon is not None:
            try:
                lat = float(lat)
                lon = float(lon)

                threshold = DISTANCE_THRESHOLDS.get(content_type, 10)
                lat_delta = threshold / 111
                lon_delta = threshold / (111 * max(0.1, math.cos(math.radians(lat))))

                result = session.execute(
                    text("""
                        SELECT id, name, lat, lon FROM unified_sites
                        WHERE lat BETWEEN :min_lat AND :max_lat
                        AND lon BETWEEN :min_lon AND :max_lon
                    """),
                    {
                        "min_lat": lat - lat_delta,
                        "max_lat": lat + lat_delta,
                        "min_lon": lon - lon_delta,
                        "max_lon": lon + lon_delta,
                    }
                )

                for row in result:
                    site_id, site_name, site_lat, site_lon = row

                    distance = haversine_distance(lat, lon, site_lat, site_lon)
                    if distance > threshold:
                        continue

                    name_sim = name_similarity(title, site_name)
                    distance_score = 1 - (distance / threshold)
                    relevance = (name_sim * 0.5) + (distance_score * 0.5)

                    if relevance < 0.2:
                        continue

                    yield {
                        "site_id": site_id,
                        "content_type": content_type,
                        "content_source": source_id,
                        "content_id": content_id,
                        "title": title[:500],
                        "thumbnail_url": item.get("thumbnail", item.get("thumbnails", {}).get("images", [{}])[0].get("url", "")),
                        "content_url": item.get("viewerUrl", f"https://sketchfab.com/3d-models/{content_id}"),
                        "relevance_score": round(relevance, 3),
                        "metadata": {
                            "author": item.get("user", {}).get("displayName", ""),
                            "license": item.get("license", {}).get("label", ""),
                            "vertex_count": item.get("vertexCount"),
                            "face_count": item.get("faceCount"),
                        },
                    }
                return
            except (ValueError, TypeError):
                pass

        # No coordinates - try name matching
        if not title:
            return

        title_normalized = normalize_for_matching(title)

        result = session.execute(
            text("""
                SELECT id, name FROM unified_sites
                WHERE name_normalized LIKE :pattern
                LIMIT 50
            """),
            {"pattern": f"%{title_normalized[:20]}%"}
        )

        for row in result:
            site_id, site_name = row
            name_sim = name_similarity(title, site_name)

            if name_sim < 0.4:
                continue

            yield {
                "site_id": site_id,
                "content_type": content_type,
                "content_source": source_id,
                "content_id": content_id,
                "title": title[:500],
                "thumbnail_url": item.get("thumbnail", ""),
                "content_url": item.get("viewerUrl", f"https://sketchfab.com/3d-models/{content_id}"),
                "relevance_score": round(name_sim, 3),
                "metadata": {
                    "author": item.get("user", {}).get("displayName", ""),
                },
            }

    def _link_artwork(self, session, source_id: str, item: Dict, content_type: str) -> Iterator[Dict]:
        """Link Europeana artworks to sites."""
        lat = item.get("lat")
        lon = item.get("lon")

        content_id = str(item.get("id", item.get("europeanaId", "")))
        if not content_id:
            return

        title = item.get("title", item.get("dcTitleLangAware", {}).get("en", [""])[0] if isinstance(item.get("dcTitleLangAware"), dict) else "")
        if isinstance(title, list):
            title = title[0] if title else ""

        # Use proximity if coordinates available
        if lat is not None and lon is not None:
            try:
                lat = float(lat)
                lon = float(lon)

                threshold = DISTANCE_THRESHOLDS.get(content_type, 20)
                lat_delta = threshold / 111
                lon_delta = threshold / (111 * max(0.1, math.cos(math.radians(lat))))

                result = session.execute(
                    text("""
                        SELECT id, name, lat, lon FROM unified_sites
                        WHERE lat BETWEEN :min_lat AND :max_lat
                        AND lon BETWEEN :min_lon AND :max_lon
                    """),
                    {
                        "min_lat": lat - lat_delta,
                        "max_lat": lat + lat_delta,
                        "min_lon": lon - lon_delta,
                        "max_lon": lon + lon_delta,
                    }
                )

                for row in result:
                    site_id, site_name, site_lat, site_lon = row

                    distance = haversine_distance(lat, lon, site_lat, site_lon)
                    if distance > threshold:
                        continue

                    name_sim = name_similarity(title, site_name)
                    distance_score = 1 - (distance / threshold)
                    relevance = (name_sim * 0.4) + (distance_score * 0.6)

                    if relevance < 0.15:
                        continue

                    yield {
                        "site_id": site_id,
                        "content_type": content_type,
                        "content_source": source_id,
                        "content_id": content_id,
                        "title": title[:500] if title else f"Artwork {content_id}",
                        "thumbnail_url": item.get("edmPreview", [""])[0] if isinstance(item.get("edmPreview"), list) else item.get("thumbnail", ""),
                        "content_url": item.get("guid", f"https://www.europeana.eu/item/{content_id}"),
                        "relevance_score": round(relevance, 3),
                        "metadata": {
                            "provider": item.get("dataProvider", [""])[0] if isinstance(item.get("dataProvider"), list) else "",
                            "country": item.get("country", [""])[0] if isinstance(item.get("country"), list) else "",
                            "type": item.get("type", ""),
                            "year": item.get("year", [""])[0] if isinstance(item.get("year"), list) else "",
                        },
                    }
                return
            except (ValueError, TypeError):
                pass

        # No coordinates - minimal linking by name
        if not title:
            return

        title_normalized = normalize_for_matching(title)
        if len(title_normalized) < 4:
            return

        result = session.execute(
            text("""
                SELECT id, name FROM unified_sites
                WHERE name_normalized LIKE :pattern
                LIMIT 20
            """),
            {"pattern": f"%{title_normalized[:15]}%"}
        )

        for row in result:
            site_id, site_name = row
            name_sim = name_similarity(title, site_name)

            if name_sim < 0.5:
                continue

            yield {
                "site_id": site_id,
                "content_type": content_type,
                "content_source": source_id,
                "content_id": content_id,
                "title": title[:500],
                "thumbnail_url": item.get("edmPreview", [""])[0] if isinstance(item.get("edmPreview"), list) else "",
                "content_url": item.get("guid", f"https://www.europeana.eu/item/{content_id}"),
                "relevance_score": round(name_sim, 3),
                "metadata": {},
            }

    def _link_generic(self, session, source_id: str, item: Dict, content_type: str) -> Iterator[Dict]:
        """Generic linker for unknown content types."""
        lat = item.get("lat")
        lon = item.get("lon")

        if lat is None or lon is None:
            return

        try:
            lat = float(lat)
            lon = float(lon)
        except (ValueError, TypeError):
            return

        content_id = str(item.get("id", ""))
        if not content_id:
            return

        threshold = DISTANCE_THRESHOLDS.get(content_type, 10)
        lat_delta = threshold / 111
        lon_delta = threshold / (111 * max(0.1, math.cos(math.radians(lat))))

        result = session.execute(
            text("""
                SELECT id, name, lat, lon FROM unified_sites
                WHERE lat BETWEEN :min_lat AND :max_lat
                AND lon BETWEEN :min_lon AND :max_lon
            """),
            {
                "min_lat": lat - lat_delta,
                "max_lat": lat + lat_delta,
                "min_lon": lon - lon_delta,
                "max_lon": lon + lon_delta,
            }
        )

        for row in result:
            site_id, site_name, site_lat, site_lon = row

            distance = haversine_distance(lat, lon, site_lat, site_lon)
            if distance > threshold:
                continue

            distance_score = 1 - (distance / threshold)

            yield {
                "site_id": site_id,
                "content_type": content_type,
                "content_source": source_id,
                "content_id": content_id,
                "title": item.get("name", item.get("title", ""))[:500],
                "content_url": item.get("url", item.get("source_url", "")),
                "relevance_score": round(distance_score, 3),
                "metadata": {},
            }

    def _print_summary(self):
        """Print linking summary."""
        logger.info("\n" + "=" * 60)
        logger.info("CONTENT LINKING SUMMARY")
        logger.info("=" * 60)

        total_links = 0
        for source_id, stat in sorted(self.stats.items()):
            if stat.get("success"):
                logger.info(f"  ✓ {source_id}: {stat['count']:,} links")
                total_links += stat["count"]
            else:
                logger.error(f"  ✗ {source_id}: {stat.get('error', 'Unknown error')}")

        logger.info("-" * 60)
        logger.info(f"Total: {total_links:,} content links created")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Link content to sites")
    parser.add_argument("--type", "-t", help="Link only specific content type (text, map, inscription, model, artwork)")
    parser.add_argument("--status", action="store_true", help="Show linking status")
    args = parser.parse_args()

    if args.status:
        with get_session() as session:
            result = session.execute(text("""
                SELECT content_type, content_source, COUNT(*) as count
                FROM site_content_links
                GROUP BY content_type, content_source
                ORDER BY content_type, count DESC
            """))

            print("\nCurrent content links:")
            print("-" * 50)
            current_type = None
            total = 0
            for row in result:
                if row.content_type != current_type:
                    current_type = row.content_type
                    print(f"\n{current_type.upper()}:")
                print(f"  {row.content_source}: {row.count:,}")
                total += row.count
            print("-" * 50)
            print(f"Total: {total:,}")
        return

    linker = ContentLinker()
    linker.link_all(content_type=args.type)


if __name__ == "__main__":
    main()
