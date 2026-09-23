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
parameter, as PostgreSQL and SQLAlchemy would; an ADD CONSTRAINT whose object exists raises the
code PostgreSQL raises unless the statement's handler names it), and records every statement.
The FK-policy query is read, not recognised: the fake takes the exemption list out of the SQL
it is sent. The claims:

* a boot on a bare catalog emits every statement; a boot on the schema that leaves behind
  emits no DDL at all - the lock storm is gone;
* a schema missing one object gets exactly the statement(s) that create it, nothing else;
* Lyra still commits once, at the end; the API still runs each step in its own transaction
  under its lock timeout, and a retry after contention re-reads the catalog;
* only a lock timeout, a statement timeout or a deadlock counts as contention, in one function
  both boot paths share: an API step still contended after three attempts is left to the next
  boot, and any other error aborts the startup at once;
* api/main.py runs the API list and holds no DDL string of its own;
* two booters that both read "missing" stay harmless: the loser's ADD CONSTRAINT meets the
  object the winner committed, and its handler swallows exactly the error PostgreSQL raises
  (42710 for a CHECK, 42P07 for the index behind a UNIQUE). Before 2026-09-23 the handler ran
  on every boot; now it runs only in that race, so only a test can keep it honest;
* the FK-policy check and its rewrite loop read one query, so the check cannot pass while the
  loop would still find work, and the site-owned tables keep their CASCADE FKs.

