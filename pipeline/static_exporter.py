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

Retired sites (E4, migration 0020) are left out of every site-keyed file: the index,
the details, the image index, the content links, the hub list and the snapshot file.

Usage:
    python -m pipeline.static_exporter
    python -m pipeline.static_exporter --sites-only
    python -m pipeline.static_exporter --no-library   # what POST /api/sites/rebuild-static runs
"""

import gzip
import json
import shutil
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import text

from pipeline.database import LibrarySource, get_session
from pipeline.research_html_renderer import PUBLIC_PAPER_WHERE
from pipeline.sites_html_renderer import country_path
from pipeline.utils.public_sites import curated_page, is_retired, not_retired

# Output configuration
OUTPUT_DIR = Path("public/data")
GZIP_OUTPUT = True  # Also create .gz versions
HUBS_SNAPSHOT_NAME = "hubs.snapshot.json"

# Retention for file snapshots: keep the newest N, prune the rest (files +
# manifest entries) after each new snapshot write. Without this the snapshot
# dir and manifest grow unbounded (audit P6-16).
MAX_FILE_SNAPSHOTS = 50

# The E4 scope predicates this module needs, spelled once.
_SHOWN = not_retired()
_US_SHOWN = not_retired("us")
_CURATED_PAGE = curated_page()
_US_RETIRED = is_retired("us")

# Region definitions for chunking site details
REGIONS = {
    "europe": {
        "name": "Europe",
        "bounds": {"min_lat": 35, "max_lat": 72, "min_lon": -10, "max_lon": 45},
    },
    "mediterranean": {
        "name": "Mediterranean",
        "bounds": {"min_lat": 30, "max_lat": 46, "min_lon": -10, "max_lon": 40},
    },
    "middle_east": {
        "name": "Middle East",
        "bounds": {"min_lat": 15, "max_lat": 45, "min_lon": 25, "max_lon": 65},
    },
    "north_africa": {
        "name": "North Africa",
        "bounds": {"min_lat": 15, "max_lat": 38, "min_lon": -20, "max_lon": 35},
    },
    "asia": {
        "name": "Asia",
        "bounds": {"min_lat": 0, "max_lat": 60, "min_lon": 60, "max_lon": 150},
    },
    "americas": {
        "name": "Americas",
        "bounds": {"min_lat": -60, "max_lat": 72, "min_lon": -170, "max_lon": -30},
    },
    "oceania": {
        "name": "Oceania",
        "bounds": {"min_lat": -50, "max_lat": 0, "min_lon": 100, "max_lon": 180},
    },
    "africa": {
        "name": "Africa",
        "bounds": {"min_lat": -35, "max_lat": 38, "min_lon": -20, "max_lon": 55},
    },
}


def _slugify_period(period_name: str) -> str:
    """Convert period label to URL slug."""
    s = period_name.lower().strip()
    s = s.replace("<", "before").replace("+", "plus").replace(" - ", "-").replace(" ", "-")
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-")


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
            with gzip.open(str(gz_path), "wb", compresslevel=9) as f_out:
                shutil.copyfileobj(f_in, f_out)
        gz_size = gz_path.stat().st_size
        logger.info(f"  Saved {gz_path.name}: {gz_size / 1024:.1f} KB (gzip)")


def fetch_hub_rows(session) -> list[Any]:
    """Country hubs — same scope as sitemap-countries.xml (retired sites excluded)."""
    countries = session.execute(
        text(f"""
            SELECT country, COUNT(*) AS sites
            FROM unified_sites
            WHERE {_CURATED_PAGE}
            GROUP BY country
            ORDER BY country
        """)
    ).fetchall()
    return list(countries)


def build_hubs_payload(country_rows: list[Any]) -> dict:
    """Rows → the JSON the frontend build bakes into index.html.

    country_rows: objects with .country and .sites (count of curated sites).
    The papers left the snapshot on 2026-09-10: the homepage's research portal
    opens /research/, which links every paper, so the list was a duplicate.
    """
    countries = [
        {"country": row.country, "path": country_path(row.country), "sites": int(row.sites)}
        for row in sorted(country_rows, key=lambda r: r.country)
    ]
    return {
        "exported_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "countries": countries,
    }


def write_file_snapshot(session, snapshots_dir: Path) -> str:
    """Write a dated snapshot of the curated sites plus the manifest entry; return its key.

    The one writer of public/data/snapshots/ - the audit page's version history and the
    source pins of /api/sites/all read these files. It used to exist twice (here with
    fewer fields and no retention, and in api/services/snapshots.py), and POST
    /api/sites/rebuild-static ran both, writing two manifest entries per rebuild - the
    same key twice when both landed in one second.

    Retired sites are left out: the files are public (nginx serves public/data/) and a pin
    serves them on the globe. A corrupt manifest raises instead of being replaced by an
    empty one, which would silently drop the whole version history.
    """
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(UTC)
    snapshot_key = now.strftime("%Y-%m-%d_%H%M%S")

    result = session.execute(
        text(f"""
        SELECT
            us.id, us.name, us.lat, us.lon, us.source_id, us.site_type,
            us.period_start, us.period_end, us.period_name, us.country,
            us.description, us.thumbnail_url, us.source_url, us.edited_by,
            us.created_at,
            hero.original_url     AS hero_url,
            hero.commons_page_url AS hero_attribution_url,
            COALESCE(refs.links, '[]'::jsonb) AS reference_links
        FROM unified_sites us
        LEFT JOIN LATERAL (
            SELECT original_url, commons_page_url
            FROM wiki_images
            WHERE site_id = us.id AND is_hero = true
            ORDER BY id LIMIT 1
        ) hero ON TRUE
        LEFT JOIN LATERAL (
            SELECT jsonb_agg(
                jsonb_build_object('url', content_url, 'title', title)
                ORDER BY id
            ) AS links
            FROM site_content_links
            WHERE site_id = us.id AND content_type = 'reference'
              AND content_url IS NOT NULL
        ) refs ON TRUE
        WHERE us.source_id IN ('ancient_nerds', 'lyra', 'ancient_nerds_community')
          AND {_US_SHOWN}
        ORDER BY us.source_id, us.name
    """)
    )

    sites = []
    source_counts: dict[str, int] = defaultdict(int)

    for row in result:
        site: dict[str, object] = {
            "id": str(row.id),
            "n": row.name[:100] if row.name else "",
            "la": round(row.lat, 5),
            "lo": round(row.lon, 5),
            "s": row.source_id,
        }
        if row.site_type:
            site["t"] = row.site_type
        if row.period_start is not None:
            site["p"] = row.period_start
        if row.period_name:
            site["pn"] = row.period_name
        if row.country:
            site["c"] = row.country
        if row.description:
            site["d"] = row.description[:500]
        if row.thumbnail_url:
            site["i"] = row.thumbnail_url
        if row.source_url:
            site["u"] = row.source_url
        if row.edited_by and row.edited_by != "initial":
            site["eb"] = row.edited_by
        if row.created_at:
            site["ea"] = row.created_at.isoformat()
        if row.hero_url:
            site["hu"] = row.hero_url
        if row.hero_attribution_url:
            site["ha"] = row.hero_attribution_url
        if row.reference_links:
            site["rl"] = row.reference_links

        sites.append(site)
        source_counts[row.source_id] += 1

    snapshot_data = {
        "snapshot_date": now.isoformat(),
        "sites": sites,
        "count": len(sites),
        "by_source": dict(source_counts),
    }

    snapshot_file = f"{snapshot_key}.json"
    with open(snapshots_dir / snapshot_file, "w", encoding="utf-8") as f:
        json.dump(snapshot_data, f, separators=(",", ":"))

    manifest_path = snapshots_dir / "manifest.json"
    manifest: dict = {"snapshots": []}
    if manifest_path.exists():
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

    snapshots = [e for e in manifest["snapshots"] if e["date"] != snapshot_key]
    snapshots.append(
        {
            "date": snapshot_key,
            "file": snapshot_file,
            "sites": len(sites),
            "by_source": dict(source_counts),
        }
    )
    snapshots.sort(key=lambda e: e["date"], reverse=True)

    # Retention sweep: keep the newest MAX_FILE_SNAPSHOTS, delete older files and
    # drop their manifest entries.
    pruned = snapshots[MAX_FILE_SNAPSHOTS:]
    manifest["snapshots"] = snapshots[:MAX_FILE_SNAPSHOTS]
    for entry in pruned:
        (snapshots_dir / entry["file"]).unlink(missing_ok=True)

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    if pruned:
        logger.info(
            f"  Pruned {len(pruned)} file snapshot(s) beyond retention of {MAX_FILE_SNAPSHOTS}"
        )
    logger.info(f"  Snapshot {snapshot_key}: {len(sites):,} sites")
    return snapshot_key


def build_hubs_snapshot() -> dict:
    """Query the DB and build the hubs payload (no file written)."""
    with get_session() as session:
        countries = fetch_hub_rows(session)
    return build_hubs_payload(countries)


def export_hubs_snapshot(output_dir: Path = OUTPUT_DIR) -> Path:
    """Write public/data/hubs.snapshot.json — the homepage's country hub list.

    index.html is a static Vite entry, so its crawlable links to the 98
    /sites/{country} hubs are baked in at build time from this file
    (vite.config.ts → landingHubs). It is written at every full export, so
    the next frontend build carries the current countries. public/data is the
    bind-mounted volume the containers share with the host checkout; the
    committed ancient-nerds-map/src/data/hubs.snapshot.json is only the
    dev/CI baseline (scripts/export_hubs.py --baseline).
    """
    path = output_dir / HUBS_SNAPSHOT_NAME
    save_json(path, build_hubs_snapshot(), compress=False)
    return path


class StaticExporter:
    """Exports database to optimized static JSON files."""

    def __init__(self, output_dir: Path = OUTPUT_DIR):
        self.output_dir = output_dir
        self.stats = {}

    def export_all(self, sites_only: bool = False, library: bool = True):
        """Export all data to static files.

        library=False leaves public/data/library/ alone. The rebuild job passes it: the
        library has its own job (POST /api/library/refresh), which aggregates the
        citations first and then writes the same files - two jobs under two locks would
        otherwise write them at the same time.
        """
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

        # Export wiki image index
        self._export_wiki_images()

        # Homepage hub lists (country pages + public papers)
        export_hubs_snapshot(self.output_dir)

        if not sites_only:
            # Export content links
            self._export_content_links()

            # Export content data
            self._export_content()

            # Export library sources by period
            if library:
                self._export_library()

        # Save dated audit snapshot for version history
        self._save_audit_snapshot()

        self._print_summary()

    def _export_sources(self):
        """Export source metadata with colors and counts."""
        logger.info("\nExporting sources.json...")

        with get_session() as session:
            result = session.execute(
                text("""
                SELECT
                    sm.id,
                    sm.name,
                    sm.description,
                    sm.color,
                    sm.icon,
                    sm.category,
                    sm.enabled_by_default,
                    sm.is_primary,
                    sm.priority,
                    sm.license,
                    sm.attribution,
                    COALESCE(sm.record_count, 0) as record_count
                FROM source_meta sm
                WHERE sm.enabled = true
                ORDER BY sm.priority, sm.name
            """)
            )

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
                    "on": row.enabled_by_default,
                    "pri": row.is_primary,
                    "p": row.priority,
                }
                total_count += row.record_count

            output = {
                "sources": sources,
                "total": total_count,
                "exported_at": datetime.now(UTC).isoformat(),
            }

            save_json(self.output_dir / "sources.json", output)
            self.stats["sources"] = len(sources)

    def _load_alt_names(self, session) -> dict[str, list[str]]:
        """Load Latin-script alternate names grouped by site_id.

        Only includes names that differ from the primary name after normalization,
        and only Latin-script names (useful for search, not Arabic/Chinese/etc).
        """
        result = session.execute(
            text(
                """
            SELECT usn.site_id, usn.name
            FROM unified_site_names usn
            JOIN unified_sites us ON us.id = usn.site_id
            WHERE usn.name_normalized != us.name_normalized
            AND usn.name ~ '^[a-zA-Z\u00c0-\u024f\u1e00-\u1eff]'
            AND """
                + _US_SHOWN
            )
        )

        alt_names: dict[str, list[str]] = defaultdict(list)
        seen: dict[str, set[str]] = defaultdict(set)
        for row in result:
            site_id = str(row.site_id)
            name = row.name.strip()
            # Deduplicate by lowercase
            name_lower = name.lower()
            if name_lower not in seen[site_id]:
                seen[site_id].add(name_lower)
                alt_names[site_id].append(name)

        return dict(alt_names)

    def _export_site_index(self):
        """Export compact site index for rendering markers."""
        logger.info("\nExporting sites/index.json...")

        sites_dir = self.output_dir / "sites"
        sites_dir.mkdir(parents=True, exist_ok=True)

        with get_session() as session:
            # Load alternate names for search
            alt_names_map = self._load_alt_names(session)
            logger.info(f"  Loaded alt names for {len(alt_names_map):,} sites")

            # Get all sites with minimal data for markers
            result = session.execute(
                text(f"""
                SELECT
                    us.id,
                    us.name,
                    us.lat,
                    us.lon,
                    us.source_id,
                    us.site_type,
                    us.period_start,
                    us.period_end,
                    us.period_name,
                    us.country,
                    us.description,
                    us.thumbnail_url,
                    us.source_url,
                    cs.card_description,
                    cs.best_wiki_url,
                    cs.source_language,
                    us.raw_data,
                    wi.filename AS hero_filename
                FROM unified_sites us
                LEFT JOIN card_stats cs ON cs.site_id = us.id
                LEFT JOIN LATERAL (
                    SELECT filename
                    FROM wiki_images
                    WHERE site_id = us.id AND is_excluded IS NOT TRUE
                    ORDER BY is_hero DESC, is_lead DESC, sort_order
                    LIMIT 1
                ) wi ON true
                WHERE {_US_SHOWN}
                ORDER BY us.source_id, us.name
            """)
            )

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
                if row.hero_filename:
                    sid_short = str(row.id).replace("-", "")[:8]
                    site["im"] = f"/data/images/wiki/{sid_short}/{row.hero_filename}"
                elif row.thumbnail_url:
                    site["im"] = row.thumbnail_url  # fallback to legacy thumbnail
                if row.source_url:
                    site["u"] = row.source_url  # source URL
                if row.card_description:
                    site["cd"] = row.card_description  # card description
                if row.best_wiki_url and row.source_language and row.source_language != "en":
                    site["wu"] = row.best_wiki_url  # wiki URL (non-English source)
                    site["sl"] = row.source_language  # source language

                # Alternate names for search (Latin-script only, max 10)
                site_alt = alt_names_map.get(str(row.id))
                if site_alt:
                    site["an"] = site_alt[:10]

                # Description citations from enrichment pipeline
                rd = row.raw_data
                if isinstance(rd, str):
                    import json as _json

                    try:
                        rd = _json.loads(rd)
                    except (ValueError, TypeError):
                        rd = None
                if isinstance(rd, dict) and "description_citations" in rd:
                    site["dc"] = rd["description_citations"]

                sites.append(site)
                source_counts[row.source_id] += 1

            output = {
                "sites": sites,
                "count": len(sites),
                "by_source": dict(source_counts),
                "exported_at": datetime.now(UTC).isoformat(),
            }

            save_json(sites_dir / "index.json", output)
            self.stats["sites"] = len(sites)

            logger.info(f"  Total sites: {len(sites):,}")
            for source, count in sorted(source_counts.items(), key=lambda x: -x[1])[:10]:
                logger.info(f"    {source}: {count:,}")

    def _load_reference_links(self, session) -> dict[str, list[dict]]:
        """Load reference links (web-searched) grouped by site_id.

        Returns top 5 per site sorted by relevance_score descending.
        """
        result = session.execute(
            text("""
            SELECT
                site_id::text,
                content_url,
                title,
                relevance_score,
                link_metadata
            FROM site_content_links
            WHERE content_type = 'reference'
            AND content_url IS NOT NULL
            ORDER BY site_id, relevance_score DESC
        """)
        )

        refs: dict[str, list[dict]] = defaultdict(list)
        for row in result:
            site_id = row.site_id
            if len(refs[site_id]) >= 5:
                continue
            meta = row.link_metadata or {}
            ref: dict = {
                "u": row.content_url,
                "t": row.title[:200] if row.title else "",
                "d": meta.get("domain", ""),
                "k": meta.get("link_type", "article"),
            }
            refs[site_id].append(ref)

        return dict(refs)

    def _export_site_details(self):
        """Export full site details chunked by region."""
        logger.info("\nExporting site details by region...")

        details_dir = self.output_dir / "sites" / "details"
        details_dir.mkdir(parents=True, exist_ok=True)

        with get_session() as session:
            # Pre-load reference links for all sites
            ref_links = self._load_reference_links(session)
            if ref_links:
                logger.info(f"  Loaded reference links for {len(ref_links):,} sites")

            for region_id, region_config in REGIONS.items():
                bounds = region_config["bounds"]

                result = session.execute(
                    text(f"""
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
                    AND {_SHOWN}
                """),
                    {
                        "min_lat": bounds["min_lat"],
                        "max_lat": bounds["max_lat"],
                        "min_lon": bounds["min_lon"],
                        "max_lon": bounds["max_lon"],
                    },
                )

                sites = {}
                for row in result:
                    site_id = str(row.id)
                    site_data: dict = {
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
                        }
                        if row.period_start or row.period_end or row.period_name
                        else None,
                        "country": row.country,
                        "description": row.description[:1000] if row.description else None,
                        "thumbnail": row.thumbnail_url,
                        "url": row.source_url,
                    }

                    # Add reference links if available
                    site_refs = ref_links.get(site_id)
                    if site_refs:
                        site_data["refs"] = site_refs

                    # Description citations from enrichment pipeline
                    rd = row.raw_data
                    if isinstance(rd, str):
                        import json as _json

                        try:
                            rd = _json.loads(rd)
                        except (ValueError, TypeError):
                            rd = None
                    if isinstance(rd, dict) and "description_citations" in rd:
                        site_data["description_citations"] = rd["description_citations"]

                    sites[site_id] = site_data

                if sites:
                    output = {
                        "region": region_config["name"],
                        "bounds": bounds,
                        "sites": sites,
                        "count": len(sites),
                    }
                    save_json(details_dir / f"{region_id}.json", output)
                    logger.info(f"  {region_config['name']}: {len(sites):,} sites")

    def _export_wiki_images(self):
        """Export wiki image index for frontend (site_id → image metadata)."""
        logger.info("\nExporting images/index.json...")

        images_dir = self.output_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        with get_session() as session:
            result = session.execute(
                text(f"""
                SELECT
                    site_id, filename, author, license,
                    commons_page_url, is_hero, is_lead,
                    width, height, sort_order
                FROM wiki_images
                WHERE is_excluded IS NOT TRUE
                  AND NOT EXISTS (
                      SELECT 1 FROM unified_sites us
                      WHERE us.id = wiki_images.site_id AND {_US_RETIRED}
                  )
                ORDER BY site_id, sort_order
            """)
            )

            index: dict[str, list] = {}
            total_images = 0

            for row in result:
                site_id = str(row.site_id)
                site_id_short = site_id.replace("-", "")[:8]

                img: dict = {
                    "f": row.filename,
                    "p": f"/data/images/wiki/{site_id_short}/{row.filename}",
                }
                # Optional fields (only include if present to save space)
                if row.author:
                    img["a"] = row.author
                if row.license:
                    img["l"] = row.license
                if row.commons_page_url:
                    img["c"] = row.commons_page_url
                if row.is_hero:
                    img["h"] = True
                if row.is_lead:
                    img["ld"] = True
                if row.width:
                    img["w"] = row.width
                if row.height:
                    img["ht"] = row.height

                if site_id not in index:
                    index[site_id] = []
                index[site_id].append(img)
                total_images += 1

            save_json(images_dir / "index.json", index)
            self.stats["wiki_images"] = total_images
            self.stats["wiki_image_sites"] = len(index)
            logger.info(f"  {total_images:,} images for {len(index):,} sites")

    def _export_content_links(self):
        """Export site-to-content relationships."""
        logger.info("\nExporting content links...")

        with get_session() as session:
            result = session.execute(
                text(f"""
                SELECT
                    site_id,
                    content_type,
                    content_source,
                    content_id,
                    relevance_score
                FROM site_content_links
                WHERE relevance_score >= 0.2
                  AND NOT EXISTS (
                      SELECT 1 FROM unified_sites us
                      WHERE us.id = site_content_links.site_id AND {_US_RETIRED}
                  )
                ORDER BY site_id, relevance_score DESC
            """)
            )

            links = defaultdict(lambda: defaultdict(list))

            for row in result:
                site_id = str(row.site_id)
                content_type = row.content_type
                # Compact link format: [source, id, score]
                links[site_id][content_type].append(
                    [
                        row.content_source,
                        row.content_id,
                        round(row.relevance_score, 2),
                    ]
                )

            # Convert to regular dict for JSON serialization
            output = {
                "links": {k: dict(v) for k, v in links.items()},
                "count": len(links),
                "exported_at": datetime.now(UTC).isoformat(),
            }

            save_json(self.output_dir / "links.json", output)
            self.stats["links"] = sum(
                sum(len(v) for v in types.values()) for types in links.values()
            )
            logger.info(f"  Total links: {self.stats['links']:,}")

    def _export_content(self):
        """Export content items (texts, maps, inscriptions, etc.)."""
        logger.info("\nExporting content data...")

        content_dir = self.output_dir / "content"
        content_dir.mkdir(parents=True, exist_ok=True)

        with get_session() as session:
            # Get unique content items from links
            result = session.execute(
                text("""
                SELECT DISTINCT
                    content_type,
                    content_source,
                    content_id,
                    title,
                    thumbnail_url,
                    content_url,
                    link_metadata
                FROM site_content_links
            """)
            )

            content_by_type = defaultdict(dict)

            for row in result:
                key = f"{row.content_source}:{row.content_id}"
                content_by_type[row.content_type][key] = {
                    "src": row.content_source,
                    "id": row.content_id,
                    "t": row.title[:200] if row.title else "",
                    "thumb": row.thumbnail_url,
                    "url": row.content_url,
                    "meta": row.link_metadata if row.link_metadata else {},
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

    def _export_library(self):
        """Export library sources organized by period."""
        logger.info("\nExporting library data...")

        lib_dir = self.output_dir / "library"
        lib_dir.mkdir(parents=True, exist_ok=True)
        periods_dir = lib_dir / "periods"
        periods_dir.mkdir(parents=True, exist_ok=True)

        with get_session() as session:
            sources = (
                session.query(LibrarySource).order_by(LibrarySource.citation_count.desc()).all()
            )

            if not sources:
                logger.info("  No library sources to export")
                save_json(lib_dir / "index.json", [])
                save_json(lib_dir / "stats.json", {"total": 0})
                return

            # Group by period
            period_groups: dict[str, list[dict]] = {}
            type_counts: dict[str, int] = {}
            tier_counts: dict[int, int] = {}
            domain_counts: dict[str, int] = {}

            for src in sources:
                row = {
                    "id": src.id,
                    "url": src.url,
                    "title": src.title,
                    "domain": src.domain,
                    "snippet": src.snippet,
                    "reliability_tier": src.reliability_tier,
                    "citation_count": src.citation_count,
                    "source_types": src.source_types or [],
                    "parent_refs": src.parent_refs or [],
                }

                # Stats
                for st in src.source_types or []:
                    type_counts[st] = type_counts.get(st, 0) + 1
                tier_counts[src.reliability_tier] = tier_counts.get(src.reliability_tier, 0) + 1
                if src.domain:
                    domain_counts[src.domain] = domain_counts.get(src.domain, 0) + 1

                periods = src.period_tags or []
                if not periods:
                    periods = ["Uncategorized"]
                for period in periods:
                    period_groups.setdefault(period, []).append(row)

            # Write period files — chronological (oldest first), Uncategorized last
            from pipeline.utils.text import PERIOD_BUCKETS

            period_order = {label: i for i, (label, _, _) in enumerate(PERIOD_BUCKETS)}
            index = []
            sorted_periods = sorted(
                period_groups.keys(),
                key=lambda p: (
                    p == "Uncategorized",  # Uncategorized always last
                    period_order.get(p, 999),  # known periods in chronological order
                    p,  # alphabetical fallback for unknowns
                ),
            )
            for period_name in sorted_periods:
                group = period_groups[period_name]
                slug = _slugify_period(period_name)

                period_data = {
                    "period": period_name,
                    "slug": slug,
                    "total": len(group),
                    "sources": group,
                }
                save_json(periods_dir / f"{slug}.json", period_data)
                index.append({"period": period_name, "slug": slug, "count": len(group)})

            save_json(lib_dir / "index.json", index)

            # Stats
            top_domains = sorted(domain_counts.items(), key=lambda x: -x[1])[:20]
            stats = {
                "total_sources": len(sources),
                "by_type": type_counts,
                "by_tier": tier_counts,
                "top_domains": [{"domain": d, "count": c} for d, c in top_domains],
                "period_count": len(index),
                "exported_at": datetime.now(UTC).isoformat(),
            }
            save_json(lib_dir / "stats.json", stats)

            self.stats["library_sources"] = len(sources)
            logger.info(f"  Library: {len(sources)} sources across {len(index)} periods")

    def _save_audit_snapshot(self):
        """Save a dated snapshot of the curated sites for version history."""
        logger.info("\nSaving audit snapshot...")
        # Not into self.stats: _print_summary formats every stat as a number.
        with get_session() as session:
            write_file_snapshot(session, self.output_dir / "snapshots")

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


def build_static(output_dir: str | None = None, sites_only: bool = False, library: bool = True):
    """Build static files for deployment."""
    exporter = StaticExporter(Path(output_dir) if output_dir else OUTPUT_DIR)
    exporter.export_all(sites_only=sites_only, library=library)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Export database to static JSON files")
    parser.add_argument("--output", "-o", help="Output directory", default=str(OUTPUT_DIR))
    parser.add_argument(
        "--sites-only", action="store_true", help="Only export sites (skip content)"
    )
    parser.add_argument("--no-gzip", action="store_true", help="Skip gzip compression")
    parser.add_argument(
        "--no-library",
        action="store_true",
        help="Leave public/data/library/ alone (the library refresh job owns it)",
    )
    parser.add_argument(
        "--hubs-only", action="store_true", help="Only refresh hubs.snapshot.json (homepage lists)"
    )
    args = parser.parse_args()

    if args.no_gzip:
        global GZIP_OUTPUT
        GZIP_OUTPUT = False

    if args.hubs_only:
        print(export_hubs_snapshot(Path(args.output)))
        return

    build_static(output_dir=args.output, sites_only=args.sites_only, library=not args.no_library)


if __name__ == "__main__":
    main()
