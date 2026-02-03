"""
Wikimedia Commons/Wikidata image fallback for archaeological sites.

Strategy:
1. Query Wikidata SPARQL for archaeological sites with P18 (image) property
2. Match to our existing sites by name + coordinates
3. Fall back to Commons API search for unmatched sites
4. Update unified_sites.thumbnail_url in database

Usage:
    python -m pipeline.site_images.wikimedia_fallback
    python -m pipeline.site_images.wikimedia_fallback --limit 1000
    python -m pipeline.site_images.wikimedia_fallback --commons-only
    python -m pipeline.site_images.wikimedia_fallback --stats
"""

import argparse
import time
import urllib.parse
from collections.abc import Iterator
from dataclasses import dataclass

from loguru import logger
from sqlalchemy import text, update
from sqlalchemy.orm import Session

from pipeline.database import UnifiedSite, get_session
from pipeline.utils import parse_wkt_point as _parse_wkt_point
from pipeline.utils.http import RateLimitError, fetch_with_retry

# =============================================================================
# Configuration
# =============================================================================

# Wikidata SPARQL endpoint
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"

# Wikimedia Commons API
COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"

# Rate limits
WIKIDATA_DELAY = 2.0  # Wikidata requests 1 req/sec for bots
COMMONS_DELAY = 0.5   # Commons is more lenient

# Batch sizes
WIKIDATA_BATCH_SIZE = 5000  # SPARQL results per query
DB_UPDATE_BATCH_SIZE = 500  # Database updates per commit

# Coordinate matching threshold (degrees, ~5km)
COORD_THRESHOLD = 0.05

# Commons image URL template
COMMONS_THUMB_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/{hash_path}/{filename}/{width}px-{filename}"
COMMONS_FULL_URL = "https://commons.wikimedia.org/wiki/File:{filename}"

# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class WikidataResult:
    """Result from Wikidata SPARQL query."""
    qid: str
    name: str
    lat: float
    lon: float
    image_filename: str
    image_url: str

@dataclass
class SiteMatch:
    """Matched site with image."""
    site_id: str
    site_name: str
    image_url: str
    source: str  # 'wikidata' or 'commons'


# =============================================================================
# Wikidata SPARQL Queries
# =============================================================================

WIKIDATA_ARCHAEOLOGY_QUERY = """
SELECT ?item ?itemLabel ?coord ?image WHERE {{
  # Archaeological sites and related types
  VALUES ?type {{
    wd:Q839954      # archaeological site
    wd:Q4989906     # monument
    wd:Q570116      # tourist attraction (includes many heritage sites)
    wd:Q2319498     # ancient city
    wd:Q3947        # house (includes historical houses)
    wd:Q16560       # palace
    wd:Q44539       # temple
    wd:Q12518       # tower
    wd:Q1081138     # castle ruins
    wd:Q23413       # castle
    wd:Q839954      # archaeological site
    wd:Q24398318    # fortification
    wd:Q33506       # museum
    wd:Q5773637     # historic site
    wd:Q1497375     # ancient monument
    wd:Q17715832    # archaeological artifact
    wd:Q17524420    # cultural heritage
    wd:Q9259        # UNESCO World Heritage Site
    wd:Q35509       # cave
    wd:Q179700      # statue
    wd:Q4989906     # monument
    wd:Q271669      # megalith
    wd:Q178561      # battle
    wd:Q751876      # hill fort
    wd:Q201676      # dolmen
    wd:Q179049      # menhir
    wd:Q210272      # stone circle
    wd:Q152095      # burial mound
    wd:Q7075        # library (ancient libraries)
  }}
  ?item wdt:P31/wdt:P279* ?type .

  # Must have coordinates
  ?item wdt:P625 ?coord .

  # Must have image
  ?item wdt:P18 ?image .

  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,de,fr,es,it,nl,la". }}
}}
LIMIT {limit}
OFFSET {offset}
"""

# Simpler query for specific regions (faster)
WIKIDATA_REGION_QUERY = """
SELECT ?item ?itemLabel ?coord ?image WHERE {{
  ?item wdt:P625 ?coord .
  ?item wdt:P18 ?image .

  # Filter by bounding box
  SERVICE wikibase:box {{
    ?item wdt:P625 ?coord .
    bd:serviceParam wikibase:cornerWest "Point({lon_min} {lat_min})"^^geo:wktLiteral .
    bd:serviceParam wikibase:cornerEast "Point({lon_max} {lat_max})"^^geo:wktLiteral .
  }}

  # Archaeological site types
  ?item wdt:P31/wdt:P279* wd:Q839954 .

  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,de,fr,es,it,nl,la". }}
}}
LIMIT {limit}
"""


