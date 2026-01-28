#!/usr/bin/env python3
"""
Test ingesters without database connection.

This script tests the fetch() and parse() methods of all ingesters
without requiring PostgreSQL. Useful for validating data sources work.

Usage:
    python scripts/test_ingesters.py [source]
    python scripts/test_ingesters.py pleiades
    python scripts/test_ingesters.py all
"""

import sys
from pathlib import Path
from datetime import datetime
import argparse

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from loguru import logger

# Configure logging
logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>")

console = Console()

# Import ingesters (without database)
from pipeline.ingesters.pleiades import PleiadesIngester
from pipeline.ingesters.unesco import UNESCOIngester
from pipeline.ingesters.geonames import GeoNamesIngester
from pipeline.ingesters.open_context import OpenContextIngester
from pipeline.ingesters.wikidata import WikidataIngester
from pipeline.ingesters.p3k14c import P3k14cIngester
from pipeline.ingesters.historic_england import HistoricEnglandIngester
from pipeline.ingesters.pastmap_scotland import PastMapScotlandIngester
from pipeline.ingesters.ireland_nms import IrelandNMSIngester
from pipeline.ingesters.arachne import ArachneIngester
from pipeline.ingesters.eamena import EAMENAIngester
from pipeline.ingesters.maeasam import MAEASaMIngester
from pipeline.ingesters.dinaa import DINAAIngester

INGESTERS = {
    "pleiades": (PleiadesIngester, "Pleiades - Mediterranean (38K sites)"),
    "unesco": (UNESCOIngester, "UNESCO World Heritage (1.2K sites)"),
    "geonames": (GeoNamesIngester, "GeoNames Archaeological (~50K sites) - LARGE DOWNLOAD"),
    "open_context": (OpenContextIngester, "Open Context (5M+ records) - SLOW"),
    "wikidata": (WikidataIngester, "Wikidata Archaeological (~500K sites) - SLOW"),
    "p3k14c": (P3k14cIngester, "P3k14c Radiocarbon (180K dates)"),
    "historic_england": (HistoricEnglandIngester, "Historic England (~20K monuments)"),
    "pastmap_scotland": (PastMapScotlandIngester, "PastMap Scotland (~8K sites)"),
    "ireland_nms": (IrelandNMSIngester, "Ireland NMS (~140K monuments)"),
    "arachne": (ArachneIngester, "Arachne/iDAI German (~200K records)"),
    "eamena": (EAMENAIngester, "EAMENA Middle East (338K sites) - MAY NEED API KEY"),
    "maeasam": (MAEASaMIngester, "MAEASaM Africa (~10K sites)"),
    "dinaa": (DINAAIngester, "DINAA North America (900K sites) - VERY SLOW"),
}

# Quick test sources (smaller, faster)
QUICK_SOURCES = ["pleiades", "unesco", "historic_england", "pastmap_scotland"]


def test_ingester(source_id: str, max_records: int = 100) -> dict:
    """
    Test a single ingester's fetch and parse methods.

    Returns dict with results.
    """
    ingester_class, description = INGESTERS[source_id]

    result = {
        "source": source_id,
        "description": description,
        "fetch_success": False,
        "parse_success": False,
        "records_parsed": 0,
        "sample_records": [],
        "error": None,
        "duration": 0,
    }

    start_time = datetime.now()

    try:
        # Create ingester without database session
        ingester = ingester_class(session=None)

        # Test fetch
        console.print(f"  [cyan]Fetching {source_id}...[/cyan]")
        raw_path = ingester.fetch()
        result["fetch_success"] = True
        result["raw_path"] = str(raw_path)
        console.print(f"  [green]OK - Fetched to {raw_path}[/green]")

        # Test parse (limit records for speed)
        console.print(f"  [cyan]Parsing (first {max_records} records)...[/cyan]")
        count = 0
        for site in ingester.parse(raw_path):
            count += 1
            if count <= 5:
                result["sample_records"].append({
                    "name": site.name,
                    "lat": site.lat,
                    "lon": site.lon,
                    "type": site.site_type,
                })
            if count >= max_records:
                break

        result["parse_success"] = True
        result["records_parsed"] = count
        console.print(f"  [green]OK - Parsed {count} records[/green]")

    except Exception as e:
        result["error"] = str(e)
        console.print(f"  [red]FAIL - Error: {e}[/red]")

    result["duration"] = (datetime.now() - start_time).total_seconds()
    return result


