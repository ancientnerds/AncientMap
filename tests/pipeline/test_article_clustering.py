"""The clustering step must survive a malformed group from the model.

On 2026-10-05 the weekly journal died three times with

    File "pipeline/lyra/article_generator.py", line 225, in _cluster_related_items
        for i in cluster:
    TypeError: 'int' object is not iterable

The strict JSON schema says a group is a list of item indices, but the call is
stochastic and returned a bare index where a group belongs. A journal run is
worth hours of quota; one malformed group must cost that group, not the week.
"""

from types import SimpleNamespace

import pytest

from pipeline.lyra import article_generator as ag


def _items(n: int = 4) -> list[dict]:
    return [
        {
            "id": f"n{i}",
            "headline": f"Headline {i}",
            "summary": f"Summary {i}",
            "site_name": f"Site {i}",
            "news_category": "excavation",
            "significance": 3,
        }
        for i in range(n)
    ]


def _patch_clustering(monkeypatch, payload: dict) -> None:
    monkeypatch.setattr(ag, "call_api", lambda *a, **k: SimpleNamespace(text="{}"))
    monkeypatch.setattr(ag, "parse_json_response", lambda text: payload)


def _fake_settings() -> ag.LyraSettings:
    return ag.LyraSettings(minimax_api_key="k", model_cluster="m")


class TestClusterShapeValidation:
    def test_a_bare_index_instead_of_a_group_is_skipped(self, monkeypatch):
        # The exact shape the model returned on 2026-10-05.
        _patch_clustering(monkeypatch, {"clusters": [3, [0, 1]], "reasoning": "two groups"})

        result = ag._cluster_related_items(_items(), _fake_settings())

        # 0+1 merged into one winner, the bare 3 ignored, 2 kept as it is.
        assert sorted(item["id"] for item in result) == ["n0", "n2", "n3"]

    def test_a_string_group_is_skipped(self, monkeypatch):
        _patch_clustering(monkeypatch, {"clusters": ["0,1", [2, 3]], "reasoning": "r"})

        result = ag._cluster_related_items(_items(), _fake_settings())

        # "0,1" is not a group; [2, 3] merges, so three items remain.
        assert sorted(item["id"] for item in result) == ["n0", "n1", "n2"]

    def test_nothing_fusible_leaves_the_items_alone(self, monkeypatch):
        _patch_clustering(monkeypatch, {"clusters": [1, 2, 3], "reasoning": "r"})

        result = ag._cluster_related_items(_items(), _fake_settings())

        assert sorted(item["id"] for item in result) == ["n0", "n1", "n2", "n3"]

    def test_clusters_that_is_not_a_list_keeps_the_items(self, monkeypatch):
        _patch_clustering(monkeypatch, {"clusters": {"a": [0, 1]}, "reasoning": "r"})

        result = ag._cluster_related_items(_items(), _fake_settings())

        assert sorted(item["id"] for item in result) == ["n0", "n1", "n2", "n3"]

    def test_well_formed_groups_still_merge(self, monkeypatch):
        _patch_clustering(monkeypatch, {"clusters": [[0, 1], [2, 3]], "reasoning": "r"})

        result = ag._cluster_related_items(_items(), _fake_settings())

        assert len(result) == 2

    def test_a_malformed_group_is_not_silent(self, monkeypatch, caplog):
        _patch_clustering(monkeypatch, {"clusters": [3, [0, 1]], "reasoning": "two groups"})

        with caplog.at_level("WARNING"):
            ag._cluster_related_items(_items(), _fake_settings())

        assert any("where a group belongs" in record.message for record in caplog.records)
