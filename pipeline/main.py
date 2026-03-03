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
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import click
from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.config import DATA_SOURCES
from pipeline.database import SessionLocal, Site, SourceDatabase, SourceRecord
from pipeline.ingesters import (
    ArachneIngester,
    CanmoreScotlandIngester,
    CofleinWalesIngester,
    DAREIngester,
    EAMENAIngester,
    EarthImpactsIngester,
    GeoNamesIngester,
    HistoricEnglandIngester,
    HolVolIngester,
    IrelandNMSIngester,
    LISTInscriptionsIngester,
    LuwianAtlasIngester,
    MycenaeanAtlasIngester,
    NCEIEarthquakesIngester,
    NCEITsunamiObservationsIngester,
    NCEITsunamisIngester,
    NCEIVolcanoesIngester,
    NomismaIngester,
    OpenContextIngester,
    OSMHistoricIngester,
    OXREPShipwrecksIngester,
    PeruAmazonIngester,
    PleiadesIngester,
    RadiocarbonPaleoIngester,
    RockArtIngester,
    SeshatIngester,
    ToposTextIngester,
    UNESCOIngester,
    ViciOrgIngester,
    WikidataIngester,
)
from pipeline.ingesters.base import IngesterResult, VerifyResult

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
    "dare": DAREIngester,
    "osm_historic": OSMHistoricIngester,
    "topostext": ToposTextIngester,
    "vici_org": ViciOrgIngester,
    "canmore_scotland": CanmoreScotlandIngester,
    "coflein_wales": CofleinWalesIngester,
    "mycenaean_atlas": MycenaeanAtlasIngester,
    "radiocarbon_paleo": RadiocarbonPaleoIngester,
    # Epigraphy / Numismatics / Maritime
    "list_inscriptions": LISTInscriptionsIngester,
    "coins_nomisma": NomismaIngester,
    "shipwrecks_oxrep": OXREPShipwrecksIngester,
    # Middle East / Africa
    "eamena": EAMENAIngester,
    "luwian_atlas": LuwianAtlasIngester,
    # Rock Art
    "rock_art": RockArtIngester,
    # Geological / Volcanic
    "earth_impacts": EarthImpactsIngester,
    "volcanic_holvol": HolVolIngester,
    "boundaries_seshat": SeshatIngester,
    # Americas
    "peru_amazon": PeruAmazonIngester,
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
@click.option("--verify-first", is_flag=True, help="Run smoke test before full ingestion")
@click.option(
    "--workers", type=int, default=8, help="Max parallel workers for fetch/verify (default: 8)"
)
def ingest(source: str, skip_fetch: bool, batch_size: int, verify_first: bool, workers: int):
    """
    Ingest data from a source.

    SOURCE can be a specific source name (e.g., 'pleiades') or 'all' to run all ingesters.
    """
    console.print("\n[bold blue]ANCIENT NERDS - Data Ingestion[/bold blue]")
    console.print(f"Source: {source}")
    console.print(f"Skip fetch: {skip_fetch}")
    console.print(f"Batch size: {batch_size}\n")

    if source == "all":
        sources = list(INGESTERS.keys())
    else:
        sources = [source]

    # Pre-flight verification
    if verify_first:
        console.print("[bold]Running pre-flight verification...[/bold]\n")
        verify_results = _run_verify(sources, sample_size=5, skip_fetch=skip_fetch, workers=workers)
        failed = sum(1 for vr in verify_results if not vr.success)
        if failed:
            console.print(
                f"\n[bold red]Aborting: {failed} source(s) failed verification.[/bold red]"
            )
            raise SystemExit(1)
        console.print(
            f"\n[green]Verification passed for {len(sources)} source(s). "
            f"Starting full ingestion...[/green]\n"
        )
        # Verify already downloaded raw data — don't re-fetch
        skip_fetch = True

    results = []

    if workers > 1 and len(sources) > 1 and not skip_fetch:
        # PHASE 1: Parallel fetch (download only)
        console.print(
            f"[bold]Phase 1: Downloading {len(sources)} sources ({workers} workers)...[/bold]\n"
        )
        fetch_results: dict[str, str | None] = {}  # src -> error or None
        print_lock = threading.Lock()
        completed_count = 0
        total = len(sources)

        def fetch_one(src: str) -> tuple[str, str | None]:
            nonlocal completed_count
            ingester_class = INGESTERS[src]
            error = None
            try:
                with ingester_class() as ingester:
                    if not ingester.available:
                        error = ingester.unavailable_reason or "unavailable"
                    else:
                        ingester.fetch()
            except Exception as e:
                logger.exception(f"Error fetching {src}")
                error = str(e)

            with print_lock:
                completed_count += 1
                tag = "[green]OK[/green]" if error is None else f"[red]FAIL: {error}[/red]"
                console.print(f"  [{completed_count}/{total}] {src} {tag}")

            return src, error

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(fetch_one, src): src for src in sources}
            for future in as_completed(futures):
                src, error = future.result()
                fetch_results[src] = error

        fetch_failed = {s: e for s, e in fetch_results.items() if e is not None}
        if fetch_failed:
            console.print(f"\n[yellow]{len(fetch_failed)} source(s) failed to download[/yellow]")

        # PHASE 2: Sequential ingest (parse + DB write) with skip_fetch=True
        console.print(f"\n[bold]Phase 2: Ingesting {len(sources)} sources (sequential)...[/bold]\n")
        for src in sources:
            if fetch_results.get(src) is not None:
                console.print(f"  [yellow]Skipping {src} (fetch failed)[/yellow]")
                results.append(
                    IngesterResult(
                        source_id=src,
                        success=False,
                        errors=[f"Fetch failed: {fetch_results[src]}"],
                    )
                )
                continue

            console.print(f"  Processing: {src}...")
            ingester_class = INGESTERS[src]
            try:
                with ingester_class() as ingester:
                    result = ingester.run(skip_fetch=True, batch_size=batch_size)
                    results.append(result)
                    tag = "[green]OK[/green]" if result.success else "[red]FAIL[/red]"
                    console.print(f"  {src} {tag}")
            except Exception as e:
                console.print(f"  [red]{src} CRASH: {e}[/red]")
                logger.exception(f"Error ingesting {src}")
                results.append(
                    IngesterResult(
                        source_id=src,
                        success=False,
                        errors=[f"CRASH: {e}"],
                    )
                )
    else:
        # Sequential mode (single source, --skip-fetch, or --workers 1)
        for src in sources:
            console.print(f"\n[bold]Processing: {src}[/bold]")
            ingester_class = INGESTERS[src]

            with Progress(
                SpinnerColumn("line"),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(f"Ingesting {src}...", total=None)
                try:
                    with ingester_class() as ingester:
                        result = ingester.run(skip_fetch=skip_fetch, batch_size=batch_size)
                        results.append(result)
                        if result.success:
                            progress.update(
                                task,
                                description=f"[green]{src} complete[/green]",
                            )
                        else:
                            progress.update(
                                task,
                                description=f"[red]{src} failed[/red]",
                            )
                except Exception as e:
                    console.print(f"[red]Error ingesting {src}: {e}[/red]")
                    logger.exception(f"Error ingesting {src}")
                    results.append(
                        IngesterResult(
                            source_id=src,
                            success=False,
                            errors=[f"CRASH: {e}"],
                        )
                    )

    # Print summary
    console.print("\n[bold]Ingestion Summary[/bold]")
    table = Table()
    table.add_column("Source")
    table.add_column("Status")
    table.add_column("Fetched", justify="right")
    table.add_column("Parsed", justify="right")
    table.add_column("Saved", justify="right")
    table.add_column("Failed", justify="right")
    table.add_column("Duration", justify="right")

    problem_sources = []

    for result in results:
        if not result.success:
            status = "[red]FAILED[/red]"
        elif result.records_saved == 0:
            status = "[yellow]EMPTY[/yellow]"
        else:
            status = "[green]OK[/green]"
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

        if not result.success or result.records_saved == 0 or result.errors:
            problem_sources.append(result)

    console.print(table)

    # Detailed error report
    if problem_sources:
        console.print(f"\n[bold red]{len(problem_sources)} source(s) need attention:[/bold red]")
        for result in problem_sources:
            label = "[red]FAILED[/red]" if not result.success else "[yellow]EMPTY[/yellow]"
            console.print(f"\n  {label} [bold]{result.source_id}[/bold]")
            if result.errors:
                for err in result.errors[:5]:
                    console.print(f"    - {err}")
            elif result.records_saved == 0:
                console.print(
                    f"    - Fetched {result.records_fetched}, parsed {result.records_parsed}, saved 0"
                )
        console.print()
        console.print("[dim]Retry individually:[/dim]")
        for r in problem_sources:
            console.print(f"  python -m pipeline.main ingest {r.source_id}")
        console.print()


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
            console.print(
                "[yellow]No sources configured. Run 'python scripts/init_db.py' first.[/yellow]"
            )
        else:
            for source in sources:
                last_sync = (
                    source.last_sync.strftime("%Y-%m-%d %H:%M") if source.last_sync else "Never"
                )
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
        stats_table.add_row(
            "Deduplication Rate",
            f"{(1 - site_count / max(source_record_count, 1)) * 100:.1f}%"
            if source_record_count > 0
            else "N/A",
        )

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
        description = (
            source_info.get("description", "")[:50] + "..."
            if len(source_info.get("description", "")) > 50
            else source_info.get("description", "")
        )

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
@click.option(
    "--contributions/--no-contributions", default=True, help="Include contributions.json backup"
)
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
@click.confirmation_option(
    prompt="Are you sure you want to restore? This will overwrite current data."
)
def backup_restore(timestamp: str, db: bool, contributions: bool):
    """Restore from a specific backup."""
    from pipeline.backup import restore_backup

    success = restore_backup(timestamp, restore_db=db, restore_contributions=contributions)
    if success:
        console.print(f"[green]Restore complete from backup: {timestamp}[/green]")
    else:
        console.print("[red]Restore failed[/red]")


def _run_verify(
    sources: list[str], sample_size: int, skip_fetch: bool, workers: int = 1
) -> list[VerifyResult]:
    """Run verification for a list of sources and print results table."""
    results_dict: dict[str, VerifyResult] = {}
    print_lock = threading.Lock()
    completed_count = 0
    total = len(sources)

    def verify_one(src: str) -> VerifyResult:
        nonlocal completed_count
        ingester_class = INGESTERS[src]

        try:
            with ingester_class() as ingester:
                vr = ingester.verify(sample_size=sample_size, skip_fetch=skip_fetch)
        except Exception as e:
            logger.exception(f"Error verifying {src}")
            vr = VerifyResult(source_id=src, success=False, error=f"CRASH: {e}")

        with print_lock:
            completed_count += 1
            status = "[green]PASS[/green]" if vr.success else "[red]FAIL[/red]"
            duration = f"({vr.duration_seconds:.1f}s)" if vr.duration_seconds else ""
            console.print(f"  [{completed_count}/{total}] {src} {status} {duration}")

        return vr

    if workers <= 1:
        for src in sources:
            results_dict[src] = verify_one(src)
    else:
        console.print(f"  Running with {workers} parallel workers...\n")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(verify_one, src): src for src in sources}
            for future in as_completed(futures):
                src = futures[future]
                results_dict[src] = future.result()

    # Preserve original order for table
    results = [results_dict[src] for src in sources]

    # Print results table
    console.print("\n[bold]Verification Results[/bold]")
    table = Table()
    table.add_column("Source")
    table.add_column("Status")
    table.add_column("Fetched")
    table.add_column("Parsed")
    table.add_column("Valid")
    table.add_column("Coverage")
    table.add_column("Time", justify="right")

    for vr in results:
        if vr.success:
            status = "[green]PASS[/green]"
        else:
            status = "[red]FAIL[/red]"

        fetched = "[green]OK[/green]" if vr.fetch_ok else "[red]ERR[/red]"
        parsed = f"{vr.records_sampled}" if vr.parse_ok else "-"
        valid = f"{vr.records_valid}/{vr.records_sampled}" if vr.records_sampled else "-"

        cov_parts = []
        for field_name, count in vr.field_coverage.items():
            cov_parts.append(f"{field_name}:{count}")
        coverage = " ".join(cov_parts) if cov_parts else "-"

        duration = f"{vr.duration_seconds:.1f}s" if vr.duration_seconds else "-"

        table.add_row(vr.source_id, status, fetched, parsed, valid, coverage, duration)

    console.print(table)

    # Summary
    passed = sum(1 for vr in results if vr.success)
    failed = len(results) - passed

    console.print(f"\n[bold]{passed} passed[/bold], [bold]{failed} failed[/bold]")

    if failed:
        console.print("\n[bold red]Failed sources:[/bold red]")
        for vr in results:
            if not vr.success:
                error_msg = vr.error or "; ".join(vr.sample_errors[:3])
                console.print(f"  [red]x[/red] [bold]{vr.source_id}[/bold]: {error_msg}")
    else:
        console.print("\n[green]All sources verified. Safe to run full ingestion.[/green]")

    return results


@cli.command()
@click.argument("source", type=click.Choice(list(INGESTERS.keys()) + ["all"]))
@click.option("--sample-size", type=int, default=5, help="Number of records to sample per source")
@click.option("--skip-fetch", is_flag=True, help="Use existing raw data")
@click.option("--workers", type=int, default=8, help="Max parallel workers (default: 8)")
def verify(source: str, sample_size: int, skip_fetch: bool, workers: int):
    """Smoke test: fetch and validate sample records from sources."""
    console.print("\n[bold blue]ANCIENT NERDS - Source Verification[/bold blue]")
    console.print(f"Source: {source}")
    console.print(f"Sample size: {sample_size}\n")

    sources = list(INGESTERS.keys()) if source == "all" else [source]
    results = _run_verify(sources, sample_size, skip_fetch, workers=workers)

    failed = sum(1 for vr in results if not vr.success)
    if failed:
        raise SystemExit(1)


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
