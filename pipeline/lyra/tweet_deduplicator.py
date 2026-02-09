"""Semantic similarity deduplication for news feed posts."""

import logging
import re

from pipeline.database import NewsItem, get_session
from pipeline.lyra.config import LyraSettings

logger = logging.getLogger(__name__)


def _extract_features(text: str) -> dict:
    """Extract comparison features from post text."""
    # Remove URLs and HTML comments
    clean = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    clean = re.sub(r"https?://\S+", "", clean)
    # Remove @mentions
    clean = re.sub(r"@\w+", "", clean)
    # Remove timestamps like "2:34'"
    clean = re.sub(r"\d+:\d+'?", "", clean)

    # Extract numbers (including those with commas)
    numbers = set(re.findall(r"\b[\d,]+\.?\d*\b", text))

    # Extract significant words (>3 chars, lowered)
    words = {w.lower() for w in re.findall(r"\b[a-zA-Z]{4,}\b", clean)}

    # Extract URLs
    urls = set(re.findall(r"https?://\S+", text))

    # Extract timestamps
    timestamps = set(re.findall(r"\d+:\d+'?", text))

    return {
        "numbers": numbers,
        "words": words,
        "urls": urls,
        "timestamps": timestamps,
    }


def _similarity(feat1: dict, feat2: dict) -> float:
    """Calculate similarity between two feature sets.

    Weighted: 40% numbers, 40% words, 20% metadata (URLs + timestamps).
    """
    # Number similarity
    all_nums = feat1["numbers"] | feat2["numbers"]
    shared_nums = feat1["numbers"] & feat2["numbers"]
    num_sim = len(shared_nums) / len(all_nums) if all_nums else 0.0

    # Word similarity
    all_words = feat1["words"] | feat2["words"]
    shared_words = feat1["words"] & feat2["words"]
    word_sim = len(shared_words) / len(all_words) if all_words else 0.0

    # Metadata match
    urls_match = 1.0 if feat1["urls"] == feat2["urls"] and feat1["urls"] else 0.0
    ts_match = 1.0 if feat1["timestamps"] == feat2["timestamps"] and feat1["timestamps"] else 0.0
    meta_sim = (urls_match + ts_match) / 2.0

    return 0.4 * num_sim + 0.4 * word_sim + 0.2 * meta_sim


def deduplicate_posts(settings: LyraSettings | None = None) -> int:
    """Soft-delete duplicate posts from the queue.

    Keeps newer posts, marks older duplicates by clearing post_text and
    setting news_category to "duplicate" for audit trail.
    Returns number of duplicates removed.
    """
    threshold = settings.dedup_similarity_threshold if settings else 0.25

    with get_session() as session:
        items = session.query(NewsItem).filter(
            NewsItem.post_text.isnot(None),
        ).order_by(NewsItem.id.desc()).limit(500).all()

        if len(items) < 2:
            return 0

        # Extract features for all items
        features = {item.id: _extract_features(item.post_text) for item in items}

        # Find duplicates (newer items take priority)
        to_clear: dict[int, tuple[int, float]] = {}  # older_id -> (kept_id, similarity)
        checked = []

        for item in items:
            if item.id in to_clear:
                continue

            for older_id in checked:
                if older_id in to_clear:
                    continue

                sim = _similarity(features[item.id], features[older_id])
                if sim > threshold:
                    to_clear[older_id] = (item.id, sim)

            checked.append(item.id)

        # Soft-delete: clear post_text and mark as duplicate
        if to_clear:
            for item in items:
                if item.id in to_clear:
                    kept_id, sim = to_clear[item.id]
                    logger.info(f"Dedup: soft-deleting item {item.id} (similar to {kept_id}, score={sim:.2f})")
                    item.post_text = None
                    item.news_category = "duplicate"

        logger.info(f"Deduplication: soft-deleted {len(to_clear)} duplicates from {len(items)} items")
        return len(to_clear)
