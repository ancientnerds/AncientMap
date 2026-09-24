# SPDX-License-Identifier: AGPL-3.0-only
"""The Wikidata P18 thumbnail Lyra stores on a radar card must be a width Wikimedia serves.

Wikimedia answers any width outside its fixed buckets with HTTP 400 ("Use thumbnail sizes listed
on https://w.wiki/GHai"). The card thumbnails were built at 300px: on 2026-09-24 every one of
the 30 such `user_contributions.thumbnail_url` values was a 400, and the radar card fell back to
the story screenshot - Chaco Canyon showed a frame of the Stennis Space Center.
"""

import hashlib

from pipeline.lyra import site_identifier
from pipeline.wiki_image_downloader import COMMONS_BUCKETS


class _Resp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def _entity_with_image(image: str) -> dict:
    claim = {"mainsnak": {"datavalue": {"value": image}}}
    return {"entities": {"Q1": {"claims": {"P18": [claim]}, "sitelinks": {}, "labels": {}}}}


def _thumb_for(monkeypatch, image: str) -> str:
    monkeypatch.setattr(
        site_identifier, "fetch_with_retry", lambda *a, **k: _Resp(_entity_with_image(image))
    )
    return site_identifier._enrich_from_wikidata("Q1")["thumbnail_url"]


def test_the_card_thumbnail_width_is_a_wikimedia_bucket():
    assert site_identifier.RADAR_THUMB_WIDTH in COMMONS_BUCKETS


def test_p18_thumbnail_is_built_at_the_bucket_width(monkeypatch):
    name = "Spean_Praptos_1.JPG"
    md5 = hashlib.md5(name.encode(), usedforsecurity=False).hexdigest()
    assert _thumb_for(monkeypatch, "Spean Praptos 1.JPG") == (
        f"https://upload.wikimedia.org/wikipedia/commons/thumb/{md5[0]}/{md5[0:2]}/{name}/330px-{name}"
    )


def test_an_svg_thumbnail_keeps_the_png_suffix(monkeypatch):
    url = _thumb_for(monkeypatch, "Plan of a temple.svg")
    assert url.endswith("/330px-Plan_of_a_temple.svg.png")
