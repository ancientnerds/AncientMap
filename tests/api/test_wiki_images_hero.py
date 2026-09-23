# SPDX-License-Identifier: AGPL-3.0-only
"""The founder hero tools write a 1600 px hero, never an upscale, and report the hero's own file.

`POST /api/wiki-images/{site_id}/set-hero` downscaled every new hero to `HERO_WIDTH = 800` until
2026-09-23, while the pages that show the hero want 1600x900 (plan 6.3, design entry 7 of
`output/remediation/logs/design_texts_images_2026-09-22.json`). `GET /hero-status` built every
path from the literal `hero.webp`, which since the 2026-09-20 hero repair is the demoted file on
every site whose flag moved to a gallery image.

DB-less: the endpoint runs against `tests/fake_sql.RecordingSession` (strict about `text()`), the
remote image through an `httpx.MockTransport`, and the image directory is a tmp path.
"""

from __future__ import annotations

import asyncio
from io import BytesIO

import httpx
import pytest
from PIL import Image

from api.routes import wiki_images
from tests.fake_sql import RecordingSession

SITE_ID = "abcdef12-3456-4789-8abc-def012345678"


def _jpeg(width: int, height: int, mode: str = "RGB") -> bytes:
    buf = BytesIO()
    Image.new(mode, (width, height), (120, 90, 60) if mode == "RGB" else 0).save(buf, "JPEG")
    return buf.getvalue()


def _size_of_webp(data: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(data)) as img:
        assert img.format == "WEBP"
        return img.size


# --------------------------------------------------------------------------------------
# the renderer
# --------------------------------------------------------------------------------------


def test_a_wide_source_becomes_a_1600_px_hero_with_its_aspect_kept():
    webp, width, height = wiki_images.render_hero_webp(_jpeg(3200, 1800))
    assert (width, height) == (1600, 900)
    assert _size_of_webp(webp) == (1600, 900)


def test_a_source_narrower_than_the_hero_width_is_never_upscaled():
    webp, width, height = wiki_images.render_hero_webp(_jpeg(1200, 900))
    assert (width, height) == (1200, 900)
    assert _size_of_webp(webp) == (1200, 900)


def test_a_cmyk_source_is_converted_instead_of_failing_the_request():
    """WebP has no CMYK mode; the old code converted only RGBA and P and raised on CMYK."""
    webp, width, height = wiki_images.render_hero_webp(_jpeg(2000, 1000, mode="CMYK"))
    assert (width, height) == (1600, 800)
    with Image.open(BytesIO(webp)) as img:
        assert img.mode == "RGB"


# --------------------------------------------------------------------------------------
# set-hero, end to end without a database
# --------------------------------------------------------------------------------------


def _fake_async_client(payload: bytes):
    real = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload, headers={"content-type": "image/jpeg"})

    def factory(*args, **kwargs):
        return real(*args, transport=httpx.MockTransport(handler), **kwargs)

    return factory


def test_set_hero_stores_a_1600_px_file_and_records_its_real_size(tmp_path, monkeypatch):
    monkeypatch.setattr(wiki_images, "IMAGE_DIR", tmp_path)
    monkeypatch.setattr(wiki_images, "cache_delete_pattern", lambda pattern: 0)
    monkeypatch.setattr(wiki_images.httpx, "AsyncClient", _fake_async_client(_jpeg(4000, 2250)))
    db = RecordingSession(
        {
            "SELECT id FROM unified_sites": [(SITE_ID,)],
            "RETURNING id": [(4242,)],
        }
    )
    body = wiki_images.SetHeroRequest(
        image_url="https://upload.wikimedia.org/wikipedia/commons/a/ab/Temple.jpg",
        attribution_url="https://commons.wikimedia.org/wiki/File:Temple.jpg",
    )
    out = asyncio.run(wiki_images.set_hero(SITE_ID, body, db=db, _user=None))

    assert out["success"] is True
    stored = tmp_path / "abcdef12" / "hero.webp"
    assert _size_of_webp(stored.read_bytes()) == (1600, 900)
    ((sql, params),) = [(s, p) for s, p in db.log if "INSERT INTO wiki_images" in s]
    assert (params["w"], params["h"]) == (1600, 900)
    assert db.commits == 1


# --------------------------------------------------------------------------------------
# hero-status
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("filename", ["Temple_gate.webp", "hero.webp"])
def test_hero_status_names_the_hero_rows_own_file(filename):
    db = RecordingSession(
        {
            "WHERE is_hero = true": [
                (SITE_ID, "https://upload.wikimedia.org/x.jpg", "https://commons/x", filename)
            ]
        }
    )
    out = asyncio.run(wiki_images.get_hero_status(db=db))
    assert out[SITE_ID]["path"] == f"/data/images/wiki/abcdef12/{filename}"
    assert "filename" in db.statement_with("WHERE is_hero = true").split("FROM wiki_images")[0]
