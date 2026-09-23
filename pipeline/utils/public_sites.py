# SPDX-License-Identifier: AGPL-3.0-only
"""Which sites the platform shows, and when a site's public page last changed.

Scope (owner decision E4, plan docs/procedures/SITES_DB_REMEDIATION_2026-09.md 8.4):
a site outside the project's time window is flagged AND hidden platform-wide.
Migration 0020 adds ``unified_sites.scope_status`` for it:

    NULL       - never assessed. Counts as in scope: no backfill, nothing disappears.
    in_scope   - assessed and kept.
    pending    - assessment open. Still shown until someone decides.
    retired    - assessed and hidden everywhere a visitor, a crawler or a card draw
                 can reach it. The row stays (E1: no DELETE), so matching and
                 dedup still see it and never propose the site again.

``not_retired()`` is the one spelling of "shown" every public read path uses. It is
``IS DISTINCT FROM`` on purpose: ``scope_status <> 'retired'`` is NULL, not true, for
the NULL rows - i.e. for every site nobody has assessed - and would hide all of
them. tests/pipeline/test_public_sites.py evaluates the predicate in a real SQL
engine so that trap cannot come back.

Deliberately NOT filtered (a retired site must stay matchable, or it is proposed
again): pipeline/lyra/site_matcher.py and pipeline/lyra/prospector/dedup.py.

``last_change()`` is the journal-aware "last modified" of a site's public page. The
remediation writes through ``apply_remediation_change()`` (migration 0017), which does
not touch ``updated_at`` - 0 of 984 corrected sites carried a newer timestamp on
2026-09-22, so neither the sitemap lastmod nor IndexNow ever announced them. The
journal's ``applied_at`` is the timestamp of those writes; the page changed at the
later of the two.
"""

from __future__ import annotations

import re

#: The scope vocabulary migration 0020 enforces with a CHECK constraint.
SCOPE_STATUSES = ("in_scope", "retired", "pending")

#: The one status that hides a site.
RETIRED = "retired"

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _column(alias: str, column: str) -> str:
    if not alias:
        return column
    if not _IDENTIFIER.fullmatch(alias):
        # Callers pass literal table aliases; anything else is a programming error that
        # must not be spliced into SQL.
        raise ValueError(f"not an SQL alias: {alias!r}")
    return f"{alias}.{column}"


def not_retired(alias: str = "") -> str:
    """SQL predicate: the row is shown (``scope_status`` is not 'retired', NULL included).

    ``alias`` is the table alias of ``unified_sites`` in the calling query, or empty for
    an unaliased single-table query.
    """
    return f"{_column(alias, 'scope_status')} IS DISTINCT FROM '{RETIRED}'"


def is_retired(alias: str = "") -> str:
    """SQL predicate: the row is retired. For the paths that answer 410 or delete."""
    return f"{_column(alias, 'scope_status')} = '{RETIRED}'"


def curated_page(alias: str = "") -> str:
    """SQL predicate: the row has a crawlable page at /sites/{country}/{slug}.

    An Ancient Nerds Original with a country, not retired. The SSR routes serve exactly
    these pages, so the sitemap, IndexNow, the country hubs and the homepage hub list must
    use exactly this rule - a mismatch advertises URLs that answer 404/410 or never
    announces pages that exist.
    """
    country = _column(alias, "country")
    return (
        f"{_column(alias, 'source_id')} = 'ancient_nerds' "
        f"AND {country} IS NOT NULL AND {country} != '' AND {not_retired(alias)}"
    )


