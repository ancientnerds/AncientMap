# SPDX-License-Identifier: AGPL-3.0-only
"""Boot migrations take a DDL lock only when the catalog says there is work.

``ALTER TABLE ... ADD COLUMN IF NOT EXISTS`` locks its table ACCESS EXCLUSIVE before it looks
for the column, so the "idempotent" boot migrations of Lyra (one transaction, every lock held
to the final commit) and of the API (api and api2, every deploy) locked a dozen tables on every
start. On 2026-09-22/23 that deadlocked the deploy's library refresh on news_items, twice.
pipeline/utils/boot_ddl.py now asks pg_catalog first.

Both boot paths run here, through their real functions, against a fake database that models
the catalog: it answers the catalog queries from what it holds, applies the DDL it is given
(and refuses DDL it cannot parse, DDL on a missing table and a statement with a missing bind
parameter, as PostgreSQL and SQLAlchemy would), and records every statement. The claims:

* a boot on a bare catalog emits every statement; a boot on the schema that leaves behind
  emits no DDL at all - the lock storm is gone;
* a schema missing one object gets exactly the statement(s) that create it, nothing else;
* Lyra still commits once, at the end; the API still runs each step in its own transaction
  under its lock timeout, and a retry after contention re-reads the catalog.

What a fake cannot prove - that each catalog query is right for PostgreSQL - was checked
read-only against production on 2026-09-23: all 108 checks of both boot paths answer "present"
there, and negative controls (a missing column, index, constraint, extension, a wrong varchar
length, a table only in the tiger schema) answer "missing".
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ArgumentError, InvalidRequestError, OperationalError, ProgrammingError

import api.cardgame.models  # noqa: F401 - card tables join Base.metadata, as in the API boot
from api import boot_schema
from api.boot_schema import FK_POLICY, run_api_boot_schema
from pipeline.database import Base
from pipeline.utils.boot_ddl import (
    BootDDL,
    add_column,
    add_constraint,
    create_extension,
    create_index,
    create_table,
    ensure,
    set_varchar_length,
)
from tests.fake_sql import FakeResult, sql_of

#: Tables Lyra's own migrations create; every other table the boot touches comes from the models.
LYRA_CREATES = {
    "unified_site_names",
    "pipeline_heartbeats",
    "wiki_images",
    "source_version_pins",
    "library_sources",
    "tts_requests",
}

_DDL_HEAD = ("ALTER ", "CREATE ", "DROP ", "DO ")

_TYPES = {
    "INTEGER": "integer",
    "SERIAL": "integer",
    "TEXT": "text",
    "JSONB": "jsonb",
    "TIMESTAMP": "timestamp without time zone",
    "BOOLEAN": "boolean",
    "FLOAT": "double precision",
    "UUID": "uuid",
}


def _format_type(definition: str) -> str:
    """format_type()'s spelling of a column definition's type."""
    if definition.startswith("TIMESTAMP WITH TIME ZONE"):
        return "timestamp with time zone"
    varchar = re.match(r"VARCHAR\((\d+)\)(\[\])?", definition)
    if varchar:
        return f"character varying({varchar.group(1)})" + (varchar.group(2) or "")
    word = definition.split()[0]
    array = "[]" if word.endswith("[]") else ""
    word = word.removesuffix("[]")
    if word not in _TYPES:
        raise AssertionError(f"the fake does not know the type {word!r} - teach it deliberately")
    return _TYPES[word] + array


class _PgError(Exception):
    """The driver error SQLAlchemy wraps; the code under test reads ``exc.orig.pgcode``."""

    def __init__(self, pgcode: str, message: str) -> None:
        super().__init__(message)
        self.pgcode = pgcode


@dataclass
class Catalog:
    """What the fake database holds. One schema (public), as in production."""

    tables: set[str]
    columns: dict[tuple[str, str], str] = field(default_factory=dict)
    indexes: dict[str, str] = field(default_factory=dict)  # index name -> its table
    constraints: set[tuple[str, str]] = field(default_factory=set)
    extensions: set[str] = field(default_factory=set)
    #: Tables that still carry an ON DELETE CASCADE FK onto unified_sites outside the exemptions.
    cascade_fks: set[str] = field(default_factory=set)

    def relations(self) -> set[str]:
        return self.tables | set(self.indexes)


_ADD_COLUMN = re.compile(r"ALTER TABLE (\w+) ADD COLUMN IF NOT EXISTS (\w+) (.+)")
_SET_TYPE = re.compile(r"ALTER TABLE (\w+) ALTER COLUMN (\w+) TYPE VARCHAR\((\d+)\)")
_CREATE_INDEX = re.compile(r"CREATE (?:UNIQUE )?INDEX IF NOT EXISTS (\w+) ON (\w+) .+")
_CREATE_TABLE = re.compile(r"CREATE TABLE IF NOT EXISTS (\w+) \((.+)\)")
_ADD_CONSTRAINT = re.compile(
    r"DO \$\$ BEGIN ALTER TABLE (\w+) ADD CONSTRAINT (\w+) (CHECK|UNIQUE) .+; "
    r"EXCEPTION WHEN ([\w ]+) THEN NULL; END \$\$"
)
_CREATE_EXTENSION = re.compile(r"CREATE EXTENSION IF NOT EXISTS (\w+)")
_FK_POLICY_HEAD = "DO $$ DECLARE r RECORD; BEGIN FOR r IN SELECT tc.table_name"


class Database:
    """A PostgreSQL stand-in that knows its catalog and records every statement."""

    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog
        #: ("sql", text) for every statement, plus ("CONNECT"|"BEGIN"|"COMMIT"|"ROLLBACK"|"CLOSE",)
        self.events: list[tuple[str, ...]] = []
        #: (kind, key, sql) for every DDL statement that created or changed something.
        self.created: list[tuple[str, Any, str]] = []
        #: raised by the next DDL statement instead of running it (after calling ``on_fail``)
        self.fail_next_ddl: Exception | None = None
        self.on_fail = lambda: None

    # -- what the tests read --------------------------------------------------------------

    def statements(self) -> list[str]:
        return [e[1] for e in self.events if e[0] == "sql"]

    def ddl(self) -> list[str]:
        return [s for s in self.statements() if " ".join(s.split()).startswith(_DDL_HEAD)]

    # -- the engine -----------------------------------------------------------------------

    @contextmanager
    def connect(self) -> Iterator[Connection]:
        self.events.append(("CONNECT",))
        yield Connection(self)
        self.events.append(("CLOSE",))

    @contextmanager
    def begin(self) -> Iterator[Connection]:
        self.events.append(("BEGIN",))
        try:
            yield Connection(self)
        except BaseException:
            self.events.append(("ROLLBACK",))
            raise
        self.events.append(("COMMIT",))

    # -- statements -----------------------------------------------------------------------

    def run(self, sql: str, params: dict[str, Any]) -> FakeResult:
        head = " ".join(sql.split())
        if head.startswith(_DDL_HEAD):
            if self.fail_next_ddl is not None:
                error, self.fail_next_ddl = self.fail_next_ddl, None
                self.on_fail()
                raise error
            self._apply(head, sql, params)
            return FakeResult([], rowcount=0)
        answer = self._catalog_answer(head, params)
        if answer is not None:
            return FakeResult([(answer,)])
        # a data statement or a SET: nothing to answer
        return FakeResult([], rowcount=0)

    def _catalog_answer(self, head: str, p: dict[str, Any]) -> bool | None:
        cat = self.catalog
        if "FROM pg_catalog.pg_attribute" in head and "format_type(" in head:
            key = (p["table_name"], p["column_name"])
            return key[0] in cat.tables and cat.columns.get(key) == p["column_type"]
        if "FROM pg_catalog.pg_attribute" in head:
            return (
                p["table_name"] in cat.tables and (p["table_name"], p["column_name"]) in cat.columns
            )
        if "FROM pg_catalog.pg_constraint" in head:
            key = (p["table_name"], p["constraint_name"])
            return key[0] in cat.tables and key in cat.constraints
        if "FROM pg_catalog.pg_extension" in head:
            return p["extension_name"] in cat.extensions
        if "FROM pg_catalog.pg_class" in head and "index_name" in p:
            # the index's namespace is its table's; no table, no namespace, no match
            return p["table_name"] in cat.tables and p["index_name"] in cat.relations()
        if "FROM pg_catalog.pg_class" in head and "current_schema()" in head:
            return p["relation_name"] in cat.relations()
        if head == "SELECT to_regclass(:relation_name) IS NOT NULL":
            return p["relation_name"] in cat.relations()
        if head.startswith("SELECT NOT EXISTS (") and "referential_constraints" in head:
            return not cat.cascade_fks
        return None

    def _require_table(self, table: str, sql: str, params: dict[str, Any]) -> None:
        if table not in self.catalog.tables:
            raise ProgrammingError(
                sql, params, _PgError("42P01", f'relation "{table}" does not exist')
            )

    def _apply(self, head: str, sql: str, params: dict[str, Any]) -> None:
        cat = self.catalog
        if m := _ADD_COLUMN.fullmatch(head):
            table, column, definition = m.groups()
            self._require_table(table, sql, params)
            if (table, column) not in cat.columns:  # IF NOT EXISTS
                cat.columns[(table, column)] = _format_type(definition)
                self.created.append(("column", (table, column), sql))
        elif m := _SET_TYPE.fullmatch(head):
            table, column, length = m.groups()
            self._require_table(table, sql, params)
            if (table, column) not in cat.columns:
                raise ProgrammingError(sql, params, _PgError("42703", f'column "{column}"'))
            cat.columns[(table, column)] = f"character varying({length})"
            self.created.append(("type", (table, column), sql))
        elif m := _CREATE_INDEX.fullmatch(head):
            name, table = m.groups()
            self._require_table(table, sql, params)
            if name not in cat.relations():  # IF NOT EXISTS: any relation of that name
                cat.indexes[name] = table
                self.created.append(("index", name, sql))
        elif m := _CREATE_TABLE.fullmatch(head):
            name, body = m.groups()
            if name not in cat.relations():
                cat.tables.add(name)
                for column_def in _top_level_parts(body):
                    column, definition = column_def.split(" ", 1)
                    cat.columns[(name, column)] = _format_type(definition)
                self.created.append(("table", name, sql))
        elif m := _ADD_CONSTRAINT.fullmatch(head):
            table, name, kind, handled = m.groups()
            self._require_table(table, sql, params)
            duplicate = "duplicate_object" if kind == "CHECK" else "duplicate_table"
            clash = (table, name) in cat.constraints or (
                kind == "UNIQUE" and name in cat.relations()
            )
            if clash:
                if duplicate not in handled.split(" OR "):
                    raise ProgrammingError(sql, params, _PgError("42P07", f"{name} exists"))
                return
            cat.constraints.add((table, name))
            if kind == "UNIQUE":
                cat.indexes[name] = table  # the backing index carries the constraint's name
            self.created.append(("constraint", (table, name), sql))
        elif m := _CREATE_EXTENSION.fullmatch(head):
            if m.group(1) not in cat.extensions:
                cat.extensions.add(m.group(1))
                self.created.append(("extension", m.group(1), sql))
        elif head.startswith(_FK_POLICY_HEAD):
            if cat.cascade_fks:
                cat.cascade_fks.clear()
                self.created.append(("fk_policy", None, sql))
        else:
            raise AssertionError(f"the fake does not know this DDL - teach it deliberately: {head}")


def _top_level_parts(body: str) -> list[str]:
    parts, depth, current = [], 0, ""
    for ch in body:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += ch
    parts.append(current.strip())
    return [p for p in parts if p]


class Connection:
    """``Connection.execute`` / ``commit``, refusing what SQLAlchemy 2 refuses."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> FakeResult:
        sql = sql_of(stmt)  # a plain string raises ArgumentError, as in SQLAlchemy 2
        params = dict(params or {})
        missing = sorted(set(stmt.compile().params) - set(params))
        if missing:
            raise InvalidRequestError(f"A value is required for bind parameter {missing[0]!r}")
        self.db.events.append(("sql", sql))
        return self.db.run(sql, params)

    def commit(self) -> None:
        self.db.events.append(("COMMIT",))


