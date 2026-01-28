#!/usr/bin/env python3
"""
Build Static Data for Ancient Nerds Map.

Complete pipeline to generate static files for the zero-API frontend:
1. Create/migrate database tables
2. Load all raw data into unified_sites
3. Link content to sites
4. Export optimized static JSON files

Usage:
    python scripts/build_static.py           # Full build
    python scripts/build_static.py --export  # Export only (skip loading)
    python scripts/build_static.py --source pleiades  # Load single source
"""

import sys
import argparse
import time
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


def check_database():
    """Check if database is accessible."""
    try:
        from pipeline.database import get_session, engine
        from sqlalchemy import text

        with get_session() as session:
            result = session.execute(text("SELECT 1"))
            result.fetchone()
        return True
    except Exception as e:
        console.print(f"[red]Database connection failed: {e}[/red]")
        console.print("\n[yellow]Make sure PostgreSQL is running:[/yellow]")
        console.print("  docker-compose up -d")
        return False


def create_tables():
    """Create database tables if they don't exist."""
    console.print("\n[bold]Step 1: Creating database tables...[/bold]")

    try:
        from pipeline.database import Base, engine

        Base.metadata.create_all(engine)
        console.print("[green]✓ Tables created/verified[/green]")
        return True
    except Exception as e:
        console.print(f"[red]✗ Failed to create tables: {e}[/red]")
        return False


def load_data(source: str = None):
    """Load raw data into unified_sites table."""
    console.print("\n[bold]Step 2: Loading data into unified_sites...[/bold]")

    try:
        from pipeline.unified_loader import UnifiedLoader

        loader = UnifiedLoader()
        loader.load_all(source_filter=source)

        success_count = sum(1 for s in loader.stats.values() if s.get("success"))
        total_records = sum(s.get("count", 0) for s in loader.stats.values())

        console.print(f"[green]✓ Loaded {total_records:,} records from {success_count} sources[/green]")
        return True
    except Exception as e:
        console.print(f"[red]✗ Failed to load data: {e}[/red]")
        import traceback
        traceback.print_exc()
        return False


def link_content():
    """Link content to sites."""
    console.print("\n[bold]Step 3: Linking content to sites...[/bold]")

    try:
        from pipeline.content_linker import ContentLinker

        linker = ContentLinker()
        linker.link_all()

        total_links = sum(s.get("count", 0) for s in linker.stats.values())
        console.print(f"[green]✓ Created {total_links:,} content links[/green]")
        return True
    except Exception as e:
        console.print(f"[red]✗ Failed to link content: {e}[/red]")
        import traceback
        traceback.print_exc()
        return False


def export_static(output_dir: str = None):
    """Export to static JSON files."""
    console.print("\n[bold]Step 4: Exporting static files...[/bold]")

    try:
        from pipeline.static_exporter import build_static

        build_static(output_dir=output_dir)

        console.print("[green]✓ Static files exported successfully[/green]")
        return True
    except Exception as e:
        console.print(f"[red]✗ Failed to export: {e}[/red]")
        import traceback
        traceback.print_exc()
        return False


def print_status():
    """Print current database status."""
    from pipeline.database import get_session
    from sqlalchemy import text

    console.print("\n[bold]Current Database Status:[/bold]")

    with get_session() as session:
        # Site counts by source
        result = session.execute(text("""
            SELECT source_id, COUNT(*) as count
            FROM unified_sites
            GROUP BY source_id
            ORDER BY count DESC
        """))

        console.print("\n[cyan]Sites by source:[/cyan]")
        total_sites = 0
        for row in result:
            console.print(f"  {row.source_id}: {row.count:,}")
            total_sites += row.count
        console.print(f"  [bold]Total: {total_sites:,}[/bold]")

        # Content link counts
        result = session.execute(text("""
            SELECT content_type, COUNT(*) as count
            FROM site_content_links
            GROUP BY content_type
            ORDER BY count DESC
        """))

        console.print("\n[cyan]Content links by type:[/cyan]")
        total_links = 0
        for row in result:
            console.print(f"  {row.content_type}: {row.count:,}")
            total_links += row.count
        console.print(f"  [bold]Total: {total_links:,}[/bold]")


def main():
    parser = argparse.ArgumentParser(description="Build static data for Ancient Nerds Map")
    parser.add_argument("--export-only", action="store_true", help="Only export (skip data loading)")
    parser.add_argument("--load-only", action="store_true", help="Only load data (skip export)")
    parser.add_argument("--link-only", action="store_true", help="Only link content")
    parser.add_argument("--source", "-s", help="Load only specific source")
    parser.add_argument("--output", "-o", help="Output directory for static files")
    parser.add_argument("--status", action="store_true", help="Show current status and exit")
    args = parser.parse_args()

    start_time = time.time()

    console.print(Panel.fit(
        "[bold cyan]Ancient Nerds Map - Static Build Pipeline[/bold cyan]\n"
        f"Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        border_style="cyan"
    ))

    # Check database connection
    if not check_database():
        return 1

    if args.status:
        print_status()
        return 0

    # Determine what to run
    run_create = True
    run_load = not args.export_only and not args.link_only
    run_link = not args.export_only and not args.load_only
    run_export = not args.load_only and not args.link_only

    success = True

    # Step 1: Create tables
    if run_create:
        if not create_tables():
            return 1

    # Step 2: Load data
    if run_load:
        if not load_data(source=args.source):
            success = False

    # Step 3: Link content
    if run_link and success:
        if not link_content():
            success = False

    # Step 4: Export static files
    if run_export and success:
        if not export_static(output_dir=args.output):
            success = False

    # Summary
    elapsed = time.time() - start_time
    console.print("\n" + "=" * 60)

    if success:
        console.print(Panel.fit(
            f"[bold green]Build completed successfully![/bold green]\n"
            f"Time: {elapsed:.1f} seconds",
            border_style="green"
        ))
    else:
        console.print(Panel.fit(
            f"[bold red]Build completed with errors[/bold red]\n"
            f"Time: {elapsed:.1f} seconds",
            border_style="red"
        ))

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
