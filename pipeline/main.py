#!/usr/bin/env python3
"""
ANCIENT NERDS - Research Platform - Data Pipeline Entry Point

This is the main entry point for running the data pipeline.
It can ingest data from multiple sources and process them into the unified database.

Usage:
    python -m pipeline.main ingest pleiades
    python -m pipeline.main ingest all
    python -m pipeline.main status
"""

import sys
from pathlib import Path
from datetime import datetime

import click
from loguru import logger
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.config import settings, DATA_SOURCES
from pipeline.database import SessionLocal, SourceDatabase, SourceRecord, Site
from pipeline.ingesters import (
    PleiadesIngester,
    UNESCOIngester,
    GeoNamesIngester,
    OpenContextIngester,
    WikidataIngester,
    HistoricEnglandIngester,
    IrelandNMSIngester,
    ArachneIngester,
    EAMENAIngester,
    DINAAIngester,
    # NCEI Hazards
    NCEIEarthquakesIngester,
    NCEITsunamisIngester,
    NCEITsunamiObservationsIngester,
    NCEIVolcanoesIngester,
)


console = Console()

# Registry of available ingesters
INGESTERS = {
    # Global / Large databases
    "pleiades": PleiadesIngester,
    "unesco": UNESCOIngester,
    "geonames": GeoNamesIngester,
    "open_context": OpenContextIngester,
    "wikidata": WikidataIngester,
    # Europe
    "historic_england": HistoricEnglandIngester,
    "ireland_nms": IrelandNMSIngester,
    "arachne": ArachneIngester,
    # Middle East / Africa
    "eamena": EAMENAIngester,
    # North America
    "dinaa": DINAAIngester,
    # NCEI Hazards
    "ncei_earthquakes": NCEIEarthquakesIngester,
    "ncei_tsunamis": NCEITsunamisIngester,
    "ncei_tsunami_obs": NCEITsunamiObservationsIngester,
    "ncei_volcanoes": NCEIVolcanoesIngester,
}


@click.group()
@click.option("--debug", is_flag=True, help="Enable debug logging")
def cli(debug):
    """ANCIENT NERDS - Research Platform Data Pipeline"""
    if debug:
        from pipeline.utils.logging import setup_logging
        setup_logging(level="DEBUG")


@cli.command()
@click.argument("source", type=click.Choice(list(INGESTERS.keys()) + ["all"]))
@click.option("--skip-fetch", is_flag=True, help="Use existing raw data instead of downloading")
@click.option("--batch-size", type=int, default=1000, help="Batch size for database commits")
def ingest(source: str, skip_fetch: bool, batch_size: int):
    """
    Ingest data from a source.

    SOURCE can be a specific source name (e.g., 'pleiades') or 'all' to run all ingesters.
    """
    console.print(f"\n[bold blue]ANCIENT NERDS - Data Ingestion[/bold blue]")
    console.print(f"Source: {source}")
    console.print(f"Skip fetch: {skip_fetch}")
    console.print(f"Batch size: {batch_size}\n")

    if source == "all":
        sources = list(INGESTERS.keys())
    else:
        sources = [source]

    results = []

    for src in sources:
        console.print(f"\n[bold]Processing: {src}[/bold]")

        ingester_class = INGESTERS[src]

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Ingesting {src}...", total=None)

            try:
                with ingester_class() as ingester:
                    result = ingester.run(skip_fetch=skip_fetch, batch_size=batch_size)
                    results.append(result)

                    if result.success:
                        progress.update(task, description=f"[green]✓ {src} complete[/green]")
                    else:
                        progress.update(task, description=f"[red]✗ {src} failed[/red]")

            except Exception as e:
                console.print(f"[red]Error ingesting {src}: {e}[/red]")
                logger.exception(f"Error ingesting {src}")

    # Print summary
    console.print("\n[bold]Ingestion Summary[/bold]")
    table = Table()
    table.add_column("Source")
    table.add_column("Status")
    table.add_column("Fetched")
    table.add_column("Parsed")
    table.add_column("Saved")
    table.add_column("Failed")
    table.add_column("Duration")

    for result in results:
        status = "[green]Success[/green]" if result.success else "[red]Failed[/red]"
        duration = f"{result.duration_seconds:.1f}s" if result.duration_seconds else "-"

        table.add_row(
            result.source_id,
            status,
            str(result.records_fetched),
            str(result.records_parsed),
            str(result.records_saved),
            str(result.records_failed),
            duration,
        )

    console.print(table)


