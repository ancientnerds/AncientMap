# SPDX-License-Identifier: AGPL-3.0-only
"""Every unified_sites read path in api/ either hides retired sites or says why not.

Owner decision E4 hides a retired site platform-wide (migration 0020). The plan names about
twenty consumers, and a missed one leaks a retired site (plan section 8.4 risk). A list in
a document goes stale the day someone adds a route; this test does not: it parses every
module under api/, finds each function (and module-level SQL constant) that READS
unified_sites - SQL ``FROM``/``JOIN unified_sites`` or an ORM query/join/get on
``UnifiedSite`` - and requires one of two things:

* the scope has visibly been handled: the function (or a module constant it uses) mentions
  ``scope_status``, ``not_retired``, ``is_retired``, ``RETIRED`` or ``card_site_in_scope``
  (a snapshot that copies the scope columns counts - it handles them on purpose);
* or the read path is in ``EXEMPT`` below, with the reason it must not filter.

A new read path without either fails here with its location. A stale exemption (the
function is gone, or it filters now) fails too, so the list cannot rot.

The per-consumer tests (tests/api/test_sites_scope.py and friends) check that the filter is
in the right WHERE with the right alias; this test checks that nobody forgot to ask.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
API = REPO / "api"

_READ_SQL = re.compile(r"(?<!DELETE )\b(?:FROM|JOIN)\s+unified_sites\b", re.IGNORECASE)
#: ORM calls that read the table: session.query(UnifiedSite ...), .join(UnifiedSite ...),
#: session.get(UnifiedSite, ...), select(UnifiedSite ...).
_ORM_READERS = frozenset({"query", "join", "get", "select"})
_SCOPE_TOKENS = ("scope_status", "not_retired", "is_retired", "RETIRED", "card_site_in_scope")

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
    # --- founder/editor tools: the whole table, retired rows included -----------------
    "api/routes/sites.py::batch_update_sites": "founder edit path (write)",
    "api/routes/sites.py::update_site": "founder edit path (write)",
    "api/routes/sites.py::_sync_to_radar": "copies a founder edit into the radar row (write)",
    "api/routes/sites.py::replace_source": (
        "founder bulk replace of one non-protected source; snapshots every row first"
    ),
    "api/services/snapshots.py::create_manual_snapshot": (
        "restore point of a whole source - it must hold the retired rows too"
    ),
    "api/services/snapshots.py::create_unified_snapshot": (
        "restore point of the curated set - it must hold the retired rows too"
    ),
    "api/routes/wiki_images.py::set_hero": "founder image tool: existence check",
    "api/routes/proposals.py::merge_proposal": "founder review: merge into an existing row",
    "api/routes/radar.py::merge_into_site": "founder review: merge into an existing row",
    # --- matching: a retired site must stay matchable, or it is proposed again ---------
    "api/routes/radar.py::_find_nearest_an_sites_batch": (
        "matches radar candidates against curated sites (same rule as site_matcher and "
        "prospector dedup: never filter matching)"
    ),
    "api/routes/contributions.py::get_lyra_stats": (
        "size of Lyra's matching knowledge base - retired rows are part of it"
    ),
    # --- vocabulary aggregates, not sites -----------------------------------------------
    "api/routes/contributions.py::get_site_types": (
        "dropdown vocabulary over 1.76M rows for the contribution form"
    ),
    "api/routes/contributions.py::get_countries": (
        "autocomplete vocabulary over 1.76M rows for the contribution form"
    ),
    "api/routes/public_v1.py::get_graph": (
        "research graph; its one read is an average longitude that orders country nodes"
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
    # --- a player's own cards and history -----------------------------------------------
    "api/cardgame/achievements.py::_check_single": (
        "counts what the player liked, bookmarked or owns - their history, not a draw"
    ),
    "api/cardgame/discord_commands.py::deck_command": "shows the player's own deck",
    "api/cardgame/discord_commands.py::_build_round_lines": "shows cards already in a battle",
    "api/cardgame/generator.py::_count_combos": (
        "card-stat computation, not a draw - every draw applies card_site_in_scope()"
    ),
    "api/cardgame/generator.py::backfill_placeholder_stats": "card-stat computation",
    "api/cardgame/generator.py::generate_stats": "card-stat computation",
}


def _functions(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]


def _innermost(funcs, node: ast.AST):
    best = None
    for f in funcs:
        if f.lineno <= node.lineno <= f.end_lineno and (best is None or f.lineno >= best.lineno):
            best = f
    return best


def _reads_sql(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and bool(_READ_SQL.search(node.value))
    )


def _reads_orm(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    if name not in _ORM_READERS:
        return False
    return any(_is_unified_site(arg) for arg in node.args)


def _is_unified_site(node: ast.AST) -> bool:
    """``UnifiedSite`` or one of its columns (``UnifiedSite.country``)."""
    if isinstance(node, ast.Attribute):
        node = node.value
    return isinstance(node, ast.Name) and node.id == "UnifiedSite"


def _mentions_scope(source: str, scoped_names: set[str]) -> bool:
    if any(token in source for token in _SCOPE_TOKENS):
        return True
    return any(re.search(rf"\b{re.escape(name)}\b", source) for name in scoped_names)


def _module_constants(tree: ast.Module, source: str) -> dict[str, str]:
    """Top-level NAME = <expr> assignments and their source text."""
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                out[target.id] = ast.get_source_segment(source, node) or ""
    return out


def read_paths() -> dict[str, bool]:
    """{key: filters} for every unified_sites read path in api/."""
    found: dict[str, bool] = {}
    for path in sorted(API.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "unified_sites" not in source and "UnifiedSite" not in source:
            continue
        tree = ast.parse(source)
        rel = path.relative_to(REPO).as_posix()
        constants = _module_constants(tree, source)
        # Constants that carry the scope filter, directly or through another constant.
        scoped: set[str] = set()
        changed = True
        while changed:
            changed = False
            for name, text in constants.items():
                if name not in scoped and _mentions_scope(text, scoped):
                    scoped.add(name)
                    changed = True
        funcs = _functions(tree)
        for node in ast.walk(tree):
            if not (_reads_sql(node) or _reads_orm(node)):
                continue
            func = _innermost(funcs, node)
            if func is None:
                const = next(
                    (
                        n
                        for n in tree.body
                        if isinstance(n, ast.Assign) and n.lineno <= node.lineno <= n.end_lineno
                    ),
                    None,
                )
                assert const is not None, f"{rel}:{node.lineno}: read outside any function"
                name = const.targets[0].id  # type: ignore[attr-defined]
                key = f"{rel}::<module>:{name}"
                filters = name in scoped
            else:
                key = f"{rel}::{func.name}"
                filters = _mentions_scope(ast.get_source_segment(source, func) or "", scoped)
            found[key] = found.get(key, True) and filters
    return found


@pytest.fixture(scope="module")
def api_read_paths() -> dict[str, bool]:
    return read_paths()


def test_every_read_path_filters_retired_sites_or_is_exempt_with_a_reason(api_read_paths):
    unclassified = sorted(
        k for k, filters in api_read_paths.items() if not filters and k not in EXEMPT
    )
    assert unclassified == [], (
        "these read unified_sites without the E4 scope filter (not_retired()/"
        "card_site_in_scope()) and are not in EXEMPT: " + ", ".join(unclassified)
    )


def test_no_exemption_is_stale(api_read_paths):
    paths = api_read_paths
    missing = sorted(k for k in EXEMPT if k not in paths)
    now_filtering = sorted(k for k in EXEMPT if paths.get(k))
    assert missing == [], f"EXEMPT names read paths that no longer exist: {missing}"
    assert now_filtering == [], f"EXEMPT names read paths that filter now: {now_filtering}"


def test_the_scanner_sees_a_read_path_without_the_filter(tmp_path, monkeypatch):
    """The ratchet has teeth: a new unfiltered read is reported, a filtered one is not."""
    pkg = tmp_path / "api"
    pkg.mkdir()
    (pkg / "leaky.py").write_text(
        "from sqlalchemy import text\n"
        "def leaky(db):\n"
        "    return db.execute(text('SELECT id FROM unified_sites')).fetchall()\n"
        "def tight(db):\n"
        "    return db.execute(text('SELECT id FROM unified_sites WHERE ' + not_retired()))\n"
        "def writer(db):\n"
        "    db.execute(text('DELETE FROM unified_sites WHERE id = :i'))\n"
        "def orm_leaky(session):\n"
        "    return session.query(UnifiedSite).all()\n"
        "def orm_columns_leaky(session):\n"
        "    return session.query(UnifiedSite.id, UnifiedSite.name).all()\n"
        "def orm_tight(session):\n"
        "    return session.query(UnifiedSite).filter(\n"
        "        UnifiedSite.scope_status.is_distinct_from(RETIRED)).all()\n",
        encoding="utf-8",
    )
    module = sys.modules[__name__]
    monkeypatch.setattr(module, "API", pkg)
    monkeypatch.setattr(module, "REPO", tmp_path)
    assert read_paths() == {
        "api/leaky.py::leaky": False,
        "api/leaky.py::tight": True,
        "api/leaky.py::orm_leaky": False,
        "api/leaky.py::orm_columns_leaky": False,
        "api/leaky.py::orm_tight": True,
    }
