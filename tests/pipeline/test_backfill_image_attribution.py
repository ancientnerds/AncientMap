# SPDX-License-Identifier: AGPL-3.0-only
"""The attribution backfill's pure pieces.

49,766 wiki_images rows came from a one-day importer (2026-03-14) that left
author, license AND commons_page_url NULL — Commons licences require
attribution. The only key it left behind is the local filename stem.
"""

from __future__ import annotations

from unittest.mock import patch

from pipeline.image_attribution_backfill import fetch_batch, title_candidates
from pipeline.wiki_image_downloader import parse_attribution


class TestTitleCandidates:
    def test_webp_extension_is_swapped(self):
        assert title_candidates("Pedra das Cabras.webp", "jpg") == "File:Pedra das Cabras.jpg"

    def test_spaces_survive_mediawiki_treats_them_as_underscores(self):
        assert (
            title_candidates("Pedra das Cabras Ribeira (7).webp", "JPG")
            == "File:Pedra das Cabras Ribeira (7).JPG"
        )

    def test_non_webp_name_is_used_as_stem(self):
        # 8 'manual' rows carry other extensions; the stem guess still applies.
        assert title_candidates("hero", "png") == "File:hero.png"


class TestParseAttribution:
    def test_artist_html_is_stripped_and_url_kept(self):
        info = {
            "url": "https://upload.wikimedia.org/x/y/Foo.jpg",
            "width": 4000,
            "height": 3000,
            "extmetadata": {
                "Artist": {"value": '<a href="//commons.wikimedia.org/wiki/User:J">J. Doe</a>'},
                "LicenseShortName": {"value": "CC BY-SA 4.0"},
                "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0"},
            },
        }
        meta = parse_attribution(info)
        assert meta["author"] == "J. Doe"
        assert meta["author_url"] == "https://commons.wikimedia.org/wiki/User:J"
        assert meta["license"] == "CC BY-SA 4.0"
        assert meta["original_url"] == "https://upload.wikimedia.org/x/y/Foo.jpg"

    def test_missing_metadata_stays_none_not_empty_string(self):
        meta = parse_attribution({"url": "https://u/x.jpg", "extmetadata": {}})
        assert meta["author"] is None
        assert meta["license"] is None


class TestFetchBatchMapping:
    """The API rewrites titles twice (normalisation, redirects) — results must
    map back onto the QUERIED title or every row misses, which is exactly the
    lookup bug pattern that left the March import without metadata."""

    def _api(self, payload):
        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return payload

        return _Resp()

    def test_normalised_and_redirected_titles_map_back(self):
        payload = {
            "query": {
                "normalized": [{"from": "File:a_b.jpg", "to": "File:A b.jpg"}],
                "redirects": [{"from": "File:A b.jpg", "to": "File:A b (renamed).jpg"}],
                "pages": {
                    "1": {
                        "title": "File:A b (renamed).jpg",
                        "imageinfo": [
                            {
                                "url": "https://upload.wikimedia.org/a.jpg",
                                "extmetadata": {
                                    "Artist": {"value": "X"},
                                    "LicenseShortName": {"value": "CC0"},
                                },
                            }
                        ],
                    }
                },
            }
        }
        with patch(
            "pipeline.image_attribution_backfill._http_client.get",
            return_value=self._api(payload),
        ):
            out = fetch_batch(["File:a_b.jpg"])
        assert "File:a_b.jpg" in out
        assert out["File:a_b.jpg"]["author"] == "X"
        # The page link points at the CANONICAL (post-redirect) title.
        assert "renamed" in out["File:a_b.jpg"]["commons_page_url"]

    def test_missing_pages_are_absent_not_faked(self):
        payload = {"query": {"pages": {"-1": {"title": "File:Gone.jpg", "missing": ""}}}}
        with patch(
            "pipeline.image_attribution_backfill._http_client.get",
            return_value=self._api(payload),
        ):
            out = fetch_batch(["File:Gone.jpg"])
        assert out == {}
