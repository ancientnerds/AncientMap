"""
Batch updater for site images from all sources.

Orchestrates image acquisition from multiple sources in priority order:
1. Source-native images (already in database from ingesters)
2. Wikidata SPARQL (sites with P18 image property)
3. Wikimedia Commons search (fallback)

Note: Flickr images are now fetched on-demand in the frontend.

Usage:
    python -m pipeline.site_images.batch_updater --all
    python -m pipeline.site_images.batch_updater --source wikidata
    python -m pipeline.site_images.batch_updater --stats
"""

import argparse
from datetime import datetime

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from pipeline.database import get_session

# =============================================================================
# Image Source Priority
# =============================================================================

IMAGE_SOURCES = [
    {
        "id": "source_native",
        "name": "Source Native Images",
        "description": "Images from original data sources (Met Museum, Europeana, etc.)",
        "priority": 1,
        "method": None,  # Already populated by ingesters
    },
    {
        "id": "wikidata",
        "name": "Wikidata P18",
        "description": "Archaeological sites with image property in Wikidata",
        "priority": 2,
        "method": "run_wikidata",
    },
    {
        "id": "commons_search",
        "name": "Commons Search",
        "description": "Wikimedia Commons search by site name",
        "priority": 3,
        "method": "run_commons_search",
    },
]


# =============================================================================
# Statistics Functions
# =============================================================================

def get_comprehensive_stats(session: Session) -> dict:
    """Get comprehensive image coverage statistics."""

    # Overall stats
    overall = session.execute(text("""
        SELECT
            COUNT(*) as total,
            COUNT(thumbnail_url) as with_image,
            COUNT(*) - COUNT(thumbnail_url) as without_image,
            ROUND(100.0 * COUNT(thumbnail_url) / NULLIF(COUNT(*), 0), 2) as coverage_pct
        FROM unified_sites
    """)).fetchone()

    # By source
    by_source = session.execute(text("""
        SELECT
            source_id,
            COUNT(*) as total,
            COUNT(thumbnail_url) as with_image,
            ROUND(100.0 * COUNT(thumbnail_url) / NULLIF(COUNT(*), 0), 2) as coverage_pct
        FROM unified_sites
        GROUP BY source_id
        ORDER BY total DESC
    """)).fetchall()

    # By site type (top 20)
    by_type = session.execute(text("""
        SELECT
            COALESCE(site_type, 'unknown') as site_type,
            COUNT(*) as total,
            COUNT(thumbnail_url) as with_image,
            ROUND(100.0 * COUNT(thumbnail_url) / NULLIF(COUNT(*), 0), 2) as coverage_pct
        FROM unified_sites
        GROUP BY site_type
        ORDER BY total DESC
        LIMIT 20
    """)).fetchall()

    # By country (top 20)
    by_country = session.execute(text("""
        SELECT
            COALESCE(country, 'unknown') as country,
            COUNT(*) as total,
            COUNT(thumbnail_url) as with_image,
            ROUND(100.0 * COUNT(thumbnail_url) / NULLIF(COUNT(*), 0), 2) as coverage_pct
        FROM unified_sites
        GROUP BY country
        ORDER BY total DESC
        LIMIT 20
    """)).fetchall()

    # Sites with most potential (large sources with low coverage)
    improvement_potential = session.execute(text("""
        SELECT
            source_id,
            COUNT(*) as total,
            COUNT(thumbnail_url) as with_image,
            COUNT(*) - COUNT(thumbnail_url) as without_image,
            ROUND(100.0 * COUNT(thumbnail_url) / NULLIF(COUNT(*), 0), 2) as coverage_pct
        FROM unified_sites
        GROUP BY source_id
        HAVING COUNT(*) > 1000 AND COUNT(thumbnail_url) < COUNT(*) * 0.5
        ORDER BY (COUNT(*) - COUNT(thumbnail_url)) DESC
        LIMIT 10
    """)).fetchall()

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "overall": {
            "total": overall[0],
            "with_image": overall[1],
            "without_image": overall[2],
            "coverage_pct": overall[3],
        },
        "by_source": [
            {"source": r[0], "total": r[1], "with_image": r[2], "coverage_pct": r[3]}
            for r in by_source
        ],
        "by_type": [
            {"type": r[0], "total": r[1], "with_image": r[2], "coverage_pct": r[3]}
            for r in by_type
        ],
        "by_country": [
            {"country": r[0], "total": r[1], "with_image": r[2], "coverage_pct": r[3]}
            for r in by_country
        ],
        "improvement_potential": [
            {"source": r[0], "total": r[1], "with_image": r[2], "without_image": r[3], "coverage_pct": r[4]}
            for r in improvement_potential
        ],
    }


