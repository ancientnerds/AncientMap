# SPDX-License-Identifier: AGPL-3.0-only
"""Live research events must survive the worker/API process boundary.

Since the 2026-08-08 container split the pipeline runs in theo-worker while
GET /theo/research/{id}/stream is served by api/api2. The events lived in a
plain in-process dict, so the reader always saw an empty list: every live view
sat on "CONNECTING / AWAITING PIPELINE" until the 5-minute idle timeout, for
over a month, while the run itself was perfectly healthy.

These tests pin the Redis bridge that carries them across, and the elapsed
clock that made a 7-hour run read as "1629:28:49".
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from api.services import theo_worker

_ROOT = Path(__file__).resolve().parents[2]


class FakeRedis:
    """Just enough Redis: the list ops the bridge uses, plus TTL bookkeeping."""

    def __init__(self):
        self.lists: dict[str, list[str]] = {}
        self.ttls: dict[str, int] = {}

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    def expire(self, key, ttl):
        self.ttls[key] = ttl

    def lrange(self, key, start, end):
        items = self.lists.get(key, [])
        return items[start:] if end == -1 else items[start : end + 1]

    def delete(self, key):
        self.lists.pop(key, None)
        self.ttls.pop(key, None)

    def pipeline(self):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, client):
        self._client = client
        self._queued = []

    def rpush(self, key, value):
        self._queued.append(("rpush", key, value))

    def expire(self, key, ttl):
        self._queued.append(("expire", key, ttl))

    def execute(self):
        for op, key, arg in self._queued:
            getattr(self._client, op)(key, arg)
        self._queued.clear()


@pytest.fixture
def redis(monkeypatch):
    client = FakeRedis()
    monkeypatch.setattr(theo_worker, "get_redis_client", lambda: client)
    monkeypatch.setattr(theo_worker, "_live_events", {})
    return client


REQ = "11111111-2222-3333-4444-555555555555"


class TestCrossProcessDelivery:
    def test_reader_sees_events_without_the_writer_s_memory(self, redis, monkeypatch):
        """The regression itself: the API process never ran _process_request,
        so its _live_events has no key for this id. Redis must carry it."""
        theo_worker._live_events[REQ] = []
        theo_worker._append_event(REQ, {"type": "pipeline", "stage": "web_search"})

        # Hard cut to a fresh process: same Redis, empty local dict.
        monkeypatch.setattr(theo_worker, "_live_events", {})
        assert theo_worker.get_live_events(REQ) == [{"type": "pipeline", "stage": "web_search"}]

    def test_cursor_returns_only_new_events(self, redis):
        theo_worker._live_events[REQ] = []
        for i in range(3):
            theo_worker._append_event(REQ, {"type": "progress", "n": i})

        assert len(theo_worker.get_live_events(REQ)) == 3
        tail = theo_worker.get_live_events(REQ, start=2)
        assert tail == [{"type": "progress", "n": 2}]

    def test_backlog_replays_for_a_browser_opening_mid_run(self, redis):
        """Opening the overlay an hour in must show the run so far, not blank."""
        theo_worker._live_events[REQ] = []
        for i in range(5):
            theo_worker._append_event(REQ, {"type": "progress", "n": i})

        assert [e["n"] for e in theo_worker.get_live_events(REQ)] == [0, 1, 2, 3, 4]

    def test_ttl_is_refreshed_on_every_push(self, redis):
        """A 72h batch run must not have its buffer expire mid-flight."""
        theo_worker._live_events[REQ] = []
        theo_worker._append_event(REQ, {"type": "progress", "n": 0})
        key = f"{theo_worker._EVENTS_KEY_PREFIX}{REQ}"
        assert redis.ttls[key] == theo_worker._EVENTS_TTL_SECONDS

        redis.ttls[key] = 5  # simulate the clock running down
        theo_worker._append_event(REQ, {"type": "progress", "n": 1})
        assert redis.ttls[key] == theo_worker._EVENTS_TTL_SECONDS

    def test_cap_applies_to_both_transports(self, redis):
        """Otherwise the lists diverge and the reader's cursor walks off."""
        theo_worker._live_events[REQ] = []
        for i in range(theo_worker._MAX_EVENTS_PER_REQUEST + 25):
            theo_worker._append_event(REQ, {"type": "progress", "n": i})

        key = f"{theo_worker._EVENTS_KEY_PREFIX}{REQ}"
        assert len(redis.lists[key]) == theo_worker._MAX_EVENTS_PER_REQUEST
        assert len(theo_worker._live_events[REQ]) == theo_worker._MAX_EVENTS_PER_REQUEST

    def test_unregistered_request_is_not_pushed(self, redis):
        """No _live_events key = this process is not running that request."""
        theo_worker._append_event(REQ, {"type": "progress"})
        assert redis.lists == {}

    def test_drop_clears_both_transports(self, redis):
        theo_worker._live_events[REQ] = []
        theo_worker._append_event(REQ, {"type": "done"})
        theo_worker._drop_live_events(REQ)

        assert REQ not in theo_worker._live_events
        assert theo_worker.get_live_events(REQ) == []

    def test_reclaimed_run_starts_from_a_clean_buffer(self, redis):
        """A deferred run re-claimed after the quota back-off must not replay
        the abandoned attempt's events — and must not leave the two transports
        holding different counts, which would walk the reader's cursor off."""
        src = (_ROOT / "api" / "services" / "theo_worker.py").read_text(encoding="utf-8")
        init = src.index("_live_events[request_id] = []")
        assert "_drop_live_events(request_id)" in src[:init]

        theo_worker._live_events[REQ] = []
        theo_worker._append_event(REQ, {"type": "progress", "n": "abandoned"})

        # Re-claim: same clearing sequence _process_request performs.
        theo_worker._drop_live_events(REQ)
        theo_worker._live_events[REQ] = []
        theo_worker._append_event(REQ, {"type": "progress", "n": "fresh"})

        assert [e["n"] for e in theo_worker.get_live_events(REQ)] == ["fresh"]

    def test_events_round_trip_as_json(self, redis):
        """Nested meta must survive the serialize/deserialize hop intact."""
        theo_worker._live_events[REQ] = []
        event = {
            "type": "pipeline",
            "stage": "search_a1b2",
            "status": "done",
            "meta": {"angle": "Panspermia", "total_sources": 42, "round": 3},
        }
        theo_worker._append_event(REQ, event)
        assert theo_worker.get_live_events(REQ)[0] == event


