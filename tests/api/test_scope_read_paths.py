# SPDX-License-Identifier: AGPL-3.0-only
"""Every read of unified_sites in api/ and pipeline/ either hides retired sites or says why not.

Owner decision E4 hides a retired site platform-wide (migration 0020). The plan names about
twenty consumers, and a missed one leaks a retired site (plan section 8.4 risk). A list in
a document goes stale the day someone adds a route; this test does not. It parses every
module under api/ and pipeline/ (plus scripts/build_lyra_index.py, which builds the Qdrant
index Lyra searches), finds each READ of unified_sites - SQL ``FROM``/``JOIN unified_sites``
or an ORM query/join/outerjoin/select/select_from/get/aliased on ``UnifiedSite`` - and
requires one of two things of the function (or module constant) it sits in:

* every read in it applies the scope filter. Each read is judged ON ITS OWN, by its own
  statement and the values that statement is built from (tests/scope_scanner.py spells out
  the rule). A comment, a docstring, an ``import RETIRED`` or a second, filtered query in
  the same function does not count - the first version of this test judged whole
  functions by substring and passed all four;
* or the function is in ``EXEMPT`` below, with the reason it must not filter.

A new unfiltered read fails here with its location. A stale exemption (the function is
gone, or every read in it filters now) fails too, so the list cannot rot.

What this test does not prove: that the filter sits in the right WHERE with the right
alias (a join of two unified_sites aliases passes with one filtered), or that a Python-side
check after ``SELECT ... scope_status`` is correct. The per-consumer tests
(tests/api/test_scope_consumers.py, test_sites_scope.py, test_cardgame_scope.py,
tests/pipeline/test_scope_pipeline.py) render each statement and pin that.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.scope_scanner import ModuleScan, read_paths

REPO = Path(__file__).resolve().parents[2]
SCANNED = [REPO / "api", REPO / "pipeline", REPO / "scripts" / "build_lyra_index.py"]

_WRITE = "founder edit path (write)"
_MATCHING = (
    "matching: a retired site must stay matchable, or it is proposed again (same rule as "
    "site_matcher and prospector dedup)"
)
_INGEST = "ingest/maintenance job over the whole table, not a read surface"
_IMAGE_JOB = (
    "image fetch/backfill job or its CLI stats, not a read surface; the static export and "
    "the APIs never show a retired site's images"
)
_CONTENT_LINKS = (
    "links content to sites (write); a retired site's links are never exported "
    "(static_exporter._export_content_links) and its page answers 410"
)
_CARD_STATS = "card-stat computation, not a draw - every draw applies card_site_in_scope()"

#: Read paths that deliberately do NOT filter retired sites, with the reason. Keyed by
#: "path::function" (innermost function) or "path::<module>:CONSTANT".
EXEMPT: dict[str, str] = {
    # --- boot and maintenance code, not a read surface --------------------------------
    "api/main.py::lifespan": (
        "boot import of legacy JSON contributions: an existence check before an INSERT"
    ),
    "api/services/card_descriptions.py::<module>:_STALE_IDS_SQL": (
        "which card ids have no site row at all - identity, not visibility"
    ),
    "pipeline/lyra/orchestrator.py::_run_migrations": "Lyra's boot migrations and data patches",
    "pipeline/lyra/data_patches.py::add_aliases": "boot data patch: writes alternate names",
    "pipeline/unified_loader.py::load_all": _INGEST,
    "pipeline/unified_loader.py::main": _INGEST,
    "pipeline/lyra/prospector/external_ids.py::refresh_site_external_ids": (
        "identity maintenance (Wikipedia title + QID) that prospector dedup matches on"
    ),
    "pipeline/image_attribution_backfill.py::_hero_rows": _IMAGE_JOB,
    "pipeline/wiki_image_downloader.py::get_sites_to_process": _IMAGE_JOB,
    "pipeline/wiki_image_downloader.py::print_stats": _IMAGE_JOB,
    "pipeline/site_images/batch_updater.py::get_comprehensive_stats": _IMAGE_JOB,
    "pipeline/site_images/batch_updater.py::get_sample_sites": _IMAGE_JOB,
    "pipeline/site_images/megalithic_images.py::get_megalithic_sites_without_images": _IMAGE_JOB,
    "pipeline/site_images/megalithic_images.py::get_stats": _IMAGE_JOB,
    "pipeline/site_images/sketchfab_images.py::get_sites_without_images": _IMAGE_JOB,
    "pipeline/site_images/sketchfab_images.py::get_stats": _IMAGE_JOB,
    "pipeline/site_images/wikimedia_fallback.py::get_image_stats": _IMAGE_JOB,
    "pipeline/site_images/wikimedia_fallback.py::get_sites_without_images": _IMAGE_JOB,
    # --- founder/editor tools and restore points: the whole table, retired rows included
    "api/routes/sites.py::batch_update_sites": _WRITE,
    "api/routes/sites.py::update_site": _WRITE,
    "api/routes/sites.py::_sync_to_radar": "copies a founder edit into the radar row (write)",
    "api/routes/sites.py::replace_source": (
        "founder bulk replace of one non-protected source; snapshots every row first"
    ),
    "api/services/snapshots.py::create_snapshot": (
        "counts the rows a restore point will hold - retired rows are captured too"
    ),
    "api/services/snapshots.py::create_manual_snapshot": (
        "restore point of a whole source - it must hold the retired rows too"
    ),
    "api/services/snapshots.py::create_unified_snapshot": (
        "restore point of the curated set - it must hold the retired rows too"
    ),
    "api/services/snapshots.py::restore_snapshot": (
        "the undo capture of a restore: every row the restore will delete, retired included"
    ),
    "api/routes/wiki_images.py::set_hero": "founder image tool: existence check",
    "api/routes/proposals.py::merge_proposal": "founder review: merge into an existing row",
    "api/routes/radar.py::merge_into_site": "founder review: merge into an existing row",
    # --- matching: a retired site must stay matchable, or it is proposed again ---------
    "api/routes/radar.py::_find_nearest_an_sites_batch": _MATCHING,
    "api/routes/contributions.py::get_lyra_stats": (
        "size of Lyra's matching knowledge base - retired rows are part of it"
    ),
    "pipeline/lyra/site_matcher.py::_find_site_by_name": _MATCHING,
    "pipeline/lyra/site_matcher.py::_match_site_ids": _MATCHING,
    "pipeline/lyra/prospector/dedup.py::<module>:_AN_CTE": _MATCHING,
    "pipeline/lyra/prospector/dedup.py::_r0": _MATCHING,
    "pipeline/lyra/prospector/dedup.py::_r3": _MATCHING,
    "pipeline/lyra/site_identifier.py::_check_name_an_match": _MATCHING,
    "pipeline/lyra/site_identifier.py::_check_spatial_an_match": _MATCHING,
    "pipeline/lyra/site_identifier.py::_fetch_db_candidates": _MATCHING,
    "pipeline/lyra/site_identifier.py::_handle_db_match": _MATCHING,
    "pipeline/lyra/site_identifier.py::_resolve_parent_site": _MATCHING,
    "pipeline/lyra/site_identifier.py::_promote_to_unified_sites": (
        "promotes a radar discovery into unified_sites; the read is its duplicate check"
    ),
    "pipeline/content_linker.py::_link_artwork": _CONTENT_LINKS,
    "pipeline/content_linker.py::_link_generic": _CONTENT_LINKS,
    "pipeline/content_linker.py::_link_inscription": _CONTENT_LINKS,
    "pipeline/content_linker.py::_link_map": _CONTENT_LINKS,
    "pipeline/content_linker.py::_link_model": _CONTENT_LINKS,
    "pipeline/content_linker.py::_link_text": _CONTENT_LINKS,
    # --- vocabulary aggregates, not sites -----------------------------------------------
    "api/routes/contributions.py::get_site_types": (
        "dropdown vocabulary over 1.76M rows for the contribution form"
    ),
    "api/routes/contributions.py::get_countries": (
        "autocomplete vocabulary over 1.76M rows for the contribution form"
    ),
    # --- other content that mentions a site ---------------------------------------------
    "api/routes/news.py::get_news_feed": (
        "stories are their own content; the join only filters stories by the type, "
        "country or period of the site they mention"
    ),
    "api/routes/news.py::get_news_filters": "filter vocabulary of the story feed",
    "api/routes/public_v1.py::get_news": "stories, labelled with the site they mention",
    "api/services/lyra_agent.py::_get_related_news": "stories, labelled with their site",
    "api/services/lyra_tools.py::search_news": "stories, labelled with their site",
    "api/services/lyra_prompts.py::_build_context_prompt": (
        "context of the page the user has open; a retired page answers 410 anyway"
    ),
    "api/routes/og.py::_thumbnail_url": (
        "share image for a URL someone already holds; the page itself answers 410"
    ),
    "pipeline/library_aggregator.py::_scan_news_items": (
        "period label of the site a story mentions; the story is its own content"
    ),
    # --- a player's own cards and history -----------------------------------------------
    "api/cardgame/achievements.py::_check_single": (
        "counts what the player liked, bookmarked or owns - their history, not a draw"
    ),
    "api/cardgame/leaderboard_service.py::fetch_collection_page": (
        "the player's own collection: cards they already own stay theirs, consistent with "
        "their decks and battles; only new draws skip a retired site"
    ),
    "api/cardgame/discord_commands.py::deck_command": "shows the player's own deck",
    "api/cardgame/discord_commands.py::_build_round_lines": "shows cards already in a battle",
    "api/cardgame/generator.py::_count_combos": _CARD_STATS,
    "api/cardgame/generator.py::backfill_placeholder_stats": _CARD_STATS,
    "api/cardgame/generator.py::generate_stats": _CARD_STATS,
}


@pytest.fixture(scope="module")
def scanned_read_paths() -> dict[str, bool]:
    return read_paths(REPO, SCANNED)


def test_every_read_path_filters_retired_sites_or_is_exempt_with_a_reason(scanned_read_paths):
    unclassified = sorted(
        k for k, filters in scanned_read_paths.items() if not filters and k not in EXEMPT
    )
    assert unclassified == [], (
        "these read unified_sites without the E4 scope filter (not_retired()/"
        "card_site_in_scope()) and are not in EXEMPT: " + ", ".join(unclassified)
    )


def test_no_exemption_is_stale(scanned_read_paths):
    paths = scanned_read_paths
    missing = sorted(k for k in EXEMPT if k not in paths)
    now_filtering = sorted(k for k in EXEMPT if paths.get(k))
    assert missing == [], f"EXEMPT names read paths that no longer exist: {missing}"
    assert now_filtering == [], f"EXEMPT names read paths that filter now: {now_filtering}"


def test_the_scan_covers_the_public_pipeline_consumers(scanned_read_paths):
    """The pipeline half of E4 (static export, IndexNow, library, graph, Qdrant, shorts) is
    under the ratchet too, not only api/."""
    for key in (
        "pipeline/static_exporter.py::_export_site_index",
        "pipeline/indexnow.py::<module>:_CHANGED_SITES_SQL",
        "pipeline/library_aggregator.py::_scan_sites",
        "pipeline/lyra/graph_full_ingest.py::_ingest_sites",
        "pipeline/lyra/graph_miner.py::mine_spatial_cooccurrence",
        "pipeline/lyra/research_graph.py::_pick_frontier",
        "pipeline/video/shorts_export.py::<module>:_LOOKUP_SQL",
        "scripts/build_lyra_index.py::index_sites",
    ):
        assert scanned_read_paths.get(key) is True, key


# --------------------------------------------------------------------------------------
# the scanner has teeth
# --------------------------------------------------------------------------------------

_TEETH = '''
from sqlalchemy import func, text

_SHOWN = "u.scope_status IS DISTINCT FROM 'retired'"
_BARE = text("SELECT id FROM unified_sites u")


def leaky(db):
    return db.execute(text("SELECT id FROM unified_sites")).fetchall()


def tight(db):
    return db.execute(text("SELECT id FROM unified_sites WHERE " + not_retired())).fetchall()


def tight_fstring(db):
    return db.execute(text(f"SELECT id FROM unified_sites u WHERE {not_retired('u')}"))


def tight_constant(db):
    return db.execute(text("SELECT id FROM unified_sites u WHERE " + _SHOWN))


def tight_built(db, country):
    clauses = ["u.country = :c"]
    clauses.append(not_retired("u"))
    where = " AND ".join(clauses)
    return db.execute(text(f"SELECT id FROM unified_sites u WHERE {where}"), {"c": country})


def _where():
    parts = ["u.lat IS NOT NULL", not_retired("u")]
    return " AND ".join(parts)


def tight_helper(db):
    return db.execute(text(f"SELECT id FROM unified_sites u WHERE {_where()}"))


def writer(db):
    db.execute(text("DELETE FROM unified_sites WHERE id = :i"))


def leaky_import(db):
    from pipeline.utils.public_sites import RETIRED, not_retired

    return db.execute(text("SELECT id FROM unified_sites")).fetchall()


def leaky_comment(db):
    """Filters with not_retired() - says the docstring, FROM unified_sites."""
    # scope_status: not_retired() is applied elsewhere
    return db.execute(text("SELECT id FROM unified_sites -- scope_status")).fetchall()


def leaky_two_queries(db):
    shown = db.execute(text("SELECT id FROM unified_sites WHERE " + not_retired())).fetchall()
    every = db.execute(text("SELECT id FROM unified_sites")).fetchall()
    return shown + every


def leaky_sibling_name(db):
    sql = "SELECT id FROM unified_sites"
    return db.execute(text(sql)).fetchall()


def orm_leaky(session):
    return session.query(UnifiedSite).all()


def orm_columns_leaky(session):
    return session.query(UnifiedSite.id, UnifiedSite.name).all()


def orm_count_leaky(session):
    return session.query(func.count(UnifiedSite.id)).scalar()


def orm_select_from_leaky(session):
    return session.query(func.count()).select_from(UnifiedSite).scalar()


def orm_outerjoin_leaky(session):
    return session.query(CardStats).outerjoin(UnifiedSite, CardStats.site_id == UnifiedSite.id)


def orm_tight(session):
    return session.query(UnifiedSite).filter(
        UnifiedSite.scope_status.is_distinct_from(RETIRED)).all()


def orm_tight_stepwise(session):
    q = session.query(UnifiedSite)
    q = q.filter(UnifiedSite.scope_status.is_distinct_from(RETIRED))
    return q.all()


def orm_tight_after_get(session, site_id):
    site = session.get(UnifiedSite, site_id)
    if site is None or site.scope_status == RETIRED:
        raise LookupError(site_id)
    return site


def factory():
    def route_a(db):
        where = not_retired("u")
        return db.execute(text(f"SELECT 1 FROM unified_sites u WHERE {where}"))

    def route_b(db, where):
        return db.execute(text(f"SELECT 1 FROM unified_sites u WHERE {where}"))

    return route_a, route_b


def outer(session, site):
    if site.scope_status == RETIRED:
        return None

    def inner_get(site_id):
        site = session.get(UnifiedSite, site_id)
        return site

    return inner_get


def shadowed(db, _where):
    return db.execute(text(f"SELECT 1 FROM unified_sites u WHERE {_where}"))


def for_each_row(db):
    for row in db.execute(text("SELECT id, scope_status FROM unified_sites")):
        yield row


def for_each_row_leaky(db):
    for row in db.execute(text("SELECT id FROM unified_sites")):
        if row.id:
            yield row
'''


def test_the_scanner_judges_each_read_on_its_own(tmp_path):
    """The ratchet has teeth: every leak the first version let through is reported now -
    an in-function import of RETIRED (the Discord /card case), a comment or docstring, a
    second unfiltered query next to a filtered one, and ORM reads through func.count,
    select_from and outerjoin - while the real ways to filter still count."""
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "teeth.py").write_text(_TEETH, encoding="utf-8")
    found = read_paths(tmp_path, [tmp_path / "api"])
    verdicts = {key.split("::", 1)[1]: filters for key, filters in found.items()}
    assert verdicts == {
        "<module>:_BARE": False,
        "leaky": False,
        "tight": True,
        "tight_fstring": True,
        "tight_constant": True,
        "tight_built": True,
        "tight_helper": True,
        "leaky_import": False,
        "leaky_comment": False,
        "leaky_two_queries": False,
        "leaky_sibling_name": False,
        "orm_leaky": False,
        "orm_columns_leaky": False,
        "orm_count_leaky": False,
        "orm_select_from_leaky": False,
        "orm_outerjoin_leaky": False,
        "orm_tight": True,
        "orm_tight_stepwise": True,
        "orm_tight_after_get": True,
        # route_b's `where` is a parameter: a sibling route's local of the same name
        # must not lend it a filter
        "route_a": True,
        "route_b": False,
        # the outer function's check of ITS `site` says nothing about inner_get's read
        "inner_get": False,
        # a parameter named like the scoped module function _where() is not that function
        "shadowed": False,
        "for_each_row": True,
        "for_each_row_leaky": False,
    }


def test_the_scanner_does_not_take_a_write_or_a_docstring_for_a_read():
    scan = ModuleScan(
        'def f(db):\n    """Reads FROM unified_sites."""\n'
        '    db.execute(text("DELETE FROM unified_sites WHERE id = :i"))\n'
    )
    assert list(scan.reads()) == []
