"""Read-only diagnostic: print audit_result + quality_score for a Theo run.

Usage:
    python scripts/inspect_run_result.py <request_id>

Reads the `result_json` JSONB column from research_requests on the local DB
(via SQLAlchemy session). Prints the audit gate counts + quality dimensions
so we can tell WHY a run got demoted to "Unverified" when its quality_score
is otherwise high.

Useful on prod via the localhost:15432 tunnel:
    python scripts/inspect_run_result.py 2f055c7e-d61c-4310-91eb-cd404249d303
"""

from __future__ import annotations

import json
import sys

from sqlalchemy import text

from pipeline.database import get_session


def main(request_id: str) -> int:
    with get_session() as session:
        row = session.execute(
            text("SELECT result_json FROM research_requests WHERE id = :id"),
            {"id": request_id},
        ).fetchone()
    if not row or not row[0]:
        print("no result_json on row", file=sys.stderr)
        return 2

    data = json.loads(row[0])

    print("=== audit_gate_failures ===")
    audit = data.get("audit_gate_failures")
    if audit is None:
        audit = data.get("audit", {})
    print(json.dumps(audit, indent=2, default=str))

    print()
    print("=== quality_score ===")
    print(json.dumps(data.get("quality_score", {}), indent=2, default=str))

    print()
    print("=== top-level keys ===")
    print(", ".join(sorted(data.keys())))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            "usage: python scripts/inspect_run_result.py <request_id>",
            file=sys.stderr,
        )
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
