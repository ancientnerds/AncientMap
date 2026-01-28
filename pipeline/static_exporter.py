"""
Static Exporter for Ancient Nerds Map.

Exports unified data to optimized static JSON files for the Three.js globe.
Generates compact files designed for fast loading and zero-API operation.

Output files:
- public/data/sites/index.json     - Compact site markers for rendering
- public/data/sites/details/*.json - Full site details by region
- public/data/content/*.json       - Content items (texts, maps, etc.)
- public/data/links.json           - Site-to-content relationships
- public/data/sources.json         - Source metadata with colors

Usage:
    python -m pipeline.static_exporter
    python -m pipeline.static_exporter --sites-only
"""

import json
import gzip
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import defaultdict

from loguru import logger
from sqlalchemy import text

from pipeline.database import get_session


# Output configuration
OUTPUT_DIR = Path("public/data")
GZIP_OUTPUT = True  # Also create .gz versions

# Region definitions for chunking site details
REGIONS = {
    "europe": {"name": "Europe", "bounds": {"min_lat": 35, "max_lat": 72, "min_lon": -10, "max_lon": 45}},
    "mediterranean": {"name": "Mediterranean", "bounds": {"min_lat": 30, "max_lat": 46, "min_lon": -10, "max_lon": 40}},
    "middle_east": {"name": "Middle East", "bounds": {"min_lat": 15, "max_lat": 45, "min_lon": 25, "max_lon": 65}},
    "north_africa": {"name": "North Africa", "bounds": {"min_lat": 15, "max_lat": 38, "min_lon": -20, "max_lon": 35}},
    "asia": {"name": "Asia", "bounds": {"min_lat": 0, "max_lat": 60, "min_lon": 60, "max_lon": 150}},
    "americas": {"name": "Americas", "bounds": {"min_lat": -60, "max_lat": 72, "min_lon": -170, "max_lon": -30}},
    "oceania": {"name": "Oceania", "bounds": {"min_lat": -50, "max_lat": 0, "min_lon": 100, "max_lon": 180}},
    "africa": {"name": "Africa", "bounds": {"min_lat": -35, "max_lat": 38, "min_lon": -20, "max_lon": 55}},
}


def save_json(path: Path, data: Any, compress: bool = True):
    """Save data as JSON, optionally with gzip compression."""
    path.parent.mkdir(parents=True, exist_ok=True)

    # Save regular JSON
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"), ensure_ascii=False)

    size = path.stat().st_size
    logger.info(f"  Saved {path.name}: {size / 1024:.1f} KB")

    # Save gzipped version
    if compress and GZIP_OUTPUT:
        gz_path = path.with_suffix(path.suffix + ".gz")
        with open(path, "rb") as f_in:
            with gzip.open(gz_path, "wb", compresslevel=9) as f_out:
                shutil.copyfileobj(f_in, f_out)
        gz_size = gz_path.stat().st_size
        logger.info(f"  Saved {gz_path.name}: {gz_size / 1024:.1f} KB (gzip)")