class TestWithoutRedis:
    def test_same_process_still_works(self, monkeypatch):
        """Local dev has no Redis and no container split — the in-process
        list is the whole transport there."""
        monkeypatch.setattr(theo_worker, "get_redis_client", lambda: None)
        monkeypatch.setattr(theo_worker, "_live_events", {})

        theo_worker._live_events[REQ] = []
        theo_worker._append_event(REQ, {"type": "progress", "n": 0})
        assert theo_worker.get_live_events(REQ) == [{"type": "progress", "n": 0}]
        assert theo_worker.get_live_events(REQ, start=1) == []


class TestStreamEndpointConsumesTheCursor:
    def test_generator_advances_by_batch_length(self):
        """cursor = len(events) only held while the reader fetched the WHOLE
        list; with a cursor-scoped fetch it must advance by what it got."""
        src = (_ROOT / "api" / "routes" / "theo.py").read_text(encoding="utf-8")
        assert "get_live_events(request_id, start=cursor)" in src
        assert "cursor += len(new_events)" in src


class TestElapsedClock:
    def test_list_endpoint_exposes_started_at(self):
        src = (_ROOT / "api" / "routes" / "theo.py").read_text(encoding="utf-8")
        assert '"started_at": r.started_at.isoformat() if r.started_at else None' in src

    def test_live_overlay_counts_from_started_at(self):
        """created_at is when the row was QUEUED. A batch row waits weeks in
        the single batch lane, so created_at showed a 7h run as 1629 hours."""
        src = (_ROOT / "ancient-nerds-map" / "src" / "pages" / "TheoPage.tsx").read_text(
            encoding="utf-8"
        )
        assert "setLiveOverlayStartedAt(running.started_at" in src
        assert "setLiveOverlayStartedAt(item.started_at" in src
        assert "setLiveOverlayStartedAt(running.created_at" not in src
        assert "setLiveOverlayStartedAt(item.created_at" not in src


class TestConnectorBreakdown:
    def test_counts_are_post_dedup_and_labelled(self):
        """The UI needs every adapter id the backend can emit to have a label,
        otherwise a connector shows up as a raw snake_case id."""
        handlers = (_ROOT / "pipeline" / "lyra" / "handlers" / "__init__.py").read_text(
            encoding="utf-8"
        )
        assert "def emit_connector_breakdown" in handlers
        assert '"type": "connectors"' in handlers

        sources = (_ROOT / "pipeline" / "lyra" / "theo_sources.py").read_text(encoding="utf-8")
        adapter_ids = set(re.findall(r'self\._adapters\["([a-z_]+)"\]', sources))
        assert adapter_ids, "adapter registration pattern changed"

        ui = (
            _ROOT / "ancient-nerds-map" / "src" / "components" / "theo" / "TheoResearchLive.tsx"
        ).read_text(encoding="utf-8")
        labels = set(re.findall(r"^  ([a-z_]+): '", ui, re.MULTILINE))
        missing = adapter_ids - labels
        assert not missing, f"connectors with no display label: {sorted(missing)}"

    def test_search_handler_emits_after_registering(self):
        """Emitting before register_source would report the previous round."""
        src = (_ROOT / "pipeline" / "lyra" / "handlers" / "angle_search.py").read_text(
            encoding="utf-8"
        )
        assert src.index("register_source(") < src.index("emit_connector_breakdown()")


class TestEventShapeMatchesTheReader:
    def test_stream_names_the_sse_event_from_type(self):
        """The frontend switches on the SSE event name, which the endpoint
        takes from evt["type"] — so "connectors" must be the type value."""
        src = (_ROOT / "api" / "routes" / "theo.py").read_text(encoding="utf-8")
        assert 'event_type = evt.get("type", "progress")' in src

        ui = (
            _ROOT / "ancient-nerds-map" / "src" / "components" / "theo" / "TheoResearchLive.tsx"
        ).read_text(encoding="utf-8")
        assert "case 'connectors':" in ui