What a fake cannot prove - that each catalog query is right for PostgreSQL - was checked
read-only against production on 2026-09-23: all 108 checks of both boot paths answer "present"
there, and negative controls (a missing column, index, constraint, extension, a wrong varchar
length, a table only in the tiger schema) answer "missing".
"""

from __future__ import annotations

import ast
import copy
import logging
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
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
    is_contention_error,
    pgcode_of,
    relation_exists,
    set_varchar_length,
)
from tests.api.test_fk_policy_exemptions import SITE_OWNED_CASCADE_TABLES
from tests.fake_sql import FakeResult, sql_of
from tests.source_functions import names_used_by

REPO = Path(__file__).resolve().parents[2]

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
    #: Tables that carry an ON DELETE CASCADE FK onto unified_sites, the exempt site-owned ones
    #: included: the FK-policy query decides which of them count.
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
#: What makes the FK-policy query a query for CASCADE FKs onto unified_sites; the fake refuses one
#: without them rather than guess what it would find.
_FK_ONTO_SITES = (
    "WHERE table_name = 'unified_sites' AND constraint_type = 'PRIMARY KEY'",
    "AND rc.delete_rule = 'CASCADE'",
)
_FK_EXEMPT = re.compile(r"AND tc\.table_name NOT IN \(([^)]*)\)")
#: What PostgreSQL raises for an ADD CONSTRAINT whose name is taken: a CHECK's own name (42710), or
#: the name of the index a UNIQUE constraint creates (42P07).
_DUPLICATE_RAISED = {"CHECK": ("duplicate_object", "42710"), "UNIQUE": ("duplicate_table", "42P07")}


class Database:
    """A PostgreSQL stand-in that knows its catalog and records every statement."""

    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog
        #: ("sql", text, params) for every statement, plus ("CONNECT"|"BEGIN"|"COMMIT"|"ROLLBACK"|
        #: "CLOSE",)
        self.events: list[tuple[Any, ...]] = []
        #: (kind, key, sql) for every DDL statement that created or changed something.
        self.created: list[tuple[str, Any, str]] = []
        #: raised by the next DDL statement instead of running it (after calling ``on_fail``)
        self.fail_next_ddl: Exception | None = None
        self.on_fail = lambda: None
        #: called once, right before the next DDL statement runs: another booter read "missing"
        #: too and committed the object first, so this statement meets it
        self.other_booter_first: Callable[[], None] | None = None

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
            if self.other_booter_first is not None:
                winner, self.other_booter_first = self.other_booter_first, None
                winner()
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
            return not self._cascade_fks_found_by(head)
        return None

    def _cascade_fks_found_by(self, head: str) -> set[str]:
        """The CASCADE FKs onto unified_sites this FK-policy query finds, exemptions read from it.

        The exemption list comes out of the SQL the code sent, so a check and a rewrite loop that
        disagree about it disagree here too.
        """
        if not all(part in head for part in _FK_ONTO_SITES):
            raise AssertionError(
                f"the fake does not know this FK query - teach it deliberately: {head}"
            )
        exempt = _FK_EXEMPT.search(head)
        exempted = set(re.findall(r"'(\w+)'", exempt.group(1))) if exempt else set()
        return self.catalog.cascade_fks - exempted

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
            duplicate, pgcode = _DUPLICATE_RAISED[kind]
            clash = (table, name) in cat.constraints or (
                kind == "UNIQUE" and name in cat.relations()
            )
            if clash:
                if duplicate not in handled.split(" OR "):
                    raise ProgrammingError(sql, params, _PgError(pgcode, f"{name} exists"))
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
            found = self._cascade_fks_found_by(head)
            if found:
                cat.cascade_fks -= found
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
        self.db.events.append(("sql", sql, params))
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
    """What create_all leaves in the API boot, none of what the API steps ensure; one CASCADE FK
    outside the exemptions.

    grant_period exists as Lyra first adds it (VARCHAR(7)): the API only widens it. The site-owned
    tables carry their CASCADE FKs, as on production (read-only, 2026-09-23: exactly those five
    tables have one), so a query that forgets its exemptions finds work where there is none.
    """
    return Catalog(
        tables=set(Base.metadata.tables),
        columns={("credit_grants", "grant_period"): "character varying(7)"},
        cascade_fks=SITE_OWNED_CASCADE_TABLES | {"site_likes"},
    )


def _migrate_lyra(db: Database) -> Database:
    import pipeline.lyra.orchestrator as orch

    orch._run_migrations(db)
    return db


def _boot_lyra(catalog: Catalog) -> Database:
    return _migrate_lyra(Database(catalog))


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


def _constraints_created(first: Database) -> list[tuple[tuple[str, str], str]]:
    """Every constraint the first boot added, and the statement that added it, in boot order."""
    return [(key, sql) for kind, key, sql in first.created if kind == "constraint"]


def _losing_the_race_for(up_to_date: Catalog, key: tuple[str, str]) -> Database:
    """A database whose check for ``key`` reads "missing", after which the other booter commits it.

    The loser's ADD CONSTRAINT then meets the winner's constraint (and, for a UNIQUE one, the
    index behind it), the state PostgreSQL shows it once the winner's lock is released.
    """
    catalog = copy.deepcopy(up_to_date)
    _remove(catalog, "constraint", key)
    db = Database(catalog)

    def the_other_booter_commits_it() -> None:
        catalog.constraints.add(key)
        if key[1] in up_to_date.indexes:  # the index a UNIQUE constraint carries
            catalog.indexes[key[1]] = up_to_date.indexes[key[1]]

    db.other_booter_first = the_other_booter_commits_it
    return db


@dataclass
class Transaction:
    """One transaction of the API boot: what it ran, and how it ended."""

    #: (the statement, whitespace-normalised; its bind parameters), in the order they ran
    statements: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    outcome: str = ""  # "COMMIT" or "ROLLBACK"

    def sql(self) -> list[str]:
        return [sql for sql, _ in self.statements]


def _transactions(db: Database) -> list[Transaction]:
    """The API boot's transactions, in the order they ran."""
    transactions: list[Transaction] = []
    for event in db.events:
        if event == ("BEGIN",):
            transactions.append(Transaction())
        elif event[0] == "sql":
            transactions[-1].statements.append((" ".join(event[1].split()), event[2]))
        elif event[0] in ("COMMIT", "ROLLBACK"):
            transactions[-1].outcome = event[0]
    return transactions


