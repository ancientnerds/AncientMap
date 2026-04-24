"""One-shot swap of a Theo research payload between two request_ids.

Usage:
    python scripts/swap_theo_payload.py --old <uuid> --new <uuid>

Takes the result_json and published_at from NEW and writes them into
OLD (preserving OLD's slug so the existing URL continues to serve).
NEW is marked as superseded so it doesn't double-publish.

This is the post-regen payload swap for the Shining Ones fix: after
the pipeline regenerates the paper into a new request_id, we atomically
move the new content under the existing public slug.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys

# Load .env so DB credentials come from the same place the pipeline uses.
try:
    for line in pathlib.Path(".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
except FileNotFoundError:
    pass

from sqlalchemy import text  # noqa: E402

from pipeline.database import get_session  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", required=True, help="Request ID to keep (URL stays)")
    parser.add_argument("--new", required=True, help="Request ID to consume (content source)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with get_session() as session:
        new_row = session.execute(
            text(
                "SELECT id::text, result_json, published_at, slug "
                "FROM research_requests WHERE id = :id"
            ),
            {"id": args.new},
        ).fetchone()
        if not new_row:
            print(f"ERROR: new row {args.new} not found", file=sys.stderr)
            return 2

        old_row = session.execute(
            text("SELECT id::text, slug, is_public FROM research_requests WHERE id = :id"),
            {"id": args.old},
        ).fetchone()
        if not old_row:
            print(f"ERROR: old row {args.old} not found", file=sys.stderr)
            return 2

        print(
            f"OLD {args.old} (slug={old_row.slug}, public={old_row.is_public}) "
            f"<- NEW {args.new} (slug={new_row.slug})"
        )
        if args.dry_run:
            print("DRY RUN - no changes")
            return 0

        # Move content: old keeps its id, slug, url; takes new's result_json and published_at.
        session.execute(
            text(
                """
                UPDATE research_requests
                SET result_json = :result,
                    published_at = :pub
                WHERE id = :id
                """
            ),
            {
                "id": args.old,
                "result": new_row.result_json,
                "pub": new_row.published_at,
            },
        )
        # Mark new row as superseded so it doesn't keep serving under its slug.
        session.execute(
            text(
                "UPDATE research_requests SET is_public = FALSE, status = 'superseded' "
                "WHERE id = :id"
            ),
            {"id": args.new},
        )
        session.commit()
    print("Swap complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
