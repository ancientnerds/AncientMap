# SPDX-License-Identifier: AGPL-3.0-only
"""The crawlable /sites/ pages under E4 (migration 0020) and the two retired hub slugs.

A retired site is listed nowhere (country index, country hub, siblings, parent link) and its
own URL answers 410 Gone - like a withdrawn story - whether it is reached by its canonical
slug or by the legacy /site.html?id= URL. DB-less, with the strict RecordingSession.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api.routes import sites_html as sh
from pipeline.utils.public_sites import not_retired
from tests.fake_sql import RecordingSession

SHOWN = not_retired()
SITE_ID = "17cf019a-0000-4000-8000-000000000000"


def _run(coro):
    with (
        patch("api.seo_shell.render_page", return_value=("<title>x</title>", "<p>y</p>")),
        patch("api.seo_shell.render_app_shell", return_value="<html>ok</html>"),
    ):
        return asyncio.run(coro)


def test_the_curated_predicate_carries_the_scope_filter():
    assert sh._CURATED_WHERE.endswith(SHOWN)
    assert "source_id = 'ancient_nerds'" in sh._CURATED_WHERE


def test_country_index_lists_only_shown_sites():
    db = RecordingSession({"GROUP BY country": [SimpleNamespace(country="Syria", count=3)]})
    _run(sh.sites_index(db=db))
    assert SHOWN in db.statement_with("GROUP BY country")


def test_country_hub_lists_only_shown_sites():
    db = RecordingSession(
        {
            "SELECT DISTINCT country": [SimpleNamespace(country="Syria")],
            "LEFT JOIN LATERAL": [],
        }
    )
    resp = _run(sh.sites_by_country("syria", db=db))
    assert resp.status_code == 200
    assert SHOWN in db.statement_with("SELECT DISTINCT country")
    assert SHOWN in db.statement_with("LEFT JOIN LATERAL")


@pytest.mark.parametrize(
    ("old", "new"),
    [("georgia-country", "/sites/georgia"), ("chile-easter-island", "/sites/chile")],
)
def test_the_two_retired_hub_slugs_answer_301_to_the_hub_that_replaced_them(old, new):
    """The homepage hub list baked on 2026-09-05 still links both; both were 404."""
    db = RecordingSession(
        {
            "SELECT DISTINCT country": [
                SimpleNamespace(country="Georgia"),
                SimpleNamespace(country="Chile"),
            ]
        }
    )
    resp = _run(sh.sites_by_country(old, db=db))
    assert resp.status_code == 301
    assert resp.headers["location"] == new


def test_united_kingdom_stays_404():
    """Decision pinned 2026-09-22: /sites/united-kingdom is NOT redirected. The UK lane splits
    those rows into England / Scotland / Wales / Northern Ireland, so no single hub replaces
    the old one - a 301 to any of them would claim an equivalence that does not exist."""
    db = RecordingSession({"SELECT DISTINCT country": [SimpleNamespace(country="England")]})
    resp = _run(sh.sites_by_country("united-kingdom", db=db))
    assert resp.status_code == 404
    assert "united-kingdom" not in sh._RETIRED_HUBS


def test_a_live_country_wins_over_a_retired_slug_of_the_same_name():
    """If a country ever carries one of these slugs again, its hub is served, not redirected."""
    db = RecordingSession(
        {
            "SELECT DISTINCT country": [SimpleNamespace(country="Chile Easter Island")],
            "LEFT JOIN LATERAL": [],
        }
    )
    resp = _run(sh.sites_by_country("chile-easter-island", db=db))
    assert resp.status_code == 200


def test_detail_page_of_a_retired_site_answers_410():
    db = RecordingSession(
        {"WHERE id >= CAST(:lo AS uuid)": [SimpleNamespace(id=SITE_ID, scope_status="retired")]}
    )
    resp = _run(sh.site_detail(country="syria", slug="damascus-gate-17cf019a", db=db))
    assert resp.status_code == 410
    assert "location" not in resp.headers
    assert resp.headers["cache-control"] == "public, max-age=86400"
    # the curated lookup asked for shown sites only
    assert SHOWN in db.statement_with("LEFT(REPLACE(id::text, '-', ''), 8) = :prefix")


def test_detail_page_prefers_the_retired_row_on_a_shared_prefix():
    db = RecordingSession()
    sh._site_by_prefix("17cf019a", db)
    assert "ORDER BY (scope_status IS NOT DISTINCT FROM 'retired') DESC" in db.statements()[0]


def test_detail_page_of_an_uncurated_shown_site_still_goes_to_the_globe():
    db = RecordingSession(
        {"WHERE id >= CAST(:lo AS uuid)": [SimpleNamespace(id=SITE_ID, scope_status=None)]}
    )
    resp = _run(sh.site_detail(country="syria", slug="damascus-gate-17cf019a", db=db))
    assert resp.status_code == 301
    assert resp.headers["location"] == f"/globe.html#focus={SITE_ID}"


def test_legacy_url_of_a_retired_site_answers_410():
    db = RecordingSession({"SELECT scope_status FROM": [SimpleNamespace(scope_status="retired")]})
    resp = asyncio.run(sh.legacy_site_redirect(id=SITE_ID, db=db))
    assert resp.status_code == 410
    assert SHOWN in db.statement_with("SELECT name, country FROM unified_sites")


def test_siblings_and_parent_link_only_shown_sites():
    row = SimpleNamespace(
        id=SITE_ID, country="Syria", lat=33.5, lon=36.3, parent_site_id="aaaa0000-0000-4000-8000-0"
    )
    db = RecordingSession()
    with patch.object(sh, "public_stories_query") as stories:
        stories.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        related = sh._related_content(row, db)
    assert related["parent"] is None and related["siblings"] == []
    assert SHOWN in db.statement_with("WHERE id::text = :pid")
    assert SHOWN in db.statement_with("ORDER BY (lat - :lat)")
