"""Wave 0 scoping contract (scripts/audit_enrich.py).

`run_mechanical_fixes` takes a candidate list and then used to ignore it in every statement,
reading it only for `stats['total_sites']`. Against production that meant statements over
1,759,676 rows across 28 sources where only 5,004 were the curated set - and the site_type
branch was a table-wide
`UPDATE unified_sites SET site_type = :canonical WHERE site_type = :raw`, rewriting every
source's rows sharing that value.

These tests run the real function against a recording fake connection, so they assert what the
code actually sends to the database rather than what a regex thinks of the source. No database
is needed, and nothing here is reimplemented: if the function stops scoping, these fail.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import audit_enrich  # noqa: E402

#: Every scoped statement must carry one of these. `CAST(:site_ids AS uuid[])` is the id-list
#: filter; `id = :sid` / `id = :site_id` are the single-row forms. A statement touching
#: unified_sites with none of them is the bug this file exists to catch.
SCOPE_MARKERS = ("CAST(:site_ids AS uuid[])", "id = :sid", "id = :site_id")


class _Result:
    def __init__(self, rows: list[Any], rowcount: int = 0) -> None:
        self._rows = rows
        self.rowcount = rowcount

    def fetchall(self) -> list[Any]:
        return self._rows


class _Conn:
    """Records every statement and returns canned rows for matching fragments."""

    def __init__(self, log: list[tuple[str, dict[str, Any]]], rows_for: dict[str, list[Any]]) -> None:
        self.log = log
        self.rows_for = rows_for

    def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> _Result:
        sql = str(stmt)
        self.log.append((sql, dict(params or {})))
        for fragment, rows in self.rows_for.items():
            if fragment in sql:
                return _Result(rows, rowcount=len(rows))
        return _Result([], 0)

    def commit(self) -> None:
        return None

    def __enter__(self) -> _Conn:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        # Returns None, not False: this context manager never suppresses an exception, and
        # returning a bool would imply it might.
        return None


class _Engine:
    def __init__(self, log: list[tuple[str, dict[str, Any]]], rows_for: dict[str, list[Any]]) -> None:
        self.log = log
        self.rows_for = rows_for

    def connect(self) -> _Conn:
        return _Conn(self.log, self.rows_for)


def _run(
    monkeypatch: pytest.MonkeyPatch,
    sites: list[dict[str, Any]],
    rows_for: dict[str, list[Any]] | None = None,
) -> tuple[dict[str, int], list[tuple[str, dict[str, Any]]]]:
    log: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(audit_enrich, "engine", _Engine(log, rows_for or {}))
    stats = audit_enrich.run_mechanical_fixes(sites)
    return stats, log


def test_empty_candidate_list_runs_no_statement(monkeypatch: pytest.MonkeyPatch) -> None:
    """The dangerous reading of an empty list is "no filter, so do everything".

    Nothing at all may reach the database - not even the statement_timeout SET - because the
    only safe behaviour for an empty candidate list is to do nothing.
    """
    stats, log = _run(monkeypatch, [])
    assert log == [], f"an empty candidate list still executed: {[s for s, _ in log]}"
    assert stats["total_sites"] == 0
    assert stats["site_type_normalized"] == 0
    assert stats["period_name_recomputed"] == 0
    assert stats["country_filled"] == 0
    assert stats["suspect_modern_flagged"] == 0


def test_every_statement_reaching_unified_sites_is_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    """No statement may offer to touch more rows than the candidate list allows."""
    sites = [{"site_id": "11111111-1111-1111-1111-111111111111"},
             {"site_id": "22222222-2222-2222-2222-222222222222"}]
    # Make every branch produce work, so no scoped statement is merely absent from the log.
    rows_for: dict[str, list[Any]] = {
        "SELECT id::text, name, site_type": [
            SimpleNamespace(
                id="11111111-1111-1111-1111-111111111111",
                name="Wildlife Sanctuary X",
                site_type="Unknown",
            )
        ],
        "SELECT DISTINCT site_type": [("dolmen",)],
        "SELECT id::text AS site_id, period_start, period_name": [
            SimpleNamespace(site_id="11111111-1111-1111-1111-111111111111",
                            period_start=-3000, period_name="Neolithic")
        ],
        "SELECT id::text AS site_id, lat, lon": [
            SimpleNamespace(site_id="22222222-2222-2222-2222-222222222222", lat=1.0, lon=2.0)
        ],
    }
    _, log = _run(monkeypatch, sites, rows_for)

    touching = [(sql, params) for sql, params in log if "unified_sites" in sql]
    assert touching, "expected the fake rows to drive at least one statement"

    unscoped = [
        " ".join(sql.split())
        for sql, _ in touching
        if not any(marker in sql for marker in SCOPE_MARKERS)
    ]
    assert unscoped == [], f"unscoped statement(s) reached the database: {unscoped}"

    # A statement carrying the placeholder must also receive the ids, or the filter is hollow.
    for sql, params in touching:
        if "CAST(:site_ids AS uuid[])" in sql:
            assert params.get("site_ids"), f"missing site_ids param for: {' '.join(sql.split())}"


def test_the_table_wide_site_type_update_is_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    """The specific regression: this statement used to rewrite all 28 sources.

    `UPDATE unified_sites SET site_type = :canonical WHERE site_type = :raw` with no id filter
    hits every row in the table that shares the raw value. Assert the executed form carries the
    candidate filter.
    """
    sites = [{"site_id": "11111111-1111-1111-1111-111111111111"}]
    _, log = _run(monkeypatch, sites, {"SELECT DISTINCT site_type": [("dolmen",)]})

    updates = [sql for sql, _ in log if "UPDATE unified_sites SET site_type" in sql]
    assert updates, "the site_type normalization branch did not run"
    for sql in updates:
        assert "CAST(:site_ids AS uuid[])" in sql, (
            f"site_type UPDATE is table-wide: {' '.join(sql.split())}"
        )
