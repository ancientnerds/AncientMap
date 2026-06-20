"""Unit tests for pipeline.lyra.theo_research_index.search_sections.

Regression coverage for the KeyError('section_text') that took the
`ancientnerds_research` (PublicResearch) adapter fully offline: every
published-paper point in the prod Qdrant `research` collection carries
`text_preview` but NOT `section_text` (older payload schema), so reading
`hit.payload["section_text"]` raised on every query.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pipeline.lyra.theo_research_index import COLLECTION_NAME, search_sections

# A point shaped exactly like the live prod payload: text_preview present,
# section_text absent (confirmed via Qdrant scroll on 2026-06-19).
_PROD_PAYLOAD = {
    "paper_id": "p1",
    "paper_title": "Induced EMF in Ancient Technology",
    "paper_slug": "induced-emf",
    "section_title": "The Baghdad Battery",
    "text_preview": "A clay jar with a copper cylinder and iron rod, " * 10,
    "section_index": 0,
    "author_username": "lyra",
    "title": "Induced EMF — The Baghdad Battery",
}


def _mock_clients(payload: dict):
    """Build (get_qdrant_client, get_embeddings) mocks returning one hit."""
    hit = SimpleNamespace(payload=payload, score=0.91)
    client = MagicMock()
    client.get_collections.return_value.collections = [SimpleNamespace(name=COLLECTION_NAME)]
    client.query_points.return_value.points = [hit]
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.0] * 8
    return client, embedder


def test_search_sections_handles_payload_without_section_text():
    """The prod schema lacks section_text — search_sections must not raise."""
    client, embedder = _mock_clients(_PROD_PAYLOAD)
    with (
        patch("api.services.lyra_embeddings.get_qdrant_client", return_value=client),
        patch("api.services.lyra_embeddings.get_embeddings", return_value=embedder),
    ):
        results = search_sections("baghdad battery", limit=3)

    assert len(results) == 1
    row = results[0]
    # The snippet the adapter slices [:500] from now comes from text_preview.
    assert row["section_text"] == _PROD_PAYLOAD["text_preview"]
    assert row["section_title"] == "The Baghdad Battery"
    assert row["paper_slug"] == "induced-emf"


def test_search_sections_empty_when_collection_missing():
    """No `research` collection → empty list, no crash."""
    client, embedder = _mock_clients(_PROD_PAYLOAD)
    client.get_collections.return_value.collections = []  # collection absent
    with (
        patch("api.services.lyra_embeddings.get_qdrant_client", return_value=client),
        patch("api.services.lyra_embeddings.get_embeddings", return_value=embedder),
    ):
        assert search_sections("anything") == []