def print_stats(stats: dict):
    """Print comprehensive statistics."""
    print("\n" + "=" * 70)
    print("SITE IMAGE COVERAGE STATISTICS")
    print(f"Generated: {stats['timestamp']}")
    print("=" * 70)

    o = stats['overall']
    print("\nOVERALL:")
    print(f"  Total sites:    {o['total']:>10,}")
    print(f"  With image:     {o['with_image']:>10,}")
    print(f"  Without image:  {o['without_image']:>10,}")
    print(f"  Coverage:       {o['coverage_pct']:>10}%")

    print("\n" + "-" * 70)
    print("BY SOURCE:")
    print(f"{'Source':<30} {'Total':>10} {'Images':>10} {'Coverage':>10}")
    print("-" * 70)
    for src in stats['by_source']:
        print(f"{src['source']:<30} {src['total']:>10,} {src['with_image']:>10,} {src['coverage_pct']:>9}%")

    print("\n" + "-" * 70)
    print("BY SITE TYPE (Top 20):")
    print(f"{'Type':<30} {'Total':>10} {'Images':>10} {'Coverage':>10}")
    print("-" * 70)
    for t in stats['by_type']:
        print(f"{t['type'][:30]:<30} {t['total']:>10,} {t['with_image']:>10,} {t['coverage_pct']:>9}%")

    print("\n" + "-" * 70)
    print("BY COUNTRY (Top 20):")
    print(f"{'Country':<30} {'Total':>10} {'Images':>10} {'Coverage':>10}")
    print("-" * 70)
    for c in stats['by_country']:
        print(f"{c['country'][:30]:<30} {c['total']:>10,} {c['with_image']:>10,} {c['coverage_pct']:>9}%")

    if stats['improvement_potential']:
        print("\n" + "-" * 70)
        print("IMPROVEMENT POTENTIAL (Large sources with <50% coverage):")
        print(f"{'Source':<30} {'Missing':>10} {'Total':>10} {'Current':>10}")
        print("-" * 70)
        for p in stats['improvement_potential']:
            print(f"{p['source']:<30} {p['without_image']:>10,} {p['total']:>10,} {p['coverage_pct']:>9}%")

    print("=" * 70 + "\n")


# =============================================================================
# Source-Specific Runners
# =============================================================================

def run_wikidata(session: Session, limit: int = None) -> int:
    """Run Wikidata image fetching."""
    from pipeline.site_images.wikimedia_fallback import run_wikimedia_fallback

    logger.info("Running Wikidata image fetch...")
    stats = run_wikimedia_fallback(
        limit=limit,
        wikidata_only=True,
        stats_only=False,
    )
    return stats.get("with_image", 0) if stats else 0


def run_commons_search(session: Session, limit: int = None) -> int:
    """Run Wikimedia Commons search fallback."""
    from pipeline.site_images.wikimedia_fallback import run_wikimedia_fallback

    logger.info("Running Commons search fallback...")
    stats = run_wikimedia_fallback(
        limit=limit or 10000,
        commons_only=True,
        stats_only=False,
    )
    return stats.get("with_image", 0) if stats else 0


