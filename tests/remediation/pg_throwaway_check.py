"""Run lane WN's and the site-list runs' real write transactions against a throwaway Postgres.

Not a test (no `test_` prefix, never collected, needs Docker): the writer's SQL is otherwise only ever
executed by the fake psql of `phase4_write_fixtures` (which mirrors its guards in Python) and, for
real, by a production rehearsal. This renders the very statements the gate sends - apply, rehearsal
(ends in ROLLBACK), the reversal's proof and its committed reversal - over synthetic rows of the test
fixtures and runs them in a container with nothing of the project in it: no host port, no data, no
secret. It is the first real execution of invariant 6's `CASE` (lane N for a lane-WN text, the old
lane for a Phase-4 text), of guard 4 with a NULL and a blank old description, and of the reversal that
writes NULL back.

    docker run -d --name wn-sqltest -e POSTGRES_PASSWORD=x postgres:16-alpine
    PYTHONPATH="<repo>;<repo>/scripts/remediation" <repo>/.venv/Scripts/python.exe \\
        tests/remediation/pg_throwaway_check.py wn-sqltest
    docker rm -f wn-sqltest

Never point it at the project's own database container (`ancient_nerds_db`): it truncates the tables
it creates. Measured 2026-10-01 on postgres:16-alpine: every step ran, the edited lane stopped at
invariant 6.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _path in (REPO, REPO / "scripts" / "remediation", REPO / "output" / "remediation" / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from tests.remediation import test_wc_list as TL  # noqa: E402
from tests.remediation import test_wn_write as TW  # noqa: E402
from tests.remediation import wn_fixtures as WX  # noqa: E402
from tests.remediation.phase4_write_fixtures import W4  # noqa: E402

MIGRATIONS = (
    "0017_remediation_change_log.sql",
    "0018_remediation_change_log_boolean.sql",
    "0022_remediation_change_by_key.sql",
)
SCHEMA = (
    "DROP TABLE IF EXISTS unified_sites, card_stats; "
    "CREATE TABLE unified_sites (id uuid PRIMARY KEY, source_id text, name text, "
    "description text, raw_data jsonb, scope_status text); "
    "CREATE TABLE card_stats (site_id uuid, card_description varchar(200));"
)
STATE = (
    "SELECT id, description IS NULL, left(coalesce(description, ''), 30), "
    "raw_data->'_description_provenance'->>'lane', raw_data IS NULL "
    "FROM unified_sites ORDER BY id;"
)


class Container:
    def __init__(self, name: str) -> None:
        self.name = name

    def psql(self, sql: str, *, check: bool = True) -> str:
        proc = subprocess.run(
            ["docker", "exec", "-i", self.name, "psql", "-U", "postgres", "-v", "ON_ERROR_STOP=1", "-At"],
            input=sql, capture_output=True, text=True, encoding="utf-8",
        )  # fmt: skip
        if check and proc.returncode != 0:
            raise SystemExit(f"psql failed:\n{proc.stderr}\n{proc.stdout[-2000:]}")
        return proc.stdout + proc.stderr

    def migrate(self) -> None:
        self.psql(SCHEMA)
        for name in MIGRATIONS:
            self.psql((REPO / "migrations" / name).read_text(encoding="utf-8"))

    def load(self, rows: list[dict]) -> None:
        def lit(value: str | None) -> str:
            return "NULL" if value is None else "'" + value.replace("'", "''") + "'"

        statements = ["TRUNCATE unified_sites; TRUNCATE remediation_change_log;"]
        for row in rows:
            raw = (
                None if row["raw_data"] is None else json.dumps(row["raw_data"], ensure_ascii=False)
            )
            statements.append(
                "INSERT INTO unified_sites (id, source_id, name, description, raw_data) VALUES "
                f"('{row['id']}', 'ancient_nerds', {lit(row['name'])}, {lit(row['description'])}, "
                f"{lit(raw)}::jsonb);"
            )
        self.psql("\n".join(statements))


def run_chunk(db: Container, plan_path: Path, rows: list[dict], label: str) -> W4.Chunk4:
    batches, outcomes = W4.load_wc_plan([plan_path])
    (batch,) = batches
    live = {r["id"]: {"description": r["description"], "raw_data": r["raw_data"]} for r in rows}
    plan = W4.plan_wc(batch, outcomes=outcomes, live=live)
    assert not plan.refusals, plan.refusals
    chunk = W4.chunk_for(plan)
    print(f"== {label}: {len(chunk.rows)} rows, {len(chunk.site_ids)} sites")
    db.load(rows)
    before = db.psql(STATE)
    print("rehearsal:", db.psql(W4.render_apply(chunk, rehearse=True)).strip().splitlines()[-1])
    assert db.psql(STATE) == before, "the rehearsal changed something"
    print("apply:", db.psql(W4.render_apply(chunk)).strip().splitlines()[-1])
    written = db.psql(STATE)
    assert written != before, "the write changed nothing"
    print(written)
    print("reversal proof:", db.psql(W4.render_rollback(chunk)).strip().splitlines()[-1])
    assert db.psql(STATE) == written, "the rolled-back proof changed something"
    db.psql(W4.render_rollback(chunk).replace("\nROLLBACK;\n", "\nCOMMIT;\n"))
    assert db.psql(STATE) == before, "the committed reversal did not restore the old values"
    print("reversal restores the old values (NULL and blank included)")
    return chunk


def main(container: str) -> None:
    db = Container(container)
    db.migrate()
    tmp = Path(tempfile.mkdtemp())
    wn_plan = WX.build_wn_run(tmp / "wn", TW._rows(), TW._answers(), name="wn-pilot")[1]
    run_chunk(db, wn_plan, TW._rows(), "lane WN (NULL and blank old descriptions)")
    rows = TL._p4_rows()
    ids = [TL.SITE_P4, TL.SITE_ALL, TL.SITE_NONE, TL.SITE_MIS, TL.SITE_RET]
    list_plan = WX.build_list_run(
        tmp / "wl", rows, ids, TL._p4_answers(), pilot=True, name="wcl-pilot"
    )[1]
    chunk = run_chunk(db, list_plan, rows, "site-list run (Phase-4 texts)")
    # invariant 6 holds the provenance to the marking's lane: edit the rendered statement
    sql = W4.render_apply(chunk, rehearse=True)
    (line,) = [
        r for r in sql.splitlines()
        if r.lstrip().startswith(f"('{TL.SITE_P4}'::uuid, 'unified_sites', 'raw_data'")
    ]  # fmt: skip
    at = line.rfind('"lane": "W"')
    db.load(rows)
    out = db.psql(
        sql.replace(line, line[:at] + '"lane": "S"' + line[at + len('"lane": "W"') :]), check=False
    )
    assert "break the provenance or clear invariant" in out, out
    print("a provenance of another lane than the marking's stops at invariant 6")
    print("ALL OK")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "wn-sqltest")