# --------------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------------


def _lyra_bare() -> Catalog:
    """Every table the models create, none of what the Lyra migrations ensure."""
    return Catalog(tables=set(Base.metadata.tables) - LYRA_CREATES)


def _api_bare() -> Catalog:
    """What create_all leaves in the API boot, none of what the API steps ensure; one CASCADE FK.

    grant_period exists as Lyra first adds it (VARCHAR(7)): the API only widens it.
    """
    return Catalog(
        tables=set(Base.metadata.tables),
        columns={("credit_grants", "grant_period"): "character varying(7)"},
        cascade_fks={"site_likes"},
    )


def _boot_lyra(catalog: Catalog) -> Database:
    import pipeline.lyra.orchestrator as orch

    db = Database(catalog)
    orch._run_migrations(db)
    return db


def _boot_api(catalog: Catalog) -> Database:
    db = Database(catalog)
    run_api_boot_schema(db)
    return db


def _remove(catalog: Catalog, kind: str, key: Any) -> None:
    """Take one object out of the catalog, with what PostgreSQL drops along with it."""
    if kind == "column":
        del catalog.columns[key]
    elif kind == "type":
        catalog.columns[key] = "character varying(7)"
    elif kind == "index":
        del catalog.indexes[key]
    elif kind == "constraint":
        catalog.constraints.discard(key)
        catalog.indexes.pop(key[1], None)  # a UNIQUE constraint's backing index goes too
    elif kind == "extension":
        catalog.extensions.discard(key)
    elif kind == "table":
        catalog.tables.discard(key)
        catalog.columns = {k: v for k, v in catalog.columns.items() if k[0] != key}
        catalog.indexes = {k: v for k, v in catalog.indexes.items() if v != key}
        catalog.constraints = {c for c in catalog.constraints if c[0] != key}
    elif kind == "fk_policy":
        catalog.cascade_fks.add("site_likes")
    else:
        raise AssertionError(kind)