def run_megalithic(session: Session, limit: int = None) -> int:
    """Run Megalithic Portal image fetching."""
    from pipeline.site_images.megalithic_images import run_megalithic_images

    logger.info("Running Megalithic Portal image fetch...")
    try:
        stats = run_megalithic_images(limit=limit, stats_only=False)
        return stats.get("with_image", 0) if stats else 0
    except Exception as e:
        logger.warning(f"Megalithic Portal failed: {e}")
        return 0


# =============================================================================
# Batch Update Orchestrator
# =============================================================================

def run_all_sources(
    sources: list[str] = None,
    limit: int = None,
    skip_existing: bool = True,
):
    """
    Run image acquisition from all specified sources.

    Args:
        sources: List of source IDs to run (or None for all)
        limit: Maximum sites to process per source
        skip_existing: Skip sites that already have images
    """
    source_methods = {
        "wikidata": run_wikidata,
        "megalithic": run_megalithic,
        "commons_search": run_commons_search,
    }

    if sources is None:
        sources = list(source_methods.keys())

    logger.info(f"Running image sources: {sources}")

    with get_session() as session:
        # Print initial stats
        stats = get_comprehensive_stats(session)
        print_stats(stats)

        results = {}
        for source_id in sources:
            if source_id not in source_methods:
                logger.warning(f"Unknown source: {source_id}")
                continue

            method = source_methods[source_id]
            logger.info(f"\n{'='*60}")
            logger.info(f"Running source: {source_id}")
            logger.info(f"{'='*60}")

            try:
                result = method(session, limit)
                results[source_id] = result
            except Exception as e:
                logger.error(f"Error running {source_id}: {e}")
                results[source_id] = 0

        # Print final stats
        stats = get_comprehensive_stats(session)
        print_stats(stats)

        # Summary
        print("\n" + "=" * 60)
        print("BATCH UPDATE COMPLETE")
        print("=" * 60)
        for source_id, result in results.items():
            print(f"  {source_id}: {result}")
        print("=" * 60 + "\n")


# =============================================================================
# Sample Sites for Quick Testing
# =============================================================================

def get_sample_sites(session: Session, count: int = 10) -> list[dict]:
    """Get sample sites without images for testing."""
    result = session.execute(text("""
        SELECT id, name, source_id, lat, lon
        FROM unified_sites
        WHERE thumbnail_url IS NULL
        ORDER BY RANDOM()
        LIMIT :count
    """), {"count": count})

    return [
        {"id": str(r[0]), "name": r[1], "source": r[2], "lat": r[3], "lon": r[4]}
        for r in result.fetchall()
    ]


def test_single_site(site_name: str):
    """Test image search for a single site name."""
    from pipeline.site_images.wikimedia_fallback import search_commons_for_site

    logger.info(f"Testing image search for: {site_name}")
    url = search_commons_for_site(site_name)
    if url:
        logger.info(f"Found: {url}")
    else:
        logger.info("No image found")
    return url


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Batch update site images from multiple sources"
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Run all image sources"
    )
    parser.add_argument(
        "--source", "-s", type=str,
        choices=["wikidata", "megalithic", "commons_search"],
        help="Run specific source only"
    )
    parser.add_argument(
        "--limit", "-l", type=int, default=None,
        help="Maximum sites to process per source"
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Print statistics only"
    )
    parser.add_argument(
        "--test", type=str, metavar="SITE_NAME",
        help="Test image search for a site name"
    )
    parser.add_argument(
        "--sample", type=int, metavar="COUNT",
        help="Show sample sites without images"
    )

    args = parser.parse_args()

    if args.stats:
        with get_session() as session:
            stats = get_comprehensive_stats(session)
            print_stats(stats)
        return

    if args.test:
        test_single_site(args.test)
        return

    if args.sample:
        with get_session() as session:
            samples = get_sample_sites(session, args.sample)
            print("\nSample sites without images:")
            for s in samples:
                print(f"  [{s['source']}] {s['name']} ({s['lat']:.2f}, {s['lon']:.2f})")
        return

    if args.all:
        run_all_sources(limit=args.limit)
    elif args.source:
        run_all_sources(sources=[args.source], limit=args.limit)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