@cli.command()
def status():
    """Show pipeline status and database statistics."""
    console.print("\n[bold blue]ANCIENT NERDS - Pipeline Status[/bold blue]\n")

    session = SessionLocal()

    try:
        # Source databases
        console.print("[bold]Data Sources[/bold]")
        table = Table()
        table.add_column("Source")
        table.add_column("Name")
        table.add_column("Records")
        table.add_column("Last Sync")
        table.add_column("Status")

        sources = session.query(SourceDatabase).order_by(SourceDatabase.priority).all()

        if not sources:
            console.print("[yellow]No sources configured. Run 'python scripts/init_db.py' first.[/yellow]")
        else:
            for source in sources:
                last_sync = source.last_sync.strftime("%Y-%m-%d %H:%M") if source.last_sync else "Never"
                record_count = source.record_count or 0
                status = "[green]OK[/green]" if source.last_sync else "[yellow]Not synced[/yellow]"

                # Check if ingester exists
                if source.id not in INGESTERS:
                    status = "[dim]No ingester[/dim]"

                table.add_row(
                    source.id,
                    source.name,
                    str(record_count),
                    last_sync,
                    status,
                )

            console.print(table)

        # Overall statistics
        console.print("\n[bold]Database Statistics[/bold]")

        source_record_count = session.query(SourceRecord).count()
        site_count = session.query(Site).count()

        stats_table = Table()
        stats_table.add_column("Metric")
        stats_table.add_column("Value")
        stats_table.add_row("Source Records", str(source_record_count))
        stats_table.add_row("Deduplicated Sites", str(site_count))
        stats_table.add_row("Deduplication Rate", f"{(1 - site_count / max(source_record_count, 1)) * 100:.1f}%" if source_record_count > 0 else "N/A")

        console.print(stats_table)

    finally:
        session.close()


@cli.command()
def list_sources():
    """List all available data sources."""
    console.print("\n[bold blue]Available Data Sources[/bold blue]\n")

    table = Table()
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Ingester")
    table.add_column("Description")

    for source_id, source_info in DATA_SOURCES.items():
        has_ingester = "[green]✓[/green]" if source_id in INGESTERS else "[dim]✗[/dim]"
        description = source_info.get("description", "")[:50] + "..." if len(source_info.get("description", "")) > 50 else source_info.get("description", "")

        table.add_row(
            source_id,
            source_info.get("name", source_id),
            has_ingester,
            description,
        )

    console.print(table)


@cli.group()
def backup():
    """Database backup and restore operations."""
    pass


@backup.command("create")
@click.option("--db/--no-db", default=True, help="Include database backup")
@click.option("--contributions/--no-contributions", default=True, help="Include contributions.json backup")
def backup_create(db: bool, contributions: bool):
    """Create a backup of database and contributions."""
    from pipeline.backup import create_backup
    result = create_backup(include_db=db, include_contributions=contributions)
    if result.success:
        console.print(f"[green]Backup created: {result.backup_id}[/green]")
        if result.database_path:
            console.print(f"  Database: {result.database_path}")
        if result.contributions_path:
            console.print(f"  Contributions: {result.contributions_path}")
    else:
        console.print(f"[red]Backup failed: {result.error}[/red]")


@backup.command("list")
def backup_list():
    """List available backups."""
    from pipeline.backup import list_backups
    backups = list_backups()
    if not backups:
        console.print("[yellow]No backups found[/yellow]")
        return

    table = Table()
    table.add_column("Timestamp")
    table.add_column("Database")
    table.add_column("Contributions")

    for ts, files in backups:
        db_status = "[green]Yes[/green]" if "database" in files else "[dim]-[/dim]"
        contrib_status = "[green]Yes[/green]" if "contributions" in files else "[dim]-[/dim]"
        table.add_row(ts, db_status, contrib_status)

    console.print(table)


@backup.command("restore")
@click.argument("timestamp")
@click.option("--db/--no-db", default=True, help="Restore database")
@click.option("--contributions/--no-contributions", default=True, help="Restore contributions.json")
@click.confirmation_option(prompt="Are you sure you want to restore? This will overwrite current data.")
def backup_restore(timestamp: str, db: bool, contributions: bool):
    """Restore from a specific backup."""
    from pipeline.backup import restore_backup
    success = restore_backup(timestamp, restore_db=db, restore_contributions=contributions)
    if success:
        console.print(f"[green]Restore complete from backup: {timestamp}[/green]")
    else:
        console.print(f"[red]Restore failed[/red]")


@cli.command()
@click.argument("source")
@click.option("--limit", type=int, default=10, help="Number of records to show")
def preview(source: str, limit: int):
    """Preview data from a source without saving to database."""
    if source not in INGESTERS:
        console.print(f"[red]Unknown source: {source}[/red]")
        console.print(f"Available: {', '.join(INGESTERS.keys())}")
        return

    console.print(f"\n[bold blue]Preview: {source}[/bold blue]\n")

    ingester_class = INGESTERS[source]

    with ingester_class() as ingester:
        # Fetch data
        console.print("Fetching data...")
        raw_path = ingester.fetch()

        # Parse and show preview
        console.print(f"Parsing {raw_path}...\n")

        table = Table()
        table.add_column("ID")
        table.add_column("Name")
        table.add_column("Lat")
        table.add_column("Lon")
        table.add_column("Type")
        table.add_column("Period")

        count = 0
        for site in ingester.parse(raw_path):
            if count >= limit:
                break

            table.add_row(
                site.source_id[:20],
                site.name[:40],
                f"{site.lat:.4f}",
                f"{site.lon:.4f}",
                site.site_type or "-",
                site.period_name[:30] if site.period_name else "-",
            )
            count += 1

        console.print(table)
        console.print(f"\n[dim]Showing {count} of many records[/dim]")


if __name__ == "__main__":
    cli()
