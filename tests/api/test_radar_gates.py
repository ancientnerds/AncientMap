# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for radar promotion gate helpers (pure functions, no DB)."""

from api.routes.radar import _apply_overrides, _missing_core_fields

COMPLETE_ITEM = {
    "lat": 37.2231,
    "lon": 38.9225,
    "country": "Turkey",
    "site_type": "settlement",
    "description": "A pre-pottery neolithic settlement with carved orthostats and communal buildings.",
}


class TestMissingCoreFields:
    def test_complete_item_has_no_missing_fields(self):
        assert _missing_core_fields(COMPLETE_ITEM) == []

    def test_missing_coordinates(self):
        item = {**COMPLETE_ITEM, "lat": None}
        assert _missing_core_fields(item) == ["coordinates"]
        item = {**COMPLETE_ITEM, "lon": None}
        assert _missing_core_fields(item) == ["coordinates"]

    def test_missing_country(self):
        assert _missing_core_fields({**COMPLETE_ITEM, "country": None}) == ["country"]
        assert _missing_core_fields({**COMPLETE_ITEM, "country": ""}) == ["country"]

    def test_missing_site_type(self):
        assert _missing_core_fields({**COMPLETE_ITEM, "site_type": None}) == ["site_type"]

    def test_short_description(self):
        assert _missing_core_fields({**COMPLETE_ITEM, "description": "Too short."}) == [
            "description"
        ]
        assert _missing_core_fields({**COMPLETE_ITEM, "description": None}) == ["description"]

    def test_all_missing(self):
        assert _missing_core_fields({}) == ["coordinates", "country", "site_type", "description"]

    def test_wikipedia_thumbnail_qid_not_required(self):
        # The old 100%-score gate required these — the new gate must not.
        item = {**COMPLETE_ITEM, "wikipedia_url": None, "thumbnail_url": None, "wikidata_id": None}
        assert _missing_core_fields(item) == []


class TestApplyOverrides:
    def test_override_fills_missing_field(self):
        item = {**COMPLETE_ITEM, "country": None}
        merged = _apply_overrides(item, {"country": "Turkey"})
        assert merged["country"] == "Turkey"
        assert _missing_core_fields(merged) == []

    def test_override_replaces_existing_field(self):
        merged = _apply_overrides(COMPLETE_ITEM, {"lat": 40.0, "lon": 41.0})
        assert merged["lat"] == 40.0
        assert merged["lon"] == 41.0

    def test_none_values_in_overrides_are_ignored(self):
        merged = _apply_overrides(COMPLETE_ITEM, {"country": None, "lat": None})
        assert merged["country"] == "Turkey"
        assert merged["lat"] == 37.2231

    def test_original_dict_not_mutated(self):
        item = {**COMPLETE_ITEM}
        _apply_overrides(item, {"country": "Syria"})
        assert item["country"] == "Turkey"
