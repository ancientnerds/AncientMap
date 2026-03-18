"""Test transcript retrieval pipeline end-to-end.

Tests:
1. Can search_transcripts find relevant passages?
2. Do timestamps come back correctly?
3. Are YouTube URLs formatted properly for embedding?

Usage: python -m scripts.test_transcript_retrieval
"""

import json
import os
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set embedding backend to cloud (Voyage) for the transcripts collection
os.environ.setdefault("LYRA_EMBEDDING_BACKEND", "cloud")


def test_search_transcripts():
    """Test that search_transcripts returns results with correct structure."""
    from api.services.lyra_tools import search_transcripts

    print("=" * 60)
    print("TEST 1: Basic transcript search")
    print("=" * 60)

    result = search_transcripts.invoke({"query": "Atlantis", "limit": 3})
    print(result)
    print()

    # Validate structure
    assert "Found" in result, "Expected 'Found X transcript passages' header"
    assert "youtu.be/" in result, "Expected YouTube deep-link URL"
    assert "?t=" in result, "Expected timestamp parameter in URL"
    print("[PASS] Basic search returns results with timestamps and URLs\n")
    return result


def test_timestamp_search():
    """Test that searching for a specific topic returns relevant timestamps."""
    from api.services.lyra_tools import search_transcripts

    print("=" * 60)
    print("TEST 2: Specific topic -> timestamp retrieval")
    print("=" * 60)

    result = search_transcripts.invoke({"query": "submarine Bimini coast", "limit": 3})
    print(result)
    print()

    assert "Found" in result, "Expected results for submarine/Bimini query"
    print("[PASS] Specific topic search returns timestamped results\n")
    return result


def test_url_format():
    """Test that video URLs are correctly formatted for embedding."""
    from api.services.lyra_tools import search_transcripts

    print("=" * 60)
    print("TEST 3: URL format validation")
    print("=" * 60)

    result = search_transcripts.invoke({"query": "Atlantis", "limit": 1})

    import re

    # Extract URLs
    urls = re.findall(r"https://youtu\.be/[\w-]+\?t=\d+", result)
    print(f"URLs found: {urls}")

    assert len(urls) > 0, "Expected at least one YouTube URL"

    for url in urls:
        # Validate URL format: https://youtu.be/{video_id}?t={seconds}
        match = re.match(r"https://youtu\.be/([\w-]+)\?t=(\d+)", url)
        assert match, f"Invalid URL format: {url}"
        video_id = match.group(1)
        timestamp = int(match.group(2))
        print(f"  video_id={video_id}, timestamp={timestamp}s ({timestamp//60}:{timestamp%60:02d})")
        assert len(video_id) == 11, f"Expected 11-char video ID, got {len(video_id)}: {video_id}"
        assert timestamp >= 0, f"Negative timestamp: {timestamp}"

    print("[PASS] URLs correctly formatted\n")

    # Now check: does the thumbnail URL also work?
    thumb_urls = re.findall(r"https://img\.youtube\.com/vi/[\w-]+/mqdefault\.jpg", result)
    print(f"Thumbnail URLs: {thumb_urls}")
    assert len(thumb_urls) > 0, "Expected thumbnail URL"
    print("[PASS] Thumbnail URLs present\n")


def test_channel_filter():
    """Test filtering by channel name."""
    from api.services.lyra_tools import search_transcripts

    print("=" * 60)
    print("TEST 4: Channel filter")
    print("=" * 60)

    result = search_transcripts.invoke({
        "query": "Atlantis",
        "channel": "Nikkiana Jones",
        "limit": 3,
    })
    print(result)
    assert "Found" in result, "Expected results when filtering by existing channel"
    print("[PASS] Channel filter works\n")

    # Non-existent channel should return no results
    result2 = search_transcripts.invoke({
        "query": "Atlantis",
        "channel": "NonExistentChannel",
        "limit": 3,
    })
    print(f"Non-existent channel result: {result2}")
    assert "No transcript" in result2, "Expected no results for non-existent channel"
    print("[PASS] Non-existent channel correctly returns empty\n")


def test_empty_query():
    """Test edge case: empty query."""
    from api.services.lyra_tools import search_transcripts

    print("=" * 60)
    print("TEST 5: Edge cases")
    print("=" * 60)

    result = search_transcripts.invoke({"query": "", "limit": 3})
    print(f"Empty query: {result}")
    assert "No query" in result, "Expected error message for empty query"
    print("[PASS] Empty query handled\n")


if __name__ == "__main__":
    print("\nTranscript Retrieval Pipeline Test")
    print("=" * 60)
    print()

    try:
        test_search_transcripts()
        test_timestamp_search()
        test_url_format()
        test_channel_filter()
        test_empty_query()
        print("=" * 60)
        print("ALL TESTS PASSED")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n[FAIL] {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
