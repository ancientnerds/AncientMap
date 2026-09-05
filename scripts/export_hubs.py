"""Refresh the homepage hub lists: country pages + public research papers.

Thin CLI over pipeline.static_exporter.export_hubs_snapshot(). The snapshot
normally refreshes itself — every full static export writes it, and so do
the Theo publish, auto-publish and unpublish paths — and the frontend build
bakes it into index.html (vite.config.ts → landingHubs). Run this by hand
only to seed a fresh host or to refresh the committed dev/CI baseline:

    docker exec ancient_nerds_api python scripts/export_hubs.py        # VPS: public/data/hubs.snapshot.json
    python scripts/export_hubs.py --baseline                            # ancient-nerds-map/src/data/hubs.snapshot.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.static_exporter import build_hubs_snapshot, export_hubs_snapshot  # noqa: E402

BASELINE_PATH = PROJECT_ROOT / "ancient-nerds-map" / "src" / "data" / "hubs.snapshot.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="write the committed dev/CI copy (pretty-printed) instead of public/data",
    )
    args = parser.parse_args()

    if args.baseline:
        payload = build_hubs_snapshot()
        BASELINE_PATH.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        path = BASELINE_PATH
    else:
        payload = None
        path = export_hubs_snapshot()
        payload = json.loads(path.read_text(encoding="utf-8"))

    print(f"{path}: {len(payload['countries'])} countries, {len(payload['papers'])} papers")


if __name__ == "__main__":
    main()