def _restores(
    kind: str, key: Any, other_kind: str, other_key: Any, index_table: str | None
) -> bool:
    """Whether recreating (kind, key) also brings back (other_kind, other_key)."""
    if (other_kind, other_key) == (kind, key):
        return True
    if kind == "column":  # a re-added varchar column is typed again
        return other_kind == "type" and other_key == key
    if kind == "table":
        owner = (
            other_key[0]
            if other_kind in ("column", "type", "constraint")
            else index_table
            if other_kind == "index"
            else None
        )
        return owner == key
    return False


def _single_removals(first: Database) -> list[tuple[str, Any, list[str]]]:
    """For every object the first boot created: its kind, key and the DDL that recreates it."""
    index_tables = dict(first.catalog.indexes)
    cases = []
    for kind, key, _ in first.created:
        expected = [
            sql
            for other_kind, other_key, sql in first.created
            if _restores(
                kind,
                key,
                other_kind,
                other_key,
                index_tables.get(other_key) if other_kind == "index" else None,
            )
        ]
        cases.append((kind, key, expected))
    return cases


# --------------------------------------------------------------------------------------------
# the fake refuses what the real objects refuse
# --------------------------------------------------------------------------------------------


def test_the_fake_refuses_what_postgres_and_sqlalchemy_refuse():
    conn = Connection(Database(Catalog(tables={"news_items"})))
    with pytest.raises(ArgumentError):
        conn.execute("SELECT 1")  # type: ignore[arg-type]
    with pytest.raises(InvalidRequestError):
        conn.execute(text("SELECT to_regclass(:relation_name) IS NOT NULL"), {})
    with pytest.raises(ProgrammingError):
        conn.execute(text("ALTER TABLE no_such_table ADD COLUMN IF NOT EXISTS c TEXT"))
    with pytest.raises(AssertionError, match="does not know this DDL"):
        conn.execute(text("ALTER TABLE news_items DROP COLUMN c"))


