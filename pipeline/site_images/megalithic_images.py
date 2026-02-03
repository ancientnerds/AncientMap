"""
Megalithic Portal image fetcher.

Fetches images from the Megalithic Portal GeoRSS API for existing sites.
The KMZ file used by the main ingester doesn't include images, so this
script enriches the database with images from the website.

API: http://www.megalithic.co.uk/georss.php?long={lon}&lat={lat}

Usage:
    python -m pipeline.site_images.megalithic_images
    python -m pipeline.site_images.megalithic_images --limit 1000
    python -m pipeline.site_images.megalithic_images --stats
"""

import argparse
import re
import time
import xml.etree.ElementTree as ET

from loguru import logger
from sqlalchemy import text, update
from sqlalchemy.orm import Session

from pipeline.database import UnifiedSite, get_session
from pipeline.utils.http import RateLimitError, fetch_with_retry

# =============================================================================
# Configuration
# =============================================================================

# GeoRSS API endpoint
GEORSS_API_URL = "http://www.megalithic.co.uk/georss.php"

# Rate limiting
REQUEST_DELAY = 1.0  # Be respectful to their server

# Search radius (in arbitrary units used by the API, ~10 is good)
SEARCH_RADIUS = 5

# Batch sizes
DB_UPDATE_BATCH_SIZE = 100

# =============================================================================
# GeoRSS Parsing
# =============================================================================

def fetch_georss(lat: float, lon: float) -> str | None:
    """
    Fetch GeoRSS feed for a location.

    Args:
        lat: Latitude
        lon: Longitude

    Returns:
        XML content or None
    """
    params = {
        "lat": f"{lat:.6f}",
        "long": f"{lon:.6f}",
        "radius": SEARCH_RADIUS,
    }

    headers = {
        "User-Agent": "AncientNerds/1.0 (Archaeological Research Platform)",
    }

    try:
        response = fetch_with_retry(
            GEORSS_API_URL,
            params=params,
            headers=headers,
            timeout=30,
        )

        if response.status_code == 200:
            return response.text
        else:
            logger.debug(f"GeoRSS fetch failed: {response.status_code}")
            return None

    except RateLimitError:
        logger.warning("Rate limited, waiting 60s...")
        time.sleep(60)
        return None
    except Exception as e:
        logger.debug(f"GeoRSS fetch error: {e}")
        return None


def parse_georss(xml_content: str) -> list[dict]:
    """
    Parse GeoRSS XML and extract site info including images.

    Args:
        xml_content: Raw XML string

    Returns:
        List of site dicts with image URLs
    """
    sites = []

    try:
        root = ET.fromstring(xml_content)

        # GeoRSS/RSS namespaces
        namespaces = {
            'georss': 'http://www.georss.org/georss',
            'media': 'http://search.yahoo.com/mrss/',
        }

        # Find all items
        for item in root.findall('.//item'):
            site = {}

            # Get title
            title_elem = item.find('title')
            if title_elem is not None:
                site['name'] = title_elem.text

            # Get link (to extract site ID)
            link_elem = item.find('link')
            if link_elem is not None:
                site['link'] = link_elem.text
                # Extract site ID from URL
                match = re.search(r'sid=(\d+)', link_elem.text or '')
                if match:
                    site['id'] = match.group(1)

            # Get coordinates
            point_elem = item.find('.//georss:point', namespaces)
            if point_elem is None:
                # Try without namespace
                for child in item.iter():
                    if child.tag.endswith('point'):
                        point_elem = child
                        break

            if point_elem is not None and point_elem.text:
                try:
                    lat, lon = point_elem.text.strip().split()
                    site['lat'] = float(lat)
                    site['lon'] = float(lon)
                except (ValueError, IndexError):
                    pass

            # Get image/thumbnail from various sources
            # Try media:thumbnail
            thumb_elem = item.find('.//media:thumbnail', namespaces)
            if thumb_elem is not None:
                site['thumbnail'] = thumb_elem.get('url')

            # Try media:content
            if 'thumbnail' not in site:
                media_elem = item.find('.//media:content', namespaces)
                if media_elem is not None:
                    site['thumbnail'] = media_elem.get('url')

            # Try enclosure (common RSS image element)
            if 'thumbnail' not in site:
                enclosure = item.find('enclosure')
                if enclosure is not None and enclosure.get('type', '').startswith('image'):
                    site['thumbnail'] = enclosure.get('url')

            # Try description for image URLs
            if 'thumbnail' not in site:
                desc_elem = item.find('description')
                if desc_elem is not None and desc_elem.text:
                    # Look for img src in HTML description
                    img_match = re.search(r'<img[^>]+src="([^"]+)"', desc_elem.text)
                    if img_match:
                        site['thumbnail'] = img_match.group(1)

            if site.get('id') or (site.get('lat') and site.get('lon')):
                sites.append(site)

    except ET.ParseError as e:
        logger.debug(f"XML parse error: {e}")

    return sites


# =============================================================================
# Database Operations
# =============================================================================

