# SPDX-License-Identifier: AGPL-3.0-only
"""GET /api/sites/all: ``fields=globe`` and one pre-compressed body per cache entry.

The globe's first frame needs nine of the payload's fields (``id,n,la,lo,s,t,p,pn,c``); the
rest (descriptions, citations, reference links, ...) is ~90 % of 10 MB and loads after the
intro. Before this, every request - cache hit or not - walked the 10 MB dict through
``jsonable_encoder``, serialised it and gzipped it at level 9 (TTFB 1.0-1.5 s, measured
2026-09-23). Now a miss builds the payload once, derives both variants, and stores each as
gzip bytes in Redis (shared by api and api2, so ``cache_delete_pattern`` clears both).

DB-less: the route runs against tests/fake_sql.RecordingSession behind a real FastAPI app with
GZipMiddleware (like tests/api/test_landing_html.py), and api/cache.py talks to a dict-backed
fake Redis server with a text and a bytes view of the same store.
"""

from __future__ import annotations

import fnmatch
import gzip
import json
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from api import cache
from api.routes import sites as sr
from pipeline.database import get_db
from tests.fake_sql import RecordingSession

URL = "/api/sites/all?limit=100000&source=ancient_nerds"
GLOBE_KEYS = ("id", "n", "la", "lo", "s", "t", "p", "pn", "c")
KEY_BASE = "sites:all:ancient_nerds:all:all:0:100000:pin=none"
GZIP = {"Accept-Encoding": "gzip"}
IDENTITY = {"Accept-Encoding": "identity"}

ID_1 = "0b6f1c3a-1111-4c2e-9a10-000000000001"
ID_2 = "0b6f1c3a-2222-4c2e-9a10-000000000002"
ID_3 = "0b6f1c3a-3333-4c2e-9a10-000000000003"


def _row(**kw):
    """One row of the /all SELECT, every column present (the route reads them by name)."""
    row = {
        "id": None,
        "name": None,
        "lat": None,
        "lon": None,
        "source_id": "ancient_nerds",
        "site_type": None,
        "period_start": None,
        "period_name": None,
        "description": None,
        "thumbnail_url": None,
        "country": None,
        "source_url": None,
        "edited_by": None,
        "updated_at": None,
        "last_audited": None,
        "card_description": None,
        "confidence_score": None,
        "raw_data": None,
        "hero_url": None,
        "hero_attribution_url": None,
    }
    row.update(kw)
    return SimpleNamespace(**row)


SITE_ROWS = [
    # Every optional field set; non-ASCII text proves ensure_ascii=False is kept.
    _row(
        id=ID_1,
        name="Çatalhöyük",
        lat=37.66667,
        lon=32.82806,
        site_type="Settlement",
        period_start=-7100,
        period_name="Neolithic",
        description="A Neolithic proto-city on the Konya plain – “the” example.",
        thumbnail_url="https://ancientnerds.com/img/catal.webp",
        country="Turkey",
        source_url="https://example.org/catal",
        edited_by="martin",
        updated_at=datetime(2026, 9, 20, 10, 15, tzinfo=UTC),
        last_audited=datetime(2026, 9, 21, 8, 0, tzinfo=UTC),
        card_description="Proto-city.",
        confidence_score=0.8765,
        raw_data={"description_citations": [{"n": 1, "u": "https://example.org/src"}]},
        hero_url="https://upload.wikimedia.org/catal.jpg",
        hero_attribution_url="https://commons.wikimedia.org/wiki/File:Catal.jpg",
    ),
    # The minimum: no pn, no c, no details; "initial" is not an editor; citations in a string.
    _row(
        id=ID_2,
        name="Göbekli Tepe",
        lat=37.22333,
        lon=38.9225,
        site_type="Temple",
        period_start=-9500,
        edited_by="initial",
        raw_data='{"description_citations": []}',
    ),
    # A null period, a zero confidence (kept: it is not None), raw_data without citations.
    _row(
        id=ID_3,
        name="Lascaux",
        lat=45.05361,
        lon=1.16833,
        site_type="Rock art",
        country="France",
        confidence_score=0.0,
        raw_data='{"other": 1}',
    ),
]

REF_ROWS = [
    SimpleNamespace(
        site_id=ID_1,
        content_url="https://example.org/ref-a",
        title="Excavation report",
        link_metadata={"domain": "example.org", "link_type": "paper"},
        relevance_score=0.9,
    ),
    SimpleNamespace(
        site_id=ID_1,
        content_url="https://example.org/ref-b",
        title=None,
        link_metadata=None,
        relevance_score=0.5,
    ),
]

