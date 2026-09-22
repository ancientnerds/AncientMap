# SPDX-License-Identifier: AGPL-3.0-only
"""pipeline/utils/public_sites.py and migration 0020: one spelling of "this site is shown".

The predicate is evaluated in a real SQL engine (SQLite supports ``IS DISTINCT FROM`` since
3.39) because its whole point is the NULL case: ``scope_status <> 'retired'`` is NULL, not
true, for a NULL row, so that spelling would hide every one of the ~1.76M sites nobody has
assessed. A string comparison in a test cannot show that; an engine does.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from pipeline.utils.public_sites import (
    RETIRED,
    SCOPE_STATUSES,
    is_retired,
    journal_join,
    last_change,
    not_retired,
)

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "0020_unified_sites_scope_status.sql"


@pytest.fixture
def engine() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE unified_sites (id TEXT, scope_status TEXT)")
    conn.executemany(
        "INSERT INTO unified_sites VALUES (?, ?)",
        [("never", None), ("kept", "in_scope"), ("open", "pending"), ("gone", "retired")],
    )
    return conn


def _ids(conn: sqlite3.Connection, where: str) -> set[str]:
    return {row[0] for row in conn.execute(f"SELECT id FROM unified_sites u WHERE {where}")}  # noqa: S608


def test_not_retired_shows_null_in_scope_and_pending_and_hides_retired(engine):
    assert _ids(engine, not_retired()) == {"never", "kept", "open"}
    assert _ids(engine, not_retired("u")) == {"never", "kept", "open"}


def test_the_naive_spelling_would_hide_every_unassessed_site(engine):
    """Why IS DISTINCT FROM: `<>` drops the NULL row - i.e. every site nobody assessed."""
    assert _ids(engine, "scope_status <> 'retired'") == {"kept", "open"}
    assert "IS DISTINCT FROM" in not_retired()


def test_is_retired_is_the_exact_complement(engine):
    shown = _ids(engine, not_retired())
    retired = _ids(engine, is_retired())
    assert retired == {"gone"}
    assert shown | retired == {"never", "kept", "open", "gone"}
    assert not shown & retired


@pytest.mark.parametrize("alias", ["us; DROP TABLE x", "u.id", "1us", "u s"])
def test_an_alias_that_is_not_an_identifier_is_refused(alias):
    with pytest.raises(ValueError):
        not_retired(alias)


def test_last_change_takes_the_later_of_the_row_and_its_journal():
    expr = last_change("u")
    assert expr == "GREATEST(COALESCE(u.updated_at, u.created_at), jlast.applied_at)"
    join = journal_join("u")
    assert join.startswith("LEFT JOIN (SELECT site_id_ref, MAX(applied_at AT TIME ZONE 'UTC')")
    assert join.endswith("jlast ON jlast.site_id_ref = u.id")


def test_the_migration_enforces_exactly_the_module_vocabulary():
    sql = MIGRATION.read_text(encoding="utf-8")
    match = re.search(r"scope_status IN \(([^)]*)\)", sql)
    assert match is not None
    enforced = {token.strip().strip("'") for token in match.group(1).split(",")}
    assert enforced == set(SCOPE_STATUSES)
    assert RETIRED in enforced


def test_the_migration_adds_nullable_columns_without_a_default_or_backfill():
    """NULL means 'never assessed = shown'. A DEFAULT would rewrite 1.76M rows and assert a
    judgement nobody made; an UPDATE would do the same."""
    sql = MIGRATION.read_text(encoding="utf-8")
    code = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    assert "ADD COLUMN IF NOT EXISTS scope_status TEXT'" in code
    assert "ADD COLUMN IF NOT EXISTS scope_reason TEXT'" in code
    assert "DEFAULT" not in code.upper()
    assert "UPDATE UNIFIED_SITES" not in code.upper()


def test_the_check_is_added_not_valid_and_validated_outside_that_transaction():
    """VALIDATE inside the ADD's transaction would scan 1.76M rows under ACCESS EXCLUSIVE."""
    sql = MIGRATION.read_text(encoding="utf-8")
    code = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    assert "NOT VALID" in code
    first_commit = code.index("COMMIT;")
    validate = code.index("VALIDATE CONSTRAINT unified_sites_scope_status_vocab")
    assert validate > first_commit
    # the self-test reads the catalog and aborts the migration when the check is missing
    assert "SELFTEST FAILED: unified_sites_scope_status_vocab does not exist" in code
    assert "convalidated" in code
