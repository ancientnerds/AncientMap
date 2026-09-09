"""get_site_stats() is the one place that counts unified_sites; /api/stats and
the landing route both read it. DB-less: the session is a fake."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from api.services.site_stats import get_site_stats


class FakeResult:
    """scalar() for COUNT queries, iteration for the GROUP BY query."""

    def __init__(self, rows):
        self.rows = rows

    def scalar(self):
        return self.rows[0][0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class FakeSession:
    def __init__(self, results):
        self._results = list(results)

    def execute(self, *_args, **_kwargs):
        return FakeResult(self._results.pop(0))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_get_site_stats_counts_total_by_source_and_curated_countries():
    total = [(1_759_673,)]
    by_source = [
        SimpleNamespace(source_id="list_inscriptions", count=509_181),
        SimpleNamespace(source_id="ancient_nerds", count=5_004),
    ]
    countries = [(98,)]
    with (
        patch("api.services.site_stats.cache_get", return_value=None),
        patch("api.services.site_stats.cache_set") as cache_set,
        patch(
            "api.services.site_stats.get_session",
            return_value=FakeSession([total, by_source, countries]),
        ),
    ):
        stats = get_site_stats()

    assert stats == {
        "total_sites": 1_759_673,
        "by_source": {"list_inscriptions": 509_181, "ancient_nerds": 5_004},
        "curated_countries": 98,
    }
    assert cache_set.call_args.kwargs["ttl"] == 300


def test_get_site_stats_returns_the_cached_dict_untouched():
    with patch("api.services.site_stats.cache_get", return_value={"total_sites": 1}):
        assert get_site_stats() == {"total_sites": 1}