# Captured from the unchanged route (HEAD 5f06b71) with SITE_ROWS/REF_ROWS before the refactor;
# its identity body was byte-identical to JSONResponse(content=EXPECTED_ALL).body.
EXPECTED_ALL: dict = {
    "count": 3,
    "sites": [
        {
            "id": ID_1,
            "n": "Çatalhöyük",
            "la": 37.66667,
            "lo": 32.82806,
            "s": "ancient_nerds",
            "t": "Settlement",
            "p": -7100,
            "pn": "Neolithic",
            "d": "A Neolithic proto-city on the Konya plain – “the” example.",
            "i": "https://ancientnerds.com/img/catal.webp",
            "c": "Turkey",
            "u": "https://example.org/catal",
            "cd": "Proto-city.",
            "cf": 0.88,
            "eb": "martin",
            "ea": "2026-09-20T10:15:00+00:00",
            "aud": "2026-09-21T08:00:00+00:00",
            "hu": "https://upload.wikimedia.org/catal.jpg",
            "ha": "https://commons.wikimedia.org/wiki/File:Catal.jpg",
            "dc": [{"n": 1, "u": "https://example.org/src"}],
            "rf": [
                {
                    "u": "https://example.org/ref-a",
                    "t": "Excavation report",
                    "d": "example.org",
                    "k": "paper",
                },
                {"u": "https://example.org/ref-b", "t": "", "d": "", "k": "article"},
            ],
        },
        {
            "id": ID_2,
            "n": "Göbekli Tepe",
            "la": 37.22333,
            "lo": 38.9225,
            "s": "ancient_nerds",
            "t": "Temple",
            "p": -9500,
            "dc": [],
        },
        {
            "id": ID_3,
            "n": "Lascaux",
            "la": 45.05361,
            "lo": 1.16833,
            "s": "ancient_nerds",
            "t": "Rock art",
            "p": None,
            "c": "France",
            "cf": 0.0,
        },
    ],
    "dataSource": "postgres",
}


def _globe(payload: dict) -> dict:
    return {**payload, "sites": [{k: s[k] for k in GLOBE_KEYS if k in s} for s in payload["sites"]]}


class FakeRedis:
    """One view of a fake Redis server: the calls api/cache.py makes, over a shared store.

    ``decode_responses=True`` decodes every reply as UTF-8 like redis-py's text client does,
    so a gzip body read through it raises UnicodeDecodeError - the reason the bytes client
    exists.
    """

    def __init__(self, store: dict[str, bytes], ttls: dict[str, int], *, decode_responses: bool):
        self.store = store
        self.ttls = ttls
        self.decode_responses = decode_responses

    def _out(self, value: bytes):
        return value.decode("utf-8") if self.decode_responses else value

    def get(self, key):
        value = self.store.get(key)
        return None if value is None else self._out(value)

    def setex(self, key, ttl, value):
        self.store[key] = value if isinstance(value, bytes) else str(value).encode("utf-8")
        self.ttls[key] = ttl

    def scan(self, cursor, match=None, count=None):
        keys = [k for k in self.store if fnmatch.fnmatchcase(k, match or "*")]
        return 0, [self._out(k.encode("utf-8")) for k in keys]

    def delete(self, *keys):
        removed = 0
        for key in keys:
            name = key.decode("utf-8") if isinstance(key, bytes) else key
            if self.store.pop(name, None) is not None:
                self.ttls.pop(name, None)
                removed += 1
        return removed


@pytest.fixture
def redis_store(monkeypatch):
    store: dict[str, bytes] = {}
    ttls: dict[str, int] = {}
    monkeypatch.setattr(
        cache, "get_redis_client", lambda: FakeRedis(store, ttls, decode_responses=True)
    )
    monkeypatch.setattr(
        cache, "get_redis_bytes_client", lambda: FakeRedis(store, ttls, decode_responses=False)
    )
    monkeypatch.setattr(cache, "_memory_cache", {})
    return SimpleNamespace(store=store, ttls=ttls)


@pytest.fixture(autouse=True)
def _no_limits(monkeypatch):
    monkeypatch.setattr(sr._heavy_limiter, "check", lambda ip: True)


@contextmanager
def _client(db, pins=None):
    app = FastAPI()
    app.add_middleware(GZipMiddleware, minimum_size=500)
    app.include_router(sr.router, prefix="/api/sites")
    app.dependency_overrides[get_db] = lambda: db
    with (
        patch("api.routes.snapshots.get_active_pins", return_value=pins or {}),
        TestClient(app) as client,
    ):
        yield client


def _db():
    return RecordingSession(
        {"FROM unified_sites us": SITE_ROWS, "FROM site_content_links": REF_ROWS}
    )


def _site_reads(db) -> int:
    return sum(1 for sql in db.statements() if "FROM unified_sites us" in sql)


