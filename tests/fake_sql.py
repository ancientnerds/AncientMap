# SPDX-License-Identifier: AGPL-3.0-only
"""DB-less stand-ins for a SQLAlchemy Session, strict where the real one is strict.

There is no local database (CLAUDE.md, decision 2026-09-20), so route and pipeline tests
run their queries against fakes. A fake that is more permissive than the real object hides
bugs: on 2026-09-22 a startup import passed its tests while every production boot failed,
because the fake session took a plain string that SQLAlchemy 2 refuses. These fakes refuse
exactly that, and the ORM variant builds its queries with a real ``Query`` - an invalid ORM
expression raises here as it would in production.

``RecordingSession``  - for ``session.execute(text(...))``. Records (sql, params), answers each
                        statement with the rows of the first registered fragment it contains.
``OrmSession``        - for ``session.query(...)``. Builds a real Query, renders its statement
                        with the PostgreSQL dialect on every terminal call, answers from a queue.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import ArgumentError, MultipleResultsFound, NoResultFound
from sqlalchemy.orm import Session
from sqlalchemy.sql.base import Executable
from sqlalchemy.sql.elements import TextClause


class FakeResult:
    """The subset of CursorResult the code under test uses."""

    def __init__(self, rows: list[Any], rowcount: int | None = None) -> None:
        self._rows = list(rows)
        self.rowcount = len(self._rows) if rowcount is None else rowcount

    def fetchall(self) -> list[Any]:
        return list(self._rows)

    def all(self) -> list[Any]:
        return list(self._rows)

    def fetchone(self) -> Any:
        return self._rows[0] if self._rows else None

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalar(self) -> Any:
        if not self._rows:
            return None
        row = self._rows[0]
        if isinstance(row, tuple):
            return row[0]
        return row

    def mappings(self) -> FakeResult:
        return FakeResult([dict(vars(r)) if hasattr(r, "__dict__") else r for r in self._rows])

    def one(self) -> Any:
        if len(self._rows) != 1:
            raise AssertionError(f"one() on {len(self._rows)} rows")
        return self._rows[0]

    def scalar_one(self) -> Any:
        # The real one raises unless there is exactly one row; a data statement answered with
        # no rows must not read as a falsy scalar.
        if not self._rows:
            raise NoResultFound("scalar_one() on 0 rows")
        if len(self._rows) > 1:
            raise MultipleResultsFound(f"scalar_one() on {len(self._rows)} rows")
        row = self._rows[0]
        return row[0] if isinstance(row, tuple) else row

    def __iter__(self) -> Iterator[Any]:
        return iter(self._rows)


def sql_of(stmt: Any) -> str:
    """The SQL text of an Executable, refusing what SQLAlchemy 2 refuses."""
    if not isinstance(stmt, Executable):
        raise ArgumentError(
            f"SQLAlchemy 2 does not execute {type(stmt).__name__} - wrap raw SQL in text()"
        )
    if isinstance(stmt, TextClause):
        return stmt.text
    return str(stmt.compile(dialect=postgresql.dialect()))


class RecordingSession:
    """Records every statement; answers from ``answers`` by fragment match.

    ``answers`` maps an SQL fragment to the rows every statement containing it returns - the
    same rows each time. The first fragment (in insertion order) the statement contains
    wins; a statement no fragment matches returns no rows.
    """

    def __init__(self, answers: dict[str, list[Any]] | None = None) -> None:
        self.answers = {k: list(v) for k, v in (answers or {}).items()}
        self.log: list[tuple[str, dict[str, Any]]] = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, stmt: Any, params: Any = None) -> FakeResult:
        sql = sql_of(stmt)
        self.log.append((sql, dict(params or {}) if isinstance(params, dict) else {}))
        for fragment, rows in self.answers.items():
            if fragment in sql:
                return FakeResult(rows)
        return FakeResult([])

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        return None

    def __enter__(self) -> RecordingSession:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    # -- inspection helpers -------------------------------------------------------------

    def statements(self) -> list[str]:
        return [sql for sql, _ in self.log]

    def statement_with(self, fragment: str) -> str:
        hits = [sql for sql in self.statements() if fragment in sql]
        if len(hits) != 1:
            raise AssertionError(f"{len(hits)} statements contain {fragment!r}: {hits}")
        return hits[0]


class _CapturedQuery:
    """Wraps a real ORM Query: builder calls pass through, terminal calls are recorded."""

    _BUILDERS = frozenset(
        {
            "filter",
            "filter_by",
            "join",
            "outerjoin",
            "order_by",
            "limit",
            "offset",
            "distinct",
            "group_by",
            "with_entities",
            "options",
            "populate_existing",
            "with_for_update",
            "select_from",
            "yield_per",
        }
    )

    def __init__(self, query: Any, owner: OrmSession) -> None:
        self._query = query
        self._owner = owner

    def __getattr__(self, name: str) -> Any:
        if name not in self._BUILDERS:
            raise AttributeError(f"fake Query does not implement {name!r}")
        method = getattr(self._query, name)

        def builder(*args: Any, **kwargs: Any) -> _CapturedQuery:
            return _CapturedQuery(method(*args, **kwargs), self._owner)

        return builder

    def _record(self) -> list[Any]:
        sql = str(
            self._query.statement.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        self._owner.sql.append(sql)
        return self._owner.next_rows()

    def all(self) -> list[Any]:
        return list(self._record())

    def first(self) -> Any:
        rows = self._record()
        return rows[0] if rows else None

    def one(self) -> Any:
        # Strict like Query.one(): exactly one row, else the error SQLAlchemy raises.
        rows = self._record()
        if not rows:
            raise NoResultFound("one() on 0 rows")
        if len(rows) > 1:
            raise MultipleResultsFound(f"one() on {len(rows)} rows")
        return rows[0]

    def count(self) -> int:
        return len(self._record())

    def scalar(self) -> Any:
        rows = self._record()
        return rows[0] if rows else None

    def __iter__(self) -> Iterator[Any]:
        return iter(self._record())


class OrmSession:
    """``session.query(...)`` with real Query construction and queued answers."""

    def __init__(self, answers: Iterable[list[Any]] = ()) -> None:
        self._real = Session()
        self._answers = list(answers)
        self.sql: list[str] = []
        self.added: list[Any] = []

    def next_rows(self) -> list[Any]:
        return self._answers.pop(0) if self._answers else []

    def query(self, *entities: Any) -> _CapturedQuery:
        return _CapturedQuery(self._real.query(*entities), self)

    def get(self, *_args: Any) -> Any:
        rows = self.next_rows()
        return rows[0] if rows else None

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        return None