# =============================================================================
# Wikidata Functions
# =============================================================================

def parse_wkt_point(wkt: str) -> tuple[float, float]:
    """Parse WKT Point to (lat, lon). Uses shared utility."""
    lon, lat = _parse_wkt_point(wkt)
    if lon is not None and lat is not None:
        return lat, lon
    return 0.0, 0.0


def query_wikidata_sparql(query: str) -> list[dict]:
    """Execute Wikidata SPARQL query."""
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": "AncientNerds/1.0 (Archaeological Research Platform; contact@ancientnerds.com)",
    }

    try:
        response = fetch_with_retry(
            WIKIDATA_SPARQL_URL,
            params={"query": query, "format": "json"},
            headers=headers,
            timeout=120,
        )

        if response.status_code == 200:
            data = response.json()
            return data.get("results", {}).get("bindings", [])
        else:
            logger.warning(f"Wikidata query failed: {response.status_code}")
            return []

    except RateLimitError:
        logger.warning("Wikidata rate limited, waiting 60s...")
        time.sleep(60)
        return []
    except Exception as e:
        logger.error(f"Wikidata query error: {e}")
        return []


def fetch_wikidata_images(limit: int = 50000) -> Iterator[WikidataResult]:
    """
    Fetch archaeological site images from Wikidata.

    Yields WikidataResult for each site with an image.
    """
    logger.info(f"Fetching Wikidata images (limit={limit})...")

    offset = 0
    total_fetched = 0

    while total_fetched < limit:
        batch_limit = min(WIKIDATA_BATCH_SIZE, limit - total_fetched)
        query = WIKIDATA_ARCHAEOLOGY_QUERY.format(limit=batch_limit, offset=offset)

        logger.info(f"  Querying offset={offset}, limit={batch_limit}...")
        results = query_wikidata_sparql(query)

        if not results:
            logger.info("  No more results")
            break

        for item in results:
            try:
                qid = item.get("item", {}).get("value", "").split("/")[-1]
                name = item.get("itemLabel", {}).get("value", "")
                coord_wkt = item.get("coord", {}).get("value", "")
                image_url = item.get("image", {}).get("value", "")

                if not all([qid, name, coord_wkt, image_url]):
                    continue

                lat, lon = parse_wkt_point(coord_wkt)

                # Extract filename from Commons URL
                filename = urllib.parse.unquote(image_url.split("/")[-1])

                yield WikidataResult(
                    qid=qid,
                    name=name,
                    lat=lat,
                    lon=lon,
                    image_filename=filename,
                    image_url=image_url,
                )
                total_fetched += 1

            except Exception as e:
                logger.debug(f"Parse error: {e}")
                continue

        offset += batch_limit
        time.sleep(WIKIDATA_DELAY)

    logger.info(f"Fetched {total_fetched} images from Wikidata")


# =============================================================================
# Commons API Functions
# =============================================================================

def get_commons_thumb_url(filename: str, width: int = 300) -> str:
    """
    Generate Commons thumbnail URL for a filename.

    Commons uses MD5 hash-based paths for files.
    """
    import hashlib

    # Replace spaces with underscores
    filename = filename.replace(" ", "_")

    # Calculate MD5 hash of filename
    md5 = hashlib.md5(filename.encode('utf-8')).hexdigest()
    hash_path = f"{md5[0]}/{md5[0:2]}"

    return COMMONS_THUMB_URL.format(
        hash_path=hash_path,
        filename=filename,
        width=width,
    )


def search_commons_images(query: str, limit: int = 5) -> list[dict]:
    """
    Search Wikimedia Commons for images matching a query.

    Returns list of image info dicts with url, filename, etc.
    """
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": f'"{query}"',
        "gsrnamespace": "6",  # File namespace
        "gsrlimit": limit,
        "prop": "imageinfo",
        "iiprop": "url|size|mime",
        "iiurlwidth": 300,  # Request thumbnail
    }

    headers = {
        "User-Agent": "AncientNerds/1.0 (Archaeological Research Platform)",
    }

    try:
        response = fetch_with_retry(
            COMMONS_API_URL,
            params=params,
            headers=headers,
            timeout=30,
        )

        if response.status_code != 200:
            return []

        data = response.json()
        pages = data.get("query", {}).get("pages", {})

        results = []
        for page_id, page in pages.items():
            if page_id == "-1":
                continue

            imageinfo = page.get("imageinfo", [{}])[0]
            if not imageinfo:
                continue

            # Prefer thumbnail URL, fall back to full URL
            thumb_url = imageinfo.get("thumburl", imageinfo.get("url", ""))

            # Filter to only images (not PDFs, etc)
            mime = imageinfo.get("mime", "")
            if not mime.startswith("image/"):
                continue

            results.append({
                "title": page.get("title", "").replace("File:", ""),
                "url": thumb_url,
                "width": imageinfo.get("thumbwidth", imageinfo.get("width", 0)),
                "height": imageinfo.get("thumbheight", imageinfo.get("height", 0)),
            })

        return results

    except Exception as e:
        logger.debug(f"Commons search error for '{query}': {e}")
        return []


