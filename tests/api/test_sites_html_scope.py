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
SURVIVOR_ID = "ed186ea9-9ed1-415d-828b-97d9f21401d2"


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


def test_united_kingdom_is_404_once_the_uk_lane_has_moved_its_rows():
    """Decision pinned 2026-09-22: /sites/united-kingdom is NOT redirected. The UK lane splits
    those rows into England / Scotland / Wales / Northern Ireland, so no single hub replaces
    the old one - a 301 to any of them would claim an equivalence that does not exist."""
    db = RecordingSession({"SELECT DISTINCT country": [SimpleNamespace(country="England")]})
    resp = _run(sh.sites_by_country("united-kingdom", db=db))
    assert resp.status_code == 404
    assert "united-kingdom" not in sh._RETIRED_HUBS


def test_united_kingdom_is_a_live_hub_while_rows_still_carry_it():
    """6 curated rows still carried 'United Kingdom' on 2026-09-23 and the page answered 200.
    It stays a normal hub until the UK lane moves them - a deploy that serves it with 200 is
    correct, not a failed redirect."""
    db = RecordingSession(
        {
            "SELECT DISTINCT country": [
                SimpleNamespace(country="England"),
                SimpleNamespace(country="United Kingdom"),
            ],
            "LEFT JOIN LATERAL": [],
        }
    )
    resp = _run(sh.sites_by_country("united-kingdom", db=db))
    assert resp.status_code == 200


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
        {
            "WHERE id >= CAST(:lo AS uuid)": [
                SimpleNamespace(id=SITE_ID, scope_status="retired", scope_reason="out of window")
            ]
        }
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
        {
            "WHERE id >= CAST(:lo AS uuid)": [
                SimpleNamespace(id=SITE_ID, scope_status=None, scope_reason=None)
            ]
        }
    )
    resp = _run(sh.site_detail(country="syria", slug="damascus-gate-17cf019a", db=db))
    assert resp.status_code == 301
    assert resp.headers["location"] == f"/globe.html#focus={SITE_ID}"


def test_legacy_url_of_a_retired_site_answers_410():
    db = RecordingSession(
        {
            "SELECT scope_status, scope_reason FROM": [
                SimpleNamespace(scope_status="retired", scope_reason="out of window")
            ]
        }
    )
    resp = asyncio.run(sh.legacy_site_redirect(id=SITE_ID, db=db))
    assert resp.status_code == 410
    assert SHOWN in db.statement_with("SELECT name, country FROM unified_sites")


# D14: a duplicate merge retires the loser as `duplicate_of:<survivor id>`. Its URL has a
# canonical twin then, so it answers 301 to it - a 410 would leave Search Console holding a
# withdrawn page for a site that lives on under another URL. Every other retirement stays 410.
SURVIVOR = SimpleNamespace(name="Chiapa de Corzo", country="Mexico")
SURVIVOR_URL = f"/sites/mexico/chiapa-de-corzo-{SURVIVOR_ID[:8]}"


class _LoserSession(RecordingSession):
    """The curated lookup by id (_LEGACY_SITE_SQL) finds `survivor` for the survivor's id and
    nothing for the loser's: the loser is retired, so it is not a curated page."""

    def __init__(self, reason, survivor):
        super().__init__(
            {
                "WHERE id >= CAST(:lo AS uuid)": [
                    SimpleNamespace(id=SITE_ID, scope_status="retired", scope_reason=reason)
                ],
                "SELECT scope_status, scope_reason FROM": [
                    SimpleNamespace(scope_status="retired", scope_reason=reason)
                ],
            }
        )
        self.survivor = survivor

    def execute(self, stmt, params=None):
        result = super().execute(stmt, params)
        if "SELECT name, country FROM unified_sites" in self.statements()[-1]:
            found = [self.survivor] if self.survivor and params["id"] == SURVIVOR_ID else []
            return type(result)(found)
        return result

    def survivor_lookups(self):
        return [p for s, p in self.log if "SELECT name, country FROM unified_sites" in s]


def test_a_duplicate_loser_with_a_shown_survivor_answers_301_to_the_survivor():
    db = _LoserSession(f"duplicate_of:{SURVIVOR_ID}", SURVIVOR)
    resp = _run(sh.site_detail(country="syria", slug="damascus-gate-17cf019a", db=db))
    assert resp.status_code == 301
    assert resp.headers["location"] == SURVIVOR_URL
    assert db.survivor_lookups() == [{"id": SURVIVOR_ID}]
    # the survivor is looked up among the shown curated sites only
    assert SHOWN in db.statement_with("SELECT name, country FROM unified_sites")


def test_the_legacy_url_of_a_duplicate_loser_answers_301_to_the_survivor_and_keeps_utm():
    db = _LoserSession(f"duplicate_of:{SURVIVOR_ID}", SURVIVOR)
    resp = asyncio.run(sh.legacy_site_redirect(id=SITE_ID, utm_source="discord", db=db))
    assert resp.status_code == 301
    assert resp.headers["location"] == f"{SURVIVOR_URL}?utm_source=discord"
    assert db.survivor_lookups() == [{"id": SITE_ID}, {"id": SURVIVOR_ID}]


@pytest.mark.parametrize(
    "reason",
    [
        "out of the E3 window",
        None,
        "duplicate_of:",
        "duplicate_of:not-a-uuid",
        f"duplicate_of:{SURVIVOR_ID[:-1]}",
        f"duplicate_of:{SURVIVOR_ID} and more",
        f"duplicate_of:{SURVIVOR_ID.upper()}",
        f"duplicate:{SURVIVOR_ID}",
    ],
)
def test_any_other_or_malformed_reason_stays_410_without_asking_for_a_survivor(reason):
    db = _LoserSession(reason, SURVIVOR)
    resp = _run(sh.site_detail(country="syria", slug="damascus-gate-17cf019a", db=db))
    assert resp.status_code == 410
    assert "location" not in resp.headers
    assert db.survivor_lookups() == []


def test_a_duplicate_loser_whose_survivor_is_retired_or_missing_stays_410():
    """The curated predicate excludes a retired and a non-curated survivor; a missing id
    matches no row. All three look the same to the route: no row, so no redirect."""
    db = _LoserSession(f"duplicate_of:{SURVIVOR_ID}", None)
    resp = _run(sh.site_detail(country="syria", slug="damascus-gate-17cf019a", db=db))
    assert resp.status_code == 410
    assert "location" not in resp.headers
    assert db.survivor_lookups() == [{"id": SURVIVOR_ID}]


def test_the_legacy_url_of_a_loser_with_a_gone_survivor_stays_410():
    db = _LoserSession(f"duplicate_of:{SURVIVOR_ID}", None)
    resp = asyncio.run(sh.legacy_site_redirect(id=SITE_ID, db=db))
    assert resp.status_code == 410


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
