# SPDX-License-Identifier: AGPL-3.0-only
"""What a container restart may do to an already-written value (plan §10.1).

Two unconditional writers run on every boot and can reach columns the 2026-09
remediation is about to write:

* `api/services/card_descriptions.py`, imported by the API on startup, upserts
  `card_stats.card_description` from `public/data/card_descriptions.json`. It
  overwrites on purpose - the file is that column's authoritative copy and the
  import is the only path from a committed file to an existing row
  (`docs/procedures/CARD_DESCRIPTIONS.md:95`) - so the tests here pin two things
  at once: the overwrite survives (a fill-only variant would be a regression),
  and it can no longer be silent.
* `pipeline/lyra/orchestrator.py::_run_migrations` reconciles
  `unified_sites.name_normalized` on every Lyra start. Its old guard compared the
  stored value against itself, so a well-formed but stale key was durable: the
  site stayed unfindable under its own name forever.

Both are driven here through their real functions against recording fakes, so
these tests assert what the code sends to the database. No database needed.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.exc import ArgumentError
from sqlalchemy.sql.base import Executable

from api.services.card_descriptions import import_card_descriptions
from pipeline.lyra.site_key import site_key_sql

AN = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"
DELETED = "33333333-3333-3333-3333-333333333333"

CURATED_SOURCES = ("ancient_nerds", "lyra", "ancient_nerds_community")


# --------------------------------------------------------------------------
# fakes
# --------------------------------------------------------------------------


class _Result:
    def __init__(self, rows: list[Any], rowcount: int = 0) -> None:
        self._rows = rows
        self.rowcount = rowcount

    def fetchall(self) -> list[Any]:
        return self._rows

    def fetchone(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> Any:
        # The real one raises unless there is exactly one row.
        if len(self._rows) != 1:
            raise AssertionError(f"scalar_one() on {len(self._rows)} rows")
        return self._rows[0][0]


class _Conn:
    """Records every statement; answers from `rows_for` by fragment match."""

    def __init__(
        self, log: list[tuple[str, dict[str, Any]]], rows_for: dict[str, list[Any]] | None = None
    ) -> None:
        self.log = log
        self.rows_for = rows_for or {}

    def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> _Result:
        # The real Session/Connection of SQLAlchemy 2 executes only Executable objects and raises
        # on a plain string. A fake that accepted strings let a startup import ship that failed
        # on every production boot (2026-09-22: "Textual SQL expression ... should be explicitly
        # declared as text(...)").
        if not isinstance(stmt, Executable):
            raise ArgumentError(
                f"SQLAlchemy 2 does not execute {type(stmt).__name__} - wrap raw SQL in text()"
            )
        sql = str(stmt)
        self.log.append((sql, dict(params or {})))
        for fragment, rows in self.rows_for.items():
            if fragment in sql:
                return _Result(rows, rowcount=len(rows))
        # An UPSERT reports one row per statement in the fakes below.
        if "ON CONFLICT" in sql:
            return _Result([], rowcount=1)
        return _Result([], rowcount=0)

    def commit(self) -> None:
        return None

    def __enter__(self) -> _Conn:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class _Engine:
    def __init__(
        self, log: list[tuple[str, dict[str, Any]]], rows_for: dict[str, list[Any]] | None = None
    ) -> None:
        self.log = log
        self.rows_for = rows_for

    def connect(self) -> _Conn:
        return _Conn(self.log, self.rows_for)


def _upserts(log: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    return [
        params
        for sql, params in log
        if "INSERT INTO card_stats" in sql and "ON CONFLICT (site_id)" in sql
    ]


# --------------------------------------------------------------------------
# card_stats.card_description — the file stays authoritative, but loudly
# --------------------------------------------------------------------------


def test_card_description_import_still_overwrites_a_differing_value():
    """The documented carrier chain keeps working: a committed file wins.

    A fill-only variant (`WHERE card_description IS NULL`) would make the
    overwrite impossible and break the only path from an edited file to an
    existing production row. This pins the overwriting upsert.
    """
    log: list[tuple[str, dict[str, Any]]] = []
    conn = _Conn(log, {"FROM card_stats": [(AN, "the deployed old text")]})

    result = import_card_descriptions(conn, {AN: "the new text"})

    upsert_sql = next(sql for sql, _ in log if "INSERT INTO card_stats" in sql)
    assert "ON CONFLICT (site_id) DO UPDATE SET card_description" in upsert_sql
    assert "IS DISTINCT FROM :desc" in upsert_sql
    assert _upserts(log) == [{"id": AN, "desc": "the new text"}]
    assert result["imported"] == 1


def test_every_discarded_card_description_is_reported_and_logged(caplog):
    """A card text that exists only in the database is lost at the next boot.

    Losing it is the price of the file being authoritative; losing it without a
    trace is the defect. The site id and both values must appear in the boot log.
    """
    log: list[tuple[str, dict[str, Any]]] = []
    conn = _Conn(log, {"FROM card_stats": [(AN, "only in the database")]})

    with caplog.at_level(logging.WARNING, logger="api.services.card_descriptions"):
        result = import_card_descriptions(conn, {AN: "from the file"})

    assert result["discarded"] == [(AN, "only in the database", "from the file")]
    warnings = "\n".join(r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING)
    assert AN in warnings
    assert "only in the database" in warnings
    assert "from the file" in warnings


def test_identical_card_description_is_not_a_discard(caplog):
    """The normal boot must stay quiet: nothing was replaced, nothing is logged."""
    log: list[tuple[str, dict[str, Any]]] = []
    conn = _Conn(log, {"FROM card_stats": [(AN, "same text")]})

    with caplog.at_level(logging.WARNING, logger="api.services.card_descriptions"):
        result = import_card_descriptions(conn, {AN: "same text"})

    assert result["discarded"] == []
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.parametrize("stored", [None, ""])
def test_empty_card_description_is_filled_not_reported(stored):
    """Filling an empty slot replaces nothing."""
    log: list[tuple[str, dict[str, Any]]] = []
    conn = _Conn(log, {"FROM card_stats": [(AN, stored)]})

    result = import_card_descriptions(conn, {AN: "first text"})

    assert result["discarded"] == []
    assert _upserts(log) == [{"id": AN, "desc": "first text"}]


def test_truncation_happens_before_the_comparison():
    """A 250-char file value that only needs cutting is not a discard.

    `card_stats.card_description` is VARCHAR(200); comparing the untruncated
    file value would report every over-long draft as a lost database value.
    """
    log: list[tuple[str, dict[str, Any]]] = []
    conn = _Conn(log, {"FROM card_stats": [(AN, "x" * 200)]})

    result = import_card_descriptions(conn, {AN: "x" * 250})

    assert result["discarded"] == []
    assert _upserts(log) == [{"id": AN, "desc": "x" * 200}]


def test_deleted_site_ids_are_skipped_and_reported(caplog):
    log: list[tuple[str, dict[str, Any]]] = []
    conn = _Conn(log, {"FROM card_stats": [(AN, "old")]})
    # `_stale_ids_sql` returns the ids that are not in unified_sites.
    stale_rows = [(DELETED,)]
    conn.rows_for["EXCEPT SELECT id FROM unified_sites"] = stale_rows

    with caplog.at_level(logging.WARNING, logger="api.services.card_descriptions"):
        result = import_card_descriptions(conn, {AN: "new", DELETED: "orphan"})

    assert result["stale"] == [DELETED]
    assert _upserts(log) == [{"id": AN, "desc": "new"}]
    assert any(DELETED in r.getMessage() for r in caplog.records)


def test_api_startup_uses_the_service_and_carries_no_upsert_of_its_own():
    """The API boot path must go through the reporting import, not a bare upsert.

    Read as source on purpose: importing api.main builds the app and its routers
    (see tests/conftest.py), which the DB-less gate has no use for.
    """
    source = (Path(__file__).resolve().parents[2] / "api" / "main.py").read_text(encoding="utf-8")

    assert "import_card_descriptions(" in source
    assert "INSERT INTO card_stats" not in source


# --------------------------------------------------------------------------
# unified_sites.name_normalized — reconcile the curated key with its producer
# --------------------------------------------------------------------------

NAME_KEY = site_key_sql("name")


def _name_key_reconciliations(log: list[tuple[str, dict[str, Any]]]) -> list[str]:
    """The curated-source reconciliation, not the global in-place repair."""
    return [sql for sql, _ in log if NAME_KEY in sql and "source_id IN (" in sql]


def _run_migrations_log() -> list[tuple[str, dict[str, Any]]]:
    import pipeline.lyra.orchestrator as orch

    log: list[tuple[str, dict[str, Any]]] = []
    # The boot asks pg_catalog before each schema statement (pipeline/utils/boot_ddl.py);
    # answer "present" to all of them, as production's up-to-date schema does.
    up_to_date = {"FROM pg_catalog.": [(True,)], "to_regclass(:relation_name)": [(True,)]}
    orch._run_migrations(_Engine(log, up_to_date))
    return log


def test_the_existing_diacritic_repair_is_kept():
    """The pre-existing repair is untouched by the new reconciliation."""
    log = _run_migrations_log()
    self_comparison = [
        sql
        for sql, _ in log
        if "SET name_normalized = left(lower(unaccent(name)), 500)" in sql
        and "IS DISTINCT FROM lower(unaccent(name_normalized))" in sql
    ]
    assert len(self_comparison) == 1


def test_migrations_reconcile_the_curated_name_key_with_its_producer():
    """One boot statement derives the key from `name` instead of from itself.

    Without it, a key that is well-formed but was derived from an older `name`
    survives every restart (production held 'Eridu' carrying 'eridu, sumeria'),
    and the site is invisible to matching under its own name.
    """
    reconciliations = _name_key_reconciliations(_run_migrations_log())

    assert len(reconciliations) == 1
    sql = reconciliations[0]
    assert f"SET name_normalized = {NAME_KEY}" in sql
    assert f"name_normalized IS DISTINCT FROM {NAME_KEY}" in sql


def test_the_reconciliation_is_scoped_to_the_curated_sources():
    """28 external sources key their own rows; a boot migration must not rewrite them.

    Measured 2026-09-20: 80,083 non-curated rows disagree with the producer
    expression (topostext 8,046 of 8,068), the curated rows just 1.
    """
    sql = _name_key_reconciliations(_run_migrations_log())[0]
    scope = re.search(r"WHERE source_id IN \(([^)]*)\)", sql)

    assert scope is not None, sql
    assert scope.group(1).replace(" ", "") == ",".join(f"'{s}'" for s in CURATED_SOURCES)


def test_the_reconciliation_matches_nothing_once_it_has_run():
    """Idempotent by construction: the guard is the value the statement writes.

    `IS DISTINCT FROM` is false for the value on the right-hand side, so a second
    boot over an already-reconciled row updates zero rows - the restart is a
    no-op rather than a repeated rewrite.
    """
    sql = _name_key_reconciliations(_run_migrations_log())[0]
    set_rhs = re.search(r"SET name_normalized = (.+?)\n", sql)
    guard_rhs = re.search(r"IS DISTINCT FROM (.+?)\n", sql)

    assert set_rhs is not None and guard_rhs is not None
    assert set_rhs.group(1).strip() == guard_rhs.group(1).strip()


# --------------------------------------------------------------------------
# restore_snapshot — description and raw_data come from the same snapshot
# --------------------------------------------------------------------------


def _restore_log(monkeypatch) -> list[tuple[str, dict[str, Any]]]:
    from api.services import snapshots

    log: list[tuple[str, dict[str, Any]]] = []
    db = _Conn(
        log,
        {
            "FROM db_snapshots": [
                SimpleNamespace(source_id="ancient_nerds", snapshot_type="upload")
            ],
            "FROM snapshot_rows WHERE snapshot_id": [SimpleNamespace(site_id=AN)],
        },
    )
    monkeypatch.setattr(snapshots, "create_snapshot", lambda *a, **k: "undo-snapshot-id")
    monkeypatch.setattr(snapshots, "cache_delete_pattern", lambda *a, **k: 0)

    snapshots.restore_snapshot(db, "snapshot-id", restored_by="tester")
    return log


def test_restore_carries_raw_data_from_the_same_snapshot_row(monkeypatch):
    """Restoring a description without its citations leaves them dangling.

    `raw_data` holds `description_citations`, the [N] markers of the description,
    and comes from the same `snapshot_rows.old_data`. The UPDATE branch used to
    omit it, so an old snapshot reverted the text while the newer citations of a
    later enrichment stayed behind - and `snapshot_rows` has no row for a site
    whose raw_data the restore never touched.
    """
    upsert = next(
        sql for sql, _ in _restore_log(monkeypatch) if "ON CONFLICT (id) DO UPDATE SET" in sql
    )

    assert "old_data->'raw_data'" in upsert  # the INSERT branch's source
    assert "raw_data = EXCLUDED.raw_data" in upsert  # ... and the same for edits


def test_restore_reverts_every_column_the_insert_branch_writes(monkeypatch):
    """Every column the snapshot holds for an existing row is restored from it.

    The INSERT branch and the DO UPDATE branch must name the same columns, or a
    restore means different things for a row it re-creates and a row it edits.
    """
    upsert = next(
        sql for sql, _ in _restore_log(monkeypatch) if "ON CONFLICT (id) DO UPDATE SET" in sql
    )
    insert_columns = upsert.split("FROM snapshot_rows")[0]
    update_columns = upsert.split("ON CONFLICT (id) DO UPDATE SET")[1]

    for column in ("name_normalized", "description", "raw_data", "period_end", "site_type"):
        assert (
            f"old_data->>'{column}'" in insert_columns or f"old_data->'{column}'" in insert_columns
        )
        assert f"{column} = EXCLUDED.{column}" in update_columns