def search_commons_for_site(site_name: str) -> str | None:
    """
    Search Commons for an image of a specific site.

    Tries multiple search strategies.
    """
    # Clean up site name
    clean_name = site_name.strip()

    # Try exact name first
    results = search_commons_images(clean_name, limit=3)
    if results:
        return results[0]["url"]

    # Try with "archaeological site" suffix
    results = search_commons_images(f"{clean_name} archaeological", limit=3)
    if results:
        return results[0]["url"]

    # Try with "ruins" suffix
    results = search_commons_images(f"{clean_name} ruins", limit=3)
    if results:
        return results[0]["url"]

    return None


# =============================================================================
# Database Matching & Updates
# =============================================================================

def get_sites_without_images(session: Session, limit: int = None) -> list[tuple]:
    """Get sites that don't have thumbnail_url set."""
    query = text("""
        SELECT id, name, lat, lon
        FROM unified_sites
        WHERE thumbnail_url IS NULL
        ORDER BY name
        LIMIT :limit
    """)

    result = session.execute(query, {"limit": limit or 1000000})
    return list(result.fetchall())


def match_wikidata_to_sites(
    session: Session,
    wikidata_results: list[WikidataResult],
    coord_threshold: float = COORD_THRESHOLD,
) -> list[SiteMatch]:
    """
    Match Wikidata results to existing sites by coordinates.

    Uses spatial proximity matching.
    """
    matches = []

    # Build spatial index of Wikidata results
    wikidata_by_cell = {}
    for wd in wikidata_results:
        # Round to ~5km cells
        cell = (round(wd.lat / coord_threshold), round(wd.lon / coord_threshold))
        if cell not in wikidata_by_cell:
            wikidata_by_cell[cell] = []
        wikidata_by_cell[cell].append(wd)

    logger.info(f"Built index with {len(wikidata_by_cell)} cells")

    # Get all sites without images
    sites = get_sites_without_images(session, limit=None)
    logger.info(f"Matching against {len(sites)} sites without images...")

    matched_count = 0
    for site_id, site_name, lat, lon in sites:
        cell = (round(lat / coord_threshold), round(lon / coord_threshold))

        # Check this cell and neighbors
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                check_cell = (cell[0] + dx, cell[1] + dy)
                candidates = wikidata_by_cell.get(check_cell, [])

                for wd in candidates:
                    # Check if within threshold
                    dist = ((wd.lat - lat)**2 + (wd.lon - lon)**2)**0.5
                    if dist < coord_threshold:
                        matches.append(SiteMatch(
                            site_id=str(site_id),
                            site_name=site_name,
                            image_url=wd.image_url,
                            source="wikidata",
                        ))
                        matched_count += 1
                        break
                else:
                    continue
                break
            else:
                continue
            break

    logger.info(f"Matched {matched_count} sites to Wikidata images")
    return matches


def update_site_thumbnails(session: Session, matches: list[SiteMatch]) -> int:
    """Update thumbnail_url for matched sites."""
    updated = 0

    for i in range(0, len(matches), DB_UPDATE_BATCH_SIZE):
        batch = matches[i:i + DB_UPDATE_BATCH_SIZE]

        for match in batch:
            try:
                session.execute(
                    update(UnifiedSite)
                    .where(UnifiedSite.id == match.site_id)
                    .values(thumbnail_url=match.image_url)
                )
                updated += 1
            except Exception as e:
                logger.debug(f"Update error for {match.site_id}: {e}")

        session.commit()
        logger.info(f"  Updated {updated}/{len(matches)} sites")

    return updated


# =============================================================================
# Commons Fallback Search
# =============================================================================

def search_commons_fallback(
    session: Session,
    limit: int = 10000,
    skip_existing: bool = True,
) -> int:
    """
    Search Commons for images of sites that don't have one yet.

    This is slower than Wikidata matching but can find additional images.
    """
    sites = get_sites_without_images(session, limit=limit)
    logger.info(f"Searching Commons for {len(sites)} sites...")

    updated = 0

    for i, (site_id, site_name, _lat, _lon) in enumerate(sites):
        if i % 100 == 0:
            logger.info(f"  Progress: {i}/{len(sites)} ({updated} found)")

        image_url = search_commons_for_site(site_name)

        if image_url:
            try:
                session.execute(
                    update(UnifiedSite)
                    .where(UnifiedSite.id == site_id)
                    .values(thumbnail_url=image_url)
                )
                updated += 1

                if updated % 50 == 0:
                    session.commit()

            except Exception as e:
                logger.debug(f"Update error: {e}")

        time.sleep(COMMONS_DELAY)

    session.commit()
    logger.info(f"Found {updated} images via Commons search")
    return updated


