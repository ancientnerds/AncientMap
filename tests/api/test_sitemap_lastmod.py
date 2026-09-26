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
import inspect
import re
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from api.routes import sitemap as sm
from api.routes import sites_html
from pipeline.utils import public_sites as PS

NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
SITE = "4a5a324f-0000-4000-8000-000000000001"


#: The stamp of a journal row whose stamp does not matter to the test: a Phase-4 chunk.
ANY_STAMP = "phase4:p4-0001:chunk-0001"


def _journal_engine(rows: list[tuple[str | None, ...]]) -> sqlite3.Connection:
    """The journal as the grouping reads it; a row is (site, table, column, applied_at) or the same
    with its run_stamp."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE remediation_change_log (site_id_ref TEXT, table_name TEXT, "
        "column_name TEXT, applied_at TEXT, run_stamp TEXT NOT NULL)"
    )
    conn.executemany(
        "INSERT INTO remediation_change_log VALUES (?, ?, ?, ?, ?)",
        [row if len(row) == 5 else (*row, ANY_STAMP) for row in rows],
    )
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


def test_a_journalled_write_the_page_does_not_render_does_not_advance_it():
    """The card game's stats and a unified_sites column the page never shows change no byte of the
    site page, so they must not move the lastmod, nor make the hourly IndexNow cycle announce
    unchanged pages. (The card text itself is a page column since lane WB: the next test.)"""
    conn = _journal_engine(
        [
            (SITE, "unified_sites", "description", "2026-10-02 09:00:00"),
            (SITE, "card_stats", "antiquity", "2026-10-09 10:00:00"),  # the card game's stats
            (SITE, "unified_sites", "geom", "2026-10-10 09:00:00"),
            (SITE, "unified_sites", "thumbnail_url", "2026-10-10 10:00:00"),  # the hub's fallback
            (SITE, "wiki_images", "image_kind", "2026-10-11 09:00:00"),
            (SITE, "wiki_images", "author_url", "2026-10-11 10:00:00"),
            (SITE, "wiki_images", "original_url", "2026-10-11 11:00:00"),
            (SITE, "wiki_images", "file_size_bytes", "2026-10-11 12:00:00"),
            (SITE, "wiki_images", "description", "2026-10-12 09:00:00"),  # a page column's name
            (SITE, "card_stats", "is_hero", "2026-10-12 10:00:00"),  # an image column's name
        ]
    )
    assert _newest(conn) == {SITE: "2026-10-02 09:00:00"}


def test_a_lane_wb_card_write_advances_the_page():
    """Owner decision O10 (2026-09-26): the page shows the AI footnote while a lane-WB teaser
    provenance hashes the site's live card (`card_ai` in the SSR payload), so lane WB's card write -
    a teaser, a clear - and its reversal add or remove that notice and move the page's date."""
    for stamp in ("wb-teaser-card-s001", "wb-teaser-card-s001-rollback"):
        conn = _journal_engine(
            [
                (SITE, "unified_sites", "description", "2026-10-02 09:00:00"),
                (SITE, "card_stats", "card_description", "2026-10-09 09:00:00", stamp),
            ]
        )
        assert _newest(conn) == {SITE: "2026-10-09 09:00:00"}, stamp


def test_a_card_write_before_lane_wb_does_not_advance_the_page():
    """Before lane WB the card never touched the page: the P5 sitting's ~761 cards and clears and
    the card-stats waves are journalled, but counting them would move the date of pages that did
    not change when they were written (a one-time lastmod jump on the WB deploy)."""
    conn = _journal_engine(
        [
            (SITE, "unified_sites", "description", "2026-10-02 09:00:00"),
            (SITE, "card_stats", "card_description", "2026-10-09 09:00:00", ANY_STAMP),
            (SITE, "card_stats", "card_description", "2026-10-10 09:00:00", "phase5:p5-0001:c-1"),
        ]
    )
    assert _newest(conn) == {SITE: "2026-10-02 09:00:00"}


