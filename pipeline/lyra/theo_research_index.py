"""Qdrant indexing for published Theo research papers.

Splits papers by ## headings, embeds each section via Voyage AI,
and stores in the `theo_research_sections` Qdrant collection.

Used by:
  - Publish endpoint: index_paper() on publish
  - Unpublish/delete: delete_paper() on removal
  - Duplicate detection: search_similar() to find related papers
  - PublicResearchAdapter: search_sections() for citation retrieval
"""

from __future__ import annotations

import logging
import re
import uuid

logger = logging.getLogger(__name__)

COLLECTION_NAME = "theo_research_sections"
VECTOR_DIM = 1024  # voyage-4-large output dimension

# Sections to skip — not useful for semantic matching or citation
_SKIP_SECTIONS = frozenset(
    {
        "references",
        "methodology",
        "appendix: specialist debate summary",
    }
)


def _split_sections(paper_text: str) -> list[dict]:
    """Split paper markdown by ## headings into sections.

    Returns list of {title: str, text: str, index: int}.
    Skips References, Methodology, and Appendix sections.
    """
    sections: list[dict] = []
    current_title = ""
    current_lines: list[str] = []
    index = 0

    for line in paper_text.split("\n"):
        heading_match = re.match(r"^##\s+(.+)$", line)
        if heading_match:
            # Save previous section
            if current_title and current_lines:
                text = "\n".join(current_lines).strip()
                if text and current_title.lower() not in _SKIP_SECTIONS:
                    sections.append(
                        {
                            "title": current_title,
                            "text": text[:2000],  # truncate huge sections
                            "index": index,
                        }
                    )
                    index += 1
            current_title = heading_match.group(1).strip()
            current_lines = []
        elif line.startswith("# ") and not current_title:
            # Paper title — skip as section but could use as context
            continue
        else:
            current_lines.append(line)

    # Last section
    if current_title and current_lines:
        text = "\n".join(current_lines).strip()
        if text and current_title.lower() not in _SKIP_SECTIONS:
            sections.append(
                {
                    "title": current_title,
                    "text": text[:2000],
                    "index": index,
                }
            )

    return sections


def _deterministic_uuid(paper_id: str, section_index: int) -> str:
    """Generate a deterministic UUID from paper_id + section_index."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"theo:{paper_id}:{section_index}"))


def _ensure_collection() -> None:
    """Create the Qdrant collection if it doesn't exist."""
    from qdrant_client.models import Distance, VectorParams

    from api.services.lyra_embeddings import get_qdrant_client

    client = get_qdrant_client()
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection: %s", COLLECTION_NAME)


def index_paper(
    paper_id: str,
    paper_text: str,
    paper_title: str,
    paper_slug: str,
    author_username: str,
    author_discord_id: str,
    effort: str,
    published_at: str,
) -> int:
    """Split paper into sections, embed, and upsert to Qdrant.

    Returns the number of sections indexed.
    """
    from qdrant_client.models import PointStruct

    from api.services.lyra_embeddings import get_embeddings, get_qdrant_client

    sections = _split_sections(paper_text)
    if not sections:
        logger.warning("No sections found in paper %s", paper_id)
        return 0

    _ensure_collection()

    # Embed all sections in one batch
    embedder = get_embeddings("index")
    texts = [f"{s['title']}\n\n{s['text']}" for s in sections]
    vectors = embedder.embed_documents(texts)

    # Build Qdrant points
    points = []
    for section, vector in zip(sections, vectors, strict=True):
        point_id = _deterministic_uuid(paper_id, section["index"])
        points.append(
            PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "paper_id": paper_id,
                    "paper_title": paper_title,
                    "paper_slug": paper_slug,
                    "section_title": section["title"],
                    "section_text": section["text"],
                    "section_index": section["index"],
                    "author_username": author_username,
                    "author_discord_id": author_discord_id,
                    "effort": effort,
                    "published_at": published_at,
                },
            )
        )

    client = get_qdrant_client()
    client.upsert(collection_name=COLLECTION_NAME, points=points)
    logger.info("Indexed %d sections for paper %s (%s)", len(points), paper_id, paper_title)
    return len(points)


def delete_paper(paper_id: str) -> int:
    """Delete all Qdrant points for a paper. Returns count deleted."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    from api.services.lyra_embeddings import get_qdrant_client

    client = get_qdrant_client()

    # Check collection exists
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        return 0

    result = client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=Filter(
            must=[FieldCondition(key="paper_id", match=MatchValue(value=paper_id))]
        ),
    )
    logger.info("Deleted Qdrant points for paper %s: %s", paper_id, result)
    return 1  # qdrant delete doesn't return count, just success


def search_similar(question: str, limit: int = 5) -> list[dict]:
    """Search for public papers similar to a question.

    Returns list of {paper_id, paper_title, paper_slug, author_username,
    author_discord_id, effort, published_at, score, best_section_title}.
    Results are grouped by paper_id (best section score per paper).
    """
    from api.services.lyra_embeddings import get_embeddings, get_qdrant_client

    client = get_qdrant_client()

    # Check collection exists
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        return []

    embedder = get_embeddings("query")
    query_vector = embedder.embed_query(question)

    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        limit=limit * 3,  # oversample then deduplicate by paper
        score_threshold=0.3,
    )

    # Group by paper_id, keep best score per paper
    best_per_paper: dict[str, dict] = {}
    for hit in results:
        pid = hit.payload["paper_id"]
        if pid not in best_per_paper or hit.score > best_per_paper[pid]["score"]:
            best_per_paper[pid] = {
                "paper_id": pid,
                "paper_title": hit.payload["paper_title"],
                "paper_slug": hit.payload["paper_slug"],
                "author_username": hit.payload["author_username"],
                "author_discord_id": hit.payload["author_discord_id"],
                "effort": hit.payload["effort"],
                "published_at": hit.payload["published_at"],
                "score": round(hit.score, 3),
                "best_section_title": hit.payload["section_title"],
            }

    # Sort by score descending, return top N
    ranked = sorted(best_per_paper.values(), key=lambda x: x["score"], reverse=True)
    return ranked[:limit]


def search_sections(query: str, limit: int = 3) -> list[dict]:
    """Search for individual paper sections relevant to a query.

    Used by PublicResearchAdapter for citation retrieval.
    Returns list of {paper_id, paper_title, paper_slug, section_title,
    section_text, section_index, author_username, score}.
    Deduplicates by paper_id (keeps best section per paper).
    """
    from api.services.lyra_embeddings import get_embeddings, get_qdrant_client

    client = get_qdrant_client()

    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        return []

    embedder = get_embeddings("query")
    query_vector = embedder.embed_query(query)

    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        limit=limit * 3,
        score_threshold=0.35,
    )

    # Deduplicate by paper_id
    best_per_paper: dict[str, dict] = {}
    for hit in results:
        pid = hit.payload["paper_id"]
        if pid not in best_per_paper or hit.score > best_per_paper[pid]["score"]:
            best_per_paper[pid] = {
                "paper_id": pid,
                "paper_title": hit.payload["paper_title"],
                "paper_slug": hit.payload["paper_slug"],
                "section_title": hit.payload["section_title"],
                "section_text": hit.payload["section_text"],
                "section_index": hit.payload["section_index"],
                "author_username": hit.payload["author_username"],
                "score": round(hit.score, 3),
            }

    ranked = sorted(best_per_paper.values(), key=lambda x: x["score"], reverse=True)
    return ranked[:limit]
