# SPDX-License-Identifier: AGPL-3.0-only
"""pipeline.database.affected_rows: the row count of a data-changing Session.execute.

SQLAlchemy 2.0 types ``Session.execute`` as returning ``Result``, which has no ``rowcount``;
the routes that report how many rows an UPDATE or DELETE touched therefore failed
``mypy api/`` (HUMAN_ONLY A7: '"Result[Any]" has no attribute "rowcount"'). The helper
states what SQLAlchemy returns at runtime. These tests pin that runtime fact on a real
session (SQLite in memory, no Postgres needed) for both statement kinds the api runs: a
``text()`` UPDATE/DELETE and an ORM-enabled INSERT ... ON CONFLICT DO NOTHING.
"""

from __future__ import annotations

from sqlalchemy import Integer, String, create_engine, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from pipeline.database import affected_rows


class _Base(DeclarativeBase):
    pass


class _Unlock(_Base):
    __tablename__ = "unlocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(20), unique=True)


def _session() -> Session:
    engine = create_engine("sqlite://")
    _Base.metadata.create_all(engine)
    return Session(engine)


def test_a_text_update_and_delete_report_the_rows_they_matched():
    with _session() as session:
        session.execute(text("INSERT INTO unlocks (id, name) VALUES (1, 'a'), (2, 'b'), (3, 'c')"))

        updated = session.execute(text("UPDATE unlocks SET name = name || '!' WHERE id < 3"))
        deleted = session.execute(text("DELETE FROM unlocks WHERE id = 99"))

        assert isinstance(updated, CursorResult)
        assert affected_rows(updated) == 2
        assert affected_rows(deleted) == 0


def test_an_orm_insert_on_conflict_do_nothing_reports_whether_it_inserted():
    """The shape of check_and_unlock's claim: 1 for the first insert, 0 for the duplicate."""
    stmt = sqlite_insert(_Unlock).values(id=1, name="first").on_conflict_do_nothing()
    with _session() as session:
        first = session.execute(stmt)
        again = session.execute(stmt)

        assert isinstance(first, CursorResult)
        assert (affected_rows(first), affected_rows(again)) == (1, 0)