# --------------------------------------------------------------------------------------
# payload shape
# --------------------------------------------------------------------------------------


def test_globe_fields_keep_only_what_the_first_frame_draws(redis_store):
    with _client(_db()) as client:
        resp = client.get(URL + "&fields=globe", headers=GZIP)
    assert resp.status_code == 200
    body = resp.json()
    assert body == _globe(EXPECTED_ALL)
    assert body["count"] == 3 and body["dataSource"] == "postgres"
    by_id = {s["id"]: s for s in body["sites"]}
    assert set(by_id[ID_1]) == set(GLOBE_KEYS)
    # absent stays absent; p stays even when null (it is always sent)
    assert set(by_id[ID_2]) == {"id", "n", "la", "lo", "s", "t", "p"}
    assert by_id[ID_3]["p"] is None and by_id[ID_3]["c"] == "France"


@pytest.mark.parametrize("query", ["", "&fields=all"])
def test_default_and_all_are_todays_payload_byte_for_byte(redis_store, query):
    assert EXPECTED_ALL["sites"][0]["rf"]  # the fixture exercises every branch of the mapping
    with _client(_db()) as client:
        plain = client.get(URL + query, headers=IDENTITY)
        zipped = client.get(URL + query, headers=GZIP)
    # today: FastAPI's JSONResponse rendering of the dict
    assert plain.content == JSONResponse(content=EXPECTED_ALL).body
    assert zipped.json() == EXPECTED_ALL


# --------------------------------------------------------------------------------------
# encoding
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("fields", ["all", "globe"])
def test_gzip_is_applied_exactly_once_and_varies_on_accept_encoding(redis_store, fields):
    with _client(_db()) as client:
        zipped = client.get(f"{URL}&fields={fields}", headers=GZIP)
        plain = client.get(f"{URL}&fields={fields}", headers=IDENTITY)
    assert zipped.headers.get_list("content-encoding") == ["gzip"]
    assert "Accept-Encoding" in zipped.headers["vary"]
    assert zipped.headers["content-type"].startswith("application/json")
    zipped.json()  # httpx decodes once: a double-compressed body would not parse

    assert "content-encoding" not in plain.headers
    assert "Accept-Encoding" in plain.headers["vary"]
    assert plain.headers["content-type"].startswith("application/json")
    assert json.loads(plain.content) == zipped.json()


# --------------------------------------------------------------------------------------
# the shared bytes cache
# --------------------------------------------------------------------------------------


def test_one_request_fills_both_variants_from_one_database_read(redis_store):
    db = _db()
    with _client(db) as client:
        client.get(URL + "&fields=globe", headers=GZIP)
        assert sorted(redis_store.store) == [f"{KEY_BASE}:f=all", f"{KEY_BASE}:f=globe"]
        assert redis_store.ttls == {f"{KEY_BASE}:f=all": 1800, f"{KEY_BASE}:f=globe": 1800}
        assert _site_reads(db) == 1
        assert json.loads(gzip.decompress(redis_store.store[f"{KEY_BASE}:f=all"])) == EXPECTED_ALL
        client.get(URL, headers=GZIP)
    assert _site_reads(db) == 1


def test_a_warm_hit_reads_no_database_and_compresses_nothing(redis_store):
    db = _db()
    with (
        _client(db) as client,
        patch.object(gzip, "compress", wraps=gzip.compress) as compress,
    ):
        client.get(URL, headers=GZIP)
        statements, compressions = len(db.log), compress.call_count
        assert compressions == 2  # both variants, once
        for fields in ("all", "globe"):
            for headers in (GZIP, IDENTITY):
                assert client.get(f"{URL}&fields={fields}", headers=headers).status_code == 200
    assert len(db.log) == statements
    assert compress.call_count == compressions


@pytest.mark.parametrize("pattern", ["sites:*", "sites:all:*"])
def test_the_existing_invalidations_clear_both_variants(redis_store, pattern):
    db = _db()
    with _client(db) as client:
        client.get(URL + "&fields=globe", headers=GZIP)
        assert len(redis_store.store) == 2
        assert cache.cache_delete_pattern(pattern) == 2
        assert redis_store.store == {}
        client.get(URL + "&fields=globe", headers=GZIP)
    assert _site_reads(db) == 2


