#!/usr/bin/env python3
"""
Data Quality Report Generator for ANCIENT NERDS.

Generates comprehensive reports on data quality across all sources:
- Per-source field coverage percentages
- Coordinate validity checks
- Sample records for inspection
- Recommendations for fixes

Usage:
    python scripts/verify_data_quality.py
    python scripts/verify_data_quality.py --source ncei_earthquakes
    python scripts/verify_data_quality.py --json > quality_report.json
"""

import argparse
import json
import sys
from typing import Dict, List, Optional, Any
from collections import defaultdict

from loguru import logger
from sqlalchemy import text

from pipeline.database import get_session


# Fields to check for coverage
COVERAGE_FIELDS = [
    "name",
    "lat",
    "lon",
    "site_type",
    "period_start",
    "period_end",
    "period_name",
    "country",
    "description",
    "thumbnail_url",
    "source_url",
    "raw_data",
]


def get_all_sources(session) -> List[str]:
    """Get list of all source IDs in the database."""
    result = session.execute(text("""
        SELECT DISTINCT source_id
        FROM unified_sites
        ORDER BY source_id
    """))
    return [row[0] for row in result]


def count_records(session, source_id: str) -> int:
    """Count total records for a source."""
    result = session.execute(
        text("SELECT COUNT(*) FROM unified_sites WHERE source_id = :sid"),
        {"sid": source_id}
    )
    return result.scalar() or 0


def count_valid_coords(session, source_id: str) -> int:
    """Count records with valid coordinates."""
    result = session.execute(
        text("""
            SELECT COUNT(*)
            FROM unified_sites
            WHERE source_id = :sid
              AND lat IS NOT NULL
              AND lon IS NOT NULL
              AND lat BETWEEN -90 AND 90
              AND lon BETWEEN -180 AND 180
        """),
        {"sid": source_id}
    )
    return result.scalar() or 0


def count_with_field(session, source_id: str, field: str) -> int:
    """Count records with a non-null, non-empty field."""
    # Handle JSONB raw_data field specially
    if field == "raw_data":
        result = session.execute(
            text("""
                SELECT COUNT(*)
                FROM unified_sites
                WHERE source_id = :sid
                  AND raw_data IS NOT NULL
                  AND raw_data != '{}'::jsonb
            """),
            {"sid": source_id}
        )
    elif field in ["name", "site_type", "period_name", "country", "description", "source_url", "thumbnail_url"]:
        # String fields - check for non-empty
        result = session.execute(
            text(f"""
                SELECT COUNT(*)
                FROM unified_sites
                WHERE source_id = :sid
                  AND {field} IS NOT NULL
                  AND {field} != ''
            """),
            {"sid": source_id}
        )
    else:
        # Numeric fields
        result = session.execute(
            text(f"""
                SELECT COUNT(*)
                FROM unified_sites
                WHERE source_id = :sid
                  AND {field} IS NOT NULL
            """),
            {"sid": source_id}
        )
    return result.scalar() or 0


def get_sample_records(session, source_id: str, limit: int = 3) -> List[Dict]:
    """Get sample records for a source."""
    result = session.execute(
        text("""
            SELECT
                id::text,
                name,
                lat,
                lon,
                site_type,
                period_start,
                country,
                description,
                source_url
            FROM unified_sites
            WHERE source_id = :sid
            ORDER BY RANDOM()
            LIMIT :limit
        """),
        {"sid": source_id, "limit": limit}
    )

    samples = []
    for row in result:
        samples.append({
            "id": row.id,
            "name": row.name[:50] if row.name else None,
            "lat": row.lat,
            "lon": row.lon,
            "site_type": row.site_type,
            "period_start": row.period_start,
            "country": row.country,
            "description": (row.description[:100] + "...") if row.description and len(row.description) > 100 else row.description,
            "source_url": row.source_url[:50] + "..." if row.source_url and len(row.source_url) > 50 else row.source_url,
        })
    return samples


def get_site_type_distribution(session, source_id: str, limit: int = 10) -> Dict[str, int]:
    """Get distribution of site types for a source."""
    result = session.execute(
        text("""
            SELECT site_type, COUNT(*) as cnt
            FROM unified_sites
            WHERE source_id = :sid
            GROUP BY site_type
            ORDER BY cnt DESC
            LIMIT :limit
        """),
        {"sid": source_id, "limit": limit}
    )
    return {row.site_type or "(null)": row.cnt for row in result}


def generate_source_report(session, source_id: str) -> Dict[str, Any]:
    """Generate quality report for a single source."""
    total = count_records(session, source_id)
    if total == 0:
        return {"source": source_id, "total": 0, "error": "No records found"}

    report = {
        "source": source_id,
        "total": total,
        "coverage": {},
        "coverage_pct": {},
    }

    # Count coverage for each field
    report["coverage"]["valid_coords"] = count_valid_coords(session, source_id)
    report["coverage_pct"]["valid_coords"] = round(100 * report["coverage"]["valid_coords"] / total, 1)

    for field in COVERAGE_FIELDS:
        count = count_with_field(session, source_id, field)
        report["coverage"][field] = count
        report["coverage_pct"][field] = round(100 * count / total, 1)

    # Get sample records
    report["samples"] = get_sample_records(session, source_id)

    # Get site type distribution
    report["site_types"] = get_site_type_distribution(session, source_id)

    return report


