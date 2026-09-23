# SPDX-License-Identifier: AGPL-3.0-only
"""Boot-time DDL that asks the catalog first and takes a lock only when there is work.

``ALTER TABLE t ADD COLUMN IF NOT EXISTS c`` is idempotent, but it is not free: PostgreSQL
takes the ACCESS EXCLUSIVE lock on ``t`` *before* it looks for ``c``. The statement queues
behind every open reader of ``t``, and every later reader queues behind it - even when the
column has existed for months. ``CREATE INDEX IF NOT EXISTS`` takes a SHARE lock on its table
the same way, and ``ADD CONSTRAINT`` another ACCESS EXCLUSIVE one. Lyra ran its schema
statements on every start inside ONE transaction that held each of those locks until its
final commit, and the API ran its own list on api and api2 at every deploy. On 2026-09-22
and 2026-09-23 that deadlocked the deploy's library refresh (``DeadlockDetected`` on
news_items).

A step here pairs the unchanged idempotent statement with a catalog query that says whether
the statement has anything to do. The query reads pg_catalog only, so it takes no lock on the
user table; the statement runs only when the answer is no. The statement keeps its
``IF NOT EXISTS`` (or its duplicate-object handler) because two booters can both read
"missing" and both run it - the second must stay a no-op.

Every catalog query resolves a name the way its statement does:

* a column or a constraint through ``to_regclass`` - the search_path lookup ``ALTER TABLE``
  performs on an unqualified table name;
* a new table in ``current_schema()`` - where ``CREATE TABLE`` creates it and where
  ``IF NOT EXISTS`` looks;
* a new index in its table's schema - where ``CREATE INDEX`` creates it and where
  ``IF NOT EXISTS`` looks (any relation of that name counts, as it does for the statement).

``is_contention_error`` is the one rule both boot paths retry by: the API's
``api/boot_schema.py::run_boot_step`` and Lyra's ``pipeline/lyra/orchestrator.py::main``. It
lives here because ``pipeline/`` may not import ``api/``.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.engine import Connection

logger = logging.getLogger(__name__)

# Unquoted identifiers only, already in the lower case PostgreSQL folds them to. The catalog
# queries compare against the stored (folded) name, so a mixed-case name would read as
# "missing" on every boot and put the lock storm straight back.
_IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]*")

# The conditions an ADD CONSTRAINT handler may swallow: 42710 (a CHECK or FK constraint of
# that name exists) and 42P07 (the index backing a UNIQUE constraint exists).
_DUPLICATE_CONDITIONS = frozenset({"duplicate_object", "duplicate_table"})

_COLUMN_PRESENT = """
    SELECT EXISTS (
        SELECT 1 FROM pg_catalog.pg_attribute
        WHERE attrelid = to_regclass(:table_name) AND attname = :column_name
          AND attnum > 0 AND NOT attisdropped
    )
"""

_COLUMN_TYPED = """
    SELECT EXISTS (
        SELECT 1 FROM pg_catalog.pg_attribute
        WHERE attrelid = to_regclass(:table_name) AND attname = :column_name
          AND attnum > 0 AND NOT attisdropped
          AND format_type(atttypid, atttypmod) = :column_type
    )
"""

_TABLE_PRESENT = """
    SELECT EXISTS (
        SELECT 1 FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = :relation_name AND n.nspname = current_schema()
    )
"""

_INDEX_PRESENT = """
    SELECT EXISTS (
        SELECT 1 FROM pg_catalog.pg_class
        WHERE relname = :index_name
          AND relnamespace = (
              SELECT relnamespace FROM pg_catalog.pg_class WHERE oid = to_regclass(:table_name)
          )
    )
"""

_CONSTRAINT_PRESENT = """
    SELECT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conrelid = to_regclass(:table_name) AND conname = :constraint_name
    )
"""

_EXTENSION_PRESENT = """
    SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_extension WHERE extname = :extension_name)
