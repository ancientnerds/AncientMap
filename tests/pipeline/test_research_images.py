"""Unit tests for pipeline.lyra.research_images — licensed image enrichment.

Tests image search (mocked network), license filtering, and injection logic.
"""

import re
from unittest.mock import MagicMock, patch

import pytest

from pipeline.lyra.research_images import (
    ALLOWED_LICENSES,
    SourceImage,
    _is_license_allowed,
    _significant_keywords,
    inject_source_images,
    search_museum_images,
    search_wikimedia_images,
)

# ---------------------------------------------------------------------------
# TestLicenseAllowlist
# ---------------------------------------------------------------------------


class TestLicenseAllowlist:
    def test_cc0_allowed(self):
        assert _is_license_allowed("CC0")
        assert _is_license_allowed("CC0 1.0")

    def test_public_domain_allowed(self):
        assert _is_license_allowed("Public domain")
        assert _is_license_allowed("Public Domain")

    def test_cc_by_sa_allowed(self):
        assert _is_license_allowed("CC BY-SA 4.0")
        assert _is_license_allowed("CC BY-SA 3.0")
        assert _is_license_allowed("CC BY-SA 2.0")

    def test_cc_by_allowed(self):
        assert _is_license_allowed("CC BY 4.0")
        assert _is_license_allowed("CC BY 3.0")

    def test_cc_by_nc_rejected(self):
        """Non-commercial licenses are NOT allowed."""
        assert not _is_license_allowed("CC BY-NC 4.0")
        assert not _is_license_allowed("CC BY-NC-SA 4.0")
        assert not _is_license_allowed("CC BY-NC-ND 4.0")

    def test_cc_by_nd_rejected(self):
        """No-derivatives licenses are NOT allowed."""
        assert not _is_license_allowed("CC BY-ND 4.0")

    def test_empty_string_rejected(self):
        assert not _is_license_allowed("")

    def test_unknown_license_rejected(self):
        assert not _is_license_allowed("All rights reserved")
        assert not _is_license_allowed("Copyright 2024")
        assert not _is_license_allowed("Fair use")

    def test_variant_with_suffix_allowed(self):
        """CC BY-SA 4.0 International is still allowed."""
        assert _is_license_allowed("CC BY-SA 4.0 International")
        assert _is_license_allowed("CC BY 3.0 Unported")


# ---------------------------------------------------------------------------
# TestSearchWikimediaImages (mocked network)
# ---------------------------------------------------------------------------


