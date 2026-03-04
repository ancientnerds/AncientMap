#!/usr/bin/env python3
"""
Full pipeline rebuild: Download → Ingest → Export → Copy to frontend.

Single command to rebuild everything from scratch:
    python scripts/rebuild_all.py

Options:
    --skip-download   Skip downloading (use existing raw data files)
    --skip-ingest     Skip DB ingestion (use existing DB data)
    --skip-export     Skip static export
    --force-download  Re-download even if data is fresh
"""

import subprocess
import sys
import time
from pathlib import Path

# Ensure we're in the project root
PROJECT_ROOT = Path(__file__).parent.parent
FRONTEND_DATA = PROJECT_ROOT / "ancient-nerds-map" / "public" / "data"
EXPORT_DATA = PROJECT_ROOT / "public" / "data"


def run(cmd: list[str], description: str) -> bool:
    """Run a command, stream output, return success."""
    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"{'='*60}\n")
    start = time.time()
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    elapsed = time.time() - start
    mins, secs = divmod(int(elapsed), 60)
    if result.returncode == 0:
        print(f"\n  OK ({mins}m {secs}s)")
    else:
        print(f"\n  FAILED (exit {result.returncode}, {mins}m {secs}s)")
    return result.returncode == 0


def copy_to_frontend():
    """Copy exported data to frontend public dir."""
    import shutil
    if not EXPORT_DATA.exists():
        print("  ERROR: No exported data found at public/data/")
        return False

    print(f"\n{'='*60}")
    print(f"  Step 4: Copy to frontend")
    print(f"{'='*60}\n")

    # Copy each subdirectory and file
    count = 0
    for item in EXPORT_DATA.iterdir():
        dest = FRONTEND_DATA / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)
        count += 1
    print(f"  Copied {count} items to {FRONTEND_DATA}")
    return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Full pipeline rebuild")
    parser.add_argument("--skip-download", action="store_true", help="Skip downloading raw data")
    parser.add_argument("--skip-ingest", action="store_true", help="Skip DB ingestion")
    parser.add_argument("--skip-export", action="store_true", help="Skip static export")
    parser.add_argument("--force-download", action="store_true", help="Re-download even if fresh")
    args = parser.parse_args()

    start = time.time()
    steps_ok = 0
    steps_total = 0

    # Step 1: Download
    if not args.skip_download:
        steps_total += 1
        cmd = [sys.executable, "scripts/download_all.py"]
        if args.force_download:
            cmd.append("--force")
        if run(cmd, "Step 1: Download all raw data"):
            steps_ok += 1
        else:
            print("\n  WARNING: Some downloads failed. Continuing with available data.\n")
            steps_ok += 1  # Non-fatal — ingest whatever we have

    # Step 2: Ingest
    if not args.skip_ingest:
        steps_total += 1
        cmd = [sys.executable, "-m", "pipeline.unified_loader", "--no-backup"]
        if run(cmd, "Step 2: Ingest all sources into DB"):
            steps_ok += 1
        else:
            print("\n  ERROR: Ingestion failed.")
            return 1

    # Step 3: Export
    if not args.skip_export:
        steps_total += 1
        cmd = [sys.executable, "-m", "pipeline.static_exporter"]
        if run(cmd, "Step 3: Export DB to static JSON"):
            steps_ok += 1
        else:
            print("\n  ERROR: Export failed.")
            return 1

    # Step 4: Copy to frontend
    if not args.skip_export:
        steps_total += 1
        if copy_to_frontend():
            steps_ok += 1

    elapsed = time.time() - start
    mins, secs = divmod(int(elapsed), 60)
    print(f"\n{'='*60}")
    print(f"  DONE: {steps_ok}/{steps_total} steps OK ({mins}m {secs}s)")
    print(f"{'='*60}\n")

    return 0 if steps_ok == steps_total else 1


if __name__ == "__main__":
    sys.exit(main())