"""

_RELATION_RESOLVES = "SELECT to_regclass(:relation_name) IS NOT NULL"


def _identifier(name: str) -> str:
    if not _IDENTIFIER.fullmatch(name):
        # Callers pass literal names. Anything else is a programming error that must neither
        # be spliced into DDL nor be compared against the catalog in a form it is not stored in.
        raise ValueError(f"not a plain lower-case SQL identifier: {name!r}")
    return name


@dataclass(frozen=True)
class BootDDL:
    """One idempotent DDL statement and the catalog query that says whether it has work."""

    label: str
    ddl: str
    #: One row, one boolean: true when the catalog already holds what ``ddl`` would create.
    satisfied_sql: str
    params: Mapping[str, str] = field(default_factory=dict)


def ensure(conn: Connection, step: BootDDL) -> bool:
    """Run ``step.ddl`` only when the catalog says it is needed. True when it ran.

    Both statements run on ``conn``, inside whatever transaction the caller holds - Lyra's
    single migration transaction, or one of the API's per-step transactions.
    """
    if conn.execute(text(step.satisfied_sql), dict(step.params)).scalar_one():
        return False
    conn.execute(text(step.ddl))
    logger.info("boot DDL applied: %s", step.label)
    return True


def pgcode_of(exc: BaseException) -> str | None:
    """The SQLSTATE of the driver error SQLAlchemy wrapped in ``exc``; None when there is none."""
    return getattr(getattr(exc, "orig", None), "pgcode", None)


def is_contention_error(exc: BaseException) -> bool:
    """True only for a lock timeout (55P03), a statement timeout (57014) or a deadlock (40P01).

    Those are EXPECTED when api and lyra boot together and both still have DDL to run, so both
    boot paths wait out the other booter and retry. Every other error is a real failure: the API
    aborts its startup and Lyra logs its batch as rolled back. The API used to swallow every error
    as "lock contention", leaving silent schema drift while it started healthy (audit 2026-08-05,
    M5).
    """
    return pgcode_of(exc) in ("55P03", "57014", "40P01")


def relation_exists(conn: Connection, name: str) -> bool:
    """Whether ``name`` resolves to a relation on the search_path, as an ALTER TABLE would."""
    return bool(
        conn.execute(text(_RELATION_RESOLVES), {"relation_name": _identifier(name)}).scalar_one()
    )


def add_column(table: str, column: str, definition: str) -> BootDDL:
    """``ALTER TABLE t ADD COLUMN IF NOT EXISTS c <definition>``, run while ``t.c`` is missing."""
    return BootDDL(
        label=f"column {table}.{column}",
        ddl=(
            f"ALTER TABLE {_identifier(table)} "
            f"ADD COLUMN IF NOT EXISTS {_identifier(column)} {definition}"
        ),
        satisfied_sql=_COLUMN_PRESENT,
        params={"table_name": table, "column_name": column},
    )


def set_varchar_length(table: str, column: str, length: int) -> BootDDL:
    """``ALTER COLUMN c TYPE VARCHAR(n)``, run while ``t.c`` is anything but exactly varchar(n)."""
    return BootDDL(
        label=f"type {table}.{column} varchar({length:d})",
        ddl=(
            f"ALTER TABLE {_identifier(table)} "
            f"ALTER COLUMN {_identifier(column)} TYPE VARCHAR({length:d})"
        ),
        satisfied_sql=_COLUMN_TYPED,
        # format_type()'s spelling of the type the statement sets.
        params={
            "table_name": table,
            "column_name": column,
            "column_type": f"character varying({length:d})",
        },
    )


def create_table(name: str, columns: str) -> BootDDL:
    """``CREATE TABLE IF NOT EXISTS name (<columns>)``, run while ``name`` is missing."""
    return BootDDL(
        label=f"table {name}",
        ddl=f"CREATE TABLE IF NOT EXISTS {_identifier(name)} ({columns})",
        satisfied_sql=_TABLE_PRESENT,
        params={"relation_name": name},
    )


def create_index(name: str, table: str, spec: str, *, unique: bool = False) -> BootDDL:
    """``CREATE [UNIQUE] INDEX IF NOT EXISTS name ON table <spec>``, run while ``name`` is missing.

    ``spec`` is everything after the table name: the column list, ``USING gin (...)``, a
    partial-index ``WHERE``.
    """
    kind = "UNIQUE INDEX" if unique else "INDEX"
    return BootDDL(
        label=f"index {name}",
        ddl=f"CREATE {kind} IF NOT EXISTS {_identifier(name)} ON {_identifier(table)} {spec}",
        satisfied_sql=_INDEX_PRESENT,
        params={"index_name": name, "table_name": table},
    )


def add_constraint(
    table: str, name: str, definition: str, *, duplicate: tuple[str, ...]
) -> BootDDL:
    """``ALTER TABLE t ADD CONSTRAINT name <definition>``, run while ``t`` has no ``name``.

    The statement stays wrapped in a handler for ``duplicate`` so a second booter that also
    read "missing" is a no-op: 42710 ``duplicate_object`` for a CHECK constraint, 42P07
    ``duplicate_table`` for the index a UNIQUE constraint creates.
    """
    unknown = set(duplicate) - _DUPLICATE_CONDITIONS
    if not duplicate or unknown:
        raise ValueError(f"duplicate must name {sorted(_DUPLICATE_CONDITIONS)}, got {duplicate!r}")
    return BootDDL(
        label=f"constraint {table}.{name}",
        ddl=(
            "DO $$ BEGIN\n"
            f"    ALTER TABLE {_identifier(table)} ADD CONSTRAINT {_identifier(name)} {definition};\n"
            f"EXCEPTION WHEN {' OR '.join(duplicate)} THEN NULL;\n"
            "END $$"
        ),
        satisfied_sql=_CONSTRAINT_PRESENT,
        params={"table_name": table, "constraint_name": name},
    )


def create_extension(name: str) -> BootDDL:
    """``CREATE EXTENSION IF NOT EXISTS name``, run while the extension is not installed."""
    return BootDDL(
        label=f"extension {name}",
        ddl=f"CREATE EXTENSION IF NOT EXISTS {_identifier(name)}",
        satisfied_sql=_EXTENSION_PRESENT,
        params={"extension_name": name},
    )