# --------------------------------------------------------------------------------------------
# Lyra: one transaction, and no DDL on an up-to-date schema
# --------------------------------------------------------------------------------------------


def test_lyra_boot_on_an_up_to_date_schema_issues_no_ddl():
    first = _boot_lyra(_lyra_bare())
    # every schema statement of the batch ran on the bare catalog (75 plain statements, the
    # card_stats block as its three parts) - and each was a real change
    assert len(first.ddl()) == 78
    assert len(first.created) == 78

    second = _boot_lyra(first.catalog)

    assert second.ddl() == []


def test_lyra_boot_adds_exactly_a_missing_column():
    up_to_date = _boot_lyra(_lyra_bare()).catalog
    del up_to_date.columns[("news_items", "significance")]

    db = _boot_lyra(up_to_date)

    assert [" ".join(s.split()) for s in db.ddl()] == [
        "ALTER TABLE news_items ADD COLUMN IF NOT EXISTS significance INTEGER"
    ]


def test_lyra_boot_recreates_exactly_each_missing_object():
    """Take any one object away and the boot emits the statement(s) that create it - only those."""
    first = _boot_lyra(_lyra_bare())
    cases = _single_removals(first)
    assert len(cases) == 78
    # a table taken away brings its indexes and its constraint back with it
    usn = next(
        expected for kind, key, expected in cases if (kind, key) == ("table", "unified_site_names")
    )
    assert len(usn) == 5
    wrong = []
    for kind, key, expected in cases:
        catalog = copy.deepcopy(first.catalog)
        _remove(catalog, kind, key)
        got = _boot_lyra(catalog).ddl()
        if got != expected:
            wrong.append((kind, key, got, expected))
    assert wrong == []


