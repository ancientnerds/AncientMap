#!/usr/bin/env python3
"""Bulk-insert all ENTITAET prompts directly into research_requests as queued.

Bypasses the API (MAX_REQUESTS_PER_USER=1) by writing rows directly to the DB.
The Theo worker picks them up FIFO via:
  SELECT ... FROM research_requests WHERE status='queued' ORDER BY created_at ASC LIMIT 1

Skips slugs that already have a <slug>.md in the local reports dir (polygonal-masonry,
gobekli-tepe). User sees them in their theo.html UI as queued/running tasks.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

UID = "442000112756064260"
PROMPTS_DIR = Path("/home/deploy/theo_batch/prompts")
SQL_OUT = Path("/tmp/bulk_insert.sql")  # noqa: S108 — one-shot ops script on the VPS
SKIP_SLUGS = {"polygonal-masonry", "gobekli-tepe"}


def main() -> int:
    files = sorted(PROMPTS_DIR.glob("T*.txt"))
    inserts: list[str] = []
    for i, f in enumerate(files):
        m = re.match(r"T\d+_(.+)\.txt", f.name)
        if not m:
            continue
        slug = m.group(1)
        if slug in SKIP_SLUGS:
            print(f"SKIP {slug}", file=sys.stderr)
            continue
        q = f.read_text(encoding="utf-8").strip()
        q_esc = q.replace("'", "''")
        inserts.append(
            f"INSERT INTO research_requests "
            f"(id, user_id, question, effort, status, specialist_options, is_batch, created_at) "
            f"VALUES (gen_random_uuid(), '{UID}', '{q_esc}', 'research', 'queued', "
            f"NULL, TRUE, NOW() + interval '{i} seconds');"
        )
    SQL_OUT.write_text("\n".join(inserts) + "\n", encoding="utf-8")
    print(f"wrote {len(inserts)} inserts to {SQL_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