def get_megalithic_sites_without_images(session: Session, limit: int = None) -> list[tuple]:
    """Get Megalithic Portal sites without thumbnail_url."""
    query = text("""
        SELECT id, source_record_id, name, lat, lon
        FROM unified_sites
        WHERE source_id = 'megalithic_portal'
          AND thumbnail_url IS NULL
        ORDER BY name
        LIMIT :limit
    """)

    result = session.execute(query, {"limit": limit or 1000000})
    return list(result.fetchall())


def update_site_thumbnail(session: Session, site_id: str, thumbnail_url: str) -> bool:
    """Update thumbnail_url for a site."""
    try:
        session.execute(
            update(UnifiedSite)
            .where(UnifiedSite.id == site_id)
            .values(thumbnail_url=thumbnail_url)
        )
        return True
    except Exception as e:
        logger.debug(f"Update error: {e}")
        return False


# =============================================================================
# Main Processing
# =============================================================================

def fetch_images_for_megalithic_sites(
    session: Session,
    limit: int = None,
) -> int:
    """
    Fetch images from GeoRSS API for Megalithic Portal sites.

    Args:
        session: Database session
        limit: Maximum sites to process

    Returns:
        Number of sites updated
    """
    sites = get_megalithic_sites_without_images(session, limit)
    logger.info(f"Found {len(sites)} Megalithic Portal sites without images")

    if not sites:
        return 0

    updated = 0
    failed = 0

    for i, (site_id, source_record_id, _name, lat, lon) in enumerate(sites):
        if i % 50 == 0:
            logger.info(f"Progress: {i}/{len(sites)} ({updated} images found)")

        # Fetch GeoRSS for this location
        xml_content = fetch_georss(lat, lon)
        if not xml_content:
            failed += 1
            time.sleep(REQUEST_DELAY)
            continue

        # Parse and find matching site
        georss_sites = parse_georss(xml_content)

        # Find best match by ID or coordinates
        best_match = None
        for gs in georss_sites:
            # Match by Megalithic Portal ID
            if gs.get('id') == source_record_id:
                best_match = gs
                break

            # Match by proximity (within ~0.001 degrees = ~100m)
            if gs.get('lat') and gs.get('lon'):
                dist = ((gs['lat'] - lat)**2 + (gs['lon'] - lon)**2)**0.5
                if dist < 0.001:
                    if not best_match or dist < best_match.get('_dist', float('inf')):
                        gs['_dist'] = dist
                        best_match = gs

        # Update if we found an image
        if best_match and best_match.get('thumbnail'):
            if update_site_thumbnail(session, str(site_id), best_match['thumbnail']):
                updated += 1

                if updated % DB_UPDATE_BATCH_SIZE == 0:
                    session.commit()
                    logger.info(f"  Committed {updated} updates")

        time.sleep(REQUEST_DELAY)

    session.commit()
    logger.info(f"Updated {updated} sites with images ({failed} API failures)")
    return updated


def get_stats(session: Session) -> dict:
    """Get image statistics for Megalithic Portal sites."""
    result = session.execute(text("""
        SELECT
            COUNT(*) as total,
            COUNT(thumbnail_url) as with_image,
            COUNT(*) - COUNT(thumbnail_url) as without_image,
            ROUND(100.0 * COUNT(thumbnail_url) / NULLIF(COUNT(*), 0), 2) as coverage_pct
        FROM unified_sites
        WHERE source_id = 'megalithic_portal'
    """))
    row = result.fetchone()

    return {
        "source": "megalithic_portal",
        "total": row[0],
        "with_image": row[1],
        "without_image": row[2],
        "coverage_pct": row[3],
    }


def print_stats(stats: dict):
    """Print statistics."""
    print("\n" + "=" * 60)
    print("MEGALITHIC PORTAL IMAGE COVERAGE")
    print("=" * 60)
    print(f"Total sites:    {stats['total']:,}")
    print(f"With image:     {stats['with_image']:,}")
    print(f"Without image:  {stats['without_image']:,}")
    print(f"Coverage:       {stats['coverage_pct']}%")
    print("=" * 60 + "\n")


# =============================================================================
# Main Entry Point
# =============================================================================

def run_megalithic_images(limit: int = None, stats_only: bool = False):
    """Run Megalithic Portal image fetching."""
    with get_session() as session:
        stats = get_stats(session)
        print_stats(stats)

        if stats_only:
            return stats

        if stats['without_image'] == 0:
            logger.info("All Megalithic Portal sites have images!")
            return stats

        updated = fetch_images_for_megalithic_sites(session, limit)
        logger.info(f"Total updated: {updated}")

        # Final stats
        stats = get_stats(session)
        print_stats(stats)

        return stats


def main():
    parser = argparse.ArgumentParser(
        description="Fetch images for Megalithic Portal sites from GeoRSS API"
    )
    parser.add_argument(
        "--limit", "-l", type=int, default=None,
        help="Maximum sites to process"
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Print statistics only"
    )

    args = parser.parse_args()

    run_megalithic_images(
        limit=args.limit,
        stats_only=args.stats,
    )


if __name__ == "__main__":
    main()
