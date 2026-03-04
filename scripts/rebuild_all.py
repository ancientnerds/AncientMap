#!/usr/bin/env python3
"""
Full pipeline rebuild: Download → Ingest → Export.

Single command to rebuild everything from scratch:
    python scripts/rebuild_all.py

Options:
    --skip-download   Skip downloading (use existing raw data files)
    --skip-ingest     Skip DB ingestion (use existing DB data)
    --skip-export     Skip static export
    --force-download  Re-download even if data is fresh

Note: The frontend reads from public/data/ directly (symlinked on VPS).
      No copy step needed — the static exporter writes to public/data/.
"""

import subprocess
import sys
import time
from pathlib import Path

# Ensure we're in the project root
PROJECT_ROOT = Path(__file__).parent.parent


def run(cmd: list[str], description: str) -> bool:
    """Run a command, stream output, return success."""
    print(f"\n{'=' * 60}")
    print(f"  {description}")
    print(f"{'=' * 60}\n")
    start = time.time()
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    elapsed = time.time() - start
    mins, secs = divmod(int(elapsed), 60)
    if result.returncode == 0:
        print(f"\n  OK ({mins}m {secs}s)")
    else:
        print(f"\n  FAILED (exit {result.returncode}, {mins}m {secs}s)")
    return result.returncode == 0


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

    elapsed = time.time() - start
    mins, secs = divmod(int(elapsed), 60)
    print(f"\n{'=' * 60}")
    print(f"  DONE: {steps_ok}/{steps_total} steps OK ({mins}m {secs}s)")
    print(f"{'=' * 60}\n")

    return 0 if steps_ok == steps_total else 1


if __name__ == "__main__":
    sys.exit(main())
