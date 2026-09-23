# SPDX-License-Identifier: AGPL-3.0-only
"""A site page's sitemap lastmod moves when a journalled write changes it (Phase 4, WB-D4).

`apply_remediation_change()` never writes `unified_sites.updated_at` (outside the approved columns,
design entry [6], production_write, COLUMNS), so without the journal no Phase-3 correction and no
Phase-4 description would ever be announced as changed. The page's lastmod is therefore
`GREATEST(COALESCE(updated_at, created_at), max(applied_at))` over the site's journal rows
(`pipeline/utils/public_sites.py`), and the route exposes nothing of the journal but that date.

The journal grouping is evaluated in a real SQL engine (SQLite, the same stand-in
`tests/pipeline/test_public_sites.py` uses), because the question is which rows it counts, which a
string comparison cannot answer. SQLite has no `AT TIME ZONE`; the one clause that converts the
timestamptz to naive UTC is taken out for the evaluation and pinned as a string instead.
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from api.routes import sitemap as sm
from pipeline.utils import public_sites as PS

NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
SITE = "4a5a324f-0000-4000-8000-000000000001"


def _journal_engine(rows: list[tuple[str | None, str, str, str]]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE remediation_change_log (site_id_ref TEXT, table_name TEXT, "
        "column_name TEXT, applied_at TEXT)"
    )
    conn.executemany("INSERT INTO remediation_change_log VALUES (?, ?, ?, ?)", rows)
    return conn


def _newest(conn: sqlite3.Connection) -> dict[str, str]:
    sql = PS.JOURNAL_LAST_WRITE.replace(" AT TIME ZONE 'UTC'", "")
    return dict(conn.execute(f"SELECT site_id_ref, applied_at FROM {sql} jlast").fetchall())  # noqa: S608


def test_the_page_lastmod_is_the_later_of_the_row_and_its_newest_journal_write():
    assert "GREATEST(COALESCE(u.updated_at, u.created_at), jlast.applied_at)" in str(sm._SITES_SQL)
    assert PS.journal_join("u") in str(sm._SITES_SQL)
    assert PS.journal_join("u") in str(sm._COUNTRIES_SQL)
    assert "MAX(applied_at AT TIME ZONE 'UTC')" in PS.JOURNAL_LAST_WRITE


def test_a_phase4_description_write_advances_the_page():
    """The P4 rows (description, raw_data), the L row (raw_data) and the P5 card rows carry the
    site in `site_id_ref`; the newest of them is the page's journal date."""
    conn = _journal_engine(
        [
            (SITE, "unified_sites", "site_type", "2026-09-21 10:00:00"),
            (SITE, "unified_sites", "description", "2026-10-02 09:00:00"),
            (SITE, "unified_sites", "raw_data", "2026-10-02 09:00:00"),
            (None, "unified_sites", "country", "2026-10-05 09:00:00"),
        ]
    )
    assert _newest(conn) == {SITE: "2026-10-02 09:00:00"}


def test_the_route_exposes_a_date_and_nothing_of_the_journal():
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = [
        SimpleNamespace(
            name="Tarxien Temples", country="Malta", id=SITE, lastmod=datetime(2026, 10, 2, 9)
        )
    ]
    body = asyncio.run(sm.sitemap_sites(db=db)).body.decode("utf-8")
    url = ET.fromstring(body).find(f"{NS}url")
    assert [child.tag for child in url] == [f"{NS}loc", f"{NS}lastmod"]
    assert url.findtext(f"{NS}lastmod") == "2026-10-02"
    assert not re.search(r"phase4|raw_data|description", body)