#: The columns the site's public page reads, per table: a journalled write of one of them
#: changes the page (the SSR detail route api/routes/sites_html.py, rendered by
#: src/pages/SitePage.tsx; tests/api/test_sitemap_lastmod.py derives the same lists from
#: the route's own queries).
#:
#: - ``unified_sites``: the Phase-4/5 design (entry [6], production_write, COLUMNS) names
#:   description, raw_data, name, country, site_type and period_start; period_name,
#:   period_end, lat, lon, source_url and parent_site_id are rendered on the same page,
#:   and later lanes journal some of them (period_name: 220 rows, lat/lon: 9, read
#:   2026-09-23).
#: - ``card_stats``: only the page's Wikipedia link and its language. The card itself
#:   never appears on the page, and the ~4,300 P5 card writes would otherwise move the
#:   lastmod and the hourly IndexNow announcement of pages whose content did not change.
#: - ``wiki_images`` (orchestrator decision D6, 2026-09-23): the page shows one image - the
#:   hero, else the lead, else the first by sort order, never an excluded one - so a write
#:   of a column that chooses it (a hero change) or of one it renders of it (file, author,
#:   licence, Commons link, size) changes the page. The image lanes journal is_hero,
#:   is_excluded, filename, author, commons_page_url, width and height
#:   (gallery_audit/chunk_writer.WRITABLE). A rendered column counts for every image of
#:   the site, not only the one shown - the journal does not say which image the page
#:   showed at the time, and announcing a page whose gallery changed behind its hero is
#:   the cheaper error than missing a hero change.
#:
#: Not counted: any column the page does not show (``geom``, which the coordinate lane
#: writes beside lat/lon; ``thumbnail_url``, the country hub's fallback for a site with
#: no downloaded hero; the image lanes' image_kind, author_url, original_url and
#: file_size_bytes; the card game's stats).
PAGE_COLUMNS: dict[str, tuple[str, ...]] = {
    "unified_sites": (
        "description",
        "raw_data",
        "name",
        "country",
        "site_type",
        "period_start",
        "period_end",
        "period_name",
        "lat",
        "lon",
        "source_url",
        "parent_site_id",
    ),
    "card_stats": ("best_wiki_url", "source_language"),
    "wiki_images": (
        "is_hero",
        "is_excluded",
        "is_lead",
        "sort_order",
        "filename",
        "author",
        "license",
        "commons_page_url",
        "width",
        "height",
    ),
}


def _page_write(table: str, columns: tuple[str, ...]) -> str:
    listed = ", ".join("'" + column + "'" for column in columns)
    return f"(table_name = '{table}' AND column_name IN ({listed}))"


_PAGE_WRITE = " OR ".join(_page_write(table, columns) for table, columns in PAGE_COLUMNS.items())

#: LEFT JOIN target: the newest journal write per site that changed its page. Joined as
#: ``jlast``; the grouped subquery reads the journal once (6,572 rows on 2026-09-22)
#: instead of one lookup per site.
JOURNAL_LAST_WRITE = (
    "(SELECT site_id_ref, MAX(applied_at AT TIME ZONE 'UTC') AS applied_at "
    "FROM remediation_change_log WHERE site_id_ref IS NOT NULL "
    f"AND ({_PAGE_WRITE}) "
    "GROUP BY site_id_ref)"
)


def journal_join(alias: str) -> str:
    """``LEFT JOIN`` clause that makes ``jlast.applied_at`` available for ``alias``."""
    return f"LEFT JOIN {JOURNAL_LAST_WRITE} jlast ON jlast.site_id_ref = {_column(alias, 'id')}"


def last_change(alias: str = "") -> str:
    """SQL expression: when the site's page last changed. Needs ``journal_join(alias)``.

    ``GREATEST`` ignores NULLs, so a site without a journal row keeps its own
    timestamp. ``applied_at`` is timestamptz and ``updated_at`` is a naive UTC
    timestamp (the database runs in Etc/UTC); the join converts the journal side to
    naive UTC so the result stays comparable with the naive datetimes the sitemap
    compares it to.
    """
    own = f"COALESCE({_column(alias, 'updated_at')}, {_column(alias, 'created_at')})"
    return f"GREATEST({own}, jlast.applied_at)"