def test_pinned_snapshot_sites_without_optional_keys_project(redis_store, tmp_path, monkeypatch):
    """Snapshot files omit t/p/pn/c when empty (pipeline/static_exporter.py)."""
    snap = {
        "sites": [
            {"id": "keep-1", "n": "Stonehenge", "la": 51.17, "lo": -1.83, "s": "ancient_nerds"},
            {
                "id": "keep-2",
                "n": "Avebury",
                "la": 51.43,
                "lo": -1.85,
                "s": "ancient_nerds",
                "p": -2850,
                "d": "A henge.",
                "rl": [{"u": "https://example.org"}],
            },
        ]
    }
    (tmp_path / "2026-09-01_120000.json").write_text(json.dumps(snap), encoding="utf-8")
    monkeypatch.setattr("api.routes.snapshots.SNAPSHOTS_DIR", tmp_path)
    db = RecordingSession()
    with _client(db, pins={"ancient_nerds": "2026-09-01_120000"}) as client:
        resp = client.get(URL + "&fields=globe", headers=GZIP)
    assert resp.status_code == 200
    assert resp.json() == {
        "count": 2,
        "sites": [
            {"id": "keep-1", "n": "Stonehenge", "la": 51.17, "lo": -1.83, "s": "ancient_nerds"},
            {
                "id": "keep-2",
                "n": "Avebury",
                "la": 51.43,
                "lo": -1.85,
                "s": "ancient_nerds",
                "p": -2850,
            },
        ],
        "dataSource": "snapshot",
    }
    pinned_base = "sites:all:ancient_nerds:all:all:0:100000:pin=ancient_nerds=2026-09-01_120000"
    assert sorted(redis_store.store) == [f"{pinned_base}:f=all", f"{pinned_base}:f=globe"]


def test_an_unknown_fields_value_is_rejected_with_422(redis_store):
    db = _db()
    with _client(db) as client:
        resp = client.get(URL + "&fields=bogus", headers=GZIP)
    assert resp.status_code == 422
    assert db.log == []


# --------------------------------------------------------------------------------------
# api/cache.py bytes helpers
# --------------------------------------------------------------------------------------


def test_bytes_round_trip_through_redis_untouched(redis_store):
    body = gzip.compress(b'{"a":1}', mtime=0)
    cache.cache_set_bytes("k:1", body, ttl=60)
    assert redis_store.store["k:1"] == body and redis_store.ttls["k:1"] == 60
    assert cache.cache_get_bytes("k:1") == body
    assert cache.cache_get_bytes("k:missing") is None


def test_bytes_use_the_process_memory_while_redis_is_down(monkeypatch):
    monkeypatch.setattr(cache, "get_redis_bytes_client", lambda: None)
    monkeypatch.setattr(cache, "_memory_cache", {})
    body = b"\x1f\x8b\x08\x00binary"
    cache.cache_set_bytes("k:mem", body, ttl=60)
    assert cache.cache_get_bytes("k:mem") == body
    assert cache.cache_delete_pattern("k:*") == 1
    assert cache.cache_get_bytes("k:mem") is None


def test_a_redis_error_on_bytes_drops_the_connection_and_uses_memory(monkeypatch):
    class Broken:
        def setex(self, *a):
            raise ConnectionError("gone")

        def get(self, key):
            raise ConnectionError("gone")

    lost: list[str] = []
    monkeypatch.setattr(cache, "get_redis_bytes_client", lambda: Broken())
    monkeypatch.setattr(cache, "mark_redis_lost", lambda ctx, exc: lost.append(ctx))
    monkeypatch.setattr(cache, "_memory_cache", {})
    cache.cache_set_bytes("k:err", b"x", ttl=60)
    assert cache.cache_get_bytes("k:err") == b"x"
    assert lost == ["set k:err", "get k:err"]


def test_the_bytes_client_does_not_decode_and_shares_the_cooldown(monkeypatch):
    import redis

    calls: list[dict] = []

    class Conn:
        def __init__(self, kwargs):
            self.kwargs = kwargs

        def ping(self):
            return True

    def from_url(url, **kwargs):
        calls.append(kwargs)
        return Conn(kwargs)

    monkeypatch.setattr(redis, "from_url", from_url)
    monkeypatch.setattr(cache, "_redis_client", None)
    monkeypatch.setattr(cache, "_redis_bytes_client", None)
    monkeypatch.setattr(cache, "_redis_failed_at", None)
    monkeypatch.setattr(cache, "_redis_state", "init")

    text_client = cache.get_redis_client()
    bytes_client = cache.get_redis_bytes_client()
    assert text_client.kwargs == {"decode_responses": True}
    assert bytes_client.kwargs == {"decode_responses": False}
    assert cache.get_redis_bytes_client() is bytes_client  # a singleton, like the text client

    cache.mark_redis_lost("test", RuntimeError("boom"))
    assert cache._redis_client is None and cache._redis_bytes_client is None
    assert cache.get_redis_bytes_client() is None  # inside the cooldown: no reconnect
    assert cache.get_redis_client() is None
    assert len(calls) == 2