def test_lyra_leaves_card_stats_alone_when_the_table_does_not_exist():
    """card_stats comes from the API's models; on a fresh DB an ALTER on it would roll back the
    whole batch (audit 2026-08-05). The table check that guarded the old DO block stays."""
    bare = _lyra_bare()
    bare.tables.discard("card_stats")

    db = _boot_lyra(bare)

    assert [s for s in db.ddl() if "card_stats" in s] == []
    assert len(db.ddl()) == 75


def test_lyra_sets_card_description_to_varchar_200_only_while_it_is_not():
    up_to_date = _boot_lyra(_lyra_bare()).catalog
    up_to_date.columns[("card_stats", "card_description")] = "character varying(150)"

    db = _boot_lyra(up_to_date)

    assert [" ".join(s.split()) for s in db.ddl()] == [
        "ALTER TABLE card_stats ALTER COLUMN card_description TYPE VARCHAR(200)"
    ]


def test_lyra_migrations_stay_one_transaction_committed_at_the_end():
    """docs/procedures/PROJECT_LESSONS.md: the batch commits once; the catalog checks run inside it."""
    db = _boot_lyra(_lyra_bare())

    assert db.events[0] == ("CONNECT",)
    assert db.events[-2:] == [("COMMIT",), ("CLOSE",)]
    assert [e for e in db.events if e[0] in ("CONNECT", "BEGIN", "COMMIT")] == [
        ("CONNECT",),
        ("COMMIT",),
    ]


# --------------------------------------------------------------------------------------------
# API: every step asks first, each in its own transaction
# --------------------------------------------------------------------------------------------


def test_api_boot_on_an_up_to_date_schema_issues_no_ddl():
    first = _boot_api(_api_bare())
    assert len(first.ddl()) == len(boot_schema.API_BOOT_SCHEMA) == 29
    assert len(first.created) == 29

    second = _boot_api(first.catalog)

    assert second.ddl() == []


def test_api_boot_adds_exactly_a_missing_column():
    up_to_date = _boot_api(_api_bare()).catalog
    del up_to_date.columns[("research_requests", "started_at")]

    db = _boot_api(up_to_date)

    assert [" ".join(s.split()) for s in db.ddl()] == [
        "ALTER TABLE research_requests ADD COLUMN IF NOT EXISTS started_at TIMESTAMP"
    ]


def test_api_boot_recreates_exactly_each_missing_object():
    first = _boot_api(_api_bare())
    cases = _single_removals(first)
    assert len(cases) == 29
    wrong = []
    for kind, key, expected in cases:
        catalog = copy.deepcopy(first.catalog)
        _remove(catalog, kind, key)
        got = _boot_api(catalog).ddl()
        if got != expected:
            wrong.append((kind, key, got, expected))
    assert wrong == []


def test_api_sets_grant_period_to_varchar_10_only_while_it_is_not():
    """The old statement ran unconditionally: an ACCESS EXCLUSIVE lock on every boot."""
    up_to_date = _boot_api(_api_bare()).catalog
    assert _boot_api(copy.deepcopy(up_to_date)).ddl() == []
    up_to_date.columns[("credit_grants", "grant_period")] = "character varying(7)"

    db = _boot_api(up_to_date)

    assert [" ".join(s.split()) for s in db.ddl()] == [
        "ALTER TABLE credit_grants ALTER COLUMN grant_period TYPE VARCHAR(10)"
    ]


def test_the_fk_policy_rewrite_runs_only_while_a_cascade_fk_remains():
    up_to_date = _boot_api(_api_bare()).catalog
    assert up_to_date.cascade_fks == set()
    up_to_date.cascade_fks.add("site_bookmarks")

    db = _boot_api(up_to_date)

    assert db.ddl() == [FK_POLICY.ddl]
    assert db.catalog.cascade_fks == set()