# =============================================================================
# Statistics
# =============================================================================

def get_image_stats(session: Session) -> dict:
    """Get statistics about image coverage."""
    result = session.execute(text("""
        SELECT
            COUNT(*) as total,
            COUNT(thumbnail_url) as with_image,
            COUNT(*) - COUNT(thumbnail_url) as without_image,
            ROUND(100.0 * COUNT(thumbnail_url) / COUNT(*), 2) as coverage_pct
        FROM unified_sites
    """))
    row = result.fetchone()

    # By source
    by_source = session.execute(text("""
        SELECT
            source_id,
            COUNT(*) as total,
            COUNT(thumbnail_url) as with_image,
            ROUND(100.0 * COUNT(thumbnail_url) / COUNT(*), 2) as coverage_pct
        FROM unified_sites
        GROUP BY source_id
        ORDER BY total DESC
    """))

    return {
        "total_sites": row[0],
        "with_image": row[1],
        "without_image": row[2],
        "coverage_pct": row[3],
        "by_source": [
            {"source": r[0], "total": r[1], "with_image": r[2], "coverage_pct": r[3]}
            for r in by_source.fetchall()
        ]
    }


def print_stats(stats: dict):
    """Print image coverage statistics."""
    print("\n" + "=" * 60)
    print("IMAGE COVERAGE STATISTICS")
    print("=" * 60)
    print(f"Total sites:    {stats['total_sites']:,}")
    print(f"With image:     {stats['with_image']:,}")
    print(f"Without image:  {stats['without_image']:,}")
    print(f"Coverage:       {stats['coverage_pct']}%")
    print("\nBy Source:")
    print("-" * 60)
    print(f"{'Source':<25} {'Total':>10} {'Images':>10} {'Coverage':>10}")
    print("-" * 60)
    for src in stats['by_source']:
        print(f"{src['source']:<25} {src['total']:>10,} {src['with_image']:>10,} {src['coverage_pct']:>9}%")
    print("=" * 60 + "\n")


# =============================================================================
# Main Entry Point
# =============================================================================

def run_wikimedia_fallback(
    limit: int = None,
    wikidata_only: bool = False,
    commons_only: bool = False,
    stats_only: bool = False,
):
    """
    Run the Wikimedia image fallback pipeline.

    Args:
        limit: Maximum number of sites to process
        wikidata_only: Only use Wikidata SPARQL (faster)
        commons_only: Only use Commons search (slower but finds more)
        stats_only: Just print statistics
    """
    with get_session() as session:
        # Print initial stats
        stats = get_image_stats(session)
        print_stats(stats)

        if stats_only:
            return stats

        total_updated = 0

        # Phase 1: Wikidata SPARQL matching
        if not commons_only:
            logger.info("Phase 1: Wikidata SPARQL matching...")
            wikidata_results = list(fetch_wikidata_images(limit=limit or 100000))

            if wikidata_results:
                matches = match_wikidata_to_sites(session, wikidata_results)
                if matches:
                    updated = update_site_thumbnails(session, matches)
                    total_updated += updated
                    logger.info(f"Wikidata: Updated {updated} sites")

        # Phase 2: Commons search fallback
        if not wikidata_only:
            logger.info("Phase 2: Commons search fallback...")
            commons_limit = min(limit or 10000, 10000)  # Cap Commons searches
            updated = search_commons_fallback(session, limit=commons_limit)
            total_updated += updated

        # Print final stats
        stats = get_image_stats(session)
        print_stats(stats)

        logger.info(f"Total images added: {total_updated}")
        return stats


def main():
    parser = argparse.ArgumentParser(
        description="Fetch images from Wikimedia Commons/Wikidata for archaeological sites"
    )
    parser.add_argument(
        "--limit", "-l", type=int, default=None,
        help="Maximum number of sites to process"
    )
    parser.add_argument(
        "--wikidata-only", action="store_true",
        help="Only use Wikidata SPARQL (faster)"
    )
    parser.add_argument(
        "--commons-only", action="store_true",
        help="Only use Commons search (slower but finds more)"
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Just print statistics"
    )

    args = parser.parse_args()

    run_wikimedia_fallback(
        limit=args.limit,
        wikidata_only=args.wikidata_only,
        commons_only=args.commons_only,
        stats_only=args.stats,
    )


if __name__ == "__main__":
    main()
