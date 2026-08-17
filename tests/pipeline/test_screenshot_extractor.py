# SPDX-License-Identifier: AGPL-3.0-only
"""Pure-logic tests for the screenshot extractor (no network, no DB).

Covers the /data/ URL migration (2026-08-17) and the hi-res backfill
decisions: filename parsing, gone-video detection, the replace-only-when-
wider rule and the PIL width probe that drives backfill resumability.
"""

from __future__ import annotations

from pathlib import Path

from pipeline.lyra.screenshot_extractor import (
    MIN_HIRES_WIDTH,
    YTDLP_FORMAT,
    _image_width,
    is_video_gone,
    parse_screenshot_filename,
    screenshot_url_for,
    should_replace,
)


def test_screenshot_url_uses_the_data_prefix() -> None:
    """New URLs bypass /api/ — nginx serves /data/news/ directly and
    robots.txt disallows /api/ (Google Discover needs crawlable images)."""
    assert (
        screenshot_url_for("dQw4w9WgXcQ_123.webp") == "/data/news/screenshots/dQw4w9WgXcQ_123.webp"
    )


def test_parse_filename_roundtrip() -> None:
    url = screenshot_url_for("dQw4w9WgXcQ_123.webp")
    assert parse_screenshot_filename(url) == ("dQw4w9WgXcQ", 123)


def test_parse_filename_accepts_legacy_api_urls() -> None:
    """Pre-migration DB rows still carry the /api/ prefix until the SQL
    backfill runs — the hi-res backfill must handle both."""
    assert parse_screenshot_filename("/api/news/screenshots/_5_bp8maWa8_3316.webp") == (
        "_5_bp8maWa8",
        3316,
    )


def test_parse_filename_rejects_malformed_names() -> None:
    assert parse_screenshot_filename("no-timestamp.webp") is None
    assert parse_screenshot_filename("shortid_12.webp") is None  # video_id != 11 chars
    assert parse_screenshot_filename("dQw4w9WgXcQ_123.jpg") is None
    assert parse_screenshot_filename("") is None


def test_ytdlp_format_targets_720p() -> None:
    """854×480 frames are below Google Discover's >=1200px requirement;
    720p (1280×720) clears it. Pin the format so a refactor can't silently
    drop back to 480p."""
    assert YTDLP_FORMAT == "bestvideo[height<=720]/best[height<=720]/best"
    assert MIN_HIRES_WIDTH == 1200


def test_gone_video_detection() -> None:
    assert is_video_gone("ERROR: [youtube] abc12345678: Video unavailable")
    assert is_video_gone(
        "ERROR: [youtube] abc12345678: Private video. "
        "Sign in if you've been granted access to this video"
    )
    assert is_video_gone("This video has been removed by the uploader")
    assert not is_video_gone("HTTP Error 403: Forbidden")
    assert not is_video_gone("Read timed out")
    assert not is_video_gone("")


def test_replace_only_when_strictly_wider() -> None:
    assert should_replace(1280, 854)
    assert should_replace(854, 0)  # file was missing/unreadable
    assert not should_replace(854, 854)  # 480p-only source: keep the old file
    assert not should_replace(640, 854)  # never downgrade


def test_image_width_reads_webp_and_treats_missing_as_zero(tmp_path: Path) -> None:
    from PIL import Image

    lowres = tmp_path / "abc12345678_10.webp"
    Image.new("RGB", (854, 480)).save(lowres, format="WEBP")
    assert _image_width(lowres) == 854

    assert _image_width(tmp_path / "does-not-exist.webp") == 0

    corrupt = tmp_path / "abc12345678_11.webp"
    corrupt.write_bytes(b"not an image")
    assert _image_width(corrupt) == 0