class TestSearchWikimediaImages:
    def _mock_commons_response(self):
        return {
            "query": {
                "pages": {
                    "123": {
                        "title": "File:Gobekli_Tepe_pillar.jpg",
                        "imageinfo": [{
                            "mime": "image/jpeg",
                            "thumburl": "https://upload.wikimedia.org/thumb/Gobekli_Tepe_pillar.jpg",
                            "url": "https://upload.wikimedia.org/Gobekli_Tepe_pillar.jpg",
                            "extmetadata": {
                                "LicenseShortName": {"value": "CC BY-SA 4.0"},
                                "Artist": {"value": "<a href='...'>Klaus-Peter Simon</a>"},
                                "ImageDescription": {"value": "T-shaped limestone pillar at Gobekli Tepe"},
                            },
                        }],
                    },
                    "456": {
                        "title": "File:Unlicensed_photo.jpg",
                        "imageinfo": [{
                            "mime": "image/jpeg",
                            "thumburl": "https://upload.wikimedia.org/thumb/Unlicensed.jpg",
                            "url": "https://upload.wikimedia.org/Unlicensed.jpg",
                            "extmetadata": {
                                "LicenseShortName": {"value": "CC BY-NC-ND 3.0"},
                                "Artist": {"value": "Someone"},
                                "ImageDescription": {"value": "Should be rejected"},
                            },
                        }],
                    },
                }
            }
        }

    @patch("pipeline.lyra.research_images.httpx.get")
    def test_returns_licensed_images(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = self._mock_commons_response()
        mock_get.return_value = mock_resp

        results = search_wikimedia_images("Gobekli Tepe", ["archaeology"])

        assert len(results) == 1  # Only the CC BY-SA one
        assert results[0].license == "CC BY-SA 4.0"
        assert "Klaus-Peter Simon" in results[0].author
        assert results[0].url.startswith("https://")

    @patch("pipeline.lyra.research_images.httpx.get")
    def test_attribution_populated(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = self._mock_commons_response()
        mock_get.return_value = mock_resp

        results = search_wikimedia_images("Gobekli Tepe", [])

        img = results[0]
        assert "Klaus-Peter Simon" in img.attribution
        assert "Wikimedia Commons" in img.attribution
        assert "CC BY-SA 4.0" in img.attribution

    @patch("pipeline.lyra.research_images.httpx.get")
    def test_rejects_nc_license(self, mock_get):
        """CC BY-NC-ND image should be filtered out."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = self._mock_commons_response()
        mock_get.return_value = mock_resp

        results = search_wikimedia_images("test", [])

        # Only the CC BY-SA image passes
        for img in results:
            assert "NC" not in img.license
            assert "ND" not in img.license

    @patch("pipeline.lyra.research_images.httpx.get")
    def test_empty_response_returns_empty(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"query": {"pages": {}}}
        mock_get.return_value = mock_resp

        results = search_wikimedia_images("nonexistent topic", [])
        assert results == []

    @patch("pipeline.lyra.research_images.httpx.get")
    def test_api_error_returns_empty(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp

        results = search_wikimedia_images("test", [])
        assert results == []


# ---------------------------------------------------------------------------
# TestSearchMuseumImages (mocked network)
# ---------------------------------------------------------------------------


class TestSearchMuseumImages:
    @patch("pipeline.lyra.research_images.httpx.get")
    @patch("pipeline.lyra.research_images.time.sleep")  # Don't actually sleep in tests
    def test_returns_cc0_images(self, mock_sleep, mock_get):
        # First call: search returns object IDs
        search_resp = MagicMock()
        search_resp.status_code = 200
        search_resp.json.return_value = {"objectIDs": [12345]}

        # Second call: object details
        obj_resp = MagicMock()
        obj_resp.status_code = 200
        obj_resp.json.return_value = {
            "objectID": 12345,
            "title": "Statue of Gudea",
            "isPublicDomain": True,
            "primaryImageSmall": "https://images.metmuseum.org/CRDImages/an/12345.jpg",
            "primaryImage": "https://images.metmuseum.org/CRDImages/an/12345_full.jpg",
            "artistDisplayName": "",
            "objectDate": "ca. 2090 B.C.",
            "department": "Ancient Near Eastern Art",
            "culture": "Neo-Sumerian",
            "medium": "Diorite",
            "objectURL": "https://www.metmuseum.org/art/collection/search/12345",
        }

        mock_get.side_effect = [search_resp, obj_resp]

        results = search_museum_images("Sumerian sculpture", ["ancient"])

        assert len(results) == 1
        img = results[0]
        assert img.license == "CC0"
        assert "Metropolitan Museum" in img.attribution
        assert "Public Domain" in img.attribution
        assert "Gudea" in img.alt_text
        assert img.url == "https://images.metmuseum.org/CRDImages/an/12345.jpg"

    @patch("pipeline.lyra.research_images.httpx.get")
    def test_rejects_non_public_domain(self, mock_get):
        search_resp = MagicMock()
        search_resp.status_code = 200
        search_resp.json.return_value = {"objectIDs": [99999]}

        obj_resp = MagicMock()
        obj_resp.status_code = 200
        obj_resp.json.return_value = {
            "objectID": 99999,
            "title": "Copyrighted Work",
            "isPublicDomain": False,
            "primaryImageSmall": "https://images.metmuseum.org/99999.jpg",
        }

        mock_get.side_effect = [search_resp, obj_resp]

        results = search_museum_images("test", [])
        assert results == []

    @patch("pipeline.lyra.research_images.httpx.get")
    def test_no_results_returns_empty(self, mock_get):
        search_resp = MagicMock()
        search_resp.status_code = 200
        search_resp.json.return_value = {"objectIDs": None}
        mock_get.return_value = search_resp

        results = search_museum_images("xyznonexistent", [])
        assert results == []


# ---------------------------------------------------------------------------
# TestInjectSourceImages
# ---------------------------------------------------------------------------


class TestInjectSourceImages:
    def _make_paper(self) -> str:
        return (
            "# Ancient Construction Techniques\n\n"
            "## Abstract\n\n"
            "This paper investigates ancient construction methods.\n\n"
            "## Analysis of Gobekli Tepe\n\n"
            "The site at Gobekli Tepe features massive limestone pillars arranged in circles. "
            "These T-shaped monoliths were carved from the bedrock using stone tools and "
            "represent some of the earliest monumental architecture. [1] [2]\n\n"
            "## Egyptian Pyramid Construction\n\n"
            "The Great Pyramid at Giza was constructed using limestone blocks quarried nearby. "
            "Workers transported these blocks using a system of ramps and sledges across "
            "the desert landscape to the construction site. [3] [4]\n\n"
            "## References\n\n"
            "[1] Source A — https://example.com/a\n"
            "[2] Source B — https://example.com/b\n"
            "[3] Source C — https://example.com/c\n"
            "[4] Source D — https://example.com/d\n"
        )

    def _make_image(self, topic: str, url: str = "https://example.com/img.jpg") -> SourceImage:
        return SourceImage(
            url=url,
            alt_text=f"Image of {topic}",
            attribution="Author, Wikimedia Commons, CC BY-SA 4.0",
            source_url="https://commons.wikimedia.org/wiki/File:Test.jpg",
            license="CC BY-SA 4.0",
            keywords=_significant_keywords(topic),
            quality_score=3,
            author="Test Author",
        )

    def test_images_inserted_after_matching_paragraph(self):
        paper = self._make_paper()
        images = [self._make_image("Gobekli Tepe limestone pillars archaeology")]

        result = inject_source_images(paper, images)

        # Image should be placed near the Gobekli Tepe section
        assert "![Image of Gobekli Tepe" in result
        assert "*Author, Wikimedia Commons, CC BY-SA 4.0*" in result
        # Should be AFTER the Gobekli section content
        gobekli_idx = result.index("T-shaped monoliths")
        img_idx = result.index("![Image of Gobekli Tepe")
        assert img_idx > gobekli_idx

    def test_max_images_respected(self):
        paper = self._make_paper()
        images = [
            self._make_image(f"topic {i}", url=f"https://example.com/{i}.jpg")
            for i in range(10)
        ]

        result = inject_source_images(paper, images, max_images=2)

        count = result.count("![")
        assert count <= 2

    def test_no_images_returns_unchanged(self):
        paper = self._make_paper()
        result = inject_source_images(paper, [])
        assert result == paper

    def test_image_markdown_format(self):
        paper = self._make_paper()
        img = self._make_image("Gobekli Tepe limestone pillars monoliths")

        result = inject_source_images(paper, [img])

        # Check markdown format: ![alt](url) followed by *attribution*
        assert "![Image of Gobekli Tepe limestone pillars monoliths](https://example.com/img.jpg)" in result
        assert "*Author, Wikimedia Commons, CC BY-SA 4.0*" in result

    def test_images_not_placed_in_references_section(self):
        paper = self._make_paper()
        # Image with keywords matching references section content
        img = self._make_image("Source example reference bibliography")

        result = inject_source_images(paper, [img])

        # If placed, it should be before References, not inside it
        refs_idx = result.index("## References")
        img_positions = [m.start() for m in re.finditer(r"!\[", result)]
        for pos in img_positions:
            assert pos < refs_idx

    def test_images_not_placed_in_abstract(self):
        paper = self._make_paper()
        # Image with keywords matching abstract
        img = self._make_image("investigates ancient construction methods paper")

        result = inject_source_images(paper, [img])

        # Abstract section should remain image-free
        abstract_idx = result.index("## Abstract")
        next_section_idx = result.index("## Analysis")
        img_positions = [m.start() for m in re.finditer(r"!\[", result)]
        for pos in img_positions:
            assert not (abstract_idx < pos < next_section_idx)

    def test_unlicensed_image_rejected(self):
        paper = self._make_paper()
        img = SourceImage(
            url="https://example.com/stolen.jpg",
            alt_text="Stolen image",
            attribution="",
            source_url="",
            license="All rights reserved",  # NOT in allowlist
            keywords=_significant_keywords("Gobekli Tepe pillars limestone"),
            quality_score=3,
        )

        result = inject_source_images(paper, [img])
        assert result == paper  # Nothing injected

    def test_quality_score_sorting(self):
        paper = self._make_paper()
        low_quality = SourceImage(
            url="https://example.com/low.jpg",
            alt_text="Low quality Gobekli Tepe image",
            attribution="Author A, Commons, CC0",
            source_url="https://example.com",
            license="CC0",
            keywords=_significant_keywords("Gobekli Tepe limestone pillars"),
            quality_score=1,
        )
        high_quality = SourceImage(
            url="https://example.com/high.jpg",
            alt_text="High quality Gobekli Tepe detailed photo",
            attribution="Author B, Commons, CC BY-SA 4.0",
            source_url="https://example.com",
            license="CC BY-SA 4.0",
            keywords=_significant_keywords("Gobekli Tepe limestone pillars"),
            quality_score=3,
        )

        # High quality should be preferred even if listed second
        result = inject_source_images(paper, [low_quality, high_quality], max_images=1)
        assert "high.jpg" in result
        assert "low.jpg" not in result
