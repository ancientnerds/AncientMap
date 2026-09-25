# SPDX-License-Identifier: AGPL-3.0-only
"""E4 (migration 0020) in Lyra's semantic search: a retired site never comes back from Qdrant.

The Qdrant ``sites`` collection is a cache of unified_sites. scripts/build_lyra_index.py deletes
a retired site's point, but only when it runs (nightly at 03:00 UTC, api/routes/vector_sync.py),
so a site retired during the day stays in the index until then. Measured on production
2026-09-25, hours after the scope-e4 apply: all 78 retired sites were still points of ``sites``,
and ``_hybrid_search`` returned Qdrant payloads as they were - the ``vector_search`` tool and
the chat's auto-retrieve (api/services/lyra_agent.py) handed Lyra sites whose page answers 410.
The database decides what is shown; the search drops what it says is retired, whatever the
index still holds.

DB-less: Qdrant, Voyage and the BM25 model are stand-ins; the scope read is a RecordingSession.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pipeline.utils.public_sites import is_retired
from tests.fake_sql import RecordingSession

SHOWN_ID = "11111111-1111-4111-8111-111111111111"
RETIRED_ID = "22222222-2222-4222-8222-222222222222"
OTHER_ID = "33333333-3333-4333-8333-333333333333"


class _ctx:
    """get_session() stand-in: a context manager yielding the given fake session."""

    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *exc):
        return False


class _Vector:
    def __init__(self, values):
        self._values = list(values)

    def tolist(self):
        return list(self._values)


class _Sparse:
    def embed(self, texts):
        return [SimpleNamespace(indices=_Vector([1, 2]), values=_Vector([0.5, 0.5])) for _ in texts]


class _Embeddings:
    last_total_tokens = 0

    def embed_query(self, _query):
        return [0.1, 0.2, 0.3]


class _Qdrant:
    def __init__(self, points):
        self.points = points
        self.calls = 0

    def query_points(self, **_kwargs):
        self.calls += 1
        return SimpleNamespace(points=list(self.points))


class _Reranker:
    """Scores every document it is given, in order; records what it saw."""

    def __init__(self):
        self.docs: list[str] = []

    def rerank(self, _query, docs, model, top_k):
        self.docs = list(docs)
        return SimpleNamespace(
            results=[
                SimpleNamespace(index=i, relevance_score=1.0 - i / 10)
                for i in range(min(top_k, len(docs)))
            ],
            total_tokens=0,
        )


def _point(point_id: str, name: str):
    return SimpleNamespace(id=point_id, payload={"name": name, "description": f"{name} text"})


def _search(collection: str, points, session: RecordingSession):
    from api.services import lyra_embeddings, lyra_tools

    reranker = _Reranker()
    with (
        patch.object(lyra_embeddings, "get_qdrant_client", return_value=_Qdrant(points)),
        patch.object(lyra_embeddings, "get_embeddings", return_value=_Embeddings()),
        patch.object(lyra_embeddings, "get_sparse_model", return_value=_Sparse()),
        patch.object(lyra_embeddings, "get_reranker", return_value=reranker),
        patch.object(lyra_tools, "get_session", return_value=_ctx(session)),
    ):
        items, _tokens = lyra_tools._hybrid_search_inner(
            "stone fort", collection, 5, None, None, None, None
        )
    return items, reranker


def test_a_retired_site_is_dropped_before_the_rerank():
    session = RecordingSession({"FROM unified_sites": [(RETIRED_ID,)]})
    points = [_point(SHOWN_ID, "Shown Fort"), _point(RETIRED_ID, "Retired Fort")]
    items, reranker = _search("sites", points, session)
    assert [item["id"] for item in items] == [SHOWN_ID]
    assert all("Retired Fort" not in doc for doc in reranker.docs)
    (sql,) = session.statements()
    assert is_retired() in sql
    assert sorted(session.log[0][1]["ids"]) == sorted([SHOWN_ID, RETIRED_ID])


def test_nothing_retired_keeps_every_point_in_order():
    session = RecordingSession()
    points = [_point(SHOWN_ID, "Shown Fort"), _point(OTHER_ID, "Other Fort")]
    items, _ = _search("sites", points, session)
    assert [item["id"] for item in items] == [SHOWN_ID, OTHER_ID]


def test_only_retired_points_is_an_empty_result():
    session = RecordingSession({"FROM unified_sites": [(RETIRED_ID,)]})
    items, reranker = _search("sites", [_point(RETIRED_ID, "Retired Fort")], session)
    assert items == []
    assert reranker.docs == []


@pytest.mark.parametrize("collection", ["news", "empires"])
def test_other_collections_are_not_site_points(collection):
    """Their point ids are not site ids: no scope read, nothing dropped. (transcripts, articles
    and research pass through the same branch; their chunk compression needs text this stand-in
    does not carry.)"""
    session = RecordingSession({"FROM unified_sites": [(RETIRED_ID,)]})
    points = [_point(SHOWN_ID, "A"), _point(RETIRED_ID, "B")]
    items, _ = _search(collection, points, session)
    assert session.statements() == []
    assert [item["id"] for item in items] == [SHOWN_ID, RETIRED_ID]
