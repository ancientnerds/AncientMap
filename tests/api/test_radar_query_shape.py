# SPDX-License-Identifier: AGPL-3.0-only
"""Structural tests for the radar list/item SQL (no DB needed).

These guard three defects found in the 2026-09-14 audit:

1. `news_category` and `hide_speculative` were predicates in the HAVING of the
   `video_agg` CTE, which is LEFT JOINed. A CTE-internal HAVING cannot drop a
   row from the left side of a LEFT JOIN, so both filters were no-ops on the
   row count (prod returned total_count 553 for every category) while silently
   stripping the evidence fields off every non-matching card.
2. The evidence join keyed on `c.name` alone, but the pipeline keys
   contributions on the corrected name, so 25 cards showed no videos, facts,
   screenshot or last_mentioned even though their news items existed.
3. The score was written out five times and the copies had drifted.
"""

import re

from api.routes.radar import (
    _STATUS_CLAUSES,
    _VISIBLE_CLAUSE,
    _build_radar_query,
    _score_sql,
)

LIST_SQL = _build_radar_query(_STATUS_CLAUSES["enriched"], "c.id")
ITEM_SQL = _build_radar_query(_VISIBLE_CLAUSE, "c.id", single_id=True)


def _strip_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def _outer_where(sql: str) -> str:
    """The WHERE that applies to the final SELECT, after the CTEs."""
    tail = sql.rsplit("LEFT JOIN video_agg", 1)[1]
    return tail.split("ORDER BY")[0]


class TestFiltersActuallyFilter:
    def test_video_agg_cte_has_no_having(self):
        cte = LIST_SQL.split("video_agg AS (")[1].split("SELECT\n            COUNT(*) OVER()")[0]
        assert "HAVING" not in _strip_comments(cte).upper()

    def test_category_and_speculative_are_outer_predicates(self):
        where = _outer_where(LIST_SQL)
        assert ":news_category" in where
        assert ":hide_speculative" in where

    def test_hide_speculative_keeps_cards_with_no_evidence(self):
        """A card with no news items is not speculative — COALESCE, not NULL."""
        where = _outer_where(LIST_SQL)
        assert "COALESCE(va.is_speculative, false) = false" in where


class TestEvidenceJoin:
    def test_join_matches_both_the_raw_and_the_corrected_name(self):
        join = LIST_SQL.split("JOIN news_items ni ON")[1].split("JOIN news_videos")[0]
        assert "c.name" in join
        assert "c.corrected_name" in join

    def test_evidence_is_left_joined_so_a_card_without_videos_survives(self):
        assert "LEFT JOIN video_agg va" in LIST_SQL


class TestSingleScoreSource:
    def test_score_sql_is_parameterised_by_alias(self):
        assert "uc.lat" in _score_sql("uc")
        assert "c.lat" in _score_sql("c")

    def test_list_query_uses_the_shared_score(self):
        assert _score_sql("uc") in LIST_SQL

    def test_score_weights_sum_to_100(self):
        points = [int(n) for n in re.findall(r"THEN (\d+) ELSE 0 END", _score_sql("uc"))]
        assert 25 + sum(points) == 100


class TestItemQuery:
    def test_item_query_filters_by_id_and_does_not_paginate(self):
        assert "uc.id = CAST(:contribution_id AS uuid)" in ITEM_SQL
        assert "LIMIT :limit" not in ITEM_SQL

    def test_list_query_paginates_and_has_no_id_filter(self):
        assert "LIMIT :limit OFFSET :offset" in LIST_SQL
        assert ":contribution_id" not in LIST_SQL

    def test_both_queries_select_the_same_columns(self):
        """A dot on the map must render the same card shape as the list."""

        def cols(sql):
            head = sql.split("SELECT\n            COUNT(*) OVER()")[1]
            return re.findall(r"^\s+(?:c|va)\.(\w+)", head.split("FROM contrib c")[0], re.M)

        assert cols(LIST_SQL) == cols(ITEM_SQL)


class TestStatusClauses:
    def test_every_exposed_status_has_a_clause(self):
        # Must stay in sync with the `status` Query pattern on GET /radar/list.
        assert set(_STATUS_CLAUSES) == {"all", "enriched", "added", "rejected"}

    def test_all_hides_resolved_and_non_site_rows(self):
        for hidden in ("failed", "not_a_site", "matched"):
            assert hidden in _STATUS_CLAUSES["all"]

    def test_no_pending_status_is_offered(self):
        """Nothing ever holds 'pending' — match and identify run in one cycle."""
        assert "pending" not in _STATUS_CLAUSES