class StaticExporter:
    """Exports database to optimized static JSON files."""

    def __init__(self, output_dir: Path = OUTPUT_DIR):
        self.output_dir = output_dir
        self.stats = {}

    def export_all(self, sites_only: bool = False):
        """Export all data to static files."""
        logger.info("=" * 60)
        logger.info("STATIC EXPORT - Ancient Nerds Map")
        logger.info("=" * 60)
        logger.info(f"Output directory: {self.output_dir}")

        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Export source metadata
        self._export_sources()

        # Export site index (compact, for markers)
        self._export_site_index()

        # Export site details (chunked by region)
        self._export_site_details()

        if not sites_only:
            # Export content links
            self._export_content_links()

            # Export content data
            self._export_content()

        self._print_summary()

    def _export_sources(self):
        """Export source metadata with colors and counts."""
        logger.info("\nExporting sources.json...")

        with get_session() as session:
            result = session.execute(text("""
                SELECT
                    sm.id,
                    sm.name,
                    sm.description,
                    sm.color,
                    sm.icon,
                    sm.category,
                    sm.enabled,
                    sm.license,
                    sm.attribution,
                    COALESCE(sm.record_count, 0) as record_count
                FROM source_meta sm
                ORDER BY sm.priority, sm.name
            """))

            sources = {}
            total_count = 0

            for row in result:
                sources[row.id] = {
                    "n": row.name,  # Short keys for smaller file
                    "d": row.description,
                    "c": row.color,
                    "i": row.icon,
                    "cat": row.category,
                    "cnt": row.record_count,
                    "lic": row.license,
                    "att": row.attribution,
                    "on": row.enabled,
                }
                total_count += row.record_count

            output = {
                "sources": sources,
                "total": total_count,
                "exported_at": datetime.utcnow().isoformat(),
            }

            save_json(self.output_dir / "sources.json", output)
            self.stats["sources"] = len(sources)

    def _export_site_index(self):
        """Export compact site index for rendering markers."""
        logger.info("\nExporting sites/index.json...")

        sites_dir = self.output_dir / "sites"
        sites_dir.mkdir(parents=True, exist_ok=True)

        with get_session() as session:
            # Get all sites with minimal data for markers
            result = session.execute(text("""
                SELECT
                    id,
                    name,
                    lat,
                    lon,
                    source_id,
                    site_type,
                    period_start,
                    period_end,
                    period_name,
                    country,
                    description,
                    thumbnail_url,
                    source_url
                FROM unified_sites
                ORDER BY source_id, name
            """))

            sites = []
            source_counts = defaultdict(int)

            for row in result:
                # Compact format with short keys
                site = {
                    "i": str(row.id),  # id
                    "n": row.name[:100] if row.name else "",  # name (truncated)
                    "la": round(row.lat, 5),  # latitude
                    "lo": round(row.lon, 5),  # longitude
                    "s": row.source_id,  # source
                }

                # Optional fields (only if present)
                if row.site_type:
                    site["t"] = row.site_type  # type
                if row.period_start is not None or row.period_end is not None:
                    site["p"] = [row.period_start, row.period_end]  # period
                if row.period_name:
                    site["pn"] = row.period_name  # period name (user-edited)
                if row.country:
                    site["c"] = row.country  # country
                if row.description:
                    site["d"] = row.description[:500]  # description (truncated)
                if row.thumbnail_url:
                    site["im"] = row.thumbnail_url  # image
                if row.source_url:
                    site["u"] = row.source_url  # source URL

                sites.append(site)
                source_counts[row.source_id] += 1

            output = {
                "sites": sites,
                "count": len(sites),
                "by_source": dict(source_counts),
                "exported_at": datetime.utcnow().isoformat(),
            }

            save_json(sites_dir / "index.json", output)
            self.stats["sites"] = len(sites)

            logger.info(f"  Total sites: {len(sites):,}")
            for source, count in sorted(source_counts.items(), key=lambda x: -x[1])[:10]:
                logger.info(f"    {source}: {count:,}")

    def _export_site_details(self):
        """Export full site details chunked by region."""
        logger.info("\nExporting site details by region...")

        details_dir = self.output_dir / "sites" / "details"
        details_dir.mkdir(parents=True, exist_ok=True)

        with get_session() as session:
            for region_id, region_config in REGIONS.items():
                bounds = region_config["bounds"]

                result = session.execute(text("""
                    SELECT
                        id,
                        source_id,
                        source_record_id,
                        name,
                        lat,
                        lon,
                        site_type,
                        period_start,
                        period_end,
                        period_name,
                        country,
                        description,
                        thumbnail_url,
                        source_url,
                        raw_data
                    FROM unified_sites
                    WHERE lat BETWEEN :min_lat AND :max_lat
                    AND lon BETWEEN :min_lon AND :max_lon
                """), {
                    "min_lat": bounds["min_lat"],
                    "max_lat": bounds["max_lat"],
                    "min_lon": bounds["min_lon"],
                    "max_lon": bounds["max_lon"],
                })

                sites = {}
                for row in result:
                    site_id = str(row.id)
                    sites[site_id] = {
                        "id": site_id,
                        "source": row.source_id,
                        "source_record_id": row.source_record_id,
                        "name": row.name,
                        "lat": round(row.lat, 6),
                        "lon": round(row.lon, 6),
                        "type": row.site_type,
                        "period": {
                            "start": row.period_start,
                            "end": row.period_end,
                            "name": row.period_name,
                        } if row.period_start or row.period_end or row.period_name else None,
                        "country": row.country,
                        "description": row.description[:1000] if row.description else None,
                        "thumbnail": row.thumbnail_url,
                        "url": row.source_url,
                    }

                if sites:
                    output = {
                        "region": region_config["name"],
                        "bounds": bounds,
                        "sites": sites,
                        "count": len(sites),
                    }
                    save_json(details_dir / f"{region_id}.json", output)
                    logger.info(f"  {region_config['name']}: {len(sites):,} sites")

    def _export_content_links(self):
        """Export site-to-content relationships."""
        logger.info("\nExporting content links...")

        with get_session() as session:
            result = session.execute(text("""
                SELECT
                    site_id,
                    content_type,
                    content_source,
                    content_id,
                    relevance_score
                FROM site_content_links
                WHERE relevance_score >= 0.2
                ORDER BY site_id, relevance_score DESC
            """))

            links = defaultdict(lambda: defaultdict(list))

            for row in result:
                site_id = str(row.site_id)
                content_type = row.content_type
                # Compact link format: [source, id, score]
                links[site_id][content_type].append([
                    row.content_source,
                    row.content_id,
                    round(row.relevance_score, 2),
                ])

            # Convert to regular dict for JSON serialization
            output = {
                "links": {k: dict(v) for k, v in links.items()},
                "count": len(links),
                "exported_at": datetime.utcnow().isoformat(),
            }

            save_json(self.output_dir / "links.json", output)
            self.stats["links"] = sum(sum(len(v) for v in types.values()) for types in links.values())
            logger.info(f"  Total links: {self.stats['links']:,}")

    def _export_content(self):
        """Export content items (texts, maps, inscriptions, etc.)."""
        logger.info("\nExporting content data...")

        content_dir = self.output_dir / "content"
        content_dir.mkdir(parents=True, exist_ok=True)

        with get_session() as session:
            # Get unique content items from links
            result = session.execute(text("""
                SELECT DISTINCT
                    content_type,
                    content_source,
                    content_id,
                    title,
                    thumbnail_url,
                    content_url,
                    metadata
                FROM site_content_links
            """))

            content_by_type = defaultdict(dict)

            for row in result:
                key = f"{row.content_source}:{row.content_id}"
                content_by_type[row.content_type][key] = {
                    "src": row.content_source,
                    "id": row.content_id,
                    "t": row.title[:200] if row.title else "",
                    "thumb": row.thumbnail_url,
                    "url": row.content_url,
                    "meta": row.metadata if row.metadata else {},
                }

            # Save each content type to separate file
            for content_type, items in content_by_type.items():
                output = {
                    "type": content_type,
                    "items": items,
                    "count": len(items),
                }
                save_json(content_dir / f"{content_type}s.json", output)
                self.stats[f"content_{content_type}"] = len(items)
                logger.info(f"  {content_type}: {len(items):,} items")

    def _print_summary(self):
        """Print export summary."""
        logger.info("\n" + "=" * 60)
        logger.info("EXPORT SUMMARY")
        logger.info("=" * 60)

        for key, value in sorted(self.stats.items()):
            logger.info(f"  {key}: {value:,}")

        # Calculate total output size
        total_size = sum(f.stat().st_size for f in self.output_dir.rglob("*.json"))
        total_gz_size = sum(f.stat().st_size for f in self.output_dir.rglob("*.gz"))

        logger.info("-" * 60)
        logger.info(f"Total JSON size: {total_size / 1024 / 1024:.2f} MB")
        if total_gz_size:
            logger.info(f"Total gzipped size: {total_gz_size / 1024 / 1024:.2f} MB")


def build_static(output_dir: Optional[str] = None, sites_only: bool = False):
    """Build static files for deployment."""
    exporter = StaticExporter(Path(output_dir) if output_dir else OUTPUT_DIR)
    exporter.export_all(sites_only=sites_only)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Export database to static JSON files")
    parser.add_argument("--output", "-o", help="Output directory", default=str(OUTPUT_DIR))
    parser.add_argument("--sites-only", action="store_true", help="Only export sites (skip content)")
    parser.add_argument("--no-gzip", action="store_true", help="Skip gzip compression")
    args = parser.parse_args()

    if args.no_gzip:
        global GZIP_OUTPUT
        GZIP_OUTPUT = False

    build_static(output_dir=args.output, sites_only=args.sites_only)


if __name__ == "__main__":
    main()