def generate_recommendations(reports: List[Dict]) -> List[str]:
    """Generate recommendations based on quality reports."""
    recommendations = []

    for report in reports:
        source = report["source"]
        total = report.get("total", 0)
        if total == 0:
            continue

        coverage = report.get("coverage_pct", {})

        # Check country coverage
        country_pct = coverage.get("country", 0)
        if country_pct < 50:
            recommendations.append(
                f"- {source}: Add country enrichment ({country_pct}% -> ~100% via reverse geocoding)"
            )

        # Check period coverage
        period_pct = coverage.get("period_start", 0)
        if period_pct < 50:
            recommendations.append(
                f"- {source}: Review period parsing ({period_pct}% coverage) - many sites excluded from age filter"
            )

        # Check description coverage
        desc_pct = coverage.get("description", 0)
        if desc_pct < 20:
            recommendations.append(
                f"- {source}: Consider adding descriptions ({desc_pct}% coverage)"
            )

        # Check site_type coverage
        type_pct = coverage.get("site_type", 0)
        if type_pct < 90:
            recommendations.append(
                f"- {source}: Improve site_type extraction ({type_pct}% coverage)"
            )

    return recommendations


def print_table(reports: List[Dict]):
    """Print a formatted table of quality stats."""
    # Header
    print("\n" + "=" * 100)
    print(f"{'Source':<25} {'Total':>10} {'Coords':>10} {'Country':>10} {'Period':>10} {'Type':>10} {'Desc':>10}")
    print("=" * 100)

    # Sort by total descending
    sorted_reports = sorted(reports, key=lambda r: r.get("total", 0), reverse=True)

    for report in sorted_reports:
        source = report["source"][:24]
        total = report.get("total", 0)
        if total == 0:
            print(f"{source:<25} {'(no data)':>10}")
            continue

        coverage = report.get("coverage_pct", {})
        coords = f"{coverage.get('valid_coords', 0):.0f}%"
        country = f"{coverage.get('country', 0):.0f}%"
        period = f"{coverage.get('period_start', 0):.0f}%"
        site_type = f"{coverage.get('site_type', 0):.0f}%"
        desc = f"{coverage.get('description', 0):.0f}%"

        print(f"{source:<25} {total:>10,} {coords:>10} {country:>10} {period:>10} {site_type:>10} {desc:>10}")

    print("=" * 100)


def print_detailed_report(report: Dict):
    """Print detailed report for a single source."""
    print(f"\n{'=' * 60}")
    print(f"Source: {report['source']}")
    print(f"Total Records: {report.get('total', 0):,}")
    print("=" * 60)

    coverage = report.get("coverage_pct", {})
    print("\nField Coverage:")
    for field in ["valid_coords"] + COVERAGE_FIELDS:
        pct = coverage.get(field, 0)
        bar = "#" * int(pct / 5) + "-" * (20 - int(pct / 5))
        print(f"  {field:<20} [{bar}] {pct:>5.1f}%")

    if report.get("site_types"):
        print("\nSite Type Distribution (top 10):")
        for site_type, count in list(report["site_types"].items())[:10]:
            print(f"  {site_type:<30} {count:>10,}")

    if report.get("samples"):
        print("\nSample Records:")
        for i, sample in enumerate(report["samples"], 1):
            print(f"\n  [{i}] {sample.get('name', 'Unnamed')}")
            print(f"      Coords: ({sample.get('lat')}, {sample.get('lon')})")
            print(f"      Type: {sample.get('site_type', '-')}")
            print(f"      Period: {sample.get('period_start', '-')}")
            print(f"      Country: {sample.get('country', '-')}")


def main():
    parser = argparse.ArgumentParser(description="Data Quality Report Generator")
    parser.add_argument("--source", "-s", help="Analyze a specific source only")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--detailed", "-d", action="store_true", help="Show detailed reports")
    parser.add_argument("--samples", type=int, default=3, help="Number of sample records per source")

    args = parser.parse_args()

    logger.info("Generating data quality report...")

    with get_session() as session:
        if args.source:
            sources = [args.source]
        else:
            sources = get_all_sources(session)

        if not sources:
            logger.warning("No sources found in database")
            return

        logger.info(f"Analyzing {len(sources)} sources...")

        reports = []
        for source_id in sources:
            logger.info(f"  Processing {source_id}...")
            report = generate_source_report(session, source_id)
            reports.append(report)

        # Generate recommendations
        recommendations = generate_recommendations(reports)

        if args.json:
            # Output as JSON
            output = {
                "reports": reports,
                "recommendations": recommendations,
                "summary": {
                    "total_sources": len(reports),
                    "total_records": sum(r.get("total", 0) for r in reports),
                }
            }
            print(json.dumps(output, indent=2, default=str))
        else:
            # Print formatted table
            print_table(reports)

            # Print detailed reports if requested
            if args.detailed:
                for report in reports:
                    print_detailed_report(report)

            # Print recommendations
            if recommendations:
                print("\n" + "=" * 60)
                print("RECOMMENDATIONS")
                print("=" * 60)
                for rec in recommendations:
                    print(rec)

            # Summary
            total_records = sum(r.get("total", 0) for r in reports)
            print("\n" + "-" * 60)
            print(f"Total: {len(reports)} sources, {total_records:,} records")
            print("-" * 60)


if __name__ == "__main__":
    main()
