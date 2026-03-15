#!/usr/bin/env python3
"""Sync Qdrant collections from production to local.

Uses Qdrant's snapshot API: creates snapshot on prod, downloads it, restores locally.
Requires SSH tunnel to prod Qdrant (port 6333 isn't exposed publicly).

Usage:
    # Step 1: Open SSH tunnel to prod Qdrant in another terminal:
    ssh -L 16333:localhost:6333 deploy@213.199.53.42

    # Step 2: Run sync (defaults: prod=localhost:16333, local=localhost:6333):
    python scripts/sync_qdrant.py

    # Sync specific collections only:
    python scripts/sync_qdrant.py --collections news transcripts

    # Custom ports:
    python scripts/sync_qdrant.py --prod-port 16333 --local-port 6333
"""

import argparse
import os
import sys
import tempfile
import time

import httpx

COLLECTIONS = ["sites", "news", "transcripts", "articles", "empires"]


def get_collection_info(base_url: str, name: str) -> dict | None:
    try:
        r = httpx.get(f"{base_url}/collections/{name}", timeout=10)
        if r.status_code == 200:
            return r.json()["result"]
    except Exception:
        pass
    return None


def create_snapshot(base_url: str, collection: str) -> str:
    """Create a snapshot on the remote and return the snapshot name."""
    print(f"  Creating snapshot for '{collection}'...", end=" ", flush=True)
    r = httpx.post(f"{base_url}/collections/{collection}/snapshots", timeout=120)
    r.raise_for_status()
    snapshot = r.json()["result"]
    name = snapshot["name"]
    size_mb = snapshot.get("size", 0) / 1024 / 1024
    print(f"{name} ({size_mb:.1f} MB)")
    return name


def download_snapshot(base_url: str, collection: str, snapshot_name: str, dest: str) -> str:
    """Download snapshot file to local path."""
    url = f"{base_url}/collections/{collection}/snapshots/{snapshot_name}"
    print(f"  Downloading...", end=" ", flush=True)
    with httpx.stream("GET", url, timeout=300) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        path = os.path.join(dest, f"{collection}_{snapshot_name}")
        downloaded = 0
        with open(path, "wb") as f:
            for chunk in r.iter_bytes(8192):
                f.write(chunk)
                downloaded += len(chunk)
        size_mb = downloaded / 1024 / 1024
        print(f"{size_mb:.1f} MB")
    return path


def delete_remote_snapshot(base_url: str, collection: str, snapshot_name: str):
    """Clean up snapshot on remote."""
    try:
        httpx.delete(f"{base_url}/collections/{collection}/snapshots/{snapshot_name}", timeout=30)
    except Exception:
        pass


def restore_snapshot(local_url: str, collection: str, snapshot_path: str):
    """Upload snapshot to local Qdrant."""
    print(f"  Restoring to local...", end=" ", flush=True)
    # Delete existing collection first
    httpx.delete(f"{local_url}/collections/{collection}", timeout=30)
    time.sleep(0.5)

    # Upload snapshot via multipart form (required by Qdrant 1.x)
    with open(snapshot_path, "rb") as f:
        r = httpx.post(
            f"{local_url}/collections/{collection}/snapshots/upload",
            files={"snapshot": (os.path.basename(snapshot_path), f, "application/octet-stream")},
            timeout=300,
        )
    r.raise_for_status()
    print("done")


def main():
    parser = argparse.ArgumentParser(description="Sync Qdrant from prod to local")
    parser.add_argument("--prod-port", type=int, default=16333,
                        help="Local port forwarded to prod Qdrant (default: 16333)")
    parser.add_argument("--local-port", type=int, default=6333,
                        help="Local Qdrant port (default: 6333)")
    parser.add_argument("--collections", nargs="+", default=COLLECTIONS,
                        help=f"Collections to sync (default: {COLLECTIONS})")
    args = parser.parse_args()

    prod_url = f"http://localhost:{args.prod_port}"
    local_url = f"http://localhost:{args.local_port}"

    # Verify connectivity
    print(f"Prod Qdrant ({prod_url}):")
    try:
        r = httpx.get(f"{prod_url}/collections", timeout=5)
        prod_collections = [c["name"] for c in r.json()["result"]["collections"]]
        print(f"  Connected — {len(prod_collections)} collections")
    except Exception as e:
        print(f"  FAILED: {e}")
        print(f"\n  Did you open the SSH tunnel?")
        print(f"  ssh -L {args.prod_port}:localhost:6333 deploy@213.199.53.42")
        sys.exit(1)

    print(f"\nLocal Qdrant ({local_url}):")
    try:
        r = httpx.get(f"{local_url}/collections", timeout=5)
        local_collections = [c["name"] for c in r.json()["result"]["collections"]]
        print(f"  Connected — {len(local_collections)} collections")
    except Exception as e:
        print(f"  FAILED: {e}")
        print(f"  Is local Qdrant running? docker compose up -d qdrant")
        sys.exit(1)

    # Show what we're syncing
    print(f"\nCollections to sync: {args.collections}")
    for col in args.collections:
        prod_info = get_collection_info(prod_url, col)
        local_info = get_collection_info(local_url, col)
        prod_count = prod_info["points_count"] if prod_info else "N/A"
        local_count = local_info["points_count"] if local_info else "N/A"
        print(f"  {col}: prod={prod_count}, local={local_count}")

    print()
    confirm = input("Proceed? This will REPLACE local collections. [y/N] ")
    if confirm.lower() != "y":
        print("Aborted.")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        for col in args.collections:
            if col not in prod_collections:
                print(f"\n[{col}] Not found on prod, skipping")
                continue

            print(f"\n[{col}]")
            try:
                snap_name = create_snapshot(prod_url, col)
                snap_path = download_snapshot(prod_url, col, snap_name, tmpdir)
                restore_snapshot(local_url, col, snap_path)
                delete_remote_snapshot(prod_url, col, snap_name)

                # Verify
                info = get_collection_info(local_url, col)
                if info:
                    print(f"  Verified: {info['points_count']} points")
            except Exception as e:
                print(f"  ERROR: {e}")

    print("\nSync complete!")


if __name__ == "__main__":
    main()
