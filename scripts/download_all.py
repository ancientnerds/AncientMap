#!/usr/bin/env python3
"""
Download all archaeological data from all working sources.

Run weekly to keep data up to date:
    python scripts/download_all.py
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import re
import signal

# Disable logging BEFORE any pipeline imports
os.environ["DISABLE_LOGGING"] = "1"

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Suppress loguru completely
from loguru import logger
logger.remove()

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn, TimeRemainingColumn

console = Console()

# Graceful shutdown
shutdown_event = threading.Event()

def handle_signal(signum, frame):
    console.print("\n[yellow]Stopping downloads...[/yellow]")
    shutdown_event.set()

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

# All working ingesters (cleaned up - broken sources removed)
SOURCES = {
    # Priority 1: Fast, reliable sources with unique data
    "pleiades": {"enabled": True, "priority": 1, "est": "38K", "module": "pipeline.ingesters.pleiades", "class": "PleiadesIngester"},
    "unesco": {"enabled": True, "priority": 1, "est": "1.2K", "module": "pipeline.ingesters.unesco", "class": "UNESCOIngester"},
    "geonames": {"enabled": True, "priority": 1, "est": "50K", "module": "pipeline.ingesters.geonames", "class": "GeoNamesIngester"},
    "sacred_sites": {"enabled": True, "priority": 1, "est": "80+", "module": "pipeline.ingesters.sacred_sites", "class": "SacredSitesIngester"},
    "rock_art": {"enabled": True, "priority": 1, "est": "50+", "module": "pipeline.ingesters.rock_art", "class": "RockArtIngester"},

    # Priority 2: Regional databases with good APIs
    "historic_england": {"enabled": True, "priority": 2, "est": "20K", "module": "pipeline.ingesters.historic_england", "class": "HistoricEnglandIngester"},
    "ireland_nms": {"enabled": True, "priority": 2, "est": "140K", "module": "pipeline.ingesters.ireland_nms", "class": "IrelandNMSIngester"},
    "arachne": {"enabled": True, "priority": 2, "est": "60K", "module": "pipeline.ingesters.arachne", "class": "ArachneIngester"},
    "dare": {"enabled": True, "priority": 2, "est": "27K", "module": "pipeline.ingesters.dare", "class": "DAREIngester"},

    # Priority 3: Large datasets
    "wikidata": {"enabled": True, "priority": 3, "est": "177K", "module": "pipeline.ingesters.wikidata", "class": "WikidataIngester"},
    "open_context": {"enabled": True, "priority": 3, "est": "500K", "module": "pipeline.ingesters.open_context", "class": "OpenContextIngester", "max_records": 500000},
    "eamena": {"enabled": True, "priority": 3, "est": "50K", "module": "pipeline.ingesters.eamena", "class": "EAMENAIngester", "max_records": 50000},
    "dinaa": {"enabled": True, "priority": 3, "est": "500K", "module": "pipeline.ingesters.dinaa", "class": "DINAAIngester", "max_records": 500000},
    "megalithic_portal": {"enabled": True, "priority": 3, "est": "60K", "module": "pipeline.ingesters.megalithic_portal", "class": "MegalithicPortalIngester"},

    # Priority 4: OSM Historic (parallel download, ~500K sites)
    "osm_historic": {"enabled": True, "priority": 4, "est": "577K", "module": "pipeline.ingesters.osm_historic", "class": "OSMHistoricIngester"},

    # Priority 5: Historical Maps
    "david_rumsey": {"enabled": True, "priority": 5, "est": "200+", "module": "pipeline.ingesters.david_rumsey", "class": "DavidRumseyIngester"},

    # Priority 6: Shipwrecks (Maritime Archaeology)
    "shipwrecks_oxrep": {"enabled": True, "priority": 6, "est": "1.8K", "module": "pipeline.ingesters.shipwrecks_oxrep", "class": "OXREPShipwrecksIngester"},

    # Priority 7: Numismatics (Coins)
    "coins_nomisma": {"enabled": True, "priority": 7, "est": "50K+", "module": "pipeline.ingesters.coins_nomisma", "class": "NomismaIngester"},

    # Priority 8: Inscriptions (Epigraphic Data)
    "inscriptions_edh": {"enabled": True, "priority": 8, "est": "82K", "module": "pipeline.ingesters.inscriptions_edh", "class": "EDHInscriptionsIngester"},

    # Priority 9: Environmental Data
    "volcanic_holvol": {"enabled": True, "priority": 9, "est": "850+", "module": "pipeline.ingesters.volcanic_holvol", "class": "HolVolIngester"},

    # Priority 10: 3D Models
    "models_sketchfab": {"enabled": True, "priority": 10, "est": "50K+", "module": "pipeline.ingesters.models_sketchfab", "class": "SketchfabIngester"},

    # Priority 11: Historical Boundaries
    "boundaries_seshat": {"enabled": True, "priority": 11, "est": "500+", "module": "pipeline.ingesters.boundaries_seshat", "class": "SeshatIngester"},

    # Priority 12: Museum Collections & Artworks
    "met_museum": {"enabled": False, "priority": 12, "est": "50K+", "module": "pipeline.ingesters.met_museum", "class": "MetMuseumIngester", "reason": "API has bot protection"},
    "europeana": {"enabled": True, "priority": 12, "est": "100K+", "module": "pipeline.ingesters.europeana", "class": "EuropeanaIngester"},

    # Priority 13: Ancient Texts
    "topostext": {"enabled": True, "priority": 13, "est": "21K+", "module": "pipeline.ingesters.topostext", "class": "ToposTextIngester"},
}

FRESHNESS_DAYS = 7
MIN_VALID_SIZE = 1024

# Pre-loaded ingester classes
_ingester_classes: Dict[str, Any] = {}


def cleanup_old_files() -> int:
    """Remove old timestamped files."""
    data_dir = Path("data/raw")
    if not data_dir.exists():
        return 0

    pattern = re.compile(r".*-\d{8}\.(json|csv|txt|zip)$")
    removed = 0

    for source_dir in data_dir.iterdir():
        if source_dir.is_dir():
            for f in source_dir.iterdir():
                if pattern.match(f.name):
                    try:
                        f.unlink()
                        removed += 1
                    except:
                        pass
    return removed


def get_data_file(source_id: str) -> Optional[Path]:
    """Get data file for a source."""
    data_dir = Path("data/raw") / source_id
    if not data_dir.exists():
        return None

    files = [f for f in data_dir.glob("*") if f.is_file() and not re.search(r"-\d{8}\.", f.name)]
    if files:
        return max(files, key=lambda f: f.stat().st_mtime)
    return None


def is_data_fresh(source_id: str) -> bool:
    """Check if data is fresh and valid."""
    f = get_data_file(source_id)
    if not f:
        return False
    if f.stat().st_size < MIN_VALID_SIZE:
        return False
    age = datetime.now() - datetime.fromtimestamp(f.stat().st_mtime)
    return age < timedelta(days=FRESHNESS_DAYS)


def get_file_size(path: Path) -> str:
    """Human-readable file size."""
    if not path or not path.exists():
        return "-"
    size = path.stat().st_size
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def preload_ingesters(source_ids: List[str]) -> None:
    """Pre-load ingester classes to avoid thread deadlocks."""
    import importlib
    for sid in source_ids:
        if sid in SOURCES and SOURCES[sid].get("enabled"):
            try:
                mod = importlib.import_module(SOURCES[sid]["module"])
                _ingester_classes[sid] = getattr(mod, SOURCES[sid]["class"])
            except Exception as e:
                console.print(f"[red]Failed to load {sid}: {e}[/red]")


def download_source(source_id: str, config: dict, progress: Progress, task_id) -> dict:
    """Download a single source."""
    result = {"source": source_id, "success": False, "error": None, "size": None}

    if shutdown_event.is_set():
        progress.update(task_id, description=f"[yellow]{source_id}: stopped[/yellow]")
        return result

    # Progress callback that updates the Rich progress bar
    def on_progress(current: int, total: int = None, status: str = None):
        if total and total > 0:
            pct = min(99, int(current * 100 / total))  # Cap at 99 until done
            progress.update(task_id, completed=pct, total=100,
                          description=f"[cyan]{source_id}: {status or f'{current:,}'}")
        else:
            progress.update(task_id, description=f"[cyan]{source_id}: {status or f'{current:,}'}")

    progress.update(task_id, description=f"[cyan]{source_id}: starting...[/cyan]")

    try:
        ingester_class = _ingester_classes.get(source_id)
        if not ingester_class:
            raise ValueError("Not loaded")

        # Pass progress callback to ingester
        with ingester_class(progress_callback=on_progress) as ingester:
            if "max_records" in config:
                ingester.MAX_RECORDS = config["max_records"]

            data_path = ingester.fetch()

            if shutdown_event.is_set():
                progress.update(task_id, description=f"[yellow]{source_id}: stopped[/yellow]")
                return result

        size = get_file_size(data_path)
        result["success"] = True
        result["size"] = size
        progress.update(task_id, description=f"[green]{source_id}: OK {size}[/green]", completed=100)

    except Exception as e:
        result["error"] = str(e)[:50]
        progress.update(task_id, description=f"[red]{source_id}: FAIL {str(e)[:30]}[/red]", completed=100)

    return result


def print_final_status():
    """Print final status table."""
    from rich.table import Table
    table = Table(title="Data Status", show_header=True)
    table.add_column("Source", style="cyan")
    table.add_column("Status")
    table.add_column("File")
    table.add_column("Size", justify="right")

    for sid, cfg in sorted(SOURCES.items(), key=lambda x: x[1]["priority"]):
        f = get_data_file(sid)

        if not cfg.get("enabled"):
            table.add_row(sid, "[dim]DISABLED[/dim]", cfg.get("reason", "-"), "-")
        elif f:
            size = f.stat().st_size
            age = datetime.now() - datetime.fromtimestamp(f.stat().st_mtime)
            if size < MIN_VALID_SIZE:
                status = "[red]INVALID[/red]"
            elif age < timedelta(days=FRESHNESS_DAYS):
                status = "[green]FRESH[/green]"
            else:
                status = "[yellow]STALE[/yellow]"
            table.add_row(sid, status, f.name, get_file_size(f))
        else:
            table.add_row(sid, "[red]MISSING[/red]", "-", "-")

    console.print(table)


def get_default_parallel():
    """Get default parallel workers (cpu_count - 2, minimum 1)."""
    cpu_count = os.cpu_count() or 1
    return max(1, cpu_count - 2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", action="store_true", help="Show status only")
    parser.add_argument("--force", "-f", action="store_true", help="Re-download all")
    parser.add_argument("--parallel", "-p", type=int, default=get_default_parallel(), help=f"Parallel downloads (default: {get_default_parallel()})")
    parser.add_argument("--source", "-s", type=str, help="Single source only")
    args = parser.parse_args()

    Path("data/raw").mkdir(parents=True, exist_ok=True)

    if args.status:
        print_final_status()
        return 0

    # Cleanup old files
    removed = cleanup_old_files()
    if removed:
        console.print(f"[dim]Cleaned {removed} old files[/dim]")

    # Get sources to download
    if args.source:
        if args.source not in SOURCES:
            console.print(f"[red]Unknown: {args.source}[/red]")
            return 1
        sources = {args.source: SOURCES[args.source]}
    else:
        sources = {k: v for k, v in SOURCES.items() if v.get("enabled")}

    # Filter fresh
    to_download = []
    skipped = []
    for sid, cfg in sorted(sources.items(), key=lambda x: x[1]["priority"]):
        if not args.force and is_data_fresh(sid):
            skipped.append(sid)
        else:
            to_download.append((sid, cfg))

    if skipped:
        console.print(f"[dim]Skipping fresh: {', '.join(skipped)}[/dim]")

    if not to_download:
        console.print("[green]All data fresh![/green]")
        print_final_status()
        return 0

    console.print(f"\n[bold]Downloading {len(to_download)} sources in parallel...[/bold]\n")

    # Pre-load ingesters
    preload_ingesters([s[0] for s in to_download])

    # Download with progress bars
    results = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}", justify="left"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        # Create tasks for each source
        tasks = {}
        for sid, cfg in to_download:
            task_id = progress.add_task(f"[dim]{sid}: waiting...[/dim]", total=100, completed=0)
            tasks[sid] = (task_id, cfg)

        # Run all downloads in parallel
        with ThreadPoolExecutor(max_workers=min(args.parallel, len(to_download))) as executor:
            futures = {
                executor.submit(download_source, sid, cfg, progress, task_id): sid
                for sid, (task_id, cfg) in tasks.items()
            }

            for future in as_completed(futures):
                sid = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    results.append({"source": sid, "success": False, "error": str(e)})

                if shutdown_event.is_set():
                    for f in futures:
                        f.cancel()
                    break

    # Summary
    console.print()
    ok = sum(1 for r in results if r.get("success"))
    fail = sum(1 for r in results if not r.get("success"))

    if fail:
        console.print(f"[red]Failed ({fail}):[/red]")
        for r in results:
            if not r.get("success"):
                console.print(f"  [red]X[/red] {r['source']}: {r.get('error', '?')}")

    console.print(f"\n[green]{ok} done[/green], [red]{fail} failed[/red], [dim]{len(skipped)} skipped[/dim]\n")

    print_final_status()
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
