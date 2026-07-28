"""Scan / repair citation integrity of stored Theo research papers.

Runs validate_paper_artifact over every completed research_requests row and
optionally applies the deterministic repair_artifact (never fabricates or
remaps a citation — unrepairable papers are reported and left untouched).

Usage (inside the api container, or locally with DATABASE_URL on the tunnel):

  docker exec ancient_nerds_api python scripts/repair_theo_citations.py
  docker exec ancient_nerds_api python scripts/repair_theo_citations.py --apply <id> [<id> ...]
  docker exec ancient_nerds_api python scripts/repair_theo_citations.py --apply --all-dirty

Local (Bitvise tunnel, psql port 15432):
  DATABASE_URL=postgresql://ancient_map:<pw>@localhost:15432/ancient_map \\
    python scripts/repair_theo_citations.py

For published papers whose published_report changed, re-run Qdrant indexing
on the VPS afterwards (pipeline.lyra.theo_research_index) — this script only
prints a reminder, it does not reach Qdrant.

Note on `report` vs `published_report`: a row is only ever HELD (left
untouched, no DB write) when the main `report` field can't reach a clean
state. If `report` repairs clean but the row is public and its separate
`published_report` field cannot be repaired clean, the row is still written
and printed as FIXED (the `report` field genuinely is fixed) — but a
`PUB-HOLD` line is also printed calling out that the public-facing text
remains dirty, so this doesn't get silently missed. The persisted `audit`
field is always recomputed from the final stored artifact-of-record
(`published_report` when present, else `report`) — matching the publish
route's semantics — so a PUB-HOLD row correctly persists `audit.passed=False`
even though the `report` field itself is clean.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from pipeline.database import get_session  # noqa: E402
from pipeline.lyra.theo_citations import repair_artifact, validate_paper_artifact  # noqa: E402


def _fetch_rows(session):
    return session.execute(
        text("""
            SELECT id::text, slug, is_public, result_json
            FROM research_requests
            WHERE status = 'completed' AND result_json IS NOT NULL
            ORDER BY created_at
        """)
    ).fetchall()


def _repair_field(result: dict, field: str) -> tuple[bool, dict]:
    """Repair one markdown field in result_json. Returns (changed, report)."""
    original = result.get(field) or ""
    if not original:
        return False, {"passed": False, "issues": [f"{field} empty"]}
    repaired, report = repair_artifact(original)
    if report["passed"] and repaired != original:
        result[field] = repaired
        return True, report
    return False, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--apply",
        nargs="*",
        metavar="ID",
        default=None,
        help="Repair the given request ids (with --all-dirty: every failing row)",
    )
    ap.add_argument(
        "--all-dirty",
        action="store_true",
        help="With --apply: repair every row that fails validation",
    )
    args = ap.parse_args()

    apply_ids = set(args.apply or [])
    dirty = held = clean = 0

    with get_session() as session:
        for row in _fetch_rows(session):
            result = json.loads(row.result_json)
            report_md = result.get("report") or ""
            verdict = validate_paper_artifact(report_md)
            if verdict["passed"]:
                clean += 1
                continue

            dirty += 1
            label = row.slug or row.id
            print(f"\nDIRTY  {row.id}  ({label})  public={row.is_public}")
            for issue in verdict["issues"][:8]:
                print(f"       - {issue}")

            should_apply = args.apply is not None and (args.all_dirty or row.id in apply_ids)
            if not should_apply:
                continue

            changed, rep = _repair_field(result, "report")
            pub_changed = False
            pub_rep: dict | None = None
            if result.get("published_report"):
                pub_changed, pub_rep = _repair_field(result, "published_report")
            if not rep["passed"]:
                held += 1
                print(f"HOLD   {row.id} — repair could not reach clean:")
                for issue in rep["issues"][:5]:
                    print(f"       - {issue}")
                continue

            # The audit must describe the artifact readers see: the published
            # view when one exists, else the report (matches the publish
            # route's semantics). Recompute from the FINAL stored text —
            # _repair_field's verdict can refer to a non-adopted repair.
            final_md = result.get("published_report") or result.get("report") or ""
            result["audit"] = validate_paper_artifact(final_md)
            session.execute(
                text("UPDATE research_requests SET result_json = :r WHERE id = :id"),
                {"id": row.id, "r": json.dumps(result)},
            )
            session.commit()
            print(
                f"FIXED  {row.id}  (report={'yes' if changed else 'already-clean'}, "
                f"published_report={'yes' if pub_changed else 'n/a'})"
            )
            if row.is_public and pub_changed:
                print(f"       NOTE: re-index {row.id} in Qdrant on the VPS")
            if row.is_public and pub_rep is not None and not pub_rep["passed"]:
                print(
                    f"       PUB-HOLD {row.id} — published_report still fails validation, left untouched:"
                )
                for issue in pub_rep["issues"][:5]:
                    print(f"              - {issue}")

    print(f"\nScanned: clean={clean} dirty={dirty} held={held}")
    return 1 if (dirty and args.apply is None) else 0


if __name__ == "__main__":
    raise SystemExit(main())
