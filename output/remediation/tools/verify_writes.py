"""The acceptance for the write wave: the journal says what changed, the database must agree.

A check the writer's own driver runs is not an acceptance, so this asks production directly - in both
directions. Every journal row for this wave must find its new value in the database, and every planned
row *without* a journal row must still hold its old value, which covers the withheld and the
boundary-refused rows in the same pass.

    ./.venv/Scripts/python.exe output/remediation/logs/verify_writes.py
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

LOGS = pathlib.Path(__file__).resolve().parent
ROWS = LOGS / "_write_dry" / "ALL_ROWS.jsonl"
HOST = "ancientnerds"
COLUMNS = ("site_type", "period_start", "country")
PSQL = "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v ON_ERROR_STOP=1 -t -A -F '|'"


def read_jsonl(path: pathlib.Path) -> list[dict]:
    records: list[dict] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{number}: not readable JSON: {exc}") from exc
    return records


def psql(sql: str) -> list[list[str]]:
    result = subprocess.run(
        ["ssh", HOST, PSQL],
        input=sql.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"psql failed ({result.returncode}): {result.stderr.decode('utf-8', 'replace')}"
        )
    return [line.split("|") for line in result.stdout.decode("utf-8").splitlines() if line]


def stored_values(ids: list[str]) -> dict[str, list[str]]:
    """Read all three columns for these sites, in one query."""
    rows: dict[str, list[str]] = {}
    columns = ", ".join(COLUMNS)
    for start in range(0, len(ids), 200):
        window = ids[start : start + 200]
        sql = (
            f"SELECT id, {columns} FROM unified_sites WHERE id IN ('"
            + "', '".join(window)
            + "');\n"
        )
        for row in psql(sql):
            rows[row[0]] = row[1:]
    return rows


def main() -> int:
    planned = read_jsonl(ROWS)
    journal = psql(
        "SELECT column_name, row_pk, old_value, new_value FROM remediation_change_log "
        "WHERE run_stamp LIKE 'phase3:batch-%' AND run_stamp NOT LIKE '%-rollback' ORDER BY id;\n"
    )
    changed = {(column, pk) for column, pk, _old, _new in journal if column in COLUMNS}
    print(
        f"Journaleintraege dieser Welle: {len(journal)} | davon in den drei Feldern: {len(changed)}"
    )

    ids = sorted({row["pk"] for row in planned})
    stored = stored_values(ids)
    print(f"aus der Datenbank gelesen: {len(stored)} von {len(ids)} Sites")

    bad = 0
    for column, pk, _old, new in journal:
        if column not in COLUMNS:
            continue
        found = stored.get(pk)
        if found is None:
            print(f"  FEHLT      {pk} ({column})")
            bad += 1
        elif found[COLUMNS.index(column)] != new:
            print(
                f"  NICHT NEU  {pk} {column}: erwartet {new!r}, gelesen {found[COLUMNS.index(column)]!r}"
            )
            bad += 1

    untouched = 0
    for row in planned:
        if (row["column"], row["pk"]) in changed:
            continue
        untouched += 1
        found = stored.get(row["pk"])
        if found is None:
            print(f"  FEHLT      {row['site_name']} ({row['pk']})")
            bad += 1
        elif found[COLUMNS.index(row["column"])] != str(row["old_value"]):
            print(
                f"  DOCH GE\u00c4NDERT {row['site_name'][:34]:35} {row['column']:12} "
                f"erwartet alt {row['old_value']!r}, gelesen {found[COLUMNS.index(row['column'])]!r}"
            )
            bad += 1

    print(
        f"\n{len(changed)} Zeilen tragen den neuen Wert, {untouched} geplante Zeilen tragen "
        f"unveraendert den alten, davon {len(stored)} Sites gelesen"
    )
    print(f"ERGEBNIS: {bad} Abweichungen")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