def test_each_api_step_checks_and_alters_in_its_own_transaction_under_the_lock_timeout():
    up_to_date = _boot_api(_api_bare()).catalog
    del up_to_date.columns[("card_stats", "commons_image")]

    db = _boot_api(up_to_date)

    transactions: list[list[str]] = []
    for event in db.events:
        if event == ("BEGIN",):
            transactions.append([])
        elif event[0] == "sql":
            transactions[-1].append(" ".join(event[1].split()))
    assert len(transactions) == len(boot_schema.API_BOOT_SCHEMA)
    assert all(
        t[:2] == ["SET LOCAL lock_timeout = '5s'", "SET LOCAL statement_timeout = '30s'"]
        for t in transactions
    )
    altering = [t for t in transactions if len(t) == 4]
    assert len(altering) == 1
    check, ddl = altering[0][2:]
    assert "pg_catalog.pg_attribute" in check
    assert ddl == "ALTER TABLE card_stats ADD COLUMN IF NOT EXISTS commons_image VARCHAR(500)"
    assert all(len(t) == 3 for t in transactions if t is not altering[0])


def test_a_step_retried_after_contention_reads_the_catalog_again(monkeypatch):
    """api and lyra can both read "missing"; the loser of the lock race retries, finds the
    column the winner added, and runs no DDL of its own."""
    monkeypatch.setattr(boot_schema.time, "sleep", lambda s: None)
    up_to_date = _boot_api(_api_bare()).catalog
    del up_to_date.columns[("research_nodes", "outcome")]
    db = Database(up_to_date)
    db.fail_next_ddl = OperationalError(
        "ALTER TABLE", {}, _PgError("55P03", "canceling statement due to lock timeout")
    )

    def the_other_booter_adds_it() -> None:
        up_to_date.columns[("research_nodes", "outcome")] = "character varying(20)"

    db.on_fail = the_other_booter_adds_it

    run_api_boot_schema(db)

    assert [" ".join(s.split()) for s in db.ddl()] == [
        "ALTER TABLE research_nodes ADD COLUMN IF NOT EXISTS outcome VARCHAR(20)"
    ]  # the one attempt that lost the race; the retry ran none
    assert ("ROLLBACK",) in db.events
    assert db.catalog.columns[("research_nodes", "outcome")] == "character varying(20)"


# --------------------------------------------------------------------------------------------
# the building blocks
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["News_Items", "news items", "x;drop", '"quoted"', "", "1st"])
def test_a_name_that_is_not_a_plain_lower_case_identifier_is_refused(bad):
    """PostgreSQL folds an unquoted name to lower case and the catalog queries compare against
    the folded name: a mixed-case name would read as "missing" on every boot."""
    builders = [
        lambda n: add_column(n, "c", "TEXT"),
        lambda n: add_column("t", n, "TEXT"),
        lambda n: set_varchar_length(n, "c", 10),
        lambda n: create_table(n, "id INTEGER"),
        lambda n: create_index(n, "t", "(c)"),
        lambda n: create_index("i", n, "(c)"),
        lambda n: add_constraint(n, "k", "CHECK (c > 0)", duplicate=("duplicate_object",)),
        lambda n: create_extension(n),
    ]
    for build in builders:
        with pytest.raises(ValueError, match="plain lower-case SQL identifier"):
            build(bad)


@pytest.mark.parametrize("duplicate", [(), ("unique_violation",), ("duplicate_object", "others")])
def test_a_constraint_handler_swallows_only_a_duplicate(duplicate):
    with pytest.raises(ValueError, match="duplicate must name"):
        add_constraint("t", "k", "CHECK (c > 0)", duplicate=duplicate)


def test_ensure_runs_the_statement_only_when_the_catalog_says_it_is_missing():
    step = add_column("news_items", "significance", "INTEGER")
    db = Database(Catalog(tables={"news_items"}))
    conn = Connection(db)

    assert ensure(conn, step) is True
    assert ensure(conn, step) is False
    assert db.ddl() == [step.ddl]


def test_a_boot_step_is_a_value_the_api_list_can_hold():
    assert all(isinstance(step, BootDDL) for step in boot_schema.API_BOOT_SCHEMA)
    assert len({step.label for step in boot_schema.API_BOOT_SCHEMA}) == len(
        boot_schema.API_BOOT_SCHEMA
    )