def main():
    parser = argparse.ArgumentParser(description="Test ingesters without database")
    parser.add_argument(
        "source",
        nargs="?",
        default="quick",
        choices=list(INGESTERS.keys()) + ["all", "quick"],
        help="Source to test (default: quick = small sources only)",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=100,
        help="Max records to parse per source (default: 100)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available sources",
    )
    args = parser.parse_args()

    if args.list:
        console.print("\n[bold]Available Data Sources[/bold]\n")
        table = Table()
        table.add_column("ID")
        table.add_column("Description")
        table.add_column("Quick Test")

        for source_id, (_, desc) in INGESTERS.items():
            quick = "Yes" if source_id in QUICK_SOURCES else ""
            table.add_row(source_id, desc, quick)

        console.print(table)
        console.print("\n[dim]Use 'quick' to test only fast sources[/dim]")
        return

    console.print("\n[bold blue]============================================================[/bold blue]")
    console.print("[bold blue]  ANCIENT NERDS - Ingester Test (No Database Required)  [/bold blue]")
    console.print("[bold blue]============================================================[/bold blue]\n")

    # Determine which sources to test
    if args.source == "all":
        sources = list(INGESTERS.keys())
        console.print("[yellow]WARNING: Testing ALL sources - this may take a long time![/yellow]\n")
    elif args.source == "quick":
        sources = QUICK_SOURCES
        console.print("[cyan]Testing quick sources only (pleiades, unesco, historic_england, pastmap_scotland)[/cyan]\n")
    else:
        sources = [args.source]

    results = []

    for source_id in sources:
        console.print(f"\n[bold]>> Testing: {source_id}[/bold]")
        result = test_ingester(source_id, args.max_records)
        results.append(result)

    # Summary table
    console.print("\n[bold]============================================================[/bold]")
    console.print("[bold]                        SUMMARY                             [/bold]")
    console.print("[bold]============================================================[/bold]\n")

    table = Table()
    table.add_column("Source")
    table.add_column("Fetch")
    table.add_column("Parse")
    table.add_column("Records")
    table.add_column("Duration")
    table.add_column("Error")

    for r in results:
        fetch = "[green]OK[/green]" if r["fetch_success"] else "[red]FAIL[/red]"
        parse = "[green]OK[/green]" if r["parse_success"] else "[red]FAIL[/red]"
        error = r["error"][:30] + "..." if r["error"] and len(r["error"]) > 30 else (r["error"] or "")

        table.add_row(
            r["source"],
            fetch,
            parse,
            str(r["records_parsed"]),
            f"{r['duration']:.1f}s",
            error,
        )

    console.print(table)

    # Show sample data from first successful source
    for r in results:
        if r["sample_records"]:
            console.print(f"\n[bold]Sample records from {r['source']}:[/bold]")
            sample_table = Table()
            sample_table.add_column("Name")
            sample_table.add_column("Lat")
            sample_table.add_column("Lon")
            sample_table.add_column("Type")

            for site in r["sample_records"][:5]:
                sample_table.add_row(
                    site["name"][:40],
                    f"{site['lat']:.4f}",
                    f"{site['lon']:.4f}",
                    site["type"] or "-",
                )

            console.print(sample_table)
            break

    # Success count
    success_count = sum(1 for r in results if r["fetch_success"] and r["parse_success"])
    total = len(results)

    console.print(f"\n[bold]Results: {success_count}/{total} ingesters working[/bold]")

    if success_count == total:
        console.print("[green]All ingesters passed! Ready for database ingestion.[/green]")
    else:
        console.print("[yellow]Some ingesters failed. Check errors above.[/yellow]")


if __name__ == "__main__":
    main()
