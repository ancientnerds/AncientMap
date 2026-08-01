# SPDX-License-Identifier: AGPL-3.0-only
"""Data-API prefilter: shorts + members-only/private out BEFORE the proxy fetch.

playlistItems delivers no duration — shorts and unaired premieres used to pull
the full watch-page (~0.3 MB residential traffic) through Webshare before the
min_video_minutes check could drop them. The prefilter asks videos.list
(1 quota unit per 50 IDs, no proxy) first:

- ID missing from the response -> private/members-only/deleted -> skipped row.
- 0 < duration < min_video_minutes (covers shorts) -> skipped row.
- Duration 0/unknown (livestream/premiere, PT0S/P0D) -> NOT skipped.
- liveBroadcastContent upcoming/live -> defer without row, no proxy contact.
- API error/quota -> fall back to the old unfiltered behavior.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pipeline.lyra.channels as channels_mod
import pipeline.lyra.transcript_fetcher as tf
import pipeline.utils.http as http_mod
from pipeline.lyra.config import LyraSettings

VID = "VIDpre000001"


def _settings(**kwargs) -> LyraSettings:
    base = {"youtube_api_key": "test-key", "min_video_minutes": 5.0}
    base.update(kwargs)
    return LyraSettings(**base)


def _video(vid: str = VID) -> dict:
    return {
        "id": vid,
        "title": "Kandidat",
        "published_at": datetime(2026, 8, 1, tzinfo=UTC),
        "thumbnail_url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
        "description": "playlist snippet",
    }


def _meta(
    duration_minutes: float | None = 10.0,
    live: str = "none",
    description: str = "full description",
    tags: list[str] | None = None,
) -> dict:
    return {
        "duration_minutes": duration_minutes,
        "live_broadcast_content": live,
        "description": description,
        "tags": tags if tags is not None else ["archaeology"],
    }


class _FakeQuery:
    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return []


class _FakeSession:
    def __init__(self) -> None:
        self.added: list = []

    def query(self, *args, **kwargs):
        return _FakeQuery()

    def add(self, obj) -> None:
        self.added.append(obj)


def _setup(monkeypatch, batch_result: dict | None) -> tuple[_FakeSession, list[str], list[str]]:
    """Mock channel, playlist discovery, batch call, transcript and per-video
    metadata fetch. Returns (session, transcript_calls, per_video_meta_calls)."""
    session = _FakeSession()

    @contextmanager
    def fake_get_session():
        yield session

    monkeypatch.setattr(tf, "get_session", fake_get_session)
    monkeypatch.setattr(
        channels_mod,
        "get_enabled_channels",
        lambda: [SimpleNamespace(id="UCtest", name="Demo")],
    )
    monkeypatch.setattr(tf, "get_recent_videos", lambda ch, days, key: [_video()])
    monkeypatch.setattr(tf, "_fetch_videos_metadata_batch", lambda ids, key: batch_result)

    transcript_calls: list[str] = []

    def spy_fetch(video_id, settings):
        transcript_calls.append(video_id)
        return "[00:00] hallo", 9.5

    monkeypatch.setattr(tf, "fetch_transcript", spy_fetch)

    meta_calls: list[str] = []

    def spy_meta(video_id, api_key):
        meta_calls.append(video_id)
        return {"description": "per-video description", "tags": ["fallback"]}

    monkeypatch.setattr(tf, "_fetch_metadata_youtube_api", spy_meta)
    return session, transcript_calls, meta_calls


def test_missing_from_data_api_skips_without_proxy(monkeypatch) -> None:
    session, transcript_calls, _ = _setup(monkeypatch, batch_result={})

    total = tf.fetch_new_videos(_settings())

    assert transcript_calls == []  # no proxy fetch!
    assert total == 0
    assert len(session.added) == 1
    assert session.added[0].status == "skipped"


def test_short_video_skips_without_proxy(monkeypatch) -> None:
    session, transcript_calls, _ = _setup(monkeypatch, {VID: _meta(duration_minutes=2.0)})

    total = tf.fetch_new_videos(_settings())

    assert transcript_calls == []
    assert total == 0
    assert len(session.added) == 1
    assert session.added[0].status == "skipped"
    assert session.added[0].duration_minutes == 2.0


def test_zero_duration_live_or_premiere_is_not_skipped(monkeypatch) -> None:
    # Livestreams/premieres report PT0S/P0D — must NOT count as "too short",
    # otherwise real videos get permanently skipped.
    session, transcript_calls, _ = _setup(monkeypatch, {VID: _meta(duration_minutes=0.0)})

    total = tf.fetch_new_videos(_settings())

    assert transcript_calls == [VID]
    assert total == 1
    assert session.added[0].status == "transcribed"
    # API duration 0 is not trusted — transcript-derived duration wins
    assert session.added[0].duration_minutes == 9.5


def test_upcoming_premiere_deferred_without_proxy_or_row(monkeypatch) -> None:
    session, transcript_calls, _ = _setup(
        monkeypatch, {VID: _meta(duration_minutes=None, live="upcoming")}
    )

    total = tf.fetch_new_videos(_settings())

    assert transcript_calls == []  # no watch-page burned per cycle anymore
    assert total == 0
    assert session.added == []  # no row -> re-checked next cycle


def test_normal_video_fetches_and_enriches_from_batch(monkeypatch) -> None:
    session, transcript_calls, meta_calls = _setup(monkeypatch, {VID: _meta()})

    total = tf.fetch_new_videos(_settings())

    assert transcript_calls == [VID]
    assert meta_calls == []  # enrichment from the prefilter call, no second videos.list
    assert total == 1
    video = session.added[0]
    assert video.status == "transcribed"
    assert video.description == "full description"
    assert video.tags == ["archaeology"]
    assert video.duration_minutes == 10.0  # API duration beats transcript estimate


def test_api_error_falls_back_to_old_behavior(monkeypatch) -> None:
    session, transcript_calls, meta_calls = _setup(monkeypatch, batch_result=None)

    total = tf.fetch_new_videos(_settings())

    # Prefilter gone, but the pipeline keeps working like before.
    assert transcript_calls == [VID]
    assert meta_calls == [VID]
    assert total == 1
    video = session.added[0]
    assert video.status == "transcribed"
    assert video.description == "per-video description"
    assert video.tags == ["fallback"]


def test_parse_iso8601_duration_minutes() -> None:
    assert tf._parse_iso8601_duration_minutes("PT1H2M3S") == (3600 + 120 + 3) / 60.0
    assert tf._parse_iso8601_duration_minutes("PT45S") == 0.75
    assert tf._parse_iso8601_duration_minutes("PT0S") == 0.0
    assert tf._parse_iso8601_duration_minutes("P0D") is None  # livestream artifact
    assert tf._parse_iso8601_duration_minutes(None) is None
    assert tf._parse_iso8601_duration_minutes("") is None


class _FakeResp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_batch_fetch_parses_items_and_omits_missing_ids(monkeypatch) -> None:
    payload = {
        "items": [
            {
                "id": VID,
                "snippet": {
                    "liveBroadcastContent": "none",
                    "description": "desc",
                    "tags": ["a"],
                },
                "contentDetails": {"duration": "PT10M30S"},
            }
        ]
    }
    monkeypatch.setattr(http_mod, "fetch_with_retry", lambda url, **kw: _FakeResp(payload))

    result = tf._fetch_videos_metadata_batch([VID, "VIDgone00001"], "key")

    assert result is not None
    assert result[VID]["duration_minutes"] == 10.5
    assert result[VID]["live_broadcast_content"] == "none"
    assert "VIDgone00001" not in result  # private/deleted — API omits it


def test_batch_fetch_returns_none_on_api_error(monkeypatch) -> None:
    def boom(url, **kwargs):
        raise RuntimeError("quotaExceeded")

    monkeypatch.setattr(http_mod, "fetch_with_retry", boom)

    assert tf._fetch_videos_metadata_batch([VID], "key") is None