def _attempts(db: Database, params: dict[str, str]) -> list[Transaction]:
    """Every attempt of one API step: the transactions whose catalog check asked ``params``."""
    return [t for t in _transactions(db) if any(p == params for _, p in t.statements)]


#: The API step the contention tests take away, its catalog question and its statement.
_OUTCOME_LABEL = "Migration (column research_nodes.outcome)"
_OUTCOME = {"table_name": "research_nodes", "column_name": "outcome"}
_ADD_OUTCOME = "ALTER TABLE research_nodes ADD COLUMN IF NOT EXISTS outcome VARCHAR(20)"


def _outcome_missing_and_contended(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> tuple[Database, list[float]]:
    """An up-to-date API schema without research_nodes.outcome, whose next DDL statement times
    out on its lock (55P03); and the list the retry's sleeps land in."""
    slept: list[float] = []
    monkeypatch.setattr(boot_schema.time, "sleep", slept.append)
    caplog.set_level(logging.WARNING, logger=boot_schema.logger.name)
    catalog = _boot_api(_api_bare()).catalog
    del catalog.columns[("research_nodes", "outcome")]
    db = Database(catalog)
    db.fail_next_ddl = OperationalError(
        "ALTER TABLE", {}, _PgError("55P03", "canceling statement due to lock timeout")
    )
    return db, slept


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


def test_the_fake_raises_the_code_postgres_raises_for_a_taken_constraint_name():
    """42710 for a CHECK whose name is taken, 42P07 for the index behind a UNIQUE: a handler that
    names the other condition does not catch it, in PostgreSQL or here."""
    catalog = Catalog(
        tables={"t"},
        constraints={("t", "k_check"), ("t", "k_unique")},
        indexes={"k_unique": "t"},
    )
    conn = Connection(Database(catalog))
    for definition, handled, pgcode in (
        ("k_check CHECK (c > 0)", "duplicate_table", "42710"),
        ("k_unique UNIQUE (c)", "duplicate_object", "42P07"),
    ):
        with pytest.raises(ProgrammingError) as raised:
            conn.execute(
                text(
                    f"DO $$ BEGIN ALTER TABLE t ADD CONSTRAINT {definition}; "
                    f"EXCEPTION WHEN {handled} THEN NULL; END $$"
                )
            )
        assert raised.value.orig.pgcode == pgcode


def test_the_fake_reads_the_fk_query_it_is_sent_and_refuses_one_it_cannot():
    catalog = Catalog(tables={"site_likes"}, cascade_fks=SITE_OWNED_CASCADE_TABLES | {"site_likes"})
    conn = Connection(Database(catalog))
    # the exemption list is taken from the query: without it the site-owned FKs count too
    everything = FK_POLICY.satisfied_sql.split("AND tc.table_name NOT IN")[0] + ")"
    assert conn.execute(text(everything)).scalar_one() is False
    catalog.cascade_fks -= {"site_likes"}
    assert conn.execute(text(FK_POLICY.satisfied_sql)).scalar_one() is True
    assert conn.execute(text(everything)).scalar_one() is False
    with pytest.raises(AssertionError, match="does not know this FK query"):
        conn.execute(text(FK_POLICY.satisfied_sql.replace("AND rc.delete_rule = 'CASCADE'", "")))


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


def test_a_lyra_constraint_another_booter_added_first_leaves_the_batch_intact():
    """The loser of the race reads "missing", runs its ADD CONSTRAINT and meets the winner's
    constraint. Its handler must swallow exactly that 42P07: anything else raises out of the ONE
    migration transaction and rolls back every statement of the batch."""
    first = _boot_lyra(_lyra_bare())
    constraints = _constraints_created(first)
    assert [key for key, _ in constraints] == [
        ("unified_site_names", "uq_usn"),
        ("wiki_images", "uq_wiki_image_site_url"),
        ("credit_grants", "uq_credit_grants_user_reason_period"),
    ]
    for key, sql in constraints:
        db = _migrate_lyra(_losing_the_race_for(first.catalog, key))

        assert db.ddl() == [sql]  # it ran, lost the race, and changed nothing
        assert db.created == []
        assert [e for e in db.events if e[0] in ("COMMIT", "ROLLBACK")] == [("COMMIT",)]
        assert key in db.catalog.constraints


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
    """Only a CASCADE FK outside the exemptions makes the rewrite run, and the rewrite leaves the
    site-owned tables' CASCADE FKs where they are."""
    up_to_date = _boot_api(_api_bare()).catalog
    assert up_to_date.cascade_fks == SITE_OWNED_CASCADE_TABLES
    up_to_date.cascade_fks.add("site_bookmarks")

    db = _boot_api(up_to_date)

    assert db.ddl() == [FK_POLICY.ddl]
    assert db.catalog.cascade_fks == SITE_OWNED_CASCADE_TABLES


def test_the_fk_policy_check_and_its_rewrite_loop_are_one_query():
    """FK_POLICY promises that the check cannot pass while the loop would still find work. That
    holds only while both read the very same query, exemption list included."""
    query = boot_schema._CASCADE_FKS_ONTO_SITES
    assert FK_POLICY.satisfied_sql == "SELECT NOT EXISTS (" + query + ")"
    assert FK_POLICY.ddl.count(query) == 1


def test_an_api_constraint_another_booter_added_first_does_not_abort_the_boot():
    """api and api2 boot together and can both read "missing". The loser's ADD CONSTRAINT meets
    the winner's constraint and raises 42710 (CHECK) or 42P07 (the index behind a UNIQUE). Neither
    is contention (pipeline/utils/boot_ddl.py::is_contention_error), so a handler that misses it
    aborts the loser's startup and fails the deploy's health check."""
    first = _boot_api(_api_bare())
    constraints = _constraints_created(first)
    assert [key for key, _ in constraints] == [
        ("discord_users", "credits_non_negative"),  # CHECK
        ("site_content_links", "uq_content_link"),  # UNIQUE
    ]
    for key, sql in constraints:
        db = _losing_the_race_for(first.catalog, key)
        run_api_boot_schema(db)

        assert db.ddl() == [sql]  # it ran, lost the race, and changed nothing
        assert db.created == []
        assert ("ROLLBACK",) not in db.events
        assert key in db.catalog.constraints


def test_each_api_step_checks_and_alters_in_its_own_transaction_under_the_lock_timeout():
    up_to_date = _boot_api(_api_bare()).catalog
    del up_to_date.columns[("card_stats", "commons_image")]

    db = _boot_api(up_to_date)

    transactions = [t.sql() for t in _transactions(db)]
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


def test_a_step_retried_after_contention_reads_the_catalog_again(monkeypatch, caplog):
    """api and lyra can both read "missing"; the loser of the lock race retries, finds the
    column the winner added, and runs no DDL of its own.

    The other booter adds the column here, so the column at the end, the single ALTER and the
    ROLLBACK prove nothing about a retry: they hold just as well when the step is given up after
    its first timeout. What does is the step's second transaction, the one backoff before it and
    the absence of a "skipped" warning."""
    db, slept = _outcome_missing_and_contended(monkeypatch, caplog)

    def the_other_booter_adds_it() -> None:
        db.catalog.columns[("research_nodes", "outcome")] = "character varying(20)"

    db.on_fail = the_other_booter_adds_it

    run_api_boot_schema(db)

    attempts = _attempts(db, _OUTCOME)
    assert [t.outcome for t in attempts] == ["ROLLBACK", "COMMIT"]
    assert attempts[0].sql()[-1] == _ADD_OUTCOME  # the attempt that lost the lock race
    assert "FROM pg_catalog.pg_attribute" in attempts[1].sql()[-1]  # the retry asked, and stopped
    assert db.ddl() == [_ADD_OUTCOME]
    assert db.created == []
    assert slept == [2]
    assert f"{_OUTCOME_LABEL} hit lock contention (attempt 1/3)" in caplog.text
    assert "skipped after 3 contention retries" not in caplog.text


def test_a_step_retried_after_contention_runs_its_statement_again_while_it_is_needed(
    monkeypatch, caplog
):
    """Nobody else added the column: the retry finds it still missing and adds it itself. A boot
    that gave the step up instead would start without the column its models read."""
    db, slept = _outcome_missing_and_contended(monkeypatch, caplog)

    run_api_boot_schema(db)

    attempts = _attempts(db, _OUTCOME)
    assert [t.outcome for t in attempts] == ["ROLLBACK", "COMMIT"]
    assert [t.sql()[-1] for t in attempts] == [_ADD_OUTCOME, _ADD_OUTCOME]
    assert db.ddl() == [_ADD_OUTCOME, _ADD_OUTCOME]
    assert [(kind, key) for kind, key, _ in db.created] == [
        ("column", ("research_nodes", "outcome"))
    ]
    assert db.catalog.columns[("research_nodes", "outcome")] == "character varying(20)"
    assert slept == [2]
    assert "skipped after 3 contention retries" not in caplog.text


def test_a_step_still_contended_after_three_attempts_is_left_to_the_next_boot(monkeypatch, caplog):
    """Contention is expected while api and lyra both still have DDL to run. After three attempts
    the step is skipped with a warning (the next boot completes it) and the API starts: every later
    step still runs."""
    db, slept = _outcome_missing_and_contended(monkeypatch, caplog)
    timeout = db.fail_next_ddl

    def the_lock_is_still_held() -> None:
        db.fail_next_ddl = timeout

    db.on_fail = the_lock_is_still_held

    run_api_boot_schema(db)

    attempts = _attempts(db, _OUTCOME)
    assert [t.outcome for t in attempts] == ["ROLLBACK", "ROLLBACK", "ROLLBACK"]
    assert slept == [2, 4]
    assert f"{_OUTCOME_LABEL} skipped after 3 contention retries" in caplog.text
    assert ("research_nodes", "outcome") not in db.catalog.columns
    transactions = _transactions(db)
    assert len(transactions) == len(boot_schema.API_BOOT_SCHEMA) + 2
    assert transactions[-1].outcome == "COMMIT"
    assert transactions[-1].statements[-1][0] == " ".join(FK_POLICY.satisfied_sql.split())


@pytest.mark.parametrize("pgcode", ["42703", "42P07"])
def test_an_error_that_is_not_contention_aborts_the_startup_at_once(monkeypatch, caplog, pgcode):
    """Until the audit of 2026-08-05 (M5) every boot error was swallowed as "lock contention" and
    the API started healthy on a schema it did not have. Anything else than a lock timeout, a
    statement timeout or a deadlock raises out of the boot at its first attempt, so the deploy's
    health check fails loudly."""
    db, slept = _outcome_missing_and_contended(monkeypatch, caplog)
    db.fail_next_ddl = ProgrammingError("ALTER TABLE", {}, _PgError(pgcode, "not contention"))

    with pytest.raises(ProgrammingError):
        run_api_boot_schema(db)

    assert [t.outcome for t in _attempts(db, _OUTCOME)] == ["ROLLBACK"]
    labels = [f"Migration ({step.label})" for step in boot_schema.API_BOOT_SCHEMA]
    assert len(_transactions(db)) == labels.index(_OUTCOME_LABEL) + 1  # no later step ran
    assert slept == []
    assert f"[STARTUP] {_OUTCOME_LABEL} FAILED (aborting startup)" in caplog.text


@pytest.mark.parametrize(
    ("error", "pgcode", "contention"),
    [
        (OperationalError("x", {}, _PgError("55P03", "lock timeout")), "55P03", True),
        (OperationalError("x", {}, _PgError("57014", "statement timeout")), "57014", True),
        (OperationalError("x", {}, _PgError("40P01", "deadlock detected")), "40P01", True),
        (ProgrammingError("x", {}, _PgError("42P07", "relation exists")), "42P07", False),
        (ProgrammingError("x", {}, _PgError("42703", "column does not exist")), "42703", False),
        (InvalidRequestError("no driver error behind it"), None, False),
    ],
)
def test_only_a_lock_timeout_a_statement_timeout_or_a_deadlock_is_contention(
    error, pgcode, contention
):
    assert pgcode_of(error) == pgcode
    assert is_contention_error(error) is contention


def test_both_boot_paths_classify_contention_with_the_one_shared_function():
    """The API's run_boot_step and Lyra's main() each carried their own copy of the pgcode list.
    pipeline/ may not import api/ (import-linter), so the one copy lives in pipeline/utils/."""
    import pipeline.lyra.orchestrator as orch

    assert boot_schema.is_contention_error is is_contention_error
    assert orch.is_contention_error is is_contention_error
    assert "is_contention_error" in names_used_by(REPO / "api" / "boot_schema.py", "run_boot_step")
    assert "is_contention_error" in names_used_by(REPO / "pipeline/lyra/orchestrator.py", "main")


#: The start of a DDL statement in a source string. A regex, not the fake's _DDL_HEAD: an f-string
#: splits into parts, and its first part may be just ``"ALTER "``.
_DDL_IN_SOURCE = re.compile(r"\s*(?:ALTER|CREATE|DROP|DO)\b")


def test_the_api_startup_runs_the_boot_schema_and_holds_no_ddl_of_its_own():
    """api/main.py::lifespan ran the API's 29 statements unconditionally until 2026-09-23. It must
    call run_api_boot_schema - a startup without it leaves create_all's existing tables without the
    columns the models read - and no DDL string may come back into api/main.py beside it: such a
    statement would lock its table on every start of api and api2, and no boot here would see it."""
    main = REPO / "api" / "main.py"
    used = names_used_by(main, "lifespan")
    assert {"run_api_boot_schema", "api.boot_schema.run_api_boot_schema"} <= used
    ddl = [
        (node.lineno, node.value)
        for node in ast.walk(ast.parse(main.read_text(encoding="utf-8")))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and _DDL_IN_SOURCE.match(node.value)
    ]
    assert ddl == []


# --------------------------------------------------------------------------------------------
# the building blocks
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["News_Items", "news items", "x;drop", '"quoted"', "", "1st"])
def test_a_name_that_is_not_a_plain_lower_case_identifier_is_refused(bad):
    """PostgreSQL folds an unquoted name to lower case and the catalog queries compare against
    the folded name: a mixed-case name would read as "missing" on every boot, and its ALTER TYPE
    or ADD CONSTRAINT would take ACCESS EXCLUSIVE on every boot again."""
    builders = [
        lambda n: add_column(n, "c", "TEXT"),
        lambda n: add_column("t", n, "TEXT"),
        lambda n: set_varchar_length(n, "c", 10),
        lambda n: set_varchar_length("t", n, 10),
        lambda n: create_table(n, "id INTEGER"),
        lambda n: create_index(n, "t", "(c)"),
        lambda n: create_index("i", n, "(c)"),
        lambda n: add_constraint(n, "k", "CHECK (c > 0)", duplicate=("duplicate_object",)),
        lambda n: add_constraint("t", n, "CHECK (c > 0)", duplicate=("duplicate_object",)),
        lambda n: create_extension(n),
        lambda n: relation_exists(Connection(Database(Catalog(tables=set()))), n),
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