def test_a_hero_change_advances_the_page():
    """The page shows one image - the hero, else the lead, else the first by sort order, never an
    excluded one - with its author, licence and Commons link (decision D6, 2026-09-23). An image
    lane that sets a new hero or excludes the shown one changes the page, so the page's date moves
    and the hourly IndexNow cycle announces it."""
    for column in ("is_hero", "is_excluded"):
        conn = _journal_engine(
            [
                (SITE, "unified_sites", "description", "2026-10-02 09:00:00"),
                (SITE, "wiki_images", column, "2026-10-20 09:00:00"),
            ]
        )
        assert _newest(conn) == {SITE: "2026-10-20 09:00:00"}, column


def test_every_column_the_site_page_reads_advances_it():
    """The design's six (description, raw_data, name, country, site_type, period_start), the other
    unified_sites columns the SSR site page renders, which later lanes journal (period_name, the
    coordinates), the two card_stats columns the page shows (its Wikipedia link and language), and
    the image columns: every one of them moves the date, in its own table only. The card text is
    one of them since lane WB, as lane WB writes it (the page's AI footnote reads it,
    `test_a_lane_wb_card_write_advances_the_page`)."""
    for table, columns in PS.PAGE_COLUMNS.items():
        for column in columns:
            stamp = PS.PAGE_COLUMN_STAMPS.get((table, column), ANY_STAMP).replace("%", "s001")
            conn = _journal_engine([(SITE, table, column, "2026-10-02 09:00:00", stamp)])
            assert _newest(conn) == {SITE: "2026-10-02 09:00:00"}, (table, column)
    assert set(PS.PAGE_COLUMN_STAMPS) == {("card_stats", "card_description")}
    assert {"description", "raw_data", "name", "country", "site_type", "period_start"} <= set(
        PS.PAGE_COLUMNS["unified_sites"]
    )
    assert "card_description" in PS.PAGE_COLUMNS["card_stats"]


def _columns(listed: str) -> set[str]:
    """The column names of a comma-separated SQL list: casts, JSON paths, aliases, table prefixes
    and sort directions are cut off."""
    names = set()
    for item in listed.split(","):
        name = re.split(r"::|->| AS | DESC| ASC", item.strip())[0].strip()
        names.add(name.split(".")[-1])
    return names


def test_the_page_columns_are_exactly_the_ones_the_ssr_route_reads():
    """The date must move for a write of every column the page reads and of nothing else, so the
    list is taken from the route's own queries: the detail SELECT (unified_sites, and card_stats
    through `cs.`) and the one-image query of `_related_content` (its SELECT list, the exclusion in
    its WHERE and its ORDER BY, which picks the hero). A column the route starts to render, or
    stops rendering, turns this red until PAGE_COLUMNS follows."""
    detail = inspect.getsource(sites_html.site_detail)
    listed = re.search(r"SELECT (id::text AS id,.*?)\n\s*FROM unified_sites", detail, re.S)
    assert listed is not None
    items = [item.strip() for item in listed.group(1).split(",")]
    own = _columns(",".join(item for item in items if not item.startswith("cs.")))
    card = _columns(",".join(item for item in items if item.startswith("cs.")))
    assert set(PS.PAGE_COLUMNS["unified_sites"]) == own - {"id"}
    assert set(PS.PAGE_COLUMNS["card_stats"]) == card

    related = inspect.getsource(sites_html._related_content)
    image = re.search(
        r"SELECT (?P<select>[^\n]*)\n\s*FROM wiki_images\n\s*WHERE (?P<where>[^\n]*)\n"
        r"\s*ORDER BY (?P<order>[^\n]*)\n\s*LIMIT 1",
        related,
    )
    assert image is not None
    chooses = set(re.findall(r"\b(is_[a-z_]+)\b", image["where"])) | _columns(image["order"])
    assert set(PS.PAGE_COLUMNS["wiki_images"]) == _columns(image["select"]) | chooses
    assert set(PS.PAGE_COLUMNS) == {"unified_sites", "card_stats", "wiki_images"}


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
