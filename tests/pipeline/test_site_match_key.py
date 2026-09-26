"""The DB match key must be computed by Postgres, not by normalize_name().

`unified_sites.name_normalized` is maintained as `left(lower(unaccent(name)),
500)` (two UPDATEs in orchestrator.py's startup migrations). normalize_name()
produces something different for two whole classes of name, so comparing the
two silently loses matches. Measured on prod 2026-09-14: 124 of the 5,004
curated sites, ~1.6% of all 1.76M rows, ~2% of the alias table.

These tests pin the divergence itself. If someone later teaches
normalize_name() to fold ı and keep parentheses, these fail loudly and the
whole `_KEY_SQL` detour can be reconsidered on purpose rather than by accident.
"""

import inspect

from pipeline.lyra.site_matcher import _KEY_SQL, _find_site_by_name, _match_site_ids
from pipeline.utils.text import normalize_name


class TestTheDivergenceIsReal:
    def test_dotless_i_is_not_folded_by_normalize_name(self):
        # Postgres unaccent gives 'aysepinar'; NFKD leaves the dotless ı alone.
        assert normalize_name("Ayşepınar") != "aysepinar"
        assert "ı" in normalize_name("Ayşepınar")

    def test_slashed_o_is_not_folded_by_normalize_name(self):
        assert normalize_name("Bølareinen") != "bolareinen"

    def test_parenthesised_suffix_is_stripped_by_normalize_name(self):
        # The column keeps it: 'kemune (zahiku)'.
        assert normalize_name("Kemune (Zahiku)") == "kemune"
        assert normalize_name("Aké (Yucatan)") == "ake"

    def test_plain_names_agree(self):
        for name in ("Stonehenge", "Machu Picchu", "Chichen Itza"):
            assert normalize_name(name) == name.lower()


class TestKeyIsComputedInPostgres:
    def test_key_sql_matches_the_column_definition(self):
        assert _KEY_SQL == "left(lower(unaccent(:raw)), 500)"

    def test_lookup_binds_the_raw_name_not_a_python_key(self):
        src = inspect.getsource(_match_site_ids)
        assert '{"raw": extracted_name}' in src
        assert "normalize_name" not in src

    def test_both_name_columns_are_consulted(self):
        src = inspect.getsource(_match_site_ids)
        assert "unified_sites" in src
        assert "unified_site_names" in src

    def test_spaceless_variant_only_runs_on_a_miss(self):
        """`replace(name_normalized,' ','')` has no index — ~125 ms per call."""
        src = inspect.getsource(_match_site_ids)
        exact_pos = src.index("exact = session.execute")
        guard_pos = src.index("if exact:")
        spaceless_pos = src.index("spaceless = session.execute")
        assert exact_pos < guard_pos < spaceless_pos

    def test_caller_still_applies_the_blocklist_and_length_floor(self):
        src = inspect.getsource(_find_site_by_name)
        assert "_GENERIC_NAME_BLOCKLIST" in src
        assert "len(normalized) < 3" in src

    def test_caller_filters_by_matchable_source(self):
        src = inspect.getsource(_find_site_by_name)
        assert "UnifiedSite.source_id.in_(matchable_sources)" in src


class TestTheCuratedNameMatchKeysInPostgres:
    """Audit 2026-09-25 M10 (read-only part): `site_identifier._check_name_an_match` compared
    `normalize_name()` with `name_normalized` - the Python key the module docstring above rules
    out. It asks `_match_site_ids` with the raw name and keeps the curated rows."""

    def test_the_raw_name_goes_to_the_postgres_key(self, monkeypatch):
        from unittest.mock import MagicMock

        from pipeline.lyra import site_identifier as SI

        asked: list[str] = []
        monkeypatch.setattr(SI, "_match_site_ids", lambda session, name: asked.append(name) or {1})
        session = MagicMock()
        found = SI._check_name_an_match(session, "Ayşepınar")
        assert asked == ["Ayşepınar"]
        assert found is session.query.return_value.filter.return_value.order_by.return_value.first()

    def test_no_python_key_is_compared_with_the_column(self):
        from pipeline.lyra import site_identifier as SI

        src = inspect.getsource(SI._check_name_an_match)
        assert ".name_normalized" not in src and "UnifiedSiteName" not in src
        assert '== "ancient_nerds"' in src

    def test_no_match_is_no_query(self, monkeypatch):
        from unittest.mock import MagicMock

        from pipeline.lyra import site_identifier as SI

        monkeypatch.setattr(SI, "_match_site_ids", lambda session, name: set())
        session = MagicMock()
        assert SI._check_name_an_match(session, "Stonehenge") is None
        session.query.assert_not_called()
