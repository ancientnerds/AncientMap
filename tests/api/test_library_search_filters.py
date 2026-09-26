# SPDX-License-Identifier: AGPL-3.0-only
"""GET /api/library/search filters by array membership: '<value> = ANY (column)'.

period_tags and source_types are Postgres arrays. The filters were written as
``column.any(value)``, which the ARRAY comparator renders as ``value = ANY (column)`` but
which the ORM attribute's type reads as the relationship ``any()`` - ``mypy api/`` refused
the string argument (HUMAN_ONLY A7). ``any_(column) == value`` is the typed spelling of the
same SQL; these tests pin the rendered statement.

DB-less on tests/fake_sql.OrmSession: real ORM queries rendered with the PostgreSQL dialect.
"""

from __future__ import annotations

from api.routes import library
from tests.fake_sql import OrmSession


def _search(**filters: object) -> str:
    """The page query's SQL; the count query must filter the same way."""
    session = OrmSession()
    args: dict[str, object] = {
        "q": None,
        "period": None,
        "source_type": None,
        "tier": None,
        "sort": "citations",
        "page": 1,
        "page_size": 50,
    }
    library.search_library(**{**args, **filters}, db=session)
    count_sql, page_sql = session.sql
    where = page_sql.split("WHERE ", 1)[1].split(" ORDER BY", 1)[0]
    assert where in count_sql
    return page_sql


def test_the_period_filter_asks_for_the_tag_in_the_array():
    sql = _search(period="Neolithic")
    assert "WHERE 'Neolithic' = ANY (library_sources.period_tags)" in sql


def test_the_type_filter_asks_for_the_type_in_the_array():
    sql = _search(source_type="journal")
    assert "WHERE 'journal' = ANY (library_sources.source_types)" in sql


def test_both_filters_combine():
    sql = _search(period="Bronze Age", source_type="story")
    assert (
        "WHERE 'Bronze Age' = ANY (library_sources.period_tags) "
        "AND 'story' = ANY (library_sources.source_types)"
    ) in sql
